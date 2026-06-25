"""sprint 2 schema alignment

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25

Changes:
- page_analyses: status values changed from UPPERCASE to lowercase snake_case
- page_analyses: status CHECK constraint updated to 10-state machine (lowercase)
- page_analyses: added columns for Sprint 2 workers
- pages: added path, title, last_analyzed_at, analysis_count
- pages: added UNIQUE(site_id, url) constraint
- workspaces: added slug, plan, analyses_used_this_period, analyses_limit

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUSES_OLD = (
    "QUEUED", "COLLECTING_DATA", "DATA_READY", "SUMMARIZING_CONTENT",
    "SUMMARIES_READY", "RUNNING_READINESS", "RUNNING_BOTTLENECK",
    "ASSEMBLING_VERDICT", "COMPLETE", "FAILED",
)
_STATUSES_NEW = (
    "queued", "collecting_data", "data_ready", "summarizing_content",
    "summaries_ready", "running_readiness", "running_bottleneck",
    "assembling_verdict", "complete", "failed",
)
_CONFIDENCE = ("low", "medium", "high")


def upgrade() -> None:
    # ── workspaces: add quota and plan columns ──────────────────────────────
    op.add_column("workspaces", sa.Column("slug", sa.String(255), nullable=True, unique=True))
    op.add_column("workspaces", sa.Column("plan", sa.String(50), nullable=False, server_default="free"))
    op.add_column("workspaces", sa.Column("analyses_used_this_period", sa.Integer, nullable=False, server_default="0"))
    op.add_column("workspaces", sa.Column("analyses_limit", sa.Integer, nullable=False, server_default="10"))

    # ── pages: add metadata columns and unique constraint ───────────────────
    op.add_column("pages", sa.Column("path", sa.Text, nullable=True))
    op.add_column("pages", sa.Column("title", sa.Text, nullable=True))
    op.add_column("pages", sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pages", sa.Column("analysis_count", sa.Integer, nullable=False, server_default="0"))
    op.create_unique_constraint("uq_pages_site_url", "pages", ["site_id", "url"])

    # ── page_analyses: migrate status values from UPPERCASE to lowercase ────
    # Drop the old CHECK constraint first (name defined in migration 0001)
    op.drop_constraint("ck_page_analyses_status", "page_analyses", type_="check")

    # Bulk-update any existing rows (safe: no production data at this stage)
    for old, new in zip(_STATUSES_OLD, _STATUSES_NEW):
        op.execute(
            f"UPDATE page_analyses SET status = '{new}' WHERE status = '{old}'"
        )

    # Update the default value
    op.alter_column(
        "page_analyses",
        "status",
        server_default="queued",
        existing_type=sa.String(50),
        existing_nullable=False,
    )

    # Re-create the CHECK constraint with lowercase values
    op.create_check_constraint(
        "ck_page_analyses_status",
        "page_analyses",
        f"status IN ({', '.join(repr(s) for s in _STATUSES_NEW)})",
    )

    # ── page_analyses: add new Sprint 2 columns ─────────────────────────────
    op.add_column(
        "page_analyses",
        sa.Column("workspace_id", UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("page_analyses", sa.Column("summarization_prompt_version", sa.String(100), nullable=True))
    op.add_column("page_analyses", sa.Column("prompt_version", sa.String(100), nullable=True))
    op.add_column("page_analyses", sa.Column("content_summaries", JSONB, nullable=True))
    op.add_column("page_analyses", sa.Column("readiness_verdict", JSONB, nullable=True))
    op.add_column("page_analyses", sa.Column("bottleneck_verdict", JSONB, nullable=True))
    op.add_column("page_analyses", sa.Column("readiness_confidence", sa.String(10), nullable=True))
    op.add_column("page_analyses", sa.Column("bottleneck_confidence", sa.String(10), nullable=True))
    op.add_column("page_analyses", sa.Column("data_quality", JSONB, nullable=True))
    op.add_column("page_analyses", sa.Column("validation_overrides", JSONB, nullable=True))
    op.add_column("page_analyses", sa.Column("outcome_tracked", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("page_analyses", sa.Column("bottleneck_confirmed", sa.Boolean, nullable=True))
    op.add_column("page_analyses", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_analyses", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_analyses", sa.Column("failed_reason", sa.Text, nullable=True))

    # Confidence CHECK constraints
    op.create_check_constraint(
        "ck_page_analyses_readiness_confidence",
        "page_analyses",
        f"readiness_confidence IN ({', '.join(repr(c) for c in _CONFIDENCE)})",
    )
    op.create_check_constraint(
        "ck_page_analyses_bottleneck_confidence",
        "page_analyses",
        f"bottleneck_confidence IN ({', '.join(repr(c) for c in _CONFIDENCE)})",
    )

    # Indexes for new columns
    op.create_index("ix_page_analyses_workspace_id", "page_analyses", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_page_analyses_workspace_id", "page_analyses")

    op.drop_constraint("ck_page_analyses_bottleneck_confidence", "page_analyses", type_="check")
    op.drop_constraint("ck_page_analyses_readiness_confidence", "page_analyses", type_="check")

    for col in (
        "failed_reason", "completed_at", "started_at", "bottleneck_confirmed",
        "outcome_tracked", "validation_overrides", "data_quality",
        "bottleneck_confidence", "readiness_confidence", "bottleneck_verdict",
        "readiness_verdict", "content_summaries", "prompt_version",
        "summarization_prompt_version", "workspace_id",
    ):
        op.drop_column("page_analyses", col)

    op.drop_constraint("ck_page_analyses_status", "page_analyses", type_="check")
    for new, old in zip(_STATUSES_NEW, _STATUSES_OLD):
        op.execute(f"UPDATE page_analyses SET status = '{old}' WHERE status = '{new}'")
    op.alter_column("page_analyses", "status", server_default="QUEUED",
                    existing_type=sa.String(50), existing_nullable=False)
    op.create_check_constraint(
        "ck_page_analyses_status", "page_analyses",
        f"status IN ({', '.join(repr(s) for s in _STATUSES_OLD)})",
    )

    op.drop_constraint("uq_pages_site_url", "pages", type_="unique")
    for col in ("analysis_count", "last_analyzed_at", "title", "path"):
        op.drop_column("pages", col)

    for col in ("analyses_limit", "analyses_used_this_period", "plan", "slug"):
        op.drop_column("workspaces", col)
