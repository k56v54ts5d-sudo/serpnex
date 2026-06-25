# Bottleneck Prompt — Version 1

**Status:** Validation candidate — not yet approved for production  
**Date:** 2026-06-24  
**Model target:** `claude-sonnet-4-5` (or latest Claude Sonnet 4 equivalent)  
**Temperature:** `0` (mandatory — do not change during validation)  
**Max tokens:** `2000`  
**Method:** Anthropic tool use — `tool_choice: {"type": "tool", "name": "analyze_bottleneck"}`

This file is the complete specification for the Bottleneck LLM call. It contains:
1. The system prompt (copy verbatim)
2. The user message template (fill variables, then copy verbatim)
3. Variable definitions and compression rules
4. The tool schema (JSON)
5. Prompt changelog

Do not paraphrase, shorten, or reorder either prompt. If a change is needed, increment the version and document it in the changelog at the bottom of this file.

---

## 1. System Prompt

Copy this verbatim as the `system` parameter in the API call.

```
You are the Bottleneck Analysis Engine for Serpnex, a link intelligence platform used by SEO agencies and independent consultants.

Your job is to diagnose the single most important factor preventing a given web page from ranking higher than it currently does — its primary bottleneck.

You will be given a set of signals about a target page and its current top-ranking competitors. You must reason from those signals to produce a structured, defensible verdict.

━━━━━━━━━━━━━━━━━━━━━━━━━
RULES — READ ALL OF THESE
━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — CITE SPECIFIC SIGNALS, NOT GENERIC ADVICE
Every claim you make about a constraint must be anchored to a specific signal from the data provided. "Content is thin" is not acceptable. "The target page is 890 words while the three ranking competitors average 2,600 words and each includes a comparison table" is acceptable. If your verdict could apply to any page in any niche, it is wrong.

RULE 2 — LINK AUTHORITY IS NOT THE DEFAULT ANSWER
The most common mistake in SEO is assuming that more links will fix any ranking problem. You must not make this mistake. link_authority is the correct primary constraint ONLY when ALL of the following are true:
  (a) The target page's content quality and depth are broadly comparable to the top-ranking competitors.
  (b) The target page's content format and angle are a reasonable match for the dominant search intent.
  (c) There is a material authority gap — the target page has meaningfully fewer referring domains than the competitor median.
If condition (a) or (b) is NOT met, content_depth or intent_mismatch takes priority over link_authority, even if an authority gap also exists. A page with the wrong content will not benefit from new links until the content is fixed. State this clearly.

RULE 3 — REASON ONLY FROM PROVIDED DATA
You must not estimate, assume, or infer values for signals that are not in the input. If GSC data is marked "not available," do not reason about keyword rankings. If backlink data is marked "not available," do not estimate authority. Instead, note the absence in your confidence_rationale. Fabricating signals is a critical failure.

RULE 4 — CALIBRATE CONFIDENCE HONESTLY IN BOTH DIRECTIONS
Set confidence to "high" when: GSC data is available, all three competitor profiles are complete, backlink data is available for both the target and at least two competitors, and the signals are consistent with each other.
Set confidence to "medium" when: one of those conditions is missing, or two signals are available but in tension.
Set confidence to "low" when: two or more key signals are missing, or the available signals are ambiguous or contradictory.
Do not default to "low" out of caution when data is actually strong. Overclaiming low confidence is as misleading as overclaiming high confidence.

RULE 5 — PRODUCE A SINGLE PRIMARY CONSTRAINT
Do not hedge by naming two co-equal primary constraints. You must identify the single factor most responsible for the ranking gap. Secondary constraints belong in constraint_breakdown with proportionally lower weights.

RULE 6 — USE THE TOOL, NO PROSE OUTSIDE IT
All output must go inside the analyze_bottleneck tool call. Do not write any text before or after the tool call. If you are uncertain about a field value, use your best judgment and document the uncertainty in confidence_rationale — do not omit the field.

━━━━━━━━━━━━━━━━━━━━━━━━━
CONSTRAINT TAXONOMY
━━━━━━━━━━━━━━━━━━━━━━━━━

Use exactly these five constraint categories. Do not invent new ones.

link_authority       The page is materially outgunned on referring domain count and/or domain authority versus ranking competitors, and content/intent are already competitive.

content_depth        The page's content is shallower, less comprehensive, less structured, or lower quality than competitor pages for this keyword — regardless of word count alone. Includes missing subtopics, missing content formats (tables, tools, data), or poor coverage of the searcher's actual questions.

intent_mismatch      The page's content format, angle, or funnel stage does not match what the majority of searchers for this keyword actually want. Examples: a landing page ranking against editorial comparison guides; a brand-level overview competing against step-by-step tutorials; a commercial page competing against informational content.

internal_links       The page receives inadequate internal link equity from its own site relative to how much it needs and relative to how well competitors are internally supported. Use this as a primary only when link_authority vs. competitors is not the issue and the internal signal is clearly the weak point.

technical            There are fundamental technical barriers — crawlability, indexing, rendering, canonical conflicts — that would prevent the page from ranking even if authority and content were improved. Use sparingly and only with specific evidence.

━━━━━━━━━━━━━━━━━━━━━━━━━
WEIGHT GUIDANCE
━━━━━━━━━━━━━━━━━━━━━━━━━

constraint_breakdown weights must sum to exactly 1.0. Typical distributions:

Clear single bottleneck:         primary 0.75–0.85, secondary 0.15–0.25
Two meaningful constraints:      primary 0.55–0.65, secondary 0.35–0.45
Three meaningful constraints:    0.50 / 0.30 / 0.20 (approximate)

Do not distribute weights evenly across all five categories. That signals you have not identified the primary constraint.
```

