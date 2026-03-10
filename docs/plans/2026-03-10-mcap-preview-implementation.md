# MCAP 预览功能实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 MCAP 文件多路视频预览功能，支持时间轴拖动和播放控制

**Architecture:** 后端使用 mcap-py 库按需提取指定时间戳的图像帧，前端使用 React + Canvas 展示多路视频网格和播放控制

**Tech Stack:** Python (mcap, mcap-ros2-support, opencv), React 19, TypeScript, TanStack Query

---

## 前置检查

### Task 0: 检查现有依赖

**Step 1: 检查后端依赖**

查看 `services/pipeline/pyproject.toml` 是否已有 mcap 相关依赖。

Run:
```bash
grep -E "mcap|opencv" services/pipeline/pyproject.toml
```

Expected: 已存在 `mcap`, `mcap-ros2-support`, `opencv-python`

**Step 2: 检查前端结构**

查看 `web/src/api/` 目录结构。

Run:
```bash
ls -la web/src/api/
```

Expected: 存在 `client.ts`, `episodes.ts` 等文件

---

## Phase 1: 后端 Frame 提取 API

### Task 1: 创建 Frame 提取服务

**Files:**
- Create: `services/dataset-service/app/services/frame_extractor.py`

**Step 1: 实现 MCAP 帧提取器**

```python
"""Frame extractor service for MCAP files."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from mcap.reader import McapReader


@dataclass
class FrameResult:
    """Result of frame extraction."""

    data: bytes
    timestamp_ns: int
    format: str  # "jpeg" | "png"


class McapFrameExtractor:
    """Extract image frames from MCAP files at specific timestamps."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._reader: McapReader | None = None
        self._image_topics: list[str] | None = None

    def _get_reader(self) -> McapReader:
        """Lazy init reader."""
        if self._reader is None:
            from mcap.reader import make_reader

            self._reader = make_reader(open(self.file_path, "rb"))
        return self._reader

    def get_image_topics(self) -> list[dict]:
        """Get list of image topics in the MCAP file."""
        reader = self._get_reader()
        summary = reader.get_summary()

        topics = []
        if summary and summary.channels:
            for channel_id, channel in summary.channels.items():
                schema = summary.schemas.get(channel.schema_id)
                if schema and schema.name in (
                    "sensor_msgs/msg/Image",
                    "sensor_msgs/msg/CompressedImage",
                ):
                    topics.append({
                        "name": channel.topic,
                        "type": "image" if schema.name == "sensor_msgs/msg/Image" else "compressed_image",
                        "schema_name": schema.name,
                    })
        return topics

    def extract_frame(
        self,
        topic: str,
        target_timestamp_ns: int,
        max_time_diff_ns: int = 100_000_000,  # 100ms tolerance
    ) -> FrameResult | None:
        """Extract the frame closest to target timestamp.

        Args:
            topic: Topic name to extract from
            target_timestamp_ns: Target timestamp in nanoseconds
            max_time_diff_ns: Maximum allowed time difference from target

        Returns:
            FrameResult with JPEG data or None if no frame found
        """
        reader = self._get_reader()

        best_frame: bytes | None = None
        best_timestamp: int | None = None
        min_diff = float("inf")

        for schema, channel, message in reader.iter_messages():
            if channel.topic != topic:
                continue

            if schema and schema.name not in (
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ):
                continue

            time_diff = abs(message.log_time - target_timestamp_ns)
            if time_diff < min_diff:
                min_diff = time_diff
                best_timestamp = message.log_time

                # Decode based on message type
                if schema.name == "sensor_msgs/msg/CompressedImage":
                    best_frame = self._decode_compressed_image(message.data)
                else:
                    best_frame = self._decode_raw_image(message.data)

            # Early exit if we found a very close frame
            if min_diff < max_time_diff_ns:
                break

        if best_frame is None or best_timestamp is None:
            return None

        return FrameResult(
            data=best_frame,
            timestamp_ns=best_timestamp,
            format="jpeg",
        )

    def _decode_compressed_image(self, data: bytes) -> bytes | None:
        """Decode compressed image message."""
        try:
            from rosbags.typesys.types import sensor_msgs__msg__CompressedImage

            msg = sensor_msgs__msg__CompressedImage.deserialize(data)
            # CompressedImage already has JPEG data
            return msg.data.tobytes() if hasattr(msg.data, "tobytes") else bytes(msg.data)
        except Exception as e:
            logger.warning("Failed to decode compressed image: {}", e)
            return None

    def _decode_raw_image(self, data: bytes) -> bytes | None:
        """Decode raw Image message to JPEG."""
        try:
            import cv2
            from rosbags.typesys.types import sensor_msgs__msg__Image

            msg = sensor_msgs__msg__Image.deserialize(data)

            # Convert to numpy array
            height = msg.height
            width = msg.width
            encoding = msg.encoding

            # Handle different encodings
            if encoding in ("rgb8", "bgr8"):
                img = np.frombuffer(msg.data.tobytes() if hasattr(msg.data, "tobytes") else bytes(msg.data), dtype=np.uint8)
                img = img.reshape((height, width, 3))

                # Convert RGB to BGR for OpenCV
                if encoding == "rgb8":
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

                # Encode to JPEG
                success, encoded = cv2.imencode(".jpg", img)
                if success:
                    return encoded.tobytes()
            elif encoding == "mono8":
                img = np.frombuffer(msg.data.tobytes() if hasattr(msg.data, "tobytes") else bytes(msg.data), dtype=np.uint8)
                img = img.reshape((height, width))

                success, encoded = cv2.imencode(".jpg", img)
                if success:
                    return encoded.tobytes()

            logger.warning("Unsupported image encoding: {}", encoding)
            return None
        except Exception as e:
            logger.warning("Failed to decode raw image: {}", e)
            return None

    def close(self):
        """Close the reader and release resources."""
        if self._reader:
            self._reader.close()
            self._reader = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

**Step 2: 添加到项目依赖**

检查并添加 `rosbags` 依赖到 `services/dataset-service/pyproject.toml`:

```toml
dependencies = [
    # ... existing deps
    "rosbags>=0.9.0",
]
```

Run:
```bash
cd services/dataset-service && uv add rosbags
```

**Step 3: Commit**

```bash
git add services/dataset-service/
git commit -m "feat: add MCAP frame extractor service"
```

---

### Task 2: 添加 Frame API 端点

**Files:**
- Modify: `services/dataset-service/app/routers/episodes.py`

**Step 1: 导入依赖和添加路由**

在文件顶部添加：

```python
from fastapi import Response
from fastapi.responses import StreamingResponse

