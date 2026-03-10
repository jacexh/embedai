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


# ---------------------------------------------------------------------------
# TestQualityScorerThresholds — boundary value and weighted formula tests
# ---------------------------------------------------------------------------

# Single-camera schema: 1 required topic at 30 Hz.
_SINGLE_CAM_SCHEMA = {
    "required_topics": ["/camera/rgb"],
    "topic_frequency": {"/camera/rgb": 30.0},
}


def _make_cam_meta(cam_hz: float) -> EpisodeMeta:
    """Build EpisodeMeta with a single topic typed 'imu' so signal_quality
    defaults to 1.0 without any cv2 / file I/O dependency."""
    return EpisodeMeta(
        format="mcap",
        duration_seconds=10.0,
        topics=[
            TopicMeta("/camera/rgb", "imu", int(cam_hz * 10), cam_hz, 0.0, 10.0, "sensor_msgs/msg/Image"),
        ],
    )


class TestQualityScorerThresholds:
    """Boundary value and weighted formula unit tests for QualityScorer."""

    def test_weighted_formula_exact_values(self):
        """30 Hz on single-topic schema: all dims = 1.0 → total = 1.0."""
        meta = _make_cam_meta(30.0)
        score, detail = QualityScorer(_SINGLE_CAM_SCHEMA).score(meta, MCAP_FIXTURE)

        assert detail.frame_rate_stability == 1.0
        assert detail.sensor_completeness == 1.0
        assert detail.signal_quality == 1.0

        expected = round(
            0.4 * detail.frame_rate_stability
            + 0.4 * detail.sensor_completeness
            + 0.2 * detail.signal_quality,
            4,
        )
        assert detail.total_score == expected
        assert score == 1.0

    def test_frame_rate_clearly_inside_upper_tolerance(self):
        """32 Hz (≈+6.7% from 30 Hz) is clearly inside ±10% → fps = 1.0."""
        meta = _make_cam_meta(32.0)
        _, detail = QualityScorer(_SINGLE_CAM_SCHEMA).score(meta, MCAP_FIXTURE)
        assert detail.frame_rate_stability == 1.0

    def test_frame_rate_clearly_outside_upper_tolerance(self):
        """36 Hz (+20% from 30 Hz) is clearly outside ±10% → fps < 1.0."""
        meta = _make_cam_meta(36.0)
        _, detail = QualityScorer(_SINGLE_CAM_SCHEMA).score(meta, MCAP_FIXTURE)
        assert detail.frame_rate_stability < 1.0

    def test_frame_rate_clearly_inside_lower_tolerance(self):
        """28 Hz (≈-6.7% from 30 Hz) is clearly inside ±10% → fps = 1.0."""
        meta = _make_cam_meta(28.0)
        _, detail = QualityScorer(_SINGLE_CAM_SCHEMA).score(meta, MCAP_FIXTURE)
        assert detail.frame_rate_stability == 1.0

    def test_frame_rate_clearly_outside_lower_tolerance(self):
        """24 Hz (-20% from 30 Hz) is clearly outside ±10% → fps < 1.0."""
        meta = _make_cam_meta(24.0)
        _, detail = QualityScorer(_SINGLE_CAM_SCHEMA).score(meta, MCAP_FIXTURE)
        assert detail.frame_rate_stability < 1.0

    def test_total_score_below_isolation_threshold(self):
        """Craft score < 0.3 by using separate required_topics and topic_frequency lists.

        - required_topics: [/sensor_a, /sensor_b] — both absent → completeness = 0.0
        - topic_frequency: {/camera/rgb: 30.0} — /camera/rgb at 0 Hz → fps = 0.0
        - signal_quality = 1.0 (imu-typed topic, no image branch)
        total = 0.4*0.0 + 0.4*0.0 + 0.2*1.0 = 0.2 < 0.3
        """
        schema = {
            "required_topics": ["/sensor_a", "/sensor_b"],
            "topic_frequency": {"/camera/rgb": 30.0},
        }
        meta = EpisodeMeta(
            format="mcap",
            duration_seconds=10.0,
            topics=[
                # /camera/rgb present in meta at 0 Hz → fps scored as 0.0
                # /sensor_a and /sensor_b absent → completeness = 0.0
                TopicMeta("/camera/rgb", "imu", 0, 0.0, 0.0, 10.0, "sensor_msgs/msg/Image"),
            ],
        )
        score, detail = QualityScorer(schema).score(meta, MCAP_FIXTURE)
        assert detail.sensor_completeness == 0.0
        assert detail.frame_rate_stability == 0.0
        assert detail.total_score < 0.3
        assert score < 0.3

    def test_total_score_in_low_quality_range(self):
        """Craft score in [0.3, 0.6): camera at 10 Hz + /lidar missing.
        fps≈0.333, completeness=0.5, signal=1.0
        total = 0.4*0.333 + 0.4*0.5 + 0.2*1.0 ≈ 0.533."""
        schema = {
            "required_topics": ["/camera/rgb", "/lidar/points"],
            "topic_frequency": {"/camera/rgb": 30.0, "/lidar/points": 10.0},
        }
        meta = EpisodeMeta(
            format="mcap",
            duration_seconds=10.0,
            topics=[
                TopicMeta("/camera/rgb", "imu", 100, 10.0, 0.0, 10.0, "sensor_msgs/msg/Image"),
            ],
        )
        score, detail = QualityScorer(schema).score(meta, MCAP_FIXTURE)
        assert 0.3 <= detail.total_score < 0.6
        assert 0.3 <= score < 0.6
