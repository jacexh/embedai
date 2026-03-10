"""Tests for Frame extractor service with mocked MCAP dependencies."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.frame_extractor import FrameResult, McapFrameExtractor


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_jpeg() -> bytes:
    """Minimal valid JPEG bytes for testing."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


@pytest.fixture
def mock_ros1_compressed_image() -> MagicMock:
    """Mock decoded ROS1 CompressedImage message."""
    msg = MagicMock()
    msg.data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    return msg


@pytest.fixture
def mock_ros1_raw_image() -> MagicMock:
    """Mock decoded ROS1 raw Image message."""
    msg = MagicMock()
    msg.height = 480
    msg.width = 640
    msg.encoding = "bgr8"
    msg.data = np.zeros((480, 640, 3), dtype=np.uint8).tobytes()
    return msg


class MockMcapSummary:
    """Mock MCAP summary for testing."""

    def __init__(
        self,
        channels: dict | None = None,
        schemas: dict | None = None,
        statistics: MagicMock | None = None,
    ):
        self.channels = channels or {}
        self.schemas = schemas or {}
        self.statistics = statistics


class MockMcapChannel:
    """Mock MCAP channel for testing."""

    def __init__(
        self,
        id: int = 1,
        topic: str = "/camera/image",
        schema_id: int = 1,
        message_encoding: str = "ros1",
    ):
        self.id = id
        self.topic = topic
        self.schema_id = schema_id
        self.message_encoding = message_encoding


class MockMcapSchema:
    """Mock MCAP schema for testing."""

    def __init__(self, id: int = 1, name: str = "sensor_msgs/msg/Image", encoding: str = "ros1msg"):
        self.id = id
        self.name = name
        self.encoding = encoding


class MockMcapMessage:
    """Mock MCAP message for testing."""

    def __init__(self, log_time: int = 1000000000, data: bytes = b"test_data"):
        self.log_time = log_time
        self.data = data


@pytest.fixture
def mock_mcap_reader():
    """Factory for creating mock MCAP readers."""

    def _create_reader(
        channels: list[dict] | None = None,
        schemas: list[dict] | None = None,
        messages: list[dict] | None = None,
        statistics: dict | None = None,
    ) -> MagicMock:
        reader = MagicMock()

        # Build summary
        channel_map = {}
        schema_map = {}

        if channels:
            for ch in channels:
                channel_map[ch["id"]] = MockMcapChannel(
                    id=ch.get("id", 1),
                    topic=ch.get("topic", "/camera/image"),
                    schema_id=ch.get("schema_id", 1),
                    message_encoding=ch.get("message_encoding", "ros1"),
                )

        if schemas:
            for sch in schemas:
                schema_map[sch["id"]] = MockMcapSchema(
                    id=sch.get("id", 1),
                    name=sch.get("name", "sensor_msgs/msg/Image"),
                    encoding=sch.get("encoding", "ros1msg"),
                )

        stats = None
        if statistics:
            stats = MagicMock()
            stats.message_start_time = statistics.get("message_start_time", 1000000000)
            stats.message_end_time = statistics.get("message_end_time", 2000000000)

        summary = MockMcapSummary(
            channels=channel_map,
            schemas=schema_map,
            statistics=stats,
        )
        reader.get_summary.return_value = summary

        # Build messages iterator
        message_list = []
        if messages:
            for msg in messages:
                schema = schema_map.get(1, MockMcapSchema())
                channel = channel_map.get(1, MockMcapChannel())
                message = MockMcapMessage(
                    log_time=msg.get("log_time", 1000000000),
                    data=msg.get("data", b"test_data"),
                )
                message_list.append((schema, channel, message))

        reader.iter_messages.return_value = iter(message_list)

        return reader

    return _create_reader


# -----------------------------------------------------------------------------
# TestMcapFrameExtractorInit
# -----------------------------------------------------------------------------


class TestMcapFrameExtractorInit:
    """Test initialization logic."""

    def test_init_with_string_path(self):
        """使用字符串路径初始化"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        assert extractor.file_path == Path("/tmp/test.mcap")

    def test_init_with_path_object(self):
        """使用 Path 对象初始化"""
        extractor = McapFrameExtractor(Path("/tmp/test.mcap"))
        assert extractor.file_path == Path("/tmp/test.mcap")

    def test_typestore_initialization(self):
        """验证 ROS1 typestore 正确加载"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        assert extractor._typestore is not None
        assert "sensor_msgs/msg/CompressedImage" in extractor._typestore.types
        assert "sensor_msgs/msg/Image" in extractor._typestore.types


# -----------------------------------------------------------------------------
# TestGetImageTopics
# -----------------------------------------------------------------------------


