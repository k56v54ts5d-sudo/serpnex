# IDE Validation Plan — Real-World Pipeline Testing

**Status:** Pre-Sprint 4 — complete before implementation resumes  
**Date:** 2026-06-27  
**Purpose:** Identify weaknesses in the scoring model, signal extraction, and prompt quality using live websites before Sprint 4 scope is committed  
**Method:** Run the complete IDE pipeline (live providers, no mocks) against 16 hand-selected URLs, then compare each verdict against expert SEO judgment

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

---

## 1. What This Validates

The IDE pipeline has four distinct layers. Each layer can fail independently. This validation tests all four simultaneously on real data.

| Layer | What can go wrong |
|---|---|
| **Mode detection** | Misclassifies a placement article as a category; misclassifies a category URL as Mode A; domain detection unreliable |
| **Signal extraction (Haiku Call 1)** | P1 scores inflated for tangentially related content; D4 scores too lenient for link farms; P5 miscalibrated for Mode B |
| **Deterministic scoring** | Cluster weights produce wrong outcome for edge cases; risk multiplier too aggressive or too lenient; editorial cap threshold wrong |
| **Verdict language (Haiku Call 2)** | Headline does not match outcome tier; primary_reason does not reference D4 when required; conditions are vague or generic |

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

This order matters: verdict-first comparison is corrupted if you see the score before forming a judgment.

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

────────────────────────────────────────────────────────────────
EXPERT JUDGMENT (fill before running)
────────────────────────────────────────────────────────────────
Expected outcome:         [ ] RECOMMENDED  [ ] WITH_CONDITIONS  [ ] NOT_RECOMMENDED  [ ] INSUFFICIENT_DATA
Expected confidence:      [ ] high  [ ] medium  [ ] low
Expected mode:            [ ] specific_placement  [ ] category_url  [ ] domain_inferred
Expected gate (if any):   [ ] none  [ ] H1  [ ] H2  [ ] H3  [ ] H4  [ ] H5
Reasoning (1–3 sentences):



────────────────────────────────────────────────────────────────
PIPELINE RESULT
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

Verdict headline:
___________________________________________

Primary reason:
___________________________________________

Supporting signals:
1. _______________________________
2. _______________________________
3. _______________________________
4. _______________________________

Conditions (if with_conditions):
1. _______________________________
2. _______________________________

Mode qualifier:
___________________________________________

Confidence rationale:
___________________________________________

Data quality:
  placement_page_crawled:        [ ] yes  [ ] no
  article_samples:               ___
  domain_samples:                ___
  backlink_metrics_available:    [ ] yes  [ ] no
  domain_metrics_available:      [ ] yes  [ ] no
  section_inferred:              [ ] yes  [ ] no

────────────────────────────────────────────────────────────────
ASSESSMENT
────────────────────────────────────────────────────────────────
Verdict matches expert judgment:       [ ] yes  [ ] partial  [ ] no

If partial or no — specific discrepancy:
___________________________________________

Suspected cause:
[ ] Signal extraction error (Call 1 scored X when evidence supports Y)
[ ] Scoring formula error (correct signals, wrong math)
[ ] Verdict language error (Call 2 tone/framing mismatch)
[ ] Mode detection error (wrong mode assigned)
[ ] Data quality error (missing signal affected score incorrectly)
[ ] Threshold calibration (verdict correct in direction, but boundary wrong)
[ ] Other: ___________

Severity:
[ ] Critical — verdict is completely wrong and would cause user harm
[ ] Significant — verdict is directionally wrong or misses a key signal
[ ] Minor — correct verdict, suboptimal explanation or confidence

Notes:
```

---

## 6. Findings and Weaknesses

**Complete after all 16 URLs are run.** This section is intentionally left blank until execution is done.

### 6.1 Summary Table

| # | URL | Expected | Got | Match | Severity |
|---|-----|---------|-----|-------|---------|
| A1 | | | | | |
| A2 | | | | | |
| A3 | | | | | |
| A4 | | | | | |
| B1 | | | | | |
| B2 | | | | | |
| B3 | | | | | |
| B4 | | | | | |
| C1 | | | | | |
| C2 | | | | | |
| C3 | | | | | |
| C4 | | | | | |
| G1 | | | | | |
| G2 | | | | | |
| G3 | | | | | |
| G4 | | | | | |
| E1 | | | | | |
| E2 | | | | | |
| E3 | | | | | |

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

---

## 7. Go / Conditional Go / No-Go

Complete after §6 is finished.

### Decision Criteria

| Condition | Go | Conditional Go | No-Go |
|---|---|---|---|
| Critical verdict errors | 0 | 1 | ≥ 2 |
| Significant verdict errors | ≤ 2 | 3–4 | ≥ 5 |
| Gate accuracy | All G1–G4 correct | 3/4 correct | ≤ 2/4 correct |
| Mode detection accuracy | ≥ 14/16 | 12–13/16 | ≤ 11/16 |
| Confidence ceiling enforcement | Always correct | 1 failure | ≥ 2 failures |

### Decision

```
Verdict: [ ] GO — Sprint 4 may begin with no blocking changes
         [ ] CONDITIONAL GO — specific changes required before Sprint 4 (list below)
         [ ] NO-GO — scoring model or prompt requires rework

Date: ___________
Signed off by: ___________

Required changes before Sprint 4 (if Conditional Go or No-Go):
1.
2.
3.
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