---

## 2. User Message Template

Copy this as the `content` of the user message, after substituting all `{variables}`. Rules for each variable are in Section 3.

Unfilled variables must be replaced with `not available` — never leave a `{variable}` placeholder in the final prompt.

```
Diagnose the primary ranking bottleneck for the following page versus its current top organic competitors.

════════════════════════════════════
TARGET PAGE
════════════════════════════════════
URL: {target_url}
Title tag: {title}
H1: {h1}
Word count: {word_count}
Content format: {content_format}

Primary keyword: {primary_keyword}
Keyword source: {keyword_source}
GSC average position (90 days): {gsc_avg_position}
GSC impressions (90 days): {gsc_impressions}
Page indexed in Google: {is_indexed}

Referring domains (approx): {target_rds}
Backlink data source: {backlink_source}

Content summary:
{target_content_summary}

════════════════════════════════════
TOP 3 ORGANIC COMPETITORS
(First 3 non-ad, non-local-pack results for the primary keyword, excluding the target page)
════════════════════════════════════

── Competitor 1 ──
URL: {c1_url}
Title tag: {c1_title}
Word count: {c1_word_count}
Content format: {c1_content_format}
Referring domains (approx): {c1_rds}
Content summary:
{c1_content_summary}

── Competitor 2 ──
URL: {c2_url}
Title tag: {c2_title}
Word count: {c2_word_count}
Content format: {c2_content_format}
Referring domains (approx): {c2_rds}
Content summary:
{c2_content_summary}

── Competitor 3 ──
URL: {c3_url}
Title tag: {c3_title}
Word count: {c3_word_count}
Content format: {c3_content_format}
Referring domains (approx): {c3_rds}
Content summary:
{c3_content_summary}

════════════════════════════════════
PRE-CALCULATED GAPS
════════════════════════════════════
Authority gap: Target ~{target_rds} RDs vs. competitor median ~{competitor_median_rds} RDs → gap of {authority_gap} RDs {authority_gap_direction}
Content gap: Target ~{word_count} words vs. competitor median ~{competitor_median_words} words → {content_gap_words} words {content_gap_direction}
SERP feature environment: {serp_features}
Dominant competitor content format: {dominant_competitor_format}

════════════════════════════════════
DATA AVAILABILITY FLAGS
════════════════════════════════════
GSC data connected: {gsc_connected}
Competitors retrieved: {competitor_count} of 3
Backlink data available for target: {target_backlinks_available}
Backlink data available for competitors: {competitor_backlinks_available}
Page crawled successfully: {page_crawled}
```