class TestGetImageTopics:
    """Test image topic identification."""

    def test_get_image_topics_with_ros1_compressed(self, mock_mcap_reader):
        """识别 ROS1 CompressedImage topic"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/compressed",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[
                {
                    "id": 1,
                    "name": "sensor_msgs/msg/CompressedImage",
                    "encoding": "ros1msg",
                }
            ],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]["name"] == "/camera/compressed"
        assert topics[0]["type"] == "compressed_image"
        assert topics[0]["schema_name"] == "sensor_msgs/msg/CompressedImage"

    def test_get_image_topics_with_ros1_raw(self, mock_mcap_reader):
        """识别 ROS1 Image topic"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/raw",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[
                {
                    "id": 1,
                    "name": "sensor_msgs/msg/Image",
                    "encoding": "ros1msg",
                }
            ],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]["type"] == "image"

    def test_get_image_topics_with_ros2_cdr(self, mock_mcap_reader):
        """识别 ROS2 CDR Image topic"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "cdr",
                }
            ],
            schemas=[
                {
                    "id": 1,
                    "name": "sensor_msgs/msg/Image",
                    "encoding": "ros2msg",
                }
            ],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1

    def test_get_image_topics_filters_non_image(self, mock_mcap_reader):
        """过滤非图像 topic"""
        reader = mock_mcap_reader(
            channels=[
                {"id": 1, "topic": "/camera/image", "schema_id": 1},
                {"id": 2, "topic": "/odom", "schema_id": 2},
                {"id": 3, "topic": "/imu", "schema_id": 3},
            ],
            schemas=[
                {"id": 1, "name": "sensor_msgs/msg/Image"},
                {"id": 2, "name": "nav_msgs/msg/Odometry"},
                {"id": 3, "name": "sensor_msgs/msg/Imu"},
            ],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]["name"] == "/camera/image"

    def test_get_image_topics_empty_mcap(self, mock_mcap_reader):
        """空 MCAP 文件返回空列表"""
        reader = mock_mcap_reader(channels=[], schemas=[])

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert topics == []

    def test_get_image_topics_no_summary(self, mock_mcap_reader):
        """无 summary 时返回空列表"""
        reader = mock_mcap_reader()
        reader.get_summary.return_value = None

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert topics == []


# -----------------------------------------------------------------------------
# TestGetTimeRange
# -----------------------------------------------------------------------------


class TestGetTimeRange:
    """Test time range retrieval."""

    def test_get_time_range_success(self, mock_mcap_reader):
        """成功获取时间范围"""
        reader = mock_mcap_reader(
            statistics={
                "message_start_time": 1000000000,
                "message_end_time": 2000000000,
            }
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        time_range = extractor.get_time_range()
        assert time_range == (1000000000, 2000000000)

    def test_get_time_range_no_statistics(self, mock_mcap_reader):
        """无统计信息返回 None"""
        reader = mock_mcap_reader(statistics=None)

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        time_range = extractor.get_time_range()
        assert time_range is None

    def test_get_time_range_no_summary(self, mock_mcap_reader):
        """无 summary 返回 None"""
        reader = mock_mcap_reader()
        reader.get_summary.return_value = None

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        time_range = extractor.get_time_range()
        assert time_range is None


# -----------------------------------------------------------------------------
# TestExtractFrame
# -----------------------------------------------------------------------------


class TestExtractFrame:
    """Test frame extraction core logic."""

    def test_extract_frame_ros1_compressed(self, mock_mcap_reader, sample_jpeg):
        """提取 ROS1 CompressedImage 帧"""
        ros1_bytes = b"ros1_serialized_data"

        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/compressed",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[
                {
                    "id": 1,
                    "name": "sensor_msgs/msg/CompressedImage",
                    "encoding": "ros1msg",
                }
            ],
            messages=[{"log_time": 1500000000, "data": ros1_bytes}],
        )

        mock_decoded = MagicMock()
        mock_decoded.data = sample_jpeg

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_ros1.return_value = mock_decoded

        result = extractor.extract_frame("/camera/compressed", 1500000000)

        assert result is not None
        assert result.data == sample_jpeg
        assert result.timestamp_ns == 1500000000
        extractor._typestore.deserialize_ros1.assert_called_once()

    def test_extract_frame_ros2_cdr(self, mock_mcap_reader):
        """提取 ROS2 CDR Image 帧"""
        cdr_bytes = b"cdr_serialized_data"

        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "cdr",
                }
            ],
            schemas=[
                {
                    "id": 1,
                    "name": "sensor_msgs/msg/Image",
                    "encoding": "ros2msg",
                }
            ],
            messages=[{"log_time": 1000000000, "data": cdr_bytes}],
        )

        mock_decoded = MagicMock()
        mock_decoded.height = 480
        mock_decoded.width = 640
        mock_decoded.encoding = "bgr8"
        mock_decoded.data = np.zeros((480, 640, 3), dtype=np.uint8).tobytes()

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_cdr.return_value = mock_decoded

        with patch("cv2.imencode", return_value=(True, np.array([1, 2, 3]))):
            result = extractor.extract_frame("/camera/image", 1000000000)

        assert result is not None
        extractor._typestore.deserialize_cdr.assert_called_once()

    def test_extract_frame_timestamp_clamping_below_start(self, mock_mcap_reader):
        """时间戳小于 start_time 时自动调整到 start_time"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[{"id": 1, "name": "sensor_msgs/msg/CompressedImage"}],
            messages=[{"log_time": 1000000000, "data": b"data"}],
            statistics={
                "message_start_time": 1000000000,
                "message_end_time": 2000000000,
            },
        )

        mock_decoded = MagicMock()
        mock_decoded.data = b"jpeg_data"

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_ros1.return_value = mock_decoded

        # Request timestamp before start
        result = extractor.extract_frame("/camera/image", 500000000)

        assert result is not None
        # Should have found the frame at start_time
        assert result.timestamp_ns == 1000000000

    def test_extract_frame_timestamp_clamping_above_end(self, mock_mcap_reader):
        """时间戳大于 end_time 时自动调整到 end_time"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[{"id": 1, "name": "sensor_msgs/msg/CompressedImage"}],
            messages=[{"log_time": 2000000000, "data": b"data"}],
            statistics={
                "message_start_time": 1000000000,
                "message_end_time": 2000000000,
            },
        )

        mock_decoded = MagicMock()
        mock_decoded.data = b"jpeg_data"

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_ros1.return_value = mock_decoded

        # Request timestamp after end
        result = extractor.extract_frame("/camera/image", 3000000000)

        assert result is not None
        # Should have found the frame at end_time
        assert result.timestamp_ns == 2000000000

    def test_extract_frame_no_messages(self, mock_mcap_reader):
        """无消息时返回 None"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[{"id": 1, "name": "sensor_msgs/msg/Image"}],
            messages=[],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        result = extractor.extract_frame("/camera/image", 1000000000)
        assert result is None

    def test_extract_frame_unknown_topic(self, mock_mcap_reader):
        """未知 topic 返回 None"""
        reader = mock_mcap_reader(channels=[], schemas=[])

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        result = extractor.extract_frame("/unknown/topic", 1000000000)
        assert result is None

    def test_extract_frame_unknown_encoding(self, mock_mcap_reader):
        """未知 message_encoding 跳过并记录警告"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "protobuf",  # 未知编码
                }
            ],
            schemas=[{"id": 1, "name": "sensor_msgs/msg/Image"}],
            messages=[{"log_time": 1000000000, "data": b"data"}],
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        with patch("app.services.frame_extractor.logger") as mock_logger:
            result = extractor.extract_frame("/camera/image", 1000000000)
            mock_logger.warning.assert_called_with(
                "Unknown message encoding: {}", "protobuf"
            )

    def test_extract_frame_early_exit_on_close_timestamp(self, mock_mcap_reader):
        """找到接近目标时间戳的帧时提前退出"""
        reader = mock_mcap_reader(
            channels=[
                {
                    "id": 1,
                    "topic": "/camera/image",
                    "schema_id": 1,
                    "message_encoding": "ros1",
                }
            ],
            schemas=[{"id": 1, "name": "sensor_msgs/msg/CompressedImage"}],
            messages=[
                {"log_time": 1000000000, "data": b"data1"},
                {"log_time": 1000000100, "data": b"data2"},  # Within 100ms tolerance
                {"log_time": 1000001000, "data": b"data3"},
            ],
        )

        mock_decoded = MagicMock()
        mock_decoded.data = b"jpeg_data"

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_ros1.return_value = mock_decoded

        result = extractor.extract_frame("/camera/image", 1000000000)

        assert result is not None
        assert result.timestamp_ns == 1000000000


# -----------------------------------------------------------------------------
# TestDecodeCompressedImage
# -----------------------------------------------------------------------------


class TestDecodeCompressedImage:
    """Test CompressedImage decoding."""

    def test_decode_bytes_data(self, sample_jpeg):
        """处理 bytes 类型数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = sample_jpeg

        result = extractor._decode_compressed_image(msg)
        assert result == sample_jpeg

    def test_decode_numpy_array(self, sample_jpeg):
        """处理 numpy array 数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = np.frombuffer(sample_jpeg, dtype=np.uint8)

        result = extractor._decode_compressed_image(msg)
        assert result == sample_jpeg

    def test_decode_list_data(self):
        """处理 list 类型数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = [1, 2, 3, 4, 5]

        result = extractor._decode_compressed_image(msg)
        assert result == bytes([1, 2, 3, 4, 5])

    def test_decode_missing_data_attr(self):
        """缺失 data 属性返回 None"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        del msg.data

        result = extractor._decode_compressed_image(msg)
        assert result is None

    def test_decode_exception_handling(self):
        """异常处理返回 None 并记录日志"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = MagicMock()
        msg.data.tobytes.side_effect = Exception("Conversion error")

        with patch("app.services.frame_extractor.logger") as mock_logger:
            result = extractor._decode_compressed_image(msg)
            assert result is None
            mock_logger.warning.assert_called_once()


