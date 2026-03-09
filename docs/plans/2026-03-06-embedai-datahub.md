# EmbedAI DataHub 完整开发计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建具身机器人领域一站式多模态数据管理平台，覆盖 MCAP/HDF5 数据采集、处理、标注、数据集版本管理与训练导出全链路。

**Architecture:** 微服务架构，Golang 承担高性能 API 网关与流式接入，Python 承担数据处理/标注/导出业务逻辑，React 前端，PostgreSQL 元数据存储，MinIO 对象存储，Redis Streams 异步消息队列，Label Studio 标注集成。

**Tech Stack:** Golang 1.22+, Python 3.11+, React 19 + TypeScript, PostgreSQL 16, MinIO, Redis 7, gRPC, Label Studio, sqlalchemy 2.x, alembic, FastAPI, Gin

**Design Docs:** `docs/design-catalog/` — 所有 ERD、状态图、时序图、ADR 均在此目录

---

## 仓库结构约定

```
embedai/
├── services/
│   ├── gateway/          # Golang: HTTP API 网关 + 上传 + gRPC 流接入
│   ├── pipeline/         # Python: 数据处理流水线 Worker
│   ├── task-service/     # Python: 标注任务管理 + Label Studio 集成
│   ├── dataset-service/  # Python: 数据集 + 版本管理
│   └── export-worker/    # Python: 异步导出 Worker
├── web/                  # React + TypeScript 前端
├── shared/
│   ├── proto/            # gRPC .proto 定义
│   └── migrations/       # Alembic DB migrations
├── infra/
│   ├── docker-compose.yml
│   └── config/
└── docs/
    ├── design-catalog/
    └── plans/
```

---

## Phase 0: 基础设施与开发环境

### Task 0.1: 仓库骨架与 Docker Compose

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `infra/config/postgres-init.sql`
- Create: `Makefile`
- Create: `.env.example`

**Step 1: 创建 Docker Compose（PostgreSQL + MinIO + Redis + Label Studio）**

```yaml
# infra/docker-compose.yml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: embedai
      POSTGRES_USER: embedai
      POSTGRES_PASSWORD: embedai_dev
    ports: ["5432:5432"]
    volumes: ["postgres_data:/var/lib/postgresql/data"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    ports: ["9000:9000", "9001:9001"]
    volumes: ["minio_data:/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  label-studio:
    image: heartexlabs/label-studio:latest
    ports: ["8080:8080"]
    environment:
      DJANGO_DB: default
      POSTGRE_NAME: labelstudio
      POSTGRE_USER: embedai
      POSTGRE_PASSWORD: embedai_dev
      POSTGRE_PORT: 5432
      POSTGRE_HOST: postgres
    depends_on: [postgres]

volumes:
  postgres_data:
  minio_data:
```

**Step 2: 创建 `.env.example`**

```bash
# Database
DATABASE_URL=postgresql://embedai:embedai_dev@localhost:5432/embedai

# MinIO / Object Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET_EPISODES=episodes
MINIO_BUCKET_EXPORTS=exports

# Redis
REDIS_URL=redis://localhost:6379/0

# Label Studio
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=<set after first login>

# Auth
JWT_SECRET=change_me_in_production
JWT_EXPIRE_HOURS=24

# Services
GATEWAY_PORT=8000
PIPELINE_WORKER_CONCURRENCY=4
EXPORT_WORKER_CONCURRENCY=2
```

**Step 3: 创建 Makefile**

```makefile
.PHONY: up down migrate test

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd shared/migrations && alembic upgrade head

test-gateway:
	cd services/gateway && go test ./...

test-pipeline:
	cd services/pipeline && pytest tests/ -v

test-all:
	$(MAKE) test-gateway && $(MAKE) test-pipeline
```

**Step 4: 启动并验证**

```bash
make up
# 验证: curl http://localhost:9001  # MinIO Console
# 验证: psql postgresql://embedai:embedai_dev@localhost:5432/embedai -c "\l"
# 验证: redis-cli -u redis://localhost:6379 ping
```

**Step 5: Commit**

```bash
git add infra/ Makefile .env.example
git commit -m "chore: add docker-compose dev environment"
```

---

### Task 0.2: 数据库 Schema 与 Migration

**Files:**
- Create: `shared/migrations/alembic.ini`
- Create: `shared/migrations/env.py`
- Create: `shared/migrations/versions/001_initial_schema.py`

**Step 1: 初始化 Alembic**

```bash
cd shared/migrations
pip install alembic sqlalchemy psycopg2-binary
alembic init .
```

**Step 2: 编写初始 Schema Migration**

基于 `docs/design-catalog/data/erd.mmd`，创建所有表：

```python
# shared/migrations/versions/001_initial_schema.py
"""Initial schema

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
import uuid

def upgrade():
    # projects
    op.create_table('projects',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('topic_schema', JSONB),  # required topics per project
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # users
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),  # admin|engineer|annotator_internal|annotator_outsource
        sa.Column('skill_tags', JSONB, server_default='[]'),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id')),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # episodes
    op.create_table('episodes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('format', sa.String(10), nullable=False),  # mcap|hdf5
        sa.Column('size_bytes', sa.BigInteger),
        sa.Column('duration_seconds', sa.Float),
        sa.Column('status', sa.String(20), nullable=False, server_default='uploading'),
        sa.Column('quality_score', sa.Float),
        sa.Column('metadata', JSONB, server_default='{}'),
        sa.Column('storage_path', sa.String(1000)),
        sa.Column('recorded_at', sa.DateTime(timezone=True)),
        sa.Column('ingested_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_episodes_project_status', 'episodes', ['project_id', 'status'])
    op.create_index('ix_episodes_recorded_at', 'episodes', ['recorded_at'])

    # topics
    op.create_table('topics',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50)),  # image|pointcloud|imu|force|joint_state|other
        sa.Column('start_time_offset', sa.Float),
        sa.Column('end_time_offset', sa.Float),
        sa.Column('message_count', sa.Integer),
        sa.Column('frequency_hz', sa.Float),
        sa.Column('schema_name', sa.String(255)),
    )
    op.create_index('ix_topics_episode', 'topics', ['episode_id'])

    # upload_sessions
    op.create_table('upload_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id'), nullable=False),
        sa.Column('initiated_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('total_chunks', sa.Integer, nullable=False),
        sa.Column('received_chunks', sa.Integer, server_default='0'),
        sa.Column('chunk_size_bytes', sa.Integer),
        sa.Column('checksum_expected', sa.String(64)),
        sa.Column('status', sa.String(20), server_default='in_progress'),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # datasets
    op.create_table('datasets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # dataset_versions
    op.create_table('dataset_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('dataset_id', UUID(as_uuid=True), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('version_tag', sa.String(50), nullable=False),
        sa.Column('episode_refs', JSONB, nullable=False, server_default='[]'),
        sa.Column('episode_count', sa.Integer),
        sa.Column('total_size_bytes', sa.BigInteger),
        sa.Column('is_immutable', sa.Boolean, server_default='false'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # annotation_tasks
    op.create_table('annotation_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('dataset_version_id', UUID(as_uuid=True), sa.ForeignKey('dataset_versions.id')),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('guideline_url', sa.String(500)),
        sa.Column('required_skills', JSONB, server_default='[]'),
        sa.Column('deadline', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(20), nullable=False, server_default='created'),
        sa.Column('assigned_to', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('label_studio_task_id', sa.Integer),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_tasks_project_status', 'annotation_tasks', ['project_id', 'status'])
    op.create_index('ix_tasks_assigned_to', 'annotation_tasks', ['assigned_to'])

    # annotations
    op.create_table('annotations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id'), nullable=False),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id'), nullable=False),
        sa.Column('annotator_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('time_start', sa.Float),
        sa.Column('time_end', sa.Float),
        sa.Column('labels', JSONB, nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer, server_default='1'),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('reviewer_comment', sa.Text),
        sa.Column('label_studio_annotation_id', sa.Integer),
        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # export_jobs
    op.create_table('export_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('dataset_version_id', UUID(as_uuid=True), sa.ForeignKey('dataset_versions.id'), nullable=False),
        sa.Column('triggered_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('format', sa.String(30), nullable=False),  # raw|webdataset|hf_datasets
        sa.Column('target_bucket', sa.String(255), nullable=False),
        sa.Column('target_prefix', sa.String(500)),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('progress_pct', sa.Float, server_default='0'),
        sa.Column('manifest_url', sa.String(1000)),
        sa.Column('error_message', sa.Text),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # recording_sessions (for streaming reconnect, H2)
    op.create_table('recording_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('robot_id', sa.String(255)),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('episode_ids', JSONB, server_default='[]'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    for table in ['recording_sessions', 'export_jobs', 'annotations',
                  'annotation_tasks', 'dataset_versions', 'datasets',
                  'upload_sessions', 'topics', 'episodes', 'users', 'projects']:
        op.drop_table(table)
```

