# Bottleneck Validation Plan

**Document type:** Pre-implementation validation protocol  
**Status:** Ready to execute  
**Date:** 2026-06-24  
**Prerequisite:** `/docs/intelligence-architecture.md` approved  
**Gate:** Sprint 1 does not begin until this validation produces a Go decision

---

## Purpose

The Bottleneck module is the intellectual center of Serpnex. It is the screen that makes a user say *"I've never seen a tool tell me that."* It is also the most expensive LLM call in the product and the one most likely to fail in ways that damage user trust — because a wrong confident verdict here is worse than no verdict at all.

Before investing in pipeline infrastructure, we need to answer a single question empirically:

> **Does Claude Sonnet 4, given the Bottleneck prompt and manually-gathered real page data, produce verdicts that a competent SEO strategist would call genuinely useful?**

This document defines exactly how to answer that question using 10 real URLs, a manual data-gathering procedure, a structured scoring rubric, and a binary Go / No-Go decision gate.

---

## What this validation tests

It tests the **reasoning quality** of the Bottleneck prompt under realistic inputs. It does not test infrastructure, APIs, schemas, or pipeline reliability. Those are Sprint 1 concerns.

Specifically, the test is asking:

1. Does the model correctly identify the primary ranking bottleneck — including cases where the bottleneck is NOT links?
2. Are the reasons specific to the page and competitors, or generic filler?
3. Is the confidence level appropriate given the data provided?
4. Does the output follow the structured schema well enough to be parseable?
5. Does the verdict say something the evaluator could not have said in 30 seconds from a quick page glance?

### What this validation does NOT test

- Whether data collection workers work correctly (that is a Sprint 1 integration test)
- Whether the pipeline handles errors and retries (Sprint 1)
- Whether the UI renders the verdict well (Sprint 4)
- Whether the confidence scoring model is well-calibrated over a large sample (post-launch)

---

## The ground truth problem

The fundamental challenge: for most URLs, we do not have a verified ground truth answer. We cannot know with certainty what the "correct" bottleneck is without a longitudinal SEO experiment.

This validation handles that constraint with two strategies:

**Strategy A — Known-outcome URLs (3 of the 10):** Select pages from your own sites or client sites where you have worked on the problem and know what happened. You know what the bottleneck was. The verdict can be compared to a known answer.

**Strategy B — Expert panel judgment (all 10):** The verdict is evaluated by a qualified SEO strategist who reviews the input signals and the verdict independently. The question is not "is this objectively correct?" but "would a competent strategist agree with this reasoning, given this data?" This is the right bar for a B2B SaaS product — the product must produce verdicts that professionals find credible and non-trivially useful.

If Jason is the sole evaluator for the pilot, he must put on the "expert reviewer hat" separately from the "product builder hat." Ideally, a second independent SEO reviewer scores the same 10 verdicts without seeing your scores first.

---

## URL selection criteria

### Required distribution (10 URLs total)

The 10 URLs must be distributed across these archetypes. Do not pick 10 URLs from the same niche or the same scenario — that produces a biased test.

| Archetype | Count | Why it's required |
|---|---|---|
| **A — Genuinely link-limited** | 3 | Good content, clear authority gap vs. competitors. The model should correctly identify links as the answer. |
| **B — Content/intent bottleneck** | 3 | Competitive authority is roughly equal but the page's content is thin, wrong format, or wrong intent. The model must NOT identify links as the primary answer. This is the hardest and most important test. |
| **C — Mixed (both content and links weak)** | 2 | Real ambiguity. The model must weight the constraints and identify a primary. Evaluates nuance. |
| **D — No GSC data available** | 1 | Data-sparse scenario. Tests confidence degradation. The verdict should be medium or low confidence with honest rationale. |
| **E — Brand-new / low-history page** | 1 | Insufficient signal. The model should produce an `insufficient_data` verdict or heavily caveated low-confidence output. Tests the model's ability to say "I don't know enough." |

### Selection rules

- Pages must be in position 5–30 in Google search results (not position 1 and not completely unranked). Pages at position 1 have no bottleneck to diagnose. Pages that have never ranked have no SERP comparison to analyze.
- Pages must be in English for this validation (Arabic/multilingual validation is a separate exercise before GCC launch).
- At least 2 URLs should be from domains where you have access to GSC data.
- Avoid pages on personal/test sites where you might have an emotional stake in the outcome.
- Archetypes A/B/C should be identifiable from a quick human inspection before running the test — if you genuinely cannot form a hypothesis about what the bottleneck is, pick a different URL.

