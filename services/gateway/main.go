package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"google.golang.org/grpc"

	pb "github.com/embedai/datahub/shared/proto"

	"github.com/embedai/datahub/gateway/internal/config"
	"github.com/embedai/datahub/gateway/internal/events"
	grpcserver "github.com/embedai/datahub/gateway/internal/grpc"
	"github.com/embedai/datahub/gateway/internal/handler"
	"github.com/embedai/datahub/gateway/internal/middleware"
	"github.com/embedai/datahub/gateway/internal/repo"
	"github.com/embedai/datahub/gateway/internal/storage"
)

func main() {
	cfg := config.Load()

	// ── Database ──────────────────────────────────────────────────────────
	db, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("failed to connect to database: %v", err)
	}
	defer db.Close()

	// ── Repos ─────────────────────────────────────────────────────────────
	userRepo := repo.NewUserRepo(db)
	episodeRepo := repo.NewEpisodeRepo(db)

	// ── MinIO storage ─────────────────────────────────────────────────────
	minioStorage, err := storage.NewMinioStorage(
		cfg.MinioEndpoint,
		cfg.MinioAccessKey,
		cfg.MinioSecretKey,
		cfg.MinioBucketEpisodes,
	)
	if err != nil {
		log.Fatalf("failed to init MinIO client: %v", err)
	}
	if err := minioStorage.EnsureBucket(context.Background()); err != nil {
		log.Printf("warning: could not ensure MinIO bucket: %v", err)
	}

	// ── Redis event publisher ─────────────────────────────────────────────
	pub, err := events.NewPublisher(cfg.RedisURL)
	if err != nil {
		log.Fatalf("failed to init Redis publisher: %v", err)
	}
	defer pub.Close()

	// ── HTTP handlers ─────────────────────────────────────────────────────
	authHandler := handler.NewAuthHandler(userRepo, cfg.JWTSecret, cfg.JWTExpireHours)
	uploadHandler := handler.NewUploadHandler(episodeRepo, minioStorage, pub)

	proxyHandler, err := handler.NewProxyHandler(cfg.DatasetServiceURL, cfg.TaskServiceURL)
	if err != nil {
		log.Fatalf("failed to init proxy handler: %v", err)
	}

	r := gin.Default()

	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	authGroup := r.Group("/auth")
	{
		authGroup.POST("/login", authHandler.Login)
		authGroup.POST("/register", authHandler.Register)
	}

	api := r.Group("/api/v1")
	api.Use(middleware.Auth(cfg.JWTSecret))
	{
		api.GET("/me", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{
				"user_id":    c.GetString("user_id"),
				"project_id": c.GetString("project_id"),
				"role":       c.GetString("role"),
			})
		})

		upload := api.Group("/episodes/upload")
		{
			upload.POST("/init", uploadHandler.Init)
			upload.PUT("/:session_id/chunk/:n", uploadHandler.UploadChunk)
			upload.POST("/:session_id/complete", uploadHandler.Complete)
		}

	}

	// Reverse-proxy unmatched /api/v1/* to dataset-service or task-service.
	// NoRoute avoids Gin's radix-tree conflict between static routes and catch-all wildcards.
	r.NoRoute(middleware.Auth(cfg.JWTSecret), proxyHandler.Handle)

	// ── gRPC server ───────────────────────────────────────────────────────
	streamSrv := grpcserver.NewStreamServer(episodeRepo, minioStorage, pub)
	grpcSrv := grpc.NewServer()
	pb.RegisterStreamIngestionServer(grpcSrv, streamSrv)

	grpcLis, err := net.Listen("tcp", fmt.Sprintf(":%s", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("failed to listen on gRPC port: %v", err)
	}

	go func() {
		log.Printf("gRPC server listening on :%s", cfg.GRPCPort)
		if err := grpcSrv.Serve(grpcLis); err != nil {
			log.Printf("gRPC server stopped: %v", err)
		}
	}()

	// ── HTTP server ───────────────────────────────────────────────────────
	httpSrv := &http.Server{
		Addr:    fmt.Sprintf(":%s", cfg.Port),
		Handler: r,
	}

	go func() {
		log.Printf("gateway HTTP listening on :%s", cfg.Port)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP listen error: %v", err)
		}
	}()

	// ── Graceful shutdown ─────────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("shutting down...")

	grpcSrv.GracefulStop()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	httpSrv.Shutdown(ctx)

	log.Println("gateway stopped")
}