from app.services.frame_extractor import McapFrameExtractor
from app.storage import get_storage_client  # 需要创建
```

**Step 2: 添加 frame 提取端点**

在 episodes.py 末尾添加：

```python
@router.get("/{episode_id}/frame")
async def get_frame(
    episode_id: uuid.UUID,
    topic: str = Query(..., description="Topic name to extract frame from"),
    timestamp: int = Query(..., description="Target timestamp in nanoseconds"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Extract a single frame from MCAP file at specified timestamp."""
    from app.storage import StorageClient

    project_id = uuid.UUID(current_user.project_id)

    # Get episode
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.project_id == project_id,
        )
    )
    ep = result.scalar_one_or_none()
    if ep is None:
        raise HTTPException(status_code=404, detail="episode not found")

    if ep.format != "mcap":
        raise HTTPException(status_code=400, detail="only MCAP format supported")

    if not ep.storage_path:
        raise HTTPException(status_code=400, detail="episode file not available")

    # Download file to temp location
    storage = StorageClient()
    with tempfile.NamedTemporaryFile(suffix=".mcap", delete=False) as tmp:
        tmp_path = tmp.name
        await storage.download_to_file(ep.storage_path, tmp_path)

    try:
        # Extract frame
        with McapFrameExtractor(tmp_path) as extractor:
            frame = extractor.extract_frame(topic, timestamp)

        if frame is None:
            raise HTTPException(status_code=404, detail="no frame found at specified time")

        return Response(
            content=frame.data,
            media_type="image/jpeg",
            headers={
                "X-Frame-Timestamp": str(frame.timestamp_ns),
                "Cache-Control": "private, max-age=300",
            },
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
```

**Step 3: 添加必要的导入**

在文件顶部确保有以下导入：

```python
import os
import tempfile
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
```

**Step 4: Commit**

```bash
git add services/dataset-service/app/routers/episodes.py
git commit -m "feat: add frame extraction API endpoint"
```

---

### Task 3: 添加 StorageClient 下载方法

**Files:**
- Create: `services/dataset-service/app/storage.py`

**Step 1: 实现 StorageClient**

```python
"""MinIO storage client for dataset service."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aioboto3
from app.config import settings


class StorageClient:
    """Async MinIO/S3 storage client."""

    def __init__(self):
        self.endpoint_url = settings.minio_endpoint
        self.bucket = settings.minio_bucket
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key

    async def download_to_file(self, storage_path: str, local_path: str) -> None:
        """Download object from MinIO to local file."""
        session = aioboto3.Session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            await s3.download_file(self.bucket, storage_path, local_path)

    async def get_object_stream(self, storage_path: str):
        """Get object as async stream."""
        session = aioboto3.Session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=storage_path)
            return response["Body"]
```

**Step 2: 更新 config 添加 MinIO 配置**

检查并更新 `services/dataset-service/app/config.py`:

```python
class Settings(BaseSettings):
    # ... existing settings

    # MinIO
    minio_endpoint: str = "http://minio:9000"
    minio_bucket: str = "embedai"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
```

**Step 3: Commit**

```bash
git add services/dataset-service/app/storage.py services/dataset-service/app/config.py
git commit -m "feat: add storage client for frame extraction"
```

---

### Task 4: 测试 Frame API

**Files:**
- Create: `services/dataset-service/tests/test_frame_api.py`

**Step 1: 编写测试**

```python
"""Tests for frame extraction API."""
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_frame_invalid_episode(client: AsyncClient, auth_headers):
    """Test frame extraction with non-existent episode."""
    response = await client.get(
        "/episodes/invalid-id/frame?topic=/camera/front&timestamp=1234567890000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_frame_missing_params(client: AsyncClient, auth_headers):
    """Test frame extraction without required params."""
    # Missing topic
    response = await client.get(
        "/episodes/some-id/frame?timestamp=1234567890000000000",
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Missing timestamp
    response = await client.get(
        "/episodes/some-id/frame?topic=/camera/front",
        headers=auth_headers,
    )
    assert response.status_code == 422
```

**Step 2: 运行测试**

```bash
cd services/dataset-service && uv run pytest tests/test_frame_api.py -v
```

Expected: 测试通过

**Step 3: Commit**

```bash
git add services/dataset-service/tests/test_frame_api.py
git commit -m "test: add frame API tests"
```

---

## Phase 2: 前端组件

### Task 5: 添加 Frame API 客户端

**Files:**
- Modify: `web/src/api/episodes.ts`

**Step 1: 添加 frame 获取函数**

在 `episodes.ts` 末尾添加：

```typescript
// ── Frame Extraction ──────────────────────────────────────────────────────

export interface FrameOptions {
  topic: string;
  timestamp: number; // nanoseconds
}

export interface FrameResult {
  blobUrl: string;
  timestampNs: number;
}

export async function getFrame(
  episodeId: string,
  options: FrameOptions
): Promise<FrameResult> {
  const params = new URLSearchParams({
    topic: options.topic,
    timestamp: String(options.timestamp),
  });

  const response = await apiClient.get<ArrayBuffer>(
    `/episodes/${episodeId}/frame?${params}`,
    { responseType: "arraybuffer" }
  );

  const timestampNs = parseInt(
    response.headers["x-frame-timestamp"] || String(options.timestamp),
    10
  );

  const blob = new Blob([response.data], { type: "image/jpeg" });
  const blobUrl = URL.createObjectURL(blob);

  return { blobUrl, timestampNs };
}
```

**Step 2: Commit**

```bash
git add web/src/api/episodes.ts
git commit -m "feat: add frame extraction API client"
```

---

### Task 6: 创建 useMcapFrames Hook

**Files:**
- Create: `web/src/hooks/useMcapFrames.ts`

**Step 1: 实现 Hook**

```typescript
"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { getFrame, type FrameResult } from "@/api/episodes";

interface UseMcapFramesOptions {
  episodeId: string;
  topics: string[];
}

interface FrameCache {
  [key: string]: string; // topic_timestamp -> blobUrl
}

const CACHE_KEY = (topic: string, timestamp: number): string =>
  `${topic}_${Math.floor(timestamp / 100_000_000)}`; // 100ms buckets

export function useMcapFrames({ episodeId, topics }: UseMcapFramesOptions) {
  const [frames, setFrames] = useState<Map<string, string>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const cacheRef = useRef<FrameCache>({});
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(cacheRef.current).forEach((url) => {
        URL.revokeObjectURL(url);
      });
    };
  }, []);

  const loadFrames = useCallback(
    async (timestamp: number) => {
      if (topics.length === 0) return;

      // Cancel pending requests
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      setIsLoading(true);

      try {
        const newFrames = new Map<string, string>();
        const requests = topics.map(async (topic) => {
          const cacheKey = CACHE_KEY(topic, timestamp);

          // Check cache first
          if (cacheRef.current[cacheKey]) {
            newFrames.set(topic, cacheRef.current[cacheKey]);
            return;
          }

          try {
            const result = await getFrame(episodeId, { topic, timestamp });
            newFrames.set(topic, result.blobUrl);
            cacheRef.current[cacheKey] = result.blobUrl;
          } catch (error) {
            console.error(`Failed to load frame for ${topic}:`, error);
            // Leave empty for failed topics
          }
        });

        await Promise.all(requests);
        setFrames(newFrames);
      } finally {
        setIsLoading(false);
      }
    },
    [episodeId, topics]
  );

  const preloadFrames = useCallback(
    async (timestamp: number) => {
      if (topics.length === 0) return;

      topics.forEach(async (topic) => {
        const cacheKey = CACHE_KEY(topic, timestamp);
        if (cacheRef.current[cacheKey]) return;

        try {
          const result = await getFrame(episodeId, { topic, timestamp });
          cacheRef.current[cacheKey] = result.blobUrl;
        } catch {
          // Ignore preload errors
        }
      });
    },
    [episodeId, topics]
  );

  return {
    frames,
    isLoading,
    loadFrames,
    preloadFrames,
  };
}
```

**Step 2: Commit**

```bash
git add web/src/hooks/useMcapFrames.ts
git commit -m "feat: add useMcapFrames hook for frame management"
```

---

### Task 7: 创建 Timeline 组件

**Files:**
- Create: `web/src/components/TimelineControl.tsx`

**Step 1: 实现 Timeline 组件**

```typescript
"use client";