**Step 3: 执行 Migration**

```bash
cd shared/migrations
cp ../../.env.example ../../.env
export DATABASE_URL=postgresql://embedai:embedai_dev@localhost:5432/embedai
alembic upgrade head
```

预期：`Running upgrade -> 001, Initial schema`

**Step 4: 验证**

```bash
psql $DATABASE_URL -c "\dt"
# 应看到 12 张表
```

**Step 5: Commit**

```bash
git add shared/migrations/
git commit -m "feat: add initial database schema migration"
```

---

### Task 0.3: 共享 Proto 定义

**Files:**
- Create: `shared/proto/episode.proto`
- Create: `shared/proto/stream.proto`
- Create: `shared/proto/Makefile`

**Step 1: 定义 Episode 事件 Proto**

```protobuf
// shared/proto/episode.proto
syntax = "proto3";
package embedai.v1;
option go_package = "github.com/embedai/datahub/shared/proto;proto";

message EpisodeIngestedEvent {
  string episode_id = 1;
  string project_id = 2;
  string storage_path = 3;
  string format = 4;  // mcap | hdf5
}

message EpisodeReadyEvent {
  string episode_id = 1;
  float quality_score = 2;
  int32 topic_count = 3;
}
```

```protobuf
// shared/proto/stream.proto
syntax = "proto3";
package embedai.v1;
option go_package = "github.com/embedai/datahub/shared/proto;proto";

service StreamIngestion {
  rpc OpenStream(stream StreamFrame) returns (stream StreamAck);
}

message StreamFrame {
  string session_id = 1;
  string project_id = 2;
  string robot_id = 3;
  uint64 seq_num = 4;
  int64 timestamp_ns = 5;
  string topic = 6;
  bytes payload = 7;
  bool is_last = 8;
}

message StreamAck {
  uint64 last_ack_seq = 1;
  string episode_id = 2;
  string status = 3;  // ok | reconnect | error
}
```

**Step 2: 生成代码**

```bash
# 安装工具
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
pip install grpcio-tools

# 生成 Go 代码
cd shared/proto
protoc --go_out=. --go-grpc_out=. *.proto

# 生成 Python 代码
python -m grpc_tools.protoc -I. --python_out=../python_proto --grpc_python_out=../python_proto *.proto
```

**Step 3: Commit**

```bash
git add shared/proto/
git commit -m "feat: add gRPC proto definitions for streaming and events"
```

---

## Phase 1: API 网关与认证 (Golang)

### Task 1.1: Gateway 项目骨架

**Files:**
- Create: `services/gateway/main.go`
- Create: `services/gateway/go.mod`
- Create: `services/gateway/internal/config/config.go`
- Create: `services/gateway/internal/middleware/auth.go`

**Step 1: 初始化 Go Module**

```bash
cd services/gateway
go mod init github.com/embedai/datahub/gateway
go get github.com/gin-gonic/gin
go get github.com/golang-jwt/jwt/v5
go get github.com/google/uuid
go get github.com/jackc/pgx/v5
go get github.com/redis/go-redis/v9
go get github.com/minio/minio-go/v7
```

**Step 2: Config**

```go
// services/gateway/internal/config/config.go
package config

import (
    "os"
    "strconv"
)

type Config struct {
    Port           string
    DatabaseURL    string
    RedisURL       string
    MinioEndpoint  string
    MinioAccessKey string
    MinioSecretKey string
    MinioBucketEpisodes string
    JWTSecret      string
    JWTExpireHours int
}

func Load() *Config {
    expHours, _ := strconv.Atoi(getEnv("JWT_EXPIRE_HOURS", "24"))
    return &Config{
        Port:           getEnv("GATEWAY_PORT", "8000"),
        DatabaseURL:    mustEnv("DATABASE_URL"),
        RedisURL:       getEnv("REDIS_URL", "redis://localhost:6379/0"),
        MinioEndpoint:  getEnv("MINIO_ENDPOINT", "localhost:9000"),
        MinioAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
        MinioSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin123"),
        MinioBucketEpisodes: getEnv("MINIO_BUCKET_EPISODES", "episodes"),
        JWTSecret:      mustEnv("JWT_SECRET"),
        JWTExpireHours: expHours,
    }
}

func getEnv(key, fallback string) string {
    if v := os.Getenv(key); v != "" { return v }
    return fallback
}

func mustEnv(key string) string {
    v := os.Getenv(key)
    if v == "" { panic("required env var not set: " + key) }
    return v
}
```

**Step 3: JWT Auth Middleware**

```go
// services/gateway/internal/middleware/auth.go
package middleware

import (
    "net/http"
    "strings"
    "github.com/gin-gonic/gin"
    "github.com/golang-jwt/jwt/v5"
)

type Claims struct {
    UserID    string `json:"user_id"`
    ProjectID string `json:"project_id"`
    Role      string `json:"role"`
    jwt.RegisteredClaims
}

func Auth(jwtSecret string) gin.HandlerFunc {
    return func(c *gin.Context) {
        header := c.GetHeader("Authorization")
        if !strings.HasPrefix(header, "Bearer ") {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing token"})
            return
        }
        tokenStr := strings.TrimPrefix(header, "Bearer ")
        claims := &Claims{}
        _, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
            return []byte(jwtSecret), nil
        })
        if err != nil {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
            return
        }
        c.Set("user_id", claims.UserID)
        c.Set("project_id", claims.ProjectID)
        c.Set("role", claims.Role)
        c.Next()
    }
}

func RequireRole(roles ...string) gin.HandlerFunc {
    return func(c *gin.Context) {
        role := c.GetString("role")
        for _, r := range roles {
            if role == r { c.Next(); return }
        }
        c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "insufficient permissions"})
    }
}
```

**Step 4: 编写测试**

```go
// services/gateway/internal/middleware/auth_test.go
func TestAuth_MissingToken(t *testing.T) {
    w := httptest.NewRecorder()
    c, r := gin.CreateTestContext(w)
    r.GET("/test", Auth("secret"), func(c *gin.Context) { c.Status(200) })
    c.Request, _ = http.NewRequest("GET", "/test", nil)
    r.ServeHTTP(w, c.Request)
    assert.Equal(t, 401, w.Code)
}

func TestAuth_ValidToken(t *testing.T) {
    // 生成合法 token 并验证通过
    ...
}
```

**Step 5: 运行测试**

```bash
cd services/gateway
go test ./internal/middleware/... -v
```

**Step 6: Commit**

```bash
git add services/gateway/
git commit -m "feat: gateway skeleton with JWT auth middleware"
```

---

### Task 1.2: 用户认证 API

