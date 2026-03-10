"""Integration tests for frame extractor using real MCAP files.

These tests require actual MCAP test files to be present in the testdata directory.
To generate test files, use the helper script at testdata/generate_test_data.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "testdata"

# Skip marker for when test data is not available
needs_test_data = pytest.mark.skipif(
    not TEST_DATA_DIR.exists() or not any(TEST_DATA_DIR.iterdir()),
    reason="Test data files not available"
)


class TestFrameExtractorWithRealRos1Mcap:
    """使用真实 ROS1 MCAP 文件测试"""

    @pytest.fixture(scope="class")
    def ros1_mcap_path(self):
        """提供 ROS1 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros1_compressed_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_read_ros1_compressed_image_topics(self, ros1_mcap_path):
        """读取 ROS1 CompressedImage topics"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()

            assert len(topics) > 0
            compressed_topics = [t for t in topics if t["type"] == "compressed_image"]
            assert len(compressed_topics) > 0

            for topic in topics:
                assert "name" in topic
                assert "type" in topic
                assert "schema_name" in topic
                assert topic["schema_name"] in [
                    "sensor_msgs/msg/Image",
                    "sensor_msgs/msg/CompressedImage",
                ]

    def test_get_time_range_from_ros1_mcap(self, ros1_mcap_path):
        """获取 ROS1 MCAP 时间范围"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            time_range = extractor.get_time_range()

            assert time_range is not None
            start, end = time_range
            assert start < end
            assert start > 0  # ROS1 使用 Unix 时间戳

    def test_extract_frame_from_ros1_compressed(self, ros1_mcap_path):
        """从 ROS1 CompressedImage topic 提取帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            compressed_topics = [t for t in topics if t["type"] == "compressed_image"]

            if not compressed_topics:
                pytest.skip("No compressed image topics in test file")

            topic_name = compressed_topics[0]["name"]
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            frame = extractor.extract_frame(topic_name, mid_time)

            assert frame is not None
            assert isinstance(frame.data, bytes)
            assert len(frame.data) > 0
            assert frame.timestamp_ns >= time_range[0]
            assert frame.timestamp_ns <= time_range[1]

            # Verify valid JPEG
            assert frame.data[:2] == b"\xff\xd8"  # JPEG SOI marker
            assert frame.data[-2:] == b"\xff\xd9"  # JPEG EOI marker

    def test_extract_frame_timestamp_clamping(self, ros1_mcap_path):
        """时间戳自动调整到有效范围"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()

            # Request timestamp before start
            frame = extractor.extract_frame(topic_name, 0)
            assert frame is not None
            assert frame.timestamp_ns >= time_range[0]

            # Request timestamp after end
            frame = extractor.extract_frame(topic_name, time_range[1] + 1000000000)
            assert frame is not None
            assert frame.timestamp_ns <= time_range[1]

    def test_extract_frame_closest_timestamp(self, ros1_mcap_path):
        """提取最接近目标时间戳的帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()

            # Extract frames at different timestamps
            frame1 = extractor.extract_frame(topic_name, time_range[0])
            frame2 = extractor.extract_frame(topic_name, time_range[1])

            assert frame1 is not None
            assert frame2 is not None
            assert frame1.timestamp_ns != frame2.timestamp_ns

    def test_extract_multiple_frames_sequential(self, ros1_mcap_path):
        """顺序提取多个帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()
            duration = time_range[1] - time_range[0]

            # Extract 5 frames at regular intervals
            timestamps = [
                time_range[0] + i * duration // 5
                for i in range(5)
            ]

            frames = []
            for ts in timestamps:
                frame = extractor.extract_frame(topic_name, ts)
                if frame:
                    frames.append(frame)

            assert len(frames) > 0
            for frame in frames:
                assert isinstance(frame.data, bytes)
                assert len(frame.data) > 0


