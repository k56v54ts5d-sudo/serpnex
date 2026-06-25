"""Analysis API endpoints (§4).

POST /analyses — create a page analysis and enqueue the Celery task
GET  /analyses/{analysis_id} — poll current analysis state
GET  /analyses/{analysis_id}/stream — SSE stream of real-time progress events"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Page, PageAnalysis, Site
from app.db.session import get_db
from app.pipeline.orchestrator import enqueue_analysis

router = APIRouter(prefix="/analyses", tags=["analysis"])

_CHANNEL_PREFIX = "serpnex:analysis:"
_SSE_TIMEOUT = 300  # 5 minutes max stream duration


# ── Request / response schemas ────────────────────────────────────────────────

class CreateAnalysisRequest(BaseModel):
    url: HttpUrl
    site_id: uuid.UUID


class AnalysisStatusResponse(BaseModel):
    analysis_id: uuid.UUID
    status: str
    readiness_outcome: str | None = None
    readiness_confidence: str | None = None
    bottleneck_primary: str | None = None
    bottleneck_confidence: str | None = None
    links_are_the_answer: bool | None = None
    data_quality: dict | None = None
    failed_reason: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def create_analysis(
    body: CreateAnalysisRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Create a page analysis job and enqueue it for processing.

    If the Page record doesn't exist it is created automatically.
    Returns analysis_id immediately — clients should stream progress via /stream."""
    url_str = str(body.url)

    # Verify site exists
    site_result = await session.execute(
        select(Site).where(Site.id == body.site_id)
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    # Upsert page record
    page_result = await session.execute(
        select(Page).where(Page.site_id == body.site_id, Page.url == url_str)
    )
    page = page_result.scalar_one_or_none()
    if page is None:
        page = Page(site_id=body.site_id, url=url_str)
        session.add(page)
        await session.commit()
        await session.refresh(page)

    analysis = await enqueue_analysis(
        session,
        page_id=page.id,
        workspace_id=site.workspace_id,
    )

    return {"analysis_id": str(analysis.id), "status": analysis.status}


@router.get("/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis(
    analysis_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> AnalysisStatusResponse:
    """Return the current state of an analysis job."""
    result = await session.execute(
        select(PageAnalysis).where(PageAnalysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    readiness_outcome = None
    links_are_the_answer = None
    bottleneck_primary = None

    if analysis.readiness_verdict:
        readiness_outcome = analysis.readiness_verdict.get("outcome")
    if analysis.bottleneck_verdict:
        bottleneck_primary = analysis.bottleneck_verdict.get("primary_constraint")
        links_are_the_answer = analysis.bottleneck_verdict.get("links_are_the_answer")

    return AnalysisStatusResponse(
        analysis_id=analysis.id,
        status=analysis.status,
        readiness_outcome=readiness_outcome,
        readiness_confidence=analysis.readiness_confidence,
        bottleneck_primary=bottleneck_primary,
        bottleneck_confidence=analysis.bottleneck_confidence,
        links_are_the_answer=links_are_the_answer,
        data_quality=analysis.data_quality,
        failed_reason=analysis.failed_reason,
        started_at=analysis.started_at.isoformat() if analysis.started_at else None,
        completed_at=analysis.completed_at.isoformat() if analysis.completed_at else None,
    )


@router.get("/{analysis_id}/stream")
async def stream_analysis(analysis_id: uuid.UUID) -> StreamingResponse:
    """Stream real-time analysis progress via Server-Sent Events.

    The client receives one SSE message per pipeline stage transition plus
    a final 'complete' or 'failed' event. The stream closes automatically
    when the analysis reaches a terminal state or after 5 minutes."""
    return StreamingResponse(
        _event_generator(str(analysis_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_generator(analysis_id: str) -> AsyncGenerator[str, None]:
    """Subscribe to Redis pub/sub and yield SSE-formatted messages."""
    channel = f"{_CHANNEL_PREFIX}{analysis_id}"
    terminal_events = {"complete", "failed"}

    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)

        # Send initial connection confirmation
        yield _sse("connected", {"analysis_id": analysis_id})

        deadline = asyncio.get_event_loop().time() + _SSE_TIMEOUT

        while asyncio.get_event_loop().time() < deadline:
            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=2.0)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue

            if message is None:
                yield ": heartbeat\n\n"
                continue

            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, KeyError):
                continue

            event = payload.get("event", "update")
            data = payload.get("data", {})

            yield _sse(event, data)

            if event in terminal_events:
                break

        yield _sse("stream_closed", {"reason": "timeout" if asyncio.get_event_loop().time() >= deadline else "terminal"})

    except Exception as exc:
        yield _sse("error", {"detail": str(exc)})
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await client.aclose()
        except Exception:
            pass


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
