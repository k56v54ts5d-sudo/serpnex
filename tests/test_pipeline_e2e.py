"""End-to-end integration test for the analysis pipeline (§3).

Runs the full _run_pipeline() coroutine with all external dependencies
mocked. Verifies every state transition fires in order and that the
final DB record has the expected fields populated."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import Page, PageAnalysis
from app.pipeline.collectors import AnalysisContext
from app.providers.base.crawler import CrawlResult
from app.providers.base.gsc import GSCKeywordRow, GSCPageMetrics
from app.providers.base.search_data import BacklinkMetrics, OrganicResult, SerpResult
from app.schemas.verdicts import (
    BottleneckCategory,
    BottleneckVerdict,
    Confidence,
    ConstraintBreakdown,
    ConstraintSeverity,
    Priority,
    ReadinessDimension,
    ReadinessOutcome,
    ReadinessVerdict,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_crawl_result(url: str = "https://example.com/seo-guide") -> CrawlResult:
    return CrawlResult(
        url=url,
        status_code=200,
        markdown="# SEO Guide\n\n## Section One\n\n" + ("word " * 500),
        html="<h1>SEO Guide</h1>",
        title="SEO Guide",
        meta_description="A complete guide to SEO.",
    )


def _make_analysis_context() -> AnalysisContext:
    crawl = _make_crawl_result()
    competitor_crawl = _make_crawl_result("https://competitor.com/seo")
    return AnalysisContext(
        page_url="https://example.com/seo-guide",
        page_crawl=crawl,
        gsc_metrics=GSCPageMetrics(
            url="https://example.com/seo-guide",
            keywords=[
                GSCKeywordRow(keyword="seo guide", clicks=50, impressions=1000, ctr=0.05, position=8.2)
            ],
            total_clicks=50,
            total_impressions=1000,
        ),
        gsc_connected=True,
        serp_result=SerpResult(
            keyword="seo guide",
            total_results=10_000_000,
            organic=[
                OrganicResult(position=1, url="https://competitor.com/seo", title="Best SEO Guide", description=None),
                OrganicResult(position=2, url="https://other.com/seo", title="SEO Guide 2024", description=None),
            ],
        ),
        primary_keyword="seo guide",
        competitor_crawls=[competitor_crawl],
        competitor_urls=["https://competitor.com/seo"],
        target_backlinks=BacklinkMetrics(url="https://example.com/seo-guide", referring_domains=5, domain_rating=22.0, spam_score=0.02),
        competitor_backlinks=[
            BacklinkMetrics(url="https://competitor.com/seo", referring_domains=85, domain_rating=60.0, spam_score=0.01)
        ],
    )


def _make_readiness_verdict() -> ReadinessVerdict:
    return ReadinessVerdict(
        outcome=ReadinessOutcome.READY,
        confidence=Confidence.MEDIUM,
        confidence_rationale="GSC data available; internal link data unavailable.",
        headline="Page is ready to receive link investment.",
        dimensions={
            "content_sufficiency": ReadinessDimension(passed=True, severity="low", reason="500+ words covering the topic."),
            "intent_alignment": ReadinessDimension(passed=True, severity="low", reason="Guide format matches informational intent."),
            "indexing": ReadinessDimension(passed=True, severity="low", reason="Page is crawlable and returns 200."),
            "internal_authority": ReadinessDimension(passed=True, severity="low", reason="Internal links assumed adequate."),
        },
        actions=["Build authoritative links from topically relevant sites."],
        data_quality={"page_crawled": True, "gsc_connected": True},
    )


def _make_bottleneck_verdict() -> BottleneckVerdict:
    return BottleneckVerdict(
        primary_constraint=BottleneckCategory.LINK_AUTHORITY,
        primary_severity=ConstraintSeverity.SIGNIFICANT,
        links_are_the_answer=True,
        headline="80 referring domain gap vs top competitor is the primary ranking barrier.",
        competitive_context="Target has 5 RDs; top competitor has 85 RDs for the same keyword.",
        constraint_breakdown=[
            ConstraintBreakdown(
                category=BottleneckCategory.LINK_AUTHORITY,
                severity=ConstraintSeverity.SIGNIFICANT,
                weight=0.85,
                reason="Target sits at position 8 with 5 RDs; competitor at position 1 with 85 RDs.",
            ),
            ConstraintBreakdown(
                category=BottleneckCategory.CONTENT_DEPTH,
                severity=ConstraintSeverity.MILD,
                weight=0.15,
                reason="Minor content depth gap; not the primary constraint.",
            ),
        ],
        recommended_action="Acquire 15–20 high-authority referring domains from SEO-adjacent publications.",
        recommended_action_priority=Priority.HIGH,
        confidence=Confidence.MEDIUM,
        confidence_rationale="GSC and backlink data available; internal link data missing.",
        data_quality={"gsc_data": True, "target_backlinks": True},
        authority_gap_rds=80,
        content_gap_words=None,
    )


def _make_summaries_dict() -> dict:
    return {
        "target": {
            "topic_and_angle": "A comprehensive guide to SEO fundamentals for beginners.",
            "format_label": "guide",
            "heading_structure": "H1 + 1 H2 subheading covering SEO basics.",
            "intent_alignment": "Informational intent — guide format is well matched.",
            "notable_elements": ["Numbered steps", "Definition list"],
            "visible_content_gaps": ["No case studies", "No data tables"],
        },
        "competitors": [],
        "prompt_version": "summarize-page/v1",
    }


# ── Fake DB session ───────────────────────────────────────────────────────────

class _FakeSession:
    """Minimal async SQLAlchemy session substitute."""

    def __init__(self, analysis: PageAnalysis, page: Page) -> None:
        self._analysis = analysis
        self._page = page
        self.committed = 0

    async def execute(self, stmt):
        # Return analysis or page depending on what was queried
        from sqlalchemy.orm import DeclarativeBase
        # Detect which model is being queried by looking at the whereclause
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "page_analyses" in compiled:
            return _FakeResult(self._analysis)
        return _FakeResult(self._page)

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        pass

    def add(self, obj):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeResult:
    def __init__(self, obj) -> None:
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


# ── Tests ────────────────────────────────────────────────────────────────────

class TestPipelineE2E:
    """Full _run_pipeline execution with all external calls mocked."""

    @pytest.mark.asyncio
    async def test_happy_path_reaches_complete_state(self):
        analysis_id = str(uuid.uuid4())
        page_id = uuid.uuid4()

        page = Page(id=page_id, site_id=uuid.uuid4(), url="https://example.com/seo-guide")
        analysis = PageAnalysis(id=uuid.UUID(analysis_id), page_id=page_id, status="queued")
        ctx = _make_analysis_context()
        readiness_verdict = _make_readiness_verdict()
        bottleneck_verdict = _make_bottleneck_verdict()
        summaries = _make_summaries_dict()

        status_transitions: list[str] = []
        published_events: list[tuple[str, str]] = []

        fake_session = _FakeSession(analysis, page)

        async def fake_set_status(session, analysis_obj, status, *, analysis_id, extra=None):
            status_transitions.append(status)
            analysis_obj.status = status
            if extra:
                for k, v in extra.items():
                    setattr(analysis_obj, k, v)
            await session.commit()

        async def fake_publish(aid, event, payload):
            published_events.append((event, aid))

        from app.pipeline import orchestrator as orch

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", side_effect=fake_set_status),
            patch.object(orch, "_publish", side_effect=fake_publish),
            patch("app.pipeline.orchestrator.collect", AsyncMock(return_value=ctx)),
            patch("app.pipeline.orchestrator.summarize_all", AsyncMock(return_value=summaries)),
            patch("app.pipeline.orchestrator.assess_readiness", AsyncMock(return_value=(readiness_verdict, {}))),
            patch("app.pipeline.orchestrator.identify_bottleneck", AsyncMock(return_value=(bottleneck_verdict, {}))),
        ):
            await orch._run_pipeline(analysis_id)

        assert status_transitions == [
            "collecting_data",
            "data_ready",
            "summarizing_content",
            "summaries_ready",
            "running_readiness",
            "running_bottleneck",
            "assembling_verdict",
            "complete",
        ], f"Unexpected transitions: {status_transitions}"

        assert analysis.status == "complete"
        assert analysis.readiness_verdict is not None
        assert analysis.bottleneck_verdict is not None
        assert analysis.readiness_confidence == "medium"
        assert analysis.bottleneck_confidence == "medium"

    @pytest.mark.asyncio
    async def test_crawl_failure_transitions_to_failed(self):
        analysis_id = str(uuid.uuid4())
        page_id = uuid.uuid4()

        page = Page(id=page_id, site_id=uuid.uuid4(), url="https://example.com/seo-guide")
        analysis = PageAnalysis(id=uuid.UUID(analysis_id), page_id=page_id, status="queued")

        status_transitions: list[str] = []
        failed_reason: list[str] = []

        fake_session = _FakeSession(analysis, page)

        async def fake_set_status(session, obj, status, *, analysis_id, extra=None):
            status_transitions.append(status)
            obj.status = status
            await session.commit()

        async def fake_set_failed(session, obj, reason, aid):
            obj.status = "failed"
            obj.failed_reason = reason
            failed_reason.append(reason)
            await session.commit()

        from app.pipeline import orchestrator as orch

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", side_effect=fake_set_status),
            patch.object(orch, "_set_failed", side_effect=fake_set_failed),
            patch.object(orch, "_publish", AsyncMock()),
            patch("app.pipeline.orchestrator.collect", AsyncMock(side_effect=RuntimeError("Crawler timeout"))),
        ):
            await orch._run_pipeline(analysis_id)

        assert "collecting_data" in status_transitions
        assert analysis.status == "failed"
        assert "Crawler timeout" in failed_reason[0]

    @pytest.mark.asyncio
    async def test_missing_page_record_exits_silently(self):
        analysis_id = str(uuid.uuid4())
        page_id = uuid.uuid4()

        analysis = PageAnalysis(id=uuid.UUID(analysis_id), page_id=page_id, status="queued")

        fake_session = _FakeSession(analysis, None)  # page is None

        from app.pipeline import orchestrator as orch

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        failed_calls: list = []

        async def fake_set_failed(session, obj, reason, aid):
            failed_calls.append(reason)
            obj.status = "failed"
            await session.commit()

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_failed", side_effect=fake_set_failed),
            patch.object(orch, "_publish", AsyncMock()),
        ):
            await orch._run_pipeline(analysis_id)

        assert len(failed_calls) == 1
        assert "Page record not found" in failed_calls[0]

    @pytest.mark.asyncio
    async def test_page_crawl_none_skips_summarization_and_reaches_complete(self):
        """When page_crawl is None, readiness returns INSUFFICIENT_DATA but pipeline completes."""
        analysis_id = str(uuid.uuid4())
        page_id = uuid.uuid4()

        page = Page(id=page_id, site_id=uuid.uuid4(), url="https://example.com/seo-guide")
        analysis = PageAnalysis(id=uuid.UUID(analysis_id), page_id=page_id, status="queued")

        ctx = _make_analysis_context()
        ctx.page_crawl = None  # simulate crawl failure

        from app.schemas.verdicts import ReadinessOutcome
        fast_fail_verdict = ReadinessVerdict(
            outcome=ReadinessOutcome.INSUFFICIENT_DATA,
            confidence=Confidence.LOW,
            confidence_rationale="Page could not be crawled.",
            headline="Page could not be reached.",
            dimensions={},
            actions=[],
            data_quality={"page_crawled": False},
        )
        bottleneck_verdict = _make_bottleneck_verdict()
        summaries = {"target": None, "competitors": [], "prompt_version": "summarize-page/v1"}

        status_transitions: list[str] = []
        fake_session = _FakeSession(analysis, page)

        async def fake_set_status(session, obj, status, *, analysis_id, extra=None):
            status_transitions.append(status)
            obj.status = status
            if extra:
                for k, v in extra.items():
                    setattr(obj, k, v)
            await session.commit()

        from app.pipeline import orchestrator as orch

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(orch, "_AsyncSession", return_value=session_ctx),
            patch.object(orch, "_set_status", side_effect=fake_set_status),
            patch.object(orch, "_publish", AsyncMock()),
            patch("app.pipeline.orchestrator.collect", AsyncMock(return_value=ctx)),
            patch("app.pipeline.orchestrator.summarize_all", AsyncMock(return_value=summaries)),
            patch("app.pipeline.orchestrator.assess_readiness", AsyncMock(return_value=(fast_fail_verdict, {}))),
            patch("app.pipeline.orchestrator.identify_bottleneck", AsyncMock(return_value=(bottleneck_verdict, {}))),
        ):
            await orch._run_pipeline(analysis_id)

        assert "complete" in status_transitions
        assert analysis.status == "complete"


class TestCeleryTaskRegistration:
    """Smoke test: verify the Celery task is registered with the correct name."""

    def test_run_analysis_task_is_registered(self):
        from app.worker.celery_app import celery_app
        import app.pipeline.orchestrator  # noqa: F401 — ensure module is imported

        registered_tasks = list(celery_app.tasks.keys())
        assert "serpnex.run_analysis" in registered_tasks, (
            f"serpnex.run_analysis not found in registered tasks: {registered_tasks}"
        )

    def test_run_analysis_task_is_callable(self):
        from app.pipeline.orchestrator import run_analysis_task
        assert callable(run_analysis_task)
        assert run_analysis_task.name == "serpnex.run_analysis"

    def test_celery_config_includes_orchestrator_module(self):
        from app.worker.celery_app import celery_app
        assert "app.pipeline.orchestrator" in celery_app.conf.include
