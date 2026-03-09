package handler

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/embedai/datahub/gateway/internal/repo"
	"github.com/embedai/datahub/gateway/internal/storage"
)

const uploadChunkSize = 64 * 1024 * 1024 // 64 MB

// EpisodeRepository is the subset of repo.EpisodeRepo used by UploadHandler.
type EpisodeRepository interface {
	CreateEpisode(ctx context.Context, ep *repo.Episode) error
	GetEpisode(ctx context.Context, episodeID string) (*repo.Episode, error)
	UpdateEpisodeStatus(ctx context.Context, episodeID, status, storagePath string) error
	CreateUploadSession(ctx context.Context, s *repo.UploadSession) error
	GetUploadSession(ctx context.Context, sessionID string) (*repo.UploadSession, error)
	IncrementReceivedChunks(ctx context.Context, sessionID string) error
	CompleteSession(ctx context.Context, sessionID string) error
}

// EventPublisher is the subset of events.Publisher used by UploadHandler.
type EventPublisher interface {
	PublishEpisodeIngested(ctx context.Context, episodeID, storagePath, format string) error
}

// UploadHandler handles the multipart chunked upload API.
type UploadHandler struct {
	episodeRepo EpisodeRepository
	storage     *storage.MinioStorage
	publisher   EventPublisher
}

func NewUploadHandler(episodeRepo EpisodeRepository, storage *storage.MinioStorage, publisher EventPublisher) *UploadHandler {
	return &UploadHandler{
		episodeRepo: episodeRepo,
		storage:     storage,
		publisher:   publisher,
	}
}

// POST /api/v1/episodes/upload/init
// Body: { filename, size_bytes, format, checksum?, project_id? }
// Response 201: { episode_id, session_id, chunk_size, total_chunks }
func (h *UploadHandler) Init(c *gin.Context) {
	var req struct {
		Filename  string `json:"filename"  binding:"required"`
		SizeBytes int64  `json:"size_bytes" binding:"required,min=1"`
		Format    string `json:"format"     binding:"required,oneof=mcap hdf5"`
		Checksum  string `json:"checksum"`
		ProjectID string `json:"project_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// JWT project_id takes priority; body can override for admins.
	projectID := c.GetString("project_id")
	if req.ProjectID != "" {
		projectID = req.ProjectID
	}

	ep := &repo.Episode{
		ProjectID: projectID,
		Filename:  req.Filename,
		Format:    req.Format,
		SizeBytes: req.SizeBytes,
	}
	if err := h.episodeRepo.CreateEpisode(c.Request.Context(), ep); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create episode"})
		return
	}

	totalChunks := int(math.Ceil(float64(req.SizeBytes) / float64(uploadChunkSize)))
	sess := &repo.UploadSession{
		EpisodeID:        ep.ID,
		TotalChunks:      totalChunks,
		ChunkSizeBytes:   uploadChunkSize,
		ChecksumExpected: req.Checksum,
		ExpiresAt:        time.Now().Add(24 * time.Hour),
	}
	if err := h.episodeRepo.CreateUploadSession(c.Request.Context(), sess); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create upload session"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"episode_id":   ep.ID,
		"session_id":   sess.ID,
		"chunk_size":   uploadChunkSize,
		"total_chunks": totalChunks,
	})
}

// PUT /api/v1/episodes/upload/:session_id/chunk/:n
// Body: raw binary chunk data (Content-Length required)
func (h *UploadHandler) UploadChunk(c *gin.Context) {
	sessionID := c.Param("session_id")

	chunkN, err := strconv.Atoi(c.Param("n"))
	if err != nil || chunkN < 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid chunk number"})
		return
	}

	sess, err := h.episodeRepo.GetUploadSession(c.Request.Context(), sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}
	if sess.Status != "in_progress" {
		c.JSON(http.StatusConflict, gin.H{"error": "session not in progress"})
		return
	}
	if chunkN >= sess.TotalChunks {
		c.JSON(http.StatusBadRequest, gin.H{"error": "chunk number out of range"})
		return
	}

	size := c.Request.ContentLength
	if err := h.storage.UploadChunk(c.Request.Context(), sessionID, chunkN, c.Request.Body, size); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to store chunk"})
		return
	}

	if err := h.episodeRepo.IncrementReceivedChunks(c.Request.Context(), sessionID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update session"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"chunk": chunkN, "status": "received"})
}

// POST /api/v1/episodes/upload/:session_id/complete
// Validates all chunks received, assembles file, updates DB, publishes event.
func (h *UploadHandler) Complete(c *gin.Context) {
	sessionID := c.Param("session_id")

	sess, err := h.episodeRepo.GetUploadSession(c.Request.Context(), sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}
	if sess.Status != "in_progress" {
		c.JSON(http.StatusConflict, gin.H{"error": "session not in progress"})
		return
	}
	if sess.ReceivedChunks != sess.TotalChunks {
		c.JSON(http.StatusBadRequest, gin.H{
			"error": fmt.Sprintf("expected %d chunks, received %d", sess.TotalChunks, sess.ReceivedChunks),
		})
		return
	}

	ep, err := h.episodeRepo.GetEpisode(c.Request.Context(), sess.EpisodeID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch episode"})
		return
	}

	storagePath := fmt.Sprintf("episodes/%s/%s", ep.ID, ep.Filename)
	if err := h.storage.AssembleChunks(c.Request.Context(), sessionID, sess.TotalChunks, storagePath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to assemble chunks"})
		return
	}

	if err := h.episodeRepo.CompleteSession(c.Request.Context(), sessionID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to mark session complete"})
		return
	}

	if err := h.episodeRepo.UpdateEpisodeStatus(c.Request.Context(), ep.ID, "processing", storagePath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update episode"})
		return
	}

	// Publish event; non-fatal – pipeline will pick up via DB polling as fallback.
	_ = h.publisher.PublishEpisodeIngested(c.Request.Context(), ep.ID, storagePath, ep.Format)

	// Clean up temp chunks asynchronously.
	go h.storage.DeleteChunks(context.Background(), sessionID, sess.TotalChunks)

	c.JSON(http.StatusOK, gin.H{
		"episode_id":   ep.ID,
		"storage_path": storagePath,
		"status":       "processing",
	})
}
