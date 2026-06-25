"""Bottleneck analysis LLM worker (§3.4, §5.4).

Identifies the primary constraint preventing the target page from ranking
higher. Uses Claude Sonnet 4.6 (Bottleneck is the core product value).
Applies the validation layer and deterministic confidence scoring."""

from __future__ import annotations

import json

from app.pipeline.collectors import AnalysisContext
from app.pipeline.confidence import SignalStatus, apply_confidence_floors, calculate_confidence
from app.pipeline.validation import validate_bottleneck_verdict
from app.providers.base.llm import LLMMessage, ToolDefinition
from app.providers.base.crawler import CrawlResult
from app.providers.registry import get_llm_provider
from app.schemas.verdicts import (
    BottleneckCategory,
    BottleneckVerdict,
    PageSummary,
)

_MODEL = "claude-sonnet-4-6"
_PROMPT_VERSION = "bottleneck/v1"

_SYSTEM = """\
You are the Bottleneck Engine — the core analysis component of Serpnex, a link intelligence
platform used by SEO agencies.

Your purpose is to identify the primary constraint that is preventing a target page from
ranking at position 1–3 for its primary keyword. You reason from evidence. Every claim in
your verdict must be directly traceable to a data signal in the context you are given.

You distinguish between symptoms and root causes. You identify the single most important
constraint, not a list of everything that could be improved. You also determine whether
link building is the correct investment — or whether the real bottleneck lies elsewhere.

This verdict is actionable. Strategists will use it to decide whether to invest in a
link-building campaign for this page. Vague, generic, or unsupported verdicts waste their
time and damage the product's credibility.

Rules:
- Every claim must be supported by a specific data point from the context
- Do not invent data, rankings, or metrics that are not present
- If data is insufficient, say so in confidence_rationale and set confidence to "low"
- constraint_breakdown weights must sum to exactly 1.0
- Do not include prose outside the tool call"""

_TOOL: ToolDefinition = ToolDefinition(
    name="identify_bottleneck",
    description="Return a structured bottleneck verdict identifying the primary ranking constraint.",
    input_schema={
        "type": "object",
        "required": [
            "primary_constraint", "primary_severity", "links_are_the_answer",
            "headline", "competitive_context", "constraint_breakdown",
            "recommended_action", "recommended_action_priority",
            "confidence", "confidence_rationale", "data_quality",
        ],
        "properties": {
            "primary_constraint": {
                "type": "string",
                "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"],
            },
            "primary_severity": {
                "type": "string",
                "enum": ["mild", "significant", "severe"],
            },
            "links_are_the_answer": {
                "type": "boolean",
                "description": "True only if link_authority is the primary constraint and severity is significant or severe.",
            },
            "headline": {
                "type": "string",
                "maxLength": 150,
                "description": "One concrete, specific verdict sentence. No generic statements.",
            },
            "competitive_context": {
                "type": "string",
                "maxLength": 200,
                "description": "Describe the competitive landscape in relation to this constraint.",
            },
            "constraint_breakdown": {
                "type": "array",
                "description": "All identified constraints with weights summing to exactly 1.0.",
                "items": {
                    "type": "object",
                    "required": ["category", "severity", "weight", "reason"],
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"],
                        },
                        "severity": {"type": "string", "enum": ["mild", "significant", "severe"]},
                        "weight": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "maxLength": 250},
                    },
                },
            },
            "recommended_action": {
                "type": "string",
                "maxLength": 250,
                "description": "The single most important action the strategist should take.",
            },
            "recommended_action_priority": {
                "type": "string",
                "enum": ["immediate", "high", "medium", "low"],
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence_rationale": {
                "type": "string",
                "maxLength": 300,
                "description": "Why this confidence level was assigned. Reference specific data availability.",
            },
            "data_quality": {
                "type": "object",
                "additionalProperties": {"type": "boolean"},
            },
            "authority_gap_rds": {
                "type": ["integer", "null"],
                "description": "Estimated referring domain gap vs top competitor. Null if unavailable.",
            },
            "content_gap_words": {
                "type": ["integer", "null"],
                "description": "Estimated word count gap vs top competitor. Null if unavailable.",
            },
        },
    },
)


