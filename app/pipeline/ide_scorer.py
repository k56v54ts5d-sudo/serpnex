"""Deterministic Investment Decision Engine scoring (§3.5).

All functions are pure — no I/O, no LLM calls. Takes SignalScores (from LLM
Call 1) and IDEContext (domain metrics from providers) and returns a ScoreResult.
The outcome tier, investment score, and confidence ceiling are all determined
here. LLM Call 2 receives these results and translates them into language only.

Formulas reference: ide-implementation-design.md §7, intelligence-architecture §3.5."""

from __future__ import annotations

from app.providers.base.search_data import DomainMetrics
from app.schemas.opportunities import (
    ClusterScores,
    IDEContext,
    InvestmentOutcome,
    PlacementFeasibility,
    ScoreResult,
    SignalScores,
)

# ── Conversion tables ─────────────────────────────────────────────────────────

_TRAFFIC_TIER_TO_FLOAT = {
    "high": 0.90,
    "medium": 0.65,
    "low": 0.35,
    "minimal": 0.10,
    "unknown": 0.30,
}

_TRAFFIC_TRAJECTORY_TO_FLOAT = {
    "growing": 1.00,
    "stable": 0.80,
    "declining": 0.40,
    "unknown": 0.60,
}

_P5_TO_FLOAT = {
    PlacementFeasibility.NATURAL: 1.00,
    PlacementFeasibility.WORKABLE: 0.70,
    PlacementFeasibility.FORCED: 0.35,
    PlacementFeasibility.IMPLAUSIBLE: 0.00,
}

# Confidence ceiling by mode and sub-type
_CONFIDENCE_CEILING = {
    ("specific_placement", None): "high",
    ("guest_post_opportunity", "category_url"): "medium",
    ("guest_post_opportunity", "domain_inferred"): "low",
}


def compute_score(ctx: IDEContext, signals: SignalScores) -> ScoreResult:
    """Compute the full Investment Score and all cluster values from signals.

    Steps:
    1. Convert provider-supplied metrics to 0-1 floats (D2, D3, D7, D8)
    2. Convert P5 enum to float
    3. Compute Quality cluster (with D4 and P5 caps)
    4. Compute Relevance and Authority clusters
    5. Compute Risk cluster and Risk multiplier
    6. Apply Risk multiplier to Base Score → Investment Score
    7. Apply editorial integrity cap (D4 < 0.30 → Investment Score ≤ 45)
    8. Determine outcome tier
    9. Compute deterministic confidence
    10. Apply confidence ceiling (mode-based)
    """

    # ── Step 1: Convert domain signals to 0-1 floats ──────────────────────────
    dm: DomainMetrics | None = ctx.domain_metrics
    bm = ctx.backlink_metrics

    d2 = _referring_domains_to_float(bm.referring_domains if bm else None)
    d3_current = _TRAFFIC_TIER_TO_FLOAT.get(dm.traffic_tier if dm else "unknown", 0.30)
    d3_trend = _TRAFFIC_TRAJECTORY_TO_FLOAT.get(dm.traffic_trajectory if dm else "unknown", 0.60)
    d7 = dm.spam_risk if (dm and dm.spam_risk is not None) else 0.50
    d8 = _maturity_to_float(dm.maturity_years if dm else None)

    # ── Step 2: P5 float ──────────────────────────────────────────────────────
    p5_float = _P5_TO_FLOAT[signals.p5_placement_feasibility]
    p5_cap = signals.p5_placement_feasibility == PlacementFeasibility.IMPLAUSIBLE

    # ── Step 3: Quality cluster (with caps) ───────────────────────────────────
    d4 = signals.d4_editorial_integrity
    d5 = 0.50  # Domain size signal — not yet collected (insufficient_data default)
    d6 = 0.50  # Indexed ratio — not yet collected (insufficient_data default)

    quality_raw = (d4 * 0.35) + (signals.p4_obl_quality * 0.25) + (p5_float * 0.20) + (d5 * 0.10) + (d6 * 0.10)
    if d4 < 0.30:
        quality = min(quality_raw, 0.40)
    elif p5_cap:
        quality = min(quality_raw, 0.35)
    else:
        quality = quality_raw

    # ── Step 4: Relevance and Authority clusters ──────────────────────────────
    relevance = (
        (signals.p1_topical_relevance * 0.45)
        + (signals.d1_topical_coherence * 0.25)
        + (signals.d9_geo_language_match * 0.20)
        + (signals.language_match * 0.10)
    )

    authority = (
        (d3_current * 0.35)
        + (signals.p2_content_quality * 0.25)
        + (d2 * 0.25)
        + (d3_current * 0.15)   # D3_current used for both P3 proxy and D3_current
    )

    # ── Step 5: Risk cluster and multiplier ───────────────────────────────────
    risk_score = _compute_risk(d7, d3_trend, d8, signals.d1_topical_coherence, signals.p4_obl_quality)
    risk_multiplier = _risk_to_multiplier(risk_score)

    cluster_scores = ClusterScores(
        relevance=round(relevance, 4),
        authority=round(authority, 4),
        quality=round(quality, 4),
        risk=round(risk_score, 4),
        risk_multiplier=risk_multiplier,
    )

    # ── Step 6: Base Score → Investment Score ─────────────────────────────────
    base_score = (relevance * 0.35) + (authority * 0.30) + (quality * 0.35)
    investment_score = base_score * risk_multiplier * 100

    # ── Step 7: Editorial integrity cap ──────────────────────────────────────
    editorial_cap = d4 < 0.30
    if editorial_cap:
        investment_score = min(investment_score, 45.0)

    investment_score = round(investment_score, 2)

    # ── Step 8: Outcome tier ──────────────────────────────────────────────────
    outcome = _determine_outcome(investment_score, relevance, risk_multiplier, d4)

    # ── Step 9: Deterministic confidence ─────────────────────────────────────
    det_confidence = _compute_confidence(ctx, signals)

    # ── Step 10: Confidence ceiling ───────────────────────────────────────────
    ceiling_key = (ctx.mode, ctx.mode_b_subtype)
    ceiling = _CONFIDENCE_CEILING.get(ceiling_key, "low")
    final_confidence = _apply_ceiling(det_confidence, ceiling)

    return ScoreResult(
        cluster_scores=cluster_scores,
        investment_score=investment_score,
        editorial_integrity_cap_applied=editorial_cap,
        p5_cap_applied=p5_cap,
        deterministic_confidence=final_confidence,
        confidence_ceiling=ceiling,
        outcome=outcome,
    )


