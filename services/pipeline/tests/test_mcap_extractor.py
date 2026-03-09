import os
import pytest

from pipeline.extractors.mcap_extractor import McapExtractor

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.mcap")


def test_extract_topics():
    extractor = McapExtractor(FIXTURE)
    result = extractor.extract()

    assert result.format == "mcap"
    assert result.duration_seconds > 0
    assert len(result.topics) == 2


def test_camera_topic_detected():
    result = McapExtractor(FIXTURE).extract()
    camera = next((t for t in result.topics if "camera" in t.name), None)
    assert camera is not None
    assert camera.type == "image"
    assert camera.message_count == 30
    assert camera.frequency_hz > 0


def test_imu_topic_detected():
    result = McapExtractor(FIXTURE).extract()
    imu = next((t for t in result.topics if "imu" in t.name), None)
    assert imu is not None
    assert imu.type == "imu"
    assert imu.message_count == 200
    assert imu.frequency_hz > 0


def test_infer_type_unknown():
    extractor = McapExtractor(FIXTURE)
    assert extractor._infer_type("custom_msgs/msg/Custom") == "other"
