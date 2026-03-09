import h5py

from pipeline.extractors.models import EpisodeMeta, TopicMeta


def _infer_hdf5_type(name: str, dataset: "h5py.Dataset") -> str:
    name_lower = name.lower()
    if any(k in name_lower for k in ("image", "rgb", "depth", "camera")):
        return "image"
    if any(k in name_lower for k in ("point", "lidar", "cloud")):
        return "pointcloud"
    if "imu" in name_lower or "accel" in name_lower or "gyro" in name_lower:
        return "imu"
    if any(k in name_lower for k in ("force", "wrench", "torque")):
        return "force"
    if any(k in name_lower for k in ("joint", "qpos", "qvel")):
        return "joint_state"
    return "other"


def _extract_freq(f: "h5py.File", name: str) -> float:
    """Try to read frequency from sibling attrs or timestamps dataset."""
    try:
        parts = name.split("/")
        # Look for timestamps dataset alongside data
        ts_candidates = ["/".join(parts[:-1] + ["timestamps"]), "/timestamps", "timestamps"]
        for ts_path in ts_candidates:
            if ts_path in f:
                ts = f[ts_path][()]
                if len(ts) > 1:
                    avg_dt = (ts[-1] - ts[0]) / (len(ts) - 1)
                    return round(1.0 / avg_dt, 2) if avg_dt > 0 else 0.0
    except Exception:
        pass
    return 0.0


def extract_hdf5_meta(file_path: str) -> EpisodeMeta:
    meta = EpisodeMeta(format="hdf5")

    with h5py.File(file_path, "r") as f:
        # Try to read duration from top-level attrs
        if "duration" in f.attrs:
            meta.duration_seconds = float(f.attrs["duration"])

        def visitor(name: str, obj: object) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            t = TopicMeta(
                name=f"/{name}",
                type=_infer_hdf5_type(name, obj),
                message_count=obj.shape[0] if obj.ndim > 0 else 1,
                frequency_hz=_extract_freq(f, name),
                start_time_offset=0.0,
                end_time_offset=meta.duration_seconds,
                schema_name=str(obj.dtype),
            )
            meta.topics.append(t)

        f.visititems(visitor)

    return meta
