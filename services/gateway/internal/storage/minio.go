package storage

import (
	"context"
	"fmt"
	"io"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

const ChunkSize = 64 * 1024 * 1024 // 64 MB

type MinioStorage struct {
	client *minio.Client
	bucket string
}

func NewMinioStorage(endpoint, accessKey, secretKey, bucket string) (*MinioStorage, error) {
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: false,
	})
	if err != nil {
		return nil, err
	}
	return &MinioStorage{client: client, bucket: bucket}, nil
}

// EnsureBucket creates the bucket if it does not exist.
func (s *MinioStorage) EnsureBucket(ctx context.Context) error {
	exists, err := s.client.BucketExists(ctx, s.bucket)
	if err != nil {
		return err
	}
	if !exists {
		return s.client.MakeBucket(ctx, s.bucket, minio.MakeBucketOptions{})
	}
	return nil
}

// UploadChunk stores a single chunk under tmp/{sessionID}/chunk_{n:05d}.
func (s *MinioStorage) UploadChunk(ctx context.Context, sessionID string, chunkN int, data io.Reader, size int64) error {
	key := fmt.Sprintf("tmp/%s/chunk_%05d", sessionID, chunkN)
	_, err := s.client.PutObject(ctx, s.bucket, key, data, size, minio.PutObjectOptions{})
	return err
}

// AssembleChunks uses MinIO server-side compose to merge all chunks into destPath.
func (s *MinioStorage) AssembleChunks(ctx context.Context, sessionID string, totalChunks int, destPath string) error {
	sources := make([]minio.CopySrcOptions, totalChunks)
	for i := range sources {
		sources[i] = minio.CopySrcOptions{
			Bucket: s.bucket,
			Object: fmt.Sprintf("tmp/%s/chunk_%05d", sessionID, i),
		}
	}
	_, err := s.client.ComposeObject(ctx, minio.CopyDestOptions{
		Bucket: s.bucket,
		Object: destPath,
	}, sources...)
	return err
}

// DeleteChunks removes all temporary chunk objects for a session (best-effort).
func (s *MinioStorage) DeleteChunks(ctx context.Context, sessionID string, totalChunks int) {
	for i := 0; i < totalChunks; i++ {
		key := fmt.Sprintf("tmp/%s/chunk_%05d", sessionID, i)
		_ = s.client.RemoveObject(ctx, s.bucket, key, minio.RemoveObjectOptions{})
	}
}

// PutObject uploads an in-memory payload directly to destPath.
func (s *MinioStorage) PutObject(ctx context.Context, key string, data io.Reader, size int64) error {
	_, err := s.client.PutObject(ctx, s.bucket, key, data, size, minio.PutObjectOptions{})
	return err
}
