"""Readiness analysis LLM worker (§3.3, §5.3).

Runs rules-based pre-checks first. Skips the LLM call if a hard Not Ready
result can be determined without it. On LLM call: validates schema + business
logic, applies confidence floors, returns a final ReadinessVerdict."""

from __future__ import annotations

import json

from app.pipeline.collectors import AnalysisContext
from app.pipeline.confidence import SignalStatus, apply_confidence_floors, calculate_confidence
from app.pipeline.validation import validate_readiness_verdict
from app.providers.base.llm import LLMMessage, ToolDefinition
from app.providers.registry import get_llm_provider
from app.schemas.verdicts import PageSummary, ReadinessDimension, ReadinessOutcome, ReadinessVerdict

_MODEL = "claude-haiku-4-5-20251001"
_PROMPT_VERSION = "readiness/v1"

_SYSTEM = """\
You are the analysis engine for Serpnex, a link intelligence platform used by SEO agencies.
Your role is to analyze web pages and produce structured, defensible verdicts that help
strategists make decisions about link building.

You analyze signals objectively. You do not overstate confidence. When data is insufficient
to support a verdict, you say so clearly. You produce verdicts that are actionable and specific,
not vague or generic.

All outputs must match the tool schema exactly. Do not include prose outside the tool call."""

_TOOL: ToolDefinition = ToolDefinition(
    name="assess_readiness",
    description="Return a structured readiness verdict for the target page.",
    input_schema={
        "type": "object",
        "required": [
            "outcome", "confidence", "confidence_rationale", "headline",
            "dimensions", "actions", "data_quality",
        ],
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["ready", "not_ready", "ready_with_caveats", "insufficient_data"],
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence_rationale": {"type": "string", "maxLength": 300},
            "headline": {"type": "string", "maxLength": 120},
            "dimensions": {
                "type": "object",
                "description": "Keys: content_sufficiency, intent_alignment, indexing, internal_authority",
                "additionalProperties": {
                    "type": "object",
                    "required": ["passed", "severity", "reason"],
                    "properties": {
                        "passed": {"type": "boolean"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "reason": {"type": "string", "maxLength": 200},
                        "action": {"type": "string", "maxLength": 200},
                    },
                },
            },
            "actions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "data_quality": {
                "type": "object",
                "additionalProperties": {"type": "boolean"},
            },
        },
    },
)


def _rules_based_hard_not_ready(ctx: AnalysisContext) -> ReadinessVerdict | None:
    """Return a hard Not Ready verdict without an LLM call if obvious signals fail (§3.3).

    Returns None if the LLM call is needed."""
    if ctx.page_crawl is None:
        return ReadinessVerdict(
            outcome=ReadinessOutcome.INSUFFICIENT_DATA,
            confidence="low",
            confidence_rationale="Page could not be crawled. No content signals available.",
            headline="Page could not be reached — analysis incomplete.",
            dimensions={
                "indexing": ReadinessDimension(
                    passed=False, severity="high",
                    reason="Page returned an error or could not be crawled.",
                    action="Verify the URL is correct and the page is publicly accessible.",
                )
            },
            actions=["Verify the URL is reachable before re-running analysis."],
            data_quality=ctx.data_quality,
        )

    word_count = len((ctx.page_crawl.markdown or "").split())
    if word_count < 200:
        return ReadinessVerdict(
            outcome=ReadinessOutcome.NOT_READY,
            confidence="high",
            confidence_rationale="Word count is below the minimum threshold for any ranking potential.",
            headline=f"Page has only {word_count} words — insufficient for link-building investment.",
            dimensions={
                "content_sufficiency": ReadinessDimension(
                    passed=False, severity="high",
                    reason=f"Page body contains {word_count} words. Minimum for indexable content is ~300 words.",
                    action="Expand the page with substantive, keyword-relevant content before building links.",
                )
            },
            actions=["Expand page content to at least 600 words before any link-building investment."],
            data_quality=ctx.data_quality,
        )

    return None


