"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # projects
    op.create_table('projects',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('topic_schema', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # users
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),  # admin|engineer|annotator_internal|annotator_outsource
        sa.Column('skill_tags', JSONB, server_default='[]'),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id')),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # episodes
    op.create_table('episodes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('format', sa.String(10), nullable=False),  # mcap|hdf5
        sa.Column('size_bytes', sa.BigInteger),
        sa.Column('duration_seconds', sa.Float),
        sa.Column('status', sa.String(20), nullable=False, server_default='uploading'),
        sa.Column('quality_score', sa.Float),
        sa.Column('metadata', JSONB, server_default='{}'),
        sa.Column('storage_path', sa.String(1000)),
        sa.Column('recorded_at', sa.DateTime(timezone=True)),
        sa.Column('ingested_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_episodes_project_status', 'episodes', ['project_id', 'status'])
    op.create_index('ix_episodes_recorded_at', 'episodes', ['recorded_at'])

    # topics
    op.create_table('topics',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50)),  # image|pointcloud|imu|force|joint_state|other
        sa.Column('start_time_offset', sa.Float),
        sa.Column('end_time_offset', sa.Float),
        sa.Column('message_count', sa.Integer),
        sa.Column('frequency_hz', sa.Float),
        sa.Column('schema_name', sa.String(255)),
    )
    op.create_index('ix_topics_episode', 'topics', ['episode_id'])

    # upload_sessions
    op.create_table('upload_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id'), nullable=False),
        sa.Column('initiated_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('total_chunks', sa.Integer, nullable=False),
        sa.Column('received_chunks', sa.Integer, server_default='0'),
        sa.Column('chunk_size_bytes', sa.Integer),
        sa.Column('checksum_expected', sa.String(64)),
        sa.Column('status', sa.String(20), server_default='in_progress'),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # datasets
    op.create_table('datasets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # dataset_versions
    op.create_table('dataset_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('dataset_id', UUID(as_uuid=True), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('version_tag', sa.String(50), nullable=False),
        sa.Column('episode_refs', JSONB, nullable=False, server_default='[]'),
        sa.Column('episode_count', sa.Integer),
        sa.Column('total_size_bytes', sa.BigInteger),
        sa.Column('is_immutable', sa.Boolean, server_default='false'),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # annotation_tasks
    op.create_table('annotation_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('dataset_version_id', UUID(as_uuid=True), sa.ForeignKey('dataset_versions.id')),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('guideline_url', sa.String(500)),
        sa.Column('required_skills', JSONB, server_default='[]'),
        sa.Column('deadline', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(20), nullable=False, server_default='created'),
        sa.Column('assigned_to', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('label_studio_task_id', sa.Integer),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_tasks_project_status', 'annotation_tasks', ['project_id', 'status'])
    op.create_index('ix_tasks_assigned_to', 'annotation_tasks', ['assigned_to'])

    # annotations
    op.create_table('annotations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('annotation_tasks.id'), nullable=False),
        sa.Column('episode_id', UUID(as_uuid=True), sa.ForeignKey('episodes.id'), nullable=False),
        sa.Column('annotator_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('time_start', sa.Float),
        sa.Column('time_end', sa.Float),
        sa.Column('labels', JSONB, nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer, server_default='1'),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('reviewer_comment', sa.Text),
        sa.Column('label_studio_annotation_id', sa.Integer),
        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # export_jobs
    op.create_table('export_jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('dataset_version_id', UUID(as_uuid=True), sa.ForeignKey('dataset_versions.id'), nullable=False),
        sa.Column('triggered_by', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('format', sa.String(30), nullable=False),  # raw|webdataset|hf_datasets
        sa.Column('target_bucket', sa.String(255), nullable=False),
        sa.Column('target_prefix', sa.String(500)),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('progress_pct', sa.Float, server_default='0'),
        sa.Column('manifest_url', sa.String(1000)),
        sa.Column('error_message', sa.Text),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # recording_sessions (for streaming reconnect)
    op.create_table('recording_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('robot_id', sa.String(255)),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('episode_ids', JSONB, server_default='[]'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(timezone=True)),
    )


def downgrade():
    for table in ['recording_sessions', 'export_jobs', 'annotations',
                  'annotation_tasks', 'dataset_versions', 'datasets',
                  'upload_sessions', 'topics', 'episodes', 'users', 'projects']:
        op.drop_table(table)
