# Opportunity Evaluation Prompt — Version 1

**Status:** Pre-implementation specification — awaiting approval before Sprint 3 code is written  
**Date:** 2026-06-27  
**Model target:** `claude-haiku-4-5-20251001` (both calls)  
**Temperature:** `0` (mandatory — do not change)  
**Max tokens:** Call 1: `2500` / Call 2: `1500`  
**Method:** Anthropic tool use — `tool_choice: {"type": "tool", "name": "<tool_name>"}`

This file is the complete specification for both LLM calls in the Investment Decision Engine (§3.5).

**Call 1 — Signal Extraction:** Receives crawled content from the prospect site. Produces structured float scores for each signal. No verdict, no recommendation — only scored signals.

**Call 2 — Verdict Assembly:** Receives all computed cluster scores and the deterministic Investment Score and outcome tier. Produces the plain-language explanation. Cannot change the outcome.

Contains:
1. Shared system prompt (used for both calls)
2. Call 1 user message template + variable definitions + tool schema
3. Call 2 user message template + variable definitions + tool schema
4. Anti-bias rules (both calls)
5. Signal scoring reference
6. Prompt changelog

Do not paraphrase, shorten, or reorder either prompt. If a change is needed, increment the version and document it in the changelog at the bottom of this file.

---

## 1. Shared System Prompt

Copy this verbatim as the `system` parameter for both API calls.

```
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
All output must go inside the tool call. Do not write any text before or after the tool call. If you are uncertain about a field value, use your best judgment and document the uncertainty in the rationale field — do not omit the field or return null for required scores.
```

---

## 2. Call 1 — Signal Extraction

### 2.1 Purpose

Call 1 asks Haiku to read the crawled content and score each signal as a float or enum. The output (`SignalScores`) feeds directly into the deterministic scoring formulas in `ide_scorer.py`. The LLM produces numbers, not words. No verdict language, no investment recommendation.

### 2.2 User Message Template — Mode A (Specific Placement)

Copy as the `content` of the user message, after substituting all `{variables}`.

Unfilled variables must be replaced with `not available` — never leave a `{variable}` placeholder in the final prompt.

```
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
Word count: {placement_word_count}
H1: {placement_h1}
H2 subheadings: {placement_h2_list}

Content:
{placement_content}

Outbound links found on this page:
{placement_obl_list}

════════════════════════════════════
DOMAIN SAMPLE PAGES
(3 additional pages from the same domain, used to assess domain-level signals)
════════════════════════════════════
{for each domain sample page:}
── Sample {n} ──
URL: {sample_n_url}
Title: {sample_n_title}
Content excerpt (first 300 words): {sample_n_excerpt}
Outbound links found: {sample_n_obl_list}

════════════════════════════════════
DATA AVAILABILITY FLAGS
════════════════════════════════════
Placement page crawled: {placement_crawled}
Domain sample pages available: {domain_sample_count} of 3
DataForSEO domain metrics available: {domain_metrics_available}

════════════════════════════════════
SCORING INSTRUCTIONS
════════════════════════════════════
Score each signal using the tool. Use the signal reference (Section 5 of the prompt spec) for exact definitions.

For P5 (Placement Feasibility) in Mode A: score based on whether a link to the target topic could be placed WITHIN THIS SPECIFIC ARTICLE naturally. Consider the article's existing angle, subtopics, and outbound link pattern. A link that would require rewriting significant portions of the article to accommodate should score "forced" or lower.

Use the tool to return all scores. Do not add a recommendation or investment conclusion — that is computed separately.
```

### 2.3 User Message Template — Mode B (Guest Post Opportunity)

