"""Content summarization stage (§3.1a).

Converts raw Firecrawl markdown into structured PageSummary objects using
Claude Haiku. Runs in parallel for the target page and all competitor pages.
The outputs feed directly into the Readiness and Bottleneck LLM prompts."""

from __future__ import annotations

import asyncio
import json
import re

from app.providers.base.crawler import CrawlResult
from app.providers.base.llm import LLMMessage, ToolDefinition
from app.providers.registry import get_llm_provider
from app.schemas.verdicts import PageSummary

_MODEL = "claude-haiku-4-5-20251001"
_PROMPT_VERSION = "summarize-page/v1"

_SYSTEM = """\
You are a content characterization engine. Your job is to read a web page and produce a structured \
factual description of its content — not an evaluation of its quality.

You describe what is on the page. You do not judge whether it is good or bad, thin or comprehensive, \
strong or weak. Evaluative language is forbidden. Downstream analysis systems will do the evaluation. \
Your job is to give them accurate raw material.

━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — DESCRIPTIVE LANGUAGE ONLY
Do not use: comprehensive, thin, weak, strong, good, bad, poor, excellent, detailed, lacking, \
adequate, insufficient, thorough. Replace them with specific descriptions.

RULE 2 — USE ONLY WHAT IS ON THE PAGE
Do not infer, assume, or extrapolate content that is not present.

RULE 3 — USE THE TOOL, NO PROSE OUTSIDE IT
All output must go inside the summarize_page tool call.

RULE 4 — FORMAT LABEL FROM THE APPROVED TAXONOMY
Use exactly one of: guide, listicle, comparison, tutorial, case_study, data_piece, opinion, \
landing_page, faq, tool_or_calculator, news_or_update, other"""

_TOOL: ToolDefinition = ToolDefinition(
    name="summarize_page",
    description="Return a structured factual description of the page's content.",
    input_schema={
        "type": "object",
        "required": [
            "topic_and_angle",
            "format_label",
            "heading_structure",
            "intent_alignment",
            "notable_elements",
            "visible_content_gaps",
        ],
        "properties": {
            "topic_and_angle": {
                "type": "string",
                "description": "One sentence describing the specific topic and angle. Max 150 characters.",
                "maxLength": 150,
            },
            "format_label": {
                "type": "string",
                "enum": [
                    "guide", "listicle", "comparison", "tutorial", "case_study",
                    "data_piece", "opinion", "landing_page", "faq",
                    "tool_or_calculator", "news_or_update", "other",
                ],
            },
            "heading_structure": {
                "type": "string",
                "description": "Factual description of heading structure. Max 200 characters.",
                "maxLength": 200,
            },
            "intent_alignment": {
                "type": "string",
                "description": "Whether the page format matches the apparent search intent. Max 200 characters.",
                "maxLength": 200,
            },
            "notable_elements": {
                "type": "array",
                "description": "Specific content elements present (tables, tools, data, etc.). Max 6.",
                "items": {"type": "string", "maxLength": 80},
                "maxItems": 6,
            },
            "visible_content_gaps": {
                "type": "array",
                "description": "Specific subtopics absent from the page. Max 4.",
                "items": {"type": "string", "maxLength": 100},
                "maxItems": 4,
            },
        },
    },
)