---

## 3. Variable Definitions and Compression Rules

### Target page variables

**`{target_url}`**
The full URL being analyzed. Include `https://`. Example: `https://example.com/best-crm-software`

**`{title}`**
The page's `<title>` tag content verbatim. If not retrievable, write `not available`.

**`{h1}`**
The page's first `<h1>` tag content verbatim. If the page has no `<h1>` or multiple H1s, note that: `none found` or `multiple H1s — primary: [text]`.

**`{word_count}`**
Visible body word count, excluding navigation, footer, and sidebar. Use any word-count browser extension or paste the main content into Google Docs and use Tools → Word Count. Round to nearest 50. Example: `1,450 words`.

**`{content_format}`**
Choose the single best-fit label: `guide` / `listicle` / `comparison` / `tutorial` / `review` / `landing page` / `pillar page` / `news article` / `product page` / `other: [describe]`.

**`{primary_keyword}`**
The single keyword phrase that represents this page's primary strategic intent. Selection logic:
- If GSC is connected: use the keyword with the highest impression volume in the last 90 days where the page ranks in positions 1–30.
- If no GSC: use the page's `<title>` and `<h1>` to identify the most specific, non-branded phrase that describes the page's topic. Confirm it returns the target URL in a Google search.
- If neither yields a clear answer: use the most prominent `<h1>` phrase and note `inferred`.

**`{keyword_source}`**
`GSC — top impressions keyword` / `inferred from title and H1` / `inferred from H1 only`.

**`{gsc_avg_position}`**
GSC → Performance → Pages → [this URL] → Queries tab → select the primary keyword → average position over last 90 days. Round to one decimal. Example: `7.4`. Write `not available` if GSC is not connected.

**`{gsc_impressions}`**
GSC → same view → impressions for the primary keyword over last 90 days. Example: `4,200`. Write `not available` if GSC is not connected.

**`{is_indexed}`**
Run `site:full-url-here` in Google. If the page appears: `yes`. If not: `no`. If uncertain (site: returns domain but not specific URL): `uncertain`.

**`{target_rds}`**
Approximate referring domain count to the specific URL (not the domain). Source from Ahrefs, Moz, Semrush, or Ubersuggest free tier — note which. Round to nearest 5 for counts under 100, nearest 25 for counts over 100. Example: `~45 RDs (Moz)`. Write `not available` if no tool is accessible.

**`{backlink_source}`**
Tool used for backlink data. Example: `Ahrefs free (1 check)` / `Moz Link Explorer free` / `Semrush free (limited)` / `not available`.

**`{target_content_summary}`**
Write 100–150 words covering ALL of:
1. The page's central topic and the specific angle it takes (what does it argue, recommend, or explain — not just the topic name).
2. Content format and structure (how it is organized — headers only? steps? a comparison table?).
3. Up to 5 key H2 subheadings verbatim or closely paraphrased.
4. Apparent search intent alignment: does the page's format and angle match what someone searching the primary keyword most likely wants?
5. Notable content elements present: original data, embedded tools, video, comparison tables, pricing, screenshots, expert quotes.
6. What the page is visibly missing relative to a thorough treatment of the topic.

**Be descriptive, not evaluative.** Describe what is there, not what you think it means. The model does the evaluation. If you write "the content is weak," you are doing the model's job — and possibly biasing it.

---

### Competitor variables (×3: c1, c2, c3)

**`{c1_url}`, `{c2_url}`, `{c3_url}`**
Full URLs of the 1st, 2nd, and 3rd organic results (non-ad, non-local pack, non-featured snippet) for the primary keyword in an incognito Google search. If the target URL itself ranks in the top 3, skip it and use the next result.