```
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
Mode: Guest Post Opportunity — {mode_b_subtype}
{if mode_b_subtype == "category_url":}
You are evaluating a specific content section (category/topic page) of this site.
Section evaluated: {section_url}
{if mode_b_subtype == "domain_inferred":}
You are evaluating a content section inferred as the best topical match for the target.
Section inferred: {inferred_section_url}
Section inference basis: {section_inference_note}

You are assessing the SECTION as a whole, not any individual article. Scores for P1 and P2 reflect the average quality of the sampled articles, not the best or worst individual article.

════════════════════════════════════
SAMPLED ARTICLES FROM SECTION
({article_count} articles sampled)
════════════════════════════════════
{for each sampled article:}
── Article {n} ──
URL: {article_n_url}
Title: {article_n_title}
Word count: {article_n_word_count}
H2 subheadings: {article_n_h2_list}
Content excerpt (first 400 words): {article_n_excerpt}
Outbound links found: {article_n_obl_list}

════════════════════════════════════
DOMAIN SAMPLE PAGES
(additional pages from outside the evaluated section, used for domain-level signals)
════════════════════════════════════
{for each domain sample page:}
── Sample {n} ──
URL: {sample_n_url}
Title: {sample_n_title}
Content excerpt (first 300 words): {sample_n_excerpt}
Outbound links found: {sample_n_obl_list}

════════════════════════════════════
DATA AVAILABILITY FLAGS
════════════════════════════════════
Articles sampled: {article_count}
Domain sample pages available: {domain_sample_count}
DataForSEO domain metrics available: {domain_metrics_available}

════════════════════════════════════
SCORING INSTRUCTIONS
════════════════════════════════════
Score each signal using the tool. Use the signal reference (Section 5 of the prompt spec) for exact definitions.

P1 and P2: average across all sampled articles — do not let one outlier article dominate.

P5 (Placement Feasibility) in Mode B: score based on whether a GUEST POST written for this SECTION could naturally include a link to the target topic. Consider whether the section publishes content that would logically mention or link to content about {target_topic}. This is about the feasibility of writing a relevant guest post — not about whether the current articles contain such a link.

D4 (Editorial Integrity): evaluate across ALL sampled articles and domain sample pages. Consistent OBL patterns reveal editorial standards better than any single page.

Use the tool to return all scores. Do not add a recommendation or investment conclusion — that is computed separately.
```

### 2.4 Call 1 Variable Definitions

**Target context variables**

**`{target_url}`**
Full URL of the page being analyzed for link-building. Example: `https://example.com/seo-guide`.

