package grpcserver_test

import (
	"context"
	"encoding/binary"
	"io"
	"testing"
	"time"

	pb "github.com/embedai/datahub/shared/proto"
	"github.com/google/uuid"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/proto"

	grpcserver "github.com/embedai/datahub/gateway/internal/grpc"
	"github.com/embedai/datahub/gateway/internal/repo"
)

// --- fakes ---

type fakeEpisodeStore struct {
	episodes map[string]*repo.Episode
}

func newFakeEpisodeStore() *fakeEpisodeStore {
	return &fakeEpisodeStore{episodes: make(map[string]*repo.Episode)}
}

func (s *fakeEpisodeStore) CreateEpisodeFromStream(_ context.Context, ep *repo.Episode, _ string) error {
	ep.ID = uuid.New().String()
	ep.Status = "processing"
	s.episodes[ep.ID] = ep
	return nil
}

func (s *fakeEpisodeStore) UpdateEpisodeStatus(_ context.Context, id, status, path string) error {
	if ep, ok := s.episodes[id]; ok {
		ep.Status = status
		ep.StoragePath = path
	}
	return nil
}

type fakeObjectStorage struct {
	objects map[string][]byte
}

func newFakeObjectStorage() *fakeObjectStorage {
	return &fakeObjectStorage{objects: make(map[string][]byte)}
}

func (s *fakeObjectStorage) PutObject(_ context.Context, key string, data io.Reader, _ int64) error {
	b, err := io.ReadAll(data)
	if err != nil {
		return err
	}
	s.objects[key] = b
	return nil
}

type fakeEventBus struct {
	events []string
}

func (b *fakeEventBus) PublishEpisodeIngested(_ context.Context, episodeID, _, _ string) error {
	b.events = append(b.events, episodeID)
	return nil
}

// --- bidi stream stub ---

// noopServerStream satisfies grpc.ServerStream with no-ops so the fake
// can embed it without panicking.
type noopServerStream struct{}

func (noopServerStream) SetHeader(metadata.MD) error  { return nil }
func (noopServerStream) SendHeader(metadata.MD) error { return nil }
func (noopServerStream) SetTrailer(metadata.MD)       {}
func (noopServerStream) Context() context.Context     { return context.Background() }
func (noopServerStream) SendMsg(any) error            { return nil }
func (noopServerStream) RecvMsg(any) error            { return nil }

// fakeBidiStream simulates a gRPC bidirectional stream for OpenStream.
type fakeBidiStream struct {
	noopServerStream
	ctx    context.Context
	input  []*pb.StreamFrame
	pos    int
	output []*pb.StreamAck
}

func newFakeBidiStream(ctx context.Context, frames []*pb.StreamFrame) *fakeBidiStream {
	return &fakeBidiStream{ctx: ctx, input: frames}
}

func (s *fakeBidiStream) Context() context.Context { return s.ctx }

func (s *fakeBidiStream) Recv() (*pb.StreamFrame, error) {
	if s.pos >= len(s.input) {
		return nil, io.EOF
	}
	f := s.input[s.pos]
	s.pos++
	return f, nil
}

func (s *fakeBidiStream) Send(ack *pb.StreamAck) error {
	s.output = append(s.output, ack)
	return nil
}

// --- helpers ---

func makeFrames(sessionID string, count int, markLastIndex int) []*pb.StreamFrame {
	frames := make([]*pb.StreamFrame, count)
	now := time.Now().UnixNano()
	for i := range frames {
		frames[i] = &pb.StreamFrame{
			SessionId:   sessionID,
			SeqNum:      uint64(i),
			TimestampNs: now + int64(i)*int64(time.Millisecond),
			Topic:       "/camera/image_raw",
			Payload:     []byte("data"),
		}
	}
	if markLastIndex >= 0 && markLastIndex < count {
		frames[markLastIndex].IsLast = true
	}
	return frames
}

// --- tests ---