# ── Outcome tier determination ────────────────────────────────────────────────

def _determine_outcome(
    investment_score: float,
    relevance: float,
    risk_multiplier: float,
    d4: float,
) -> InvestmentOutcome:
    # Hard not_recommended conditions (any one triggers)
    if relevance < 0.30 or risk_multiplier < 0.55 or d4 < 0.30:
        return InvestmentOutcome.NOT_RECOMMENDED
    if investment_score < 48.0:
        return InvestmentOutcome.NOT_RECOMMENDED

    # Clean recommended: all conditions must pass
    if (
        investment_score >= 68.0
        and relevance >= 0.55
        and risk_multiplier >= 0.80
        and d4 >= 0.55
    ):
        return InvestmentOutcome.RECOMMENDED

    return InvestmentOutcome.WITH_CONDITIONS


# ── Risk scoring ──────────────────────────────────────────────────────────────

def _compute_risk(d7: float, d3_trend: float, d8: float, d1: float, p4: float) -> float:
    """Risk cluster: weighted average (60%) + minimum individual signal (40%)."""
    weights = [(d7, 0.30), (d3_trend, 0.25), (d8, 0.20), (d1, 0.15), (p4, 0.10)]
    weighted_avg = sum(score * weight for score, weight in weights)
    min_signal = min(score for score, _ in weights)
    return round((weighted_avg * 0.60) + (min_signal * 0.40), 4)


def _risk_to_multiplier(risk_score: float) -> float:
    if risk_score >= 0.75:
        return 1.00
    elif risk_score >= 0.55:
        return 0.80
    elif risk_score >= 0.35:
        return 0.55
    return 0.25


# ── Conversion helpers ────────────────────────────────────────────────────────

def _referring_domains_to_float(rd: int | None) -> float:
    """Convert referring domain count to a 0-1 authority signal."""
    if rd is None:
        return 0.30  # unknown — use partial default
    if rd >= 500:
        return 1.00
    elif rd >= 100:
        return 0.75
    elif rd >= 50:
        return 0.55
    elif rd >= 20:
        return 0.35
    elif rd >= 5:
        return 0.20
    return 0.05


def _maturity_to_float(years: float | None) -> float:
    """Convert domain age (years) to a 0-1 maturity signal."""
    if years is None:
        return 0.50
    if years >= 10:
        return 1.00
    elif years >= 5:
        return 0.80
    elif years >= 3:
        return 0.60
    elif years >= 1:
        return 0.40
    return 0.20


# ── Confidence scoring ────────────────────────────────────────────────────────

_CONFIDENCE_LEVELS = ["low", "medium", "high"]


def _compute_confidence(ctx: IDEContext, signals: SignalScores) -> str:
    """Deterministic confidence based on signal availability."""
    score = 0.0
    # Required signals (high weight)
    if ctx.placement_page_crawl is not None or ctx.sampled_article_crawls:
        score += 0.35
    if ctx.domain_metrics is not None:
        score += 0.25
    if ctx.backlink_metrics is not None:
        score += 0.20
    # Optional signals
    if ctx.domain_sample_crawls:
        score += 0.10
    if ctx.mode is not None:
        score += 0.10

    if score >= 0.80:
        return "high"
    elif score >= 0.55:
        return "medium"
    return "low"


def _apply_ceiling(confidence: str, ceiling: str) -> str:
    """Return the lower of computed confidence and mode-based ceiling."""
    order = {"low": 0, "medium": 1, "high": 2}
    if order[confidence] <= order[ceiling]:
        return confidence
    return ceiling
