"""add system_events table for tracking external events

Revision ID: 8f2c4e7a9d3b
Revises: b3c9f1a04e87
Create Date: 2026-04-27

Creates a new system_events table to track when external events occur:
  - ingest (API sync from Chess.com)
  - stockfish (analysis completions)
  - lc0 (analysis completions)

Fields:
  - event_type: type of event (ingest, stockfish, lc0)
  - status: started, completed, or failed
  - started_at: when the event began
  - completed_at: when the event finished (null if failed or ongoing)
  - duration_seconds: how long the event took
  - details: JSON payload with event-specific metadata
  - error_message: error details if status is failed
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f2c4e7a9d3b"
down_revision: Union[str, Sequence[str], None] = "b3c9f1a04e87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_system_events_event_type"),
        "system_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_events_status"),
        "system_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_events_started_at"),
        "system_events",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_events_completed_at"),
        "system_events",
        ["completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_system_events_completed_at"),
        table_name="system_events",
    )
    op.drop_index(
        op.f("ix_system_events_started_at"),
        table_name="system_events",
    )
    op.drop_index(
        op.f("ix_system_events_status"),
        table_name="system_events",
    )
    op.drop_index(
        op.f("ix_system_events_event_type"),
        table_name="system_events",
    )
    op.drop_table("system_events")
