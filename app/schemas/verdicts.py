"""Pydantic schemas for all LLM output types. These are the source of truth
for both the LLM tool schemas and the database JSONB columns (§6)."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Priority(str, Enum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Page summary (output of summarize-page-v1) ────────────────────────────────

class FormatLabel(str, Enum):
    GUIDE = "guide"
    LISTICLE = "listicle"
    COMPARISON = "comparison"
    TUTORIAL = "tutorial"
    CASE_STUDY = "case_study"
    DATA_PIECE = "data_piece"
    OPINION = "opinion"
    LANDING_PAGE = "landing_page"
    FAQ = "faq"
    TOOL_OR_CALCULATOR = "tool_or_calculator"
    NEWS_OR_UPDATE = "news_or_update"
    OTHER = "other"


class PageSummary(BaseModel):
    topic_and_angle: Annotated[str, Field(max_length=150)]
    format_label: FormatLabel
    heading_structure: Annotated[str, Field(max_length=200)]
    intent_alignment: Annotated[str, Field(max_length=200)]
    notable_elements: Annotated[list[str], Field(max_length=6)]
    visible_content_gaps: Annotated[list[str], Field(max_length=4)]


# ── Readiness verdict (§6.1) ──────────────────────────────────────────────────

class ReadinessOutcome(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    READY_WITH_CAVEATS = "ready_with_caveats"
    INSUFFICIENT_DATA = "insufficient_data"


class ReadinessDimension(BaseModel):
    passed: bool
    severity: Annotated[str, Field(pattern=r"^(low|medium|high)$")]
    reason: Annotated[str, Field(max_length=200)]
    action: Annotated[str | None, Field(None, max_length=200)]


class ReadinessVerdict(BaseModel):
    outcome: ReadinessOutcome
    confidence: Confidence
    confidence_rationale: Annotated[str, Field(max_length=300)]
    headline: Annotated[str, Field(max_length=120)]
    dimensions: dict[str, ReadinessDimension]
    actions: Annotated[list[str], Field(default_factory=list, max_length=5)]
    data_quality: dict[str, bool]


# ── Bottleneck verdict (§6.2) ─────────────────────────────────────────────────

class BottleneckCategory(str, Enum):
    LINK_AUTHORITY = "link_authority"
    CONTENT_DEPTH = "content_depth"
    INTENT_MISMATCH = "intent_mismatch"
    INTERNAL_LINKS = "internal_links"
    TECHNICAL = "technical"


class ConstraintSeverity(str, Enum):
    MILD = "mild"
    SIGNIFICANT = "significant"
    SEVERE = "severe"


class ConstraintBreakdown(BaseModel):
    category: BottleneckCategory
    severity: ConstraintSeverity
    weight: Annotated[float, Field(ge=0, le=1)]
    reason: Annotated[str, Field(max_length=250)]


class BottleneckVerdict(BaseModel):
    primary_constraint: BottleneckCategory
    primary_severity: ConstraintSeverity
    links_are_the_answer: bool
    headline: Annotated[str, Field(max_length=150)]
    competitive_context: Annotated[str, Field(max_length=200)]
    constraint_breakdown: list[ConstraintBreakdown]
    recommended_action: Annotated[str, Field(max_length=250)]
    recommended_action_priority: Priority
    confidence: Confidence
    confidence_rationale: Annotated[str, Field(max_length=300)]
    data_quality: dict[str, bool]
    authority_gap_rds: int | None = None
    content_gap_words: int | None = None
