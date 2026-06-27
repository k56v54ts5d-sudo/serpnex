# IDE Validation Plan — Real-World Pipeline Testing

**Status:** Pre-Sprint 4 — complete before implementation resumes  
**Date:** 2026-06-27  
**Purpose:** Identify weaknesses in the scoring model, signal extraction, prompt quality, and explanation quality using live websites before Sprint 4 scope is committed  
**Method:** Run the complete IDE pipeline (live providers, no mocks) against 16 hand-selected URLs, then compare each verdict — and the reasoning behind it — against expert SEO judgment

Do not change any implementation until this plan is fully executed and the findings section (§6) is complete.

---

## Table of Contents

1. [What This Validates](#1-what-this-validates)
2. [Pre-flight Checklist](#2-pre-flight-checklist)
3. [URL Roster](#3-url-roster)
4. [Execution Instructions](#4-execution-instructions)
5. [Verdict Worksheets](#5-verdict-worksheets)
6. [Findings and Weaknesses](#6-findings-and-weaknesses)
7. [Go / Conditional Go / No-Go](#7-go--conditional-go--no-go)
8. [Assumptions Under Test](#8-assumptions-under-test)
9. [Reasoning Quality Rubric](#9-reasoning-quality-rubric)

---

## 1. What This Validates

The IDE pipeline has five distinct layers. Each layer can fail independently. This validation tests all five simultaneously on real data.

| Layer | What can go wrong |
|---|---|
| **Mode detection** | Misclassifies a placement article as a category; misclassifies a category URL as Mode A; domain detection unreliable |
| **Signal extraction (Haiku Call 1)** | P1 scores inflated for tangentially related content; D4 scores too lenient for link farms; P5 miscalibrated for Mode B |
| **Deterministic scoring** | Cluster weights produce wrong outcome for edge cases; risk multiplier too aggressive or too lenient; editorial cap threshold wrong |
| **Verdict language (Haiku Call 2)** | Headline does not match outcome tier; primary_reason does not reference D4 when required; conditions are vague or generic |
| **Reasoning quality** | Correct verdict, wrong reason — the explanation cites the wrong signal, reverses cause and effect, or would not be trusted by an experienced SEO professional even though the outcome number is correct |

A correct verdict with incorrect reasoning is **not a full success.** Users act on the explanation as much as the outcome tier. An explanation that is technically consistent with the score but names the wrong cause, omits the decisive signal, or uses language that does not match what an SEO practitioner would say from the same evidence will erode trust and produce wrong follow-on decisions.

Additionally, this plan tests five confidence dimensions:

- Does the confidence level match the actual data availability?
- Does the confidence ceiling enforce correctly for Mode B/domain?
- Does the `data_quality` dict accurately reflect what was and was not collected?
- Do hard exclusion gates fire on obvious disqualifying sites?
- Does `insufficient_data` trigger correctly when crawls fail?

---

## 2. Pre-flight Checklist

Complete all items before running the first URL.

**Environment:**
- [ ] `ANTHROPIC_API_KEY` set and valid (Haiku calls will be charged)
- [ ] `FIRECRAWL_API_KEY` set and valid
- [ ] `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` set
- [ ] Redis running locally (`docker compose up redis -d`)
- [ ] PostgreSQL running locally with migration 0003 applied (`uv run alembic upgrade head`)
- [ ] FastAPI running (`uv run uvicorn app.main:app --reload`)
- [ ] Celery worker running (`uv run celery -A app.worker.celery_app worker --loglevel=info`)

**Test script ready:**
- [ ] Copy the execution script from §4.2 and verify it connects to the local API
- [ ] Run one URL as a smoke test before recording results
- [ ] Confirm SSE stream is receivable (or poll `GET /api/v1/opportunities/{id}` every 5 seconds)

**For each URL — before running the pipeline:**
- [ ] Write your expert judgment in the worksheet (§5) before seeing the verdict
- [ ] Record what outcome you expect and why
- [ ] Record what confidence level you expect and why
- [ ] Write the primary reason you would give if you were writing the verdict yourself — in one sentence, citing the most decisive signal
- [ ] Write the two or three supporting signals you would expect a correct explanation to name
- [ ] Write one condition you would require if the verdict were WITH_CONDITIONS

This order matters: verdict-first comparison is corrupted if you see the score before forming a judgment. **Reasoning-first comparison is equally important** — if you write the expected explanation after reading the pipeline output, you will unconsciously align it with what the pipeline said, even when the pipeline is wrong.

Read §9 (Reasoning Quality Rubric) before filling in the expert reasoning section for the first time.

---

## 3. URL Roster

Sixteen URLs across six test categories. Select real websites from the list below — the specific URLs are illustrative. Replace with actual live URLs before execution. Each entry states the hypothesis (what the expert expects) and the failure mode being tested.

### 3.1 Mode A — Specific Article Placements

Four articles where a specific page is being evaluated as a link placement host.

| # | Category | Description | Expected outcome | Mode expected |
|---|---|---|---|---|
| A1 | High-quality, topically perfect | A well-written, authoritative article from a respected domain (e.g., Ahrefs blog, Search Engine Journal, Moz) that directly covers the same topic as the target page | RECOMMENDED | specific_placement |
| A2 | High-quality, wrong topic | Same high-authority domain, but the article covers an unrelated niche (e.g., a technical SEO article evaluated for a recipe target page) | NOT_RECOMMENDED | specific_placement |
| A3 | Medium-quality, appropriate topic | A solid but not exceptional blog post from a niche domain (DR 30–50, reasonable traffic) covering the right topic | WITH_CONDITIONS | specific_placement |
| A4 | Thin/low-quality, link-selling signals | An article with inflated OBL count, no editorial voice, generic content — the kind of "write for us" farm that places any link for payment | NOT_RECOMMENDED | specific_placement |

**What A2 tests:** The scorer must not reward authority when relevance fails. P1 low + D1 high = NOT_RECOMMENDED via relevance gate, regardless of domain metrics.

**What A4 tests:** D4 (editorial integrity) must be scored independently of P2 (content quality). A fluent article can still have corrupted editorial patterns. The editorial integrity cap (investment score ≤ 45) must trigger.

---

### 3.2 Mode B — Category URL

Four category/section pages where the prospect is a topic section rather than a single article.

| # | Category | Description | Expected outcome | Mode expected |
|---|---|---|---|---|
| B1 | Strong topical section | A clearly-defined category page on a mid-authority domain that consistently publishes relevant, substantive articles | RECOMMENDED or WITH_CONDITIONS | guest_post_opportunity / category_url |
| B2 | Mixed-niche section | A section that covers the target topic but also mixes in tangential content, diluting topical coherence | WITH_CONDITIONS | guest_post_opportunity / category_url |
| B3 | Clearly irrelevant section | A category page for a completely different niche submitted by mistake | NOT_RECOMMENDED | guest_post_opportunity / category_url |
| B4 | Guest post farm section | A "guest posts" or "contributors" section where every article has 10+ external links, inconsistent topics, and no editorial standards | NOT_RECOMMENDED (editorial cap) | guest_post_opportunity / category_url |

**What B2 tests:** P1 averaging across sampled articles (scores should not be dominated by one good article). D1 coherence should be penalised.

**What B4 tests:** D4 detection across multiple articles. Consistent OBL patterns must produce a low D4 score even if individual articles are readable.

---

### 3.3 Mode B — Domain-Only Input

Four bare domain inputs requiring section inference.

| # | Category | Description | Expected outcome | Mode expected |
|---|---|---|---|---|
| C1 | Strong, relevant domain | A clean, well-established domain clearly operating in the target niche — section inference should find a matching section | WITH_CONDITIONS (low confidence ceiling) | guest_post_opportunity / domain_inferred |
| C2 | Relevant domain, no clear sections | A domain that publishes relevant content but has a flat URL structure with no clear section pages — inference should fail or return homepage | WITH_CONDITIONS or INSUFFICIENT_DATA | guest_post_opportunity / domain_inferred |
| C3 | Unrelated domain | A domain in a completely different industry (intentional mismatch) | NOT_RECOMMENDED | guest_post_opportunity / domain_inferred |
| C4 | Suspicious/spam domain | A domain with visible spam signals, unverified traffic, or a DataForSEO spam score above 60 | NOT_RECOMMENDED (gate expected) | guest_post_opportunity / domain_inferred |

**What C1 tests:** Confidence ceiling enforcement. Even a strong result must show `confidence: low` and `confidence_ceiling: low`. If it shows `high`, the ceiling is broken.

**What C2 tests:** Graceful degradation when section inference cannot find a section. The pipeline must not crash — it should fall back and document the limitation in `data_quality`.

**What C4 tests:** Gate H3 (malware/spam) or H2 (deindexed) must fire before any LLM call is made.

---

### 3.4 Hard Exclusion Gate Cases

Four URLs specifically selected to trigger individual hard gates.

| # | Gate | Description | Expected |
|---|---|---|---|
| G1 | H3 — Malware/spam | A domain with DataForSEO spam_score ≥ 95 (spam_risk ≈ 0.0 after inversion) | Gate H3 fires. LLM never called. Outcome: NOT_RECOMMENDED. |
| G2 | H2 — Deindexed | A domain with near-zero estimated traffic but a substantial backlink profile (suggests a prior penalty). Use a domain known to have been penalised. | Gate H2 fires. LLM never called. |
| G3 | H1 — Prohibited content | A domain operating in a clearly prohibited category (adult content, gambling, etc.). Use a flagged domain if available, or a subdomain known to contain disqualifying content. | Gate H1 fires. |
| G4 | H5 — Manual action | A domain with sharply declining traffic trajectory despite 50+ referring domains and acceptable spam risk. | Gate H5 fires. |

> **Note:** If a real domain for G3 is unavailable (due to content filters on Firecrawl), substitute a URL known to return H1 keywords in its metadata or title tags. Document the substitution.

---

### 3.5 Edge Cases

Three URLs that test boundary behaviour.

| # | Case | Description | What to observe |
|---|---|---|---|
| E1 | Crawl failure (blocked site) | A real site that blocks bots or returns 403/429 to Firecrawl | Does the pipeline degrade gracefully? Does `data_quality` reflect the crawl failure? Does confidence drop to `low`? |
| E2 | Score right at the threshold | A site expected to land near the 68-point recommended boundary | Does the outcome (RECOMMENDED vs WITH_CONDITIONS) match expert judgment? Is the boundary calibrated correctly? |
| E3 | Language mismatch (H4 case) | A real site in a clearly non-Latin script (Japanese, Arabic, or Cyrillic) evaluated for an English-language target | Does gate H4 fire? If not, does the language_match score penalise correctly? |

---

## 4. Execution Instructions

### 4.1 Setting Up a Test Page Record

The `POST /opportunities` endpoint requires a `page_id`. Create a test page record first:

```sql
-- Run once. Record the returned UUID as YOUR_PAGE_ID.
INSERT INTO pages (id, site_id, url, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    (SELECT id FROM sites LIMIT 1),  -- use any existing site_id
    'https://yoursite.com/target-page',
    NOW(),
    NOW()
)
RETURNING id;
```

If no site record exists:

```sql
INSERT INTO workspaces (id, name, plan, analyses_used_this_period, analyses_limit)
VALUES (gen_random_uuid(), 'IDE Validation', 'free', 0, 100)
RETURNING id;

INSERT INTO sites (id, workspace_id, domain, created_at, updated_at)
VALUES (gen_random_uuid(), '<workspace_id>', 'yoursite.com', NOW(), NOW())
RETURNING id;

INSERT INTO pages (id, site_id, url, created_at, updated_at)
VALUES (gen_random_uuid(), '<site_id>', 'https://yoursite.com/target-page', NOW(), NOW())
RETURNING id;
```

### 4.2 Execution Script

Run this Python script for each URL. Replace `PAGE_ID` and `PROSPECT_URL` per worksheet.

```python
import requests
import time
import json

BASE = "http://localhost:8000/api/v1"
PAGE_ID = "YOUR_PAGE_ID_HERE"
PROSPECT_URL = "https://example.com/article-to-evaluate"

# 1. Create the opportunity
resp = requests.post(f"{BASE}/opportunities", json={
    "page_id": PAGE_ID,
    "prospect_url": PROSPECT_URL,
})
assert resp.status_code == 202, f"Create failed: {resp.status_code} {resp.text}"
opp_id = resp.json()["opportunity_id"]
print(f"Created: {opp_id}")

# 2. Poll until terminal state (or 5 minutes)
deadline = time.time() + 300
while time.time() < deadline:
    result = requests.get(f"{BASE}/opportunities/{opp_id}").json()
    status = result["status"]
    print(f"  Status: {status}")
    if status in ("complete", "failed"):
        break
    time.sleep(5)

# 3. Print full result
print(json.dumps(result, indent=2))
```

> To use SSE streaming instead of polling, replace step 2 with:
> `curl -N "http://localhost:8000/api/v1/opportunities/{opp_id}/stream"`

### 4.3 What to Record

For each URL, capture exactly:

1. **Full JSON response** from `GET /opportunities/{id}` at completion
2. **Celery worker log** for this task run (copy from terminal)
3. **All values** in §5 worksheet for that URL

Capture the Celery log because it shows:
- Which states were entered and in what order
- Whether any stage raised an exception
- Whether a gate fired (logged before LLM call)
- Call 1 and Call 2 token usage

---

## 5. Verdict Worksheets

One worksheet per URL. Fill **Expert Judgment** section BEFORE running the pipeline.

---

### Worksheet Template

```
URL: ___________________________________________
Test category: [ ] A1 [ ] A2 [ ] A3 [ ] A4  [ ] B1 [ ] B2 [ ] B3 [ ] B4
               [ ] C1 [ ] C2 [ ] C3 [ ] C4  [ ] G1 [ ] G2 [ ] G3 [ ] G4
               [ ] E1 [ ] E2 [ ] E3

Target page context given to pipeline:
  target_topic:    ___________________________________________
  target_audience: ___________________________________________

════════════════════════════════════════════════════════════════
SECTION A — EXPERT JUDGMENT (complete entirely before running)
════════════════════════════════════════════════════════════════

A1. EXPECTED VERDICT
────────────────────────────────────────────────────────────────
Expected outcome:         [ ] RECOMMENDED  [ ] WITH_CONDITIONS  [ ] NOT_RECOMMENDED  [ ] INSUFFICIENT_DATA
Expected confidence:      [ ] high  [ ] medium  [ ] low
Expected mode:            [ ] specific_placement  [ ] category_url  [ ] domain_inferred
Expected gate (if any):   [ ] none  [ ] H1  [ ] H2  [ ] H3  [ ] H4  [ ] H5

Brief verdict rationale (why you chose this outcome):




A2. EXPECTED REASONING
────────────────────────────────────────────────────────────────
Write this as if you were the one producing the explanation. Use
the signal names (P1, D4, etc.) if you know them. Be specific —
do not write "good site" or "relevant content." Cite what you
actually observe about the prospect URL.

Expected primary reason (one sentence, the single most decisive
signal — the one that, if removed, would change the outcome):




Expected supporting signals (the 2–3 observations that reinforce
the primary reason but do not drive the outcome alone):
1. ___________________________________________
2. ___________________________________________
3. ___________________________________________

Expected conditions (if WITH_CONDITIONS — specific and
actionable, not generic):
1. ___________________________________________

Expected confidence rationale (what data is or is not available
that determines the confidence level):




What a trustworthy explanation must NOT do for this URL
(preemptive anti-patterns to watch for):
___________________________________________


════════════════════════════════════════════════════════════════
SECTION B — PIPELINE RESULT (complete after pipeline finishes)
════════════════════════════════════════════════════════════════

B1. VERDICT
────────────────────────────────────────────────────────────────
Status:                   ___________
Mode detected:            ___________
Mode sub-type:            ___________
Inferred section:         ___________
Investment score:         ___________
Outcome:                  ___________
Confidence:               ___________
Confidence ceiling:       ___________
Gate triggered:           [ ] none  [ ] H1  [ ] H2  [ ] H3  [ ] H4  [ ] H5

Cluster scores:
  Relevance:   _______    Authority:  _______
  Quality:     _______    Risk:       _______    Risk ×: _______

Editorial integrity cap applied: [ ] yes  [ ] no
P5 cap applied:                  [ ] yes  [ ] no

B2. REASONING (copy verbatim from pipeline output)
────────────────────────────────────────────────────────────────
Verdict headline:
___________________________________________

Primary reason (copy exactly):
___________________________________________

Supporting signals (copy exactly):
1. ___________________________________________
2. ___________________________________________
3. ___________________________________________
4. ___________________________________________

Conditions (copy exactly, if with_conditions):
1. ___________________________________________
2. ___________________________________________

Mode qualifier (copy exactly):
___________________________________________

Confidence rationale (copy exactly):
___________________________________________

B3. SIGNAL SCORES FROM CALL 1 (copy from opportunity_verdict)
────────────────────────────────────────────────────────────────
P1 topical relevance:      _______   rationale: ___________________
P2 content quality:        _______   rationale: ___________________
P4 OBL quality:            _______   rationale: ___________________
P5 placement feasibility:  _______   rationale: ___________________
D1 topical coherence:      _______   rationale: ___________________
D4 editorial integrity:    _______   rationale: ___________________
D9 geo/language match:     _______   rationale: ___________________
language_match:            _______
data_quality_notes: ___________________________________________

B4. DATA QUALITY
────────────────────────────────────────────────────────────────
placement_page_crawled:        [ ] yes  [ ] partial  [ ] no
article_samples:               ___
domain_samples:                ___
backlink_metrics_available:    [ ] yes  [ ] no
domain_metrics_available:      [ ] yes  [ ] no
section_inferred:              [ ] yes  [ ] no


════════════════════════════════════════════════════════════════
SECTION C — VERDICT ASSESSMENT
════════════════════════════════════════════════════════════════

C1. OUTCOME ACCURACY
────────────────────────────────────────────────────────────────
Outcome matches:           [ ] yes  [ ] no
Confidence matches:        [ ] yes  [ ] close enough  [ ] no
Mode detected correctly:   [ ] yes  [ ] no
Gate fired correctly:      [ ] yes  [ ] n/a  [ ] no

If outcome does not match — specific discrepancy:
___________________________________________

Suspected cause of outcome error:
[ ] Signal extraction error (Call 1 scored incorrectly)
[ ] Scoring formula (correct signals, wrong math or weights)
[ ] Mode detection error (wrong mode, affected data collected)
[ ] Data quality error (missing signal skewed the score)
[ ] Threshold calibration (direction correct, boundary wrong)
[ ] Other: ___________


════════════════════════════════════════════════════════════════
SECTION D — REASONING ASSESSMENT
════════════════════════════════════════════════════════════════

Fill this section even when the outcome is correct. A correct
verdict with wrong reasoning is a separate failure mode that
must be recorded independently.

D1. PRIMARY REASON QUALITY
────────────────────────────────────────────────────────────────
Does the primary reason cite the signal that actually drove
the outcome (per the cluster scores)?
[ ] yes — the named signal matches what the scores show
[ ] partial — the right topic, but wrong framing or direction
[ ] no — the primary reason names the wrong signal entirely

Is the primary reason grounded in observable evidence from the
crawled content, not a generic statement?
[ ] yes — cites specific content, OBL patterns, or domain signals
[ ] partial — somewhat specific but could apply to many sites
[ ] no — generic ("good site", "relevant content", "high authority")

If D4 < 0.30 (editorial integrity cap was applied), does the
primary reason explicitly reference editorial integrity?
[ ] yes  [ ] no  [ ] n/a (D4 ≥ 0.30)

Does the primary reason match what you wrote in Section A2?
[ ] yes — same signal, same direction
[ ] partial — same signal, different framing
[ ] no — different signal or contradicts expert expectation

Primary reason discrepancy (if partial or no):
___________________________________________

D2. SUPPORTING SIGNALS QUALITY
────────────────────────────────────────────────────────────────
Are the supporting signals consistent with the cluster scores?
(A supporting signal that contradicts a cluster score is a
reasoning error even if the signal sounds plausible.)
[ ] yes, all consistent   [ ] one inconsistency   [ ] multiple

Do the supporting signals provide additional information beyond
what the primary reason already said?
[ ] yes — each signal adds a distinct observation
[ ] partial — some overlap or repetition
[ ] no — supporting signals restate the primary reason

Are the supporting signals specific to this URL, or could they
have been written for any site in this category?
[ ] specific — names observable facts about this URL
[ ] generic — could apply to any similar site

Do the supporting signals match what you expected in A2?
[ ] yes  [ ] partial  [ ] no

Supporting signal discrepancy (if partial or no):
___________________________________________

D3. CONDITIONS QUALITY (with_conditions outcomes only)
────────────────────────────────────────────────────────────────
Are conditions specific and actionable?
(A condition is actionable if an SEO practitioner could follow
it without further clarification.)
[ ] yes, all specific   [ ] partially   [ ] no, vague   [ ] n/a

Example of a good condition: "Verify no more than 2 OBL per
paragraph in the target article before placement."
Example of a bad condition: "Ensure content quality is high."

Do the conditions address the actual risk that triggered the
WITH_CONDITIONS verdict?
[ ] yes   [ ] partially   [ ] no   [ ] n/a

D4. CONFIDENCE RATIONALE QUALITY
────────────────────────────────────────────────────────────────
Does the confidence rationale accurately describe what data
was and was not available?
[ ] yes — matches data_quality flags exactly
[ ] partial — mostly correct but omits or misstates one item
[ ] no — contradicts the data_quality flags

Is the confidence rationale specific to this evaluation, or
generic boilerplate?
[ ] specific   [ ] partially specific   [ ] generic boilerplate

D5. MODE QUALIFIER QUALITY
────────────────────────────────────────────────────────────────
Does the mode qualifier correctly describe the evaluation mode
and any structural caveat it introduces?
[ ] yes   [ ] partial   [ ] no   [ ] n/a (Mode A, no qualifier needed)

If Mode B/domain_inferred: does it explain that confidence is
capped at low due to section inference?
[ ] yes   [ ] no   [ ] n/a

D6. OVERALL REASONING TRUSTWORTHINESS
────────────────────────────────────────────────────────────────
Imagine showing this verdict explanation — without the score —
to an experienced SEO professional who knows the prospect site.
Would they consider the explanation credible and well-grounded?

[ ] Fully trustworthy — an experienced SEO practitioner would
    accept this reasoning as sound, even if they might weight
    one signal differently. The explanation cites real evidence,
    names the right causes, and would not mislead a user.

[ ] Partially trustworthy — the main thrust is correct, but
    one element (a supporting signal, the confidence rationale,
    or a condition) is vague, generic, or slightly off. An
    experienced practitioner would notice the gap but not be
    seriously misled.

[ ] Not trustworthy — the explanation would mislead an
    experienced practitioner. It names the wrong cause, omits
    the decisive signal, contradicts observable evidence, or
    produces a plausible-sounding but factually wrong rationale.
    A user acting on this explanation would make a worse
    decision than if they had received no explanation at all.

Specific reasoning failure (if partial or not trustworthy):
___________________________________________

D7. REASONING FAILURE CLASSIFICATION
────────────────────────────────────────────────────────────────
If any reasoning failure was found, classify it (select all
that apply):

[ ] Wrong primary signal — outcome is correct but the named
    cause is not the signal that drove the score
[ ] Cause-effect reversal — signal named correctly but the
    direction of its impact is wrong ("high D4 hurt the score"
    when D4 was actually high and positive)
[ ] Generic explanation — correct signal category but no
    specific evidence cited from crawled content
[ ] Missing decisive signal — the explanation omits a signal
    that visibly drove the outcome (e.g., editorial cap applied
    but D4 not mentioned)
[ ] Contradicts cluster scores — explanation praises a signal
    whose cluster score shows it was low, or criticises one
    whose score was high
[ ] Vague conditions — WITH_CONDITIONS verdict but conditions
    cannot be acted on without further clarification
[ ] Confidence rationale mismatch — rationale describes data
    availability incorrectly relative to data_quality flags
[ ] Mode qualifier absent or wrong — Mode B verdict without a
    clear statement of what the confidence ceiling means
[ ] Outcome-explanation mismatch — explanation tone does not
    match the outcome (e.g., enthusiastic language for
    NOT_RECOMMENDED, or hedging language for RECOMMENDED)
[ ] No reasoning failure found


════════════════════════════════════════════════════════════════
SECTION E — FINAL SEVERITY AND NOTES
════════════════════════════════════════════════════════════════

Overall verdict accuracy:
[ ] Correct outcome  [ ] Wrong outcome

Overall reasoning quality:
[ ] Fully trustworthy  [ ] Partially trustworthy  [ ] Not trustworthy

Combined result:
[ ] Full pass    — correct outcome AND fully trustworthy reasoning
[ ] Partial pass — correct outcome, partially trustworthy reasoning
[ ] Reasoning failure — correct outcome, not trustworthy reasoning
[ ] Verdict failure — wrong outcome (reasoning automatically fails)

Severity:
[ ] Critical   — wrong outcome, or reasoning that actively
                 misleads (user would make a worse decision)
[ ] Significant — correct outcome, reasoning failure on primary
                  reason or a decisive signal omitted
[ ] Minor      — correct outcome and reasoning, one supporting
                 signal vague or one secondary element off
[ ] Pass       — correct outcome and fully trustworthy reasoning

Notes:
```

---

## 6. Findings and Weaknesses

**Complete after all 16 URLs are run.** This section is intentionally left blank until execution is done.

### 6.1 Summary Table

Two columns per result: outcome accuracy (O) and reasoning quality (R).

O: ✓ correct outcome / ~ wrong direction but right category / ✗ wrong outcome  
R: ✓ fully trustworthy / ~ partially trustworthy / ✗ not trustworthy

| # | URL | Expected outcome | Got outcome | O | Reasoning quality | R | Severity |
|---|-----|---------|-----|---|---------|---|---------|
| A1 | | | | | | | |
| A2 | | | | | | | |
| A3 | | | | | | | |
| A4 | | | | | | | |
| B1 | | | | | | | |
| B2 | | | | | | | |
| B3 | | | | | | | |
| B4 | | | | | | | |
| C1 | | | | | | | |
| C2 | | | | | | | |
| C3 | | | | | | | |
| C4 | | | | | | | |
| G1 | | | | | | | |
| G2 | | | | | | | |
| G3 | | | | | | | |
| G4 | | | | | | | |
| E1 | | | | | | | |
| E2 | | | | | | | |
| E3 | | | | | | | |

**Outcome accuracy rate:** ___ / 19 correct  
**Full pass rate (correct outcome AND trustworthy reasoning):** ___ / 19  
**Reasoning failure rate (correct outcome, not trustworthy reasoning):** ___ / 19

### 6.2 Pattern Analysis

Document each failure pattern observed across multiple URLs. For each:

```
Pattern: [describe what went wrong]
URLs affected: [list URL IDs]
Layer: [ ] mode detection  [ ] signal extraction  [ ] scoring  [ ] verdict language
Root cause hypothesis:
Fix options:
  Option A: [describe]
  Option B: [describe]
Recommended fix:
Priority: [ ] Sprint 4 blocker  [ ] Sprint 4 improvement  [ ] post-Sprint 4
```

### 6.3 Signal-Specific Observations

Fill after all URLs are complete. For each signal, record whether the LLM-assigned score was consistently calibrated.

| Signal | Tendency | Example |
|---|---|---|
| P1 topical relevance | [ ] inflated  [ ] deflated  [ ] calibrated | |
| P2 content quality | [ ] inflated  [ ] deflated  [ ] calibrated | |
| P4 OBL quality | [ ] inflated  [ ] deflated  [ ] calibrated | |
| P5 feasibility | [ ] inflated  [ ] deflated  [ ] calibrated | |
| D1 topical coherence | [ ] inflated  [ ] deflated  [ ] calibrated | |
| D4 editorial integrity | [ ] inflated  [ ] deflated  [ ] calibrated | |
| D9 geo/language match | [ ] inflated  [ ] deflated  [ ] calibrated | |

### 6.4 Mode Detection Accuracy

| URL | Expected mode | Got mode | Correct? | Notes |
|---|---|---|---|---|
| | | | | |

### 6.5 Gate Accuracy

| Gate | URLs tested | Fired correctly | Failed to fire | False positive |
|---|---|---|---|---|
| H1 | | | | |
| H2 | | | | |
| H3 | | | | |
| H4 | | | | |
| H5 | | | | |

### 6.6 Confidence Calibration

Record whether the reported confidence matched the actual data situation.

```
Cases where confidence was too high (pipeline reported medium/high, data was insufficient):

Cases where confidence was too low (pipeline reported low, data was fully available):

Confidence ceiling enforcement (C1 should be low — did it enforce?):
```

### 6.7 Prompt Quality Observations

Specific observations about Haiku output quality — not scores, but language.

```
Call 1 (signal extraction):
- Were rationale fields informative or generic?
- Did any rationale contradict the score it explained?
- Were data_quality_notes used appropriately?

Call 2 (verdict assembly):
- Did headlines match the outcome tier tone?
- Did primary_reason cite D4 when the editorial cap was applied?
- Were conditions (for with_conditions) specific and actionable, or vague?
- Did the mode_qualifier correctly describe the structural caveat?
```

### 6.8 Reasoning Quality Analysis

**Complete after all 19 URLs are run.** This section aggregates the per-URL reasoning assessments (Section D of each worksheet) into patterns.

#### 6.8.1 Reasoning Failure Frequency

Count how many URLs triggered each failure classification from Section D7.

| Failure type | Count | Example URL(s) |
|---|---|---|
| Wrong primary signal | | |
| Cause-effect reversal | | |
| Generic explanation | | |
| Missing decisive signal | | |
| Contradicts cluster scores | | |
| Vague conditions | | |
| Confidence rationale mismatch | | |
| Mode qualifier absent or wrong | | |
| Outcome-explanation mismatch | | |

#### 6.8.2 Primary Reason Accuracy

The primary reason is the single most user-visible output. It is the sentence a user reads to understand why the pipeline decided what it decided.

```
URLs where primary reason named the correct decisive signal: ___ / 19

URLs where primary reason named a plausible-but-wrong signal: ___
  List:

URLs where primary reason was generic (no specific evidence cited): ___
  List:

URLs where D4 cap applied but primary reason did not cite D4: ___
  List:
```

**Assessment:** If primary reason accuracy is below 80% (15/19), the Call 2 prompt requires revision before Sprint 4. The anti-bias rule "if D4 < 0.30, primary_reason must reference D4" should be tightened with an explicit instruction.

#### 6.8.3 Supporting Signal Quality

```
URLs where all supporting signals were specific to the URL: ___
URLs where at least one supporting signal was generic: ___
URLs where a supporting signal contradicted a cluster score: ___

Most common generic phrase observed across multiple URLs:
  (copy verbatim if seen more than twice)

Most common cause of signal-score contradiction:
  (describe the pattern)
```

#### 6.8.4 Conditions Quality (WITH_CONDITIONS cases only)

```
WITH_CONDITIONS URLs evaluated: ___

Of those, conditions that were specific and actionable: ___
Of those, conditions that were vague or generic: ___

Examples of good conditions produced (copy verbatim):
1.
2.

Examples of bad conditions produced (copy verbatim):
1.
2.

Pattern: what made the bad conditions unactionable?
```

#### 6.8.5 Trustworthiness by URL Category

```
Mode A (A1–A4):        ___ / 4 fully trustworthy
Mode B/category (B1–B4): ___ / 4 fully trustworthy
Mode B/domain (C1–C4):  ___ / 4 fully trustworthy
Gate cases (G1–G4):     ___ / 4 fully trustworthy (gate reason quality)
Edge cases (E1–E3):     ___ / 3 fully trustworthy

Which category produced the worst reasoning quality, and why?
```

#### 6.8.6 Correct Outcome / Wrong Reasoning Cases

These are the most insidious failures — the verdict number looks right, but the explanation would mislead a user or mask a real issue.

```
For each URL where outcome was correct but reasoning was not trustworthy:

URL ID: ___
Outcome: _____ (correct)
What the primary reason said:
What it should have said:
What a user acting on this explanation might do wrong:
Root cause (which layer produced the wrong reasoning):
  [ ] Call 1 rationale fields — signal was scored correctly but
      rationale text was generic, giving Call 2 nothing to cite
  [ ] Call 2 prompt — correct rationale available but Call 2
      ignored it and chose a different framing
  [ ] Both — rationale was generic AND Call 2 did not compensate
  [ ] Other: ___
```

#### 6.8.7 Reasoning Quality Summary

```
Full pass (correct outcome + trustworthy reasoning):     ___ / 19 ( __% )
Partial pass (correct outcome + partial reasoning):      ___ / 19 ( __% )
Reasoning failure (correct outcome + untrustworthy):     ___ / 19 ( __% )
Verdict failure (wrong outcome):                         ___ / 19 ( __% )

Verdict: Is the reasoning quality sufficient to ship to users?
[ ] Yes — reasoning failures are minor and infrequent
[ ] Conditional — specific prompt changes needed (list in §7)
[ ] No — reasoning quality is a blocking issue; Call 2 prompt
    requires significant revision before Sprint 4
```

---

## 7. Go / Conditional Go / No-Go

Complete after §6 is finished.

### Decision Criteria

Verdict accuracy and reasoning quality are scored separately. Both must pass for a Go decision.

**Verdict accuracy thresholds:**

| Condition | Go | Conditional Go | No-Go |
|---|---|---|---|
| Critical verdict errors | 0 | 1 | ≥ 2 |
| Significant verdict errors | ≤ 2 | 3–4 | ≥ 5 |
| Gate accuracy | All G1–G4 correct | 3/4 correct | ≤ 2/4 correct |
| Mode detection accuracy | ≥ 14/19 | 12–13/19 | ≤ 11/19 |
| Confidence ceiling enforcement | Always correct | 1 failure | ≥ 2 failures |

**Reasoning quality thresholds:**

| Condition | Go | Conditional Go | No-Go |
|---|---|---|---|
| Full pass rate (correct outcome + trustworthy reasoning) | ≥ 80% (15/19) | 68–79% (13–14/19) | < 68% (≤ 12/19) |
| Primary reason names correct signal | ≥ 80% (15/19) | 68–79% | < 68% |
| Untrustworthy reasoning on correct outcome | ≤ 1 | 2–3 | ≥ 4 |
| D4 cap applied but not cited in primary_reason | 0 | 1 | ≥ 2 |
| Vague/unactionable conditions (WITH_CONDITIONS) | 0 | 1 | ≥ 2 |

**Interpretation:** A Conditional Go on reasoning means specific prompt changes are required before Sprint 4 begins — not after. The Call 2 prompt (`docs/prompts/opportunity-v1.md`) must be revised, re-tested on the failing cases, and signed off. Do not defer reasoning improvements to Sprint 4 scope.

### Decision

```
VERDICT ACCURACY: [ ] GO  [ ] CONDITIONAL GO  [ ] NO-GO
REASONING QUALITY: [ ] GO  [ ] CONDITIONAL GO  [ ] NO-GO

Combined decision:
[ ] GO — Sprint 4 may begin
[ ] CONDITIONAL GO — required changes documented below; must be
    complete and verified before Sprint 4 implementation starts
[ ] NO-GO — scoring model or prompt requires rework; re-run
    affected URL categories after changes

Date: ___________
Signed off by: ___________

Required changes before Sprint 4 (if Conditional Go or No-Go):
Verdict accuracy changes:
1.
2.

Reasoning quality changes (prompt revisions):
1.
2.
3.

Verification plan (how to confirm each change worked):
1.
2.
```

---

## 8. Assumptions Under Test

The following assumptions from `docs/validation/assumptions.md` are directly tested by this validation. Record whether each was confirmed or falsified.

| ID | Assumption | Test URLs | Result |
|---|---|---|---|
| A21 | Mode detection accuracy ≥ 85% for production URLs | A1–A4, B1–B4, C1–C4 | |
| A22 | Section inference finds a relevant section in ≥ 70% of well-structured domains | C1, C2 | |
| — | D4 scoring reliably identifies guest post farms vs editorial sites | A4, B4 | |
| — | Risk multiplier correctly differentiates declining domains from stable low-traffic domains | G2, G4, E2 | |
| — | Editorial integrity cap fires on all domains with D4 < 0.30 | A4, B4, C4 | |
| — | Haiku Call 1 rationale fields are informative enough to audit | All | |
| — | Confidence ceiling enforces to `low` for all domain_inferred evaluations | C1, C2, C3 | |
| — | Hard gates fire before any LLM call | G1–G4 | |

---

## 9. Reasoning Quality Rubric

Read this section before filling in Section A2 (Expected Reasoning) of any worksheet. It defines what "trustworthy reasoning" means precisely so assessments are consistent across all 19 URLs.

### 9.1 What Makes Reasoning Trustworthy

An explanation is trustworthy when an experienced SEO professional, shown only the verdict text (not the score), would:

1. Agree that the named cause is the right cause — not just a plausible one
2. Recognise that the evidence cited is specific to the evaluated URL, not generic to its category
3. Be able to act on the explanation without second-guessing whether the pipeline understood the site
4. Trust the conditions (if WITH_CONDITIONS) enough to negotiate around them with a client

None of these criteria require the explanation to be perfect. They require it to be honest about what the data showed and to name the right thing as the right thing.

### 9.2 What Makes Reasoning Untrustworthy

An explanation is untrustworthy when any of the following are true:

**Wrong cause named.** The primary reason identifies a signal that was not the decisive factor. Example: primary reason says "high organic traffic supports this investment" but the outcome was driven by a low D4 score and editorial cap — traffic was high but irrelevant to the outcome. A user reading this would believe they should look for high-traffic sites, when the real issue was editorial integrity.

**Direction reversed.** The named signal is correct, but its impact is described backwards. Example: "The site's editorial integrity score of 0.22 indicates strong content standards" — D4 of 0.22 is below the cap threshold and triggered NOT_RECOMMENDED. The user would be confused why a "strong" site was rejected.

**Generic content.** The explanation could have been written for any site in the same category without changing a word. Example: "This site covers relevant topics in your niche and maintains a reasonable posting frequency." This provides no information that distinguishes this site from the 50 other sites an SEO practitioner is considering.

**Omits the decisive signal.** When the editorial integrity cap fired (D4 < 0.30), the primary reason must name editorial integrity. When the risk multiplier was 0.25 (site is collapsing), the primary reason must name the risk signals. Omitting the decisive signal — even while naming correct secondary signals — produces a verdict the user cannot act on correctly.

**Contradicts observable evidence.** The explanation says "content quality is strong" but the sampled articles are thin, generic, or AI-generated. The explanation says "outbound links are selective" but the OBL list has 20 external links per article. A practitioner who visited the site would immediately distrust the verdict.

**Vague conditions.** For WITH_CONDITIONS verdicts, conditions like "ensure quality is maintained" or "check the site's editorial standards before proceeding" are not actionable. An actionable condition names a specific, verifiable criterion: "Confirm that the target article has fewer than 3 external links before outreach" or "Verify that the linking article covers the target topic at ≥ 400 words depth."

### 9.3 The "Swap Test"

For each explanation, apply this test: could you swap the `primary_reason` between two URLs in the same category without anyone noticing? If yes, the explanation is generic and fails the specificity criterion regardless of whether the outcome is correct.

Example of a swap-proof primary reason:
> "The placement article's outbound link list contains 14 links to finance offer pages, none of which relate to the article's topic of productivity tools — this pattern of indiscriminate OBL indicates low editorial integrity (D4: 0.18)."

Example of a swappable (generic) primary reason:
> "This site's editorial standards are not consistent with the quality of link investment required for your target page."

The first cites observable evidence. The second could appear on any rejection verdict.

### 9.4 Special Cases

**Gate-triggered verdicts.** When a hard exclusion gate fires, the explanation is the `hard_exclusion_reason` field, not Call 2 output. Evaluate it by the same criteria: does it name the specific signal that triggered the gate, and is the reason specific enough that a practitioner could verify it?

**INSUFFICIENT_DATA verdicts.** The primary reason should name which signals were missing and why that prevented scoring — not generic "data was unavailable." Example: "The placement page returned a 403 to the crawler, preventing content analysis, and DataForSEO returned no organic traffic data for this domain. Scoring requires at least one of these sources."

**Mode B verdicts.** The mode qualifier must appear and must explain the confidence ceiling in plain language. "This evaluation covered a domain-level section inferred by the pipeline rather than a specific article provided by you — the confidence ceiling is low because section inference may not reflect the section where your link would appear" is trustworthy. "Confidence is low due to limited data" is not — it does not explain *why* the data is limited by design.

### 9.5 Calibration Example

To calibrate your assessment before scoring the first URL, here are four examples of the same WITH_CONDITIONS verdict at different reasoning quality levels.

**Example scenario:** Mode A placement, investment score 58, D4 = 0.52, risk_multiplier = 0.80, relevance cluster = 0.61.

**Level 1 — Fully trustworthy:**
> Primary reason: "The article covers adjacent content (content marketing strategy) rather than the target topic (technical SEO), producing a topical relevance score of 0.61 — sufficient for WITH_CONDITIONS but below the 0.70 threshold for RECOMMENDED."
> Conditions: "Confirm that the target article's anchor text context directly references technical SEO methodology rather than content strategy broadly."

**Level 2 — Partially trustworthy:**
> Primary reason: "The article's topical relevance is moderate. It covers related topics but may not fully align with your target page's focus."
> Conditions: "Ensure that the anchor text is contextually appropriate."

Level 2 is directionally correct but generic. "Moderate relevance" applies to hundreds of sites. "May not fully align" is a hedge. "Contextually appropriate" is not actionable.

**Level 3 — Not trustworthy (correct outcome, misleading explanation):**
> Primary reason: "Despite good content quality and a solid domain authority profile, the site's risk signals indicate caution is warranted before committing to this placement."
> Conditions: "Conduct additional due diligence on the site's traffic trends."

This reverses the actual picture: the outcome is WITH_CONDITIONS because of relevance, not risk (risk_multiplier = 0.80 is fine). A user reading this would investigate traffic trends, not relevance — wasting time and potentially dismissing a viable placement.

**Level 4 — Not trustworthy (outcome wrong, for contrast):**
> Primary reason: "This site represents a strong investment opportunity across all evaluated dimensions."
> Outcome: RECOMMENDED

This would be a verdict error (wrong outcome) in addition to a reasoning failure.

---

## Appendix: Known Risks to Watch For

These are failure modes anticipated during implementation. Watch for them during execution.

**Risk 1 — P1 inflation on tangentially related content.**  
The Haiku model may score P1 high when the article mentions the target topic in passing. Expert judgment: does the article *primarily* address the target topic, or merely mention it?

**Risk 2 — D4 leniency on high-quality link farms.**  
Some link farm articles are well-written but have corrupted OBL patterns. Haiku may score D4 ≥ 0.30 based on prose quality rather than OBL evidence. Watch for this in A4 and B4. The editorial cap only fires if D4 < 0.30.

**Risk 3 — Risk multiplier too aggressive.**  
A declining traffic trajectory produces a risk_multiplier of 0.55 or lower. For young domains (< 1 year) that have simply not yet accumulated traffic, this may be unfair. Watch for correct outcome in E2.

**Risk 4 — Section inference quality.**  
For C2 (flat URL structure), the inferred section may be the homepage or an irrelevant page. Watch whether the pipeline documents this correctly in `data_quality.section_inferred` and whether confidence reflects the degraded input.

**Risk 5 — Crawl quality on JS-heavy sites.**  
Firecrawl renders JavaScript, but some sites still return partial content. Watch `data_quality.placement_page_crawled` for "partial" status and whether the confidence score responds appropriately.

**Risk 6 — Mode detection false positives.**  
A deep article URL (e.g., `/blog/seo/technical-guide`) may be misclassified as a category if the article signals check returns < 2. Watch the `mode_detection_note` field for borderline cases.

**Risk 7 — Call 1 rationale fields are too thin to support Call 2.**  
Call 2 receives the computed scores but not the crawled content. It builds the explanation from the rationale strings produced by Call 1. If those rationale strings are generic ("Content is relevant to the target topic"), Call 2 has no specific evidence to cite and will produce a generic explanation. The problem originates in Call 1 but appears in the Call 2 output. When a reasoning failure is found, check the Call 1 rationale fields first — if they are generic, the root cause is Call 1, not Call 2.

**Risk 8 — Call 2 ignores rationale in favour of score patterns.**  
Even when Call 1 rationale fields are specific, Call 2 may pattern-match on the score values and produce a canned explanation ("strong relevance score indicates alignment") instead of citing the evidence in the rationale. This is a prompt compliance failure. It will appear as generic-sounding primary reasons on URLs where Call 1 rationales were actually detailed. To diagnose: compare the Call 1 `p1_rationale` field with the Call 2 `primary_reason` — if Call 2 did not paraphrase or cite any of the specific content from Call 1's rationale, this is the failure mode.

**Risk 9 — Correct outcome, systematically wrong explanation category.**  
Some scoring configurations produce a correct outcome for two different reasons. Example: a site scores NOT_RECOMMENDED because both relevance is low (0.28) AND D4 is below the cap (0.25). Call 2 might consistently cite relevance and ignore D4, producing a not-trustworthy explanation even though the outcome is right. This matters because a user who reads "low relevance" will look for a more relevant site — which might have the same editorial integrity problem. Watch for this specifically on A4 and B4 where both signals are expected to be weak.
