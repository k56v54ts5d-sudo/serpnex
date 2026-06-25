"""Tests for the deterministic confidence scoring model (§8)."""

import pytest

from app.pipeline.confidence import (
    SignalStatus,
    apply_confidence_floors,
    calculate_confidence,
)

A = SignalStatus.AVAILABLE
P = SignalStatus.PARTIAL
M = SignalStatus.MISSING


class TestCalculateConfidence:
    def test_all_signals_available_readiness_returns_high(self):
        signals = {
            "page_crawl_success": A,
            "gsc_data": A,
            "page_indexed": A,
            "internal_link_data": A,
        }
        assert calculate_confidence(signals, "readiness") == "high"

    def test_missing_gsc_readiness_returns_medium(self):
        signals = {
            "page_crawl_success": A,
            "gsc_data": M,
            "page_indexed": A,
            "internal_link_data": A,
        }
        # Score: 0.25 + 0 + 0.20 + 0.25 = 0.70 → medium
        assert calculate_confidence(signals, "readiness") == "medium"

    def test_all_missing_readiness_returns_low(self):
        signals = {
            "page_crawl_success": M,
            "gsc_data": M,
            "page_indexed": M,
            "internal_link_data": M,
        }
        assert calculate_confidence(signals, "readiness") == "low"

    def test_partial_signals_score_half_weight(self):
        signals = {
            "page_crawl_success": A,
            "gsc_data": P,    # 0.30 * 0.5 = 0.15
            "page_indexed": A,
            "internal_link_data": A,
        }
        # Score: 0.25 + 0.15 + 0.20 + 0.25 = 0.85 → high
        result = calculate_confidence(signals, "readiness")
        assert result == "high"

    def test_all_bottleneck_signals_available_returns_high(self):
        signals = {
            "gsc_keyword_data": A,
            "competitor_crawls": A,
            "target_backlink_data": A,
            "competitor_backlink_data": A,
            "serp_results": A,
        }
        assert calculate_confidence(signals, "bottleneck") == "high"

    def test_missing_backlinks_bottleneck_medium(self):
        signals = {
            "gsc_keyword_data": A,
            "competitor_crawls": A,
            "target_backlink_data": M,
            "competitor_backlink_data": M,
            "serp_results": A,
        }
        # Score: 0.25 + 0.25 + 0 + 0 + 0.10 = 0.60 → medium
        assert calculate_confidence(signals, "bottleneck") == "medium"

    def test_unknown_module_returns_low(self):
        signals = {"page_crawl_success": A}
        assert calculate_confidence(signals, "unknown_module") == "low"


class TestApplyConfidenceFloors:
    def _floors(self, confidence, **kwargs):
        defaults = dict(
            gsc_connected=True,
            backlink_data_available=True,
            competitor_count=3,
            page_crawl_success=True,
            page_age_days=None,
            module="readiness",
        )
        defaults.update(kwargs)
        return apply_confidence_floors(confidence, **defaults)

    def test_no_overrides_returns_original(self):
        result, overrides = self._floors("high")
        assert result == "high"
        assert overrides == []

    def test_gsc_not_connected_floors_high_to_medium(self):
        result, overrides = self._floors("high", gsc_connected=False)
        assert result == "medium"
        assert "gsc_not_connected" in overrides

    def test_gsc_not_connected_does_not_raise_low(self):
        result, overrides = self._floors("low", gsc_connected=False)
        assert result == "low"

    def test_page_crawl_failed_floors_to_low(self):
        result, overrides = self._floors("high", page_crawl_success=False)
        assert result == "low"
        assert "page_crawl_failed" in overrides

    def test_bottleneck_no_backlinks_floors_to_low(self):
        result, overrides = self._floors("high", backlink_data_available=False, module="bottleneck")
        assert result == "low"

    def test_bottleneck_insufficient_competitors_floors_to_medium(self):
        result, overrides = self._floors("high", competitor_count=1, module="bottleneck")
        assert result == "medium"
        assert "insufficient_competitors" in overrides

    def test_readiness_page_too_new_floors_to_low(self):
        result, overrides = self._floors("high", page_age_days=10, module="readiness")
        assert result == "low"
        assert "page_too_new" in overrides

    def test_multiple_overrides_applied_sequentially(self):
        result, overrides = self._floors(
            "high",
            gsc_connected=False,
            page_crawl_success=False,
        )
        assert result == "low"
        assert len(overrides) >= 1