**`{c1_title}`, `{c2_title}`, `{c3_title}`**
`<title>` tag verbatim.

**`{c1_word_count}`, `{c2_word_count}`, `{c3_word_count}`**
Same method as target page. Round to nearest 50.

**`{c1_content_format}`, `{c2_content_format}`, `{c3_content_format}`**
Same label set as target: `guide` / `listicle` / `comparison` / `tutorial` / `review` / `landing page` / `pillar page` / `news article` / `product page` / `other: [describe]`.

**`{c1_rds}`, `{c2_rds}`, `{c3_rds}`**
Referring domains to the specific competitor URL (not their domain), using the same tool as for the target. If you can only check the domain-level, note it: `~1,200 domain-level RDs`. Write `not available` if unreachable.

**`{c1_content_summary}`, `{c2_content_summary}`, `{c3_content_summary}`**
Write 60–100 words per competitor covering:
1. The competitor's specific angle vs. the target page — how is it different in approach or emphasis?
2. Structural advantages or differences (depth, original data, tools, format, etc.).
3. Whether it targets the exact same search intent as the target page or a slightly different angle.

Be descriptive. Do not write "this is a better page." Write what it contains that differs.

If a competitor page is unavailable (403, paywall, etc.), write: `not available — [reason]`.

---

### Gap variables

**`{competitor_median_rds}`**
The median of `{c1_rds}`, `{c2_rds}`, `{c3_rds}`. If one is `not available`, take the median of the two available values. If all three are unavailable, write `not available`.

Median of three values: sort ascending, take the middle value.

**`{authority_gap}`**
`{competitor_median_rds}` minus `{target_rds}`. A positive number means the target is behind. A negative number means the target has more RDs than the median competitor. If either value is `not available`, write `not available`.

**`{authority_gap_direction}`**
`(target is behind)` / `(target is ahead)` / `(roughly equal — within 20%)` / `(not calculable)`.

**`{competitor_median_words}`**
The median of the three competitor word counts.

**`{content_gap_words}`**
`{competitor_median_words}` minus `{word_count}`. Positive = target is shorter.

**`{content_gap_direction}`**
`(target is shorter)` / `(target is longer)` / `(roughly equal — within 15%)`.

**`{serp_features}`**
Features visible in the Google SERP for the primary keyword during your incognito search. List all that apply: `featured snippet` / `people also ask` / `knowledge panel` / `image pack` / `video carousel` / `local pack` / `shopping results` / `none`. Example: `featured snippet, people also ask`.

**`{dominant_competitor_format}`**
The most common content format across the three competitors. Example: `editorial comparison guide (all 3)` / `long-form tutorial (2 of 3)` / `mixed`.

---

### Data availability flags

These are `yes` / `no` / `partial` answers — no elaboration needed in the flag fields; elaboration goes in the content summary and confidence rationale.

**`{gsc_connected}`** — `yes` / `no`

**`{competitor_count}`** — `3` / `2` / `1` / `0`

**`{target_backlinks_available}`** — `yes` / `no`

**`{competitor_backlinks_available}`** — `all 3` / `2 of 3` / `1 of 3` / `none`

**`{page_crawled}`** — `yes` / `partial (JS-heavy, content limited)` / `no (blocked)`

---

## 4. Tool Schema

Pass this as the single entry in the `tools` array. Use `tool_choice: {"type": "tool", "name": "analyze_bottleneck"}` to force the model to call it.

