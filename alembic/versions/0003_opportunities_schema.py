"""Sprint 3: create opportunities table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-27

Creates the opportunities table for the Investment Decision Engine (§3.5).
State machine: 9 states. Outcome: 4 tiers. Stores InvestmentVerdict as JSONB.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUSES = (
    "queued", "detecting_mode", "inferring_section",
    "collecting_data", "classifying_signals", "computing_score",
    "assembling_verdict", "complete", "failed",
)
_OUTCOMES = ("recommended", "with_conditions", "not_recommended", "insufficient_data")
_CONFIDENCE = ("low", "medium", "high")
_MODES = ("specific_placement", "guest_post_opportunity")


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Prospect
        sa.Column("prospect_url", sa.Text, nullable=False),
        sa.Column("prospect_domain", sa.String(255), nullable=False),
        # Mode
        sa.Column("evaluation_mode", sa.String(50), nullable=True),
        sa.Column("mode_b_subtype", sa.String(50), nullable=True),
        sa.Column("inferred_section", sa.Text, nullable=True),
        # State machine
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        # Prompt versioning
        sa.Column("prompt_version", sa.String(100), nullable=True),
        # Computed scores
        sa.Column("investment_score", sa.Float, nullable=True),
        sa.Column("cluster_scores", JSONB, nullable=True),
        # Verdict
        sa.Column("opportunity_verdict", JSONB, nullable=True),
        sa.Column("overall_outcome", sa.String(50), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("confidence_ceiling", sa.String(10), nullable=True),
        # Audit
        sa.Column("validation_overrides", JSONB, nullable=True),
        sa.Column("data_quality", JSONB, nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Constraints
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _STATUSES)})",
            name="ck_opportunities_status",
        ),
        sa.CheckConstraint(
            f"evaluation_mode IN ({', '.join(repr(m) for m in _MODES)}) OR evaluation_mode IS NULL",
            name="ck_opportunities_evaluation_mode",
        ),
        sa.CheckConstraint(
            f"overall_outcome IN ({', '.join(repr(o) for o in _OUTCOMES)}) OR overall_outcome IS NULL",
            name="ck_opportunities_outcome",
        ),
        sa.CheckConstraint(
            f"confidence IN ({', '.join(repr(c) for c in _CONFIDENCE)}) OR confidence IS NULL",
            name="ck_opportunities_confidence",
        ),
    )

    op.create_index("idx_opportunities_page_id", "opportunities", ["page_id"])
    op.create_index("idx_opportunities_workspace_id", "opportunities", ["workspace_id"])
    op.create_index("idx_opportunities_outcome", "opportunities", ["overall_outcome"])
    op.create_index("idx_opportunities_status", "opportunities", ["status"])


def downgrade() -> None:
    op.drop_index("idx_opportunities_status", "opportunities")
    op.drop_index("idx_opportunities_outcome", "opportunities")
    op.drop_index("idx_opportunities_workspace_id", "opportunities")
    op.drop_index("idx_opportunities_page_id", "opportunities")
    op.drop_table("opportunities")
