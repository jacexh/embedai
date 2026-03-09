# Architecture Decision Records (ADR)

## H1 — 数据质量评分维度

**决策：** 三维评分，加权求和，低于阈值的 Episode 自动标记为 `low_quality`，不阻塞入库但在 UI 中高亮警示。

| 维度 | 权重 | 检查内容 |
|------|------|----------|
| 帧率稳定性 | 40% | 各 Topic 实际帧率 vs 标称帧率，允许 ±10% 抖动 |
| 传感器完整性 | 40% | 必需 Topic 是否全部存在（按 Project 配置的 topic schema） |
| 信号质量 | 20% | 图像曝光/模糊检测（Laplacian variance）、IMU 零偏异常检测 |

**阈值：** 总分 < 0.6 → `low_quality` 标记；< 0.3 → 自动隔离，不可加入数据集。

**实现：** Python Worker，处理流水线中独立步骤，结果写入 `Episode.quality_score` 和 `Episode.metadata.quality_detail`。

---

## H2 — 实时流断线重连策略

**决策：** 客户端序列号 + 服务端滑动窗口缓冲，断线后生成独立 Episode 片段，不跨段合并。

**具体方案：**

```
客户端行为：
  - 每帧携带单调递增 seq_num
  - 断线后尝试重连（指数退避，最长 30s）
  - 重连时携带 last_ack_seq，服务端从此处续传

服务端行为：
  - 滑动窗口缓冲 5 秒数据（防乱序）
  - 断线超过 30s → 封存当前片段，生成 Episode A
  - 重连成功 → 开启新 Episode B，metadata 记录 parent_session_id
  - 同一次任务的多个 Episode 通过 session_id 关联，供后续拼接
```

**存储：** 断线产生的多个 Episode 通过 `Episode.metadata.session_id` 和 `recording_session` 表关联，算法侧可按需拼接。

---

## H3 — 标注工具选型

**决策：** MVP 集成 Label Studio（开源自托管），中期评估自研。

**阶段计划：**

| 阶段 | 方案 | 触发条件 |
|------|------|----------|
| MVP | Label Studio（Docker 自托管） | 立即 |
| 中期 | Label Studio + 自研时序查看器（React） | 时序/多模态联合标注体验不满足需求时 |
| 长期 | 完全自研标注工具 | 团队规模 > 20 标注员，或需要深度 MCAP 时间轴联动时 |

**集成方式：**
- 平台通过 Label Studio REST API 创建/同步任务
- 数据通过平台 Stream API 代理给 Label Studio（不直接暴露对象存储）
- 标注结果通过 Webhook 回写平台 Annotation 表

**外包隔离：** 外包标注员账号在 Label Studio 侧也按 Project 隔离，与平台 RBAC 同步。

---

## H4 — 标注任务分配策略

**决策：** 初期手动分配，系统支持过滤辅助；预留自动分配接口，后续按需启用。

**分配模式（可配置）：**

```
mode=manual   : 管理员从候选人列表选择，系统展示当前负载
mode=auto     : 按 skill_tags 匹配 + 当前任务数最少者优先（Round-Robin）
```

**字段设计：**
- `User.skill_tags`: `["3d_bbox", "keypoint", "timeline"]`，管理员维护
- `AnnotationTask.required_skills`: 创建任务时指定，用于自动匹配过滤

**负载展示：** 管理员视图实时展示每个标注员「待完成任务数 / 本周已完成数」，辅助手动决策。

---

## H5 — 数据集版本策略

**决策：** 引用快照（Reference Snapshot），不复制原始文件。

**方案：**

```
DatasetVersion 记录：
  episode_refs: [
    {
      episode_id: "uuid",
      clip_start:  12.5,   // 秒，null = 从头
      clip_end:    87.3,   // 秒，null = 到尾
      topic_filter: ["/camera/rgb", "/joint_states"],  // null = 全部 Topic
      annotation_ids: ["uuid1", "uuid2"]               // 绑定的标注
    },
    ...
  ]
  is_immutable: true   // 快照创建后禁止修改 episode_refs
```

**版本不可变性：** `DatasetVersion` 一旦创建即冻结，后续修改只能创建新版本。删除 Episode 不影响已有版本（逻辑删除，对象存储保留）。

**存储成本：** 原始文件只存一份；导出时才做实际的 clip 提取，不提前复制。

---

## H6 — 导出格式优先级

**决策：** 主推 WebDataset，兼容裸文件 + JSON sidecar，按需支持 HuggingFace datasets。

| 格式 | 优先级 | 适用场景 |
|------|--------|----------|
| **WebDataset** (`.tar` shard) | P0 | PyTorch 流式训练，大规模数据，云存储直读 |
| **裸文件 + JSON sidecar** | P0 | 调试、自定义加载器、MCAP 原生消费 |
| **HuggingFace datasets** (Parquet) | P1 | 与 HF 生态对接，结构化特征数据（HDF5 来源） |

**WebDataset shard 结构：**
```
shard-000000.tar
  episode_abc123_000.mcap       ← 原始 MCAP clip
  episode_abc123_000.json       ← 标注 + 元数据
  episode_abc123_001.mcap
  episode_abc123_001.json
  ...
```

**Shard 大小目标：** 200–500 MB / shard，便于并行加载和断点续传。

**格式选择：** 导出时由算法工程师在 Export Job 中指定 `format` 字段，多格式可并行导出。
