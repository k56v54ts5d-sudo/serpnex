"""Tests for the Investment Decision Engine deterministic scorer."""

import pytest
from unittest.mock import MagicMock

from app.pipeline.ide_scorer import (
    _apply_ceiling,
    _compute_confidence,
    _compute_risk,
    _determine_outcome,
    _maturity_to_float,
    _referring_domains_to_float,
    _risk_to_multiplier,
    compute_score,
)
from app.schemas.opportunities import IDEContext, InvestmentOutcome, PlacementFeasibility, SignalScores


def _signals(**overrides) -> SignalScores:
    defaults = dict(
        p1_topical_relevance=0.80,
        p1_rationale="Highly relevant topic.",
        p2_content_quality=0.75,
        p2_rationale="Well-written content.",
        p4_obl_quality=0.80,
        p4_rationale="Clean outbound links.",
        p5_placement_feasibility=PlacementFeasibility.NATURAL,
        p5_rationale="Fits naturally.",
        d1_topical_coherence=0.85,
        d1_rationale="Coherent domain.",
        d4_editorial_integrity=0.80,
        d4_rationale="High editorial standards.",
        d9_geo_language_match=0.90,
        d9_rationale="English / US match.",
        language_match=0.95,
        data_quality_notes="All data available.",
    )
    defaults.update(overrides)
    return SignalScores(**defaults)


def _domain_metrics(
    traffic_tier="high",
    traffic_trajectory="stable",
    spam_risk=0.80,
    referring_domains=200,
    maturity_years=7.0,
):
    m = MagicMock()
    m.traffic_tier = traffic_tier
    m.traffic_trajectory = traffic_trajectory
    m.spam_risk = spam_risk
    m.referring_domains = referring_domains
    m.maturity_years = maturity_years
    return m


def _backlinks(referring_domains=200):
    b = MagicMock()
    b.referring_domains = referring_domains
    return b


def _ctx(**overrides) -> IDEContext:
    defaults = dict(
        prospect_url="https://example.com/article",
        prospect_domain="example.com",
        mode="specific_placement",
        mode_b_subtype=None,
        domain_metrics=_domain_metrics(),
        backlink_metrics=_backlinks(),
        placement_page_crawl=MagicMock(),
        domain_sample_crawls=[MagicMock()],
    )
    defaults.update(overrides)
    return IDEContext(**defaults)


# ── Conversion helpers ────────────────────────────────────────────────────────

class TestReferringDomainsToFloat:
    def test_500_plus(self):
        assert _referring_domains_to_float(600) == 1.00

    def test_100_to_499(self):
        assert _referring_domains_to_float(150) == 0.75

    def test_50_to_99(self):
        assert _referring_domains_to_float(70) == 0.55

    def test_20_to_49(self):
        assert _referring_domains_to_float(30) == 0.35

    def test_5_to_19(self):
        assert _referring_domains_to_float(10) == 0.20

    def test_below_5(self):
        assert _referring_domains_to_float(2) == 0.05

    def test_none_returns_default(self):
        assert _referring_domains_to_float(None) == 0.30


class TestMaturityToFloat:
    def test_10_plus_years(self):
        assert _maturity_to_float(12.0) == 1.00

    def test_5_to_9_years(self):
        assert _maturity_to_float(7.0) == 0.80

    def test_3_to_4_years(self):
        assert _maturity_to_float(3.5) == 0.60

    def test_1_to_2_years(self):
        assert _maturity_to_float(1.5) == 0.40

    def test_under_1_year(self):
        assert _maturity_to_float(0.5) == 0.20

    def test_none_returns_default(self):
        assert _maturity_to_float(None) == 0.50


# ── Risk scoring ──────────────────────────────────────────────────────────────

class TestComputeRisk:
    def test_high_signals_produce_high_risk_score(self):
        score = _compute_risk(
            d7=0.90, d3_trend=0.80, d8=1.00, d1=0.85, p4=0.80
        )
        assert score >= 0.80

    def test_low_min_signal_drags_down_risk(self):
        # One very low signal should reduce the risk score significantly
        score_low = _compute_risk(d7=0.90, d3_trend=0.80, d8=0.10, d1=0.85, p4=0.80)
        score_high = _compute_risk(d7=0.90, d3_trend=0.80, d8=0.90, d1=0.85, p4=0.80)
        assert score_low < score_high

    def test_all_signals_low_produces_low_score(self):
        score = _compute_risk(d7=0.10, d3_trend=0.20, d8=0.15, d1=0.10, p4=0.10)
        assert score <= 0.20


class TestRiskToMultiplier:
    def test_high_risk_returns_1(self):
        assert _risk_to_multiplier(0.80) == 1.00

    def test_medium_high_risk_returns_0_80(self):
        assert _risk_to_multiplier(0.60) == 0.80

    def test_medium_low_risk_returns_0_55(self):
        assert _risk_to_multiplier(0.40) == 0.55

    def test_low_risk_returns_0_25(self):
        assert _risk_to_multiplier(0.20) == 0.25

    def test_boundary_at_0_55(self):
        assert _risk_to_multiplier(0.55) == 0.80

    def test_boundary_at_0_75(self):
        assert _risk_to_multiplier(0.75) == 1.00


