package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port                string
	GRPCPort            string
	DatabaseURL         string
	RedisURL            string
	MinioEndpoint       string
	MinioAccessKey      string
	MinioSecretKey      string
	MinioBucketEpisodes string
	JWTSecret           string
	JWTExpireHours      int
	DatasetServiceURL   string
	TaskServiceURL      string
}

func Load() *Config {
	expHours, _ := strconv.Atoi(getEnv("JWT_EXPIRE_HOURS", "24"))
	return &Config{
		Port:                getEnv("GATEWAY_PORT", "8000"),
		GRPCPort:            getEnv("GRPC_PORT", "9090"),
		DatabaseURL:         mustEnv("DATABASE_URL"),
		RedisURL:            getEnv("REDIS_URL", "redis://localhost:6379/0"),
		MinioEndpoint:       getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:      getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey:      getEnv("MINIO_SECRET_KEY", "minioadmin123"),
		MinioBucketEpisodes: getEnv("MINIO_BUCKET_EPISODES", "episodes"),
		JWTSecret:           mustEnv("JWT_SECRET"),
		JWTExpireHours:      expHours,
		DatasetServiceURL:   getEnv("DATASET_SERVICE_URL", "http://localhost:8100"),
		TaskServiceURL:      getEnv("TASK_SERVICE_URL", "http://localhost:8200"),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func mustEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic("required env var not set: " + key)
	}
	return v
}
