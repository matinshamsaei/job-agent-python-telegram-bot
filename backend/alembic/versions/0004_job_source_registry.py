"""Add the per-company job source registry and ATS adapter catalog columns.

Revision ID: 0004_job_source_registry
Revises: 0003_company_research
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_job_source_registry"
down_revision: Union[str, Sequence[str], None] = "0003_company_research"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_sources",
        sa.Column("ats_type", sa.String(length=40), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "job_sources",
        sa.Column("collection_strategy", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.add_column(
        "job_sources",
        sa.Column("adapter_implemented", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "job_sources",
        sa.Column("roadmap_phase", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("job_sources", sa.Column("docs_url", sa.String(length=500), nullable=True))
    op.create_index("ix_job_sources_ats_type", "job_sources", ["ats_type"])

    op.create_table(
        "company_job_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False, server_default="primary"),
        sa.Column("ats_type", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("board_token", sa.String(length=200), nullable=True),
        sa.Column("feed_url", sa.String(length=1000), nullable=True),
        sa.Column("job_url_pattern", sa.String(length=1000), nullable=True),
        sa.Column("collection_strategy", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="discovered"),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["target_companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "label", name="uq_company_job_source_label"),
    )
    op.create_index("ix_company_job_sources_company_id", "company_job_sources", ["company_id"])
    op.create_index("ix_company_job_sources_ats_type", "company_job_sources", ["ats_type"])
    op.create_index("ix_company_job_sources_status", "company_job_sources", ["status"])


def downgrade() -> None:
    op.drop_index("ix_company_job_sources_status", table_name="company_job_sources")
    op.drop_index("ix_company_job_sources_ats_type", table_name="company_job_sources")
    op.drop_index("ix_company_job_sources_company_id", table_name="company_job_sources")
    op.drop_table("company_job_sources")

    op.drop_index("ix_job_sources_ats_type", table_name="job_sources")
    op.drop_column("job_sources", "docs_url")
    op.drop_column("job_sources", "roadmap_phase")
    op.drop_column("job_sources", "adapter_implemented")
    op.drop_column("job_sources", "collection_strategy")
    op.drop_column("job_sources", "ats_type")