### The hypothesis requirement

For each URL, before running any LLM call, the evaluator writes a one-sentence hypothesis:

> *"I expect the primary bottleneck to be [category] because [brief reason]."*

This hypothesis is sealed (written down, not changed) before the test runs. It is used post-test to assess whether the model agreed with expert intuition. Agreement is not required for a pass — a non-obvious correct verdict that surprises the evaluator is a better outcome than a verdict that simply confirms what was already obvious.

---

## Manual data-gathering procedure

For each URL, gather the following inputs manually. This replicates what the data collection workers will do — confirming the signal set is sufficient for reasoning.

### Step 1: Target page signals (10–15 min per URL)

**Page content:**
- Open the URL in a browser
- Note the `<title>` tag (visible in browser tab)
- Note the `<h1>` tag (main heading on page)
- Estimate word count (browser extension like Word Counter Plus, or paste into Google Docs)
- Note the content format: listicle / guide / comparison / landing page / other

**Indexing:**
- Run `site:exact-url.com/path` in Google — is the page indexed?

**Primary keyword:**
- If GSC access is available: check Performance → Pages → filter to this URL → sort keywords by Impressions → take the top keyword
- If no GSC: use the page's `<title>` and `<h1>` to infer the primary keyword; note this as estimated

**GSC position:**
- If available: average position for the primary keyword over last 90 days
- If not available: run a Google search for the primary keyword, note approximately where the page appears (page 1 position 5–10, page 2, etc.)

### Step 2: SERP and competitor signals (15–20 min per URL)

**Find competitors:**
- Search Google for the primary keyword in an incognito/private window
- Record the URLs of the top 3 organic results (exclude the target page itself)

**For each of the top 3 competitor pages:**
- Visit the page; note the `<title>`, `<h1>`, estimated word count, and content format
- Write 1–2 sentences summarizing the page's approach vs. the target page

**Backlink gap (approximate):**
Use any of the following free/accessible methods:
- **Ahrefs free account** (limited to 1 check/day): check DR and referring domains for target + competitors
- **Moz Link Explorer** (free account): DA and linking root domains
- **Semrush free account** (10 queries/day): authority score and backlinks
- **Ubersuggest free**: domain score, backlinks

Record for each domain: approximate referring domain count and a rough authority score. Exact numbers are not needed — order-of-magnitude accuracy is sufficient for this test. E.g., "target: ~45 RDs | competitor 1: ~320 RDs | competitor 2: ~180 RDs | competitor 3: ~95 RDs."

### Step 3: Construct the prompt input

Fill in the Bottleneck prompt template from `/docs/intelligence-architecture.md §5.4` with the gathered data. Use the exact prompt text — do not paraphrase or summarize the instructions.

For the competitor content summaries, write 2–3 sentences per competitor describing the page's content depth, format, and angle. Do not paste raw HTML.

For the gap analysis section, calculate:
- Authority gap: `target_RDs - median(top3_RDs)`
- Content gap: `competitor_median_words - target_word_count` (estimate if needed)

### Step 4: Run the LLM call

Use the Anthropic API directly. No application code required — use the API playground or a minimal one-off script.

**Model:** `claude-sonnet-4-5` (or latest available Sonnet 4 equivalent)  
**Temperature:** `0` (deterministic; we want consistent reasoning, not creative variation)  
**Max tokens:** `2,000`  
**Method:** Tool use with the Bottleneck tool schema (see §Appendix A below)

Record:
- The full prompt sent (system + user message)
- The full raw response
- The parsed tool call output
- Any errors (schema violations, refusals, truncations)
- Approximate token count (input + output)
- Latency (seconds to first token + completion)

---

## Scoring rubric

Each verdict is scored independently across six dimensions. Score each dimension 0, 1, or 2.

### Dimension 1: Constraint identification accuracy (0–2)

**2 — Correct and specific:** The primary constraint identified matches expert judgment AND the reason given is specific to this page and these competitors (not generic SEO advice).

**1 — Plausible but arguable:** The constraint identification is defensible but not the most compelling conclusion given the data. Or the constraint is correct but the reason is generic.

**0 — Wrong or misleading:** The primary constraint is clearly incorrect given the signals provided. Especially: classifying a content/intent bottleneck as a link authority bottleneck. This is the critical failure mode.

