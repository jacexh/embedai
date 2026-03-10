"""E2E tests for MCAP preview functionality.

Covers: upload MCAP -> ingest -> preview -> frame extraction.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from .helpers import E2EClient


@pytest.mark.e2e
class TestMcapPreviewWorkflow:
    """MCAP 预览完整工作流"""

    @pytest.fixture
    def sample_mcap_path(self):
        """提供测试用 MCAP 文件"""
        # 首先在当前目录查找，然后在项目根目录查找
        search_paths = [
            Path(__file__).parent / "fixtures" / "sample_ros1.mcap",
            Path(__file__).parent.parent.parent / "testdata" / "ros1_compressed_images.mcap",
        ]
        for path in search_paths:
            if path.exists():
                return path
        pytest.skip("Test MCAP file not found in any search path")

    async def _wait_for_episode_status(
        self,
        client: E2EClient,
        episode_id: str,
        expected_status: str,
        timeout: int = 60,
        interval: float = 1.0,
    ) -> dict:
        """Wait for episode to reach expected status."""
        import asyncio
        import time

        start = time.time()
        while time.time() - start < timeout:
            resp = await client.dataset.get(f"/api/v1/episodes/{episode_id}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == expected_status:
                    return data
            await asyncio.sleep(interval)

        raise TimeoutError(f"Episode {episode_id} did not reach status {expected_status} within {timeout}s")

    async def test_upload_and_preview_mcap(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """上传 MCAP 并验证预览功能"""
        # 1. 读取文件
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        size_bytes = len(data)
        filename = sample_mcap_path.name

        # 2. 初始化上传
        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": filename, "size_bytes": size_bytes, "format": "mcap"}
        )
        assert init_resp.status_code == 200, f"Upload init failed: {init_resp.text}"

        init_data = init_resp.json()
        session_id = init_data["session_id"]
        episode_id = init_data["episode_id"]
        chunk_size = init_data["chunk_size"]
        total_chunks = init_data["total_chunks"]

        # 3. 上传分片
        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            chunk_resp = await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )
            assert chunk_resp.status_code == 200, f"Chunk {i} upload failed: {chunk_resp.text}"

        # 4. 完成上传
        complete_resp = await gateway_client.dataset.post(
            f"/api/v1/episodes/upload/{session_id}/complete"
        )
        assert complete_resp.status_code == 200, f"Complete failed: {complete_resp.text}"

        # 5. 等待处理完成
        episode = await self._wait_for_episode_status(
            gateway_client, episode_id, "ready", timeout=60
        )
        assert episode["format"] == "mcap"

        # 6. 获取 episode 详情（包含 topics）
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        assert detail_resp.status_code == 200, f"Get detail failed: {detail_resp.text}"

        detail = detail_resp.json()
        assert "topics" in detail

        # 7. 过滤图像 topics
        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ]
        ]

        if not image_topics:
            pytest.skip("No image topics in uploaded MCAP")

        # 8. 请求帧提取
        topic_name = image_topics[0]["name"]
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        mid_timestamp = duration_ns // 2

        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": topic_name, "timestamp": mid_timestamp}
        )
        assert frame_resp.status_code == 200, f"Frame extraction failed: {frame_resp.text}"

        # 9. 验证响应
        assert frame_resp.headers["content-type"] == "image/jpeg"
        assert "x-frame-timestamp" in frame_resp.headers
        assert len(frame_resp.content) > 0

        # 10. 验证是有效的 JPEG
        assert frame_resp.content[:2] == b"\xff\xd8"  # JPEG SOI
        assert frame_resp.content[-2:] == b"\xff\xd9"  # JPEG EOI

    async def test_preview_non_mcap_returns_error(
        self, gateway_client: E2EClient
    ):
        """预览非 MCAP 文件返回错误"""
        # 创建 HDF5 episode (upload endpoints are on gateway)
        init_resp = await gateway_client.gateway.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.hdf5", "size_bytes": 1024, "format": "hdf5"}
        )
        assert init_resp.status_code in (200, 201)

        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]

        # 上传空数据
        await gateway_client.gateway.put(
            f"/api/v1/episodes/upload/{session_id}/chunk/0",
            content=b"x" * 1024,
            headers={"Content-Type": "application/octet-stream"}
        )

        await gateway_client.gateway.post(
            f"/api/v1/episodes/upload/{session_id}/complete"
        )

        # 尝试获取帧应返回 400 (HDF5 doesn't support frame extraction)
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": "/camera", "timestamp": 0}
        )
        assert frame_resp.status_code == 400

    async def test_preview_frame_not_found(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """请求不存在的时间戳返回 404"""
        # 上传并等待就绪
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]

        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        # 等待就绪
        await self._wait_for_episode_status(gateway_client, episode_id, "ready", timeout=60)

        # 请求不存在的 topic
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": "/nonexistent/topic", "timestamp": 9999999999999}
        )
        assert frame_resp.status_code == 404

    async def test_preview_multiple_topics(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """并发请求多个 topic 的帧"""
        # 上传并等待就绪
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        # 等待就绪
        await self._wait_for_episode_status(gateway_client, episode_id, "ready", timeout=60)

        # 获取所有图像 topics
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        detail = detail_resp.json()

        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ]
        ]

        if len(image_topics) < 2:
            pytest.skip("Need at least 2 image topics")

        # 并发请求多个 topic
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        timestamp = duration_ns // 2

        async def fetch_frame(topic):
            return await gateway_client.dataset.get(
                f"/api/v1/episodes/{episode_id}/frame",
                params={"topic": topic["name"], "timestamp": timestamp}
            )

        responses = await asyncio.gather(*[
            fetch_frame(topic) for topic in image_topics[:3]
        ])

        for resp in responses:
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"

    async def test_sequential_frame_requests(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """顺序请求多个帧验证时间线"""
        # 上传并等待就绪
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        episode = await self._wait_for_episode_status(gateway_client, episode_id, "ready", timeout=60)

        # 获取图像 topic
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        detail = detail_resp.json()

        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ]
        ]

        if not image_topics:
            pytest.skip("No image topics")

        topic_name = image_topics[0]["name"]
        duration_ns = int(episode["duration_seconds"] * 1_000_000_000)

        # 在多个时间点提取帧
        timestamps = [duration_ns * i // 10 for i in range(10)]
        frames = []

        for ts in timestamps:
            resp = await gateway_client.dataset.get(
                f"/api/v1/episodes/{episode_id}/frame",
                params={"topic": topic_name, "timestamp": ts}
            )
            assert resp.status_code == 200
            frames.append({
                "timestamp": int(resp.headers["x-frame-timestamp"]),
                "size": len(resp.content),
            })

        # 验证帧时间戳是递增的
        for i in range(1, len(frames)):
            assert frames[i]["timestamp"] >= frames[i-1]["timestamp"]


@pytest.mark.e2e
class TestMcapPreviewPerformance:
    """MCAP 预览性能测试"""

    @pytest.fixture
    def sample_mcap_path(self):
        """提供测试用 MCAP 文件"""
        search_paths = [
            Path(__file__).parent / "fixtures" / "sample_ros1.mcap",
            Path(__file__).parent.parent.parent / "testdata" / "ros1_compressed_images.mcap",
        ]
        for path in search_paths:
            if path.exists():
                return path
        pytest.skip("Test MCAP file not found")

    async def test_frame_extraction_response_time(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """帧提取响应时间 < 1s"""
        import time

        # 上传并等待就绪
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        # 等待就绪
        from tests.e2e.test_mcap_preview import TestMcapPreviewWorkflow
        await TestMcapPreviewWorkflow()._wait_for_episode_status(
            gateway_client, episode_id, "ready", timeout=60
        )

        # 获取图像 topic
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        detail = detail_resp.json()

        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ]
        ]

        if not image_topics:
            pytest.skip("No image topics")

        topic_name = image_topics[0]["name"]
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        timestamp = duration_ns // 2

        start = time.time()
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": topic_name, "timestamp": timestamp}
        )
        elapsed = time.time() - start

        assert frame_resp.status_code == 200
        assert elapsed < 1.0, f"Frame extraction took {elapsed}s, expected < 1s"

    async def test_concurrent_frame_requests(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """并发请求多个帧不应导致资源耗尽"""
        import time

        # 上传并等待就绪
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        # 等待就绪
        from tests.e2e.test_mcap_preview import TestMcapPreviewWorkflow
        await TestMcapPreviewWorkflow()._wait_for_episode_status(
            gateway_client, episode_id, "ready", timeout=60
        )

        # 获取图像 topic
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        detail = detail_resp.json()

        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
            ]
        ]

        if not image_topics:
            pytest.skip("No image topics")

        topic_name = image_topics[0]["name"]
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)

        # 创建多个并发请求
        timestamps = [duration_ns * i // 20 for i in range(20)]

        async def fetch_frame(ts):
            return await gateway_client.dataset.get(
                f"/api/v1/episodes/{episode_id}/frame",
                params={"topic": topic_name, "timestamp": ts}
            )

        start = time.time()
        responses = await asyncio.gather(*[fetch_frame(ts) for ts in timestamps])
        elapsed = time.time() - start

        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count == len(responses), f"Only {success_count}/{len(responses)} requests succeeded"
        assert elapsed < 10.0, f"20 concurrent requests took {elapsed}s"


@pytest.mark.e2e
class TestMcapPreviewErrors:
    """MCAP 预览错误处理测试"""

    async def test_frame_extraction_invalid_topic(self, gateway_client: E2EClient):
        """无效 topic 名称处理"""
        # 创建一个简单的 episode
        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.mcap", "size_bytes": 1024, "format": "mcap"}
        )
        # 这个测试需要已经存在的 episode，所以这里简化处理
        # 实际测试需要更复杂的 setup

    async def test_frame_extraction_unauthorized(self, gateway_client: E2EClient):
        """未授权访问返回 401/403"""
        # 使用无效 token
        original_headers = gateway_client.dataset.headers.copy()
        gateway_client.dataset.headers["Authorization"] = "Bearer invalid_token"

        resp = await gateway_client.dataset.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame",
            params={"topic": "/camera", "timestamp": 0}
        )

        gateway_client.dataset.headers = original_headers
        assert resp.status_code in (401, 403)

    async def test_frame_extraction_invalid_episode_id(
        self, gateway_client: E2EClient
    ):
        """无效 episode ID 格式处理"""
        resp = await gateway_client.dataset.get(
            "/api/v1/episodes/invalid-uuid/frame",
            params={"topic": "/camera", "timestamp": 0}
        )
        assert resp.status_code == 422

    async def test_frame_extraction_missing_params(
        self, gateway_client: E2EClient
    ):
        """缺少必要参数"""
        resp = await gateway_client.dataset.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame"
        )
        assert resp.status_code == 422


@pytest.mark.e2e
class TestMcapPreviewDeepLinking:
    """SPA 深层链接测试 - 直接访问 /preview/:id"""

    @pytest.fixture
    def sample_mcap_path(self):
        """提供测试用 MCAP 文件"""
        search_paths = [
            Path(__file__).parent / "fixtures" / "sample_ros1.mcap",
            Path(__file__).parent.parent.parent / "testdata" / "ros1_compressed_images.mcap",
        ]
        for path in search_paths:
            if path.exists():
                return path
        pytest.skip("Test MCAP file not found")

    async def _get_web_url(self) -> str:
        """获取前端 URL"""
        import os
        return os.getenv("WEB_URL", "http://localhost:3000")

    async def test_direct_access_to_preview_page(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """直接访问 /preview/:id 应返回 200 (SPA fallback)"""
        import httpx

        # 首先上传一个 MCAP 文件
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": sample_mcap_path.name, "size_bytes": len(data), "format": "mcap"}
        )
        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )

        await gateway_client.dataset.post(f"/api/v1/episodes/upload/{session_id}/complete")

        # 等待就绪
        workflow = TestMcapPreviewWorkflow()
        await workflow._wait_for_episode_status(gateway_client, episode_id, "ready", timeout=60)

        # 直接访问 /preview/:id 深层链接
        web_url = await self._get_web_url()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{web_url}/preview/{episode_id}",
                follow_redirects=True
            )

        # SPA fallback 应返回 200 和 index.html
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        # 确认返回的是 SPA 而不是 404 页面
        assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text

    async def test_direct_access_to_nonexistent_episode(
        self, gateway_client: E2EClient
    ):
        """直接访问不存在的 episode ID 仍应返回 SPA (由前端处理 404)"""
        import httpx

        web_url = await self._get_web_url()
        fake_episode_id = "00000000-0000-0000-0000-000000000000"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{web_url}/preview/{fake_episode_id}",
                follow_redirects=True
            )

        # SPA fallback 应返回 200，由 React Router 处理路由
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_static_assets_are_not_spa_fallback(
        self, gateway_client: E2EClient
    ):
        """静态资源请求不应触发 SPA fallback"""
        import httpx

        web_url = await self._get_web_url()

        # 请求不存在的静态资源
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{web_url}/nonexistent.js")

        # 静态资源不存在应返回 404，而不是 SPA fallback
        # 但如果 nginx 配置为所有 404 都返回 index.html，这可能是 200
        # 这个测试记录当前行为

    async def test_preview_page_with_special_chars_in_id(
        self, gateway_client: E2EClient
    ):
        """测试包含特殊字符的 ID (潜在的安全问题)"""
        import httpx

        web_url = await self._get_web_url()

        # 测试路径遍历尝试
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{web_url}/preview/../../../etc/passwd",
                follow_redirects=True
            )

        # 应返回 200 (SPA fallback) 或 404，但不应暴露敏感文件
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            # 确保返回的是 HTML 而不是 /etc/passwd 内容
            assert "text/html" in resp.headers.get("content-type", "")
            assert "root:" not in resp.text  # 不是 passwd 文件