import { useCallback, useState } from "react";

interface TimelineControlProps {
  currentTime: number; // nanoseconds
  duration: number; // seconds
  isPlaying: boolean;
  playbackRate: number;
  onSeek: (timeNs: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onRateChange: (rate: number) => void;
}

const PLAYBACK_RATES = [0.5, 1, 2];

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${mins.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}.${ms.toString().padStart(3, "0")}`;
}

export function TimelineControl({
  currentTime,
  duration,
  isPlaying,
  playbackRate,
  onSeek,
  onPlay,
  onPause,
  onRateChange,
}: TimelineControlProps) {
  const [isDragging, setIsDragging] = useState(false);

  const currentSeconds = currentTime / 1_000_000_000;
  const progress = duration > 0 ? (currentSeconds / duration) * 100 : 0;

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newProgress = parseFloat(e.target.value);
      const newTime = (newProgress / 100) * duration * 1_000_000_000;
      onSeek(newTime);
    },
    [duration, onSeek]
  );

  const handleSkip = useCallback(
    (seconds: number) => {
      const newTime = currentTime + seconds * 1_000_000_000;
      onSeek(Math.max(0, Math.min(newTime, duration * 1_000_000_000)));
    },
    [currentTime, duration, onSeek]
  );

  return (
    <div className="bg-gray-900 text-white p-4 rounded-lg">
      {/* Time display */}
      <div className="flex justify-between text-sm font-mono mb-2">
        <span>{formatTime(currentSeconds)}</span>
        <span>{formatTime(duration)}</span>
      </div>

      {/* Progress bar */}
      <div className="relative mb-4">
        <input
          type="range"
          min="0"
          max="100"
          step="0.1"
          value={progress}
          onChange={handleSliderChange}
          onMouseDown={() => setIsDragging(true)}
          onMouseUp={() => setIsDragging(false)}
          onTouchStart={() => setIsDragging(true)}
          onTouchEnd={() => setIsDragging(false)}
          className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
        />
        {isDragging && (
          <div
            className="absolute top-6 bg-gray-800 text-xs px-2 py-1 rounded transform -translate-x-1/2"
            style={{ left: `${progress}%` }}
          >
            {formatTime(currentSeconds)}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSkip(-5)}
            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            title="Back 5s"
          >
            ← 5s
          </button>

          <button
            onClick={isPlaying ? onPause : onPlay}
            className="px-4 py-1 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium"
          >
            {isPlaying ? "⏸ Pause" : "▶ Play"}
          </button>

          <button
            onClick={() => handleSkip(5)}
            className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm"
            title="Forward 5s"
          >
            5s →
          </button>
        </div>

        {/* Playback rate */}
        <div className="flex items-center gap-1">
          {PLAYBACK_RATES.map((rate) => (
            <button
              key={rate}
              onClick={() => onRateChange(rate)}
              className={`px-2 py-1 text-xs rounded ${
                playbackRate === rate
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 hover:bg-gray-600"
              }`}
            >
              {rate}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add web/src/components/TimelineControl.tsx
git commit -m "feat: add TimelineControl component"
```

---

### Task 8: 创建 VideoGrid 组件

**Files:**
- Create: `web/src/components/VideoGrid.tsx`

**Step 1: 实现 VideoGrid 组件**

```typescript
"use client";

import { useMemo } from "react";

interface VideoTileProps {
  topic: string;
  frameUrl: string | undefined;
  isLoading: boolean;
}

function VideoTile({ topic, frameUrl, isLoading }: VideoTileProps) {
  return (
    <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
      {frameUrl ? (
        <img
          src={frameUrl}
          alt={topic}
          className="w-full h-full object-contain"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-gray-500">
          {isLoading ? (
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
          ) : (
            <span className="text-sm">No frame</span>
          )}
        </div>
      )}

      {/* Topic overlay */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
        <span className="text-xs text-white font-mono truncate block">
          {topic}
        </span>
      </div>
    </div>
  );
}

interface VideoGridProps {
  topics: string[];
  frames: Map<string, string>;
  isLoading: boolean;
}

export function VideoGrid({ topics, frames, isLoading }: VideoGridProps) {
  const gridCols = useMemo(() => {
    const count = topics.length;
    if (count <= 1) return 1;
    if (count <= 2) return 2;
    if (count <= 4) return 2;
    if (count <= 6) return 3;
    if (count <= 9) return 3;
    return 4;
  }, [topics.length]);

  if (topics.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-gray-100 rounded-lg">
        <p className="text-gray-500">No image topics found in this episode</p>
      </div>
    );
  }

  return (
    <div
      className="grid gap-4"
      style={{
        gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`,
      }}
    >
      {topics.map((topic) => (
        <VideoTile
          key={topic}
          topic={topic}
          frameUrl={frames.get(topic)}
          isLoading={isLoading}
        />
      ))}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add web/src/components/VideoGrid.tsx