### Dimension 2: The "links won't help" test (0–2 for Archetype B/C; N/A for Archetype A)

This dimension only applies to URLs in Archetypes B (content/intent bottleneck) and C (mixed).

**2 — Correctly defers links:** For Archetype B pages, the model explicitly concludes that building links is NOT the primary action. `links_are_the_answer = false`. The reason correctly identifies the non-link constraint.

**1 — Partial deferral:** The model names a non-link constraint as primary but hedges ("also consider links" or "once content is fixed, links will matter") in a way that dilutes the verdict.

**0 — False positive:** The model assigns link authority as the primary constraint on a page where expert judgment says the bottleneck is content or intent. This is a product-level failure.

### Dimension 3: Specificity (0–2)

**2 — Page-specific:** The verdict cites specific signals from the provided data. E.g., "Competitors rank with tutorial-format content while your page uses a landing page format for a keyword where searchers want step-by-step instructions." The user could not have read this from a generic SEO tool.

**1 — Partially specific:** Some specific signals are cited but the conclusion could broadly apply to many pages. Some generic SEO advice present.

**0 — Generic:** The verdict could apply to virtually any page in any niche. No specific signal is cited. Output reads like a boilerplate SEO audit.

### Dimension 4: Confidence calibration (0–2)

**2 — Appropriately calibrated:** Confidence level matches data availability. High confidence only when GSC data was available AND competitor data was complete AND the signals aligned. Low confidence correctly flagged when data was sparse or signals contradicted.

**1 — Slightly off:** Confidence is one level higher or lower than appropriate, but the confidence rationale acknowledges the limitation.

**0 — Miscalibrated:** High confidence with obviously sparse data, or low confidence with complete clean data and clear signal alignment.

### Dimension 5: Schema compliance (0–2)

**2 — Clean parse:** The output matches the tool schema exactly. All required fields present. Enum values are valid. `constraint_breakdown` weights sum to 1.0. No extra fields.

**1 — Minor issues:** One or two fields missing or slightly malformed but the core verdict is recoverable.

**0 — Parse failure:** The output cannot be parsed into the schema. Critical fields missing, invalid enum values, or the model refused to use the tool.

### Dimension 6: Actionability (0–2)

**2 — Specific next action:** The `recommended_action` field gives a concrete, specific instruction that a strategist could act on immediately. E.g., "Restructure the page as a step-by-step tutorial covering [specific subtopics] before investing in links" is specific. "Improve your content" is not.

**1 — Direction without specifics:** The recommended action points in the right direction but lacks the specificity to act on without further thinking.

**0 — Vague or circular:** The action is generic, repeats the constraint without adding direction, or is simply not actionable.

---

## Per-verdict scoring sheet

Copy this block for each of the 10 URLs.

```
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis (evaluator's expected bottleneck): _______________
Date/time run: _______________

DATA GATHERED:
  Primary keyword: _______________
  GSC available: Yes / No
  Target page RDs (approx): _______________
  Competitor 1 URL + RDs: _______________
  Competitor 2 URL + RDs: _______________
  Competitor 3 URL + RDs: _______________
  Authority gap (target - median): _______________
  Content gap (competitor median - target word count): _______________

LLM OUTPUT SUMMARY:
  primary_constraint: _______________
  links_are_the_answer: True / False
  confidence: low / medium / high
  confidence_rationale (first 100 chars): _______________
  recommended_action (first 150 chars): _______________
  Schema parsed cleanly: Yes / No / Partial
  Latency (seconds): _______________
  Approx tokens (in + out): _______________

SCORES:
  D1 — Constraint identification:    0 / 1 / 2
  D2 — "Links won't help" test:      0 / 1 / 2 / N/A
  D3 — Specificity:                  0 / 1 / 2
  D4 — Confidence calibration:       0 / 1 / 2
  D5 — Schema compliance:            0 / 1 / 2
  D6 — Actionability:                0 / 1 / 2

  Total (out of 10 or 12):           _____ / _____

EVALUATOR NOTES:
  Did the verdict surprise you (in a good or bad way)? _______________
  Did the model agree with your pre-test hypothesis? Yes / No / Partial
  If no: was the model more likely right, or more likely wrong? _______________
  Any hallucinated signals (model cited data that wasn't in the prompt)? Yes / No
  If yes, describe: _______________
```

---

## Aggregate success and failure criteria