def _format_gsc_block(ctx: AnalysisContext) -> str:
    gsc = ctx.gsc_metrics
    if not gsc:
        return "GSC data: not connected / unavailable"
    if not gsc.keywords:
        return f"GSC data: connected, no keyword data for this URL\nTotal clicks (90d): {gsc.total_clicks}\nTotal impressions (90d): {gsc.total_impressions}"
    lines = [
        f"Total clicks (90d): {gsc.total_clicks}",
        f"Total impressions (90d): {gsc.total_impressions}",
        "Top keywords:",
    ]
    for kw in gsc.keywords[:5]:
        lines.append(f"  - \"{kw.keyword}\" → pos {kw.position:.1f}, {kw.impressions} impressions, {kw.clicks} clicks")
    return "\n".join(lines)


def _format_backlinks_block(ctx: AnalysisContext) -> str:
    if not ctx.target_backlinks:
        return "Target backlinks: not available"
    b = ctx.target_backlinks
    lines = [f"Target referring domains: {b.referring_domains}"]
    if ctx.competitor_backlinks:
        comp_rds = [
            f"{ctx.competitor_urls[i]}: {cb.referring_domains} RDs"
            for i, cb in enumerate(ctx.competitor_backlinks)
            if cb is not None and i < len(ctx.competitor_urls)
        ]
        if comp_rds:
            lines.append("Competitor referring domains:")
            for entry in comp_rds:
                lines.append(f"  - {entry}")
    return "\n".join(lines)


def _format_competitor_summaries(
    competitor_summaries: list[PageSummary | None],
    competitor_urls: list[str],
) -> str:
    if not competitor_summaries:
        return "Competitor content summaries: not available"
    lines = []
    for i, (url, summary) in enumerate(zip(competitor_urls, competitor_summaries), 1):
        if summary is None:
            lines.append(f"Competitor {i} ({url}): crawl unavailable")
        else:
            lines.append(
                f"Competitor {i} ({url}):\n"
                f"  Topic: {summary.topic_and_angle}\n"
                f"  Format: {summary.format_label.value}\n"
                f"  Notable elements: {', '.join(summary.notable_elements) or 'none'}"
            )
    return "\n".join(lines)


def _build_user_message(
    ctx: AnalysisContext,
    target_summary: PageSummary | None,
    competitor_summaries: list[PageSummary | None],
) -> str:
    word_count = len((ctx.page_crawl.markdown or "").split()) if ctx.page_crawl else 0
    target_summary_str = (
        f"Topic: {target_summary.topic_and_angle}\n"
        f"Format: {target_summary.format_label.value}\n"
        f"Intent fit: {target_summary.intent_alignment}\n"
        f"Notable elements: {', '.join(target_summary.notable_elements) or 'none'}\n"
        f"Content gaps: {'; '.join(target_summary.visible_content_gaps) or 'none'}"
    ) if target_summary else "not available"

    serp_block = "SERP data: not available"
    if ctx.serp_result:
        serp_block = (
            f"Primary keyword: {ctx.primary_keyword}\n"
            f"Top organic results:\n"
            + "\n".join(
                f"  {i+1}. {r.url} — {r.title}"
                for i, r in enumerate(ctx.serp_result.organic[:5])
            )
        )

    return f"""\
Identify the primary bottleneck preventing this page from ranking in positions 1–3.

## Target Page
URL: {ctx.page_url}
Title: {ctx.page_crawl.title if ctx.page_crawl else 'unavailable'}
Word count: {word_count}

## GSC Performance
{_format_gsc_block(ctx)}

## SERP Landscape
{serp_block}

## Target Page Content Summary
{target_summary_str}

## Competitor Content Summaries
{_format_competitor_summaries(competitor_summaries, ctx.competitor_urls)}

## Backlink Data
{_format_backlinks_block(ctx)}

## Instructions
Analyze the above signals and identify the primary constraint. Consider:
1. Is the link authority gap vs top competitors large enough to explain the ranking gap?
2. Does the content depth, format, or angle match what top-ranking pages provide?
3. Is there an intent mismatch (e.g., commercial page ranking for informational query)?
4. Is the internal link profile adequate for the page's topic authority?
5. Are there any technical signals that indicate indexing or crawl issues?

Determine whether link building is the correct investment. If the bottleneck is content,
intent, or technical — set links_are_the_answer to false and explain why.

All constraint_breakdown weights must sum to exactly 1.0.

Use the tool to return your verdict."""


