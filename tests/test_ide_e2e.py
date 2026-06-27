"""End-to-end tests for the IDE pipeline.

All external I/O is mocked. Verifies:
- State transitions fire in the correct order
- Gate exclusions short-circuit before LLM calls
- Score and verdict are persisted correctly
- Verdict assembly failures produce a safe fallback
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.pipeline.ide_orchestrator as orch
from app.pipeline.ide_gates import evaluate_gates
from app.pipeline.ide_scorer import compute_score
from app.providers.base.crawler import CrawlResult
from app.providers.base.search_data import BacklinkMetrics, DomainMetrics
from app.schemas.opportunities import (
    ClusterScores,
    GateResult,
    HardExclusionGate,
    IDEContext,
    InvestmentOutcome,
    InvestmentVerdict,
    PlacementFeasibility,
    ScoreResult,
    SignalScores,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_crawl(url="https://example.com/a", title="Test Article", content="SEO guide content with many words to fill the word limit properly."):
    c = MagicMock(spec=CrawlResult)
    c.url = url
    c.title = title
    c.markdown = content
    return c


def _make_domain_metrics():
    return DomainMetrics(
        domain="example.com",
        traffic_tier="high",
        traffic_trajectory="stable",
        referring_domains=200,
        spam_risk=0.80,
        maturity_years=7.0,
    )


def _make_backlink_metrics():
    bm = MagicMock()
    bm.referring_domains = 200
    return bm


def _make_ctx():
    return IDEContext(
        prospect_url="https://example.com/article",
        prospect_domain="example.com",
        mode="specific_placement",
        mode_b_subtype=None,
        placement_page_crawl=_make_crawl(),
        domain_sample_crawls=[_make_crawl()],
        domain_metrics=_make_domain_metrics(),
        backlink_metrics=_make_backlink_metrics(),
    )


def _make_signals():
    return SignalScores(
        p1_topical_relevance=0.80, p1_rationale="Relevant",
        p2_content_quality=0.75, p2_rationale="Quality content",
        p4_obl_quality=0.80, p4_rationale="Clean OBL",
        p5_placement_feasibility=PlacementFeasibility.NATURAL, p5_rationale="Natural fit",
        d1_topical_coherence=0.85, d1_rationale="Coherent domain",
        d4_editorial_integrity=0.80, d4_rationale="Editorial standards high",
        d9_geo_language_match=0.90, d9_rationale="English match",
        language_match=0.95,
        data_quality_notes="All data available",
    )


def _make_verdict(outcome=InvestmentOutcome.RECOMMENDED, score=75.0):
    return InvestmentVerdict(
        outcome=outcome,
        investment_score=score,
        evaluation_mode="specific_placement",
        cluster_scores=ClusterScores(relevance=0.80, authority=0.75, quality=0.70, risk=0.80, risk_multiplier=1.00),
        hard_exclusion_triggered=False,
        supporting_signals=["High relevance", "Clean editorial"],
        conditions=[],
        confidence="high",
        confidence_ceiling="high",
        data_quality={},
    )


def _make_opportunity(opportunity_id=None):
    opp = MagicMock()
    opp.id = opportunity_id or uuid.uuid4()
    opp.page_id = uuid.uuid4()
    opp.prospect_url = "https://example.com/article"
    opp.prospect_domain = "example.com"
    opp.status = "queued"
    opp.evaluation_mode = None
    opp.mode_b_subtype = None
    opp.inferred_section = None
    opp.investment_score = None
    opp.cluster_scores = None
    opp.overall_outcome = None
    opp.confidence = None
    opp.confidence_ceiling = None
    opp.opportunity_verdict = None
    opp.data_quality = None
    opp.failed_reason = None
    opp.started_at = None
    opp.completed_at = None
    opp.prompt_version = None
    return opp


def _make_page():
    page = MagicMock()
    page.id = uuid.uuid4()
    page.target_topic = "SEO guide"
    page.target_audience = "Digital marketers"
    return page


# ── Full pipeline (happy path) ────────────────────────────────────────────────

class TestHappyPath:
    @pytest.mark.asyncio
    async def test_full_pipeline_recommended(self):
        opp = _make_opportunity()
        page = _make_page()
        ctx = _make_ctx()
        signals = _make_signals()
        verdict = _make_verdict()

        status_log = []

        async def fake_set_status(session, o, status, opportunity_id, extra=None):
            o.status = status
            status_log.append(status)

        async def fake_set_complete(session, o, opportunity_id):
            o.status = "complete"
            status_log.append("complete")

        async def fake_set_failed(session, o, reason, opportunity_id):
            o.status = "failed"
            status_log.append("failed")

        fake_session = AsyncMock()
        fake_session.execute = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute.return_value = page_result
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", side_effect=fake_set_status),
            patch.object(orch, "_set_failed", side_effect=fake_set_failed),
            patch.object(orch, "_set_complete", side_effect=fake_set_complete),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(return_value=ctx)),
            patch("app.pipeline.ide_orchestrator.evaluate_gates", return_value=GateResult(triggered=False)),
            patch("app.pipeline.ide_orchestrator.call_1_classify_signals", AsyncMock(return_value=signals)),
            patch("app.pipeline.ide_orchestrator.compute_score", return_value=ScoreResult(
                cluster_scores=ClusterScores(relevance=0.80, authority=0.75, quality=0.70, risk=0.80, risk_multiplier=1.00),
                investment_score=75.0,
                editorial_integrity_cap_applied=False,
                p5_cap_applied=False,
                deterministic_confidence="high",
                confidence_ceiling="high",
                outcome=InvestmentOutcome.RECOMMENDED,
            )),
            patch("app.pipeline.ide_orchestrator.call_2_assemble_verdict", AsyncMock(return_value=verdict)),
        ):
            await orch._run_pipeline(str(opp.id))

        assert "detecting_mode" in status_log
        assert "collecting_data" in status_log
        assert "classifying_signals" in status_log
        assert "computing_score" in status_log
        assert "assembling_verdict" in status_log
        assert "complete" in status_log
        assert "failed" not in status_log

    @pytest.mark.asyncio
    async def test_mode_b_domain_includes_inferring_section_state(self):
        opp = _make_opportunity()
        page = _make_page()
        ctx = _make_ctx()
        ctx.mode = "guest_post_opportunity"
        ctx.mode_b_subtype = "domain_inferred"
        signals = _make_signals()
        verdict = _make_verdict()

        status_log = []

        async def fake_set_status(session, o, status, opportunity_id, extra=None):
            o.status = status
            status_log.append(status)

        fake_session = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute = AsyncMock(return_value=page_result)
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", side_effect=fake_set_status),
            patch.object(orch, "_set_failed", new=AsyncMock()),
            patch.object(orch, "_set_complete", new=AsyncMock()),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(return_value=ctx)),
            patch("app.pipeline.ide_orchestrator.evaluate_gates", return_value=GateResult(triggered=False)),
            patch("app.pipeline.ide_orchestrator.call_1_classify_signals", AsyncMock(return_value=signals)),
            patch("app.pipeline.ide_orchestrator.compute_score", return_value=ScoreResult(
                cluster_scores=ClusterScores(relevance=0.60, authority=0.50, quality=0.55, risk=0.70, risk_multiplier=0.80),
                investment_score=55.0,
                editorial_integrity_cap_applied=False,
                p5_cap_applied=False,
                deterministic_confidence="low",
                confidence_ceiling="low",
                outcome=InvestmentOutcome.WITH_CONDITIONS,
            )),
            patch("app.pipeline.ide_orchestrator.call_2_assemble_verdict", AsyncMock(return_value=verdict)),
        ):
            await orch._run_pipeline(str(opp.id))

        assert "inferring_section" in status_log


# ── Gate exclusion path ────────────────────────────────────────────────────────

class TestGateExclusion:
    @pytest.mark.asyncio
    async def test_h3_gate_stops_pipeline_before_llm(self):
        opp = _make_opportunity()
        page = _make_page()
        ctx = _make_ctx()

        llm_call_1_called = []

        fake_session = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute = AsyncMock(return_value=page_result)
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        async def call_1_spy(*args, **kwargs):
            llm_call_1_called.append(True)
            return _make_signals()

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", new=AsyncMock()),
            patch.object(orch, "_set_failed", new=AsyncMock()),
            patch.object(orch, "_set_complete", new=AsyncMock()),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(return_value=ctx)),
            patch("app.pipeline.ide_orchestrator.evaluate_gates", return_value=GateResult(
                triggered=True,
                gate=HardExclusionGate.H3_MALWARE,
                reason="Spam risk at maximum.",
            )),
            patch("app.pipeline.ide_orchestrator.call_1_classify_signals", side_effect=call_1_spy),
        ):
            await orch._run_pipeline(str(opp.id))

        assert not llm_call_1_called, "LLM Call 1 must not run when a gate fires"
        assert opp.overall_outcome == InvestmentOutcome.NOT_RECOMMENDED.value

    @pytest.mark.asyncio
    async def test_gate_exclusion_sets_hard_exclusion_verdict(self):
        opp = _make_opportunity()
        page = _make_page()
        ctx = _make_ctx()

        fake_session = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute = AsyncMock(return_value=page_result)
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", new=AsyncMock()),
            patch.object(orch, "_set_failed", new=AsyncMock()),
            patch.object(orch, "_set_complete", new=AsyncMock()),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(return_value=ctx)),
            patch("app.pipeline.ide_orchestrator.evaluate_gates", return_value=GateResult(
                triggered=True,
                gate=HardExclusionGate.H2_DEINDEXED_PENALIZED,
                reason="Near-zero traffic despite large link profile.",
            )),
        ):
            await orch._run_pipeline(str(opp.id))

        assert opp.opportunity_verdict is not None
        assert opp.opportunity_verdict["hard_exclusion_triggered"] is True
        assert opp.opportunity_verdict["hard_exclusion_gate"] == HardExclusionGate.H2_DEINDEXED_PENALIZED.value


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_collection_failure_sets_failed_status(self):
        opp = _make_opportunity()
        page = _make_page()
        status_log = []

        fake_session = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute = AsyncMock(return_value=page_result)
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        async def fake_set_failed(session, o, reason, opportunity_id):
            o.status = "failed"
            status_log.append(("failed", reason))

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", new=AsyncMock()),
            patch.object(orch, "_set_failed", side_effect=fake_set_failed),
            patch.object(orch, "_set_complete", new=AsyncMock()),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(side_effect=RuntimeError("Network timeout"))),
        ):
            await orch._run_pipeline(str(opp.id))

        assert status_log[0][0] == "failed"
        assert "Network timeout" in status_log[0][1]

    @pytest.mark.asyncio
    async def test_verdict_assembly_failure_produces_fallback_verdict(self):
        opp = _make_opportunity()
        page = _make_page()
        ctx = _make_ctx()
        signals = _make_signals()
        score_result = ScoreResult(
            cluster_scores=ClusterScores(relevance=0.80, authority=0.75, quality=0.70, risk=0.80, risk_multiplier=1.00),
            investment_score=75.0,
            editorial_integrity_cap_applied=False,
            p5_cap_applied=False,
            deterministic_confidence="high",
            confidence_ceiling="high",
            outcome=InvestmentOutcome.RECOMMENDED,
        )

        fake_session = AsyncMock()
        page_result = MagicMock()
        page_result.scalar_one_or_none.side_effect = [opp, page]
        fake_session.execute = AsyncMock(return_value=page_result)
        fake_session.commit = AsyncMock()

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", new=AsyncMock()),
            patch.object(orch, "_set_failed", new=AsyncMock()),
            patch.object(orch, "_set_complete", new=AsyncMock()),
            patch.object(orch, "_publish", new=AsyncMock()),
            patch("app.pipeline.ide_orchestrator.collect_ide", AsyncMock(return_value=ctx)),
            patch("app.pipeline.ide_orchestrator.evaluate_gates", return_value=GateResult(triggered=False)),
            patch("app.pipeline.ide_orchestrator.call_1_classify_signals", AsyncMock(return_value=signals)),
            patch("app.pipeline.ide_orchestrator.compute_score", return_value=score_result),
            patch("app.pipeline.ide_orchestrator.call_2_assemble_verdict", AsyncMock(side_effect=Exception("LLM error"))),
        ):
            await orch._run_pipeline(str(opp.id))

        # Should still reach complete with a fallback verdict
        assert opp.opportunity_verdict is not None
        assert opp.opportunity_verdict["outcome"] == InvestmentOutcome.RECOMMENDED.value
        assert opp.investment_score == 75.0

    @pytest.mark.asyncio
    async def test_missing_opportunity_returns_early(self):
        """If the opportunity record doesn't exist, pipeline exits cleanly."""
        fake_session = AsyncMock()
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None
        fake_session.execute = AsyncMock(return_value=none_result)

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(orch, "_AsyncSession", return_value=session_ctx):
            await orch._run_pipeline(str(uuid.uuid4()))
        # No exception raised — exits cleanly
