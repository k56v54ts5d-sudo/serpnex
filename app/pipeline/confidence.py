"""Deterministic confidence scoring model (§8).

Confidence is a data sufficiency score, not an ML probability. It is computed
from signal availability weights defined per module. The LLM's self-reported
confidence is stored for audit but never used as the final value."""

from __future__ import annotations

from enum import Enum


class SignalStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"


# Signal weights per module (§8.3)
_READINESS_WEIGHTS: dict[str, float] = {
    "page_crawl_success": 0.25,
    "gsc_data": 0.30,
    "page_indexed": 0.20,
    "internal_link_data": 0.25,
}

_BOTTLENECK_WEIGHTS: dict[str, float] = {
    "gsc_keyword_data": 0.25,
    "competitor_crawls": 0.25,
    "target_backlink_data": 0.20,
    "competitor_backlink_data": 0.20,
    "serp_results": 0.10,
}

_WEIGHTS_BY_MODULE = {
    "readiness": _READINESS_WEIGHTS,
    "bottleneck": _BOTTLENECK_WEIGHTS,
}


def calculate_confidence(
    signals: dict[str, SignalStatus],
    module: str,
) -> str:
    """Compute confidence level from signal availability.

    Returns 'high', 'medium', or 'low'. Always returns a value — never raises."""
    weights = _WEIGHTS_BY_MODULE.get(module, {})
    score = 0.0
    for signal, status in signals.items():
        weight = weights.get(signal, 0.0)
        if status == SignalStatus.AVAILABLE:
            score += weight * 1.0
        elif status == SignalStatus.PARTIAL:
            score += weight * 0.5
        # MISSING contributes 0

    if score >= 0.80:
        return "high"
    elif score >= 0.55:
        return "medium"
    return "low"


def apply_confidence_floors(
    confidence: str,
    *,
    gsc_connected: bool,
    backlink_data_available: bool,
    competitor_count: int,
    page_crawl_success: bool,
    page_age_days: int | None,
    module: str,
) -> tuple[str, list[str]]:
    """Apply deterministic confidence floor rules (§7.4).

    Returns the final confidence and a list of override reasons applied.
    These rules override the LLM self-report regardless of the score."""
    overrides: list[str] = []

    _FLOOR_ORDER = {"low": 0, "medium": 1, "high": 2}

    def _floor(current: str, limit: str, reason: str) -> str:
        if _FLOOR_ORDER[current] > _FLOOR_ORDER[limit]:
            overrides.append(reason)
            return limit
        return current

    if not page_crawl_success:
        confidence = _floor(confidence, "low", "page_crawl_failed")

    if not gsc_connected:
        confidence = _floor(confidence, "medium", "gsc_not_connected")

    if module == "bottleneck":
        if not backlink_data_available:
            confidence = _floor(confidence, "low", "backlink_data_unavailable")
        if competitor_count < 2:
            confidence = _floor(confidence, "medium", "insufficient_competitors")

    if module == "readiness" and page_age_days is not None and page_age_days < 30:
        confidence = _floor(confidence, "low", "page_too_new")

    return confidence, overrides
