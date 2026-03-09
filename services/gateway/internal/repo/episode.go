package repo

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Episode mirrors the episodes table (fields used by the gateway).
type Episode struct {
	ID          string
	ProjectID   string
	Filename    string
	Format      string
	SizeBytes   int64
	Status      string
	StoragePath string
}

// UploadSession mirrors the upload_sessions table.
type UploadSession struct {
	ID               string
	EpisodeID        string
	TotalChunks      int
	ReceivedChunks   int
	ChunkSizeBytes   int
	ChecksumExpected string
	Status           string
	ExpiresAt        time.Time
}

type EpisodeRepo struct {
	db *pgxpool.Pool
}

func NewEpisodeRepo(db *pgxpool.Pool) *EpisodeRepo {
	return &EpisodeRepo{db: db}
}

// CreateEpisode inserts a new episode with status='uploading' and populates ep.ID.
func (r *EpisodeRepo) CreateEpisode(ctx context.Context, ep *Episode) error {
	ep.ID = uuid.New().String()
	_, err := r.db.Exec(ctx,
		`INSERT INTO episodes (id, project_id, filename, format, size_bytes, status)
		 VALUES ($1, $2, $3, $4, $5, 'uploading')`,
		ep.ID, ep.ProjectID, ep.Filename, ep.Format, ep.SizeBytes,
	)
	return err
}

// GetEpisode retrieves an episode by ID.
func (r *EpisodeRepo) GetEpisode(ctx context.Context, episodeID string) (*Episode, error) {
	ep := &Episode{}
	var storagePath *string
	err := r.db.QueryRow(ctx,
		`SELECT id, project_id, filename, format, size_bytes, status, storage_path
		 FROM episodes WHERE id=$1`,
		episodeID,
	).Scan(&ep.ID, &ep.ProjectID, &ep.Filename, &ep.Format, &ep.SizeBytes, &ep.Status, &storagePath)
	if err != nil {
		return nil, err
	}
	if storagePath != nil {
		ep.StoragePath = *storagePath
	}
	return ep, nil
}

// UpdateEpisodeStatus updates episode status and storage_path.
func (r *EpisodeRepo) UpdateEpisodeStatus(ctx context.Context, episodeID, status, storagePath string) error {
	_, err := r.db.Exec(ctx,
		`UPDATE episodes SET status=$2, storage_path=NULLIF($3,''), ingested_at=NOW() WHERE id=$1`,
		episodeID, status, storagePath,
	)
	return err
}

// CreateUploadSession inserts a new upload session and populates s.ID.
func (r *EpisodeRepo) CreateUploadSession(ctx context.Context, s *UploadSession) error {
	s.ID = uuid.New().String()
	_, err := r.db.Exec(ctx,
		`INSERT INTO upload_sessions
		   (id, episode_id, total_chunks, chunk_size_bytes, checksum_expected, expires_at)
		 VALUES ($1, $2, $3, $4, $5, $6)`,
		s.ID, s.EpisodeID, s.TotalChunks, s.ChunkSizeBytes, s.ChecksumExpected, s.ExpiresAt,
	)
	return err
}

// GetUploadSession retrieves a session by ID.
func (r *EpisodeRepo) GetUploadSession(ctx context.Context, sessionID string) (*UploadSession, error) {
	s := &UploadSession{}
	err := r.db.QueryRow(ctx,
		`SELECT id, episode_id, total_chunks, received_chunks, chunk_size_bytes, status
		 FROM upload_sessions WHERE id=$1`,
		sessionID,
	).Scan(&s.ID, &s.EpisodeID, &s.TotalChunks, &s.ReceivedChunks, &s.ChunkSizeBytes, &s.Status)
	if err != nil {
		return nil, err
	}
	return s, nil
}

// IncrementReceivedChunks atomically increments received_chunks.
func (r *EpisodeRepo) IncrementReceivedChunks(ctx context.Context, sessionID string) error {
	_, err := r.db.Exec(ctx,
		`UPDATE upload_sessions SET received_chunks = received_chunks + 1 WHERE id=$1`,
		sessionID,
	)
	return err
}

// CompleteSession marks the session as completed.
func (r *EpisodeRepo) CompleteSession(ctx context.Context, sessionID string) error {
	_, err := r.db.Exec(ctx,
		`UPDATE upload_sessions SET status='completed' WHERE id=$1`,
		sessionID,
	)
	return err
}

// CreateEpisodeFromStream creates an episode record for a streamed recording.
// recordingSessionID is stored in the metadata JSONB column to support reconnect linking.
func (r *EpisodeRepo) CreateEpisodeFromStream(ctx context.Context, ep *Episode, recordingSessionID string) error {
	ep.ID = uuid.New().String()
	meta, _ := json.Marshal(map[string]string{"recording_session_id": recordingSessionID})
	_, err := r.db.Exec(ctx,
		`INSERT INTO episodes (id, project_id, filename, format, size_bytes, status, metadata)
		 VALUES ($1, $2, $3, $4, $5, 'processing', $6::jsonb)`,
		ep.ID, ep.ProjectID, ep.Filename, ep.Format, ep.SizeBytes, string(meta),
	)
	return err
}
