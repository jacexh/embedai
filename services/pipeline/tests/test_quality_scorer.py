import os
import pytest

from pipeline.extractors.models import EpisodeMeta, TopicMeta
from pipeline.quality.scorer import QualityScorer

MCAP_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.mcap")

PROJECT_SCHEMA = {
    "required_topics": ["/camera/rgb", "/imu/data"],
    "topic_frequency": {"/camera/rgb": 30.0, "/imu/data": 200.0},
}


def _make_meta(cam_hz: float = 30.0, imu_hz: float = 200.0, include_imu: bool = True) -> EpisodeMeta:
    topics = [
        TopicMeta("/camera/rgb", "image", int(cam_hz * 10), cam_hz, 0.0, 10.0, "sensor_msgs/msg/Image"),
    ]
    if include_imu:
        topics.append(
            TopicMeta("/imu/data", "imu", int(imu_hz * 10), imu_hz, 0.0, 10.0, "sensor_msgs/msg/Imu")
        )
    return EpisodeMeta(format="mcap", duration_seconds=10.0, topics=topics)


def test_score_healthy_episode():
    meta = _make_meta()
    score, detail = QualityScorer(PROJECT_SCHEMA).score(meta, MCAP_FIXTURE)
    assert score >= 0.8
    assert detail.frame_rate_stability >= 0.9
    assert detail.sensor_completeness == 1.0


def test_score_missing_topic():
    meta = _make_meta(include_imu=False)
    score, detail = QualityScorer(PROJECT_SCHEMA).score(meta, MCAP_FIXTURE)
    # sensor_completeness = 0.5 (1 of 2 required topics missing)
    # total = 1.0*0.4 + 0.5*0.4 + 0.9*0.2 = 0.78 — lower than healthy (>=0.9)
    assert detail.sensor_completeness == 0.5
    assert score < 0.85  # penalised vs healthy episode


def test_score_degraded_frame_rate():
    # Single-topic schema so score only reflects camera rate
    schema = {"required_topics": ["/camera/rgb"], "topic_frequency": {"/camera/rgb": 30.0}}
    meta = EpisodeMeta(
        format="mcap",
        duration_seconds=10.0,
        topics=[TopicMeta("/camera/rgb", "image", 150, 15.0, 0.0, 10.0, "sensor_msgs/msg/Image")],
    )
    score, detail = QualityScorer(schema).score(meta, MCAP_FIXTURE)
    # fps score: ratio=0.5, penalty = 1 - 0.5 = 0.5
    assert detail.frame_rate_stability == 0.5
    assert score < 0.85  # fps penalty pulls total below healthy (0.5*0.4 + 1.0*0.4 + 0.9*0.2 = 0.78)


def test_score_no_schema():
    meta = _make_meta()
    score, detail = QualityScorer({}).score(meta, MCAP_FIXTURE)
    # With no schema constraints, frame_rate and completeness both default to 1.0
    assert detail.sensor_completeness == 1.0
    assert detail.frame_rate_stability == 1.0


def test_score_no_image_topics():
    meta = EpisodeMeta(
        format="mcap",
        duration_seconds=5.0,
        topics=[
            TopicMeta("/imu/data", "imu", 1000, 200.0, 0.0, 5.0, "sensor_msgs/msg/Imu"),
        ],
    )
    score, detail = QualityScorer({"required_topics": ["/imu/data"], "topic_frequency": {"/imu/data": 200.0}}).score(meta, MCAP_FIXTURE)
    assert detail.signal_quality == 1.0  # no image topics → default 1.0
    assert score >= 0.8


def test_score_returns_float_in_range():
    meta = _make_meta()
    score, detail = QualityScorer(PROJECT_SCHEMA).score(meta, MCAP_FIXTURE)
    assert 0.0 <= score <= 1.0
    assert 0.0 <= detail.frame_rate_stability <= 1.0
    assert 0.0 <= detail.sensor_completeness <= 1.0
    assert 0.0 <= detail.signal_quality <= 1.0