**`{target_topic}`**
A concise description of what the target page covers. Derived from the page's H1 and primary keyword. Example: `A beginner's guide to technical SEO fundamentals`. Maximum 120 characters.

**`{target_audience}`**
The intended readership of the target page. Derived from the page's content and positioning. Example: `In-house SEO practitioners and marketing managers at mid-size companies`. Maximum 120 characters.

---

**Mode A placement page variables**

**`{placement_url}`**
The full URL of the specific article being evaluated for link placement.

**`{placement_title}`**
`<title>` tag content verbatim.

**`{placement_word_count}`**
Visible body word count, rounded to nearest 50.

**`{placement_h1}`**
First `<h1>` tag verbatim. If absent: `not found`. If multiple: `multiple — primary: [text]`.

**`{placement_h2_list}`**
All `<h2>` tags verbatim, comma-separated. Maximum 10. If more than 10, include the first 10 and append `... [+N more]`.

**`{placement_content}`**
Compressed page content: H1 + all H2s + first 600 words of visible body text. Strip navigation, footer, sidebar, cookie banners. Do not send raw HTML.

**`{placement_obl_list}`**
All outbound links from this page (links to other domains), formatted as `anchor text → destination domain`. Maximum 20 links. If more than 20: include first 20, append `... [+N more links]`.

---

**Mode B article variables**

**`{article_count}`**
The number of articles sampled (3–5).

**`{article_n_url}`**, **`{article_n_title}`**, **`{article_n_word_count}`**, **`{article_n_h2_list}`**
Same definitions as placement page equivalents, applied per sampled article.

**`{article_n_excerpt}`**
First 400 words of visible body text. Strip navigation, footer, sidebar. Do not send raw HTML.

**`{article_n_obl_list}`**
Same as placement_obl_list, maximum 15 per article.

**`{section_url}`** / **`{inferred_section_url}`**
The URL of the section being evaluated (category page, inferred section root, or homepage if no section was inferred).

**`{section_inference_note}`**
A one-sentence description of how the section was chosen. Example: `Identified via sitemap.xml — section /resources/seo/ matched target topic with highest article density`.

---

**Domain sample variables (both modes)**

**`{sample_n_url}`**, **`{sample_n_title}`**, **`{sample_n_excerpt}`**, **`{sample_n_obl_list}`**
Three domain sample pages from outside the evaluated section. Same compression rules as article excerpts, 300 words max. Used for D1 (topical coherence) and D4 (editorial integrity) domain-level assessment.

---

**Data availability flags**

**`{placement_crawled}`** — `yes` / `partial (JS-heavy, content limited)` / `no (blocked)`
**`{domain_sample_count}`** — integer 0–3
**`{domain_metrics_available}`** — `yes` / `no`

---

### 2.5 Call 1 Tool Schema

```json
{
  "name": "extract_investment_signals",
  "description": "Record scored content and authority signals for the prospect site. All float scores are 0.0–1.0. All fields are required. Do not include any investment recommendation — that is computed separately from these scores.",
  "input_schema": {
    "type": "object",
    "required": [
      "p1_topical_relevance",
      "p1_rationale",
      "p2_content_quality",
      "p2_rationale",
      "p4_obl_quality",
      "p4_rationale",
      "p5_placement_feasibility",
      "p5_rationale",
      "d1_topical_coherence",
      "d1_rationale",
      "d4_editorial_integrity",
      "d4_rationale",
      "d9_geo_language_match",
      "d9_rationale",
      "language_match",
      "data_quality_notes"
    ],
    "properties": {
      "p1_topical_relevance": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "How closely does the evaluated content (placement page or section) cover the same topic as the target page? Score based on semantic overlap, not keyword presence. 1.0 = directly about the same topic. 0.7 = closely related, same vertical. 0.4 = loosely related, adjacent vertical. 0.1 = essentially unrelated. In Mode B, average this score across sampled articles."
      },
      "p1_rationale": {
        "type": "string",
        "maxLength": 200,
        "description": "One sentence citing the specific content observation that determined this score."
      },
      "p2_content_quality": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "How substantive, accurate, and well-written is the content? Score independently of topical relevance. 1.0 = well-researched, clearly written, publication-grade. 0.7 = solid, minor gaps. 0.4 = thin, generic, or partially accurate. 0.1 = low-effort, inaccurate, or AI-generated filler with no substance. In Mode B, average across sampled articles."
      },
      "p2_rationale": {
        "type": "string",
        "maxLength": 200,
        "description": "One sentence citing the specific content observation that determined this score."
      },
      "p4_obl_quality": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "What is the quality of the outbound link profile on this page or section? 1.0 = selective, contextually relevant links to authoritative sources only. 0.7 = mostly relevant, a few unnecessary links. 0.4 = mixed — some contextual links, some that appear commercial or irrelevant. 0.1 = excessive commercial links, paid link patterns, links to many unrelated domains. 0.0 = clear PBN or link farm indicators. In Mode B, average across sampled articles."
      },
      "p4_rationale": {
        "type": "string",
        "maxLength": 200,
        "description": "One sentence citing specific outbound link observations."
      },
      "p5_placement_feasibility": {
        "type": "string",
        "enum": ["natural", "workable", "forced", "implausible"],
        "description": "How feasible is a link placement to the target topic? Mode A: could a link to the target page be placed in THIS article without damaging it? Mode B: could a guest post for THIS SECTION naturally include a link to the target topic? natural = fits without any editorial forcing. workable = fits with minor framing. forced = requires a contrived angle. implausible = incompatible — no plausible editorial framing exists."
      },
      "p5_rationale": {
        "type": "string",
        "maxLength": 200,
        "description": "One sentence explaining why this feasibility level was assigned. Be specific about what would make placement natural or difficult."
      },
      "d1_topical_coherence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "How topically focused is this domain as a whole? Assess from the domain sample pages. 1.0 = tightly focused on one topic area. 0.7 = primary topic clear with adjacent coverage. 0.4 = broad, multi-niche, some relevant content. 0.1 = no coherent topic focus — random or opportunistic publishing."
      },
      "d1_rationale": {
        "type": "string",
        "maxLength": 200,
        "description": "One sentence citing domain sample page observations."
      },
      "d4_editorial_integrity": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Does this domain publish content based on editorial merit, or do commercial relationships visibly drive publishing decisions? This is the most consequential signal. Assess across ALL pages provided. 1.0 = content is clearly editorially driven; outbound links are selective and contextual; no visible monetisation of link placement. 0.7 = mostly editorial with minor commercial signals. 0.4 = mixed — some genuine editorial content alongside visible link-commercial patterns. 0.1 = editorial integrity severely compromised — links appear sold, content appears to exist primarily to host outbound links. 0.0 = link farm or PBN indicators."
      },
      "d4_rationale": {
        "type": "string",
        "maxLength": 250,
        "description": "Two sentences: first cite the most important editorial integrity observation (positive or negative); second describe the overall OBL pattern across the pages reviewed."
      },
      "d9_geo_language_match": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Does this domain primarily serve audiences compatible with the target page's audience? Consider TLD, content language, geographic references in content, and hreflang tags if visible. 1.0 = same geographic target and language. 0.7 = overlapping audience (e.g., global English site targeting a compatible region). 0.4 = partial overlap. 0.1 = different primary geography with minimal audience overlap. 0.0 = completely incompatible (different language, closed national market)."
      },
      "d9_rationale": {
        "type": "string",
        "maxLength": 150,
        "description": "One sentence noting the TLD, language, and any geographic signals observed."
      },
      "language_match": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Is the content language compatible with the target page? 1.0 = same language. 0.5 = bilingual site with the target language present. 0.2 = minor content in target language, primarily another language. 0.0 = completely different language."
      },
      "data_quality_notes": {
        "type": "string",
        "maxLength": 300,
        "description": "Note any signals that were unavailable, pages that were inaccessible, or data that would have changed any score if available. Write 'none' if all data was available and complete. This field is stored for audit and debugging — be specific."
      }
    }
  }
}
```

---

## 3. Call 2 — Verdict Assembly

### 3.1 Purpose

Call 2 receives the deterministic outcome tier and all cluster scores computed by `ide_scorer.py`. It produces the plain-language explanation — the headline, primary reason, conditions (if any), and mode qualifier (Mode B only). **The LLM cannot change the outcome tier or the Investment Score.** Both arrive as inputs and must be reflected faithfully in the output.

### 3.2 User Message Template

```
Write the investment verdict explanation for the following prospect site evaluation.