class TestFrameExtractorWithRealRos2Mcap:
    """使用真实 ROS2 MCAP 文件测试"""

    @pytest.fixture(scope="class")
    def ros2_mcap_path(self):
        """提供 ROS2 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros2_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_read_ros2_image_topics(self, ros2_mcap_path):
        """读取 ROS2 Image topics"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros2_mcap_path) as extractor:
            topics = extractor.get_image_topics()

            assert len(topics) > 0
            for topic in topics:
                assert topic["schema_name"] in [
                    "sensor_msgs/msg/Image",
                    "sensor_msgs/msg/CompressedImage",
                ]

    def test_extract_frame_from_ros2_raw_image(self, ros2_mcap_path):
        """从 ROS2 raw Image topic 提取并编码帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros2_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            raw_topics = [t for t in topics if t["type"] == "image"]

            if not raw_topics:
                pytest.skip("No raw image topics in test file")

            topic_name = raw_topics[0]["name"]
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            frame = extractor.extract_frame(topic_name, mid_time)

            assert frame is not None
            assert isinstance(frame.data, bytes)
            assert len(frame.data) > 0
            # Verify valid JPEG
            assert frame.data[:2] == b"\xff\xd8"


class TestFrameExtractorWithRealRos2CompressedMcap:
    """使用真实 ROS2 CompressedImage MCAP 文件测试"""

    @pytest.fixture(scope="class")
    def ros2_compressed_mcap_path(self):
        """提供 ROS2 CompressedImage MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros2_compressed.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_extract_frame_from_ros2_compressed(self, ros2_compressed_mcap_path):
        """从 ROS2 CompressedImage topic 提取帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros2_compressed_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            compressed_topics = [t for t in topics if t["type"] == "compressed_image"]

            if not compressed_topics:
                pytest.skip("No compressed image topics in test file")

            topic_name = compressed_topics[0]["name"]
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            frame = extractor.extract_frame(topic_name, mid_time)

            assert frame is not None
            assert isinstance(frame.data, bytes)
            assert len(frame.data) > 0
            assert frame.data[:2] == b"\xff\xd8"


class TestFrameExtractorEdgeCases:
    """边缘情况测试"""

    @pytest.fixture(scope="class")
    def empty_mcap_path(self):
        """提供空 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "empty.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    @pytest.fixture(scope="class")
    def no_images_mcap_path(self):
        """提供无图像 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "no_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_empty_mcap_returns_no_topics(self, empty_mcap_path):
        """空 MCAP 返回空 topic 列表"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(empty_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            assert topics == []

    def test_empty_mcap_no_time_range(self, empty_mcap_path):
        """空 MCAP 无时间范围"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(empty_mcap_path) as extractor:
            time_range = extractor.get_time_range()
            assert time_range is None

    def test_no_images_mcap_returns_empty_topics(self, no_images_mcap_path):
        """无图像 MCAP 返回空图像 topic 列表"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(no_images_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            assert topics == []

    def test_no_images_mcap_extract_frame_returns_none(self, no_images_mcap_path):
        """无图像 MCAP 提取帧返回 None"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(no_images_mcap_path) as extractor:
            frame = extractor.extract_frame("/camera/image", 1000000000)
            assert frame is None


class TestFrameExtractorConcurrency:
    """并发安全测试"""

    @pytest.fixture(scope="class")
    def ros1_mcap_path(self):
        """提供 ROS1 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros1_compressed_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_multiple_extractors_same_file(self, ros1_mcap_path):
        """多个 extractor 同时读取同一文件"""
        from app.services.frame_extractor import McapFrameExtractor
        import concurrent.futures

        def extract_frame(extractor, topic, timestamp):
            return extractor.extract_frame(topic, timestamp)

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()

            # Concurrent extraction
            timestamps = [
                time_range[0] + i * (time_range[1] - time_range[0]) // 10
                for i in range(5)
            ]

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(extract_frame, extractor, topic_name, ts)
                    for ts in timestamps
                ]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            assert all(r is not None for r in results)

    def test_sequential_extractors_same_file(self, ros1_mcap_path):
        """顺序创建多个 extractor 读取同一文件"""
        from app.services.frame_extractor import McapFrameExtractor

        for _ in range(3):
            with McapFrameExtractor(ros1_mcap_path) as extractor:
                topics = extractor.get_image_topics()
                if topics:
                    time_range = extractor.get_time_range()
                    frame = extractor.extract_frame(topics[0]["name"], time_range[0])
                    assert frame is not None


class TestFrameExtractorPerformance:
    """性能测试"""

    @pytest.fixture(scope="class")
    def ros1_mcap_path(self):
        """提供 ROS1 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros1_compressed_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_frame_extraction_response_time(self, ros1_mcap_path):
        """帧提取响应时间 < 1s"""
        import time
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            start = time.time()
            frame = extractor.extract_frame(topic_name, mid_time)
            elapsed = time.time() - start

            assert frame is not None
            assert elapsed < 1.0, f"Frame extraction took {elapsed}s, expected < 1s"

    def test_sequential_frame_requests(self, ros1_mcap_path):
        """顺序请求多个帧"""
        import time
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]["name"]
            time_range = extractor.get_time_range()
            duration = time_range[1] - time_range[0]

            timestamps = [time_range[0] + duration * i // 10 for i in range(10)]

            start = time.time()
            for ts in timestamps:
                frame = extractor.extract_frame(topic_name, ts)
                assert frame is not None
            elapsed = time.time() - start

            # 10 frames should complete in reasonable time
            assert elapsed < 5.0, f"10 frame extractions took {elapsed}s"