### Go criteria (all must be met to proceed to Sprint 1)

**G1 — Overall quality score:** Average verdict score ≥ 7.5 / 10 (or 7.5 / 12 for Archetype B/C URLs) across all 10 URLs.

**G2 — Zero critical failures on the "links won't help" test:** No Archetype B URL receives a D2 score of 0. A single false-positive confident link recommendation on a clearly content-bottlenecked page is a blocking failure.

**G3 — Specificity floor:** At least 8 of 10 verdicts score ≥ 1 on Dimension 3 (specificity). A product producing generic verdicts has no competitive differentiation.

**G4 — Schema reliability:** At least 9 of 10 verdicts parse cleanly (D5 score = 2). Schema failures at >10% will produce systematic pipeline errors.

**G5 — No systematic hallucination:** The model does not cite signals that were not present in the prompt in more than 2 of 10 verdicts. Hallucinated competitor URLs, fabricated backlink counts, or invented keyword rankings are disqualifying if they appear in more than 2 verdicts.

### Conditional Go criteria (prompt revision required, then re-run 5 URLs)

**C1 — Confidence miscalibration pattern:** If ≥ 3 of 10 verdicts score D4 = 0 AND the failure mode is consistent (e.g., always overclaims High confidence), this is a fixable prompt issue. Revise the confidence instruction in the prompt; re-run only the failing URLs.

**C2 — Specificity pattern failure:** If ≥ 3 of 10 verdicts score D3 = 0 AND the prompt instructions for specificity are vague, revise the prompt with explicit specificity requirements; re-run.

**C3 — Schema minor issues only:** If no D5 = 0 failures occur but D5 = 1 issues appear on 3+ verdicts with the same field consistently missing, fix the tool schema definition and re-run those URLs only.

A Conditional Go requires a partial re-run (5 URLs, same archetypes as failures) before Sprint 1 begins. Do not start building the pipeline while the prompt is still being revised.

### No-Go criteria (stop, re-architect the prompt, re-run all 10)

**N1 — Average score below 6.0:** The prompt is producing verdicts that are not useful. Fundamental prompt re-architecture required before any further testing.

**N2 — Any Archetype B false positive (D2 = 0):** A single confident wrong verdict on a content-bottlenecked page triggers a full prompt re-architecture. The non-obvious "links won't help" insight is the product's core differentiator. If the model systematically fails this, the prompt logic is wrong.

**N3 — Schema failures on ≥ 3 URLs (D5 = 0):** The tool schema definition or the prompt's output instructions are not working. Revise schema structure, not prompt content.

**N4 — Systematic hallucination (≥ 3 URLs):** The model is filling in signals it was not given, either because the data compression left too many gaps or because the prompt implicitly invites fabrication. Prompt context structure needs revision.

---

## Failure mode taxonomy

These are the five known failure modes to watch for. They each have distinct fixes.

### FM-1: The confident generalist

**Symptom:** Verdicts are well-structured and plausible but could describe any page. Low specificity scores across multiple URLs. The recommended action is always "improve your content quality and build more links."

**Root cause:** The prompt is not forcing the model to cite specific signals. The model is reasoning from priors, not from the data provided.

**Fix:** Add to the prompt: *"Every claim you make about the primary constraint must cite a specific signal from the data provided. Do not make claims that could apply to any page."*

---

### FM-2: The link-biased analyst

**Symptom:** Multiple Archetype B URLs receive `links_are_the_answer = true` or `primary_constraint = link_authority` despite the content/intent signals being dominant.

**Root cause:** The model has internalized that Serpnex is a link-building tool and is anchoring its verdicts to what it expects the user wants to hear. The explicit counter-instruction in the prompt is not strong enough.

**Fix:** Strengthen the explicit instruction. Consider adding a few-shot example in the prompt of an Archetype B verdict where links are explicitly not the answer, showing the correct reasoning path.

---

### FM-3: The over-hedger

**Symptom:** Every verdict returns `confidence = low` regardless of data quality. Or the `confidence_rationale` is always the same boilerplate regardless of actual data availability.

**Root cause:** The confidence instruction is too conservative. The model is defaulting to hedging rather than reasoning about actual data quality.

**Fix:** Make the confidence instruction bidirectional: *"Set confidence to 'high' when all three primary signals (GSC data, competitor backlinks, competitor content) are available and consistent. Reserve 'low' for cases where at least two primary signals are missing."*

