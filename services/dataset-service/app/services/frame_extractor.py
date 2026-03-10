"""Frame extractor service for MCAP files."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
from loguru import logger
from mcap.reader import make_reader
from rosbags.typesys import Stores, get_typestore


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
        self._reader = None
        self._typestore = get_typestore(Stores.ROS1_NOETIC)

    def _get_reader(self):
        """Lazy init reader."""
        if self._reader is None:
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
                    "sensor_msgs/Image",
                    "sensor_msgs/CompressedImage",
                ):
                    is_raw_image = schema.name in ("sensor_msgs/msg/Image", "sensor_msgs/Image")
                    topics.append({
                        "name": channel.topic,
                        "type": "image" if is_raw_image else "compressed_image",
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
        time_offset_ns: int = 0,  # Offset to convert relative timestamp to absolute
    ) -> FrameResult | None:
        """Extract the frame closest to target timestamp.

        Args:
            topic: Topic name to extract from
            target_timestamp_ns: Target timestamp in nanoseconds (relative to episode start)
            max_time_diff_ns: Maximum allowed time difference from target
            time_offset_ns: Time offset to add to target_timestamp_ns to get absolute timestamp

        Returns:
            FrameResult with JPEG data or None if no frame found
        """
        reader = self._get_reader()
        summary = reader.get_summary()

        # Convert relative timestamp to absolute timestamp
        absolute_target_ns = target_timestamp_ns + time_offset_ns

        # Adjust timestamp to valid range if needed
        time_range = self.get_time_range()
        if time_range:
            start_time, end_time = time_range
            if absolute_target_ns < start_time:
                absolute_target_ns = start_time
            elif absolute_target_ns > end_time:
                absolute_target_ns = end_time

        # Get channel and schema info for the topic
        topic_channel = None
        topic_schema = None
        if summary and summary.channels:
            for channel_id, channel in summary.channels.items():
                if channel.topic == topic:
                    topic_channel = channel
                    topic_schema = summary.schemas.get(channel.schema_id)
                    break

        if topic_channel is None or topic_schema is None:
            logger.warning("Topic {} not found in MCAP file", topic)
            return None

        best_frame: bytes | None = None
        best_timestamp: int | None = None
        min_diff = float("inf")

        for schema, channel, message in reader.iter_messages():
            if channel.topic != topic:
                continue

            if schema and schema.name not in (
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage",
                "sensor_msgs/Image",
                "sensor_msgs/CompressedImage",
            ):
                continue

            time_diff = abs(message.log_time - absolute_target_ns)
            if time_diff < min_diff:
                min_diff = time_diff
                best_timestamp = message.log_time

                # Deserialize based on message encoding
                try:
                    # Map ROS1 schema names to rosbags format (e.g., sensor_msgs/CompressedImage -> sensor_msgs/msg/CompressedImage)
                    type_name = schema.name
                    if "/msg/" not in type_name:
                        parts = type_name.split("/")
                        if len(parts) == 2:
                            type_name = f"{parts[0]}/msg/{parts[1]}"

                    if channel.message_encoding == "ros1":
                        # Raw ROS1 serialized bytes - use rosbags
                        decoded_msg = self._typestore.deserialize_ros1(
                            message.data, type_name
                        )
                    elif channel.message_encoding in ("cdr", "ros2"):
                        # ROS2 CDR encoding - use rosbags CDR deserializer
                        # "ros2" encoding is used by some MCAP writers and is compatible with CDR
                        decoded_msg = self._typestore.deserialize_cdr(
                            message.data, type_name
                        )
                    else:
                        logger.warning(
                            "Unknown message encoding: {}", channel.message_encoding
                        )
                        continue
                except Exception as e:
                    logger.warning(
                        "Failed to deserialize message on topic {}: {}", topic, e
                    )
                    continue

                if schema.name in ("sensor_msgs/msg/CompressedImage", "sensor_msgs/CompressedImage"):
                    best_frame = self._decode_compressed_image(decoded_msg)
                else:
                    best_frame = self._decode_raw_image(decoded_msg)

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

    def _decode_compressed_image(self, msg) -> bytes | None:
        """Decode compressed image message."""
        try:
            # msg is decoded by rosbags
            # CompressedImage has: header, format, data
            data = msg.data
            if isinstance(data, bytes):
                return data
            elif hasattr(data, "tobytes"):
                return data.tobytes()
            else:
                return bytes(data)
        except Exception as e:
            logger.warning("Failed to decode compressed image: {}", e)
            return None

    def _decode_raw_image(self, msg) -> bytes | None:
        """Decode raw Image message to JPEG."""
        try:
            import cv2

            # msg is decoded by rosbags
            # Image has: header, height, width, encoding, is_bigendian, step, data
            height = msg.height
            width = msg.width
            encoding = msg.encoding
            data = msg.data

            # Convert data to bytes
            if hasattr(data, "tobytes"):
                data = data.tobytes()
            elif not isinstance(data, bytes):
                data = bytes(data)

            # Handle different encodings
            if encoding in ("rgb8", "bgr8"):
                img = np.frombuffer(data, dtype=np.uint8)
                img = img.reshape((height, width, 3))

                # Convert RGB to BGR for OpenCV
                if encoding == "rgb8":
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

                # Encode to JPEG
                success, encoded = cv2.imencode(".jpg", img)
                if success:
                    return encoded.tobytes()
            elif encoding == "mono8":
                img = np.frombuffer(data, dtype=np.uint8)
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