**Files:**
- Create: `services/gateway/internal/handler/auth.go`
- Create: `services/gateway/internal/repo/user.go`
- Modify: `services/gateway/main.go`

**Step 1: 编写用户 Repo 测试**

```go
// services/gateway/internal/repo/user_test.go
func TestUserRepo_FindByEmail(t *testing.T) {
    // 使用 testcontainers 或 mock db
    repo := NewUserRepo(testDB)
    user, err := repo.FindByEmail(ctx, "test@example.com")
    assert.NoError(t, err)
    assert.Equal(t, "test@example.com", user.Email)
}
```

**Step 2: 实现 User Repo**

```go
// services/gateway/internal/repo/user.go
package repo

type User struct {
    ID             string
    Email          string
    Name           string
    HashedPassword string
    Role           string
    ProjectID      string
    SkillTags      []string
}

type UserRepo struct { db *pgxpool.Pool }

func NewUserRepo(db *pgxpool.Pool) *UserRepo { return &UserRepo{db: db} }

func (r *UserRepo) FindByEmail(ctx context.Context, email string) (*User, error) {
    u := &User{}
    err := r.db.QueryRow(ctx,
        `SELECT id, email, name, hashed_password, role, project_id
         FROM users WHERE email=$1 AND is_active=true`, email,
    ).Scan(&u.ID, &u.Email, &u.Name, &u.HashedPassword, &u.Role, &u.ProjectID)
    return u, err
}
```

**Step 3: 实现 Login Handler**

```go
// services/gateway/internal/handler/auth.go
package handler

// POST /auth/login
// Body: { email, password }
// Response: { token, user }
func (h *AuthHandler) Login(c *gin.Context) {
    var req struct {
        Email    string `json:"email" binding:"required,email"`
        Password string `json:"password" binding:"required"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(400, gin.H{"error": err.Error()}); return
    }
    user, err := h.userRepo.FindByEmail(c, req.Email)
    if err != nil || !checkPassword(req.Password, user.HashedPassword) {
        c.JSON(401, gin.H{"error": "invalid credentials"}); return
    }
    token, _ := generateJWT(user, h.jwtSecret, h.expireHours)
    c.JSON(200, gin.H{"token": token, "user": gin.H{
        "id": user.ID, "email": user.Email,
        "role": user.Role, "project_id": user.ProjectID,
    }})
}
```

**Step 4: 测试并 Commit**

```bash
go test ./internal/handler/... -v
git add services/gateway/
git commit -m "feat: add user login API with JWT"
```

---

## Phase 2: 数据采集 — 分块上传 (Golang)

### Task 2.1: Upload API

**Files:**
- Create: `services/gateway/internal/handler/upload.go`
- Create: `services/gateway/internal/repo/episode.go`
- Create: `services/gateway/internal/storage/minio.go`

**Step 1: 编写 Upload 集成测试**

```go
// services/gateway/internal/handler/upload_test.go
func TestUploadInit_Success(t *testing.T) {
    body := `{"filename":"test.mcap","size_bytes":1073741824,"format":"mcap","checksum":"abc123"}`
    w := postJSON(t, "/api/v1/episodes/upload/init", body, adminToken)
    assert.Equal(t, 201, w.Code)
    var resp map[string]interface{}
    json.Unmarshal(w.Body.Bytes(), &resp)
    assert.NotEmpty(t, resp["episode_id"])
    assert.NotEmpty(t, resp["session_id"])
    assert.Equal(t, float64(67108864), resp["chunk_size"])  // 64MB
}

func TestUploadChunk_Success(t *testing.T) {
    // 初始化会话后上传单个分块
    ...
}

func TestUploadComplete_AssemblesFile(t *testing.T) {
    // 完整上传后验证文件在 MinIO 中存在
    ...
}
```

**Step 2: 实现 MinIO Storage**

```go
// services/gateway/internal/storage/minio.go
package storage

const ChunkSize = 64 * 1024 * 1024 // 64MB

type MinioStorage struct {
    client *minio.Client
    bucket string
}

func (s *MinioStorage) UploadChunk(ctx context.Context, sessionID string, chunkN int, data io.Reader, size int64) error {
    key := fmt.Sprintf("tmp/%s/chunk_%05d", sessionID, chunkN)
    _, err := s.client.PutObject(ctx, s.bucket, key, data, size, minio.PutObjectOptions{})
    return err
}

func (s *MinioStorage) AssembleChunks(ctx context.Context, sessionID string, totalChunks int, destPath string) error {
    // 使用 MinIO Compose 合并分块
    sources := make([]minio.CopySrcOptions, totalChunks)
    for i := range sources {
        sources[i] = minio.CopySrcOptions{
            Bucket: s.bucket,
            Object: fmt.Sprintf("tmp/%s/chunk_%05d", sessionID, i),
        }
    }
    _, err := s.client.ComposeObject(ctx, minio.CopyDestOptions{
        Bucket: s.bucket, Object: destPath,
    }, sources...)
    return err
}
```

**Step 3: 实现 Upload Handler**

```go
// services/gateway/internal/handler/upload.go
// POST /api/v1/episodes/upload/init
func (h *UploadHandler) Init(c *gin.Context) { ... }

// PUT /api/v1/episodes/upload/:session_id/chunk/:n
func (h *UploadHandler) UploadChunk(c *gin.Context) { ... }

// POST /api/v1/episodes/upload/:session_id/complete
// 1. 验证所有分块已收到
// 2. 组装文件到 episodes/{project_id}/{episode_id}.mcap
// 3. 更新 Episode status=processing
// 4. 发布 EpisodeIngested 事件到 Redis Stream
func (h *UploadHandler) Complete(c *gin.Context) { ... }
```

**Step 4: Redis Stream 事件发布**

```go
// services/gateway/internal/events/publisher.go
func (p *Publisher) PublishEpisodeIngested(ctx context.Context, episodeID, storagePath, format string) error {
    return p.redis.XAdd(ctx, &redis.XAddArgs{
        Stream: "episodes:ingested",
        Values: map[string]interface{}{
            "episode_id":   episodeID,
            "storage_path": storagePath,
            "format":       format,
        },
    }).Err()
}
```

**Step 5: 运行测试，Commit**

```bash
go test ./internal/handler/... -run TestUpload -v
git add services/gateway/internal/handler/upload.go services/gateway/internal/storage/ services/gateway/internal/events/
git commit -m "feat: chunked upload API with MinIO storage and Redis event publish"
```

---

### Task 2.2: gRPC 流式接入

**Files:**
- Create: `services/gateway/internal/grpc/stream_server.go`
- Create: `services/gateway/internal/grpc/frame_buffer.go`

**Step 1: 编写流接入测试**

```go
func TestStreamServer_NormalFlow(t *testing.T) {
    // 模拟机器人发送 100 帧，验证：
    // 1. 每帧都收到 ACK
    // 2. 发送 is_last=true 后 Episode 被创建
    ...
}

func TestStreamServer_Reconnect(t *testing.T) {
    // 断线后重连，验证：
    // 1. 第一段封存为 Episode A
    // 2. 重连后创建 Episode B
    // 3. 两个 Episode 共享 recording_session_id
    ...
}
```

**Step 2: 实现帧缓冲区（5s 滑动窗口）**

```go
// services/gateway/internal/grpc/frame_buffer.go
type FrameBuffer struct {
    mu      sync.Mutex
    frames  []StreamFrame
    maxAge  time.Duration  // 5s
    lastSeq uint64
}

func (b *FrameBuffer) Add(f StreamFrame) {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.frames = append(b.frames, f)
    b.lastSeq = f.SeqNum
    b.evictExpired()
}

