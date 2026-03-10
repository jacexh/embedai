"""Frame extractor service for MCAP files."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

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
        self._file_handle: BinaryIO | None = None
        self._reader: McapReader | None = None

    def _get_reader(self) -> McapReader:
        """Lazy init reader."""
        if self._reader is None:
            from mcap.reader import make_reader

            self._file_handle = open(self.file_path, "rb")
            self._reader = make_reader(self._file_handle)
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

    def get_time_range(self) -> tuple[int, int] | None:
        """Get the time range of the MCAP file in nanoseconds.

        Returns:
            Tuple of (start_time_ns, end_time_ns) or None if not available
        """
        reader = self._get_reader()
        summary = reader.get_summary()

        if summary and summary.statistics:
            start = summary.statistics.message_start_time
            end = summary.statistics.message_end_time
            return (start, end)
        return None

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

        # Adjust timestamp to valid range if needed
        time_range = self.get_time_range()
        if time_range:
            start_time, end_time = time_range
            if target_timestamp_ns < start_time:
                target_timestamp_ns = start_time
            elif target_timestamp_ns > end_time:
                target_timestamp_ns = end_time

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
        """Close the file handle and release resources."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        self._reader = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
