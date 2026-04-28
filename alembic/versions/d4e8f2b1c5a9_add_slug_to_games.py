"""add slug to games

Revision ID: d4e8f2b1c5a9
Revises: c1d9e7a4b2f0
Create Date: 2026-04-28

Adds a human-readable slug column to the games table.
Format: <white>-vs-<black>-<YYYY-MM-DD> with a numeric suffix
(-2, -3, …) when the same pair plays more than once on a given day.

The chess.com UUID primary key (games.id) is unchanged.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e8f2b1c5a9"
down_revision: Union[str, Sequence[str], None] = "c1d9e7a4b2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("slug", sa.String(length=80), nullable=True),
    )
    op.create_index("ix_games_slug", "games", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_games_slug", table_name="games")
    op.drop_column("games", "slug")