---

### FM-4: The schema rebel

**Symptom:** The model produces the reasoning in prose outside the tool call, or produces a partially-filled schema, or uses enum values not in the schema (e.g., "moderate" instead of "medium").

**Root cause:** The system prompt instruction to use the tool is not strong enough, or the tool schema is too complex for the model to fill reliably in one pass.

**Fix A (instruction):** Strengthen the tool use instruction: *"You MUST use the analyze_bottleneck tool. Do not write any prose outside the tool call. If you are uncertain about a field, use your best judgment — do not omit the field."*

**Fix B (schema):** If certain fields consistently fail (e.g., `constraint_breakdown` weights not summing to 1.0), simplify that field — use integer percentages (0-100) instead of floats, or reduce to 3 max constraints instead of open-ended.

---

### FM-5: The signal fabricator

**Symptom:** The model cites specific numbers (referring domain counts, keyword positions, content statistics) that were not in the prompt.

**Root cause:** The model is filling in "reasonable" values for missing data rather than working with what it was given. This is especially likely if the data compression step left too many `null` values.

**Fix:** Add to the prompt: *"You must only reason from the specific data provided. If a signal is not in the data above, do not estimate or assume it. Instead, note the absence of that signal in your confidence_rationale."*

---

## Decision framework

After all 10 verdicts are scored:

```
Calculate: average score across all 10 URLs
Check G1–G5: all passed?
  → Yes: PROCEED TO SPRINT 1

Check N1–N4: any triggered?
  → Yes: STOP. Re-architect prompt. Re-run all 10.

Check C1–C3: any triggered (and no N triggers)?
  → Yes: Targeted fix. Re-run 5 URLs (same archetypes as failures).
     Re-score those 5. If now passing G1–G5: PROCEED TO SPRINT 1.
     If still failing: escalate to N1–N4 evaluation.
```

### Expected outcome

Based on prior testing of Claude Sonnet on structured SEO analysis tasks:

- FM-2 (link bias) is the most likely failure mode. The prompt's explicit counter-instruction should handle most cases, but it may need strengthening.
- FM-1 (confident generalist) is likely on Archetype D/E URLs where data is sparse. Acceptable as long as confidence is correctly set to Low.
- FM-5 (fabrication) is uncommon with Claude Sonnet when the prompt clearly delineates what data is provided. Watch for it especially on Archetype D URLs.

A first-run score of 7.0–8.5 is a realistic outcome. Below 7.0 requires prompt revision. Above 8.5 on the first run would be exceptional — the validation is designed with high standards.

---

## Running the validation: step-by-step checklist

```
□ Select 10 URLs matching the archetype distribution (§URL selection criteria)
□ For each URL, write the pre-test hypothesis BEFORE gathering data
□ Gather target page signals for all 10 URLs (Step 1)
□ Gather SERP and competitor signals for all 10 URLs (Step 2)
□ Construct prompt inputs for all 10 URLs (Step 3)
□ Run LLM calls for all 10 URLs using claude-sonnet-4-5 at temperature 0 (Step 4)
□ Complete per-verdict scoring sheet for all 10 URLs
□ Calculate aggregate scores and check against Go/Conditional Go/No-Go criteria
□ If second evaluator is available: share raw verdicts (not scores) for blind scoring
□ Record final decision in /docs/decisions.md
□ If Go: update /docs/progress.md and begin Sprint 1
□ If Conditional Go or No-Go: document prompt revisions, re-run, re-score
```

---

## What a good verdict looks like

This is a reference example. It is constructed, not an actual LLM output, but it illustrates the bar being set.

**URL:** A guide about "best CRM software for small business" stuck at position 8.

**Input signals provided:**
- Target page: 1,400 words, landing-page format (feature bullets, "get a quote" CTAs), 42 RDs
- Competitor 1: 3,200 words, detailed comparison table + scoring rubric, 310 RDs
- Competitor 2: 2,800 words, "top 10 reviewed" listicle, 185 RDs  
- Competitor 3: 2,200 words, "how we tested" editorial review, 97 RDs
- Authority gap: target has 42 RDs; competitors have 97–310 RDs
- Content gap: target is 1,400 words; competitors average 2,733 words

**A 0-score generic verdict would say:**

> "Your page lacks sufficient authority compared to competitors. Focus on building more links and improving content quality."

**A 2-score specific verdict would say:**

