"""Investment Decision Engine Celery orchestrator (§3.5).

Exposes:
  run_ide_task(opportunity_id)  — Celery task (name: serpnex.run_ide)
  enqueue_opportunity(db, opp)  — enqueue helper called from the API endpoint

Nine-state machine:
  queued → detecting_mode → inferring_section → collecting_data
         → classifying_signals → computing_score → assembling_verdict
         → complete | failed

All state transitions are persisted to the DB and published as SSE events via Redis.
Failures are caught per-stage so that partial progress is preserved in the DB."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Opportunity, Page
from app.pipeline.ide_collector import collect_ide
from app.pipeline.ide_gates import evaluate_gates
from app.pipeline.ide_llm import call_1_classify_signals, call_2_assemble_verdict
from app.pipeline.ide_scorer import compute_score
from app.schemas.opportunities import GateResult, HardExclusionGate, InvestmentOutcome, InvestmentVerdict
from app.worker.celery_app import celery_app

logger = get_task_logger(__name__)

_PROMPT_VERSION = "opportunity-v1"

_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_AsyncSession = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# ── Public enqueue helper (called from the REST endpoint) ─────────────────────

async def enqueue_opportunity(db: AsyncSession, opportunity: Opportunity) -> None:
    """Persist the opportunity as 'queued' and dispatch the Celery task."""
    opportunity.status = "queued"
    await db.commit()
    run_ide_task.delay(str(opportunity.id))


# ── SSE publish ───────────────────────────────────────────────────────────────

async def _publish(opportunity_id: str, event: str, payload: dict) -> None:
    """Publish an SSE event to Redis pub/sub for streaming to the frontend."""
    import redis.asyncio as aioredis
    client = aioredis.from_url(settings.redis_url)
    channel = f"serpnex:opportunity:{opportunity_id}"
    message = json.dumps({"event": event, "data": payload})
    try:
        await client.publish(channel, message)
    finally:
        await client.aclose()


# ── State transition helpers ───────────────────────────────────────────────────

async def _set_status(
    session: AsyncSession,
    opp: Opportunity,
    status: str,
    opportunity_id: str,
    extra: dict | None = None,
) -> None:
    opp.status = status
    await session.commit()
    await _publish(opportunity_id, "status_update", {"status": status, **(extra or {})})


async def _set_failed(
    session: AsyncSession,
    opp: Opportunity,
    reason: str,
    opportunity_id: str,
) -> None:
    opp.status = "failed"
    opp.failed_reason = reason
    opp.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await _publish(opportunity_id, "failed", {"reason": reason})


async def _set_complete(
    session: AsyncSession,
    opp: Opportunity,
    opportunity_id: str,
) -> None:
    opp.status = "complete"
    opp.completed_at = datetime.now(timezone.utc)
    await session.commit()
    verdict_data = opp.opportunity_verdict or {}
    await _publish(opportunity_id, "complete", {
        "outcome": opp.overall_outcome,
        "investment_score": opp.investment_score,
        "confidence": opp.confidence,
        "verdict": verdict_data,
    })


# ── Gate-triggered failure path ───────────────────────────────────────────────

async def _apply_gate_exclusion(
    session: AsyncSession,
    opp: Opportunity,
    gate_result: GateResult,
    opportunity_id: str,
) -> None:
    """Persist a hard exclusion verdict and mark the opportunity complete."""
    verdict = InvestmentVerdict(
        outcome=InvestmentOutcome.NOT_RECOMMENDED,
        evaluation_mode=opp.evaluation_mode,
        mode_b_subtype=opp.mode_b_subtype,
        hard_exclusion_triggered=True,
        hard_exclusion_gate=gate_result.gate,
        hard_exclusion_reason=gate_result.reason,
        supporting_signals=[],
        conditions=[],
        confidence="low",
        confidence_ceiling="low",
        data_quality={},
    )
    opp.opportunity_verdict = verdict.model_dump(mode="json")
    opp.overall_outcome = InvestmentOutcome.NOT_RECOMMENDED.value
    opp.confidence = "low"
    opp.confidence_ceiling = "low"
    opp.prompt_version = _PROMPT_VERSION
    await _set_complete(session, opp, opportunity_id)


# ── Main pipeline coroutine ────────────────────────────────────────────────────

async def _run_pipeline(opportunity_id: str) -> None:
    async with _AsyncSession() as session:
        result = await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
        opp: Opportunity | None = result.scalar_one_or_none()
        if opp is None:
            logger.error("Opportunity %s not found", opportunity_id)
            return

        page_result = await session.execute(select(Page).where(Page.id == opp.page_id))
        page: Page | None = page_result.scalar_one_or_none()

        opp.started_at = datetime.now(timezone.utc)
        opp.prompt_version = _PROMPT_VERSION
        await session.commit()

        # ── State: detecting_mode ──────────────────────────────────────────────
        await _set_status(session, opp, "detecting_mode", opportunity_id)

        target_topic = getattr(page, "target_topic", None) if page else None
        target_audience = getattr(page, "target_audience", None) if page else None

        try:
            ctx = await collect_ide(
                prospect_url=opp.prospect_url,
                target_topic=target_topic,
                target_audience=target_audience,
            )
        except Exception as exc:
            await _set_failed(session, opp, f"Mode detection failed: {exc}", opportunity_id)
            return

        opp.evaluation_mode = ctx.mode
        opp.mode_b_subtype = ctx.mode_b_subtype
        opp.inferred_section = ctx.inferred_section
        await session.commit()

        # ── State: inferring_section (Mode B/domain only) ─────────────────────
        if ctx.mode == "guest_post_opportunity" and ctx.mode_b_subtype == "domain_inferred":
            await _set_status(session, opp, "inferring_section", opportunity_id)

        # ── State: collecting_data ─────────────────────────────────────────────
        await _set_status(session, opp, "collecting_data", opportunity_id)
        # Data already collected by collect_ide — just update data_quality
        opp.data_quality = ctx.data_quality
        await session.commit()

        # ── Hard exclusion gates (run before any LLM call) ────────────────────
        gate_result = evaluate_gates(ctx)
        if gate_result.triggered:
            await _apply_gate_exclusion(session, opp, gate_result, opportunity_id)
            return

        # ── State: classifying_signals ─────────────────────────────────────────
        await _set_status(session, opp, "classifying_signals", opportunity_id)
        try:
            signals = await call_1_classify_signals(ctx)
        except Exception as exc:
            await _set_failed(session, opp, f"Signal classification failed: {exc}", opportunity_id)
            return

        # ── State: computing_score ─────────────────────────────────────────────
        await _set_status(session, opp, "computing_score", opportunity_id)
        try:
            score_result = compute_score(ctx, signals)
        except Exception as exc:
            await _set_failed(session, opp, f"Score computation failed: {exc}", opportunity_id)
            return

        opp.investment_score = score_result.investment_score
        opp.cluster_scores = score_result.cluster_scores.model_dump(mode="json")
        opp.overall_outcome = score_result.outcome.value
        opp.confidence = score_result.deterministic_confidence
        opp.confidence_ceiling = score_result.confidence_ceiling
        await session.commit()

        # ── State: assembling_verdict ──────────────────────────────────────────
        await _set_status(session, opp, "assembling_verdict", opportunity_id)
        try:
            verdict = await call_2_assemble_verdict(
                ctx=ctx,
                score_result=score_result,
                target_url=str(page.url) if page else None,
            )
        except Exception as exc:
            # Verdict assembly failure: we have scores — store a minimal verdict
            logger.warning("Verdict assembly failed for %s: %s", opportunity_id, exc)
            verdict = InvestmentVerdict(
                outcome=score_result.outcome,
                investment_score=score_result.investment_score,
                evaluation_mode=ctx.mode,
                mode_b_subtype=ctx.mode_b_subtype,
                hard_exclusion_triggered=False,
                cluster_scores=score_result.cluster_scores,
                headline=f"{score_result.outcome.value.replace('_', ' ').title()} — {score_result.investment_score:.0f}/100",
                primary_reason="Verdict assembly unavailable. Scores are deterministic.",
                supporting_signals=[],
                conditions=[],
                confidence=score_result.deterministic_confidence,
                confidence_ceiling=score_result.confidence_ceiling,
                data_quality=ctx.data_quality,
            )

        opp.opportunity_verdict = verdict.model_dump(mode="json")
        await _set_complete(session, opp, opportunity_id)


# ── Celery task ────────────────────────────────────────────────────────────────

@celery_app.task(name="serpnex.run_ide", bind=True, max_retries=0)
def run_ide_task(self, opportunity_id: str) -> dict:
    """Celery entry point — runs the async IDE pipeline synchronously."""
    asyncio.run(_run_pipeline(opportunity_id))
    return {"opportunity_id": opportunity_id}
