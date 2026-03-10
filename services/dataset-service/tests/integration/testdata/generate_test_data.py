"""Generate test MCAP files for integration tests.

Usage:
    python generate_test_data.py

This script generates various MCAP test files for integration testing:
- ros1_compressed_images.mcap: ROS1 MCAP with CompressedImage messages
- ros2_images.mcap: ROS2 MCAP with raw Image messages
- ros2_compressed.mcap: ROS2 MCAP with CompressedImage messages
- empty.mcap: Empty MCAP file
- no_images.mcap: MCAP with only non-image topics
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

def create_ros1_compressed_image_mcap(output_path: Path):
    """Create a ROS1 MCAP file with CompressedImage messages."""
    try:
        from mcap.writer import Writer
        from mcap_ros1.message_encoding import Ros1MessageEncoding

        with open(output_path, "wb") as f:
            writer = Writer(f)
            writer.start()

            # Register schema for CompressedImage
            schema_id = writer.register_schema(
                name="sensor_msgs/CompressedImage",
                encoding="ros1msg",
                data=b"# CompressedImage message\nHeader header\nstring format\nuint8[] data",
            )

            # Register channel
            channel_id = writer.register_channel(
                topic="/camera/compressed",
                message_encoding=Ros1MessageEncoding,
                schema_id=schema_id,
            )

            # Write some messages with timestamps
            base_time = 1_000_000_000_000  # Unix ns timestamp
            jpeg_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 100 + b"\xff\xd9"

            for i in range(30):  # 30 frames at 10Hz = 3 seconds
                timestamp = base_time + i * 100_000_000  # 100ms intervals

                # ROS1 serialized CompressedImage
                # Format: header (serialized separately), format string, data array
                header_bytes = b"\x00" * 32  # Simplified header
                format_str = b"jpeg\x00"
                data_len = len(jpeg_data)

                msg_data = header_bytes + format_str + struct.pack("<I", data_len) + jpeg_data

                writer.add_message(
                    channel_id=channel_id,
                    log_time=timestamp,
                    data=msg_data,
                    publish_time=timestamp,
                )

            writer.finish()
        print(f"Created: {output_path}")
    except ImportError as e:
        print(f"Skipping {output_path}: {e}")

def create_ros2_image_mcap(output_path: Path):
    """Create a ROS2 MCAP file with raw Image messages."""
    try:
        from mcap.writer import Writer

        with open(output_path, "wb") as f:
            writer = Writer(f)
            writer.start()

            # Register schema for Image
            schema_id = writer.register_schema(
                name="sensor_msgs/msg/Image",
                encoding="ros2msg",
                data=b"# Image message\nbuiltin_interfaces/Time stamp\nuint32 height\nuint32 width\nstring encoding\nuint8 is_bigendian\nuint32 step\nuint8[] data",
            )

            # Register channel
            channel_id = writer.register_channel(
                topic="/camera/image_raw",
                message_encoding="cdr",
                schema_id=schema_id,
            )

            # Write some messages
            base_time = 1_000_000_000_000
            height = 480
            width = 640
            image_data = bytes([0] * (height * width * 3))  # bgr8

            for i in range(30):
                timestamp = base_time + i * 100_000_000

                # CDR serialized Image (simplified)
                # Format depends on ROS2 CDR serialization
                msg_data = struct.pack("<I", height) + struct.pack("<I", width)
                msg_data += b"bgr8\x00\x00\x00\x00"  # encoding (8 bytes padded)
                msg_data += b"\x00"  # is_bigendian
                msg_data += struct.pack("<I", width * 3)  # step
                msg_data += struct.pack("<I", len(image_data))  # data length
                msg_data += image_data

                writer.add_message(
                    channel_id=channel_id,
                    log_time=timestamp,
                    data=msg_data,
                    publish_time=timestamp,
                )

            writer.finish()
        print(f"Created: {output_path}")
    except ImportError as e:
        print(f"Skipping {output_path}: {e}")

def create_empty_mcap(output_path: Path):
    """Create an empty MCAP file."""
    try:
        from mcap.writer import Writer

        with open(output_path, "wb") as f:
            writer = Writer(f)
            writer.start()
            writer.finish()
        print(f"Created: {output_path}")
    except ImportError as e:
        print(f"Skipping {output_path}: {e}")

def create_no_images_mcap(output_path: Path):
    """Create an MCAP file with only non-image topics."""
    try:
        from mcap.writer import Writer

        with open(output_path, "wb") as f:
            writer = Writer(f)
            writer.start()

            # Register schema for Odometry
            odom_schema = writer.register_schema(
                name="nav_msgs/Odometry",
                encoding="ros1msg",
                data=b"Odometry message",
            )

            # Register channel
            odom_channel = writer.register_channel(
                topic="/odom",
                message_encoding="ros1",
                schema_id=odom_schema,
            )

            # Write some odometry messages
            base_time = 1_000_000_000_000
            for i in range(10):
                timestamp = base_time + i * 100_000_000
                writer.add_message(
                    channel_id=odom_channel,
                    log_time=timestamp,
                    data=b"odometry_data",
                    publish_time=timestamp,
                )

            writer.finish()
        print(f"Created: {output_path}")
    except ImportError as e:
        print(f"Skipping {output_path}: {e}")

def main():
    """Generate all test data files."""
    output_dir = Path(__file__).parent
    output_dir.mkdir(exist_ok=True)

    files_to_create = [
        ("ros1_compressed_images.mcap", create_ros1_compressed_image_mcap),
        ("ros2_images.mcap", create_ros2_image_mcap),
        ("ros2_compressed.mcap", create_ros1_compressed_image_mcap),  # Reuse for now
        ("empty.mcap", create_empty_mcap),
        ("no_images.mcap", create_no_images_mcap),
    ]

    for filename, creator in files_to_create:
        output_path = output_dir / filename
        if not output_path.exists():
            try:
                creator(output_path)
            except Exception as e:
                print(f"Error creating {filename}: {e}")
        else:
            print(f"Already exists: {output_path}")

    print("\nTest data generation complete!")

if __name__ == "__main__":
    main()
