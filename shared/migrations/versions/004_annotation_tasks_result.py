"""Add annotation_result to annotation_tasks.

Revision ID: 004
Revises: 003
Create Date: 2026-03-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotation_tasks",
        sa.Column("annotation_result", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotation_tasks", "annotation_result")
