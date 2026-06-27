"""Pydantic schemas for the Investment Decision Engine (§3.5, §6.3).

SignalScores and ScoreResult are internal pipeline types (not stored directly).
InvestmentVerdict is the stored schema — serialised to opportunities.opportunity_verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class InvestmentOutcome(str, Enum):
    RECOMMENDED = "recommended"
    WITH_CONDITIONS = "with_conditions"
    NOT_RECOMMENDED = "not_recommended"
    INSUFFICIENT_DATA = "insufficient_data"


class HardExclusionGate(str, Enum):
    H1_PROHIBITED_CONTENT = "H1_prohibited_content"
    H2_DEINDEXED_PENALIZED = "H2_deindexed_penalized"
    H3_MALWARE = "H3_malware"
    H4_LANGUAGE_IMPOSSIBLE = "H4_language_impossible"
    H5_MANUAL_ACTION = "H5_manual_action"


class PlacementFeasibility(str, Enum):
    NATURAL = "natural"
    WORKABLE = "workable"
    FORCED = "forced"
    IMPLAUSIBLE = "implausible"


# ── Internal pipeline types (not stored) ─────────────────────────────────────

class SignalScores(BaseModel):
    """Structured output of LLM Call 1. Feeds the deterministic scorer."""
    p1_topical_relevance: Annotated[float, Field(ge=0.0, le=1.0)]
    p1_rationale: Annotated[str, Field(max_length=200)]
    p2_content_quality: Annotated[float, Field(ge=0.0, le=1.0)]
    p2_rationale: Annotated[str, Field(max_length=200)]
    p4_obl_quality: Annotated[float, Field(ge=0.0, le=1.0)]
    p4_rationale: Annotated[str, Field(max_length=200)]
    p5_placement_feasibility: PlacementFeasibility
    p5_rationale: Annotated[str, Field(max_length=200)]
    d1_topical_coherence: Annotated[float, Field(ge=0.0, le=1.0)]
    d1_rationale: Annotated[str, Field(max_length=200)]
    d4_editorial_integrity: Annotated[float, Field(ge=0.0, le=1.0)]
    d4_rationale: Annotated[str, Field(max_length=250)]
    d9_geo_language_match: Annotated[float, Field(ge=0.0, le=1.0)]
    d9_rationale: Annotated[str, Field(max_length=150)]
    language_match: Annotated[float, Field(ge=0.0, le=1.0)]
    data_quality_notes: Annotated[str, Field(max_length=300)]


class ClusterScores(BaseModel):
    """Deterministic cluster scores computed by ide_scorer."""
    relevance: Annotated[float, Field(ge=0.0, le=1.0)]
    authority: Annotated[float, Field(ge=0.0, le=1.0)]
    quality: Annotated[float, Field(ge=0.0, le=1.0)]
    risk: Annotated[float, Field(ge=0.0, le=1.0)]
    risk_multiplier: Annotated[float, Field(ge=0.0, le=1.0)]


@dataclass
class ScoreResult:
    """Full output of ide_scorer. Passed to LLM Call 2 and the orchestrator."""
    cluster_scores: ClusterScores
    investment_score: float            # 0–100
    editorial_integrity_cap_applied: bool
    p5_cap_applied: bool
    deterministic_confidence: str      # "low" | "medium" | "high"
    confidence_ceiling: str            # mode-based ceiling
    outcome: InvestmentOutcome


# ── Gate result (internal) ────────────────────────────────────────────────────

@dataclass
class GateResult:
    """Output of ide_gates.evaluate_gates(). If triggered, the pipeline stops scoring."""
    triggered: bool
    gate: HardExclusionGate | None = None
    reason: str | None = None


# ── Stored verdict schema (§6.3) ──────────────────────────────────────────────

class InvestmentVerdict(BaseModel):
    """The complete investment verdict stored in opportunities.opportunity_verdict."""

    # Outcome (always present)
    outcome: InvestmentOutcome
    investment_score: float | None = None

    # Mode context
    evaluation_mode: str | None = None
    mode_b_subtype: str | None = None

    # Hard exclusion (populated only when a gate fired)
    hard_exclusion_triggered: bool = False
    hard_exclusion_gate: HardExclusionGate | None = None
    hard_exclusion_reason: str | None = None

    # Computed scores (null when hard exclusion triggered or insufficient_data)
    cluster_scores: ClusterScores | None = None

    # Verdict language (from LLM Call 2; null when hard exclusion triggered)
    headline: Annotated[str | None, Field(None, max_length=130)] = None
    primary_reason: Annotated[str | None, Field(None, max_length=250)] = None
    supporting_signals: Annotated[list[str], Field(default_factory=list, max_length=4)]
    conditions: Annotated[list[str], Field(default_factory=list, max_length=3)]
    mode_qualifier: Annotated[str | None, Field(None, max_length=200)] = None
    confidence_rationale: Annotated[str | None, Field(None, max_length=250)] = None

    # Confidence
    confidence: str                    # "low" | "medium" | "high"
    confidence_ceiling: str | None = None

    # Data quality (mirrors IDEContext.data_quality)
    data_quality: dict = Field(default_factory=dict)


# ── IDE context dataclass (collection output) ─────────────────────────────────

@dataclass
class IDEContext:
    """All raw data collected for a single opportunity evaluation."""

    prospect_url: str
    prospect_domain: str

    # Mode (set during detecting_mode state)
    mode: str | None = None            # "specific_placement" | "guest_post_opportunity"
    mode_b_subtype: str | None = None  # "category_url" | "domain_inferred"
    inferred_section: str | None = None
    mode_detection_note: str | None = None

    # Target page context
    target_topic: str | None = None
    target_audience: str | None = None

    # Crawled content
    placement_page_crawl: object | None = None          # CrawlResult | None (Mode A)
    sampled_article_crawls: list = field(default_factory=list)   # list[CrawlResult] (Mode B)
    domain_sample_crawls: list = field(default_factory=list)     # list[CrawlResult] (both)
    sampled_article_urls: list[str] = field(default_factory=list)

    # Domain signals
    backlink_metrics: object | None = None  # BacklinkMetrics | None
    domain_metrics: object | None = None    # DomainMetrics | None

    # Errors accumulated during collection
    crawl_errors: list[str] = field(default_factory=list)

    @property
    def data_quality(self) -> dict:
        return {
            "mode_detected": self.mode is not None,
            "placement_page_crawled": self.placement_page_crawl is not None,
            "article_samples": len(self.sampled_article_crawls),
            "domain_samples": len(self.domain_sample_crawls),
            "backlink_metrics_available": self.backlink_metrics is not None,
            "domain_metrics_available": self.domain_metrics is not None,
            "section_inferred": self.inferred_section is not None,
        }
