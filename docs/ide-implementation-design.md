# Investment Decision Engine — Implementation Design

**Document type:** Sprint 3 pre-implementation design  
**Status:** Awaiting approval before any code is written  
**Date:** 2026-06-27  
**References:** intelligence-architecture.md §3.5, §5.5, §6.3, §7.2, §8.3; decisions.md 2026-06-25 entries

---

## Table of Contents

1. [Overview](#1-overview)
2. [Complete Execution Flow](#2-complete-execution-flow)
3. [Processing Steps — Exact Order](#3-processing-steps--exact-order)
4. [Data Flow Between Components](#4-data-flow-between-components)
5. [Hard Exclusion Gates — Placement and Logic](#5-hard-exclusion-gates--placement-and-logic)
6. [Mode A vs Mode B — Divergence and Convergence](#6-mode-a-vs-mode-b--divergence-and-convergence)
7. [Deterministic Scoring ↔ LLM Reasoning Interaction](#7-deterministic-scoring--llm-reasoning-interaction)
8. [Failure Handling and Retry Strategy](#8-failure-handling-and-retry-strategy)
9. [Sequence Diagrams](#9-sequence-diagrams)
10. [Database Changes Required](#10-database-changes-required)
11. [New Files Required](#11-new-files-required)
12. [Risks Before Implementation](#12-risks-before-implementation)

---

## 1. Overview

The Investment Decision Engine (IDE) answers one question: **Is this website worth spending money on for a guest post or backlink?**

It is a **separate on-demand analysis**, not part of the automatic page analysis (Readiness + Bottleneck). It is linked to a target page — a user submits a prospect URL alongside a target page they have already analyzed.

The IDE uses a three-tier architecture:

```
Tier 0  →  Hard exclusion gates (deterministic, run first)
Tier 1  →  Signal collection + LLM scoring (Haiku call 1)
Tier 2  →  Deterministic cluster scoring + Investment Score
Final   →  LLM verdict assembly (Haiku call 2)
```

A single aggregation model, schema, validation layer, and exclusion gate set operates across both evaluation modes. **Mode only changes the data collection step.**

---

## 2. Complete Execution Flow

```
User submits: { prospect_url, target_page_id }
         │
         ▼
[API] POST /opportunities
  Creates opportunity record (status: queued)
  Enqueues Celery task
  Returns { opportunity_id, status: "queued" }
         │
         ▼
[Celery Task] run_ide_task(opportunity_id)
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 1: MODE DETECTION                           │
    │                                                  │
    │  Fetch prospect URL (HEAD → GET)                 │
    │  Classify: single article? listing? domain?      │
    │  → Mode A, Mode B/category, or Mode B/domain     │
    │  Write status: detecting_mode                    │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 2: SECTION INFERENCE (Mode B/domain only)   │
    │                                                  │
    │  Fetch robots.txt + sitemap.xml                  │
    │  Crawl homepage                                  │
    │  Haiku call: match sections to target topic      │
    │  → inferred_section recorded                     │
    │  Write status: inferring_section                 │
    └────┬─────────────────────────────────────────────┘
         │ (skipped for Mode A and Mode B/category)
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 3: DATA COLLECTION                          │
    │                                                  │
    │  Mode A: crawl placement page + 2–3 domain pages │
    │  Mode B: crawl 3–5 section articles + domain     │
    │  DataForSEO: traffic, domain authority, spam     │
    │  Run exclusion gate checks H1–H5 (see §5)        │
    │  Write status: collecting_data                   │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 4: HARD EXCLUSION GATE EVALUATION           │
    │                                                  │
    │  If any H1–H5 gate triggers:                     │
    │    Write status: complete (immediately)          │
    │    verdict.hard_exclusion_triggered = True       │
    │    verdict.outcome = not_recommended             │
    │    → Skip all LLM calls and scoring              │
    │    → Done                                        │
    └────┬─────────────────────────────────────────────┘
         │ (only reached if no gate triggered)
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 5: LLM CALL 1 — SIGNAL EXTRACTION          │
    │                                                  │
    │  Model: Claude Haiku 4.5                         │
    │  Input: crawled pages, target page topic         │
    │  Output: P1–P5 scores, D1/D4/D9 scores          │
    │  Write status: classifying_signals               │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 6: DETERMINISTIC SCORING                    │
    │                                                  │
    │  Combine LLM scores + DataForSEO data            │
    │  Compute: Relevance, Authority, Quality clusters │
    │  Compute: Risk score → Risk multiplier           │
    │  Compute: Base_Score → Investment_Score          │
    │  Apply editorial integrity cap (if D4 < 0.30)   │
    │  Compute: deterministic confidence               │
    │  Write status: computing_score                   │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 7: LLM CALL 2 — VERDICT ASSEMBLY           │
    │                                                  │
    │  Model: Claude Haiku 4.5                         │
    │  Input: all cluster scores, Investment Score,    │
    │         mode, confidence, target page context    │
    │  Output: headline, primary_reason,               │
    │           supporting_signals, conditions,        │
    │           confidence_rationale, mode_qualifier   │
    │  Write status: assembling_verdict                │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 8: VALIDATION + CONFIDENCE ENFORCEMENT      │
    │                                                  │
    │  Pydantic schema validation                      │
    │  Business logic validation (§7.2 rules)          │
    │  Mode-specific validation (§6.3 rules)           │
    │  Confidence ceiling enforcement (mode-based)     │
    │  Override deterministic score if LLM too high   │
    │  Record validation_overrides                     │
    └────┬─────────────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 9: PERSIST + COMPLETE                       │
    │                                                  │
    │  Write InvestmentVerdict to DB                   │
    │  Write status: complete                          │
    │  Publish SSE: complete event                     │
    └──────────────────────────────────────────────────┘
```

---

## 3. Processing Steps — Exact Order

### State machine for the `opportunities` table

| State | Description |
|---|---|
| `queued` | Record created; task enqueued |
| `detecting_mode` | Fetching prospect URL; classifying Mode A or B |
| `inferring_section` | Mode B/domain only: running section inference |
| `collecting_data` | Crawling pages; fetching DataForSEO signals |
| `classifying_signals` | Haiku call 1: content classification + signal extraction |
| `computing_score` | Deterministic cluster scoring and Investment Score calculation |
| `assembling_verdict` | Haiku call 2: investment verdict assembly |
| `complete` | InvestmentVerdict written; pipeline done |
| `failed` | Unrecoverable error; reason recorded |

**Hard exclusion gate triggered:** transitions directly from `collecting_data` → `complete` (no LLM calls, no scoring).

### Exact step sequence per mode

**Mode A:**
```
queued → detecting_mode → collecting_data → [gate eval]
       → classifying_signals → computing_score → assembling_verdict → complete
```

**Mode B / Category URL:**
```
queued → detecting_mode → collecting_data → [gate eval]
       → classifying_signals → computing_score → assembling_verdict → complete
```
*(same as Mode A except `detecting_mode` finds a listing/category page and data collection crawls articles from that section)*

**Mode B / Domain Only:**
```
queued → detecting_mode → inferring_section → collecting_data → [gate eval]
       → classifying_signals → computing_score → assembling_verdict → complete
```
*(additional `inferring_section` state; Haiku classification call runs before data collection)*

---

## 4. Data Flow Between Components

### 4.1 Components and their inputs/outputs

```
┌─────────────────────────────────────────────────────────────────────┐
│  ide_collector.py                                                   │
│                                                                     │
│  Inputs:  prospect_url, target_page (for context in mode B)        │
│                                                                     │
│  Outputs: IDEContext dataclass containing:                          │
│    mode: "specific_placement" | "guest_post_opportunity"           │
│    mode_b_subtype: "category_url" | "domain_inferred" | None       │
│    inferred_section: str | None                                     │
│    placement_page_crawl: CrawlResult | None    (Mode A)            │
│    sampled_article_crawls: list[CrawlResult]   (Mode B)            │
│    domain_sample_crawls: list[CrawlResult]                         │
│    prospect_traffic: DataForSEO traffic data                       │
│    domain_metrics: DataForSEO domain authority data               │
│    spam_signals: DataForSEO spam/footprint data                   │
│    sampled_article_urls: list[str]             (Mode B)            │
│    mode_detection_note: str | None                                  │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ide_gates.py                                                       │
│                                                                     │
│  Inputs:  IDEContext                                                │
│                                                                     │
│  Outputs: GateResult dataclass:                                     │
│    triggered: bool                                                  │
│    gate: HardExclusionGate | None                                   │
│    reason: str | None                                               │
│                                                                     │
│  If triggered: pipeline assembles verdict deterministically,       │
│  no further components run.                                         │
└────────────────────────────────┬────────────────────────────────────┘
                                  │ (only if not triggered)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ide_llm.py — call_1_classify_signals()                             │
│                                                                     │
│  Model: claude-haiku-4-5-20251001                                   │
│                                                                     │
│  Inputs:  IDEContext (crawled pages + target page topic)            │
│                                                                     │
│  Outputs: SignalScores dataclass:                                   │
│    p1_topical_relevance: float  (0–1)                              │
│    p2_content_quality: float                                        │
│    p4_obl_quality: float                                            │
│    p5_placement_feasibility: PlacementFeasibility enum             │
│    d1_topical_coherence: float                                      │
│    d4_editorial_integrity: EditorialIntegrityScores                │
│    d9_geo_targeting: float                                          │
│    language_match: float                                            │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ide_scorer.py                                                      │
│                                                                     │
│  Inputs:                                                            │
│    SignalScores (from LLM call 1)                                   │
│    DataForSEO data in IDEContext (D2, D3, D7, D8)                  │
│    mode (for confidence ceiling)                                    │
│                                                                     │
│  Outputs: ScoreResult dataclass:                                    │
│    cluster_scores: ClusterScores                                    │
│    investment_score: float  (0–100)                                 │
│    risk_multiplier: float                                           │
│    editorial_integrity_cap_applied: bool                            │
│    p5_cap_applied: bool                                             │
│    deterministic_confidence: str                                    │
│    confidence_ceiling: str  (mode-based)                           │
│    outcome_tier: InvestmentOutcome                                  │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ide_llm.py — call_2_assemble_verdict()                             │
│                                                                     │
│  Model: claude-haiku-4-5-20251001                                   │
│                                                                     │
│  Inputs:                                                            │
│    ScoreResult (all cluster scores + Investment Score)              │
│    IDEContext (mode, mode_b_subtype, sampled URLs)                  │
│    Target page topic and Bottleneck context (if available)          │
│                                                                     │
│  Outputs: InvestmentVerdict (partially filled):                     │
│    headline, primary_reason, supporting_signals, conditions        │
│    confidence_rationale, mode_qualifier (Mode B)                   │
│    llm_confidence (stored for audit; not surfaced)                 │
└────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  validation.py — validate_investment_verdict()                      │
│                                                                     │
│  Inputs:  Merged InvestmentVerdict (LLM output + scorer data)       │
│                                                                     │
│  Checks:                                                            │
│    • Schema validation (Pydantic, already run at parse time)       │
│    • hard_exclusion_triggered=True → outcome must be not_recommended│
│    • outcome=recommended → investment_score ≥ 68                   │
│    • outcome=with_conditions → conditions non-empty, specific      │
│    • outcome=not_recommended → primary_reason names specific signal │
│    • D4 < 0.30 → investment_score ≤ 45 (enforced deterministically) │
│    • confidence ≤ confidence_ceiling (override if LLM too high)    │
│    • Mode-specific field constraints (§6.3)                        │
│                                                                     │
│  Outputs: ValidationResult, validation_overrides list               │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 DataForSEO signals used and where

| Signal | Code | Used by | Purpose |
|---|---|---|---|
| URL-level traffic estimate | — | `ide_scorer.py` (P3) | Authority cluster input |
| Domain referring domains | D2 | `ide_scorer.py` | Authority cluster input |
| Domain traffic + 12mo trend | D3 | `ide_scorer.py` | Authority cluster input + risk signal |
| Spam footprint signals | D7 | `ide_gates.py` (H2, H5) + `ide_scorer.py` | Gate check + risk cluster |
| Domain history (age, ownership changes) | D8 | `ide_scorer.py` | Risk cluster input |

D3 trend also feeds the Risk cluster as `D3_trend`. The `D3_current` value feeds Authority.

### 4.3 Signals produced by LLM call 1

| Signal | Code | Mode A | Mode B |
|---|---|---|---|
| Topical relevance | P1 | Single-page relevance vs. target | Averaged across 3–5 sampled articles |
| Content quality | P2 | Single-page quality | Averaged across sampled articles |
| Outbound link quality | P4 | Single-page OBLs | Averaged OBLs from sampled articles |
| Placement feasibility | P5 | Does this link fit in this article? | Could we write an article for this section? |
| Topical coherence | D1 | From domain sample crawls | From domain sample crawls |
| Editorial integrity | D4 | From placement page + domain sample | From sampled articles + domain sample |
| Geo/language | D9 | TLD + content language + hreflang | Same |
| Language match | — | Is content language compatible? | Same |

P3 (organic traffic) is not an LLM signal — it comes from DataForSEO and is converted to a 0–1 float via a traffic tier mapping function in `ide_scorer.py`.

---

## 5. Hard Exclusion Gates — Placement and Logic

The gates run **in `collecting_data` phase**, as soon as the necessary signals are available. They are evaluated deterministically — no LLM needed.

### Gate evaluation order and signal requirements

| Gate | Trigger condition | Required signals |
|---|---|---|
| H3 — Malware | Google Safe Browsing flag | DataForSEO spam signals or a Safe Browsing API check |
| H1 — Prohibited content | Adult/escort/gambling-core/illegal/scam site | Crawled content + DataForSEO site category |
| H2 — Deindexed/penalized | Indexed ratio <10% AND near-zero traffic despite link history | D6 (indexed ratio) from DataForSEO + D3 traffic |
| H4 — Language impossible | Zero audience overlap | D9 (language detection from crawl) |
| H5 — Manual action | >80% traffic loss in 3 months AND backlink profile intact | D3 12-month trend + D2 backlink count |

**H3 runs first** (cheapest check; if the site has malware nothing else matters).

### Where in the code gates execute

```python
# In ide_orchestrator.py _run_ide_pipeline():

ctx = await collect(...)          # collecting_data state

gate_result = evaluate_gates(ctx)  # deterministic check
if gate_result.triggered:
    verdict = _assemble_gate_verdict(gate_result, ctx)
    # → write complete, no further work
    return
```

`evaluate_gates()` lives in `app/pipeline/ide_gates.py`. It returns a `GateResult` and never touches an LLM.

### What happens when a gate triggers

```
verdict.hard_exclusion_triggered = True
verdict.hard_exclusion_gate = gate_id   (e.g. "H1_prohibited_content")
verdict.hard_exclusion_reason = "..."   (specific, named reason)
verdict.outcome = "not_recommended"
verdict.cluster_scores = None
verdict.investment_score = None
verdict.editorial_integrity = None
```

The verdict is assembled directly in the orchestrator — no LLM call, no scoring. The Pydantic validation still runs to confirm schema correctness.

---

## 6. Mode A vs Mode B — Divergence and Convergence

### Where they diverge

**Point 1: Mode detection result (detecting_mode state)**

```
Input URL
    │
    ├── HEAD → GET response
    │
    ├── 4xx/5xx response         → Mode B / Domain-only
    │
    ├── body > 500 chars AND
    │   (date OR byline OR schema) AND
    │   NOT listing page?         → Mode A
    │
    ├── listing/category URL?
    │   non-root path              → Mode B / Category URL
    │   root path / bare domain   → Mode B / Domain-only
    │
    └── Ambiguous                 → Mode B (safe default), log note
```

**Point 2: Section inference (inferring_section state, Mode B/domain-only only)**

Mode B/domain-only runs a Haiku call before data collection:
```
Fetch robots.txt + sitemap.xml
Crawl homepage
→ Haiku: "Given this site navigation and these sections, which is most relevant to {target topic}?"
→ inferred_section = "https://example.com/seo-resources/" or similar
→ Proceed to collect articles from that section
```
This is a **third Haiku call** (on top of the standard 2). It only runs for domain-only sub-type.

**Point 3: What is crawled (collecting_data state)**

| Mode | Pages crawled | Article source |
|---|---|---|
| A | Specific placement page (1) + 2–3 domain sample pages | Known — it's the input URL |
| B / Category | 3–5 articles from the category URL | Extracted from the category page listing |
| B / Domain | 3–5 articles from the inferred section | Extracted from the inferred section listing |

In all modes, 2–3 domain sample pages are also crawled for D1 and D4 signals.

**Point 4: Haiku call 1 prompt variation**

The same tool schema is used in both modes, but the user message differs:
- Mode A: "Analyze this specific article as a placement candidate for a link to {target}."
- Mode B: "Analyze these {N} sampled articles from {site_section} as representative of where a link to {target} might be placed."

The tool schema and output model (`SignalScores`) are identical.

### Where they converge (after divergence)

| Step | Convergence point |
|---|---|
| Gate evaluation | Both modes: identical H1–H5 checks |
| Haiku call 1 | Both modes: same tool schema, same output model |
| Deterministic scoring | Both modes: identical formula, identical thresholds |
| Haiku call 2 | Both modes: same tool schema; receives `evaluation_mode` and `mode_b_subtype` to shape language |
| Validation | Both modes: same schema + business logic rules; mode-specific subset applied |
| Confidence ceiling | Enforced after validation for both modes |

### Confidence ceiling by mode

Enforced in `ide_scorer.py` (for calculation) and `validation.py` (as an override check):

| Mode | Sub-type | Ceiling | Impact |
|---|---|---|---|
| A | Specific placement | `high` | LLM may self-report any level; capped only if above high (impossible) |
| B | Category URL | `medium` | If LLM self-reports high → overridden to medium; recorded in validation_overrides |
| B | Domain only | `low` | If LLM self-reports medium or high → overridden to low |

The confidence ceiling is a **structural constraint, not a score penalty**. It reflects the epistemic limit of each evaluation type.

---

## 7. Deterministic Scoring ↔ LLM Reasoning Interaction

This is the most important architectural invariant of the IDE. The LLM produces **signal scores**, not verdicts. The verdict tier is determined **deterministically** from those scores. The LLM's second call then translates the deterministic verdict into plain language.

```
                    LLM Call 1                    Deterministic Scoring
                 ┌─────────────┐                 ┌──────────────────────┐
                 │             │                 │                      │
 Crawled pages  →  Signal      → P1, P2, P4,   → Cluster formulas     │
 DataForSEO     →  extraction    P5, D1, D4,     Authority, Relevance, │
 Target topic   →               D9 scores        Quality               │
                 │             │                 │                      │
                 └─────────────┘                 │ Risk multiplier      │
                                                 │ Investment Score     │
                                                 │ Editorial cap        │
                                                 │                      │
                                                 │ Outcome tier:        │
                                                 │  recommended /       │
                                                 │  with_conditions /   │
                                                 │  not_recommended /   │
                                                 │  insufficient_data   │
                                                 └──────────┬───────────┘
                                                            │
                    LLM Call 2                              │
                 ┌──────────────────────────────────────────▼────────────┐
                 │                                                        │
                 │  Input: all scores + outcome tier + mode context       │
                 │  Task: translate into a strategist-quality explanation │
                 │                                                        │
                 │  Output: headline, primary_reason, conditions,        │
                 │          mode_qualifier, confidence_rationale         │
                 │                                                        │
                 │  The LLM CANNOT change the outcome tier.              │
                 │  It CANNOT change the Investment Score.               │
                 │  It ONLY produces the verbal explanation.             │
                 └────────────────────────────────────────────────────────┘
```

### The scoring formula in full

```python
# Step 1: P3 conversion (DataForSEO traffic → 0–1 float)
# "high" ≥ 10k visits/mo → 0.90; "medium" 1k–10k → 0.65; "low" 100–1k → 0.35;
# "none" < 100 → 0.10; "unknown" → 0.30 (partial)

# Step 2: D3_current and D3_trend from DataForSEO traffic history
# D3_current: same conversion as P3 for domain-level traffic
# D3_trend: fraction of traffic retained over 12 months (e.g., 0.80 = 20% decline)

# Step 3: Risk cluster
risk_signals = {
    "d7": d7_spam_score,                    # DataForSEO, 0–1 (1 = clean)
    "d3_trend": d3_trend,                   # 0–1 (1 = stable/growing)
    "d8": d8_domain_history_score,          # 0–1 (1 = clean history)
    "d1_consistency": d1_topical_coherence, # from LLM call 1
    "p4_obl_flags": p4_obl_quality,        # from LLM call 1 (OBL patterns)
}
# Weighted average (60%) + minimum individual signal (40%)
weighted_avg = sum(weight * score for weight, score in risk_signals_weighted)
min_signal = min(risk_signals.values())
risk_score = (weighted_avg * 0.60) + (min_signal * 0.40)

# Risk → Multiplier
if risk_score >= 0.75:   risk_multiplier = 1.00
elif risk_score >= 0.55: risk_multiplier = 0.80
elif risk_score >= 0.35: risk_multiplier = 0.55
else:                    risk_multiplier = 0.25

# Step 4: Quality cluster caps
quality_raw = (d4 * 0.35) + (p4 * 0.25) + (p5_score * 0.20) + (d5 * 0.10) + (d6 * 0.10)
if d4 < 0.30:              quality = min(quality_raw, 0.40)
elif p5 == "implausible":  quality = min(quality_raw, 0.35)
else:                      quality = quality_raw

# Step 5: Cluster scores
relevance = (p1 * 0.45) + (d1 * 0.25) + (d9 * 0.20) + (language_match * 0.10)
authority  = (p3 * 0.35) + (p2 * 0.25) + (d2 * 0.25) + (d3_current * 0.15)
# quality already computed above

# Step 6: Investment Score
base_score = (relevance * 0.35) + (authority * 0.30) + (quality * 0.35)
investment_score = base_score * risk_multiplier * 100

# Step 7: Editorial integrity cap
if d4_overall < 0.30:
    investment_score = min(investment_score, 45)

# Step 8: Outcome tier (deterministic)
if relevance < 0.30 or risk_multiplier < 0.55 or d4_overall < 0.30:
    outcome = "not_recommended"
elif investment_score >= 68 and risk_multiplier >= 0.80 and d4_overall >= 0.55 and relevance >= 0.55:
    outcome = "recommended"
elif investment_score >= 48:
    outcome = "with_conditions"
else:
    outcome = "not_recommended"
```

Note: `p5_score` is a float derived from the `PlacementFeasibility` enum: `natural=1.0, workable=0.70, forced=0.35, implausible=0.0`.

### LLM self-reported confidence handling

The LLM's self-reported confidence (from call 2) is stored as `llm_confidence` on the verdict for audit purposes. The value surfaced to users and written to the `confidence` field is determined by:

```
final_confidence = min(deterministic_confidence, confidence_ceiling)
```

Where `deterministic_confidence` is computed by the signal-weight model in `confidence.py` (extended for IDE signals). If the LLM self-reports a higher confidence, the lower of the two takes precedence and the override is recorded in `validation_overrides`.

---

## 8. Failure Handling and Retry Strategy

### Per-component failure behavior

| Component | Failure | Behavior |
|---|---|---|
| Mode detection — URL fetch | 4xx/5xx | Default to Mode B / Domain-only; do not fail |
| Mode detection — classification | Ambiguous | Default to Mode B; log `mode_detection_note` |
| Section inference (Mode B/domain) | Haiku call fails | Retry once; on failure: fall back to homepage-linked articles; note in `data_quality` |
| Section inference — no match | No relevant section found | Sample from highest-traffic section; record note |
| Crawl (placement page / articles) | CrawlError | Partial data; lower confidence; do not raise |
| DataForSEO — traffic data | API error | Use `unknown` tier for P3; confidence -1 tier |
| DataForSEO — domain metrics | API error | D2 missing; confidence -1 tier; D7 gate cannot run → `insufficient_data` if H3/H2 cannot be assessed |
| Hard exclusion gate | Cannot assess H1 or H3 | Treat as missing signal; output `insufficient_data`, not `not_recommended` |
| LLM call 1 — validation failure | Pydantic parse error | Retry once with error in context; on second failure: `failed` state |
| LLM call 1 — API failure | Timeout / 5xx | Retry once with 5s backoff; on second failure: `failed` state |
| LLM call 2 — validation failure | Pydantic parse error | Retry once; on second failure: `failed` state |
| Insufficient data | Required signals unavailable | Verdict = `insufficient_data`, specify missing signals |

### Insufficient Data vs Failed

These are deliberately distinct:
- `insufficient_data`: The pipeline completed but required input signals were unavailable. The verdict says what is missing. The analysis is NOT charged.
- `failed`: A system error (LLM API down, database write error, unhandled exception). The analysis is NOT charged. The user can retry.

### LLM retry protocol

Both LLM calls follow the same retry pattern (already established in Sprint 2):

```python
try:
    response = await llm.call_with_tool(...)
    result = Schema.model_validate(response.tool_input)
except ValidationError as exc:
    # Retry once with error feedback
    retry_msg = f"Validation failed: {exc}. Correct the response."
    response = await llm.call_with_tool(messages=[..., error_msg], ...)
    result = Schema.model_validate(response.tool_input)  # raises on second failure → failed state
```

The Celery task has `max_retries=0` — retries happen inside the pipeline, not via Celery re-queuing. This keeps partial state visible in the DB throughout.

### Cache behavior

All DataForSEO calls and Firecrawl calls use the existing `APICache` with these TTLs:

| Data | Namespace | TTL |
|---|---|---|
| Prospect page crawl | `crawl` | 48h |
| Domain sample crawls | `crawl` | 48h |
| URL traffic estimate | `serp` (reuse) | 48h |
| Domain authority / backlinks | `backlinks_prospect` | 24h |
| Spam signals | `backlinks_prospect` | 24h |

Prospect site uses the `backlinks_prospect` TTL (24h, tighter than `backlinks_target` 72h) because freshness matters more for a new investment decision than for an existing competitive gap analysis.

---

## 9. Sequence Diagrams

### 9.1 Mode A — Specific Placement Evaluation

```
User        API          Celery/Orchestrator    Firecrawl    DataForSEO   Anthropic
 │           │                  │                   │             │            │
 │ POST      │                  │                   │             │            │
 │ /opp ────►│                  │                   │             │            │
 │           │ create record    │                   │             │            │
 │           │ enqueue task     │                   │             │            │
 │◄─── 202 ──│                  │                   │             │            │
 │           │                  │                   │             │            │
 │ GET /stream────────────────► │                   │             │            │
 │           │                  │                   │             │            │
 │           │    [status: detecting_mode]          │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │                   │             │            │
 │           │                  │─── HEAD/GET ─────►│             │            │
 │           │                  │◄── article page ──│             │            │
 │           │                  │  → Mode A detected│             │            │
 │           │                  │                   │             │            │
 │           │    [status: collecting_data]         │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │                   │             │            │
 │           │                  │─── crawl(placement_url) ───────►│            │
 │           │                  │─── crawl(domain_sample_1) ─────►│            │
 │           │                  │─── crawl(domain_sample_2) ─────►│            │
 │           │                  │─── traffic(placement_url) ──────────────────►│
 │           │                  │─── domain_metrics(prospect) ────────────────►│
 │           │                  │─── spam_signals(prospect) ──────────────────►│
 │           │                  │◄── all results (parallel) ──────┤             │
 │           │                  │                   │             │            │
 │           │                  │  evaluate_gates() [H1–H5]        │            │
 │           │                  │  → gates clean                   │            │
 │           │                  │                   │             │            │
 │           │    [status: classifying_signals]     │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │─── Haiku call 1 (signal extraction) ────────►│
 │           │                  │◄── P1,P2,P4,P5,D1,D4,D9 scores ─────────────│
 │           │                  │                   │             │            │
 │           │    [status: computing_score]         │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │  compute clusters (deterministic)│            │
 │           │                  │  Investment Score = 74.2         │            │
 │           │                  │  outcome = recommended           │            │
 │           │                  │                   │             │            │
 │           │    [status: assembling_verdict]      │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │─── Haiku call 2 (verdict assembly) ─────────►│
 │           │                  │◄── headline, primary_reason, conditions ─────│
 │           │                  │                   │             │            │
 │           │                  │  validate_investment_verdict()   │            │
 │           │                  │  confidence ceiling: high        │            │
 │           │                  │  persist verdict                 │            │
 │           │                  │                   │             │            │
 │           │    [status: complete]                │             │            │
 │◄── SSE ───│◄──────────────── │                   │             │            │
 │           │                  │                   │             │            │
```

### 9.2 Mode B — Domain Only (with section inference)

```
User        API          Celery/Orchestrator    Firecrawl    DataForSEO   Anthropic
 │           │                  │                   │             │            │
 │ POST /opp │                  │                   │             │            │
 │ (domain) ►│  create+enqueue  │                   │             │            │
 │◄─ 202 ────│                  │                   │             │            │
 │           │                  │                   │             │            │
 │           │    [status: detecting_mode]          │             │            │
 │◄── SSE    │                  │                   │             │            │
 │           │                  │─── HEAD(domain) ─►│             │            │
 │           │                  │◄── non-article ───│             │            │
 │           │                  │  → Mode B/domain  │             │            │
 │           │                  │                   │             │            │
 │           │    [status: inferring_section]       │             │            │
 │◄── SSE    │                  │                   │             │            │
 │           │                  │─── crawl(robots.txt) ──────────►│            │
 │           │                  │─── crawl(sitemap.xml) ──────────►│            │
 │           │                  │─── crawl(homepage) ─────────────►│            │
 │           │                  │◄── all results ────────────────►│            │
 │           │                  │─── Haiku: match sections to topic ──────────►│
 │           │                  │◄── inferred_section = "/seo/" ───────────────│
 │           │                  │                   │             │            │
 │           │    [status: collecting_data]         │             │            │
 │◄── SSE    │                  │                   │             │            │
 │           │                  │─── crawl(section listing) ──────►│            │
 │           │                  │  → extract 5 article URLs        │            │
 │           │                  │─── crawl(article 1) ────────────►│            │
 │           │                  │─── crawl(article 2) ────────────►│            │
 │           │                  │─── crawl(article 3) ────────────►│            │
 │           │                  │─── crawl(article 4) ────────────►│            │
 │           │                  │─── crawl(domain_sample_1) ──────►│            │
 │           │                  │─── traffic(article URLs) ────────────────────►│
 │           │                  │─── domain_metrics(prospect) ────────────────►│
 │           │                  │─── spam_signals(prospect) ──────────────────►│
 │           │                  │◄── all results ─────────────────┤             │
 │           │                  │                   │             │            │
 │           │                  │  evaluate_gates() H1–H5          │            │
 │           │                  │  → gates clean                   │            │
 │           │                  │                   │             │            │
 │           │    [status: classifying_signals]     │             │            │
 │◄── SSE    │                  │─── Haiku call 1 (multi-article analysis) ───►│
 │           │                  │◄── averaged P1,P2,P4,P5,D1,D4,D9 ───────────│
 │           │                  │                   │             │            │
 │           │    [status: computing_score]         │             │            │
 │◄── SSE    │                  │  compute clusters + score         │            │
 │           │                  │  Investment Score = 51.3         │            │
 │           │                  │  outcome = with_conditions        │            │
 │           │                  │                   │             │            │
 │           │    [status: assembling_verdict]      │             │            │
 │◄── SSE    │                  │─── Haiku call 2 (verdict with mode_qualifier) ►│
 │           │                  │◄── verdict + mode_qualifier ─────────────────│
 │           │                  │                   │             │            │
 │           │                  │  validate() + confidence ceiling: LOW         │
 │           │                  │  confidence overridden: medium → low         │
 │           │                  │  persist verdict                 │            │
 │           │    [status: complete]                │             │            │
 │◄── SSE    │                  │                   │             │            │
```

### 9.3 Hard Exclusion Gate Triggered

```
Orchestrator    Firecrawl    DataForSEO
      │               │             │
      │─── crawl ────►│             │
      │─── metrics ────────────────►│
      │◄── results ───┤             │
      │                             │
      │  evaluate_gates()
      │  H1 triggers: prohibited content
      │  (adult/escort detected in crawled pages)
      │
      │  assemble gate verdict (no LLM, no scoring)
      │  outcome = not_recommended
      │  hard_exclusion_triggered = True
      │  status → complete (immediately)
      │
      │  publish SSE: complete {outcome: not_recommended, gate: H1}
```

---

## 10. Database Changes Required

### Migration 0003: create opportunities table

The `opportunities` table is defined in §9.2 of the architecture but has not been implemented. It needs additions to match the Sprint 3 design.

```sql
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id UUID REFERENCES pages(id) ON DELETE CASCADE NOT NULL,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    
    -- The prospect being evaluated
    prospect_url TEXT NOT NULL,
    prospect_domain TEXT NOT NULL,
    
    -- Evaluation mode (set during mode detection)
    evaluation_mode TEXT CHECK (evaluation_mode IN ('specific_placement', 'guest_post_opportunity')),
    mode_b_subtype TEXT CHECK (mode_b_subtype IN ('category_url', 'domain_inferred')),
    inferred_section TEXT,
    
    -- State machine
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued', 'detecting_mode', 'inferring_section',
            'collecting_data', 'classifying_signals', 'computing_score',
            'assembling_verdict', 'complete', 'failed'
        )),
    
    -- Prompt versioning
    prompt_version TEXT,          -- e.g. "opportunity/v1"
    
    -- Computed scores (stored for debugging and UI)
    investment_score FLOAT CHECK (investment_score >= 0 AND investment_score <= 100),
    cluster_scores JSONB,         -- ClusterScores schema
    
    -- Verdict
    opportunity_verdict JSONB,    -- InvestmentVerdict schema
    overall_outcome TEXT CHECK (overall_outcome IN (
        'recommended', 'with_conditions', 'not_recommended', 'insufficient_data'
    )),
    confidence TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    confidence_ceiling TEXT CHECK (confidence_ceiling IN ('low', 'medium', 'high')),
    
    -- Audit
    validation_overrides JSONB,
    data_quality JSONB,
    
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_reason TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_opportunities_page_id ON opportunities(page_id);
CREATE INDEX idx_opportunities_workspace_id ON opportunities(workspace_id);
CREATE INDEX idx_opportunities_outcome ON opportunities(overall_outcome);
CREATE INDEX idx_opportunities_status ON opportunities(status);
```

### No changes to existing tables

`page_analyses`, `pages`, `sites`, `workspaces`, and `users` do not need changes for Sprint 3.

### New Pydantic schemas (in `app/schemas/opportunities.py`)

The `InvestmentVerdict` schema (§6.3 of the architecture) is the target schema. Key models to implement:

- `InvestmentOutcome` (enum)
- `HardExclusionGate` (enum)
- `PlacementFeasibility` (enum)
- `PlacementPageSignals` (model)
- `ClusterScores` (model)
- `EditorialIntegrityScores` (model)
- `InvestmentVerdict` (model)
- `SignalScores` (internal — LLM call 1 output, not stored directly)
- `ScoreResult` (internal — scorer output, not stored directly)

---

## 11. New Files Required

### Required before any code is written

| File | Why required before code |
|---|---|
| `docs/prompts/opportunity-v1.md` | §5.5 explicitly requires this prompt spec as a deliverable before Sprint 3. The two Haiku call prompts (signal extraction + verdict assembly) must be written, structured, and reviewed here before being implemented in code. This is the same requirement that produced `docs/prompts/summarize-page-v1.md` before the summarizer was built. |

### New pipeline files

| File | Responsibility |
|---|---|
| `app/pipeline/ide_collector.py` | Mode detection, section inference (Mode B/domain), data collection orchestration. Returns `IDEContext` dataclass. |
| `app/pipeline/ide_gates.py` | Hard exclusion gate evaluation (H1–H5). Deterministic, no LLM. Returns `GateResult`. |
| `app/pipeline/ide_llm.py` | Two async functions: `call_1_classify_signals()` and `call_2_assemble_verdict()`. Both use Haiku. Both include retry logic. |
| `app/pipeline/ide_scorer.py` | Deterministic scoring: cluster formulas, risk multiplier, Investment Score, editorial cap, outcome tier determination, confidence calculation. Pure functions with no I/O. |
| `app/pipeline/ide_orchestrator.py` | Celery task `serpnex.run_ide`. State machine, DB writes, Redis pub/sub, `enqueue_opportunity()` public API. |

### New API file

| File | Responsibility |
|---|---|
| `app/api/v1/opportunities.py` | `POST /opportunities`, `GET /opportunities/{id}`, `GET /opportunities/{id}/stream` |

### New schema file

| File | Responsibility |
|---|---|
| `app/schemas/opportunities.py` | All Pydantic models for the IDE: `InvestmentVerdict`, `InvestmentOutcome`, `HardExclusionGate`, `PlacementFeasibility`, `ClusterScores`, `EditorialIntegrityScores`, `PlacementPageSignals`, `SignalScores` |

### New migration

| File | Responsibility |
|---|---|
| `alembic/versions/0003_opportunities_schema.py` | Creates `opportunities` table |

### New tests (minimum required before Sprint 3 is closed)

| File | Covers |
|---|---|
| `tests/test_ide_gates.py` | All 5 gates — trigger and no-trigger for each |
| `tests/test_ide_scorer.py` | Cluster formulas, risk multiplier, editorial cap, P5 cap, outcome tier thresholds, confidence ceiling enforcement |
| `tests/test_ide_e2e.py` | Full pipeline: Mode A happy path, Mode B/category happy path, gate-triggered path, data collection failure path, Celery task registration |

---

## 12. Risks Before Implementation

### Risk 1 — Section inference accuracy (HIGH likelihood, HIGH impact)

**What can go wrong:** The Haiku call that matches site sections to the target topic may infer the wrong section (e.g., matches the wrong category, or infers "marketing" when the target topic is "SEO"). This produces article samples from the wrong section, invalidating P1 and P5.

**Mitigation:**
- Surface `inferred_section` prominently in the verdict. Users can re-submit with the correct category URL to get a more accurate evaluation.
- Validate the inference prompt with 5–10 real domain examples before shipping.
- If section inference confidence is low (e.g., no clear topic match), sample from homepage-linked articles and note the limitation — do not silently pick a poor section.

---

### Risk 2 — LLM signal score calibration (MEDIUM likelihood, HIGH impact)

**What can go wrong:** P1, P2, D4, and D1 are 0–1 float scores produced by the LLM. The thresholds that determine verdict tiers (e.g., Relevance ≥ 0.55 for `recommended`) are hand-tuned. Initial production verdicts may cluster incorrectly — too many `with_conditions` outcomes that should be `recommended`, or vice versa.

**Mitigation:**
- Test the prompt with 10–15 real prospect URLs before Sprint 3 closes.
- Record the raw scores for each URL and manually verify that the resulting outcome tiers match expert expectation.
- The thresholds live exclusively in `ide_scorer.py` (not the prompts), so they can be tuned without changing the LLM prompts or re-running API calls.

---

### Risk 3 — DataForSEO traffic tier mapping (MEDIUM likelihood, MEDIUM impact)

**What can go wrong:** DataForSEO URL-level traffic estimates are approximate and categorical in their API response. The mapping from a traffic estimate to a P3 score float requires a conversion function. Incorrect thresholds produce misleading Authority cluster scores.

**Mitigation:**
- The traffic tier → float mapping is a pure function in `ide_scorer.py`. Define it explicitly with documented thresholds before implementation. Capture it in the decisions log.
- Test the mapping function independently.

---

### Risk 4 — H2 gate signal availability (MEDIUM likelihood, HIGH impact)

**What can go wrong:** The H2 gate (deindexed/penalized) requires knowing the indexed page ratio, which is not directly available from DataForSEO without a specific indexed-pages query. If the signal is unavailable, the gate cannot fire — a penalized site may pass H2.

**Mitigation:**
- For MVP, approximate H2 using D3 traffic (near-zero traffic) + D7 spam signal combination as a proxy. If DataForSEO returns a spam score above a threshold AND traffic is near-zero, treat as H2 trigger.
- Document this approximation in the prompt spec and in the decision log.
- The exact H2 gate trigger is a known data limitation — surface it honestly in the `data_quality` field.

---

### Risk 5 — Mode detection misclassification (HIGH likelihood, LOW impact)

**What can go wrong:** Some URLs are ambiguous. A long product page with publication signals looks like an article. A blog index with no pagination looks like a single page.

**Mitigation:**
- Default to Mode B on any ambiguity (the safer output — a lower confidence ceiling is honest).
- Record `mode_detection_note` in all ambiguous cases.
- Mode B / Category URL is always the correct fallback when unsure — it is more precise than domain-only.

---

### Risk 6 — Two LLM calls with interdependent schemas (MEDIUM likelihood, MEDIUM impact)

**What can go wrong:** Call 1 output feeds into both the deterministic scorer (via `SignalScores`) and as context for Call 2. If the schema for `SignalScores` is not designed carefully, impedance mismatches arise — the scorer expects a float where the LLM produced a string, or Call 2 receives incomplete score context.

**Mitigation:**
- Design `SignalScores` and `ScoreResult` schemas before writing any LLM prompts. These schemas must be finalized in the prompt spec doc.
- The scorer is a pure function: it can be unit-tested with synthetic signal inputs before the LLM integration is written.

---

### Risk 7 — `opportunity-v1.md` prompt quality (HIGH likelihood, HIGH impact)

**What can go wrong:** The two Haiku prompts (call 1 signal extraction, call 2 verdict assembly) are the highest-risk new prompts in the system. Call 1 must correctly score P1, P2, P4, P5, D1, D4, and D9 from crawled content. If the prompt is under-specified, scores will be inconsistent across similar sites.

**Mitigation:**
- Write `docs/prompts/opportunity-v1.md` with the same rigor as `bottleneck-v1.md`: explicit rules for each signal, forbidden language, enumerated decision space, validation checklist.
- The prompt spec is the first deliverable of Sprint 3 — it must be reviewed and approved before any code is written, following the same workflow rule applied to `summarize-page-v1.md`.

---

### Risk 8 — Verdict assembly (call 2) overriding the deterministic outcome (LOW likelihood, HIGH impact)

**What can go wrong:** The call 2 prompt asks the LLM to translate a pre-computed score into plain language. If the prompt is ambiguous, the LLM may attempt to "correct" the outcome tier based on its own reasoning, conflicting with the deterministic result.

**Mitigation:**
- The call 2 prompt must explicitly state: "The outcome tier has already been determined as `{outcome}`. Your task is to explain it in plain language — not to evaluate or change it."
- The tool schema for call 2 does NOT include the `outcome` field. The outcome is set by the scorer, not the LLM.
- Validation checks that the outcome field in the merged `InvestmentVerdict` matches the scorer's determination.

---

## Summary — Before Sprint 3 Begins

**One required deliverable:** `docs/prompts/opportunity-v1.md` — the two-call Haiku prompt specification. This must be written and approved before any Sprint 3 code is written.

**Implementation order (once prompts are approved):**
1. `alembic/versions/0003_opportunities_schema.py` + DB model updates
2. `app/schemas/opportunities.py` — all Pydantic models
3. `app/pipeline/ide_gates.py` — deterministic, pure functions
4. `app/pipeline/ide_scorer.py` — deterministic, pure functions, unit-testable without LLM
5. `app/pipeline/ide_collector.py` — data collection + mode detection
6. `app/pipeline/ide_llm.py` — Haiku call 1 and call 2
7. `app/pipeline/ide_orchestrator.py` — Celery task + state machine
8. `app/api/v1/opportunities.py` — REST + SSE endpoints
9. Tests for each component (gates, scorer, E2E pipeline)

**No Sprint 3 code is written until this document is approved.**
