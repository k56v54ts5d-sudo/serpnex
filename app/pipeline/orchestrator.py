"""Analysis orchestrator (§3).

Implements the full 10-state analysis pipeline as a Celery task. Progress
events are published to Redis pub/sub so the SSE endpoint can stream them
to the client in real time."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Page, PageAnalysis
from app.pipeline.bottleneck import identify_bottleneck
from app.pipeline.cache import get_cache
from app.pipeline.collectors import AnalysisContext, collect
from app.pipeline.readiness import assess_readiness
from app.pipeline.summarizer import summarize_all
from app.providers.base.crawler import CrawlResult
from app.schemas.verdicts import BottleneckVerdict, PageSummary, ReadinessVerdict
from app.worker.celery_app import celery_app

_CHANNEL_PREFIX = "serpnex:analysis:"

_engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
_AsyncSession = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# ── Progress pub/sub helpers ──────────────────────────────────────────────────

async def _publish(analysis_id: str, event: str, payload: dict) -> None:
    """Publish a progress event to Redis. Never raises — progress loss is acceptable."""
    import redis.asyncio as aioredis
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        message = json.dumps({"event": event, "data": payload})
        await client.publish(f"{_CHANNEL_PREFIX}{analysis_id}", message)
        await client.aclose()
    except Exception:
        pass


async def _set_status(
    session: AsyncSession,
    analysis: PageAnalysis,
    status: str,
    *,
    analysis_id: str,
    extra: dict | None = None,
) -> None:
    """Update the DB status column and publish a progress event."""
    analysis.status = status
    analysis.updated_at = datetime.now(timezone.utc)
    if extra:
        for key, value in extra.items():
            setattr(analysis, key, value)
    await session.commit()
    await _publish(analysis_id, "status_update", {"status": status, **(extra or {})})


async def _set_failed(
    session: AsyncSession,
    analysis: PageAnalysis,
    reason: str,
    analysis_id: str,
) -> None:
    analysis.status = "failed"
    analysis.failed_reason = reason
    analysis.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await _publish(analysis_id, "failed", {"reason": reason})


# ── Main async pipeline ───────────────────────────────────────────────────────

async def _run_pipeline(analysis_id: str) -> None:
    async with _AsyncSession() as session:
        result = await session.execute(
            select(PageAnalysis).where(PageAnalysis.id == uuid.UUID(analysis_id))
        )
        analysis = result.scalar_one_or_none()
        if analysis is None:
            return

        page_result = await session.execute(
            select(Page).where(Page.id == analysis.page_id)
        )
        page = page_result.scalar_one_or_none()
        if page is None:
            await _set_failed(session, analysis, "Page record not found", analysis_id)
            return

        page_url = page.url
        gsc_tokens = None
        gsc_property = None

        analysis.started_at = datetime.now(timezone.utc)
        await session.commit()

        # ── collecting_data ───────────────────────────────────────────────────
        await _set_status(session, analysis, "collecting_data", analysis_id=analysis_id)
        try:
            ctx: AnalysisContext = await collect(
                page_url, gsc_tokens=gsc_tokens, gsc_property=gsc_property
            )
        except Exception as exc:
            await _set_failed(session, analysis, f"Data collection failed: {exc}", analysis_id)
            return

        # ── data_ready ────────────────────────────────────────────────────────
        await _set_status(
            session, analysis, "data_ready",
            analysis_id=analysis_id,
            extra={"data_quality": ctx.data_quality},
        )

        # ── summarizing_content ───────────────────────────────────────────────
        await _set_status(session, analysis, "summarizing_content", analysis_id=analysis_id)
        try:
            target_crawl = ctx.page_crawl
            competitor_crawls = [c for c in ctx.competitor_crawls if isinstance(c, CrawlResult)]
            if target_crawl is not None:
                summaries = await summarize_all(target_crawl, competitor_crawls)
            else:
                summaries = {"target": None, "competitors": [], "prompt_version": "summarize-page/v1"}
        except Exception as exc:
            await _set_failed(session, analysis, f"Content summarization failed: {exc}", analysis_id)
            return

        # ── summaries_ready ───────────────────────────────────────────────────
        await _set_status(
            session, analysis, "summaries_ready",
            analysis_id=analysis_id,
            extra={
                "content_summaries": summaries,
                "summarization_prompt_version": summaries.get("prompt_version"),
            },
        )

        # Reconstruct PageSummary objects from summaries dict for downstream workers
        target_summary: PageSummary | None = None
        if summaries.get("target"):
            try:
                target_summary = PageSummary.model_validate(summaries["target"])
            except Exception:
                pass

        competitor_summaries: list[PageSummary | None] = []
        for raw in summaries.get("competitors", []):
            if raw is None:
                competitor_summaries.append(None)
            else:
                try:
                    competitor_summaries.append(PageSummary.model_validate(raw))
                except Exception:
                    competitor_summaries.append(None)

        # ── running_readiness ─────────────────────────────────────────────────
        await _set_status(session, analysis, "running_readiness", analysis_id=analysis_id)
        try:
            readiness_verdict, readiness_overrides = await assess_readiness(ctx, target_summary)
        except Exception as exc:
            await _set_failed(session, analysis, f"Readiness analysis failed: {exc}", analysis_id)
            return

        # ── running_bottleneck ────────────────────────────────────────────────
        await _set_status(
            session, analysis, "running_bottleneck",
            analysis_id=analysis_id,
            extra={
                "readiness_verdict": readiness_verdict.model_dump(),
                "readiness_confidence": readiness_verdict.confidence.value,
            },
        )
        try:
            bottleneck_verdict, bottleneck_overrides = await identify_bottleneck(
                ctx, target_summary, competitor_summaries
            )
        except Exception as exc:
            await _set_failed(session, analysis, f"Bottleneck analysis failed: {exc}", analysis_id)
            return

        # ── assembling_verdict ────────────────────────────────────────────────
        await _set_status(session, analysis, "assembling_verdict", analysis_id=analysis_id)

        all_overrides = {**readiness_overrides, **bottleneck_overrides}

        # ── complete ──────────────────────────────────────────────────────────
        await _set_status(
            session, analysis, "complete",
            analysis_id=analysis_id,
            extra={
                "bottleneck_verdict": bottleneck_verdict.model_dump(),
                "bottleneck_confidence": bottleneck_verdict.confidence.value,
                "validation_overrides": all_overrides if all_overrides else None,
                "prompt_version": "bottleneck/v1",
                "completed_at": datetime.now(timezone.utc),
            },
        )

        # Update the parent page record
        page.last_analyzed_at = datetime.now(timezone.utc)
        page.analysis_count = (page.analysis_count or 0) + 1
        if page.title is None and ctx.page_crawl:
            page.title = ctx.page_crawl.title
        await session.commit()

        await _publish(analysis_id, "complete", {
            "analysis_id": analysis_id,
            "readiness_outcome": readiness_verdict.outcome.value,
            "bottleneck_primary": bottleneck_verdict.primary_constraint.value,
            "links_are_the_answer": bottleneck_verdict.links_are_the_answer,
        })


# ── Celery task ───────────────────────────────────────────────────────────────

@celery_app.task(name="serpnex.run_analysis", bind=True, max_retries=0)
def run_analysis_task(self, analysis_id: str) -> dict:
    """Celery entry point. Runs the async pipeline synchronously via asyncio.run()."""
    asyncio.run(_run_pipeline(analysis_id))
    return {"analysis_id": analysis_id}


# ── Public API ─────────────────────────────────────────────────────────────────

async def enqueue_analysis(
    session: AsyncSession,
    page_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
) -> PageAnalysis:
    """Create a PageAnalysis record and enqueue the Celery task. Returns the record."""
    analysis = PageAnalysis(
        page_id=page_id,
        workspace_id=workspace_id,
        status="queued",
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    run_analysis_task.delay(str(analysis.id))

    await _publish(str(analysis.id), "queued", {"analysis_id": str(analysis.id)})
    return analysis