════════════════════════════════════
CONTEXT
════════════════════════════════════
Prospect site: {prospect_url}
Target page: {target_url}
Target topic: {target_topic}
Evaluation mode: {evaluation_mode_label}
{if mode_b:}Mode detail: {mode_b_detail}

════════════════════════════════════
COMPUTED SCORES (do not change these)
════════════════════════════════════
Investment Score: {investment_score}/100
Outcome tier (pre-determined): {outcome_tier}

Cluster scores:
  Relevance:  {relevance_score:.2f}  (target: ≥ 0.55 for recommended)
  Authority:  {authority_score:.2f}
  Quality:    {quality_score:.2f}
  Risk score: {risk_score:.2f}  (multiplier applied: {risk_multiplier:.2f}x)

Key signal values:
  P1 Topical relevance:    {p1:.2f}
  P2 Content quality:      {p2:.2f}
  P4 OBL quality:          {p4:.2f}
  P5 Placement feasibility:{p5}
  D1 Topical coherence:    {d1:.2f}
  D4 Editorial integrity:  {d4:.2f}
  D9 Geo/language match:   {d9:.2f}
  Domain referring domains:{referring_domains}
  Traffic tier:            {traffic_tier}
  Traffic trajectory:      {traffic_trajectory}
  Spam risk:               {spam_risk}

Score modifiers applied:
  Editorial integrity cap (D4 < 0.30): {editorial_cap_applied}
  Placement feasibility cap (P5 = implausible): {p5_cap_applied}

Confidence level: {confidence}
Confidence ceiling (mode-based): {confidence_ceiling}

════════════════════════════════════
BOTTLENECK CONTEXT (if available)
════════════════════════════════════
Target page bottleneck: {bottleneck_constraint}
Links are the answer: {links_are_the_answer}

════════════════════════════════════
INSTRUCTIONS
════════════════════════════════════
The outcome tier ({outcome_tier}) is final and has been determined by the scoring model. Your task is to explain it in plain language that a strategist could present to a client.

Do not question the outcome. Do not reinterpret the scores. Do not suggest that the outcome might be different with more data — that is already reflected in the confidence level.

For a "recommended" verdict: the headline and primary reason should reinforce WHY this is a good investment. Name the strongest signals. Do not undersell it.

For a "with_conditions" verdict: name the specific condition(s) that prevent a clean recommendation. Each condition must be addressable and specific — not generic advice like "improve content quality."

For a "not_recommended" verdict: the primary reason must name the specific disqualifying signal. Do not soften the verdict. An honest "not recommended" is more useful than a hedged one.

For a "with_conditions" or "not_recommended" verdict where D4 < 0.30: the editorial integrity concern must be named explicitly as a primary factor, not buried in supporting signals.