```json
{
  "name": "analyze_bottleneck",
  "description": "Record the complete bottleneck analysis verdict for the target page. All fields are required. Weights in constraint_breakdown must sum to 1.0.",
  "input_schema": {
    "type": "object",
    "required": [
      "primary_constraint",
      "primary_severity",
      "links_are_the_answer",
      "headline",
      "competitive_context",
      "constraint_breakdown",
      "recommended_action",
      "recommended_action_priority",
      "confidence",
      "confidence_rationale"
    ],
    "properties": {
      "primary_constraint": {
        "type": "string",
        "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"],
        "description": "The single most important factor preventing this page from ranking higher."
      },
      "primary_severity": {
        "type": "string",
        "enum": ["mild", "significant", "severe"],
        "description": "How large is the gap on the primary constraint? mild = small gap, addressable quickly. significant = meaningful gap, requires real investment. severe = large gap, will take extended effort or a strategic rethink."
      },
      "links_are_the_answer": {
        "type": "boolean",
        "description": "True ONLY when primary_constraint is link_authority AND content and intent are already competitive with the top results. False in all other cases, including when there is an authority gap but content or intent problems are more pressing."
      },
      "headline": {
        "type": "string",
        "maxLength": 150,
        "description": "The primary constraint stated as a short, declarative sentence a strategist could read aloud to a client. Must be specific to this page, not generic SEO advice. Example: 'Link authority is your primary constraint — you have ~45 RDs vs. a competitor median of ~280.' Or: 'Links won't fix this — the page is losing on search intent, not authority.'"
      },
      "competitive_context": {
        "type": "string",
        "maxLength": 220,
        "description": "One sentence comparing the target to the current top 3 competitors in plain language. Cite a specific signal. Example: 'You are closest to Competitor 2 on content depth but furthest from all three on referring domains.' Or: 'All three ranking pages use editorial review formats; your landing-page format is the clearest differentiator.'"
      },
      "constraint_breakdown": {
        "type": "array",
        "minItems": 1,
        "maxItems": 5,
        "description": "All identified constraints, ordered by weight descending. Weights must sum to exactly 1.0. Include only constraints that are actually present — do not list all five categories with arbitrary weights.",
        "items": {
          "type": "object",
          "required": ["category", "severity", "weight", "reason"],
          "properties": {
            "category": {
              "type": "string",
              "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"]
            },
            "severity": {
              "type": "string",
              "enum": ["mild", "significant", "severe"]
            },
            "weight": {
              "type": "number",
              "minimum": 0.05,
              "maximum": 0.95,
              "description": "Proportion of the total bottleneck. All weights in this array must sum to 1.0."
            },
            "reason": {
              "type": "string",
              "maxLength": 280,
              "description": "Specific reason citing a signal from the provided data. Not generic advice."
            }
          }
        }
      },
      "recommended_action": {
        "type": "string",
        "maxLength": 280,
        "description": "The single most important next action for this page, specific enough to act on. Must name what to do, not just what the problem is. Example: 'Restructure this page as a step-by-step tutorial covering [the specific subtopics the top 3 competitors cover that this page does not], then pursue links.' Or: 'Do not invest in links until the content format is changed from a vendor landing page to an independent editorial comparison.'"
      },
      "recommended_action_priority": {
        "type": "string",
        "enum": ["immediate", "high", "medium", "low"],
        "description": "How urgently should this action be taken relative to other SEO work? immediate = blocking all other link work. high = should happen this sprint. medium = important but not blocking. low = a nice-to-have improvement."
      },
      "confidence": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      },
      "confidence_rationale": {
        "type": "string",
        "maxLength": 320,
        "description": "Why this confidence level was assigned. Must explicitly reference which data signals were available or missing and how they influenced the verdict's reliability. Example: 'High — GSC data confirmed keyword and position, all three competitor profiles were retrieved, and backlink data was available for the target and two of three competitors. Signals were consistent.' Or: 'Low — GSC not connected; keyword and position are inferred. Backlink data available for target only. Verdict direction is plausible but could shift significantly with real GSC data.'"
      }
    }
  }
}
```

---

## 5. Prompt Changelog

| Version | Date | Change | Reason |
|---|---|---|---|
| v1 | 2026-06-24 | Initial version created for validation | Pre-implementation validation |

When changes are made after validation results, add a row here. Record what changed (specific text) and why. The prompt version used for each analysis is stored in `page_analyses.prompt_version` in the database.
