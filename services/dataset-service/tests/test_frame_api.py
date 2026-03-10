"""Tests for Frame extraction API endpoint."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_PROJECT_ID, make_episode


class TestGetFrameEndpoint:
    """Test GET /episodes/{id}/frame endpoint."""

    def test_get_frame_success(self, client, auth_headers, mock_db, tmp_path):
        """成功获取帧"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_frame = MagicMock()
            mock_frame.data = b"jpeg_data"
            mock_frame.timestamp_ns = 1000000000
            mock_frame.format = "jpeg"

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = (1000000000, 2000000000)
            mock_extractor.return_value.extract_frame.return_value = mock_frame

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera/image&timestamp=1000000000",
                headers=auth_headers
            )

            assert resp.status_code == 200
            assert resp.content == b"jpeg_data"
            assert resp.headers["content-type"] == "image/jpeg"
            assert resp.headers["x-frame-timestamp"] == "1000000000"
            assert "cache-control" in resp.headers

    def test_get_frame_episode_not_found(self, client, auth_headers, mock_db):
        """Episode 不存在返回 404"""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 404

    def test_get_frame_wrong_format(self, client, auth_headers, mock_db):
        """非 MCAP 格式返回 400"""
        ep = make_episode(fmt="hdf5")

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "only mcap format supported" in resp.json()["detail"].lower()

    def test_get_frame_no_storage_path(self, client, auth_headers, mock_db):
        """无 storage_path 返回 400"""
        ep = make_episode(fmt="mcap")
        ep.storage_path = None

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "file not available" in resp.json()["detail"].lower()

    def test_get_frame_not_ready(self, client, auth_headers, mock_db):
        """Episode 状态非 ready 仍可获取帧"""
        ep = make_episode(fmt="mcap", status="processing")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )
            # Currently implementation allows non-ready status
            assert resp.status_code == 200

    def test_get_frame_no_frame_found(self, client, auth_headers, mock_db):
        """未找到帧返回 404"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = None

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=9999999999",
                headers=auth_headers
            )

            assert resp.status_code == 404
            assert "no frame found" in resp.json()["detail"].lower()

    def test_get_frame_missing_topic_param(self, client, auth_headers):
        """缺少 topic 参数返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_missing_timestamp_param(self, client, auth_headers):
        """缺少 timestamp 参数返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_invalid_timestamp(self, client, auth_headers):
        """无效 timestamp 返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=abc",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_unauthorized(self, client):
        """未认证返回 401/403"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=0"
        )
        assert resp.status_code in (401, 403)

    def test_get_frame_wrong_project(self, client, auth_headers, mock_db):
        """其他项目的 Episode 返回 404"""
        ep = make_episode(project_id=str(uuid.uuid4()))

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 404

    def test_get_frame_download_failure(self, client, auth_headers, mock_db):
        """下载失败时返回 500"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient"):

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(side_effect=Exception("Download failed"))
            mock_get_cache.return_value = mock_cache

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 500

    def test_get_frame_extractor_exception(self, client, auth_headers, mock_db):
        """提取器异常时返回 500"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.side_effect = Exception("Extraction failed")

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 500

    def test_get_frame_with_special_characters_in_topic(self, client, auth_headers, mock_db):
        """处理包含特殊字符的 topic 名称"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            # Test topic with URL-encoded special characters
            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=%2Fcamera%2Fimage_raw%2Fcompressed&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 200

    def test_get_frame_large_timestamp(self, client, auth_headers, mock_db):
        """处理大时间戳值"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=9999999999999, format="jpeg"
            )

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=9999999999999",
                headers=auth_headers
            )

            assert resp.status_code == 200

    def test_get_frame_negative_timestamp(self, client, auth_headers, mock_db):
        """处理负时间戳"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=-1000",
                headers=auth_headers
            )

            assert resp.status_code == 200

    def test_get_frame_uses_cache(self, client, auth_headers, mock_db):
        """Frame endpoint 使用 McapFileCache 而非直接下载"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient") as mock_storage_cls, \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            assert resp.status_code == 200
            mock_cache.get_or_download.assert_called_once_with(
                str(ep.id), ep.storage_path, mock_storage_cls.return_value
            )

    def test_get_frame_does_not_delete_cached_file(self, client, auth_headers, mock_db):
        """Endpoint 不调用 os.unlink — 缓存管理文件生命周期"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.routers.episodes.get_mcap_cache") as mock_get_cache, \
             patch("app.routers.episodes.StorageClient"), \
             patch("app.routers.episodes.McapFrameExtractor") as mock_extractor, \
             patch("os.unlink") as mock_unlink:

            mock_cache = AsyncMock()
            mock_cache.get_or_download = AsyncMock(return_value="/tmp/cached_ep.mcap")
            mock_get_cache.return_value = mock_cache

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.get_time_range.return_value = None
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b"jpeg", timestamp_ns=0, format="jpeg"
            )

            client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            mock_unlink.assert_not_called()
