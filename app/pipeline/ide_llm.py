"""LLM calls for the Investment Decision Engine (§3.5, docs/prompts/opportunity-v1.md).

Two calls, both using claude-haiku-4-5-20251001:
  Call 1 — signal extraction:  IDEContext → SignalScores
  Call 2 — verdict assembly:   IDEContext + ScoreResult → InvestmentVerdict language fields

Both calls use forced tool use (call_with_tool). The LLM cannot change the outcome
tier or investment score — those are deterministic outputs from ide_scorer.

Temperature is always 0 for reproducibility. Do not change this.

Prompt version: opportunity-v1 (see docs/prompts/opportunity-v1.md for full spec)."""

from __future__ import annotations

import re
from typing import Any

from app.providers.base.llm import LLMError, LLMMessage, ToolDefinition
from app.providers.registry import get_llm_provider
from app.schemas.opportunities import (
    ClusterScores,
    IDEContext,
    InvestmentOutcome,
    InvestmentVerdict,
    PlacementFeasibility,
    ScoreResult,
    SignalScores,
)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_PROMPT_VERSION = "opportunity-v1"

# ── Shared system prompt (verbatim per docs/prompts/opportunity-v1.md §1) ──────

_SYSTEM_PROMPT = """\
You are the Investment Decision Engine for Serpnex, a link intelligence platform used by SEO agencies and independent consultants.

Your job is to evaluate whether a prospect website is a worthwhile investment for a guest post or backlink placement — based on evidence from the site's content, authority, and editorial patterns.

You analyze signals objectively. You do not produce verdicts that match what a link-builder wants to hear. If the evidence says this site is not a good investment, you say so clearly.

━━━━━━━━━━━━━━━━━━━━━━━━━
RULES — READ ALL OF THESE
━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — SCORE WHAT YOU OBSERVE, NOT WHAT YOU EXPECT
Every score must be grounded in specific content you were given. Do not reason about what this type of site "usually" looks like. If the provided content shows a problem, score it accordingly. If it does not, do not assume one exists.

RULE 2 — EDITORIAL INTEGRITY IS NOT AN OPINION
D4 (Editorial Integrity) is the most consequential signal. Score it based on observable patterns in the content and outbound links — not on whether the site accepts guest posts, not on whether it has a "Write For Us" page, and not on whether you approve of its niche. A site that accepts guest posts can still have strong editorial integrity if its content is selective and its outbound link profile is clean. A site that does not label itself as a guest post site can still show editorial corruption if its OBL patterns reveal indiscriminate link placement.

RULE 3 — REASON ONLY FROM PROVIDED DATA
Do not estimate, assume, or infer values for signals not in the input. If a domain sample is missing, note it in your scores — do not fill the gap with general knowledge about the niche. Fabricating signal evidence is a critical failure.

RULE 4 — DISTINGUISH BETWEEN QUALITY AND RELEVANCE
A high-quality piece of content that covers an unrelated topic should score high on P2 (content quality) and low on P1 (topical relevance). Do not penalise quality because it is off-topic, and do not reward relevance when quality is absent.

RULE 5 — USE THE TOOL, NO PROSE OUTSIDE IT
All output must go inside the tool call. Do not write any text before or after the tool call. If you are uncertain about a field value, use your best judgment and document the uncertainty in the rationale field — do not omit the field or return null for required scores.\
"""

# ── Call 1 tool schema ────────────────────────────────────────────────────────

