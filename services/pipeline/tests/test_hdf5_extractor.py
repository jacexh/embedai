import os
import pytest

from pipeline.extractors.hdf5_extractor import extract_hdf5_meta

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.hdf5")


def test_extract_hdf5_basic():
    meta = extract_hdf5_meta(FIXTURE)
    assert meta.format == "hdf5"
    assert meta.duration_seconds == 10.0
    # datasets: image_rgb, joint_qpos, timestamps = 3 datasets
    assert len(meta.topics) > 0


def test_image_topic_type():
    meta = extract_hdf5_meta(FIXTURE)
    image_topics = [t for t in meta.topics if t.type == "image"]
    assert len(image_topics) >= 1
    assert image_topics[0].message_count == 100


def test_joint_topic_type():
    meta = extract_hdf5_meta(FIXTURE)
    joint_topics = [t for t in meta.topics if t.type == "joint_state"]
    assert len(joint_topics) >= 1
    assert joint_topics[0].message_count == 1000


def test_timestamps_frequency():
    meta = extract_hdf5_meta(FIXTURE)
    joint_topics = [t for t in meta.topics if t.type == "joint_state"]
    # timestamps dataset gives ~100 Hz
    assert joint_topics[0].frequency_hz > 0
