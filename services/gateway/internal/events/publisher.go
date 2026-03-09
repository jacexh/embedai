package events

import (
	"context"

	"github.com/redis/go-redis/v9"
)

// Publisher publishes domain events to Redis Streams.
type Publisher struct {
	client *redis.Client
}

func NewPublisher(redisURL string) (*Publisher, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &Publisher{client: redis.NewClient(opt)}, nil
}

// PublishEpisodeIngested emits an event to the "episodes:ingested" stream.
func (p *Publisher) PublishEpisodeIngested(ctx context.Context, episodeID, storagePath, format string) error {
	return p.client.XAdd(ctx, &redis.XAddArgs{
		Stream: "episodes:ingested",
		Values: map[string]interface{}{
			"episode_id":   episodeID,
			"storage_path": storagePath,
			"format":       format,
		},
	}).Err()
}

func (p *Publisher) Close() error {
	return p.client.Close()
}
