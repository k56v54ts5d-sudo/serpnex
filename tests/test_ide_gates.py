"""Tests for hard exclusion gate evaluation (H1–H5)."""

import pytest
from dataclasses import dataclass, field
from unittest.mock import MagicMock

from app.pipeline.ide_gates import evaluate_gates
from app.schemas.opportunities import GateResult, HardExclusionGate, IDEContext


def _ctx(**kwargs) -> IDEContext:
    defaults = dict(
        prospect_url="https://example.com/article",
        prospect_domain="example.com",
    )
    defaults.update(kwargs)
    return IDEContext(**defaults)


def _metrics(
    traffic_tier="medium",
    traffic_trajectory="stable",
    spam_risk=0.80,
    referring_domains=50,
    maturity_years=5.0,
):
    m = MagicMock()
    m.traffic_tier = traffic_tier
    m.traffic_trajectory = traffic_trajectory
    m.spam_risk = spam_risk
    m.referring_domains = referring_domains
    m.maturity_years = maturity_years
    return m


def _backlinks(referring_domains=50):
    bm = MagicMock()
    bm.referring_domains = referring_domains
    return bm


def _crawl(title="Title", content="Some content here with enough words to pass", url="https://example.com/a"):
    c = MagicMock()
    c.title = title
    c.markdown = content
    c.url = url
    return c


class TestH3Malware:
    def test_triggers_when_spam_risk_is_zero(self):
        ctx = _ctx(domain_metrics=_metrics(spam_risk=0.0))
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H3_MALWARE

    def test_does_not_trigger_for_low_but_nonzero_spam_risk(self):
        ctx = _ctx(
            domain_metrics=_metrics(spam_risk=0.05),
            backlink_metrics=_backlinks(referring_domains=5),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_domain_metrics_missing(self):
        ctx = _ctx(domain_metrics=None)
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_for_clean_domain(self):
        ctx = _ctx(
            domain_metrics=_metrics(spam_risk=0.95),
            backlink_metrics=_backlinks(referring_domains=5),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered


class TestH1ProhibitedContent:
    def test_triggers_on_escort_keyword(self):
        crawl = _crawl(content="This site offers escort services in London")
        ctx = _ctx(domain_metrics=_metrics(spam_risk=0.80), placement_page_crawl=crawl)
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H1_PROHIBITED_CONTENT

    def test_triggers_on_adult_dating(self):
        crawl = _crawl(content="adult dating platform for singles")
        ctx = _ctx(domain_metrics=_metrics(), placement_page_crawl=crawl)
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H1_PROHIBITED_CONTENT

    def test_does_not_trigger_on_clean_content(self):
        crawl = _crawl(content="This is a comprehensive guide to SEO best practices.")
        ctx = _ctx(
            domain_metrics=_metrics(),
            backlink_metrics=_backlinks(),
            placement_page_crawl=crawl,
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_no_crawls_available(self):
        ctx = _ctx(domain_metrics=_metrics(spam_risk=0.90), backlink_metrics=_backlinks())
        result = evaluate_gates(ctx)
        assert not result.triggered


class TestH2Deindexed:
    def test_triggers_when_minimal_traffic_and_many_backlinks(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_tier="minimal"),
            backlink_metrics=_backlinks(referring_domains=25),
        )
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H2_DEINDEXED_PENALIZED

    def test_does_not_trigger_when_traffic_is_low_but_not_minimal(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_tier="low"),
            backlink_metrics=_backlinks(referring_domains=100),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_minimal_traffic_but_few_backlinks(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_tier="minimal"),
            backlink_metrics=_backlinks(referring_domains=5),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_backlinks_missing(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_tier="minimal"),
            backlink_metrics=None,
        )
        result = evaluate_gates(ctx)
        assert not result.triggered


class TestH4LanguageImpossible:
    def test_triggers_when_all_pages_use_cjk(self):
        crawls = [
            _crawl(content="一二三四五六七八九十 Chinese content here"),
            _crawl(content="一二三 More CJK content for another page"),
        ]
        ctx = _ctx(
            domain_metrics=_metrics(),
            backlink_metrics=_backlinks(),
            sampled_article_crawls=crawls,
        )
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H4_LANGUAGE_IMPOSSIBLE

    def test_does_not_trigger_when_only_one_crawl(self):
        crawls = [_crawl(content="一 CJK single page")]
        ctx = _ctx(
            domain_metrics=_metrics(),
            backlink_metrics=_backlinks(),
            sampled_article_crawls=crawls,
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_mixed_content(self):
        crawls = [
            _crawl(content="一二三 CJK content"),
            _crawl(content="This is an English article about SEO."),
        ]
        ctx = _ctx(
            domain_metrics=_metrics(),
            backlink_metrics=_backlinks(),
            sampled_article_crawls=crawls,
        )
        result = evaluate_gates(ctx)
        assert not result.triggered


class TestH5ManualAction:
    def test_triggers_on_declining_traffic_with_many_backlinks(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_trajectory="declining", spam_risk=0.70),
            backlink_metrics=_backlinks(referring_domains=60),
        )
        result = evaluate_gates(ctx)
        assert result.triggered
        assert result.gate == HardExclusionGate.H5_MANUAL_ACTION

    def test_does_not_trigger_when_backlinks_below_threshold(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_trajectory="declining", spam_risk=0.70),
            backlink_metrics=_backlinks(referring_domains=30),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_not_declining(self):
        ctx = _ctx(
            domain_metrics=_metrics(traffic_trajectory="stable", spam_risk=0.70),
            backlink_metrics=_backlinks(referring_domains=100),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered

    def test_does_not_trigger_when_domain_metrics_missing(self):
        ctx = _ctx(domain_metrics=None, backlink_metrics=_backlinks(referring_domains=100))
        result = evaluate_gates(ctx)
        assert not result.triggered


class TestGateOrdering:
    def test_h3_fires_before_h2(self):
        """H3 (spam) must fire even if H2 conditions are also met."""
        ctx = _ctx(
            domain_metrics=_metrics(traffic_tier="minimal", spam_risk=0.0),
            backlink_metrics=_backlinks(referring_domains=25),
        )
        result = evaluate_gates(ctx)
        assert result.gate == HardExclusionGate.H3_MALWARE

    def test_no_gates_triggered_for_clean_domain(self):
        ctx = _ctx(
            domain_metrics=_metrics(),
            backlink_metrics=_backlinks(referring_domains=50),
            placement_page_crawl=_crawl(content="Technical SEO guide for practitioners."),
        )
        result = evaluate_gates(ctx)
        assert not result.triggered
        assert result.gate is None
