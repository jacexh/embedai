"""Script to generate test fixtures. Run once to create sample MCAP and HDF5 files."""
import io
import os
import struct
import time

# ------- minimal MCAP fixture -------
def make_sample_mcap(path: str):
    """Create a minimal MCAP file with one image and one IMU channel."""
    from mcap.writer import Writer

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start(profile="ros2", library="test")

        image_schema_id = writer.register_schema(
            name="sensor_msgs/msg/Image",
            encoding="ros2msg",
            data=b"",
        )
        imu_schema_id = writer.register_schema(
            name="sensor_msgs/msg/Imu",
            encoding="ros2msg",
            data=b"",
        )

        cam_channel_id = writer.register_channel(
            topic="/camera/rgb",
            message_encoding="ros2",
            schema_id=image_schema_id,
        )
        imu_channel_id = writer.register_channel(
            topic="/imu/data",
            message_encoding="ros2",
            schema_id=imu_schema_id,
        )

        base_ns = int(time.time()) * 1_000_000_000
        # 30 image frames over 1 second
        for i in range(30):
            writer.add_message(
                channel_id=cam_channel_id,
                log_time=base_ns + i * 33_333_333,
                data=b"\x00" * 16,
                publish_time=base_ns + i * 33_333_333,
            )
        # 200 IMU messages over 1 second
        for i in range(200):
            writer.add_message(
                channel_id=imu_channel_id,
                log_time=base_ns + i * 5_000_000,
                data=b"\x00" * 12,
                publish_time=base_ns + i * 5_000_000,
            )

        writer.finish()


# ------- minimal HDF5 fixture -------
def make_sample_hdf5(path: str):
    import h5py
    import numpy as np

    with h5py.File(path, "w") as f:
        f.attrs["duration"] = 10.0

        # image dataset: 100 frames of 4x4 RGB
        f.create_dataset("observations/image_rgb", data=np.zeros((100, 4, 4, 3), dtype=np.uint8))
        # joint state dataset
        f.create_dataset("observations/joint_qpos", data=np.zeros((1000, 7), dtype=np.float32))
        # timestamps
        f.create_dataset("timestamps", data=np.linspace(0, 10, 1000))


if __name__ == "__main__":
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    os.makedirs(fixtures_dir, exist_ok=True)
    make_sample_mcap(os.path.join(fixtures_dir, "sample.mcap"))
    make_sample_hdf5(os.path.join(fixtures_dir, "sample.hdf5"))
    print("Fixtures created.")