Use the tool to return the verdict explanation.
```

### 3.3 Call 2 Variable Definitions

**`{prospect_url}`**
Full URL of the evaluated prospect site or page.

**`{evaluation_mode_label}`**
Human-readable mode label:
- `Specific Placement Evaluation` (Mode A)
- `Guest Post Opportunity — Category Section` (Mode B / category_url)
- `Guest Post Opportunity — Inferred Section` (Mode B / domain_inferred)

**`{mode_b_detail}`**
For Mode B only: one sentence describing what was evaluated. Example: `Evaluated based on 4 articles sampled from the /resources/seo/ section (inferred as best topical match for the target topic).`

**`{investment_score}`**
Float, rounded to one decimal. Example: `62.4`.

**`{outcome_tier}`**
One of: `recommended` / `with_conditions` / `not_recommended` / `insufficient_data`.

**`{relevance_score}`, `{authority_score}`, `{quality_score}`, `{risk_score}`, `{risk_multiplier}`**
Float values from `ide_scorer.py`. Format to 2 decimal places.

**`{p1}` through `{d9}`**
Signal float scores or enum value (`p5`) from `SignalScores`.

**`{referring_domains}`**
Integer count, or `unknown` if unavailable.

**`{traffic_tier}`**
One of: `high` / `medium` / `low` / `minimal` / `unknown`.

**`{traffic_trajectory}`**
One of: `growing` / `stable` / `declining` / `unknown`.

**`{spam_risk}`**
Float formatted to 2 decimal places, or `unknown`.

**`{editorial_cap_applied}`**
`yes` or `no`.

**`{p5_cap_applied}`**
`yes` or `no`.

**`{confidence}`**
One of: `low` / `medium` / `high`.

**`{confidence_ceiling}`**
One of: `low` / `medium` / `high`. The ceiling applied based on evaluation mode.

**`{bottleneck_constraint}`**
The `primary_constraint` value from the target page's Bottleneck verdict, if available. Otherwise `not available`.

**`{links_are_the_answer}`**
`true` / `false` / `not available`.

---

### 3.4 Call 2 Tool Schema

```json
{
  "name": "assemble_investment_verdict",
  "description": "Produce the plain-language explanation for the pre-computed investment verdict. The outcome tier and Investment Score are fixed inputs — do not alter them. All fields are required.",
  "input_schema": {
    "type": "object",
    "required": [
      "headline",
      "primary_reason",
      "supporting_signals",
      "confidence_rationale"
    ],
    "properties": {
      "headline": {
        "type": "string",
        "maxLength": 130,
        "description": "One declarative sentence a strategist could read aloud to a client. Must state the investment recommendation and name the single most important reason. Must be specific to this prospect — not generic advice. Example (recommended): 'Strong investment — high topical relevance and clean editorial standards suggest a link here would carry real authority.' Example (not_recommended): 'Avoid — editorial integrity score of 0.18 indicates link selling patterns that would make any placement low-value.'"
      },
      "primary_reason": {
        "type": "string",
        "maxLength": 250,
        "description": "The dominant factor that determined the outcome. Must cite a specific signal value or observation. For recommended: the strongest positive signal. For with_conditions: the specific condition preventing a clean recommendation. For not_recommended: the specific disqualifying factor. No vague language — 'the content quality is poor' is not acceptable; 'P2 content quality scored 0.24 — sampled articles were thin, averaging under 400 words with no supporting data or expert attribution' is acceptable."
      },
      "supporting_signals": {
        "type": "array",
        "minItems": 1,
        "maxItems": 4,
        "description": "Additional notable signals that supported the verdict. Each item is one sentence. Cite specific values where relevant. Do not repeat the primary_reason.",
        "items": {
          "type": "string",
          "maxLength": 150
        }
      },
      "conditions": {
        "type": "array",
        "minItems": 0,
        "maxItems": 3,
        "description": "Required for with_conditions outcome only. Each condition must be a specific, addressable requirement. Not applicable to recommended or not_recommended — omit this field or return an empty array for those outcomes. Example condition: 'Confirm that the target section accepts guest contributions — the site does not currently show a submission process.' Example condition: 'Negotiate placement within an existing article rather than a new post, as D4 is borderline (0.31).'",
        "items": {
          "type": "string",
          "maxLength": 180
        }
      },
      "mode_qualifier": {
        "type": "string",
        "maxLength": 200,
        "description": "For Mode B evaluations only. A sentence that qualifies the confidence level by explaining what the evaluation is and is not based on. Example: 'This evaluation is based on 4 sampled articles from the /resources/seo/ section and may not represent all content published there — a direct placement URL would allow a more precise assessment.' Omit for Mode A (return null)."
      },
      "confidence_rationale": {
        "type": "string",
        "maxLength": 250,
        "description": "Why this confidence level was assigned. Reference which signals were available and which were missing. Example: 'Medium — 4 articles sampled from the identified section; domain metrics available; no individual placement page reviewed (Mode B ceiling: medium). Topical relevance and editorial integrity signals were consistent across all sampled articles, supporting the verdict direction.'"
      }
    }
  }
}
```

---

## 4. Anti-Bias Rules

These rules apply to BOTH calls. They are embedded in the system prompt (Rule 1–5), but are documented here explicitly for engineers reviewing or updating the prompts.

**4.1 The outcome must follow the evidence, not the use case.**
The user wants to place a link. The system must not produce a favourable verdict because a link is wanted. D4 (editorial integrity) is the primary guard against this: a site with weak editorial integrity is not a good investment regardless of topical relevance.

**4.2 "Guest post opportunity" is not an endorsement.**
Mode B evaluations assess feasibility, not desirability. A site that is feasible to approach is not automatically worth the investment. The scoring model applies the same Investment Score thresholds regardless of mode.

**4.3 Call 2 cannot override the deterministic verdict.**
The outcome tier arrives as a computed input. The Call 2 prompt explicitly states "the outcome tier is final." Any observed deviation (e.g., the model writes a headline inconsistent with the outcome tier) must be caught by `validate_investment_verdict()` and recorded in `validation_overrides`.

**4.4 D4 < 0.30 must appear in the primary reason, not a supporting signal.**
When an editorial integrity cap triggered (`editorial_cap_applied = yes`), the Call 2 instructions require this to appear in `primary_reason`. Validation checks this constraint.

**4.5 Confidence ceiling is structural, not advisory.**
If `confidence_ceiling` is `low` (Mode B / domain_inferred), the model's `confidence_rationale` must acknowledge the structural limitation. The returned confidence value is enforced deterministically by `ide_scorer.py` and checked by `validate_investment_verdict()` — not by the model.

---

## 5. Signal Scoring Reference

This table is for prompt engineers and reviewers. It defines the intended meaning and threshold examples for each scored signal. The Call 1 tool schema descriptions are derived from this reference — if they conflict, this table takes precedence.

| Signal | Code | Range | 1.0 | 0.7 | 0.4 | 0.1 |
|---|---|---|---|---|---|---|
| Topical relevance | P1 | 0–1 | Same topic, same angle | Same vertical, adjacent angle | Loosely related niche | Unrelated niche |
| Content quality | P2 | 0–1 | Publication-grade, well-researched | Solid, minor gaps | Thin, generic, partially accurate | Low-effort, filler |
| OBL quality | P4 | 0–1 | Selective, contextual, authoritative destinations | Mostly relevant, few unnecessary | Mixed commercial + contextual | Indiscriminate or paid-link patterns |
| Topical coherence | D1 | 0–1 | Tightly focused, one topic area | Primary topic clear, adjacent coverage | Broad, multi-niche, some relevant | No coherent topic focus |
| Editorial integrity | D4 | 0–1 | Clearly editorial, no commercial link signals | Mostly editorial, minor commercial | Mixed — some editorial, some commercial | Links appear sold; content exists to host OBLs |
| Geo/language match | D9 | 0–1 | Same country/language as target audience | Overlapping audience (global English, compatible region) | Partial overlap | Different primary geography, minimal overlap |
| Language match | — | 0–1 | Same language | Bilingual, target language present | Minor content in target language | Completely different language |

**P5 Placement Feasibility enum:**

| Value | Meaning |
|---|---|
| `natural` | A link would fit without any editorial forcing — the content already covers adjacent ground |
| `workable` | A link could fit with minor framing — one sentence of context would make it natural |
| `forced` | A link would require a contrived angle or significant editorial restructuring |
| `implausible` | No plausible editorial framing — incompatible content or audience |

**Scoring in Mode B:** P1, P2, P4 must be averaged across sampled articles. Do not score based on the best or worst single article. P5 is scored for the section as a whole (feasibility of writing a guest post), not any individual article.

---

## 6. Prompt Changelog

| Version | Date | Change | Reason |
|---|---|---|---|
| v1 | 2026-06-27 | Initial version — both calls specified | Pre-Sprint-3 deliverable required by architecture §5.5 |

When changes are made, add a row here. Record what changed (specific text) and why. The prompt version used for each evaluation is stored in `opportunities.prompt_version` in the database.
