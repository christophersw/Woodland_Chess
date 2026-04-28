"""merge heads for players and system events

Revision ID: c1d9e7a4b2f0
Revises: 755322e96c64, 8f2c4e7a9d3b
Create Date: 2026-04-27
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "c1d9e7a4b2f0"
down_revision: Union[str, Sequence[str], None] = ("755322e96c64", "8f2c4e7a9d3b")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
