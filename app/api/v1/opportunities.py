"""Investment Decision Engine REST + SSE endpoints (docs/api-contracts.md).

POST /opportunities             — create and enqueue an opportunity evaluation
GET  /opportunities/{id}        — poll current state and verdict
GET  /opportunities/{id}/stream — SSE stream of real-time pipeline events"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Opportunity, Page
from app.db.session import get_db
from app.pipeline.ide_orchestrator import enqueue_opportunity

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_CHANNEL_PREFIX = "serpnex:opportunity:"
_SSE_TIMEOUT = 300  # 5-minute hard cap


# ── Validation helpers ────────────────────────────────────────────────────────

_ALLOWED_SCHEMES = {"http", "https"}


def _validate_prospect_url(url: str) -> str:
    """Validate the prospect URL per api-contracts.md §2.1 rules."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format.")
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("URL must use http or https.")
    if not parsed.netloc:
        raise ValueError("URL must include a domain.")
    netloc = parsed.netloc.split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if not netloc or "." not in netloc:
        raise ValueError("URL must include a valid domain with TLD.")
    return url


# ── Request / response schemas ────────────────────────────────────────────────

class CreateOpportunityRequest(BaseModel):
    page_id: uuid.UUID
    prospect_url: str

    @field_validator("prospect_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _validate_prospect_url(v)


class OpportunityResponse(BaseModel):
    opportunity_id: uuid.UUID
    status: str
    page_id: uuid.UUID
    prospect_url: str
    prospect_domain: str | None = None
    evaluation_mode: str | None = None
    mode_b_subtype: str | None = None
    inferred_section: str | None = None
    investment_score: float | None = None
    overall_outcome: str | None = None
    confidence: str | None = None
    confidence_ceiling: str | None = None
    opportunity_verdict: dict | None = None
    cluster_scores: dict | None = None
    data_quality: dict | None = None
    failed_reason: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def create_opportunity(
    body: CreateOpportunityRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Enqueue an Investment Decision Engine evaluation.

    The page_id must reference an existing Page record. Returns opportunity_id
    immediately — clients should poll GET /opportunities/{id} or stream progress
    via GET /opportunities/{id}/stream."""
    page_result = await session.execute(select(Page).where(Page.id == body.page_id))
    page = page_result.scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=422, detail="page_id references a page that does not exist.")

    parsed = urlparse(body.prospect_url)
    netloc = parsed.netloc.split(":")[0]
    domain = netloc[4:] if netloc.startswith("www.") else netloc

    opp = Opportunity(
        id=uuid.uuid4(),
        page_id=body.page_id,
        workspace_id=getattr(page, "workspace_id", None),
        prospect_url=body.prospect_url,
        prospect_domain=domain.lower(),
        status="queued",
    )
    session.add(opp)
    await enqueue_opportunity(session, opp)

    return {
        "opportunity_id": str(opp.id),
        "status": opp.status,
        "prospect_url": body.prospect_url,
    }


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """Return the current state of an opportunity evaluation."""
    result = await session.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")

    return OpportunityResponse(
        opportunity_id=opp.id,
        status=opp.status,
        page_id=opp.page_id,
        prospect_url=opp.prospect_url,
        prospect_domain=opp.prospect_domain,
        evaluation_mode=opp.evaluation_mode,
        mode_b_subtype=opp.mode_b_subtype,
        inferred_section=opp.inferred_section,
        investment_score=opp.investment_score,
        overall_outcome=opp.overall_outcome,
        confidence=opp.confidence,
        confidence_ceiling=opp.confidence_ceiling,
        opportunity_verdict=opp.opportunity_verdict,
        cluster_scores=opp.cluster_scores,
        data_quality=opp.data_quality,
        failed_reason=opp.failed_reason,
        started_at=opp.started_at.isoformat() if opp.started_at else None,
        completed_at=opp.completed_at.isoformat() if opp.completed_at else None,
    )


@router.get("/{opportunity_id}/stream")
async def stream_opportunity(opportunity_id: uuid.UUID) -> StreamingResponse:
    """Stream real-time pipeline events via Server-Sent Events.

    Events: status_update, complete, failed, heartbeat (keep-alive comment).
    Stream closes automatically on terminal state or after 5 minutes.
    Reconnect using the Last-Event-ID header for missed events (best effort)."""
    return StreamingResponse(
        _event_generator(str(opportunity_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_generator(opportunity_id: str) -> AsyncGenerator[str, None]:
    channel = f"{_CHANNEL_PREFIX}{opportunity_id}"
    terminal_events = {"complete", "failed"}

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
        yield _sse("connected", {"opportunity_id": opportunity_id})

        deadline = asyncio.get_event_loop().time() + _SSE_TIMEOUT

        while asyncio.get_event_loop().time() < deadline:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True), timeout=2.0
                )
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

        yield _sse("stream_closed", {
            "reason": "timeout" if asyncio.get_event_loop().time() >= deadline else "terminal"
        })

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