func (b *FrameBuffer) Flush() ([]StreamFrame, error) {
    // 将缓冲帧按 seq_num 排序后序列化为 MCAP 格式
    // 写入 MinIO，返回 storage_path
    ...
}
```

**Step 3: 实现 Stream Server**

```go
// services/gateway/internal/grpc/stream_server.go
func (s *StreamServer) OpenStream(stream proto.StreamIngestion_OpenStreamServer) error {
    var sessionID, episodeID string
    buf := NewFrameBuffer(5 * time.Second)
    inactivityTimer := time.NewTimer(30 * time.Second)

    for {
        select {
        case <-inactivityTimer.C:
            // 30s 无数据 → 封存当前 Episode
            s.sealEpisode(stream.Context(), episodeID, buf)
            return nil
        default:
        }

        frame, err := stream.Recv()
        if err == io.EOF || (frame != nil && frame.IsLast) {
            s.sealEpisode(stream.Context(), episodeID, buf)
            return nil
        }
        if err != nil { return err }

        inactivityTimer.Reset(30 * time.Second)
        buf.Add(*frame)
        stream.Send(&proto.StreamAck{
            LastAckSeq: frame.SeqNum,
            EpisodeId:  episodeID,
            Status:     "ok",
        })
    }
}
```

**Step 4: 运行测试，Commit**

```bash
go test ./internal/grpc/... -v
git add services/gateway/internal/grpc/
git commit -m "feat: gRPC streaming ingestion with reconnect handling"
```

---

## Phase 3: 数据处理流水线 (Python)

### Task 3.1: Pipeline Worker 骨架

**Files:**
- Create: `services/pipeline/pyproject.toml`
- Create: `services/pipeline/pipeline/main.py`
- Create: `services/pipeline/pipeline/worker.py`
- Create: `services/pipeline/tests/conftest.py`

**Step 1: 项目依赖**

```toml
# services/pipeline/pyproject.toml
[project]
name = "embedai-pipeline"
version = "0.1.0"
dependencies = [
    "mcap>=1.1.0",           # MCAP 官方 Python SDK
    "mcap-ros2-support>=0.4",
    "h5py>=3.10",            # HDF5 读取
    "minio>=7.2",            # MinIO 客户端
    "redis>=5.0",            # Redis Streams
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "numpy>=1.26",
    "opencv-python-headless>=4.9",  # 图像质量检测
    "pydantic>=2.5",
    "loguru>=0.7",
]

[project.optional-dependencies]
test = ["pytest>=8.0", "pytest-asyncio", "pytest-mock", "factory-boy"]
```

**Step 2: Redis Stream Consumer**

```python
# services/pipeline/pipeline/worker.py
import asyncio
from redis.asyncio import Redis
from loguru import logger

class PipelineWorker:
    STREAM = "episodes:ingested"
    GROUP = "pipeline-workers"
    CONSUMER = "worker-1"

    def __init__(self, redis: Redis, processor: "EpisodeProcessor"):
        self.redis = redis
        self.processor = processor

    async def run(self):
        await self._ensure_group()
        logger.info("Pipeline worker started, listening on {}", self.STREAM)
        while True:
            messages = await self.redis.xreadgroup(
                self.GROUP, self.CONSUMER,
                {self.STREAM: ">"}, count=1, block=5000,
            )
            for _, events in (messages or []):
                for msg_id, data in events:
                    await self._handle(msg_id, data)

    async def _handle(self, msg_id: str, data: dict):
        episode_id = data[b"episode_id"].decode()
        try:
            await self.processor.process(episode_id, data)
            await self.redis.xack(self.STREAM, self.GROUP, msg_id)
        except Exception as e:
            logger.error("Failed to process episode {}: {}", episode_id, e)
            # 不 ACK → 消息重试（DLQ 后续加）
```

**Step 3: 编写 Worker 测试**

```python
# services/pipeline/tests/test_worker.py
@pytest.mark.asyncio
async def test_worker_processes_message(mock_redis, mock_processor):
    worker = PipelineWorker(mock_redis, mock_processor)
    mock_redis.xreadgroup.return_value = [
        ("episodes:ingested", [("1-0", {b"episode_id": b"test-id", b"format": b"mcap"})])
    ]
    await worker._handle("1-0", {b"episode_id": b"test-id", b"format": b"mcap"})
    mock_processor.process.assert_called_once_with("test-id", ANY)
    mock_redis.xack.assert_called_once()
```

**Step 4: 运行测试，Commit**

```bash
cd services/pipeline
pip install -e ".[test]"
pytest tests/test_worker.py -v
git add services/pipeline/
git commit -m "feat: pipeline worker skeleton with Redis Stream consumer"
```

---

### Task 3.2: MCAP 元数据提取

**Files:**
- Create: `services/pipeline/pipeline/extractors/mcap_extractor.py`
- Create: `services/pipeline/tests/test_mcap_extractor.py`
- Create: `services/pipeline/tests/fixtures/sample.mcap`（测试用小文件）

**Step 1: 编写提取器测试**

```python
# services/pipeline/tests/test_mcap_extractor.py
def test_extract_topics(sample_mcap_path):
    extractor = McapExtractor(sample_mcap_path)
    result = extractor.extract()

    assert result.format == "mcap"
    assert result.duration_seconds > 0
    assert len(result.topics) > 0

    camera_topic = next(t for t in result.topics if "camera" in t.name)
    assert camera_topic.type == "image"
    assert camera_topic.frequency_hz > 0
    assert camera_topic.message_count > 0
```

**Step 2: 实现 MCAP 提取器**

```python
# services/pipeline/pipeline/extractors/mcap_extractor.py
from dataclasses import dataclass, field
from mcap.reader import make_reader

@dataclass
class TopicMeta:
    name: str
    type: str
    message_count: int
    frequency_hz: float
    start_time_offset: float
    end_time_offset: float
    schema_name: str

@dataclass
class EpisodeMeta:
    format: str = "mcap"
    duration_seconds: float = 0.0
    topics: list[TopicMeta] = field(default_factory=list)

class McapExtractor:
    TOPIC_TYPE_MAP = {
        "sensor_msgs/msg/Image": "image",
        "sensor_msgs/msg/PointCloud2": "pointcloud",
        "sensor_msgs/msg/Imu": "imu",
        "geometry_msgs/msg/WrenchStamped": "force",
        "sensor_msgs/msg/JointState": "joint_state",
    }

    def __init__(self, file_path: str):
        self.file_path = file_path

    def extract(self) -> EpisodeMeta:
        meta = EpisodeMeta()
        topic_stats: dict[str, dict] = {}

        with open(self.file_path, "rb") as f:
            reader = make_reader(f)
            summary = reader.get_summary()

            if summary:
                start_ns = summary.statistics.message_start_time
                end_ns = summary.statistics.message_end_time
                meta.duration_seconds = (end_ns - start_ns) / 1e9

                for channel_id, channel in summary.channels.items():
                    schema = summary.schemas.get(channel.schema_id)
                    schema_name = schema.name if schema else ""
                    stats = summary.statistics.channel_message_counts.get(channel_id, 0)
                    topic_stats[channel.topic] = {
                        "schema_name": schema_name,
                        "message_count": stats,
                    }

        for topic_name, stats in topic_stats.items():
            t_type = self._infer_type(stats["schema_name"])
            freq = stats["message_count"] / meta.duration_seconds if meta.duration_seconds > 0 else 0
            meta.topics.append(TopicMeta(
                name=topic_name,
                type=t_type,
                message_count=stats["message_count"],
                frequency_hz=round(freq, 2),
                start_time_offset=0.0,
                end_time_offset=meta.duration_seconds,
                schema_name=stats["schema_name"],
            ))

        return meta

    def _infer_type(self, schema_name: str) -> str:
        return self.TOPIC_TYPE_MAP.get(schema_name, "other")
```

**Step 3: HDF5 提取器**

```python
# services/pipeline/pipeline/extractors/hdf5_extractor.py
import h5py

