"""Add episode_id to annotation_tasks.

Revision ID: 003
Revises: 002
Create Date: 2026-03-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotation_tasks",
        sa.Column("episode_id", UUID(as_uuid=True), sa.ForeignKey("episodes.id"), nullable=True),
    )
    op.create_index("ix_tasks_episode_id", "annotation_tasks", ["episode_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_episode_id", table_name="annotation_tasks")
    op.drop_column("annotation_tasks", "episode_id")