async def identify_bottleneck(
    ctx: AnalysisContext,
    target_summary: PageSummary | None,
    competitor_summaries: list[PageSummary | None],
) -> tuple[BottleneckVerdict, dict]:
    """Run bottleneck analysis. Returns (verdict, validation_overrides)."""
    llm = get_llm_provider()
    user_message = _build_user_message(ctx, target_summary, competitor_summaries)

    response = await llm.call_with_tool(
        system=_SYSTEM,
        messages=[LLMMessage(role="user", content=user_message)],
        tool=_TOOL,
        model=_MODEL,
        max_tokens=2000,
    )

    try:
        verdict = BottleneckVerdict.model_validate(response.tool_input)
    except Exception as exc:
        retry_msg = f"Validation failed: {exc}. Correct the response and call identify_bottleneck again."
        response = await llm.call_with_tool(
            system=_SYSTEM,
            messages=[
                LLMMessage(role="user", content=user_message),
                LLMMessage(role="assistant", content=json.dumps(response.tool_input)),
                LLMMessage(role="user", content=retry_msg),
            ],
            tool=_TOOL,
            model=_MODEL,
            max_tokens=2000,
        )
        verdict = BottleneckVerdict.model_validate(response.tool_input)

    # Business logic validation
    validation = validate_bottleneck_verdict(verdict)
    overrides: dict = {}
    if validation.overrides:
        overrides["bottleneck"] = validation.overrides

    # Deterministic confidence scoring
    successful_competitor_crawls = sum(
        1 for c in ctx.competitor_crawls if isinstance(c, CrawlResult)
    )
    signals = {
        "gsc_keyword_data": SignalStatus.AVAILABLE if (ctx.gsc_metrics and ctx.gsc_metrics.keywords) else SignalStatus.MISSING,
        "competitor_crawls": SignalStatus.AVAILABLE if successful_competitor_crawls >= 2 else (
            SignalStatus.PARTIAL if successful_competitor_crawls == 1 else SignalStatus.MISSING
        ),
        "target_backlink_data": SignalStatus.AVAILABLE if ctx.target_backlinks else SignalStatus.MISSING,
        "competitor_backlink_data": SignalStatus.AVAILABLE if any(b for b in ctx.competitor_backlinks) else SignalStatus.MISSING,
        "serp_results": SignalStatus.AVAILABLE if ctx.serp_result else SignalStatus.MISSING,
    }
    deterministic_confidence = calculate_confidence(signals, "bottleneck")
    final_confidence, floor_overrides = apply_confidence_floors(
        deterministic_confidence,
        gsc_connected=ctx.gsc_connected,
        backlink_data_available=ctx.target_backlinks is not None,
        competitor_count=successful_competitor_crawls,
        page_crawl_success=ctx.page_crawl is not None,
        page_age_days=None,
        module="bottleneck",
    )
    if floor_overrides:
        overrides.setdefault("bottleneck", []).extend(floor_overrides)

    verdict.confidence = verdict.confidence.__class__(final_confidence)
    return verdict, overrides