# ── Outcome determination ─────────────────────────────────────────────────────

class TestDetermineOutcome:
    def test_recommended_when_all_conditions_pass(self):
        outcome = _determine_outcome(
            investment_score=75.0, relevance=0.70, risk_multiplier=0.85, d4=0.70
        )
        assert outcome == InvestmentOutcome.RECOMMENDED

    def test_not_recommended_when_relevance_too_low(self):
        outcome = _determine_outcome(
            investment_score=70.0, relevance=0.25, risk_multiplier=0.85, d4=0.70
        )
        assert outcome == InvestmentOutcome.NOT_RECOMMENDED

    def test_not_recommended_when_d4_too_low(self):
        outcome = _determine_outcome(
            investment_score=70.0, relevance=0.70, risk_multiplier=0.85, d4=0.25
        )
        assert outcome == InvestmentOutcome.NOT_RECOMMENDED

    def test_not_recommended_when_risk_multiplier_too_low(self):
        outcome = _determine_outcome(
            investment_score=70.0, relevance=0.70, risk_multiplier=0.40, d4=0.70
        )
        assert outcome == InvestmentOutcome.NOT_RECOMMENDED

    def test_not_recommended_when_score_below_48(self):
        outcome = _determine_outcome(
            investment_score=45.0, relevance=0.70, risk_multiplier=0.80, d4=0.70
        )
        assert outcome == InvestmentOutcome.NOT_RECOMMENDED

    def test_with_conditions_between_48_and_68(self):
        outcome = _determine_outcome(
            investment_score=58.0, relevance=0.60, risk_multiplier=0.80, d4=0.60
        )
        assert outcome == InvestmentOutcome.WITH_CONDITIONS


# ── Confidence ceiling ────────────────────────────────────────────────────────

class TestApplyCeiling:
    def test_high_does_not_exceed_ceiling(self):
        assert _apply_ceiling("high", "medium") == "medium"

    def test_low_stays_low_even_with_high_ceiling(self):
        assert _apply_ceiling("low", "high") == "low"

    def test_same_level_unchanged(self):
        assert _apply_ceiling("medium", "medium") == "medium"

    def test_high_ceiling_allows_high_confidence(self):
        assert _apply_ceiling("high", "high") == "high"


# ── Full scorer integration ───────────────────────────────────────────────────

class TestComputeScore:
    def test_strong_domain_produces_recommended_outcome(self):
        ctx = _ctx()
        signals = _signals()
        result = compute_score(ctx, signals)
        assert result.outcome == InvestmentOutcome.RECOMMENDED
        assert result.investment_score >= 68.0

    def test_editorial_integrity_cap_applied_when_d4_below_30(self):
        ctx = _ctx()
        signals = _signals(d4_editorial_integrity=0.20)
        result = compute_score(ctx, signals)
        assert result.editorial_integrity_cap_applied
        assert result.investment_score <= 45.0
        assert result.outcome == InvestmentOutcome.NOT_RECOMMENDED

    def test_p5_implausible_caps_quality_cluster(self):
        ctx = _ctx()
        signals = _signals(
            p5_placement_feasibility=PlacementFeasibility.IMPLAUSIBLE,
            d4_editorial_integrity=0.80,
        )
        result = compute_score(ctx, signals)
        assert result.p5_cap_applied
        assert result.cluster_scores.quality <= 0.35

    def test_confidence_ceiling_applied_for_mode_b_domain(self):
        ctx = _ctx(
            mode="guest_post_opportunity",
            mode_b_subtype="domain_inferred",
            placement_page_crawl=None,
            sampled_article_crawls=[MagicMock()],
        )
        signals = _signals()
        result = compute_score(ctx, signals)
        assert result.confidence_ceiling == "low"
        assert result.deterministic_confidence == "low"

    def test_missing_domain_metrics_reduces_confidence(self):
        ctx = _ctx(domain_metrics=None, backlink_metrics=None)
        signals = _signals()
        result = compute_score(ctx, signals)
        # Without domain_metrics (0.25) and backlinks (0.20), max score is 0.55
        assert result.deterministic_confidence in ("low", "medium")

    def test_cluster_scores_are_between_0_and_1(self):
        ctx = _ctx()
        signals = _signals()
        result = compute_score(ctx, signals)
        cs = result.cluster_scores
        for val in [cs.relevance, cs.authority, cs.quality, cs.risk, cs.risk_multiplier]:
            assert 0.0 <= val <= 1.0

    def test_investment_score_is_between_0_and_100(self):
        ctx = _ctx()
        signals = _signals()
        result = compute_score(ctx, signals)
        assert 0.0 <= result.investment_score <= 100.0