_CALL_1_TOOL = ToolDefinition(
    name="extract_investment_signals",
    description=(
        "Record scored content and authority signals for the prospect site. "
        "All float scores are 0.0–1.0. All fields are required. "
        "Do not include any investment recommendation — that is computed separately."
    ),
    input_schema={
        "type": "object",
        "required": [
            "p1_topical_relevance", "p1_rationale",
            "p2_content_quality", "p2_rationale",
            "p4_obl_quality", "p4_rationale",
            "p5_placement_feasibility", "p5_rationale",
            "d1_topical_coherence", "d1_rationale",
            "d4_editorial_integrity", "d4_rationale",
            "d9_geo_language_match", "d9_rationale",
            "language_match", "data_quality_notes",
        ],
        "properties": {
            "p1_topical_relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "p1_rationale": {"type": "string", "maxLength": 200},
            "p2_content_quality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "p2_rationale": {"type": "string", "maxLength": 200},
            "p4_obl_quality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "p4_rationale": {"type": "string", "maxLength": 200},
            "p5_placement_feasibility": {
                "type": "string",
                "enum": ["natural", "workable", "forced", "implausible"],
            },
            "p5_rationale": {"type": "string", "maxLength": 200},
            "d1_topical_coherence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "d1_rationale": {"type": "string", "maxLength": 200},
            "d4_editorial_integrity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "d4_rationale": {"type": "string", "maxLength": 250},
            "d9_geo_language_match": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "d9_rationale": {"type": "string", "maxLength": 150},
            "language_match": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "data_quality_notes": {"type": "string", "maxLength": 300},
        },
    },
)

# ── Call 2 tool schema ────────────────────────────────────────────────────────

_CALL_2_TOOL = ToolDefinition(
    name="assemble_investment_verdict",
    description=(
        "Compose the plain-language investment verdict. "
        "The outcome tier and investment score are already decided — do not change them. "
        "Your role is to explain those results clearly and honestly."
    ),
    input_schema={
        "type": "object",
        "required": [
            "headline", "primary_reason", "supporting_signals",
            "conditions", "mode_qualifier", "confidence_rationale",
        ],
        "properties": {
            "headline": {
                "type": "string", "maxLength": 130,
                "description": "One sharp sentence summarising the investment verdict.",
            },
            "primary_reason": {
                "type": "string", "maxLength": 250,
                "description": (
                    "The single most important reason behind the outcome tier. "
                    "Must reference D4 score if D4 < 0.30."
                ),
            },
            "supporting_signals": {
                "type": "array",
                "items": {"type": "string", "maxLength": 150},
                "maxItems": 4,
                "description": "Up to 4 bullet-ready phrases naming a positive or negative signal.",
            },
            "conditions": {
                "type": "array",
                "items": {"type": "string", "maxLength": 150},
                "maxItems": 3,
                "description": "For with_conditions outcome only: specific, actionable conditions to accept the link. Empty for other outcomes.",
            },
            "mode_qualifier": {
                "type": "string", "maxLength": 200,
                "description": (
                    "A single sentence explaining the evaluation mode and any structural caveat. "
                    "E.g. 'Evaluated as a guest post opportunity — confidence is capped at medium because the section was inferred.'"
                ),
            },
            "confidence_rationale": {
                "type": "string", "maxLength": 250,
                "description": "Explain which data was available or missing that drove the confidence level.",
            },
        },
    },
)


# ── Public entry points ────────────────────────────────────────────────────────

async def call_1_classify_signals(ctx: IDEContext) -> SignalScores:
    """Run Haiku Call 1: extract signal scores from crawled content.

    Builds the appropriate Mode A or Mode B user message, calls the LLM with
    forced tool use, and parses the result into SignalScores. Retries once on
    recoverable LLM errors."""
    llm = get_llm_provider()
    user_message = _build_call_1_message(ctx)
    messages = [LLMMessage(role="user", content=user_message)]

    response = await _call_with_retry(
        llm=llm,
        system=_SYSTEM_PROMPT,
        messages=messages,
        tool=_CALL_1_TOOL,
        max_tokens=2500,
    )

    return _parse_signal_scores(response.tool_input)


async def call_2_assemble_verdict(
    ctx: IDEContext,
    score_result: ScoreResult,
    target_url: str | None = None,
) -> InvestmentVerdict:
    """Run Haiku Call 2: translate the computed scores into plain-language verdict.

    The LLM receives the outcome tier, investment score, and all cluster scores.
    It cannot change any numeric values. Its sole output is the explanation fields."""
    llm = get_llm_provider()
    user_message = _build_call_2_message(ctx, score_result, target_url)
    messages = [LLMMessage(role="user", content=user_message)]

    response = await _call_with_retry(
        llm=llm,
        system=_SYSTEM_PROMPT,
        messages=messages,
        tool=_CALL_2_TOOL,
        max_tokens=1500,
    )

    return _assemble_verdict(ctx, score_result, response.tool_input)


