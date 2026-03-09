package grpcserver

import (
	"bytes"
	"encoding/binary"
	"sort"
	"sync"
	"time"

	pb "github.com/embedai/datahub/shared/proto"
	"google.golang.org/protobuf/proto"
)

// FrameBuffer accumulates StreamFrames in memory with a sliding-window eviction policy.
// Frames older than maxAge (relative to the latest received timestamp) are dropped.
// All methods are safe for concurrent use.
type FrameBuffer struct {
	mu      sync.Mutex
	frames  []*pb.StreamFrame
	maxAge  time.Duration
	lastSeq uint64
}

func NewFrameBuffer(maxAge time.Duration) *FrameBuffer {
	return &FrameBuffer{maxAge: maxAge}
}

// Add appends a frame and evicts any frames that fall outside the sliding window.
func (b *FrameBuffer) Add(f *pb.StreamFrame) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.frames = append(b.frames, f)
	if f.SeqNum > b.lastSeq {
		b.lastSeq = f.SeqNum
	}
	if f.TimestampNs > 0 {
		b.evictExpired(f.TimestampNs)
	}
}

// LastSeq returns the highest seq_num seen so far.
func (b *FrameBuffer) LastSeq() uint64 {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.lastSeq
}

// Len returns the number of buffered frames.
func (b *FrameBuffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.frames)
}

// Reset discards all buffered frames (called after a successful seal).
func (b *FrameBuffer) Reset() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.frames = b.frames[:0]
	b.lastSeq = 0
}

// Serialize returns all frames sorted by seq_num encoded as a
// length-prefixed protobuf byte stream suitable for storage.
//
// Wire format: repeated [ 4-byte big-endian length | protobuf-encoded StreamFrame ]
func (b *FrameBuffer) Serialize() ([]byte, error) {
	b.mu.Lock()
	snapshot := make([]*pb.StreamFrame, len(b.frames))
	copy(snapshot, b.frames)
	b.mu.Unlock()

	sort.Slice(snapshot, func(i, j int) bool {
		return snapshot[i].SeqNum < snapshot[j].SeqNum
	})

	var buf bytes.Buffer
	for _, f := range snapshot {
		data, err := proto.Marshal(f)
		if err != nil {
			return nil, err
		}
		var lenBuf [4]byte
		binary.BigEndian.PutUint32(lenBuf[:], uint32(len(data)))
		buf.Write(lenBuf[:])
		buf.Write(data)
	}
	return buf.Bytes(), nil
}

// evictExpired removes frames whose timestamp is older than (nowNs - maxAge).
// Must be called with b.mu held.
func (b *FrameBuffer) evictExpired(nowNs int64) {
	cutoff := nowNs - b.maxAge.Nanoseconds()
	n := 0
	for _, f := range b.frames {
		if f.TimestampNs >= cutoff {
			b.frames[n] = f
			n++
		}
	}
	b.frames = b.frames[:n]
}