git commit -m "feat: add VideoGrid component for multi-channel display"
```

---

### Task 9: 创建预览页面

**Files:**
- Create: `web/src/pages/PreviewPage.tsx`

**Step 1: 实现 PreviewPage**

```typescript
"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEpisode } from "@/api/episodes";
import { useMcapFrames } from "@/hooks/useMcapFrames";
import { VideoGrid } from "@/components/VideoGrid";
import { TimelineControl } from "@/components/TimelineControl";
import { Spinner } from "@/components/Spinner";

// Filter image topics from episode
function getImageTopics(episode: ReturnType<typeof useEpisode>["data"]): string[] {
  if (!episode?.topics) return [];

  return episode.topics
    .filter(
      (t) =>
        t.type === "image" ||
        t.schema_name?.includes("Image") ||
        t.name.includes("camera") ||
        t.name.includes("image")
    )
    .map((t) => t.name);
}

export function PreviewPage() {
  const { episodeId } = useParams<{ episodeId: string }>();
  const navigate = useNavigate();
  const { data: episode, isLoading: isLoadingEpisode } = useEpisode(episodeId!);

  const imageTopics = getImageTopics(episode);
  const duration = episode?.duration_seconds ?? 0;

  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);

  const { frames, isLoading: isLoadingFrames, loadFrames, preloadFrames } = useMcapFrames({
    episodeId: episodeId!,
    topics: imageTopics,
  });

  const animationRef = useRef<number>();
  const lastFrameTimeRef = useRef<number>(0);

  // Initial load - get first frame
  useEffect(() => {
    if (imageTopics.length > 0 && episode?.duration_seconds) {
      loadFrames(0);
    }
  }, [imageTopics, episode?.duration_seconds, loadFrames]);

  // Handle play/pause animation
  useEffect(() => {
    if (!isPlaying) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      return;
    }

    const animate = (timestamp: number) => {
      if (lastFrameTimeRef.current === 0) {
        lastFrameTimeRef.current = timestamp;
      }

      const deltaTime = (timestamp - lastFrameTimeRef.current) / 1000; // seconds
      lastFrameTimeRef.current = timestamp;

      setCurrentTime((prev) => {
        const newTime = prev + deltaTime * playbackRate * 1_000_000_000;
        const maxTime = duration * 1_000_000_000;

        if (newTime >= maxTime) {
          setIsPlaying(false);
          return maxTime;
        }

        return newTime;
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    lastFrameTimeRef.current = 0;
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, playbackRate, duration]);

  // Load frames when currentTime changes (in pause mode or when playing)
  useEffect(() => {
    if (!isPlaying || currentTime % 10 === 0) {
      // Throttle frame loading during playback
      loadFrames(currentTime);
    }
  }, [currentTime, isPlaying, loadFrames]);

  const handleSeek = useCallback(
    (timeNs: number) => {
      setCurrentTime(timeNs);
      setIsPlaying(false);
      loadFrames(timeNs);
    },
    [loadFrames]
  );

  const handlePlay = useCallback(() => {
    setIsPlaying(true);
  }, []);

  const handlePause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  if (isLoadingEpisode) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <p className="text-red-500 mb-4">Episode not found</p>
          <button
            onClick={() => navigate("/episodes")}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Back to Episodes
          </button>
        </div>
      </div>
    );
  }

  if (episode.format !== "mcap") {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <p className="text-gray-600 mb-4">
            Preview is only available for MCAP files
          </p>
          <button
            onClick={() => navigate("/episodes")}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Back to Episodes
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/episodes")}
              className="text-gray-600 hover:text-gray-900"
            >
              ← Back
            </button>
            <h1 className="text-xl font-semibold text-gray-900">
              {episode.filename}
            </h1>
          </div>
          <div className="text-sm text-gray-500">
            Duration: {Math.floor(duration / 60)}m {Math.floor(duration % 60)}s
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="p-6 max-w-7xl mx-auto">
        {/* Video grid */}
        <div className="mb-6">
          <VideoGrid
            topics={imageTopics}
            frames={frames}
            isLoading={isLoadingFrames}
          />
        </div>

        {/* Timeline */}
        <TimelineControl
          currentTime={currentTime}
          duration={duration}
          isPlaying={isPlaying}
          playbackRate={playbackRate}
          onSeek={handleSeek}
          onPlay={handlePlay}
          onPause={handlePause}
          onRateChange={setPlaybackRate}
        />
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add web/src/pages/PreviewPage.tsx
git commit -m "feat: add MCAP preview page"
```

---

### Task 10: 添加路由和导航

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/EpisodeCard.tsx`

**Step 1: 添加路由**

在 `App.tsx` 中添加：

```typescript
import { PreviewPage } from "@/pages/PreviewPage";

// In Routes, add:
<Route path="preview/:episodeId" element={<PreviewPage />} />
```

**Step 2: 添加预览按钮到 EpisodeCard**

在 `EpisodeCard.tsx` 的 actions 区域添加预览按钮：

```typescript
// Add prop
interface EpisodeCardProps {
  // ... existing props
  onPreview?: (episodeId: string) => void;
}

// In component destructuring
export function EpisodeCard({ episode, onCreateTask, onDelete, onDetail, onPreview }: EpisodeCardProps) {

// In action buttons section, add:
{episode.status === "ready" && onPreview && (
  <button
    onClick={(e) => {
      e.stopPropagation();
      onPreview(episode.id);
    }}
    className="flex-1 px-3 py-1.5 bg-green-600 text-white text-xs rounded hover:bg-green-700 transition-colors"
  >
    预览
  </button>
)}
```

**Step 3: 更新 EpisodesPage 传递 onPreview**

在 `EpisodesPage.tsx` 中添加导航处理：

```typescript
import { useNavigate } from "react-router-dom";

// In component
const navigate = useNavigate();

const handlePreview = (episodeId: string) => {
  navigate(`/preview/${episodeId}`);
};

// Pass to EpisodeCard
<EpisodeCard
  key={ep.id}
  episode={ep}
  onCreateTask={handleCreateTask}
  onDelete={handleDelete}
  onDetail={setDetailId}
  onPreview={handlePreview}
/>
```

**Step 4: Commit**

```bash
git add web/src/App.tsx web/src/components/EpisodeCard.tsx web/src/pages/EpisodesPage.tsx
git commit -m "feat: add preview navigation and button"
```

---

## Phase 3: 测试与验证

### Task 11: 启动服务并测试

**Step 1: 启动完整服务栈**

```bash
make e2e-up
```

**Step 2: 上传测试 MCAP 文件**

1. 访问 http://localhost:3000
2. 登录 admin@embedai.local / Admin@2026!
3. 上传包含图像 topic 的 MCAP 文件
4. 等待处理完成（状态变为 ready）

**Step 3: 测试预览功能**

1. 在 Episodes 页面点击"预览"按钮
2. 验证视频网格显示
3. 测试时间轴拖动
4. 测试播放/暂停

**Step 4: 检查日志**

```bash
docker compose -f infra/docker-compose.prod.yml logs -f dataset-service
```

Expected: 看到 frame extraction 日志

---

### Task 12: 添加 E2E 测试

**Files:**
- Create: `tests/e2e/test_preview.py`

**Step 1: 编写 E2E 测试**

```python
"""E2E tests for MCAP preview functionality."""
import pytest


@pytest.mark.asyncio
async def test_preview_page_loads(client, ready_mcap_episode):
    """Test preview page loads for MCAP episode."""
    episode_id = ready_mcap_episode["id"]

    # Get episode details
    response = await client.get(f"/episodes/{episode_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["format"] == "mcap"
    assert len(data["topics"]) > 0


@pytest.mark.asyncio
async def test_frame_extraction(client, ready_mcap_episode):
    """Test frame extraction API."""
    episode_id = ready_mcap_episode["id"]

    # Get episode to find image topics
    response = await client.get(f"/episodes/{episode_id}")
    data = response.json()

    image_topics = [t for t in data["topics"] if "image" in t.get("type", "")]
    if not image_topics:
        pytest.skip("No image topics in test file")

    topic = image_topics[0]["name"]

    # Request frame at start
    response = await client.get(
        f"/episodes/{episode_id}/frame",
        params={"topic": topic, "timestamp": 0},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_frame_extraction_invalid_topic(client, ready_mcap_episode):
    """Test frame extraction with invalid topic."""
    episode_id = ready_mcap_episode["id"]

    response = await client.get(
        f"/episodes/{episode_id}/frame",
        params={"topic": "/nonexistent/topic", "timestamp": 0},
    )

    assert response.status_code == 404
```

**Step 2: 运行 E2E 测试**

```bash
cd tests && uv run pytest e2e/test_preview.py -v
```

Expected: 测试通过

**Step 3: Commit**

```bash
git add tests/e2e/test_preview.py
git commit -m "test: add E2E tests for MCAP preview"
```

---

## 完成总结

### 已实现功能

1. **后端 Frame API** (`GET /episodes/{id}/frame`)
   - 支持从 MCAP 提取指定时间戳的图像帧
   - 支持 sensor_msgs/Image 和 CompressedImage
   - 输出 JPEG 格式

2. **前端预览页面** (`/preview/{episodeId}`)
   - 自适应视频网格布局
   - 时间轴拖动和播放控制
   - 多倍速播放 (0.5x, 1x, 2x)
   - 帧缓存和预加载

3. **组件**
   - `useMcapFrames` - 帧数据管理 Hook
   - `VideoGrid` - 自适应视频网格
   - `TimelineControl` - 时间轴和播放控制

### 验证清单

- [ ] Frame API 返回正确的 JPEG 图像
- [ ] 预览页面正确显示多路视频
- [ ] 时间轴拖动更新所有视频
- [ ] 播放/暂停控制正常工作
- [ ] 非 MCAP 文件显示友好提示
- [ ] E2E 测试通过

### 后续优化建议

1. **性能优化**
   - 后端添加 MCAP 文件元数据缓存（避免重复解析）
   - 前端添加 Web Worker 处理帧解码

2. **功能扩展**
   - 支持点云可视化
   - 添加传感器数据叠加显示
   - 关键帧书签功能