# ── Message builders ──────────────────────────────────────────────────────────

def _build_call_1_message(ctx: IDEContext) -> str:
    target_url = ctx.prospect_url
    target_topic = ctx.target_topic or "not available"
    target_audience = ctx.target_audience or "not available"

    if ctx.mode == "specific_placement":
        return _call_1_mode_a(ctx, target_url, target_topic, target_audience)
    return _call_1_mode_b(ctx, target_url, target_topic, target_audience)


def _call_1_mode_a(ctx: IDEContext, target_url: str, target_topic: str, target_audience: str) -> str:
    crawl = ctx.placement_page_crawl
    placement_url = (crawl.url if crawl else target_url) or "not available"
    placement_title = _crawl_attr(crawl, "title") or "not available"
    placement_h1 = _extract_h1(crawl)
    placement_h2_list = _extract_headings(crawl, level=2)
    placement_content = _compress_content(crawl, word_limit=600)
    placement_obl_list = _format_obl(crawl, limit=20)
    placement_crawled = _crawl_status(crawl)

    domain_samples_text = _format_domain_samples(ctx.domain_sample_crawls)
    domain_sample_count = len(ctx.domain_sample_crawls)
    domain_metrics_available = "yes" if ctx.domain_metrics else "no"

    return f"""\
Score the following webpage as a candidate for hosting a link to the target page.

════════════════════════════════════
TARGET CONTEXT
════════════════════════════════════
Target page URL: {target_url}
Target topic: {target_topic}
Target audience: {target_audience}

════════════════════════════════════
EVALUATION MODE
════════════════════════════════════
Mode: Specific Placement Evaluation
You are evaluating a single, specific article as the intended placement page for a link to the target.

════════════════════════════════════
PLACEMENT PAGE
════════════════════════════════════
URL: {placement_url}
Title: {placement_title}
H1: {placement_h1}
H2 subheadings: {placement_h2_list}

Content:
{placement_content}

Outbound links found on this page:
{placement_obl_list}

════════════════════════════════════
DOMAIN SAMPLE PAGES
(additional pages from the same domain, used to assess domain-level signals)
════════════════════════════════════
{domain_samples_text}

════════════════════════════════════
DATA AVAILABILITY FLAGS
════════════════════════════════════
Placement page crawled: {placement_crawled}
Domain sample pages available: {domain_sample_count} of 3
DataForSEO domain metrics available: {domain_metrics_available}

════════════════════════════════════
SCORING INSTRUCTIONS
════════════════════════════════════
Score each signal using the tool. Use the signal reference for exact definitions.

For P5 (Placement Feasibility) in Mode A: score based on whether a link to the target topic could be placed WITHIN THIS SPECIFIC ARTICLE naturally. Consider the article's existing angle, subtopics, and outbound link pattern. A link that would require rewriting significant portions of the article to accommodate should score "forced" or lower.

Use the tool to return all scores. Do not add a recommendation or investment conclusion — that is computed separately.\
"""


