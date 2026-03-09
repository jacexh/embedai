from mcap.reader import make_reader

from pipeline.extractors.models import EpisodeMeta, TopicMeta


class McapExtractor:
    TOPIC_TYPE_MAP = {
        "sensor_msgs/msg/Image": "image",
        "sensor_msgs/msg/CompressedImage": "image",
        "sensor_msgs/msg/PointCloud2": "pointcloud",
        "sensor_msgs/msg/Imu": "imu",
        "geometry_msgs/msg/WrenchStamped": "force",
        "sensor_msgs/msg/JointState": "joint_state",
    }

    def __init__(self, file_path: str):
        self.file_path = file_path

    def extract(self) -> EpisodeMeta:
        meta = EpisodeMeta(format="mcap")
        topic_stats: dict[str, dict] = {}

        with open(self.file_path, "rb") as f:
            reader = make_reader(f)
            summary = reader.get_summary()

            if summary and summary.statistics:
                start_ns = summary.statistics.message_start_time
                end_ns = summary.statistics.message_end_time
                meta.duration_seconds = (end_ns - start_ns) / 1e9

                for channel_id, channel in summary.channels.items():
                    schema = summary.schemas.get(channel.schema_id)
                    schema_name = schema.name if schema else ""
                    msg_count = summary.statistics.channel_message_counts.get(channel_id, 0)
                    topic_stats[channel.topic] = {
                        "schema_name": schema_name,
                        "message_count": msg_count,
                    }

        duration = meta.duration_seconds if meta.duration_seconds > 0 else 1.0
        for topic_name, stats in topic_stats.items():
            t_type = self._infer_type(stats["schema_name"])
            freq = round(stats["message_count"] / duration, 2)
            meta.topics.append(TopicMeta(
                name=topic_name,
                type=t_type,
                message_count=stats["message_count"],
                frequency_hz=freq,
                start_time_offset=0.0,
                end_time_offset=meta.duration_seconds,
                schema_name=stats["schema_name"],
            ))

        return meta

    def _infer_type(self, schema_name: str) -> str:
        return self.TOPIC_TYPE_MAP.get(schema_name, "other")
