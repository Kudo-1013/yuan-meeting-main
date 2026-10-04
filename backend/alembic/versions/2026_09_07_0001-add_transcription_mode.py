"""add transcription mode to meetings

Revision ID: 8f2a7c4d91e0
Revises: 293138585702
Create Date: 2026-09-07 00:01:00+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2a7c4d91e0"
down_revision: Union[str, None] = "293138585702"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("transcription_mode", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "transcription_mode")