def _call_1_mode_b(ctx: IDEContext, target_url: str, target_topic: str, target_audience: str) -> str:
    if ctx.mode_b_subtype == "category_url":
        mode_qualifier_block = (
            f"Mode: Guest Post Opportunity — category_url\n"
            f"You are evaluating a specific content section (category/topic page) of this site.\n"
            f"Section evaluated: {ctx.prospect_url}"
        )
    else:
        inferred = ctx.inferred_section or ctx.prospect_domain
        note = ctx.mode_detection_note or "Inferred via homepage and sitemap analysis."
        mode_qualifier_block = (
            f"Mode: Guest Post Opportunity — domain_inferred\n"
            f"You are evaluating a content section inferred as the best topical match for the target.\n"
            f"Section inferred: {inferred}\n"
            f"Section inference basis: {note}"
        )

    articles_text = _format_articles(ctx.sampled_article_crawls, ctx.sampled_article_urls)
    article_count = len(ctx.sampled_article_crawls)
    domain_samples_text = _format_domain_samples(ctx.domain_sample_crawls)
    domain_sample_count = len(ctx.domain_sample_crawls)
    domain_metrics_available = "yes" if ctx.domain_metrics else "no"

    return f"""\
Score this website section as a candidate for a guest post containing a link to the target page.

════════════════════════════════════
TARGET CONTEXT
════════════════════════════════════
Target page URL: {target_url}
Target topic: {target_topic}
Target audience: {target_audience}

════════════════════════════════════
EVALUATION MODE
════════════════════════════════════
{mode_qualifier_block}

You are assessing the SECTION as a whole, not any individual article. Scores for P1 and P2 reflect the average quality of the sampled articles, not the best or worst individual article.

════════════════════════════════════
SAMPLED ARTICLES FROM SECTION
({article_count} articles sampled)
════════════════════════════════════
{articles_text}

════════════════════════════════════
DOMAIN SAMPLE PAGES
(additional pages from outside the evaluated section, used for domain-level signals)
════════════════════════════════════
{domain_samples_text}

════════════════════════════════════
DATA AVAILABILITY FLAGS
════════════════════════════════════
Articles sampled: {article_count}
Domain sample pages available: {domain_sample_count}
DataForSEO domain metrics available: {domain_metrics_available}

════════════════════════════════════
SCORING INSTRUCTIONS
════════════════════════════════════
Score each signal using the tool. Use the signal reference for exact definitions.

P1 and P2: average across all sampled articles — do not let one outlier article dominate.

P5 (Placement Feasibility) in Mode B: score based on whether a GUEST POST written for this SECTION could naturally include a link to the target topic. Consider whether the section publishes content that would logically mention or link to content about {target_topic}. This is about the feasibility of writing a relevant guest post — not about whether the current articles contain such a link.

D4 (Editorial Integrity): evaluate across ALL sampled articles and domain sample pages. Consistent OBL patterns reveal editorial standards better than any single page.

Use the tool to return all scores. Do not add a recommendation or investment conclusion — that is computed separately.\
"""


def _build_call_2_message(
    ctx: IDEContext,
    score_result: ScoreResult,
    target_url: str | None,
) -> str:
    cs = score_result.cluster_scores
    caps_note = ""
    if score_result.editorial_integrity_cap_applied:
        caps_note += "\n⚠ Editorial Integrity Cap applied (D4 < 0.30 → Investment Score capped at 45)."
    if score_result.p5_cap_applied:
        caps_note += "\n⚠ P5 Implausible Cap applied (P5 = implausible → Quality cluster capped)."

    outcome_display = score_result.outcome.value.upper().replace("_", " ")

    return f"""\
You must write the plain-language explanation for this investment verdict.
The outcome tier and investment score below are FINAL — they were computed deterministically.
You cannot change them. Your job is to explain them clearly and honestly.

════════════════════════════════════
COMPUTED VERDICT (DO NOT CHANGE)
════════════════════════════════════
Outcome tier: {outcome_display}
Investment Score: {score_result.investment_score:.1f} / 100
Confidence: {score_result.deterministic_confidence} (ceiling: {score_result.confidence_ceiling}){caps_note}

Cluster Scores:
  Relevance:  {cs.relevance:.2f}
  Authority:  {cs.authority:.2f}
  Quality:    {cs.quality:.2f}
  Risk:       {cs.risk:.2f}
  Risk ×:     {cs.risk_multiplier:.2f}

════════════════════════════════════
EVALUATION CONTEXT
════════════════════════════════════
Prospect domain: {ctx.prospect_domain}
Evaluation mode: {ctx.mode or "not detected"}
Mode sub-type: {ctx.mode_b_subtype or "n/a"}
Confidence ceiling reason: {_ceiling_reason(ctx)}

Data quality:
{_format_data_quality(ctx)}

════════════════════════════════════
ANTI-BIAS RULES FOR THIS CALL
════════════════════════════════════
1. You cannot change or soften the outcome tier. Write the explanation that fits {outcome_display}.
2. If D4 (editorial integrity) drove the outcome, you MUST reference it in primary_reason.
3. Supporting signals must reference actual data — not generic praise or criticism.
4. Conditions (with_conditions only) must be specific and actionable.
5. Do not apologise for low confidence. State factually what data was and was not available.

Use the tool to return all explanation fields. No text outside the tool call.\
"""