func TestStreamServer_NormalFlow(t *testing.T) {
	store := newFakeEpisodeStore()
	objStore := newFakeObjectStorage()
	bus := &fakeEventBus{}

	srv := grpcserver.NewStreamServer(store, objStore, bus)

	sessionID := uuid.New().String()
	frames := makeFrames(sessionID, 10, 9) // is_last on frame 9

	stream := newFakeBidiStream(context.Background(), frames)
	if err := srv.OpenStream(stream); err != nil {
		t.Fatalf("OpenStream returned error: %v", err)
	}

	// Each frame should have received an ACK.
	if len(stream.output) != 10 {
		t.Errorf("expected 10 ACKs, got %d", len(stream.output))
	}
	// Sequence numbers should be in order.
	for i, ack := range stream.output {
		if ack.LastAckSeq != uint64(i) {
			t.Errorf("ACK[%d]: expected seq %d, got %d", i, i, ack.LastAckSeq)
		}
	}
	// Final ACK should carry the episode_id.
	finalAck := stream.output[len(stream.output)-1]
	if finalAck.EpisodeId == "" {
		t.Error("final ACK must carry non-empty episode_id")
	}

	if len(store.episodes) != 1 {
		t.Errorf("expected 1 episode record, got %d", len(store.episodes))
	}
	if len(bus.events) != 1 {
		t.Errorf("expected 1 ingestion event, got %d", len(bus.events))
	}
}

func TestStreamServer_EOFSealsEpisode(t *testing.T) {
	store := newFakeEpisodeStore()
	objStore := newFakeObjectStorage()
	bus := &fakeEventBus{}

	srv := grpcserver.NewStreamServer(store, objStore, bus)

	sessionID := uuid.New().String()
	frames := makeFrames(sessionID, 5, -1) // no is_last — client disconnects

	stream := newFakeBidiStream(context.Background(), frames)
	if err := srv.OpenStream(stream); err != nil {
		t.Fatalf("OpenStream error: %v", err)
	}

	if len(store.episodes) != 1 {
		t.Errorf("expected episode sealed on EOF, got %d episodes", len(store.episodes))
	}
}

func TestStreamServer_Reconnect(t *testing.T) {
	store := newFakeEpisodeStore()
	objStore := newFakeObjectStorage()
	bus := &fakeEventBus{}

	srv := grpcserver.NewStreamServer(store, objStore, bus)

	sessionID := uuid.New().String()

	// Leg 1: frames 0-4, no is_last (simulates disconnect).
	leg1 := makeFrames(sessionID, 5, -1)
	stream1 := newFakeBidiStream(context.Background(), leg1)
	if err := srv.OpenStream(stream1); err != nil {
		t.Fatalf("leg1 OpenStream error: %v", err)
	}

	// Leg 2: same session_id, frames 5-9, is_last on last.
	leg2 := makeFrames(sessionID, 5, 4)
	for i, f := range leg2 {
		f.SeqNum = uint64(5 + i)
	}
	stream2 := newFakeBidiStream(context.Background(), leg2)
	if err := srv.OpenStream(stream2); err != nil {
		t.Fatalf("leg2 OpenStream error: %v", err)
	}

	// Two separate episode records (one per stream leg).
	if len(store.episodes) != 2 {
		t.Errorf("expected 2 episodes (one per leg), got %d", len(store.episodes))
	}
	// Two ingestion events published.
	if len(bus.events) != 2 {
		t.Errorf("expected 2 ingestion events, got %d", len(bus.events))
	}
}

func TestFrameBuffer_Serialize_OrderedBySeq(t *testing.T) {
	buf := grpcserver.NewFrameBuffer(5 * time.Second)

	// Add frames out of order.
	for _, seq := range []uint64{3, 1, 2, 0} {
		buf.Add(&pb.StreamFrame{
			SeqNum:      seq,
			TimestampNs: time.Now().UnixNano(),
			Payload:     []byte{byte(seq)},
		})
	}

	data, err := buf.Serialize()
	if err != nil {
		t.Fatalf("Serialize: %v", err)
	}
	if len(data) == 0 {
		t.Fatal("expected non-empty serialized output")
	}

	// Deserialize and verify ascending seq_num order.
	offset := 0
	prevSeq := uint64(0)
	first := true
	for offset < len(data) {
		if offset+4 > len(data) {
			t.Fatal("truncated length prefix")
		}
		msgLen := int(binary.BigEndian.Uint32(data[offset : offset+4]))
		offset += 4
		if offset+msgLen > len(data) {
			t.Fatal("truncated message body")
		}
		var f pb.StreamFrame
		if err := proto.Unmarshal(data[offset:offset+msgLen], &f); err != nil {
			t.Fatalf("proto.Unmarshal: %v", err)
		}
		offset += msgLen
		if !first && f.SeqNum < prevSeq {
			t.Errorf("frames out of order: seq %d after %d", f.SeqNum, prevSeq)
		}
		prevSeq = f.SeqNum
		first = false
	}
}
