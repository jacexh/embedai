from dataclasses import asdict, dataclass

from pipeline.extractors.models import EpisodeMeta


@dataclass
class QualityDetail:
    frame_rate_stability: float
    sensor_completeness: float
    signal_quality: float
    total_score: float


WEIGHTS = {
    "frame_rate_stability": 0.4,
    "sensor_completeness": 0.4,
    "signal_quality": 0.2,
}


class QualityScorer:
    """Three-dimensional quality scoring per ADR H1.

    Dimensions:
    - frame_rate_stability: how close actual topic frequencies are to expected
    - sensor_completeness:  fraction of required topics present
    - signal_quality:       image sharpness proxy (Laplacian variance sampling)
    """

    TOLERANCE = 0.10  # ±10% frequency tolerance

    def __init__(self, project_schema: dict):
        self.schema = project_schema

    def score(self, meta: EpisodeMeta, file_path: str) -> tuple[float, QualityDetail]:
        fps_score = self._score_frame_rate(meta)
        completeness = self._score_completeness(meta)
        signal = self._score_signal_quality(meta, file_path)

        total = round(
            fps_score * WEIGHTS["frame_rate_stability"]
            + completeness * WEIGHTS["sensor_completeness"]
            + signal * WEIGHTS["signal_quality"],
            4,
        )
        detail = QualityDetail(
            frame_rate_stability=fps_score,
            sensor_completeness=completeness,
            signal_quality=signal,
            total_score=total,
        )
        return total, detail

    # ------------------------------------------------------------------
    # Internal scorers
    # ------------------------------------------------------------------

    def _score_frame_rate(self, meta: EpisodeMeta) -> float:
        """Return [0, 1] — mean score across topics with expected frequencies."""
        expected: dict[str, float] = self.schema.get("topic_frequency", {})
        if not expected:
            return 1.0

        scores = []
        for topic in meta.topics:
            if topic.name not in expected:
                continue
            expected_hz = expected[topic.name]
            if expected_hz <= 0:
                continue
            ratio = topic.frequency_hz / expected_hz
            if abs(1.0 - ratio) <= self.TOLERANCE:
                scores.append(1.0)
            else:
                # Linear penalty outside tolerance
                scores.append(max(0.0, 1.0 - abs(1.0 - ratio)))

        return round(sum(scores) / len(scores), 4) if scores else 1.0

    def _score_completeness(self, meta: EpisodeMeta) -> float:
        """Return fraction of required topics present."""
        required: list[str] = self.schema.get("required_topics", [])
        if not required:
            return 1.0
        present = {t.name for t in meta.topics}
        return round(len(set(required) & present) / len(required), 4)

    def _score_signal_quality(self, meta: EpisodeMeta, file_path: str) -> float:
        """Sample image frames and compute Laplacian variance for blur detection.

        Falls back to 1.0 when no image topics exist or cv2 is unavailable.
        Returns score in [0, 1]: 1.0 = sharp, 0.0 = very blurry.
        """
        image_topics = [t for t in meta.topics if t.type == "image"]
        if not image_topics:
            return 1.0

        try:
            return self._sample_sharpness(file_path, image_topics[0].name)
        except Exception:
            return 0.9  # graceful degradation

    def _sample_sharpness(self, file_path: str, topic_name: str) -> float:
        """Decode up to 5 evenly-spaced image frames from MCAP and score sharpness."""
        import cv2
        import numpy as np
        from mcap.reader import make_reader

        variances = []
        with open(file_path, "rb") as f:
            reader = make_reader(f)
            frames = []
            for schema, channel, message in reader.iter_messages(topics=[topic_name]):
                frames.append(message.data)
                if len(frames) >= 50:
                    break

        if not frames:
            return 0.9

        sample_indices = [int(i * (len(frames) - 1) / 4) for i in range(min(5, len(frames)))]
        for idx in sample_indices:
            raw = frames[idx]
            arr = np.frombuffer(raw, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if img is None or img.size == 0:
                continue
            lap_var = cv2.Laplacian(img, cv2.CV_64F).var()
            variances.append(lap_var)

        if not variances:
            return 0.9

        # Normalize: >100 is sharp, <10 is blurry
        SHARP_THRESHOLD = 100.0
        mean_var = sum(variances) / len(variances)
        return round(min(1.0, mean_var / SHARP_THRESHOLD), 4)