def extract_hdf5_meta(file_path: str) -> EpisodeMeta:
    meta = EpisodeMeta(format="hdf5")
    with h5py.File(file_path, "r") as f:
        # 将 HDF5 datasets 映射为 Topic
        def visitor(name, obj):
            if isinstance(obj, h5py.Dataset):
                t = TopicMeta(
                    name=f"/{name}",
                    type=_infer_hdf5_type(name, obj),
                    message_count=obj.shape[0] if obj.ndim > 0 else 1,
                    frequency_hz=_extract_freq(f, name),
                    start_time_offset=0.0,
                    end_time_offset=meta.duration_seconds,
                    schema_name=str(obj.dtype),
                )
                meta.topics.append(t)
        f.visititems(visitor)
        # 尝试从 attrs 读取 duration
        if "duration" in f.attrs:
            meta.duration_seconds = float(f.attrs["duration"])
    return meta
```

**Step 4: 运行测试，Commit**

```bash
pytest tests/test_mcap_extractor.py tests/test_hdf5_extractor.py -v
git add services/pipeline/pipeline/extractors/
git commit -m "feat: MCAP and HDF5 metadata extractors"
```

---

### Task 3.3: 质量评分 (ADR H1)

**Files:**
- Create: `services/pipeline/pipeline/quality/scorer.py`
- Create: `services/pipeline/tests/test_quality_scorer.py`

**Step 1: 编写质量评分测试**

```python
def test_score_healthy_episode():
    meta = EpisodeMeta(topics=[
        TopicMeta("/camera/rgb", "image", 300, 30.0, ...),
        TopicMeta("/imu/data", "imu", 2000, 200.0, ...),
    ])
    project_schema = {
        "required_topics": ["/camera/rgb", "/imu/data"],
        "topic_frequency": {"/camera/rgb": 30.0, "/imu/data": 200.0},
    }
    score, detail = QualityScorer(project_schema).score(meta, "/path/to/file.mcap")
    assert score >= 0.9
    assert detail["frame_rate_stability"] >= 0.9
    assert detail["sensor_completeness"] == 1.0

def test_score_missing_topic():
    meta = EpisodeMeta(topics=[
        TopicMeta("/camera/rgb", "image", 300, 30.0, ...),
        # /imu/data 缺失
    ])
    score, _ = QualityScorer(project_schema).score(meta, ...)
    assert score < 0.6  # 传感器完整性拉低总分
```

**Step 2: 实现评分器**

```python
# services/pipeline/pipeline/quality/scorer.py
import cv2, numpy as np
from dataclasses import dataclass

@dataclass
class QualityDetail:
    frame_rate_stability: float
    sensor_completeness: float
    signal_quality: float
    total_score: float

WEIGHTS = {"frame_rate_stability": 0.4, "sensor_completeness": 0.4, "signal_quality": 0.2}

class QualityScorer:
    TOLERANCE = 0.1  # ±10% 帧率容忍

    def __init__(self, project_schema: dict):
        self.schema = project_schema

    def score(self, meta: EpisodeMeta, file_path: str) -> tuple[float, QualityDetail]:
        fps_score = self._score_frame_rate(meta)
        completeness = self._score_completeness(meta)
        signal = self._score_signal_quality(meta, file_path)

        total = (fps_score * WEIGHTS["frame_rate_stability"] +
                 completeness * WEIGHTS["sensor_completeness"] +
                 signal * WEIGHTS["signal_quality"])

        detail = QualityDetail(fps_score, completeness, signal, round(total, 3))
        return total, detail

    def _score_frame_rate(self, meta: EpisodeMeta) -> float:
        expected = self.schema.get("topic_frequency", {})
        scores = []
        for topic in meta.topics:
            if topic.name in expected:
                ratio = topic.frequency_hz / expected[topic.name]
                score = 1.0 if abs(1 - ratio) <= self.TOLERANCE else max(0, 1 - abs(1 - ratio))
                scores.append(score)
        return sum(scores) / len(scores) if scores else 1.0

    def _score_completeness(self, meta: EpisodeMeta) -> float:
        required = set(self.schema.get("required_topics", []))
        present = {t.name for t in meta.topics}
        if not required: return 1.0
        return len(required & present) / len(required)

    def _score_signal_quality(self, meta: EpisodeMeta, file_path: str) -> float:
        # 对图像 topic: Laplacian variance 检测模糊
        # 简化版: 采样 5 帧计算均值
        image_topics = [t for t in meta.topics if t.type == "image"]
        if not image_topics: return 1.0
        # TODO: 从 MCAP 采样图像帧并计算模糊度
        return 0.9  # placeholder
```

**Step 3: 运行测试，Commit**

```bash
pytest tests/test_quality_scorer.py -v
git add services/pipeline/pipeline/quality/
git commit -m "feat: three-dimensional quality scoring (ADR H1)"
```

---

### Task 3.4: 完整 Episode 处理器

**Files:**
- Create: `services/pipeline/pipeline/processor.py`
- Create: `services/pipeline/tests/test_processor.py`

**Step 1: 测试完整处理流程**

```python
@pytest.mark.asyncio
async def test_process_mcap_episode(mock_db, mock_minio, sample_mcap_in_minio):
    processor = EpisodeProcessor(db=mock_db, storage=mock_minio, ...)
    await processor.process("episode-123", {b"storage_path": b"episodes/p1/episode-123.mcap", b"format": b"mcap"})

    # 验证 DB 更新
    mock_db.execute.assert_any_call(
        contains("UPDATE episodes SET status='ready'"), ANY
    )
    # 验证 Topics 已写入
    mock_db.execute.assert_any_call(contains("INSERT INTO topics"), ANY)
```

**Step 2: 实现处理器（串联各步骤）**

```python
# services/pipeline/pipeline/processor.py
class EpisodeProcessor:
    async def process(self, episode_id: str, event_data: dict):
        storage_path = event_data[b"storage_path"].decode()
        fmt = event_data[b"format"].decode()

        # 1. 更新状态
        await self.db.update_episode_status(episode_id, "processing")

        # 2. 下载到临时文件
        local_path = await self.storage.download_temp(storage_path)

        try:
            # 3. 提取元数据
            meta = (McapExtractor(local_path).extract() if fmt == "mcap"
                    else extract_hdf5_meta(local_path))

            # 4. 质量评分
            project = await self.db.get_episode_project(episode_id)
            score, detail = QualityScorer(project.topic_schema).score(meta, local_path)

            # 5. 生成预览帧（图像 topic 第一帧）
            thumb_url = await self._generate_thumbnail(local_path, fmt, episode_id)

            # 6. 写入 DB
            await self.db.update_episode_ready(
                episode_id=episode_id,
                duration=meta.duration_seconds,
                quality_score=score,
                metadata={"quality_detail": asdict(detail), "thumbnail_url": thumb_url},
                topics=meta.topics,
            )
        finally:
            os.unlink(local_path)
```

**Step 3: 运行测试，Commit**

```bash
pytest tests/test_processor.py -v
git add services/pipeline/pipeline/processor.py
git commit -m "feat: complete episode processing pipeline (extract + score + index)"
```

---

## Phase 4: 数据管理 API (Python FastAPI)

### Task 4.1: Episode 查询 API

**Files:**
- Create: `services/dataset-service/app/main.py`
- Create: `services/dataset-service/app/routers/episodes.py`
- Create: `services/dataset-service/tests/test_episodes_api.py`

**Step 1: 测试 Episode 列表查询**

```python
def test_list_episodes_with_filters(client, auth_headers, seed_episodes):
    resp = client.get("/api/v1/episodes?status=ready&format=mcap&min_quality=0.6", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["status"] == "ready" for e in data["items"])
    assert all(e["quality_score"] >= 0.6 for e in data["items"])

