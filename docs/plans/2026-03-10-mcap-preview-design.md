# MCAP 文件预览功能设计文档

## 背景

EmbedAI DataHub 是一个具身机器人数据管理平台，支持 MCAP/HDF5 数据录制的上传、处理、标注与导出。MCAP 文件包含多个 ROS 话题（Topics），包括视频流、点云、IMU 等传感器数据。

当前系统已支持：
- MCAP 文件上传和元数据提取
- Topic 列表展示（名称、类型、消息数、频率）
- 缩略图生成（首帧图像）

需要新增：MCAP 文件预览功能，支持在网页上展示多路视频并拖动播放。

## 目标

1. 在网页上同时展示 MCAP 文件中的多路视频（图像类 topic）
2. 支持时间轴拖动查看特定时刻的画面
3. 支持播放控制（播放/暂停/快进）
4. 自适应布局，适应不同数量的视频通道

## 非目标

1. 不实现实时流式传输（WebRTC/WebSocket）—— 采用按需帧提取
2. 不预生成完整 MP4 视频 —— 避免额外存储开销
3. 不处理非图像类 topic（点云、IMU 等）的可视化

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                          Browser (React)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  McapPreviewPage                                        │   │
│  │  ┌─────────────────┐  ┌─────────────────┐              │   │
│  │  │   VideoGrid     │  │  TimelineControl │              │   │
│  │  │  ┌───┐ ┌───┐   │  │  [=========O===] │              │   │
│  │  │  │V1 │ │V2 │   │  │  [▶] [⏸] [⏩]   │              │   │
│  │  │  └───┘ └───┘   │  └─────────────────┘              │   │
│  │  └─────────────────┘                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP GET /frame?topic=X&ts=Y
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      dataset-service (Python/FastAPI)           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Frame        │  │ MCAP         │  │ MinIO        │          │
│  │ Extractor    │──│ Reader       │──│ Client       │          │
│  │ (New)        │  │ (mcap-py)    │  │ (Existing)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 组件设计

### 1. 后端 API

#### GET /episodes/{id}/topics
返回指定 episode 的所有 topic 列表（已有，无需修改）。

#### GET /episodes/{id}/frame
提取指定时间点的图像帧。

**Query Parameters:**
- `topic` (required): Topic 名称，如 `/camera/front`
- `timestamp` (required): 时间戳（纳秒），如 `1234567890000000000`

**Response:**
- Content-Type: `image/jpeg`
- Body: JPEG 图像数据

**错误码:**
- 404: Topic 不存在或该时间点无图像
- 400: 参数错误

**实现逻辑:**
1. 从 MinIO 下载 MCAP 文件到本地临时文件（或检查本地缓存）
2. 使用 mcap-py 库定位到指定时间戳附近的消息
3. 解码图像消息（sensor_msgs/Image 或 CompressedImage）
4. 转换为 JPEG 格式返回
5. 缓存提取结果（可选优化）

### 2. 前端组件

#### McapPreviewPage
主页面，协调所有子组件。

**State:**
- `episodeId`: 当前预览的 episode ID
- `imageTopics`: 图像类 topic 列表
- `currentTime`: 当前时间戳（纳秒）
- `isPlaying`: 是否正在播放
- `duration`: 录制总时长（秒）
- `playbackRate`: 播放倍速（0.5x, 1x, 2x）

#### VideoGrid
自适应视频网格布局。

**Props:**
- `topics`: Topic 列表
- `currentTime`: 当前时间戳
- `frames`: Map<topic, frameUrl>

**布局策略:**
```
1 topic   → 1×1 (全屏)
2 topics  → 1×2 (左右)
3-4 topics→ 2×2
5-6 topics→ 2×3
7-9 topics→ 3×3
10+       → 3×4+ (滚动)
```

#### VideoTile
单个视频显示单元。

**Props:**
- `topic`: Topic 信息（名称、类型）
- `frameUrl`: 当前帧 URL
- `isLoading`: 是否加载中

**显示:**
- 视频画面（img 标签）
- Topic 名称 overlay
- 加载状态 spinner

#### TimelineControl
时间轴和播放控制。

**Props:**
- `currentTime`: 当前时间
- `duration`: 总时长
- `isPlaying`: 播放状态
- `onSeek`: 拖动回调
- `onPlay`: 播放回调
- `onPause`: 暂停回调

**功能:**
- 时间轴滑块（0 到 duration，单位毫秒）
- 播放/暂停按钮
- 快进/快退按钮（±5秒）
- 当前时间显示（分:秒.毫秒格式）

### 3. 帧管理

#### useMcapFrames Hook
管理帧数据的获取和缓存。

```typescript
interface UseMcapFramesOptions {
  episodeId: string;
  topics: string[];
  currentTime: number; // nanoseconds
}

interface UseMcapFramesResult {
  frames: Map<string, string>; // topic -> blob URL
  isLoading: boolean;
  preload: (time: number) => void;
}
```

**预加载策略:**
- 播放时预加载接下来 500ms 的帧
- 拖动时间轴后预加载当前时刻前后 250ms
- 使用 LRU 缓存（最多 100 帧）

## 数据流

