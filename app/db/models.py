from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    analyses_used_this_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyses_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list[User]] = relationship("User", back_populates="workspace")
    sites: Mapped[list[Site]] = relationship("Site", back_populates="workspace")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    # GSC OAuth tokens stored as JSONB; null until user connects GSC.
    # TODO: encrypt at rest before production launch (Sprint 5 security pass).
    gsc_tokens: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="users")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gsc_property: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="sites")
    pages: Mapped[list[Page]] = relationship("Page", back_populates="site")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("site_id", "url", name="uq_pages_site_url"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analysis_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    site: Mapped[Site] = relationship("Site", back_populates="pages")
    analyses: Mapped[list[PageAnalysis]] = relationship("PageAnalysis", back_populates="page")


# Valid states for the page_analyses state machine (§3.1)
ANALYSIS_STATUSES = (
    "queued",
    "collecting_data",
    "data_ready",
    "summarizing_content",
    "summaries_ready",
    "running_readiness",
    "running_bottleneck",
    "assembling_verdict",
    "complete",
    "failed",
)

_CONFIDENCE_VALUES = ("low", "medium", "high")


class PageAnalysis(Base):
    __tablename__ = "page_analyses"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in ANALYSIS_STATUSES)})",
            name="ck_page_analyses_status",
        ),
        CheckConstraint(
            f"readiness_confidence IN ({', '.join(repr(c) for c in _CONFIDENCE_VALUES)})",
            name="ck_page_analyses_readiness_confidence",
        ),
        CheckConstraint(
            f"bottleneck_confidence IN ({', '.join(repr(c) for c in _CONFIDENCE_VALUES)})",
            name="ck_page_analyses_bottleneck_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )

    # State machine — see ANALYSIS_STATUSES tuple above
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")

    # Prompt version tracking — enables audit of which prompt produced which verdict
    summarization_prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Raw collected data snapshots (stored for debugging and re-runs without re-fetching)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Content summaries produced by the Haiku summarization stage
    content_summaries: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Structured verdicts — validated Pydantic models serialised as JSONB
    readiness_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bottleneck_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Deterministic confidence scores (post-validation, may override LLM self-report)
    readiness_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bottleneck_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Data quality flags used to compute confidence and surface in UI
    data_quality: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Records any confidence floor overrides applied during validation
    validation_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Outcome tracking (populated by future Campaigns module)
    outcome_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bottleneck_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deprecated legacy columns — retained for data continuity, not written in Sprint 2+
    verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    page: Mapped[Page] = relationship("Page", back_populates="analyses")


# Valid states for the opportunities state machine (§3.5, ide-implementation-design.md)
OPPORTUNITY_STATUSES = (
    "queued",
    "detecting_mode",
    "inferring_section",
    "collecting_data",
    "classifying_signals",
    "computing_score",
    "assembling_verdict",
    "complete",
    "failed",
)

_EVALUATION_MODES = ("specific_placement", "guest_post_opportunity")
_MODE_B_SUBTYPES = ("category_url", "domain_inferred")
_OUTCOMES = ("recommended", "with_conditions", "not_recommended", "insufficient_data")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in OPPORTUNITY_STATUSES)})",
            name="ck_opportunities_status",
        ),
        CheckConstraint(
            f"evaluation_mode IN ({', '.join(repr(m) for m in _EVALUATION_MODES)}) OR evaluation_mode IS NULL",
            name="ck_opportunities_evaluation_mode",
        ),
        CheckConstraint(
            f"overall_outcome IN ({', '.join(repr(o) for o in _OUTCOMES)}) OR overall_outcome IS NULL",
            name="ck_opportunities_outcome",
        ),
        CheckConstraint(
            f"confidence IN ({', '.join(repr(c) for c in _CONFIDENCE_VALUES)}) OR confidence IS NULL",
            name="ck_opportunities_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )

    # Prospect being evaluated
    prospect_url: Mapped[str] = mapped_column(Text, nullable=False)
    prospect_domain: Mapped[str] = mapped_column(String(255), nullable=False)

    # Evaluation mode (populated during detecting_mode state)
    evaluation_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode_b_subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    inferred_section: Mapped[str | None] = mapped_column(Text, nullable=True)

    # State machine
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")

    # Prompt versioning
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Computed scores
    investment_score: Mapped[float | None] = mapped_column(nullable=True)
    cluster_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Verdict
    opportunity_verdict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    overall_outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence_ceiling: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Audit
    validation_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    data_quality: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    page: Mapped[Page] = relationship("Page")