def _build_user_message(ctx: AnalysisContext, target_summary: PageSummary | None) -> str:
    gsc = ctx.gsc_metrics
    keywords_str = "not available"
    avg_position_str = "not available"
    impressions_str = "not available"
    if gsc and gsc.keywords:
        top_kw = gsc.keywords[0]
        keywords_str = top_kw.keyword
        avg_position_str = f"{top_kw.position:.1f}"
        impressions_str = str(top_kw.impressions)

    backlinks_str = "not available"
    if ctx.target_backlinks:
        backlinks_str = str(ctx.target_backlinks.referring_domains)

    internal_links_str = "not available"

    summary_str = "not available"
    if target_summary:
        summary_str = (
            f"Topic and angle: {target_summary.topic_and_angle}\n"
            f"Format: {target_summary.format_label.value}\n"
            f"Intent fit: {target_summary.intent_alignment}\n"
            f"Notable elements: {', '.join(target_summary.notable_elements) or 'none'}\n"
            f"Content gaps: {'; '.join(target_summary.visible_content_gaps) or 'none'}"
        )

    word_count = len((ctx.page_crawl.markdown or "").split()) if ctx.page_crawl else 0

    return f"""\
Analyze whether the following page is ready to receive link-building investment.

## Target Page
URL: {ctx.page_url}
Title: {ctx.page_crawl.title if ctx.page_crawl else 'unavailable'}
Word count: {word_count}
Primary keyword (from GSC or inferred): {keywords_str}
GSC average position: {avg_position_str}
GSC impressions (90d): {impressions_str}
Estimated referring domains: {backlinks_str}
Internal links pointing to this page: {internal_links_str}

## Content summary
{summary_str}

## Instructions
Assess readiness across these dimensions:
1. content_sufficiency: Does the page have sufficient depth and quality to rank for the primary keywords?
2. intent_alignment: Does the page format and content match the dominant search intent for these keywords?
3. indexing: Is the page reachable, indexed, and technically sound enough to benefit from links?
4. internal_authority: Is the page adequately supported by internal links within its site?

A page is "ready" only if all four dimensions pass. If any dimension fails significantly, use \
"not_ready". If a dimension fails mildly, use "ready_with_caveats".

Set confidence to "low" if GSC data is unavailable or if the page has no ranking history.

Use the tool to return your verdict."""


async def assess_readiness(
    ctx: AnalysisContext,
    target_summary: PageSummary | None,
) -> tuple[ReadinessVerdict, dict]:
    """Run readiness analysis. Returns (verdict, validation_overrides)."""

    # Rules-based hard Not Ready check (skips LLM call on obvious failures)
    fast_result = _rules_based_hard_not_ready(ctx)
    if fast_result is not None:
        return fast_result, {}

    llm = get_llm_provider()
    user_message = _build_user_message(ctx, target_summary)

    response = await llm.call_with_tool(
        system=_SYSTEM,
        messages=[LLMMessage(role="user", content=user_message)],
        tool=_TOOL,
        model=_MODEL,
        max_tokens=1500,
    )

    try:
        verdict = ReadinessVerdict.model_validate(response.tool_input)
    except Exception as exc:
        retry_msg = f"Validation failed: {exc}. Correct the response and call assess_readiness again."
        response = await llm.call_with_tool(
            system=_SYSTEM,
            messages=[
                LLMMessage(role="user", content=user_message),
                LLMMessage(role="assistant", content=json.dumps(response.tool_input)),
                LLMMessage(role="user", content=retry_msg),
            ],
            tool=_TOOL,
            model=_MODEL,
            max_tokens=1500,
        )
        verdict = ReadinessVerdict.model_validate(response.tool_input)

    # Business logic validation + confidence floors
    validation = validate_readiness_verdict(verdict, gsc_connected=ctx.gsc_connected)
    overrides: dict = {}
    if validation.overrides:
        overrides["readiness"] = validation.overrides

    # Deterministic confidence scoring
    signals = {
        "page_crawl_success": SignalStatus.AVAILABLE if ctx.page_crawl else SignalStatus.MISSING,
        "gsc_data": SignalStatus.AVAILABLE if ctx.gsc_metrics else SignalStatus.MISSING,
        "page_indexed": SignalStatus.AVAILABLE if ctx.page_crawl else SignalStatus.MISSING,
        "internal_link_data": SignalStatus.MISSING,
    }
    deterministic_confidence = calculate_confidence(signals, "readiness")
    final_confidence, floor_overrides = apply_confidence_floors(
        deterministic_confidence,
        gsc_connected=ctx.gsc_connected,
        backlink_data_available=ctx.target_backlinks is not None,
        competitor_count=sum(1 for c in ctx.competitor_crawls if not isinstance(c, Exception)),
        page_crawl_success=ctx.page_crawl is not None,
        page_age_days=None,
        module="readiness",
    )
    if floor_overrides:
        overrides.setdefault("readiness", []).extend(floor_overrides)

    verdict.confidence = verdict.confidence.__class__(final_confidence)
    return verdict, overrides
