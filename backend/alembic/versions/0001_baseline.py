"""Baseline schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-15

Phase 1 has no domain tables. This revision verifies the Alembic toolchain.
"""

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
