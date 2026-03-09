# EmbedAI DataHub

具身机器人数据管理平台——支持 MCAP/HDF5 数据录制的上传、处理、标注与导出全流程。

## 目录

- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [服务说明](#服务说明)
- [数据库结构](#数据库结构)
- [Make 命令](#make-命令)
- [默认账号](#默认账号)
- [开发指南](#开发指南)

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                  Browser / Client                   │
└───────────────────────┬─────────────────────────────┘
                        │ :3000
                        ▼
              ┌─────────────────┐
              │   Nginx + React  │  web (TypeScript/React 19)
              └────────┬────────┘
                       │ proxy /auth /api/v1
                       ▼
              ┌─────────────────┐
              │    Gateway       │  :8000  Go / Gin
              │  (JWT 认证中心)  │  :9090  gRPC
              └──┬──────────┬───┘
                 │          │ reverse proxy
         ┌───────┘          └────────────┐
         ▼                               ▼
┌────────────────┐             ┌──────────────────┐
│ dataset-service │  :8001     │  task-service     │  :8002
│  FastAPI/Python │            │  FastAPI/Python   │
└────────┬────────┘            └────────┬──────────┘
         │                              │
         └──────────┬───────────────────┘
                    ▼
        ┌───────────────────────┐
        │      PostgreSQL       │  共享数据库
        └───────────────────────┘

后台工作进程（无外部端口）:
  pipeline × 2  ←── Redis Stream ←── gateway (上传完成事件)
  export-worker × 2  ←── Redis Stream ←── dataset-service (导出请求)

对象存储:
  MinIO (S3 兼容)  ←── gateway 存储原始文件，pipeline 读取处理
```

**技术栈**

| 组件 | 技术 |
|------|------|
| API 网关 | Go 1.25 · Gin · pgx · JWT |
| 数据集服务 | Python 3.11 · FastAPI · SQLAlchemy · asyncpg |
| 任务服务 | Python 3.11 · FastAPI · Label Studio 集成 |
| 数据管道 | Python 3.11 · MCAP · HDF5 · OpenCV |
| 导出工作进程 | Python 3.11 · WebDataset · aioboto3 |
| 前端 | TypeScript · React 19 · TanStack Query · Zustand · Tailwind CSS |
| 数据库 | PostgreSQL 16 |
| 对象存储 | MinIO |
| 消息队列 | Redis 7 (Streams) |
| 标注工具 | Label Studio |

---

## 快速开始

### 前提条件

- Docker & Docker Compose
- Go 1.25+（本地开发 gateway 时需要）
- [uv](https://docs.astral.sh/uv/)（本地开发 Python 服务时需要）

### 一键启动（生产模式）

```bash
# 1. 构建所有镜像
make prod-build

# 2. 启动全栈
make e2e-up
# 等价于: docker compose up -d + migrate + seed
```

访问 http://localhost:3000，使用 [默认账号](#默认账号) 登录。

### 分步启动

```bash
# 启动基础设施（postgres, minio, redis, label-studio）
make up

# 运行数据库迁移
make migrate

# 写入初始数据（桶、项目、演示账号）
make seed

# 启动应用服务
docker compose -f infra/docker-compose.prod.yml up -d \
  gateway dataset-service task-service pipeline export-worker web
```

---

## 服务说明

### 对外暴露端口

| 端口 | 服务 | 说明 |
|------|------|------|
| **3000** | Web UI (Nginx) | 主入口，含 API 反向代理 |
| **8000** | Gateway | REST API / gRPC :9090 |
| **8001** | dataset-service | 数据集管理 API（直连调试用） |
| **8002** | task-service | 标注任务 API（直连调试用） |

> 正常使用时所有请求通过 `:3000` 的 Nginx 代理，无需直接访问后端端口。

### 页面功能

| 路径 | 功能 |
|------|------|
| `/episodes` | 数据录制列表，支持状态/格式/质量过滤，创建标注任务 |
| `/upload` | 拖拽上传 MCAP / HDF5 文件，分块传输，实时进度 |
| `/datasets` | 数据集管理，创建版本，跳转导出 |
| `/tasks` | 标注任务分配与状态跟踪，Label Studio 集成 |
| `/export` | 导出任务管理，支持 WebDataset / HuggingFace / 裸文件格式 |

### 数据处理流程

```
用户上传文件
    │
    ▼ gateway 分块接收 → 写入 MinIO
    │
    ▼ 发布事件到 Redis Stream (episodes:ingested)
    │
    ▼ pipeline worker 消费
      ├─ 下载文件到临时目录
      ├─ 解析 MCAP/HDF5 元数据（话题、时长、频率）
      ├─ 质量评分（帧率稳定性、传感器完整性）
      ├─ 生成缩略图（首帧图像）
      └─ 写回数据库，状态 → ready
```

---

## 数据库结构

主要数据表（PostgreSQL 16）：

```
projects          项目（租户隔离单元，含话题 Schema 配置）
users             用户（admin / engineer / annotator_internal / annotator_outsource）
episodes          数据录制文件（MCAP/HDF5）
topics            录制中的 ROS 话题
upload_sessions   分块上传会话管理
datasets          数据集
dataset_versions  数据集版本快照
annotation_tasks  标注任务
annotations       标注结果
export_jobs       导出任务
recording_sessions 录制会话
```

迁移脚本位于 `shared/migrations/versions/`，由 Alembic 管理。

---

## Make 命令

### 开发

```bash
make up                 # 启动基础设施（postgres/minio/redis/label-studio）
make down               # 停止基础设施

make dev-services       # 启动开发模式后端服务（热重载）
make dev-services-down  # 停止开发模式服务
```

### 数据库

```bash
make migrate            # 运行 Alembic 迁移（在 docker 网络内执行）
make seed               # 写入初始数据（开发环境，含演示账号）
make seed-prod ADMIN_PASSWORD=xxx   # 写入生产初始数据（仅 admin 账号）
```

### 测试

```bash
make test-gateway       # Gateway 单元测试（Go）
make test-pipeline      # Pipeline 单元测试（Python/pytest）
make test-all           # 运行全部单元测试
make e2e-up             # 启动完整栈 + migrate + seed
make e2e                # 运行端到端集成测试
make e2e-down           # 停止 E2E 栈
```

### 生产

```bash
make prod-build         # 构建所有 Docker 镜像
```

---

## 默认账号

> ⚠️ 以下为开发/演示用途的默认密码，**生产环境部署前必须修改**。

| 角色 | 邮箱 | 密码 |
|------|------|------|
| 管理员 | admin@embedai.local | `Admin@2026!` |
| 数据工程师 | engineer@embedai.local | `Engineer@2026!` |
| 内部标注员 | annotator1@embedai.local | `Annotator@2026!` |
| 外包标注员 | outsource1@embedai.local | `Outsource@2026!` |

**MinIO 控制台**（http://localhost:9001）：
- 用户名：`minioadmin`
- 密码：`minioadmin123`

---

## 开发指南

### 项目结构

```
embedai/
├── infra/                  # Docker Compose & 配置
│   ├── docker-compose.yml       # 基础设施（开发）
│   ├── docker-compose.dev.yml   # 后端服务（热重载开发）
│   └── docker-compose.prod.yml  # 完整生产栈
├── services/
│   ├── gateway/            # Go API 网关
│   ├── dataset-service/    # Python 数据集服务
│   ├── task-service/       # Python 标注任务服务
│   ├── pipeline/           # Python 数据处理管道
│   └── export-worker/      # Python 导出工作进程
├── shared/
│   ├── migrations/         # Alembic 数据库迁移
│   └── proto/              # gRPC Protobuf 定义
├── web/                    # React 前端
├── tests/                  # 端到端集成测试
└── Makefile
```

### 本地开发（热重载）

```bash
# 1. 启动基础设施 + Python 后端（热重载）
make dev-services

# 2. 本地运行 Gateway
DATABASE_URL=postgresql://embedai:embedai_dev@localhost:5432/embedai \
JWT_SECRET=dev-secret-change-in-production \
go run ./services/gateway

# 3. 本地运行前端
cd web && npm install && npm run dev
# → http://localhost:5173
```

开发模式端口映射：

| 端口 | 服务 |
|------|------|
| 5432 | PostgreSQL |
| 6379 | Redis |
| 9000 | MinIO API |
| 9001 | MinIO Console |
| 8080 | Label Studio |
| 8100 | dataset-service（热重载） |
| 8200 | task-service（热重载） |

### 环境变量

参考 `.env.example` 配置本地环境变量。关键变量：

```env
JWT_SECRET=change_me_in_production   # 所有服务共用，必须一致
LABEL_STUDIO_API_KEY=<首次登录 Label Studio 后获取>
ADMIN_PASSWORD=<生产环境 seed 时指定>
```

### 支持的数据格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| MCAP | `.mcap` | ROS 2 原生格式，支持话题/消息提取 |
| HDF5 | `.h5` `.hdf5` | 通用科学数据格式 |

### 导出格式

| 格式 | 说明 |
|------|------|
| WebDataset | 推荐，200-500MB/shard，适合大规模训练 |
| 裸文件 + JSON | 原始文件 + sidecar 元数据 |
| HuggingFace Parquet | 适合 HF Datasets 生态 |