def test_get_episode_detail(client, auth_headers, seed_episode):
    resp = client.get(f"/api/v1/episodes/{seed_episode.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert "topics" in resp.json()
```

**Step 2: 实现 Episode Router**

```python
# services/dataset-service/app/routers/episodes.py
@router.get("/episodes")
async def list_episodes(
    project_id: str = Depends(get_project_id),
    status: str | None = None,
    format: str | None = None,
    min_quality: float | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(Episode).where(Episode.project_id == project_id)
    if status: query = query.where(Episode.status == status)
    if format: query = query.where(Episode.format == format)
    if min_quality: query = query.where(Episode.quality_score >= min_quality)
    if search: query = query.where(Episode.filename.ilike(f"%{search}%"))
    # 返回分页结果 + 总数
    ...

@router.get("/episodes/{episode_id}/stream-token")
async def get_stream_token(episode_id: str, current_user=Depends(get_current_user)):
    # 生成时限访问令牌（用于标注工具请求数据）
    token = create_stream_token(episode_id, expires_in=3600)
    return {"stream_token": token, "expires_in": 3600}
```

**Step 3: 运行测试，Commit**

```bash
pytest tests/test_episodes_api.py -v
git add services/dataset-service/
git commit -m "feat: episode list/detail API with quality and status filters"
```

---

### Task 4.2: 数据集版本管理 API

**Files:**
- Create: `services/dataset-service/app/routers/datasets.py`
- Create: `services/dataset-service/tests/test_datasets_api.py`

**Step 1: 测试版本不可变性（ADR H5）**

```python
def test_dataset_version_is_immutable(client, auth_headers, seed_version):
    # 尝试修改已冻结版本 → 应返回 409
    resp = client.patch(
        f"/api/v1/dataset-versions/{seed_version.id}",
        json={"episode_refs": []},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "immutable" in resp.json()["error"]

def test_create_version_snapshot(client, auth_headers, seed_dataset, seed_episodes):
    resp = client.post(f"/api/v1/datasets/{seed_dataset.id}/versions", json={
        "version_tag": "v1.0.0",
        "episode_refs": [
            {"episode_id": str(seed_episodes[0].id), "clip_start": 0, "clip_end": 30.0},
        ],
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["is_immutable"] is True
```

**Step 2: 实现 Dataset Router**

```python
# services/dataset-service/app/routers/datasets.py

@router.post("/datasets/{dataset_id}/versions", status_code=201)
async def create_version(dataset_id: str, body: CreateVersionRequest, db=Depends(get_db)):
    # 验证 episode_refs 中的 episodes 均属于同一 project
    # 计算 episode_count 和 total_size_bytes
    # 创建 DatasetVersion，is_immutable=True
    ...

@router.patch("/dataset-versions/{version_id}")
async def update_version(version_id: str, db=Depends(get_db)):
    version = await db.get(DatasetVersion, version_id)
    if version.is_immutable:
        raise HTTPException(409, "Dataset version is immutable")
    ...
```

**Step 3: 运行测试，Commit**

```bash
pytest tests/test_datasets_api.py -v
git add services/dataset-service/app/routers/datasets.py
git commit -m "feat: dataset versioning API with immutability enforcement (ADR H5)"
```

---

## Phase 5: 标注集成 (Label Studio + Python)

### Task 5.1: Label Studio 集成客户端

**Files:**
- Create: `services/task-service/app/integrations/label_studio.py`
- Create: `services/task-service/tests/test_label_studio_integration.py`

**Step 1: 编写集成测试**

```python
@pytest.mark.asyncio
async def test_create_ls_task(mock_ls_client):
    client = LabelStudioClient("http://localhost:8080", "test-api-key")
    task_id = await client.create_task(
        project_id="ls-project-1",
        data_url="http://gateway:8000/api/v1/stream/episode-123?token=xxx",
        meta={"episode_id": "episode-123", "time_start": 0, "time_end": 30},
    )
    assert isinstance(task_id, int)

@pytest.mark.asyncio
async def test_sync_annotation_from_webhook(task_service, mock_db):
    webhook_payload = {
        "action": "ANNOTATION_CREATED",
        "annotation": {"id": 42, "task": 1, "result": [...], "completed_by": 5},
    }
    await task_service.handle_ls_webhook(webhook_payload)
    mock_db.upsert_annotation.assert_called_once()
```

**Step 2: 实现 Label Studio 客户端**

```python
# services/task-service/app/integrations/label_studio.py
import httpx

class LabelStudioClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"Authorization": f"Token {api_key}"}

    async def create_project(self, name: str, label_config: str) -> int:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/api/projects",
                headers=self.headers,
                json={"title": name, "label_config": label_config})
            resp.raise_for_status()
            return resp.json()["id"]

    async def create_task(self, project_id: int, data_url: str, meta: dict) -> int:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/api/tasks",
                headers=self.headers,
                json={"project": project_id, "data": {"video": data_url, **meta}})
            resp.raise_for_status()
            return resp.json()["id"]

    async def get_annotations(self, task_id: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/api/tasks/{task_id}/annotations",
                headers=self.headers)
            resp.raise_for_status()
            return resp.json()
```

**Step 3: 实现 Webhook 处理器**

```python
# services/task-service/app/routers/webhooks.py
@router.post("/webhooks/label-studio")
async def label_studio_webhook(payload: dict, db=Depends(get_db), ls=Depends(get_ls_client)):
    action = payload.get("action")
    if action == "ANNOTATION_CREATED":
        anno = payload["annotation"]
        ls_task_id = anno["task"]
        task = await db.get_task_by_ls_id(ls_task_id)
        if not task: return {"status": "ignored"}

        await db.upsert_annotation(
            task_id=task.id,
            episode_id=task.episode_id,
            annotator_id=task.assigned_to,
            labels=anno["result"],
            label_studio_annotation_id=anno["id"],
            status="submitted",
        )
        await db.update_task_status(task.id, "submitted")
    return {"status": "ok"}
```

**Step 4: 运行测试，Commit**

```bash
pytest tests/test_label_studio_integration.py tests/test_webhooks.py -v
git add services/task-service/
git commit -m "feat: Label Studio integration with webhook annotation sync (ADR H3)"
```

---

### Task 5.2: 标注任务管理 API

**Files:**
- Create: `services/task-service/app/routers/tasks.py`
- Create: `services/task-service/tests/test_tasks_api.py`

**Step 1: 测试任务分配（含负载展示，ADR H4）**

```python
def test_assign_task_with_workload(client, auth_headers, seed_task, seed_annotators):
    # 查看标注员工作负载
    resp = client.get("/api/v1/users?role=annotator&include_workload=true", headers=auth_headers)
    assert resp.status_code == 200
    annotators = resp.json()
    assert all("pending_task_count" in a for a in annotators)

    # 手动分配
    resp = client.post(f"/api/v1/tasks/{seed_task.id}/assign",
        json={"user_id": str(seed_annotators[0].id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "assigned"

def test_submit_task(client, annotator_headers, seed_assigned_task):
    resp = client.post(f"/api/v1/tasks/{seed_assigned_task.id}/submit", headers=annotator_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"

def test_approve_task(client, reviewer_headers, seed_submitted_task):
    resp = client.post(f"/api/v1/tasks/{seed_submitted_task.id}/approve", headers=reviewer_headers)
    assert resp.status_code == 200
```

**Step 2: 实现 Task Router**

```python
# services/task-service/app/routers/tasks.py
@router.post("/tasks", status_code=201)
async def create_task(body: CreateTaskRequest, db=Depends(get_db), ls=Depends(get_ls_client)):
    task = await db.create_task(body)
    # 同步创建 Label Studio 任务
    ls_project = await db.get_or_create_ls_project(task.project_id, body.type)
    stream_token = create_stream_token(body.episode_id, expires_in=86400 * 30)
    data_url = f"{settings.GATEWAY_URL}/api/v1/stream/{body.episode_id}?token={stream_token}"
    ls_task_id = await ls.create_task(ls_project.ls_id, data_url, {"episode_id": body.episode_id})
    await db.update_task_ls_id(task.id, ls_task_id)
    return task

@router.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str, body: AssignRequest, db=Depends(get_db)):
    task = await db.get_task(task_id)
    _assert_transition(task.status, "assigned")  # 验证状态机
    await db.assign_task(task_id, body.user_id)
    return await db.get_task(task_id)

@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, db=Depends(get_db), current_user=Depends(require_role("engineer", "admin"))):
    task = await db.get_task(task_id)
    _assert_transition(task.status, "approved")
    await db.approve_task(task_id, current_user.id)
    # 通知 dataset-service: 标注可用
    await publish_annotation_approved(task_id)
    return {"status": "approved"}
```

**Step 3: 运行测试，Commit**

```bash
pytest tests/test_tasks_api.py -v
git add services/task-service/app/routers/tasks.py
git commit -m "feat: annotation task CRUD with state machine enforcement (ADR H4)"
```

---

## Phase 6: 导出流水线 (Python)

### Task 6.1: Export Worker

**Files:**
- Create: `services/export-worker/worker/main.py`
- Create: `services/export-worker/worker/exporters/webdataset.py`
- Create: `services/export-worker/worker/exporters/raw.py`
- Create: `services/export-worker/tests/test_webdataset_exporter.py`

**Step 1: 测试 WebDataset 导出（ADR H6）**

```python
def test_webdataset_export_creates_shards(tmp_path, sample_episodes_with_annotations):
    exporter = WebDatasetExporter(
        shard_size_bytes=200 * 1024 * 1024,  # 200MB
        output_dir=str(tmp_path),
    )
    result = exporter.export(sample_episodes_with_annotations)

    assert len(result.shards) > 0
    # 每个 shard 是有效 tar 文件
    for shard in result.shards:
        assert tarfile.is_tarfile(shard.path)
    # manifest 包含所有文件
    assert result.manifest["episode_count"] == len(sample_episodes_with_annotations)

def test_shard_contains_mcap_and_json(tmp_path, one_episode_with_annotation):
    exporter = WebDatasetExporter(shard_size_bytes=500*1024*1024, output_dir=str(tmp_path))
    result = exporter.export([one_episode_with_annotation])
    with tarfile.open(result.shards[0].path) as tar:
        names = tar.getnames()
        assert any(n.endswith(".mcap") for n in names)
        assert any(n.endswith(".json") for n in names)
```

**Step 2: 实现 WebDataset Exporter**

```python
# services/export-worker/worker/exporters/webdataset.py
import tarfile, json, io
from dataclasses import dataclass, field

SHARD_TARGET = 400 * 1024 * 1024  # 400MB 目标

@dataclass
class ShardInfo:
    path: str
    size_bytes: int
    sample_count: int

@dataclass
class ExportResult:
    shards: list[ShardInfo] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)

class WebDatasetExporter:
    def __init__(self, shard_size_bytes: int, output_dir: str):
        self.shard_size = shard_size_bytes
        self.output_dir = output_dir

    def export(self, episode_refs: list[EpisodeRef]) -> ExportResult:
        result = ExportResult()
        shard_idx = 0
        current_size = 0
        current_tar = None
        current_path = None

        for i, ep_ref in enumerate(episode_refs):
            mcap_data = self._extract_clip(ep_ref)
            anno_data = json.dumps(ep_ref.annotations).encode()
            sample_name = f"ep_{ep_ref.episode_id[:8]}_{i:06d}"

            if current_tar is None or current_size + len(mcap_data) > self.shard_size:
                if current_tar:
                    current_tar.close()
                    result.shards.append(ShardInfo(current_path, current_size, i))
                shard_idx += 1
                current_path = f"{self.output_dir}/shard-{shard_idx:06d}.tar"
                current_tar = tarfile.open(current_path, "w")
                current_size = 0

            self._add_bytes(current_tar, f"{sample_name}.mcap", mcap_data)
            self._add_bytes(current_tar, f"{sample_name}.json", anno_data)
            current_size += len(mcap_data) + len(anno_data)

        if current_tar:
            current_tar.close()
            result.shards.append(ShardInfo(current_path, current_size, len(episode_refs)))

        result.manifest = self._build_manifest(episode_refs, result.shards)
        return result

    def _extract_clip(self, ep_ref: EpisodeRef) -> bytes:
        # 从 MinIO 下载并按 clip_start/clip_end 提取 MCAP 片段
        ...

    def _add_bytes(self, tar: tarfile.TarFile, name: str, data: bytes):
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
```

**Step 3: Export Job 异步 Worker**

```python
# services/export-worker/worker/main.py
class ExportWorker:
    STREAM = "export-jobs:pending"

    async def run(self):
        async for job in self._consume_jobs():
            await self._execute_job(job)

    async def _execute_job(self, job: ExportJob):
        await self.db.update_job_status(job.id, "running")
        try:
            version = await self.db.get_dataset_version(job.dataset_version_id)
            ep_refs = await self._resolve_episode_refs(version.episode_refs)

            if job.format == "webdataset":
                exporter = WebDatasetExporter(shard_size_bytes=400*1024*1024, output_dir="/tmp/export")
            else:
                exporter = RawExporter(output_dir="/tmp/export")

            result = exporter.export(ep_refs)

            # 上传所有 shard 到云存储
            for i, shard in enumerate(result.shards):
                await self.cloud_storage.upload(shard.path, f"{job.target_prefix}/shard-{i:06d}.tar")
                progress = (i + 1) / len(result.shards) * 100
                await self.db.update_job_progress(job.id, progress)

            # 上传 manifest
            manifest_key = f"{job.target_prefix}/manifest.json"
            await self.cloud_storage.upload_json(manifest_key, result.manifest)
            await self.db.complete_job(job.id, manifest_url=f"s3://{job.target_bucket}/{manifest_key}")

        except Exception as e:
            await self.db.fail_job(job.id, str(e))
            raise
```

**Step 4: 运行测试，Commit**

```bash
cd services/export-worker
pytest tests/ -v
git add services/export-worker/
git commit -m "feat: async export worker with WebDataset shard generation (ADR H6)"
```

---

## Phase 7: React 前端

### Task 7.1: 前端项目初始化

**Files:**
- Create: `web/` (Vite + React 19 + TypeScript)

**Step 1: 初始化项目**

```bash
cd web
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-query axios react-router-dom zustand
npm install -D @types/node tailwindcss @tailwindcss/vite
```

**Step 2: API 客户端层**

```typescript
// web/src/api/client.ts
import axios from "axios";

export const apiClient = axios.create({ baseURL: "/api/v1" });

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);
```

**Step 3: Auth Store**

```typescript
// web/src/store/auth.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  user: { id: string; email: string; role: string; project_id: string } | null;
  login: (token: string, user: AuthState["user"]) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      login: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: "auth" }
  )
);
```

**Step 4: Commit**

```bash
cd web && npm run build  # 确认无编译错误
git add web/
git commit -m "feat: React frontend skeleton with TanStack Query and Zustand auth"
```

---

### Task 7.2: Episode 管理页面

**Files:**
- Create: `web/src/pages/EpisodesPage.tsx`
- Create: `web/src/components/EpisodeCard.tsx`
- Create: `web/src/api/episodes.ts`

**Step 1: API Hooks**

```typescript
// web/src/api/episodes.ts
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "./client";