# ── Response parsers ──────────────────────────────────────────────────────────

def _parse_signal_scores(tool_input: dict[str, Any]) -> SignalScores:
    p5_raw = tool_input.get("p5_placement_feasibility", "workable")
    try:
        p5 = PlacementFeasibility(p5_raw)
    except ValueError:
        p5 = PlacementFeasibility.WORKABLE

    return SignalScores(
        p1_topical_relevance=_clamp(tool_input.get("p1_topical_relevance", 0.5)),
        p1_rationale=tool_input.get("p1_rationale", ""),
        p2_content_quality=_clamp(tool_input.get("p2_content_quality", 0.5)),
        p2_rationale=tool_input.get("p2_rationale", ""),
        p4_obl_quality=_clamp(tool_input.get("p4_obl_quality", 0.5)),
        p4_rationale=tool_input.get("p4_rationale", ""),
        p5_placement_feasibility=p5,
        p5_rationale=tool_input.get("p5_rationale", ""),
        d1_topical_coherence=_clamp(tool_input.get("d1_topical_coherence", 0.5)),
        d1_rationale=tool_input.get("d1_rationale", ""),
        d4_editorial_integrity=_clamp(tool_input.get("d4_editorial_integrity", 0.5)),
        d4_rationale=tool_input.get("d4_rationale", ""),
        d9_geo_language_match=_clamp(tool_input.get("d9_geo_language_match", 0.5)),
        d9_rationale=tool_input.get("d9_rationale", ""),
        language_match=_clamp(tool_input.get("language_match", 0.5)),
        data_quality_notes=tool_input.get("data_quality_notes", ""),
    )


def _assemble_verdict(
    ctx: IDEContext,
    score_result: ScoreResult,
    tool_input: dict[str, Any],
) -> InvestmentVerdict:
    return InvestmentVerdict(
        outcome=score_result.outcome,
        investment_score=score_result.investment_score,
        evaluation_mode=ctx.mode,
        mode_b_subtype=ctx.mode_b_subtype,
        hard_exclusion_triggered=False,
        cluster_scores=score_result.cluster_scores,
        headline=tool_input.get("headline"),
        primary_reason=tool_input.get("primary_reason"),
        supporting_signals=tool_input.get("supporting_signals") or [],
        conditions=tool_input.get("conditions") or [],
        mode_qualifier=tool_input.get("mode_qualifier"),
        confidence_rationale=tool_input.get("confidence_rationale"),
        confidence=score_result.deterministic_confidence,
        confidence_ceiling=score_result.confidence_ceiling,
        data_quality=ctx.data_quality,
    )


# ── LLM call with retry ───────────────────────────────────────────────────────

async def _call_with_retry(llm, system, messages, tool, max_tokens):
    """Call the LLM once. On LLMError, retry exactly once before raising."""
    try:
        return await llm.call_with_tool(
            system=system,
            messages=messages,
            tool=tool,
            model=_HAIKU_MODEL,
            max_tokens=max_tokens,
        )
    except LLMError:
        # One retry — transient API errors (rate limit, timeout) usually resolve
        return await llm.call_with_tool(
            system=system,
            messages=messages,
            tool=tool,
            model=_HAIKU_MODEL,
            max_tokens=max_tokens,
        )


# ── Content formatting helpers ────────────────────────────────────────────────

def _crawl_attr(crawl, attr: str) -> str | None:
    return getattr(crawl, attr, None)


def _crawl_status(crawl) -> str:
    if crawl is None:
        return "no (blocked)"
    markdown = _crawl_attr(crawl, "markdown") or ""
    if len(markdown.split()) < 50:
        return "partial (JS-heavy, content limited)"
    return "yes"