def _extract_metadata(crawl: CrawlResult) -> dict:
    """Deterministically extract h1, h2 list, and word count from markdown (§3, §3 variable definitions)."""
    md = crawl.markdown or ""

    # Strip navigation/footer noise: remove lines that are short link-only lines
    lines = md.splitlines()
    body_lines = []
    after_first_heading = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            after_first_heading = True
        # Skip short link-only lines before the first heading (site nav)
        if not after_first_heading and re.match(r"^\[.+\]\(/.+\)$", stripped):
            continue
        # Skip footer patterns
        if re.search(r"(© |Privacy Policy|Terms of Service|Cookie Policy)", stripped):
            continue
        body_lines.append(line)

    clean_md = "\n".join(body_lines)

    h1_match = re.search(r"^# (.+)$", clean_md, re.MULTILINE)
    h1 = h1_match.group(1).strip() if h1_match else "none"

    h2_matches = re.findall(r"^## (.+)$", clean_md, re.MULTILINE)
    h2_list = ", ".join(h2_matches[:10]) if h2_matches else "none"

    # Approximate word count from cleaned markdown
    text_only = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean_md)
    text_only = re.sub(r"[#*`>_~\-]+", " ", text_only)
    word_count = len(text_only.split())

    # Truncate markdown body to ~2200 words
    words = clean_md.split()
    if len(words) > 2200:
        clean_md = " ".join(words[:2200]) + " [truncated]"

    has_date = bool(re.search(r"\d{4}-\d{2}-\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", clean_md[:500]))
    has_author = bool(re.search(r"(by |author:|written by )", clean_md[:200], re.IGNORECASE))

    return {
        "h1": h1,
        "h2_list": h2_list,
        "word_count": word_count,
        "has_date": has_date,
        "has_author": has_author,
        "markdown_body": clean_md,
    }


def _build_user_message(crawl: CrawlResult, meta: dict) -> str:
    return f"""\
Summarize the following web page for use by an SEO analysis system.

## Page Metadata (extracted deterministically before this call)
URL: {crawl.url}
Title: {crawl.title or 'none'}
H1: {meta['h1']}
H2 subheadings: {meta['h2_list']}
Word count: {meta['word_count']}
Has publication date: {meta['has_date']}
Has author attribution: {meta['has_author']}

## Page Content
{meta['markdown_body']}

## Instructions
Use the summarize_page tool to return a structured summary. The summary will be used by a \
downstream analysis system to evaluate this page's content relative to competing pages for a \
target keyword. Describe the page factually. Do not evaluate it."""


async def summarize_page(crawl: CrawlResult) -> PageSummary:
    """Summarize a single page. Raises on validation failure after one retry."""
    llm = get_llm_provider()
    meta = _extract_metadata(crawl)
    user_message = _build_user_message(crawl, meta)

    response = await llm.call_with_tool(
        system=_SYSTEM,
        messages=[LLMMessage(role="user", content=user_message)],
        tool=_TOOL,
        model=_MODEL,
        max_tokens=800,
    )

    try:
        return PageSummary.model_validate(response.tool_input)
    except Exception as exc:
        # Retry once with the validation error in context
        retry_message = (
            f"Your previous response failed validation: {exc}. "
            "Correct it and call summarize_page again."
        )
        response = await llm.call_with_tool(
            system=_SYSTEM,
            messages=[
                LLMMessage(role="user", content=user_message),
                LLMMessage(role="assistant", content=json.dumps({"type": "tool_use", "name": "summarize_page", "input": response.tool_input})),
                LLMMessage(role="user", content=retry_message),
            ],
            tool=_TOOL,
            model=_MODEL,
            max_tokens=800,
        )
        return PageSummary.model_validate(response.tool_input)


async def summarize_all(
    target: CrawlResult,
    competitors: list[CrawlResult],
) -> dict:
    """Summarize target and all competitor pages concurrently.

    Returns {"target": PageSummary, "competitors": [PageSummary, ...]}
    where competitor entries may be None if that crawl failed."""
    tasks: list = [summarize_page(target)]
    for comp in competitors:
        tasks.append(summarize_page(comp))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    target_summary = results[0] if isinstance(results[0], PageSummary) else None
    competitor_summaries = [
        r if isinstance(r, PageSummary) else None for r in results[1:]
    ]

    return {
        "target": target_summary.model_dump() if target_summary else None,
        "competitors": [
            s.model_dump() if s else None for s in competitor_summaries
        ],
        "prompt_version": _PROMPT_VERSION,
    }