export interface Episode {
  id: string;
  filename: string;
  format: "mcap" | "hdf5";
  duration_seconds: number;
  quality_score: number;
  status: string;
  metadata: { thumbnail_url?: string; quality_detail?: Record<string, number> };
  recorded_at: string;
}

export function useEpisodes(filters: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ["episodes", filters],
    queryFn: async () => {
      const params = new URLSearchParams(
        Object.fromEntries(Object.entries(filters).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))
      );
      const { data } = await apiClient.get<{ items: Episode[]; total: number }>(`/episodes?${params}`);
      return data;
    },
  });
}
```

**Step 2: Episode 列表页**

```tsx
// web/src/pages/EpisodesPage.tsx
export function EpisodesPage() {
  const [filters, setFilters] = useState({ status: "ready", min_quality: 0.6 });
  const { data, isLoading } = useEpisodes(filters);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">数据录制</h1>
      <FilterBar filters={filters} onChange={setFilters} />
      {isLoading ? <Spinner /> : (
        <div className="grid grid-cols-3 gap-4 mt-4">
          {data?.items.map(ep => <EpisodeCard key={ep.id} episode={ep} />)}
        </div>
      )}
      <Pagination total={data?.total ?? 0} />
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add web/src/pages/EpisodesPage.tsx web/src/components/ web/src/api/episodes.ts
git commit -m "feat: episode list page with quality filter"
```

---

### Task 7.3: 标注任务管理页面

**Files:**
- Create: `web/src/pages/TasksPage.tsx`
- Create: `web/src/api/tasks.ts`

**Step 1: 任务列表 + 分配（含工作负载展示，ADR H4）**

```tsx
// web/src/pages/TasksPage.tsx
export function TasksPage() {
  const { data: tasks } = useTasks({ status: activeTab });
  const { data: annotators } = useAnnotatorsWithWorkload();

  return (
    <div className="flex gap-6 p-6">
      <div className="flex-1">
        <TaskTable tasks={tasks} onAssign={(taskId) => setAssigningTask(taskId)} />
      </div>
      <aside className="w-64">
        <h3 className="font-semibold mb-2">标注员负载</h3>
        {annotators?.map(a => (
          <div key={a.id} className="flex justify-between text-sm py-1">
            <span>{a.name}</span>
            <span className="text-gray-500">{a.pending_task_count} 待办</span>
          </div>
        ))}
      </aside>
      {assigningTask && (
        <AssignModal taskId={assigningTask} annotators={annotators}
          onClose={() => setAssigningTask(null)} />
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add web/src/pages/TasksPage.tsx web/src/api/tasks.ts
git commit -m "feat: annotation task management with workload display (ADR H4)"
```

---

### Task 7.4: 数据集管理 + 导出页面

**Files:**
- Create: `web/src/pages/DatasetsPage.tsx`
- Create: `web/src/pages/ExportPage.tsx`

**Step 1: 数据集版本创建界面**

```tsx
// 支持从 Episode 搜索结果直接圈选，生成引用快照版本 (ADR H5)
// 导出配置: 选择 format=webdataset|raw, 填写 target_bucket
// 进度轮询: useQuery polling export job status
```

**Step 2: 运行 E2E 验证**

```bash
cd web && npm run dev
# 手动测试完整流程: 上传 → 处理 → 创建任务 → 标注 → 数据集 → 导出
```

**Step 3: Commit**

```bash
git add web/src/pages/
git commit -m "feat: dataset management and export UI"
```

---

## Phase 8: 集成测试与部署

### Task 8.1: 端到端集成测试

**Files:**
- Create: `tests/e2e/test_upload_to_export.py`

**Step 1: 测试完整链路**

```python
# tests/e2e/test_upload_to_export.py
@pytest.mark.e2e
async def test_full_pipeline(gateway_client, pipeline_worker, sample_mcap_file):
    """
    上传 MCAP → 处理流水线 → 创建任务 → 标注 → 数据集版本 → 导出
    验证整条链路的端到端延迟 < 5 分钟
    """
    start = time.time()

    # 1. 上传
    episode_id = await upload_file(gateway_client, sample_mcap_file)

    # 2. 等待 Episode READY（最多 5 分钟）
    episode = await wait_for_status(gateway_client, episode_id, "ready", timeout=300)
    assert episode["quality_score"] is not None

    # 3. 创建并完成标注任务
    task_id = await create_and_approve_task(gateway_client, episode_id)

    # 4. 创建数据集版本并导出
    version_id = await create_dataset_version(gateway_client, episode_id)
    job_id = await trigger_export(gateway_client, version_id, format="webdataset")
    job = await wait_for_export(gateway_client, job_id, timeout=300)
    assert job["status"] == "completed"
    assert job["manifest_url"] is not None

    elapsed = time.time() - start
    assert elapsed < 300, f"Pipeline took {elapsed:.1f}s, exceeds 5min SLA"
```

**Step 2: 运行 E2E**

```bash
make up
pytest tests/e2e/ -m e2e -v --timeout=600
```

**Step 3: Commit**

```bash
git add tests/e2e/
git commit -m "test: end-to-end pipeline integration test"
```

---

### Task 8.2: 生产就绪配置

**Files:**
- Create: `infra/docker-compose.prod.yml`
- Create: `services/gateway/Dockerfile`
- Create: `services/pipeline/Dockerfile`
- Create: `services/dataset-service/Dockerfile`
- Create: `services/task-service/Dockerfile`
- Create: `services/export-worker/Dockerfile`
- Create: `web/Dockerfile`

**Step 1: 各服务 Dockerfile（多阶段构建）**

```dockerfile
# services/gateway/Dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o gateway ./main.go

FROM alpine:3.19
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/gateway /gateway
CMD ["/gateway"]
```

**Step 2: 生产 Compose（含资源限制）**

```yaml
# infra/docker-compose.prod.yml
services:
  gateway:
    build: ../services/gateway
    environment: [ *common-env ]
    deploy:
      resources:
        limits: { cpus: "2", memory: "1G" }

  pipeline:
    build: ../services/pipeline
    deploy:
      replicas: 2  # 并行处理
      resources:
        limits: { cpus: "4", memory: "4G" }  # MCAP 解析内存需求

  export-worker:
    build: ../services/export-worker
    deploy:
      replicas: 2
      resources:
        limits: { cpus: "4", memory: "8G" }  # 大文件导出
```

**Step 3: 最终验证**

```bash
docker compose -f infra/docker-compose.prod.yml build
docker compose -f infra/docker-compose.prod.yml up -d
make migrate
pytest tests/e2e/ -m e2e -v
```

**Step 4: 最终 Commit**

```bash
git add infra/ services/*/Dockerfile web/Dockerfile
git commit -m "chore: production docker builds and compose configuration"
git tag v0.1.0-mvp
```

---

## 开发顺序总览

```
Phase 0: 基础设施 (0.1→0.2→0.3)
    ↓
Phase 1: 认证 (1.1→1.2)
    ↓
Phase 2: 采集 (2.1 上传 → 2.2 流式)     ← 关键路径，其他模块依赖它
    ↓
Phase 3: 流水线 (3.1→3.2→3.3→3.4)      ← Episode 进入 READY 状态
    ↓
Phase 4: 数据集 API (4.1→4.2)            ← 查询、版本快照
    ↓
Phase 5: 标注 (5.1 LS集成 → 5.2 任务API) ← 依赖 Phase 3
    ↓
Phase 6: 导出 (6.1)                      ← 依赖 Phase 4+5
    ↓
Phase 7: 前端 (7.1→7.2→7.3→7.4)        ← 可与 4-6 并行
    ↓
Phase 8: 集成测试 + 部署
```

**可并行开发的模块：**
- Phase 4（数据集 API）与 Phase 5（标注）可在 Phase 3 完成后并行
- Phase 7（前端）可在 Phase 1 完成后并行推进（Mock API 先行）