> "Primary constraint: content depth and format mismatch. The top 3 results are all editorial comparison reviews (2,200–3,200 words, with comparison tables or scoring rubrics). Your page uses a vendor-promotion landing page format — feature bullets and a quote CTA — for a keyword where searchers are in research mode comparing options, not ready to buy. Competitors 1–3 outrank you primarily because they match search intent with an independent review format, not because they have more links. While your authority gap is real (~200+ RDs behind Competitor 1), closing it without fixing the content/format mismatch is unlikely to produce meaningful ranking improvement. Recommended action: rebuild this page as an independent review-format comparison (side-by-side table, honest scoring criteria, 2,500+ words) before investing in link acquisition. Confidence: medium (GSC keyword data not available; intent mismatch is inferred from SERP result format analysis)."

The difference is not word count. It is that the second verdict would require a human strategist with time and expertise to produce. The first could be auto-generated by any SEO tool.

---

## Appendix A — Bottleneck tool schema for API testing

Use this tool definition when calling the Anthropic API directly during validation. This is the exact schema the LLM must fill.

```json
{
  "name": "analyze_bottleneck",
  "description": "Record the bottleneck analysis verdict for the target page.",
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
        "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"]
      },
      "primary_severity": {
        "type": "string",
        "enum": ["mild", "significant", "severe"]
      },
      "links_are_the_answer": {
        "type": "boolean",
        "description": "True only if link_authority is the primary constraint and content/intent are already competitive."
      },
      "headline": {
        "type": "string",
        "description": "The primary constraint stated as a short declarative headline. Max 150 characters.",
        "maxLength": 150
      },
      "competitive_context": {
        "type": "string",
        "description": "One sentence comparing the target page to the current top 3 competitors. Plain language. Max 200 characters.",
        "maxLength": 200
      },
      "constraint_breakdown": {
        "type": "array",
        "description": "All identified constraints, ordered by weight descending. Weights must sum to 1.0.",
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
              "minimum": 0,
              "maximum": 1,
              "description": "Proportion of the total bottleneck. All weights in the array must sum to 1.0."
            },
            "reason": {
              "type": "string",
              "description": "Specific reason for this constraint, citing signals from the provided data. Max 250 characters.",
              "maxLength": 250
            }
          }
        }
      },
      "recommended_action": {
        "type": "string",
        "description": "The specific next action. Cite the page and competitors. Max 250 characters.",
        "maxLength": 250
      },
      "recommended_action_priority": {
        "type": "string",
        "enum": ["immediate", "high", "medium", "low"]
      },
      "confidence": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      },
      "confidence_rationale": {
        "type": "string",
        "description": "Why this confidence level was assigned. Must reference data availability. Max 300 characters.",
        "maxLength": 300
      }
    }
  }
}
```

---

## Appendix B — Minimum viable API call (no application code)

The simplest way to run a single test. This is a reference invocation, not a production script.

```python
import anthropic

client = anthropic.Anthropic(api_key="YOUR_KEY")

SYSTEM_PROMPT = """You are the analysis engine for Serpnex, a link intelligence platform used by SEO agencies.
Your role is to analyze web pages and produce structured, defensible verdicts that help
strategists make decisions about link building.

You analyze signals objectively. You do not overstate confidence. When data is insufficient
to support a verdict, you say so clearly. You produce verdicts that are actionable and specific,
not vague or generic.

All outputs must use the analyze_bottleneck tool. Do not include prose outside the tool call."""

# Fill this in for each URL test
USER_MESSAGE = """
[Paste the filled Bottleneck prompt template here]
"""

response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=2000,
    temperature=0,
    system=SYSTEM_PROMPT,
    tools=[BOTTLENECK_TOOL_SCHEMA],  # paste Appendix A schema here
    tool_choice={"type": "tool", "name": "analyze_bottleneck"},
    messages=[{"role": "user", "content": USER_MESSAGE}]
)

# Extract result
tool_use_block = next(b for b in response.content if b.type == "tool_use")
verdict = tool_use_block.input
print(verdict)
```

`temperature=0` is mandatory. Do not run validation tests at higher temperatures — variability in outputs is a pipeline concern, not a prompt quality concern, and should not affect the validation result.

---

*This document governs the go/no-go gate before Sprint 1. No infrastructure should be built until the validation produces a Go decision. Update `/docs/decisions.md` and `/docs/progress.md` when the validation completes.*
