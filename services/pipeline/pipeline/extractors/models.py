from dataclasses import dataclass, field


@dataclass
class TopicMeta:
    name: str
    type: str
    message_count: int
    frequency_hz: float
    start_time_offset: float
    end_time_offset: float
    schema_name: str


@dataclass
class EpisodeMeta:
    format: str = "mcap"
    duration_seconds: float = 0.0
    topics: list[TopicMeta] = field(default_factory=list)
