# EmbedAI DataHub — 设计目录

多模态数据管理平台（具身机器人领域），覆盖数据采集、处理、标注、数据集管理与训练导出全链路。

## 导航

| 文档 | 说明 |
|------|------|
| [需求文档](requirements.md) | 业务目标、角色、约束、成功标准 |
| [全局事件流](#全局事件流-big-picture) | EventStorming 大图 |
| [流程: 数据采集](#流程-数据采集) | 上传 + 实时流接入 |
| [流程: 标注](#流程-标注) | 任务创建 → 执行 → 审核 |
| [流程: 数据集导出](#流程-数据集导出) | 版本化 → 导出 → 云存储 |
| [实体关系图](#实体关系图-erd) | 核心数据模型 |
| [状态图: Episode](#状态图-episode) | 数据录制片段生命周期 |
| [状态图: 标注任务](#状态图-标注任务) | 标注任务状态机 |
| [时序: 文件上传](#时序-文件上传) | 分块上传 + 断点续传 |
| [时序: 标注工作流](#时序-标注工作流) | 端到端标注交互 |
| [时序: 导出任务](#时序-导出任务) | 异步导出到云存储 |
| [关键决策点](#关键决策点-hotspots) | 未定义的架构选择 |
| [技术栈建议](#技术栈建议) | 基于需求的选型推荐 |

---

## 全局事件流 Big Picture

```mermaid
flowchart LR
    classDef event fill:#ff9800,stroke:#e65100,color:#000
    classDef command fill:#2196f3,stroke:#0d47a1,color:#fff
    classDef actor fill:#ffeb3b,stroke:#f57f17,color:#000
    classDef system fill:#9c27b0,stroke:#4a148c,color:#fff
    classDef aggregate fill:#4caf50,stroke:#1b5e20,color:#fff
    classDef hotspot fill:#f44336,stroke:#b71c1c,color:#fff

    Robot[机器人/仿真器]:::actor
    DataEng[数据工程师]:::actor
    Annotator[标注员]:::actor
    Reviewer[审核员]:::actor
    MLEng[算法工程师]:::actor
    CloudStorage[云对象存储\nS3兼容]:::system
    TrainingPlatform[云端训练平台]:::system

    CmdUpload[上传 MCAP/HDF5]:::command
    CmdStream[开始实时流接入]:::command
    EvtFileReceived[文件已接收]:::event
    EvtStreamStarted[流接入已开始]:::event
    AggEpisode[Episode\n录制片段]:::aggregate

    Robot --> CmdUpload
    Robot --> CmdStream
    CmdUpload --> EvtFileReceived
    CmdStream --> EvtStreamStarted
    EvtFileReceived --> AggEpisode
    EvtStreamStarted --> AggEpisode

    EvtMetaExtracted[元数据已提取\nTopics/时长/传感器]:::event
    EvtQualityChecked[质量检查完成]:::event
    EvtEpisodeReady[Episode 可用]:::event
    HotQuality[? 质量检查规则\n如何定义?]:::hotspot

    AggEpisode --> EvtMetaExtracted
    EvtMetaExtracted --> EvtQualityChecked
    EvtQualityChecked -.question.- HotQuality
    EvtQualityChecked --> EvtEpisodeReady

    CmdCreateTask[创建标注任务]:::command
    CmdAssignTask[分配任务]:::command
    CmdSubmitAnno[提交标注]:::command
    CmdReview[审核标注]:::command
    EvtTaskCreated[标注任务已创建]:::event
    EvtTaskAssigned[任务已分配]:::event
    EvtAnnoSubmitted[标注已提交]:::event
    EvtAnnoApproved[标注已通过]:::event
    EvtAnnoRejected[标注已驳回]:::event
    AggTask[AnnotationTask]:::aggregate
    AggAnnotation[Annotation]:::aggregate
    HotTool[? 标注工具\n自研还是集成?]:::hotspot

    EvtEpisodeReady --> CmdCreateTask
    DataEng --> CmdCreateTask
    CmdCreateTask --> EvtTaskCreated
    EvtTaskCreated --> AggTask
    DataEng --> CmdAssignTask
    CmdAssignTask --> EvtTaskAssigned
    EvtTaskAssigned --> Annotator
    Annotator --> CmdSubmitAnno
    CmdSubmitAnno --> EvtAnnoSubmitted
    EvtAnnoSubmitted --> AggAnnotation
    Reviewer --> CmdReview
    CmdReview --> EvtAnnoApproved
    CmdReview --> EvtAnnoRejected
    EvtAnnoRejected -.retry.-> Annotator
    AggAnnotation -.question.- HotTool

    CmdCurateDataset[策划数据集]:::command
    CmdCreateVersion[创建版本快照]:::command
    EvtDatasetCreated[数据集已创建]:::event
    EvtVersionCreated[版本已创建]:::event
    AggDataset[Dataset 数据集]:::aggregate

    MLEng --> CmdCurateDataset
    DataEng --> CmdCurateDataset
    EvtAnnoApproved --> CmdCurateDataset
    CmdCurateDataset --> EvtDatasetCreated
    EvtDatasetCreated --> AggDataset
    DataEng --> CmdCreateVersion
    CmdCreateVersion --> EvtVersionCreated
    AggDataset --> EvtVersionCreated

    CmdExport[触发导出]:::command
    EvtExportStarted[导出任务已启动]:::event
    EvtExportDone[数据集已导出]:::event
    HotFormat[? 导出格式\n优先级?]:::hotspot

    MLEng --> CmdExport
    EvtVersionCreated --> CmdExport
    CmdExport --> EvtExportStarted
    EvtExportStarted --> CloudStorage
    CloudStorage --> EvtExportDone
    EvtExportDone --> TrainingPlatform
    EvtExportDone -.question.- HotFormat
```

---

## 流程: 数据采集

```mermaid
flowchart TD
    classDef event fill:#ff9800,stroke:#e65100,color:#000
    classDef command fill:#2196f3,stroke:#0d47a1,color:#fff
    classDef actor fill:#ffeb3b,stroke:#f57f17,color:#000
    classDef system fill:#9c27b0,stroke:#4a148c,color:#fff
    classDef aggregate fill:#4caf50,stroke:#1b5e20,color:#fff
    classDef hotspot fill:#f44336,stroke:#b71c1c,color:#fff

    Robot[机器人 / 操作员]:::actor
    CmdInit[初始化分块上传\n文件名/大小/格式]:::command
    EvtUploadInit[上传会话已创建]:::event
    CmdUploadChunk[上传分块\nchunk N/Total]:::command
    EvtChunkReceived[分块已接收]:::event
    CmdComplete[完成上传]:::command
    EvtFileAssembled[文件已组装]:::event

    Robot --> CmdInit
    CmdInit --> EvtUploadInit
    EvtUploadInit --> CmdUploadChunk
    CmdUploadChunk --> EvtChunkReceived
    EvtChunkReceived -->|更多分块| CmdUploadChunk
    EvtChunkReceived -->|全部完成| CmdComplete
    CmdComplete --> EvtFileAssembled

    Robot2[机器人\n实时运行]:::actor
    CmdStreamOpen[建立流式连接\ngRPC stream]:::command
    EvtStreamOpened[流连接已建立]:::event
    CmdWriteFrame[写入帧数据\nMCAP Message]:::command
    EvtFrameBuffered[帧已缓冲]:::event
    CmdStreamClose[关闭流]:::command
    EvtStreamSealed[流数据已封存\n→ 生成 MCAP 文件]:::event
    HotBuffer[? 断线重连\n数据连续性策略?]:::hotspot

    Robot2 --> CmdStreamOpen
    CmdStreamOpen --> EvtStreamOpened
    EvtStreamOpened --> CmdWriteFrame
    CmdWriteFrame --> EvtFrameBuffered
    EvtFrameBuffered -->|持续写入| CmdWriteFrame
    EvtFrameBuffered -.question.- HotBuffer
    CmdStreamClose --> EvtStreamSealed

    EvtFileAssembled --> PipelineTrigger
    EvtStreamSealed --> PipelineTrigger

    PipelineTrigger[触发处理流水线]:::command
    EvtStoredRaw[原始文件已存储]:::event
    EvtHashVerified[完整性校验通过]:::event
    EvtMetaExtracted[元数据已提取]:::event
    EvtTopicsIndexed[Topics/Channels 已索引]:::event
    EvtThumbnailGen[预览帧已生成]:::event
    EvtQualityScored[质量评分完成]:::event
    EvtEpisodeReady[Episode 状态 → READY]:::event
    AggEpisode[Episode Aggregate]:::aggregate
    HotQuality[? 质量评分维度?]:::hotspot

    PipelineTrigger --> EvtStoredRaw
    EvtStoredRaw --> EvtHashVerified
    EvtHashVerified --> EvtMetaExtracted
    EvtMetaExtracted --> EvtTopicsIndexed
    EvtTopicsIndexed --> EvtThumbnailGen
    EvtThumbnailGen --> EvtQualityScored
    EvtQualityScored -.question.- HotQuality
    EvtQualityScored --> EvtEpisodeReady
    EvtEpisodeReady --> AggEpisode
```

---

## 流程: 标注

```mermaid
flowchart TD
    classDef event fill:#ff9800,stroke:#e65100,color:#000
    classDef command fill:#2196f3,stroke:#0d47a1,color:#fff
    classDef actor fill:#ffeb3b,stroke:#f57f17,color:#000
    classDef system fill:#9c27b0,stroke:#4a148c,color:#fff
    classDef aggregate fill:#4caf50,stroke:#1b5e20,color:#fff
    classDef hotspot fill:#f44336,stroke:#b71c1c,color:#fff

    DataEng[数据工程师]:::actor
    Annotator[标注员]:::actor
    Reviewer[审核员]:::actor
    AnnoTool[标注工具 Web App]:::system

    CmdDefineTask[定义标注任务]:::command
    EvtTaskDefined[标注任务已定义]:::event
    AggTask[AnnotationTask]:::aggregate
    CmdAssign[分配给标注员]:::command
    EvtAssigned[任务已分配]:::event
    HotAssign[? 自动分配策略?]:::hotspot

    DataEng --> CmdDefineTask
    CmdDefineTask --> EvtTaskDefined
    EvtTaskDefined --> AggTask
    AggTask --> CmdAssign
    DataEng --> CmdAssign
    CmdAssign --> EvtAssigned
    EvtAssigned -.question.- HotAssign
    EvtAssigned --> Annotator

    CmdLoadData[加载任务数据]:::command
    EvtDataLoaded[数据已加载]:::event
    CmdAnnotate[执行标注]:::command
    EvtDraftSaved[草稿已保存]:::event
    CmdSubmit[提交标注]:::command
    EvtSubmitted[标注已提交]:::event
    AggAnnotation[Annotation]:::aggregate
    HotTool[? 标注工具\n自研 or 集成?]:::hotspot

    Annotator --> CmdLoadData
    CmdLoadData --> EvtDataLoaded
    EvtDataLoaded --> AnnoTool
    AnnoTool -.question.- HotTool
    AnnoTool --> CmdAnnotate
    CmdAnnotate --> EvtDraftSaved
    EvtDraftSaved -->|继续| CmdAnnotate
    Annotator --> CmdSubmit
    CmdSubmit --> EvtSubmitted
    EvtSubmitted --> AggAnnotation

    CmdApprove[通过标注]:::command
    CmdReject[驳回标注]:::command
    EvtApproved[标注已通过]:::event
    EvtRejected[标注已驳回]:::event

    Reviewer --> CmdApprove
    Reviewer --> CmdReject
    AggAnnotation --> CmdApprove
    AggAnnotation --> CmdReject
    CmdApprove --> EvtApproved
    CmdReject --> EvtRejected
    EvtRejected -->|重新分配| CmdAssign
```

---

## 流程: 数据集导出

```mermaid
flowchart TD
    classDef event fill:#ff9800,stroke:#e65100,color:#000
    classDef command fill:#2196f3,stroke:#0d47a1,color:#fff
    classDef actor fill:#ffeb3b,stroke:#f57f17,color:#000
    classDef system fill:#9c27b0,stroke:#4a148c,color:#fff
    classDef aggregate fill:#4caf50,stroke:#1b5e20,color:#fff
    classDef hotspot fill:#f44336,stroke:#b71c1c,color:#fff

    MLEng[算法工程师]:::actor
    DataEng[数据工程师]:::actor
    CloudStorage[云对象存储]:::system
    TrainingPlatform[云端训练平台]:::system

    CmdSearch[搜索/过滤 Episodes]:::command
    EvtSearchResult[搜索结果返回]:::event
    CmdSelectClips[选定数据范围]:::command
    EvtClipsSelected[数据范围已确定]:::event
    CmdCreateDataset[创建数据集]:::command
    EvtDatasetCreated[数据集已创建]:::event
    AggDataset[Dataset]:::aggregate

    MLEng --> CmdSearch
    CmdSearch --> EvtSearchResult
    EvtSearchResult --> CmdSelectClips
    CmdSelectClips --> EvtClipsSelected
    EvtClipsSelected --> CmdCreateDataset
    CmdCreateDataset --> EvtDatasetCreated
    EvtDatasetCreated --> AggDataset

    CmdSnapshotVersion[创建版本快照]:::command
    EvtVersionSnapshotted[版本快照已创建]:::event
    HotVersion[? 版本策略:\n完整快照 vs diff?]:::hotspot
    AggDataset --> CmdSnapshotVersion
    CmdSnapshotVersion --> EvtVersionSnapshotted
    EvtVersionSnapshotted -.question.- HotVersion

    CmdTriggerExport[触发导出]:::command
    EvtExportJobCreated[导出任务已创建]:::event
    AggExportJob[ExportJob]:::aggregate
    EvtDataExtracted[原始数据已提取]:::event
    EvtAnnotationsMerged[标注已合并]:::event
    EvtFormatConverted[格式转换完成]:::event
    EvtUploadedToCloud[已上传云存储]:::event
    EvtExportCompleted[导出完成]:::event
    HotFormat[? 导出格式优先级?]:::hotspot

    MLEng --> CmdTriggerExport
    EvtVersionSnapshotted --> CmdTriggerExport
    CmdTriggerExport --> EvtExportJobCreated
    EvtExportJobCreated --> AggExportJob
    AggExportJob --> EvtDataExtracted
    EvtDataExtracted --> EvtAnnotationsMerged
    EvtAnnotationsMerged --> EvtFormatConverted
    EvtFormatConverted -.question.- HotFormat
    EvtFormatConverted --> EvtUploadedToCloud
    EvtUploadedToCloud --> CloudStorage
    EvtUploadedToCloud --> EvtExportCompleted
    EvtExportCompleted --> TrainingPlatform
```

---

## 实体关系图 ERD

```mermaid
erDiagram
    PROJECT {
        uuid id PK
        string name
        string description
        timestamp created_at
    }
    USER {
        uuid id PK
        string name
        string email
        enum role "admin|engineer|annotator_internal|annotator_outsource"
        uuid project_id FK
    }
    EPISODE {
        uuid id PK
        uuid project_id FK
        string filename
        enum format "mcap|hdf5"
        bigint size_bytes
        float duration_seconds
        enum status "uploading|processing|ready|failed|archived"
        float quality_score
        jsonb metadata
        string storage_path
        timestamp recorded_at
    }
    TOPIC {
        uuid id PK
        uuid episode_id FK
        string name
        enum type "image|pointcloud|imu|force|joint_state|other"
        float start_time_offset
        float end_time_offset
        int message_count
        float frequency_hz
    }
    DATASET {
        uuid id PK
        uuid project_id FK
        string name
        enum status "draft|published|deprecated"
    }
    DATASET_VERSION {
        uuid id PK
        uuid dataset_id FK
        string version_tag
        jsonb episode_refs
        bigint total_size_bytes
        bool is_immutable
    }
    ANNOTATION_TASK {
        uuid id PK
        uuid project_id FK
        uuid dataset_version_id FK
        enum type "bbox2d|keypoint|segment|timeline|multimodal"
        enum status "created|assigned|in_progress|submitted|reviewing|approved|rejected"
        uuid assigned_to FK
        timestamp deadline
    }
    ANNOTATION {
        uuid id PK
        uuid task_id FK
        uuid episode_id FK
        uuid annotator_id FK
        float time_start
        float time_end
        jsonb labels
        int version
        enum status "draft|submitted|approved|rejected"
    }
    EXPORT_JOB {
        uuid id PK
        uuid dataset_version_id FK
        enum format "raw|webdataset|hf_datasets"
        string target_bucket
        enum status "pending|running|completed|failed"
        float progress_pct
        string manifest_url
    }
    UPLOAD_SESSION {
        uuid id PK
        uuid episode_id FK
        int total_chunks
        int received_chunks
        enum status "in_progress|assembling|completed|expired"
    }

    PROJECT ||--o{ USER : "has"
    PROJECT ||--o{ EPISODE : "contains"
    PROJECT ||--o{ DATASET : "owns"
    PROJECT ||--o{ ANNOTATION_TASK : "scopes"
    EPISODE ||--o{ TOPIC : "has"
    EPISODE ||--o{ UPLOAD_SESSION : "created_via"
    EPISODE ||--o{ ANNOTATION : "annotated_in"
    DATASET ||--o{ DATASET_VERSION : "versioned_by"
    DATASET_VERSION ||--o{ ANNOTATION_TASK : "defines_scope_for"
    DATASET_VERSION ||--o{ EXPORT_JOB : "exported_via"
    ANNOTATION_TASK ||--o{ ANNOTATION : "produces"
    USER ||--o{ ANNOTATION_TASK : "assigned_to"
    USER ||--o{ ANNOTATION : "creates"
```

---

## 状态图: Episode

```mermaid
stateDiagram-v2
    [*] --> UPLOADING : 上传会话创建 / 流连接建立
    UPLOADING --> PROCESSING : 文件组装完成 / 流封存
    UPLOADING --> FAILED : 上传超时 / 校验失败
    PROCESSING --> READY : 元数据提取 + 质量评分通过
    PROCESSING --> FAILED : 流水线异常 / 格式损坏
    READY --> ANNOTATING : 纳入标注任务
    READY --> IN_DATASET : 直接加入数据集
    READY --> ARCHIVED : 手动归档
    ANNOTATING --> READY : 所有关联任务完成
    ANNOTATING --> IN_DATASET : 标注审核通过
    IN_DATASET --> ARCHIVED : 数据集版本冻结
    FAILED --> [*] : 删除 / 重新上传
```

---

## 状态图: 标注任务

```mermaid
stateDiagram-v2
    [*] --> CREATED : 数据工程师定义任务
    CREATED --> ASSIGNED : 分配给标注员
    CREATED --> CANCELLED : 取消任务
    ASSIGNED --> IN_PROGRESS : 标注员开始工作
    ASSIGNED --> CREATED : 取消分配
    IN_PROGRESS --> SUBMITTED : 标注员提交
    IN_PROGRESS --> ASSIGNED : 标注员放弃
    SUBMITTED --> REVIEWING : 审核员接单
    REVIEWING --> APPROVED : 审核通过
    REVIEWING --> REJECTED : 审核驳回
    REJECTED --> IN_PROGRESS : 返回修改 version+1
    APPROVED --> [*] : 标注结果可用
    CANCELLED --> [*]
```

---

## 时序: 文件上传

```mermaid
sequenceDiagram
    actor Robot as 机器人/操作员
    participant API as API Gateway (Golang)
    participant UploadSvc as Upload Service (Golang)
    participant ObjStore as 对象存储 (MinIO/S3)
    participant Pipeline as 处理流水线 (Python Worker)
    participant MetaDB as 元数据 DB (PostgreSQL)

    Robot->>API: POST /episodes/upload/init {filename, size, format, checksum}
    API->>MetaDB: 创建 Episode(UPLOADING) + UploadSession
    API-->>Robot: {episode_id, session_id, chunk_size}

    loop 每个分块 (~64MB)
        Robot->>API: PUT /upload/{session_id}/chunk/{n}
        API->>ObjStore: 写入临时分块
        API->>MetaDB: 更新 received_chunks
        API-->>Robot: 200 OK
    end

    Robot->>API: POST /upload/{session_id}/complete
    API->>ObjStore: 合并分块 → 正式路径
    API->>MetaDB: Episode status=PROCESSING
    API->>Pipeline: 发布 EpisodeIngested 事件
    API-->>Robot: 202 Accepted

    Pipeline->>ObjStore: 读取 MCAP/HDF5
    Pipeline->>Pipeline: MD5校验 / Topic解析 / 预览帧 / 质量评分
    Pipeline->>MetaDB: 写入 Topics, Episode status=READY
```

---

## 时序: 标注工作流

```mermaid
sequenceDiagram
    actor DE as 数据工程师
    actor Ann as 标注员
    actor Rev as 审核员
    participant API as API Gateway (Golang)
    participant TaskSvc as Task Service (Python)
    participant AnnoTool as 标注工具 (React)
    participant StreamSvc as 数据流服务 (Golang)
    participant MetaDB as PostgreSQL

    DE->>API: POST /tasks {type, episodes, guideline}
    API->>MetaDB: 创建 Task(CREATED)
    DE->>API: POST /tasks/{id}/assign {user_id}
    API->>MetaDB: Task(ASSIGNED), 通知标注员

    Ann->>AnnoTool: 打开任务
    AnnoTool->>API: GET /tasks/{id}/data-token
    API->>StreamSvc: 生成时限访问令牌
    API-->>AnnoTool: {stream_token}

    AnnoTool->>StreamSvc: 流式请求指定时间段数据
    StreamSvc-->>AnnoTool: Camera/LiDAR/IMU 同步帧流

    loop 标注循环
        Ann->>AnnoTool: 绘制标注
        AnnoTool->>API: POST /annotations/draft (自动保存)
    end

    Ann->>API: POST /annotations/submit
    API->>MetaDB: Annotation(SUBMITTED), Task(SUBMITTED)

    Rev->>API: POST /tasks/{id}/approve
    API->>MetaDB: Annotation(APPROVED)
```

---

## 时序: 导出任务

```mermaid
sequenceDiagram
    actor MLE as 算法工程师
    participant API as API Gateway (Golang)
    participant DatasetSvc as Dataset Service (Python)
    participant ExportWorker as Export Worker (Python)
    participant ObjStore as 内部对象存储
    participant CloudStore as 云端 S3

    MLE->>API: POST /datasets/{id}/versions {filter, version_tag}
    API->>DatasetSvc: 创建不可变 DatasetVersion
    API-->>MLE: {version_id, episode_count, size_estimate}

    MLE->>API: POST /export-jobs {version_id, format, target_bucket}
    API-->>MLE: {job_id}
    API->>ExportWorker: 异步触发

    loop 每个 Episode (并行)
        ExportWorker->>ObjStore: 提取 MCAP clip / HDF5 slice
        ExportWorker->>ExportWorker: 合并标注 + 格式转换
        ExportWorker->>CloudStore: 上传 shard 文件
    end

    ExportWorker->>CloudStore: 上传 manifest.json
    ExportWorker->>API: ExportJob(COMPLETED)

    MLE->>API: GET /export-jobs/{job_id}
    API-->>MLE: {status: completed, manifest_url}
```

---

## 架构决策 ADR

详见 [decisions.md](decisions.md)，以下为摘要：

| # | 决策点 | 决策 |
|---|--------|------|
| H1 | **质量评分维度** | 帧率稳定性(40%) + 传感器完整性(40%) + 信号质量(20%)；< 0.6 标记 low_quality，< 0.3 自动隔离 |
| H2 | **实时流断线重连** | 客户端 seq_num + 服务端 5s 滑动缓冲；断线 > 30s 封存当前片段，重连开新 Episode，通过 session_id 关联 |
| H3 | **标注工具** | MVP 集成 Label Studio（自托管）；通过 REST API + Webhook 与平台双向同步；中期评估自研时序查看器 |
| H4 | **任务分配** | 默认手动分配（展示实时负载辅助决策）；预留 `mode=auto`（skill_tags 匹配 + 最少任务数优先），后续按需启用 |
| H5 | **数据集版本** | 引用快照：存 `{episode_id, clip_start, clip_end, topic_filter}`，不复制原始文件；版本创建后不可变 |
| H6 | **导出格式** | P0: WebDataset shard（200-500MB/shard）+ 裸文件/JSON sidecar；P1: HuggingFace Parquet（HDF5 场景） |

---

## 技术栈建议

| 层 | 组件 | 技术选型 | 理由 |
|----|------|----------|------|
| API 网关 | HTTP + gRPC | **Golang (Gin/gRPC)** | 高并发上传/流接入，低延迟 |
| 业务服务 | Task / Dataset / Export | **Python (FastAPI)** | 丰富的 MCAP/HDF5 生态 |
| 元数据存储 | 关系型 DB | **PostgreSQL + JSONB** | 灵活的 metadata 查询 |
| 原始数据存储 | 对象存储 | **MinIO** (本地 TB 级) | S3 兼容，自托管 |
| 消息队列 | 异步流水线触发 | **Redis Streams** 或 **NATS** | 轻量，适合 TB 级初期规模 |
| 处理流水线 | Worker | **Python + mcap SDK + h5py** | 直接利用官方 SDK |
| 前端 | Web App | **React + TypeScript** | 已定，推荐 TanStack Query + Zustand |
| 标注工具 (MVP) | 集成 | **Label Studio** (开源) | 支持视频/时序，有 REST API |
| 搜索 | Episode 全文+属性 | **PostgreSQL FTS** 或 **Meilisearch** | 初期 PG 够用 |
| 认证 | 用户/权限 | **Keycloak** 或 JWT + RBAC | 支持外包用户隔离 |
