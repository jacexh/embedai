// Package grpcserver implements the gRPC StreamIngestion service.
// It receives bidirectional streaming frames from robot clients,
// buffers them with a 5-second sliding window, and seals Episodes
// into MinIO + PostgreSQL when the stream ends or times out.
package grpcserver

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log"
	"time"

	pb "github.com/embedai/datahub/shared/proto"
	"google.golang.org/grpc"

	"github.com/embedai/datahub/gateway/internal/repo"
)

const inactivityTimeout = 30 * time.Second

// EpisodeStore is the subset of repo.EpisodeRepo used by StreamServer.
type EpisodeStore interface {
	CreateEpisodeFromStream(ctx context.Context, ep *repo.Episode, recordingSessionID string) error
	UpdateEpisodeStatus(ctx context.Context, episodeID, status, storagePath string) error
}

// ObjectStorage is the subset of storage.MinioStorage used by StreamServer.
type ObjectStorage interface {
	PutObject(ctx context.Context, key string, data io.Reader, size int64) error
}

// EventBus is the subset of events.Publisher used by StreamServer.
type EventBus interface {
	PublishEpisodeIngested(ctx context.Context, episodeID, storagePath, format string) error
}

// StreamServer implements pb.StreamIngestionServer.
type StreamServer struct {
	pb.UnimplementedStreamIngestionServer
	episodes  EpisodeStore
	storage   ObjectStorage
	publisher EventBus
}

func NewStreamServer(episodes EpisodeStore, storage ObjectStorage, publisher EventBus) *StreamServer {
	return &StreamServer{
		episodes:  episodes,
		storage:   storage,
		publisher: publisher,
	}
}

// OpenStream is the bidirectional streaming RPC entrypoint.
// Protocol:
//  1. Client sends StreamFrames; server ACKs each one.
//  2. On frame.is_last=true OR 30 s inactivity → seal episode, return final ACK.
//  3. On client disconnect (io.EOF / context cancel) → seal any pending frames.
func (s *StreamServer) OpenStream(stream grpc.BidiStreamingServer[pb.StreamFrame, pb.StreamAck]) error {
	buf := NewFrameBuffer(5 * time.Second)
	inactivity := time.NewTimer(inactivityTimeout)
	defer inactivity.Stop()

	// recordingSessionID is set from the first frame; subsequent frames must share it.
	var recordingSessionID string
	// currentEpisodeID tracks the episode created for this stream leg.
	var currentEpisodeID string

	recvDone := make(chan struct {
		frame *pb.StreamFrame
		err   error
	}, 1)

	recvNext := func() {
		f, err := stream.Recv()
		recvDone <- struct {
			frame *pb.StreamFrame
			err   error
		}{f, err}
	}

	go recvNext()

	for {
		select {
		case <-inactivity.C:
			if buf.Len() > 0 {
				epID, err := s.sealEpisode(stream.Context(), buf, recordingSessionID)
				if err != nil {
					log.Printf("stream: seal on inactivity timeout: %v", err)
				} else {
					currentEpisodeID = epID
					_ = currentEpisodeID
				}
			}
			return nil

		case result := <-recvDone:
			frame, err := result.frame, result.err

			if err == io.EOF || err == context.Canceled {
				if buf.Len() > 0 {
					if _, err2 := s.sealEpisode(stream.Context(), buf, recordingSessionID); err2 != nil {
						log.Printf("stream: seal on EOF: %v", err2)
					}
				}
				return nil
			}
			if err != nil {
				return err
			}

			// Record session from first frame.
			if recordingSessionID == "" {
				recordingSessionID = frame.SessionId
			}

			inactivity.Reset(inactivityTimeout)
			buf.Add(frame)

			ack := &pb.StreamAck{
				LastAckSeq: frame.SeqNum,
				EpisodeId:  currentEpisodeID,
				Status:     "ok",
			}

			if frame.IsLast {
				epID, err := s.sealEpisode(stream.Context(), buf, recordingSessionID)
				if err != nil {
					log.Printf("stream: seal on is_last: %v", err)
					ack.Status = "error"
				} else {
					ack.EpisodeId = epID
				}
				_ = stream.Send(ack)
				return nil
			}

			if err := stream.Send(ack); err != nil {
				return err
			}

			// Queue next receive.
			go recvNext()
		}
	}
}

// sealEpisode serializes buffered frames, writes them to object storage,
// creates an Episode record, and publishes an ingestion event.
// Returns the new episode's ID.
func (s *StreamServer) sealEpisode(ctx context.Context, buf *FrameBuffer, sessionID string) (string, error) {
	data, err := buf.Serialize()
	if err != nil {
		return "", fmt.Errorf("serialize: %w", err)
	}
	buf.Reset()

	ep := &repo.Episode{
		Filename:  fmt.Sprintf("stream_%s_%d.bin", sessionID, time.Now().UnixNano()),
		Format:    "mcap",
		SizeBytes: int64(len(data)),
	}
	if err := s.episodes.CreateEpisodeFromStream(ctx, ep, sessionID); err != nil {
		return "", fmt.Errorf("create episode: %w", err)
	}

	storagePath := fmt.Sprintf("episodes/%s/stream.bin", ep.ID)
	if err := s.storage.PutObject(ctx, storagePath, bytes.NewReader(data), int64(len(data))); err != nil {
		return "", fmt.Errorf("put object: %w", err)
	}

	if err := s.episodes.UpdateEpisodeStatus(ctx, ep.ID, "processing", storagePath); err != nil {
		return "", fmt.Errorf("update status: %w", err)
	}

	if err := s.publisher.PublishEpisodeIngested(ctx, ep.ID, storagePath, ep.Format); err != nil {
		log.Printf("stream: publish event: %v", err)
	}

	return ep.ID, nil
}