def _extract_h1(crawl) -> str:
    markdown = _crawl_attr(crawl, "markdown") or ""
    match = re.search(r'^# (.+)$', markdown, re.MULTILINE)
    return match.group(1).strip() if match else "not found"


def _extract_headings(crawl, level: int = 2) -> str:
    markdown = _crawl_attr(crawl, "markdown") or ""
    prefix = "#" * level + " "
    headings = [
        line[len(prefix):].strip()
        for line in markdown.splitlines()
        if line.startswith(prefix)
    ]
    if not headings:
        return "not found"
    if len(headings) > 10:
        extra = len(headings) - 10
        return ", ".join(headings[:10]) + f" ... [+{extra} more]"
    return ", ".join(headings)


def _compress_content(crawl, word_limit: int = 600) -> str:
    if crawl is None:
        return "not available"
    markdown = _crawl_attr(crawl, "markdown") or ""
    words = markdown.split()
    if len(words) <= word_limit:
        return markdown
    return " ".join(words[:word_limit]) + f"\n\n[content truncated — {len(words) - word_limit} words omitted]"


def _format_obl(crawl, limit: int = 20) -> str:
    markdown = _crawl_attr(crawl, "markdown") or ""
    # Extract markdown links to external domains
    links = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', markdown)
    external = [(text, url) for text, url in links if _is_external(crawl, url)]
    if not external:
        return "none found"
    lines = [f"{text} → {_domain_only(url)}" for text, url in external[:limit]]
    result = "\n".join(lines)
    if len(external) > limit:
        result += f"\n... [+{len(external) - limit} more links]"
    return result


def _format_articles(crawls: list, urls: list[str]) -> str:
    if not crawls:
        return "No articles could be sampled."
    parts = []
    for i, crawl in enumerate(crawls, 1):
        url = getattr(crawl, "url", urls[i - 1] if i - 1 < len(urls) else "unknown")
        title = _crawl_attr(crawl, "title") or "not available"
        h2_list = _extract_headings(crawl, level=2)
        excerpt = _compress_content(crawl, word_limit=400)
        obl = _format_obl(crawl, limit=15)
        parts.append(
            f"── Article {i} ──\n"
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"H2 subheadings: {h2_list}\n\n"
            f"Content excerpt:\n{excerpt}\n\n"
            f"Outbound links found:\n{obl}"
        )
    return "\n\n".join(parts)


def _format_domain_samples(crawls: list) -> str:
    if not crawls:
        return "No domain sample pages available."
    parts = []
    for i, crawl in enumerate(crawls, 1):
        url = _crawl_attr(crawl, "url") or "unknown"
        title = _crawl_attr(crawl, "title") or "not available"
        excerpt = _compress_content(crawl, word_limit=300)
        obl = _format_obl(crawl, limit=10)
        parts.append(
            f"── Sample {i} ──\n"
            f"URL: {url}\n"
            f"Title: {title}\n\n"
            f"Content excerpt (300 words):\n{excerpt}\n\n"
            f"Outbound links found:\n{obl}"
        )
    return "\n\n".join(parts)


def _format_data_quality(ctx: IDEContext) -> str:
    dq = ctx.data_quality
    return "\n".join(f"  {k}: {v}" for k, v in dq.items())


def _ceiling_reason(ctx: IDEContext) -> str:
    if ctx.mode == "specific_placement":
        return "Mode A — ceiling is high (specific placement page evaluated)."
    if ctx.mode_b_subtype == "category_url":
        return "Mode B/category — ceiling is medium (section URL evaluated, no specific article)."
    return "Mode B/domain_inferred — ceiling is low (section inferred, not directly provided)."


def _is_external(crawl, url: str) -> bool:
    domain = _crawl_attr(crawl, "url")
    if not domain:
        return True
    from urllib.parse import urlparse
    crawl_domain = urlparse(domain).netloc
    link_domain = urlparse(url).netloc
    return crawl_domain != link_domain


def _domain_only(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc or url


def _clamp(val: Any) -> float:
    try:
        return max(0.0, min(1.0, float(val)))
    except (TypeError, ValueError):
        return 0.5