# -----------------------------------------------------------------------------
# TestDecodeRawImage
# -----------------------------------------------------------------------------


class TestDecodeRawImage:
    """Test raw Image decoding."""

    def test_decode_rgb8(self):
        """解码 rgb8 编码"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "rgb8"
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        with patch("cv2.cvtColor") as mock_cvt, patch(
            "cv2.imencode", return_value=(True, np.array([1, 2, 3]))
        ) as mock_encode:
            result = extractor._decode_raw_image(msg)
            mock_cvt.assert_called_once()
            assert result is not None

    def test_decode_bgr8(self):
        """解码 bgr8 编码（无需颜色空间转换）"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "bgr8"
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        with patch("cv2.cvtColor") as mock_cvt, patch(
            "cv2.imencode", return_value=(True, np.array([1, 2, 3]))
        ):
            result = extractor._decode_raw_image(msg)
            mock_cvt.assert_not_called()
            assert result is not None

    def test_decode_mono8(self):
        """解码 mono8 灰度编码"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "mono8"
        msg.data = np.zeros((2, 2), dtype=np.uint8).tobytes()

        with patch("cv2.imencode", return_value=(True, np.array([1, 2, 3]))):
            result = extractor._decode_raw_image(msg)
            assert result is not None

    def test_decode_unsupported_encoding(self):
        """不支持的编码返回 None 并记录警告"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "16UC1"
        msg.data = b"..."

        with patch("app.services.frame_extractor.logger") as mock_logger:
            result = extractor._decode_raw_image(msg)
            assert result is None
            mock_logger.warning.assert_called_with(
                "Unsupported image encoding: {}", "16UC1"
            )

    def test_decode_numpy_array_data(self):
        """处理 numpy array 类型的 data"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "rgb8"
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8)

        with patch("cv2.imencode", return_value=(True, np.array([1, 2, 3]))):
            result = extractor._decode_raw_image(msg)
            assert result is not None

    def test_decode_cv2_encode_failure(self):
        """cv2.imencode 失败时返回 None"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "bgr8"
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        with patch("cv2.imencode", return_value=(False, None)):
            result = extractor._decode_raw_image(msg)
            assert result is None

    def test_decode_exception_handling(self):
        """异常处理返回 None 并记录日志"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = "bgr8"
        # 5 bytes cannot reshape to (2, 2, 3) — triggers ValueError inside _decode_raw_image
        msg.data = b"short"

        with patch("app.services.frame_extractor.logger") as mock_logger:
            result = extractor._decode_raw_image(msg)
            assert result is None
            mock_logger.warning.assert_called_once()


# -----------------------------------------------------------------------------
# TestContextManager
# -----------------------------------------------------------------------------


class TestContextManager:
    """Test context manager."""

    def test_context_manager_closes_file(self):
        """退出上下文时关闭文件句柄"""
        mock_file = MagicMock()

        with patch("builtins.open", return_value=mock_file):
            with McapFrameExtractor("/tmp/test.mcap") as extractor:
                extractor._file_handle = mock_file
                extractor._reader = MagicMock()

        mock_file.close.assert_called_once()

    def test_explicit_close(self):
        """显式调用 close 方法"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        mock_file = MagicMock()
        extractor._file_handle = mock_file
        extractor._reader = MagicMock()

        extractor.close()

        mock_file.close.assert_called_once()
        assert extractor._file_handle is None
        assert extractor._reader is None

    def test_close_with_no_file_handle(self):
        """无文件句柄时 close 不报错"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._file_handle = None

        extractor.close()

    def test_context_manager_exception_handling(self):
        """上下文管理器内异常时仍关闭文件"""
        mock_file = MagicMock()

        with patch("builtins.open", return_value=mock_file):
            try:
                with McapFrameExtractor("/tmp/test.mcap") as extractor:
                    extractor._file_handle = mock_file
                    extractor._reader = MagicMock()
                    raise ValueError("Test exception")
            except ValueError:
                pass

        mock_file.close.assert_called_once()
