"""Store LinkedIn URL and research metadata on target companies.

Revision ID: 0003_company_research
Revises: 0002_domain
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_company_research"
down_revision: Union[str, Sequence[str], None] = "0002_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("target_companies", sa.Column("linkedin_url", sa.String(length=500), nullable=True))
    op.add_column(
        "target_companies",
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("target_companies", "extra")
    op.drop_column("target_companies", "linkedin_url")