### 初始加载
```
1. 用户点击 episode 的"预览"按钮
2. 导航到 /preview/{episodeId}
3. 调用 GET /episodes/{id} 获取详情（含 topics）
4. 过滤出 image/compressed_image 类型的 topics
5. 获取第一帧：调用 GET /frame?topic=X&timestamp=start_time
6. 渲染 VideoGrid 和 TimelineControl
```

### 拖动时间轴
```
1. 用户拖动时间轴到时间 T
2. 设置 isPlaying = false（暂停）
3. 并发请求所有视频通道的帧：
   GET /frame?topic=topic1&timestamp=T
   GET /frame?topic=topic2&timestamp=T
   ...
4. 收到所有响应后更新 frames Map
5. 预加载 T-250ms 和 T+250ms 的帧
```

### 播放模式
```
1. 用户点击播放按钮
2. 启动 requestAnimationFrame 循环
3. 每帧计算当前时间：currentTime += deltaTime * playbackRate
4. 如果预加载缓存中有当前时间的帧，直接显示
5. 如果没有，实时请求（降级 gracefully）
6. 到达结束时间时自动暂停
```

## 性能优化

### 后端优化
1. **MCAP 文件缓存**: 短时间内多次请求同一文件时，保持本地文件句柄打开
2. **帧缓存**: 按 (episode_id, topic, timestamp_bucket) 缓存，timestamp_bucket = floor(timestamp / 100ms)
3. **并发控制**: 限制单 episode 的并发帧提取请求数

### 前端优化
1. **Blob URL 缓存**: 已加载的帧转为 Blob URL 缓存，避免重复请求
2. **预加载**: 播放时提前加载接下来 500ms 的帧
3. **降频渲染**: 视频帧率高于显示刷新率时，跳过部分帧
4. **并发请求**: 同时请求所有通道的当前帧

## 错误处理

### 后端错误
- MCAP 文件不存在/损坏 → 500，记录错误日志
- Topic 不存在 → 404
- 时间戳超出范围 → 返回最近的有效帧或 404
- 图像解码失败 → 500

### 前端错误
- 某一通道加载失败 → 显示错误占位图，其他通道正常
- 所有通道都失败 → 显示错误提示，提供重试按钮
- 网络超时 → 自动重试 3 次，然后显示错误

## 界面设计

### 页面布局
```
┌──────────────────────────────────────────────────────────────┐
│  ← 返回列表                              文件名.mcap    时长  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │                  │  │                  │                 │
│  │   /camera/front  │  │  /camera/back    │                 │
│  │                  │  │                  │                 │
│  └──────────────────┘  └──────────────────┘                 │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │                  │  │                  │                 │
│  │  /camera/left    │  │  /camera/right   │                 │
│  │                  │  │                  │                 │
│  └──────────────────┘  └──────────────────┘                 │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  00:12.340                                         02:30.500 │
│  [══════════════════════════════════○═══════════════]       │
│  [▶] [⏸] [←5s] [5s→]                    [0.5x] [1x] [2x]   │
└──────────────────────────────────────────────────────────────┘
```

### 交互细节
- 拖动时间轴时实时显示当前时间 tooltip
- 播放时时间轴进度条平滑动画
- 鼠标悬停视频时显示 topic 名称和当前时间
- 支持键盘快捷键：Space(播放/暂停), ←/→(±5秒)

## 安全考虑

1. **权限检查**: 所有 API 复用现有的 JWT 认证，确保只能访问有权限的 episode
2. **资源限制**: 限制单用户并发帧请求数，防止 DoS
3. **临时文件清理**: 后端定期清理 MCAP 临时下载文件

## 测试策略

### 单元测试
- Frame Extractor 逻辑（mock MCAP 文件）
- useMcapFrames hook（mock API）

### 集成测试
- 端到端：上传 MCAP → 打开预览 → 拖动时间轴 → 验证帧显示

### 性能测试
- 大文件（>1GB）MCAP 的帧提取性能
- 多通道（>6路）同时播放的流畅度

## 后续扩展

1. **预生成 MP4**: 处理 MCAP 时同步生成视频文件，提升播放性能
2. **点云可视化**: 集成 WebGL 点云渲染
3. **传感器数据叠加**: 在视频上叠加 IMU、关节状态等数据
4. **关键帧缓存**: 首次加载时缓存关键时间点的帧，提升拖动响应

## 接口契约

### Frame API
```yaml
GET /episodes/{episode_id}/frame
Parameters:
  topic: string      # Topic 名称，如 "/camera/front"
  timestamp: int64   # 纳秒时间戳

Responses:
  200:
    content:
      image/jpeg:
        schema:
          type: string
          format: binary
  404:
    description: Topic not found or no frame at timestamp
  400:
    description: Invalid parameters
```

### Types
```typescript
interface ImageTopic {
  name: string;
  type: 'image' | 'compressed_image';
  width?: number;
  height?: number;
  encoding?: string;  // e.g., "rgb8", "bgr8", "jpeg"
}

interface McapPreviewState {
  episodeId: string;
  imageTopics: ImageTopic[];
  currentTimeNs: number;
  startTimeNs: number;
  endTimeNs: number;
  isPlaying: boolean;
  playbackRate: number;
}
```
