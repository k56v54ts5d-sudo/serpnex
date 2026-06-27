# Serpnex Intelligence Architecture

**Document type:** Pre-implementation technical architecture  
**Status:** Complete — no code should be written until this document is reviewed and approved  
**Date:** 2026-06-24  
**Scope:** Covers all intelligence decisions: data sources, pipeline, LLM usage, prompts, schemas, validation, confidence, database, costs, and MVP scope

---

## Purpose of this document

This document answers one question with precision: **how does a URL become a verdict?**

Every recommendation here traces back to the product's core invariant — *Decision → Reason → Action* — and to the four-module object model: Readiness, Bottleneck, Opportunities, Execution. The architecture must serve those modules. Where tradeoffs exist, this document states them explicitly and commits to a choice.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Data Sources](#2-data-sources)
3. [Analysis Pipeline](#3-analysis-pipeline)
4. [LLM Architecture](#4-llm-architecture)
5. [Prompt Architecture](#5-prompt-architecture)
6. [Structured Output Schema](#6-structured-output-schema)
7. [Validation Layer](#7-validation-layer)
8. [Confidence Scoring Model](#8-confidence-scoring-model)
9. [Database Schema](#9-database-schema)
10. [Cost Per Analysis](#10-cost-per-analysis)
11. [API Provider Recommendations](#11-api-provider-recommendations)
12. [MVP Technical Scope](#12-mvp-technical-scope)

---

## 1. System Architecture

### 1.1 Overview

Serpnex is a **multi-stage analysis orchestration system** with a thin web layer on top. The core of the product is not a database or a dashboard — it is a pipeline that ingests a URL and a set of external signals, reasons over them with an LLM, and produces a structured, verifiable verdict. The web layer is a display surface for that verdict.

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT (web app)                     │
└────────────────────────────────┬────────────────────────────┘
                                 │ REST / WebSocket (verdict updates)
┌────────────────────────────────▼────────────────────────────┐
│                         API GATEWAY                         │
│             (Auth, rate limiting, quota enforcement)        │
└────────────────────────────────┬────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────┐
│                      ANALYSIS ORCHESTRATOR                  │
│  Triggers on demand. Coordinates all workers.               │
│  Writes partial state to DB. Emits progress events.         │
└────┬──────────────┬──────────────┬───────────────┬──────────┘
     │              │              │               │
┌────▼───┐  ┌───────▼──┐  ┌───────▼──┐  ┌────────▼──────┐
│CRAWLER │  │ DATA     │  │  LLM     │  │  VERDICT      │
│WORKER  │  │ FETCHER  │  │  WORKER  │  │  ASSEMBLER    │
│        │  │ WORKER   │  │          │  │               │
│Page    │  │GSC, SERP,│  │Reasoning │  │Merges module  │
│content,│  │backlinks,│  │per module│  │outputs into   │
│crawl   │  │competitor│  │          │  │final verdict  │
│signals │  │metrics   │  │          │  │objects        │
└────────┘  └──────────┘  └──────────┘  └───────────────┘
                                                │
                                    ┌───────────▼───────────┐
                                    │       DATABASE        │
                                    │  (PostgreSQL + Redis) │
                                    └───────────────────────┘
```

### 1.2 Technology choices

**Backend:** Node.js (TypeScript) or Python. **Recommendation: Python.** Reasoning: the ML/AI ecosystem (LLM SDKs, text processing, data validation with Pydantic) is native to Python. The backend is not a CRUD API — it is a reasoning pipeline. Python fits that work better than Node. Trade-off: Node is faster for high-concurrency I/O, but analysis jobs are CPU/network-bound and long-running, not concurrent-lightweight. Python's async (asyncio) is sufficient for the job queue model being used here.

**Job queue:** **Celery + Redis.** Analysis jobs are not HTTP request/response — they take 30 seconds to 2 minutes, fan out to multiple APIs, and must survive server restarts. Celery handles retries, priorities, and worker isolation cleanly. Alternative: a managed job queue (BullMQ on Node, or a cloud queue like SQS). Risk with managed cloud queues: vendor lock-in and added latency. Celery is the well-understood default for Python async work.

**Database:** **PostgreSQL.** Verdicts are structured documents (JSONB) with relational ownership (workspaces → sites → pages). PostgreSQL handles both. NoSQL alternatives (DynamoDB, MongoDB) solve the document storage problem but introduce complexity for the relational queries (e.g., "all pages analyzed this month across a workspace"). PostgreSQL JSONB with indexes handles this without splitting into two data stores.

**Cache:** **Redis.** Two purposes: (1) backing Celery, (2) caching expensive external API responses (SERP data, backlink metrics) with TTLs. This is the primary cost-control mechanism — see §10.

**Real-time updates:** **Server-Sent Events (SSE)** for analysis progress (the "strategist thinking" UI experience). WebSockets are heavier and bidirectional; the client only needs to receive progress events in one direction. SSE is simpler, HTTP-native, and sufficient. The analysis orchestrator writes progress steps to Redis pub/sub; the API gateway streams them to the client as SSE.

**API layer:** **FastAPI.** Python, async-native, auto-generates OpenAPI spec, Pydantic integration out of the box. Django REST Framework is the alternative; it is heavier and not async-first.

### 1.3 Deployment topology

**Recommendation: Railway or Render (initial MVP), migrating to AWS (scale).**

At MVP the product needs to be shipped, not operated. Managed platforms (Railway, Render) handle deployments, SSL, environment variables, and database provisioning. The analysis workers run as separate background worker processes on the same platform.

Migration trigger: when monthly active analyses exceed ~50,000/month, when multi-region latency matters for GCC users, or when custom VPC requirements emerge. At that point move to AWS ECS (workers) + RDS PostgreSQL + ElastiCache Redis + API Gateway.

**Risk:** Running LLM API calls and external data API calls from a managed PaaS means traffic egress costs can surprise at scale. Mitigate: aggressive caching from day one.

---

## 2. Data Sources

The intelligence quality ceiling is determined by data quality. This section defines exactly what data is needed for each module, where it comes from, and what happens when it is missing.

### 2.1 Data source map by module

| Signal | Readiness | Bottleneck | Opportunities | Execution |
|---|---|---|---|---|
| Page HTML content (crawled) | ✅ primary | ✅ | ✅ (prospect page) | ✅ |
| Google Search Console | ✅ primary | ✅ primary | — | — |
| SERP (top results for target keywords) | — | ✅ primary | — | — |
| Competitor page content (crawled) | — | ✅ | — | — |
| Competitor backlink profile | — | ✅ primary | — | — |
| Target page backlink profile | ✅ | ✅ | — | ✅ primary |
| Prospect site backlink/authority | — | — | ✅ primary | — |
| Prospect site content/topic match | — | — | ✅ primary | — |
| Link spam/footprint signals | — | — | ✅ primary | — |
| Anchor text distribution | — | — | — | ✅ primary |

### 2.2 Google Search Console (first-party, high trust)

**What we pull:** clicks, impressions, average position, CTR per URL, per keyword, over the last 90 days. Also: landing page performance breakdowns.

**How:** OAuth2 flow during onboarding. Uses the [Search Console API](https://developers.google.com/webmaster-tools/search-console-api-original/v3/). Property must be verified in the user's GSC account.

**When missing:** GSC connection is optional but materially degrades Readiness and Bottleneck quality. Without GSC: we cannot see real keyword rankings, CTR, or impression data. Confidence drops to Low or Medium. The UI must surface this honestly — not as an error but as an explanation ("GSC not connected — ranking signals estimated from SERP position only"). Do not block analysis; degrade gracefully.

**Freshness:** pull on every analysis run. Cache the raw GSC response for 24 hours per property (GSC data has a 24-48 hour lag anyway). Do not pull intraday.

**Risk:** GSC API quotas are generous (2,000 requests/day per project for most properties) but shared across all users. If a workspace has 10 users running simultaneous analyses, quota pressure emerges. Mitigation: batch GSC calls, cache aggressively, implement a per-workspace rate-limit on analysis runs.

### 2.3 SERP Data

**What we need:** the top 5-10 organic results for the target page's primary keywords. From those results, URLs of the competitor pages so we can crawl them.

**Why this is critical:** Bottleneck analysis is a competitive gap analysis. We need to know who is ranking above the target page and approximately how strong they are. Without this, Bottleneck becomes speculative.

**How to get it:** a third-party SERP API. See §11 for provider comparison.

**What signals we extract:**
- URLs of top-ranking pages (to crawl)
- SERP features present (featured snippet, PAA, etc. — signals if intent is informational/commercial)
- Number of results (very high = competitive; very low = low-volume niche)

**Challenge — identifying the right keywords:** a page may rank for hundreds of keywords. We need to identify the primary 1-3 keywords that represent the page's strategic intent. Strategy:
1. Pull GSC data — use the keyword with the highest impression volume where the page is in positions 1-20.
2. If no GSC: use the page's `<title>` and `<h1>` to infer the primary keyword cluster and send to SERP.
3. If the page has no rank and no GSC: use content extraction to identify the primary topic, then use SERP to understand the competitive landscape.

**Assumption challenged:** The design brief implies Bottleneck always produces a definitive verdict. For brand-new pages with no GSC data and no ranking history, the SERP competitive landscape is still accessible, but the comparison is weakened. The confidence model must reflect this.

### 2.4 Backlink Data

**What we need per module:**
- **Bottleneck:** approximate referring domain (RD) count for the target page AND each top-3 competitor page. We need the gap, not an exhaustive list.
- **Opportunities:** referring domain count, domain rating/authority, spam score, and link-selling footprint indicators for the prospect site.
- **Execution:** anchor text distribution of the target page's current backlink profile.

**Critical decision — backlink provider:** This is the most expensive recurring external cost. See §11 for detailed provider analysis. The key tradeoff: Ahrefs has the most comprehensive index but its API is expensive; DataForSEO resells Ahrefs-adjacent data at lower cost; Moz's index is smaller but pricing is accessible at MVP scale.

**Freshness:** backlink data changes daily but slowly for most pages. Cache backlink snapshots for 72 hours. For opportunity evaluation, a fresh pull is more important (the prospect site's profile matters). Set TTL accordingly: target page cache = 72h, prospect site cache = 24h.

### 2.5 Page Crawling

**What we need:** raw HTML, rendered HTML (for JS-heavy pages), title, meta description, H1, body content, internal link structure, word count, content quality signals.

**How:** A crawl worker using **Playwright** for rendered HTML (handles React/Next.js pages) with a fallback to a lightweight HTTP fetch for simple pages. Playwright is necessary because many modern pages require JavaScript rendering to expose their content.

**Risk:** Playwright is heavy (headless Chromium). At scale this becomes a resource hog. Mitigation for MVP: limit crawl to the target page and the top 3 competitor pages per analysis. For competitors, a lightweight text extraction is often sufficient — full Playwright rendering is only needed if the page returns empty content on plain HTTP fetch.

**Alternative considered: Firecrawl / Jina AI** — managed crawling APIs that handle rendering, rate limiting, and return clean markdown. These are simpler to operate but add per-crawl cost ($0.001-0.003/page). At MVP volume (hundreds of analyses/month) this is negligible. **Recommendation: use Firecrawl for MVP to avoid operating Playwright infrastructure.** Switch to self-hosted Playwright if crawl costs exceed $200/month or if customization is needed (custom headers, login, etc.).

### 2.6 What happens when data is unavailable

Every module must be designed with a degradation model:

| Missing data | Module affected | Degradation behavior |
|---|---|---|
| No GSC | Readiness, Bottleneck | Confidence drops to Low/Medium; ranking signals estimated from SERP |
| SERP unavailable | Bottleneck | Cannot identify competitors; Bottleneck deferred with explanation |
| Backlink API unreachable | Bottleneck, Opportunities | Use cached data if <72h old; else confidence drops, warn user |
| Page returns 404/403 | All | Hard failure on that URL; surface as recoverable error |
| JS-heavy page, crawl fails | Readiness | Partial content only; flag in verdict |
| Very new page (<30 days) | All | "Insufficient signal" state; offer partial verdict with caveats |

---

## 3. Analysis Pipeline

### 3.1 The pipeline as a state machine

Each analysis job is a **state machine** with defined transitions. The orchestrator moves the job through states; each state transition is written to the database so partial results are never lost.

```
QUEUED
  → COLLECTING_DATA
      ├── crawl_page          (Firecrawl → raw rendered HTML + markdown)
      ├── fetch_gsc           (GSC API → keyword/position/impression data)
      ├── fetch_serp          (DataForSEO → top organic result URLs)
      ├── crawl_competitors   (Firecrawl × 3, parallel)
      └── fetch_backlinks     (DataForSEO → RDs for target + competitors)
  → DATA_READY
  → SUMMARIZING_CONTENT       ← NEW: LLM preprocessing stage (see §3.1a)
      ├── summarize_target_page    (Haiku → structured content summary)
      └── summarize_competitors    (Haiku × 3, parallel → competitor summaries)
  → SUMMARIES_READY
  → RUNNING_READINESS
  → RUNNING_BOTTLENECK
  → RUNNING_OPPORTUNITIES (if triggered separately)
  → ASSEMBLING_VERDICT
  → COMPLETE
  → FAILED (with reason)
```

Progress steps emitted to SSE correspond to the "strategist thinking" UI experience. Each step is a human-readable label mapped to an internal state:

| Internal state | UI label |
|---|---|
| `crawl_page` | "Reading the page…" |
| `fetch_gsc` | "Checking your Search Console signals…" |
| `fetch_serp` + `crawl_competitors` | "Comparing against the current top results…" |
| `fetch_backlinks` | "Measuring authority gaps…" |
| `SUMMARIZING_CONTENT` | "Analysing content and structure…" |
| `RUNNING_READINESS` | "Assessing content readiness…" |
| `RUNNING_BOTTLENECK` | "Diagnosing what's holding this page back…" |
| `ASSEMBLING_VERDICT` | "Writing up the verdict…" |

### 3.1a Content summarization stage (NEW — required before Bottleneck prompt)

**What it is:** A dedicated LLM preprocessing step that converts raw crawled page content into structured content summaries before any analysis prompt runs. This stage runs after data collection and before Readiness or Bottleneck.

**Why it exists:** The Bottleneck prompt requires content summaries in a specific format (100–150 words for target, 60–100 words per competitor) that capture topic/angle, format, heading structure, intent alignment, notable elements, and visible content gaps. Raw HTML is too token-expensive and too noisy. Rule-based extraction (headings + first paragraph only) is too shallow — it misses the qualitative content characterization the Bottleneck model needs to reason about intent mismatch.

**Model:** Claude Haiku 4.5. The summarization task is classification and description, not complex reasoning. Haiku is sufficient and keeps this stage cheap (~$0.001 per page).

**Input per page:** Firecrawl markdown output (the rendered page content, stripped of navigation/footer/sidebar noise by Firecrawl). Title, H1, all H2 subheadings, and word count are extracted deterministically before the LLM call and passed as structured fields alongside the body text.

**Output per page:** A structured summary matching the format defined in `docs/prompts/bottleneck-v1.md §3`. The summarization prompt must enforce:
- Descriptive language only — no evaluative statements ("comprehensive," "weak," "good")
- Explicit format label from the approved taxonomy
- Intent alignment description (does the format serve the inferred search intent?)
- Visible content gaps (what is notably absent?)

**Critical requirement:** The summarization prompt is a first-class deliverable. It must be written with the same rigor as the Bottleneck prompt, stored in `docs/prompts/summarize-page-v1.md`, versioned, and validated before the pipeline ships to production. See assumption A20 in `docs/validation/assumptions.md`.

**Pipeline Validation gate:** After the summarization pipeline is built (Sprint 2), a Pipeline Validation must confirm that automated summaries produce Bottleneck verdicts consistent with those from the 10-URL prompt validation. See A20 for the validation procedure. This is a pre-launch gate, not a pre-Sprint-1 gate.

**Cost:** ~$0.001 per page (target) + ~$0.003 (3 competitors) = ~$0.004 per full analysis. Added to §10 cost table.

**Latency:** ~3–5 seconds for 4 parallel Haiku calls. Runs in parallel (target + 3 competitors simultaneously). Added to the `SUMMARIZING_CONTENT` pipeline state which overlaps with backlink fetching in the queue.

### 3.1b Future enhancement: ContentSignals (planned, post-Sprint 3)

**Status:** Planned. Not implemented. Current summarization stage is unchanged.

**Motivation:** The current `PageSummary` schema returns prose descriptions (topic, format, gaps as string lists). This is sufficient for qualitative Bottleneck reasoning but insufficient for structured gap analysis — particularly when the primary constraint is content depth. A prose-to-prose comparison between target and competitor summaries asks the LLM to infer differences that could instead be expressed as structured signals.

**Design intent:** Extend the existing Haiku summarization call to return a `ContentSignals` object alongside the current `PageSummary`. This is not a new pipeline stage and does not add a new LLM call. The same Haiku call receives an extended tool schema and returns both the prose summary (unchanged) and structured signals in a single response.

**Planned signals:**

| Signal | Type | Notes |
|---|---|---|
| `subtopics_covered` | `list[str]` | Subtopics the page explicitly addresses, relevant to the target keyword |
| `subtopics_missing` | `list[str]` | Subtopics expected for the keyword that the page omits |
| `entity_coverage` | `list[str]` | Named brands, tools, people, and concepts referenced |
| `depth` | `"shallow" \| "adequate" \| "deep"` | LLM-assessed content depth relative to the topic |
| `has_original_data` | `bool` | Whether the page contains original research, proprietary statistics, or first-party studies |
| `has_expert_attribution` | `bool` | Whether the page includes expert quotes, author credentials, or cited external expertise |
| `structural_completeness` | `float` | 0–1; derivable deterministically from heading depth and count |

**Schema sketch (not final — to be designed after Sprint 3 production data):**

```python
class ContentSignals(BaseModel):
    subtopics_covered: list[str]
    subtopics_missing: list[str]
    entity_coverage: list[str]
    depth: Literal["shallow", "adequate", "deep"]
    has_original_data: bool
    has_expert_attribution: bool
    structural_completeness: float  # deterministic, not LLM-extracted

class PageSummary(BaseModel):
    # existing fields — unchanged
    topic_and_angle: str
    format_label: str
    heading_structure: str
    intent_alignment: str
    notable_elements: list[str]
    visible_content_gaps: list[str]
    # new — added when ContentSignals is implemented
    signals: ContentSignals | None = None
```

**Downstream consumers when implemented:**
- **Bottleneck worker** — receives `target_signals` and `competitor_signals` as structured data; can compare `subtopics_missing` against competitor `subtopics_covered` directly rather than inferring gaps from prose
- **IDE verdict assembly** — receives target page `ContentSignals` alongside prospect signals for direct comparison

**Why post-Sprint 3, not now:**
1. The dominant Bottleneck case (content adequate, bottleneck is links) does not require structured content signals.
2. The IDE's Haiku call 1 already extracts structured float signals (P1, P2, D4) from prospect content in Sprint 3. After Sprint 3 ships, real verdicts will reveal which content signals drove the hardest cases — that evidence should define the `ContentSignals` schema, not pre-implementation assumptions.
3. Locking a schema before observing production failure modes risks encoding the wrong signals. `subtopics_missing` is only useful if the LLM can define "expected subtopics" reliably for the full range of keywords in production. That reliability must be measured, not assumed.

**Implementation trigger:** After Sprint 3, audit 20–30 Bottleneck verdicts where `primary_constraint = CONTENT_DEPTH`. Identify what structured information would have changed or confirmed the verdict. Use that audit to finalize the `ContentSignals` schema before writing any code.

### 3.2 Data collection phase (parallel)

All data collection tasks run **in parallel** to minimize total analysis time. Target: data collection complete in under 30 seconds for a typical page.

```python
async def collect_data(page_url: str, workspace: Workspace) -> AnalysisContext:
    results = await asyncio.gather(
        crawl_page(page_url),
        fetch_gsc_data(page_url, workspace.gsc_credentials),
        identify_keywords(page_url),  # From GSC or content inference
        return_exceptions=True
    )
    page_content, gsc_data, keywords = results
    
    # Keyword-dependent tasks (sequential after keyword identification)
    serp_results = await fetch_serp(keywords)
    competitor_urls = extract_competitor_urls(serp_results, limit=3)
    
    competitor_data, backlink_data = await asyncio.gather(
        crawl_competitors(competitor_urls),
        fetch_backlinks([page_url] + competitor_urls),
        return_exceptions=True
    )
    
    return AnalysisContext(
        page=page_content,
        gsc=gsc_data,
        keywords=keywords,
        serp=serp_results,
        competitors=competitor_data,
        backlinks=backlink_data
    )
```

**Why sequential for SERP-then-competitors:** Competitor URLs are not known until SERP results return. This is an unavoidable sequential dependency. The SERP call itself (~500ms) plus competitor crawls (~5-15 seconds) are the critical path. Target total: <45 seconds for data collection.

### 3.3 Readiness analysis phase

**Input:** page content, GSC data, backlink data for the target page.

**Processing:**

1. **Rules-based pre-checks** (fast, cheap, run first):
   - Word count (below a threshold = flag, e.g. <500 words for informational content)
   - `<title>` / `<h1>` present and relevant
   - Internal links to this page (from crawl or GSC)
   - HTTP status (200 required)
   - GSC: is the page indexed?

2. **LLM analysis** (see §4-5 for model selection and prompts):
   - Content quality assessment vs. search intent
   - Content coverage (does the page answer the query fully?)
   - Internal authority signals
   - LLM produces a structured output (see §6)

3. **Verdict assembly:** Rules output + LLM output → Readiness verdict.

**When to skip LLM:** If rules-based checks produce a hard "Not Ready" (page is <200 words, 404, or not indexed), the LLM call is skipped. This saves ~$0.005-0.02 per analysis on the most obvious cases. The rule fires before the LLM is invoked.

### 3.4 Bottleneck analysis phase

**Input:** page content, GSC data, SERP results, competitor content and backlink profiles.

This is the most complex LLM task in the product. It requires multi-factor reasoning across heterogeneous signals.

**Bottleneck taxonomy (the decision space the LLM must navigate):**

| Category | Signals | Sub-factors |
|---|---|---|
| Link authority | RD gap vs top-3, DR gap, anchor profile | Primary / secondary constraint |
| Content depth | Word count, topic coverage, semantic richness | Content too thin, wrong format, missing entities |
| Search intent mismatch | SERP feature type, competitor page types, query modifiers | Wrong content type (listicle vs. guide), wrong funnel stage |
| Internal link authority | Internal links pointing to this page vs competitors | Page isolated in site structure |
| Technical (light) | Indexing, crawlability, title/H1 alignment | Quick wins only — deep technical SEO is out of scope for MVP |

**Processing:**

1. **Quantitative gap calculation** (deterministic, pre-LLM):
   - RD gap: `target_RDs - median(top3_RDs)` → positive gap = deficit
   - Content gap: word count ratio, estimated topic coverage score
   - These are inputs to the LLM prompt

2. **LLM reasoning:** Given the quantified gaps and the content comparison, the LLM:
   - Identifies the primary constraint (which gap matters most)
   - Estimates the severity (mild / significant / severe)
   - Identifies secondary constraints
   - Produces the competitive context sentence
   - Produces the recommended action

3. **Critical check — "links won't help":** The product's signature insight. The LLM must be explicitly prompted to reach this conclusion when evidence supports it. Do not assume the LLM will volunteer it. The prompt must enumerate the conditions under which this conclusion is correct. See §5.

### 3.5 Opportunity evaluation phase — Investment Decision Engine

**Trigger:** User submits a prospect URL (domain, category URL, or specific placement page URL) alongside a target page URL.

**This is a separate on-demand job**, not part of the automatic full-page analysis:
- Opportunity verdicts are linked to a specific target page, not a site
- Multiple opportunities can be evaluated for the same page over time
- Users can evaluate before or after running a full Bottleneck (product nudges toward Bottleneck first)

---

**Architecture: one engine, two input modes**

The IDE uses a single aggregation model, schema, validation layer, and hard exclusion gate set across both modes. Branching occurs only at the data collection step. The mode is detected automatically from the input URL — users never select a mode.

---

**Mode A — Specific Placement Evaluation**

Triggered when: the input URL resolves to a crawlable article or page with substantive content.

Detection signals (all must pass):
- Response body >500 characters of article content
- At least one of: article/BlogPosting schema markup, publication date, byline/author attribution
- NOT a listing or index page (no article-card grid, no pagination to sibling articles)

Data collection:
1. Crawl the specific placement page (1 page)
2. Crawl a sample of domain content for D1, D4, D5 signals (2–3 pages from other sections)
3. Pull DataForSEO: URL-level organic traffic estimate for the placement page (P3), domain metrics (D2, D3)

All P1–P5 signals derived from the specific placement page.

Confidence ceiling: **High**

---

**Mode B — Guest Post Opportunity Evaluation**

Triggered when: the input URL does not resolve to a specific article. Covers:
- Bare domain (`example.com` or `https://example.com/`)
- Category or section URL (`https://example.com/blog/`, `https://example.com/resources/seo/`)
- Any URL returning non-200 status (domain used as fallback)
- Any URL classified as a listing or index page

**Category URLs are first-class inputs.** When a category URL is provided, the system samples articles exclusively from that section — no inference needed.

**Sub-type: Category URL**
- User provides a path identifying a content section
- Sample 3–5 articles from that section only
- Confidence ceiling: **Medium**

**Sub-type: Domain only**
- No meaningful section path provided; system infers the most relevant section before sampling
- Section inference steps:
  1. Fetch `robots.txt` and `sitemap.xml` to enumerate primary content sections
  2. Crawl homepage; extract main navigation sections and topic labels
  3. Haiku classification: match sections to the target page topic
  4. If clear match found → sample 3–5 articles from matched section
  5. If no clear match → sample from the section with highest estimated organic traffic (DataForSEO URL pattern matching or sitemap priority values)
  6. Record inferred section in `inferred_section` field of the verdict for user transparency
- Confidence ceiling: **Low**

**Exception to ceiling:** If the user provides a target pitch topic alongside the URL, P1 and P5 approximations are more precise. The ceiling tier does not change, but the score achievable within that tier is higher.

**Signal approximation in Mode B:**

| Signal | Mode A | Mode B |
|---|---|---|
| P1 (topical relevance) | Specific page vs. target topic | Averaged across 3–5 sampled articles vs. target topic |
| P2 (content quality) | Specific page quality assessment | Averaged quality across sampled articles |
| P3 (organic traffic) | URL-level DataForSEO estimate | Sum of sampled article URL traffic (category-level proxy) |
| P4 (OBL quality) | Specific page outbound links | Averaged OBLs from sampled articles |
| P5 (placement feasibility) | Can this link fit in this existing article? | Could we write an article for this site in this topic/section that accommodates this link? |

All domain-level signals (D1–D9) are derived identically in both modes — they are unaffected by input URL type.

---

**Mode detection logic:**

```
Input URL
  │
  ├─ Fetch URL (HEAD → GET)
  │
  ├─ Non-200 response → MODE B, domain-only (use domain from URL)
  │
  ├─ Single article page?
  │     body > 500 chars AND (date OR byline OR schema) AND NOT listing
  │     → MODE A
  │
  ├─ Listing or index page?
  │     URL has non-root path → MODE B, category URL sub-type
  │     URL is bare domain or root path → MODE B, domain-only sub-type
  │
  └─ Ambiguous → MODE B (safer default), log in data_quality.mode_detection_note
```

---

**Shared Tier 0 — Hard Exclusion Gates (both modes, run first):**
- H1: Prohibited content (adult, gambling-as-core-business, illegal, scam)
- H2: Deindexed/penalized (indexed ratio <10% + near-zero traffic despite historical links)
- H3: Malware or phishing flag
- H4: Complete language impossibility (zero audience overlap)
- H5: Manual action indicators (>80% traffic loss with backlink profile intact)

Any trigger → `not_recommended` immediately, no scoring.

---

**Cluster aggregation (identical across both modes):**

```
Relevance = (P1 × 0.45) + (D1 × 0.25) + (D9 × 0.20) + (language_match × 0.10)
Authority  = (P3 × 0.35) + (P2 × 0.25) + (D2 × 0.25) + (D3_current × 0.15)
Quality    = (D4 × 0.35) + (P4 × 0.25) + (P5 × 0.20) + (D5 × 0.10) + (D6 × 0.10)
             [D4 < 0.30 caps Quality at 0.40; P5 == "implausible" caps at 0.35]

Base_Score      = (Relevance × 0.35) + (Authority × 0.30) + (Quality × 0.35)
Risk_multiplier = f(D7, D3_trend, D8, D1_consistency, P4_obl_flags)  → 0.25–1.00
Investment_Score = Base_Score × Risk_multiplier × 100

Editorial integrity cap: if D4 < 0.30 → Investment_Score = min(Investment_Score, 45)
```

---

**Shared processing pipeline (both modes):**

1. Mode detection and input normalization
2. Hard exclusion gate checks (H1–H5)
3. Mode-specific data collection:
   - Mode A: crawl specific placement page + 2–3 domain sample pages
   - Mode B/category: crawl 3–5 articles from the specified section + domain sample
   - Mode B/domain: run section inference → crawl 3–5 articles from inferred section + domain sample
4. Pull DataForSEO: URL-level or category-level traffic (P3), domain metrics (D2, D3), spam signals (D7)
5. LLM Call 1 — Haiku: content classification + signal extraction. Mode-aware: receives `evaluation_mode` as a parameter; single-page analysis for Mode A, multi-article-sample analysis for Mode B. Same tool schema output regardless of mode.
6. Deterministic cluster score computation (identical formula across both modes)
7. Risk multiplier application; editorial integrity cap enforcement
8. Investment Score calculation
9. LLM Call 2 — Haiku: investment verdict assembly. Receives `evaluation_mode` and `confidence_ceiling`; verdict language reflects mode context. Mode B verdicts include `mode_qualifier`.
10. Pydantic schema validation + business logic validation (§7.2)
11. Confidence ceiling enforcement (mode-specific ceiling overrides LLM self-report)

---

**Output tiers (identical across both modes):**
- `recommended`: Score ≥ 68, Relevance ≥ 0.55, Risk multiplier ≥ 0.80, D4 ≥ 0.55, confidence within ceiling ≥ Medium
- `with_conditions`: Score 48–67 or score ≥ 68 with one named significant condition
- `not_recommended`: Any hard exclusion, OR Score < 48, OR Risk multiplier < 0.55, OR D4 < 0.30, OR Relevance < 0.30
- `insufficient_data`: Required signals unavailable, OR confidence ceiling enforcement produces Insufficient Data tier

Full signal definitions, aggregation model, conflict resolution rules, mode detection rationale, and alternatives considered: see `docs/decisions.md` — "2026-06-25 Investment Decision Engine Design" and "2026-06-25 Investment Decision Engine: Dual-Mode Architecture".

### 3.6 Execution plan phase

**Trigger:** User selects an opportunity rated Recommended or With Conditions and requests an execution plan.

**Input:** target page backlink profile (anchor text distribution), opportunity site content, target page content, bottleneck verdict.

**Processing:**
1. **Anchor text analysis** (deterministic): analyze current anchor profile, identify what anchor type is over/underrepresented
2. **LLM synthesis:** generate specific, actionable recommendations for anchor strategy, article format, placement, and target page recommendation
3. **Cross-check with readiness:** if the target page is Not Ready, the execution plan is generated but flagged — the system should surface the "build this link, but fix the page first" warning

---

## 4. LLM Architecture

### 4.1 Model selection principles

The product requires LLM calls at three levels of complexity:

| Complexity | Task type | Recommended model |
|---|---|---|
| High | Bottleneck reasoning (multi-signal, multi-competitor, reach non-obvious conclusions) | Claude Sonnet 4 |
| Medium | Readiness assessment, Opportunity evaluation, Execution plan | Claude Haiku 4.5 |
| Low | Classification, extraction, formatting | Claude Haiku 4.5 |

**Why Claude and not GPT-4o or Gemini?**

Reasoning: Anthropic's models follow structured output instructions more reliably than GPT-4o on complex multi-factor tasks. For Bottleneck analysis specifically, the model must weigh competing signals and reach a single defensible conclusion without hallucinating signal values — an area where Claude Sonnet's reasoning is notably more calibrated. Additionally, Claude's tool use / structured output (via `tool_use` or explicit JSON schemas) produces fewer parse errors than GPT-4o's JSON mode on complex nested schemas.

**Tradeoff acknowledged:** Anthropic does not offer a hosted fine-tuning pipeline for Sonnet/Haiku today. If we need domain-adapted models (e.g., trained on SEO-specific label sets), that is easier with OpenAI. This is a risk for a future capability — document it, do not design around it at MVP.

**Why not GPT-4o for Bottleneck?** Tested assumption: GPT-4o produces slightly more verbose, confident-sounding outputs that are harder to validate. For a product where "I don't have enough signal" is a first-class outcome, calibrated uncertainty is critical. Claude Sonnet produces more appropriate hedging.

**Why Haiku for most tasks?** Cost. Haiku is ~20x cheaper than Sonnet per token and adequate for single-dimension tasks like opportunity evaluation (where each dimension is essentially a binary classification with a reason). The full task breakdown:

| Task | Model | Estimated tokens (in+out) | Cost per call |
|---|---|---|---|
| Content summarization — target page | Haiku 4.5 | ~2,000 | ~$0.001 |
| Content summarization — competitor ×3 | Haiku 4.5 | ~1,500 each | ~$0.003 total |
| Bottleneck diagnosis | Sonnet 4 | ~6,000 | ~$0.025 |
| Readiness assessment | Haiku 4.5 | ~3,000 | ~$0.003 |
| Opportunity — content classification + signal extraction | Haiku 4.5 | ~4,500 | ~$0.005 |
| Opportunity — investment verdict assembly | Haiku 4.5 | ~3,500 | ~$0.004 |
| Execution plan | Haiku 4.5 | ~2,500 | ~$0.002 |

### 4.2 Structured output method

**Recommendation: Anthropic tool use (function calling) over JSON mode prompt instructions.**

Reasons:
1. The model is less likely to produce partial JSON when it is told to fill a tool schema versus when it is told "respond with valid JSON"
2. Tool use allows schema validation at the SDK level before the response reaches application code
3. The response is always in `tool_use` blocks, never mixed with prose (which requires splitting)

All LLM calls define a single tool with the full verdict schema. The model "calls" that tool. We extract the `input` object and validate it with Pydantic.

### 4.3 Retry and fallback strategy

**Primary:** Claude Sonnet 4 for Bottleneck; Claude Haiku 4.5 for all others.

**On failure or timeout (>60s):**
- Retry once with a 5-second backoff
- On second failure: log the failure, mark job as `FAILED`, return user-visible error ("Analysis couldn't complete — your usage wasn't counted, try again")
- Do not fall back to a weaker model silently — this would produce confidence-inflated verdicts from a model that may not have followed the schema correctly

**On partial data (API call returned but data was missing):**
- Proceed with available signals
- The confidence model (§8) will naturally lower the confidence score
- Document missing signals in the verdict's `data_quality` field

### 4.4 Token budget management

Token overflow is the primary prompt engineering risk for Bottleneck analysis, which receives the most data.

**Max context budget: 8,000 tokens** (input + output) for Bottleneck.

Data compression strategy:
- Competitor page content: extract top 10 headings + first paragraph only (not full HTML). Do not send raw HTML to the LLM.
- GSC data: send the top 5 keywords by impressions, not all 500 rows.
- Backlink data: send RD count, DR/DA score, top 5 anchor texts by frequency. Not the full link list.
- Page content: send title, H1, subheadings, first 500 words. Not full body.

A preprocessing step must **deterministically reduce** each data source to its compressed representation before building the prompt. This must be testable independently of the LLM.

---

## 5. Prompt Architecture

### 5.1 Prompt design principles

1. **Prompts are code.** They live in version-controlled files, are tested, and have a change log.
2. **One prompt per module.** Do not combine multiple analyses into one LLM call. Separation improves debuggability and allows independent confidence scoring.
3. **The model is told the domain explicitly.** Don't assume it knows what link building is. Provide a brief domain framing in the system prompt.
4. **Enumerate the decision space.** For every verdict field with constrained outputs (e.g., `primary_constraint`: one of `link_authority | content_depth | intent_mismatch | internal_links | technical`), list the valid options and their meaning explicitly.
5. **Instruct the model to be honest about uncertainty.** An explicit instruction like "If the available data does not support a confident verdict, you must say so in the `confidence_rationale` field and set `confidence` to `low`" is required. Without it, the model will produce confident-sounding verdicts regardless.
6. **The non-obvious insight is explicitly prompted.** For Bottleneck, the prompt must explicitly say: "If the evidence indicates content or intent mismatch is the dominant factor rather than links, you MUST conclude that links are not the primary solution, even if the user's intent was to evaluate link strategy."

### 5.2 System prompt (shared across all modules)

```
You are the analysis engine for Serpnex, a link intelligence platform used by SEO agencies.
Your role is to analyze web pages and produce structured, defensible verdicts that help
strategists make decisions about link building.

You analyze signals objectively. You do not overstate confidence. When data is insufficient
to support a verdict, you say so clearly. You produce verdicts that are actionable and specific,
not vague or generic.

All outputs must match the tool schema exactly. Do not include prose outside the tool call.
```

### 5.3 Readiness module prompt

**User message structure:**

```
Analyze whether the following page is ready to receive link-building investment.

## Target Page
URL: {url}
Title: {title}
H1: {h1}
Word count: {word_count}
Primary keywords (from GSC or inferred): {keywords}
GSC average position: {avg_position} (null if unavailable)
GSC impressions (90d): {impressions} (null if unavailable)
Is indexed: {is_indexed}
Internal links pointing to this page: {internal_link_count}

## Content summary
{compressed_content}

## Instructions
Assess readiness across these dimensions:
1. Content sufficiency: Does the page have sufficient depth and quality to rank for the primary keywords?
2. Search intent alignment: Does the page format and content match the dominant search intent for these keywords?
3. Indexing and accessibility: Is the page reachable, indexed, and technically sound enough to benefit from links?
4. Internal authority: Is the page adequately supported by internal links within its site?

A page is "Ready" only if all four dimensions pass. If any dimension fails significantly, the page
is "Not Ready." If a dimension fails mildly, it may still be "Ready with caveats."

Use the tool to return your verdict.
```

### 5.4 Bottleneck module prompt

**This is the most important prompt in the product. Every word is deliberate.**

**User message structure:**

```
Diagnose the primary ranking bottleneck for the following page versus the current top search results.

## Target Page
URL: {url}
Primary keyword: {primary_keyword}
GSC average position: {avg_position}
Estimated referring domains: {target_RDs}
Content summary: {compressed_content}

## Top 3 Competitors (currently ranking above)
{for each competitor:}
  URL: {url}
  Estimated referring domains: {competitor_RDs}
  Content summary: {compressed_content}

## Gap Analysis (pre-calculated)
Authority gap: {target_RDs} vs. {median_competitor_RDs} referring domains
Content length: Target {word_count} words vs. competitor median {competitor_median_words} words

## Instructions
Identify the PRIMARY ranking bottleneck from these categories:
- link_authority: The page is materially outgunned on referring domains/authority vs. competitors
- content_depth: The page's content is thinner, less comprehensive, or lower quality than competitors
- intent_mismatch: The page's content format or angle doesn't match what searchers and the algorithm expect
- internal_links: The page is underserved by internal link equity compared to what it needs
- technical: There are fundamental technical issues preventing the page from ranking (rare — use only with clear evidence)

CRITICAL: If content, intent, or internal links are the dominant constraint, you MUST conclude that
building external links is NOT the highest-priority action, even if the page has an authority gap.
A page with a content or intent problem will not benefit significantly from new links until those
problems are fixed. Name the real problem.

You MUST NOT assign link_authority as the primary bottleneck unless the authority gap is material
(target is meaningfully behind competitors on referring domains AND content quality is comparable).

Set confidence to "low" if:
- GSC data is unavailable
- Competitor data could not be fully retrieved
- The page has no ranking history

Use the tool to return your verdict.
```

### 5.5 Opportunity evaluation prompt — Investment Decision Engine

The Opportunity evaluation prompt is a first-class deliverable, analogous to `docs/prompts/bottleneck-v1.md`. It is stored in `docs/prompts/opportunity-v1.md` and must be created before Sprint 3 begins.

The IDE requires two Haiku LLM calls, not one:

**Call 1 — Content classification and signal extraction:**
Inputs: crawled placement page content, crawled domain article samples, target page topic.
Task: classify P1 (topical relevance), P2 (content quality), P4 (OBL quality), P5 (placement feasibility), D1 (site topical coherence), D4 editorial integrity sub-signals (authorship quality, content coherence, sponsored content ratio, OBL editorial quality), D9 (country/language targeting).
Output: structured signal scores (all 0–1 floats or categorical enums).

**Call 2 — Investment verdict assembly:**
Inputs: all cluster scores (computed deterministically from Call 1 outputs + DataForSEO data), Investment Score, hard exclusion results.
Task: produce the final `InvestmentVerdict` — headline, primary reason, supporting signals, named conditions (if any), confidence rationale.
This call does **not** perform signal assessment — it converts pre-computed scores into a plain-language verdict explanation.

**Editorial Integrity sub-signals (computed during Call 1):**
- Authorship quality (0.30 weight): identifiable authors with verifiable identities, topic specialization
- Content coherence and voice (0.25 weight): consistent niche, distinct editorial perspective vs. incoherent topic mix
- Sponsored content ratio (0.25 weight): proportion of recent articles with sponsored/paid labels (<20% = normal; >60% = primarily commercial)
- OBL editorial quality (0.20 weight): links to genuine editorial destinations vs. commercial landing pages with exact-match commercial anchors

**Anti-bias rule (mirrors Bottleneck's Rule 2):** The prompt must instruct the model that "high domain authority" is not a sufficient reason to recommend an investment. Authority is one cluster (30% weight) and cannot compensate for failed relevance or poor editorial integrity. The primary reason in the verdict must name the actual decisive signal, not default to authority.

**Prompt design:** Follow the same principles as `bottleneck-v1.md`: explicit rules, enumerated decision space, descriptive language only in content assessment, tool use for structured output, no prose outside the tool call. See `docs/prompts/bottleneck-v1.md §2` for the prompt design template to follow.

### 5.6 Execution plan prompt

```
Generate a specific execution plan for building a link from the prospect site to the target page.

## Target Page
URL: {target_url}
Current anchor text distribution: {anchor_distribution}
Primary topic: {primary_topic}

## Opportunity
Prospect domain: {prospect_domain}
Typical content format: {content_format}
Opportunity verdict: {opportunity_verdict}

## Readiness / Bottleneck Context
Page readiness status: {readiness_status}
Primary bottleneck: {bottleneck}

## Instructions
Provide specific, actionable recommendations:
1. anchor_strategy: What anchor text type (branded/partial-match/topical/generic) should be used, and why, given the current anchor distribution?
2. article_format: What article format (comparison/tutorial/case study/guide/data piece) would best justify this link naturally?
3. placement: Where in the article should the link appear (introduction/body/supporting section), and what context justifies it?
4. target_page_recommendation: Confirm the target page is the right landing page, or recommend a different page if it would benefit more.
5. risk_warnings: Any caveats — especially if the target page is not yet ready, or if the anchor profile is already skewed.

Be specific. Avoid generic advice. The output will be used as a brief for a writer.

Use the tool to return your verdict.
```

### 5.7 Prompt versioning

Each prompt is stored as `prompts/readiness/v1.md`, `prompts/bottleneck/v1.md`, etc. The prompt version used for each analysis is stored in the database (`page_analyses.prompt_version`). This enables:
- Auditing what changed between verdicts on re-runs
- A/B testing prompt versions
- Rolling back if a new prompt version regresses quality

---

## 6. Structured Output Schema

All LLM outputs are typed Pydantic models. These are the source of truth for both the LLM tool schema and the database JSONB columns.

### 6.1 Readiness verdict schema

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class ReadinessOutcome(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    READY_WITH_CAVEATS = "ready_with_caveats"
    INSUFFICIENT_DATA = "insufficient_data"

class ReadinessDimension(BaseModel):
    passed: bool
    severity: str = Field(..., pattern="^(low|medium|high)$")  # severity of failure if not passed
    reason: str = Field(..., max_length=200)
    action: Optional[str] = Field(None, max_length=200)  # fix if not passed

class ReadinessVerdict(BaseModel):
    outcome: ReadinessOutcome
    confidence: str = Field(..., pattern="^(low|medium|high)$")
    confidence_rationale: str = Field(..., max_length=300)
    headline: str = Field(..., max_length=120)  # the one-sentence verdict summary
    dimensions: dict[str, ReadinessDimension]  # keys: content_sufficiency, intent_alignment, indexing, internal_authority
    actions: list[str] = Field(default_factory=list, max_length=5)  # prioritized fix list if not ready
    data_quality: dict[str, bool]  # e.g., {"gsc_connected": True, "page_crawled": True}
```

### 6.2 Bottleneck verdict schema

```python
class BottleneckCategory(str, Enum):
    LINK_AUTHORITY = "link_authority"
    CONTENT_DEPTH = "content_depth"
    INTENT_MISMATCH = "intent_mismatch"
    INTERNAL_LINKS = "internal_links"
    TECHNICAL = "technical"

class ConstraintSeverity(str, Enum):
    MILD = "mild"
    SIGNIFICANT = "significant"
    SEVERE = "severe"

class ConstraintBreakdown(BaseModel):
    category: BottleneckCategory
    severity: ConstraintSeverity
    weight: float = Field(..., ge=0, le=1)  # proportion of the bottleneck (all weights sum to 1.0)
    reason: str = Field(..., max_length=250)

class BottleneckVerdict(BaseModel):
    primary_constraint: BottleneckCategory
    primary_severity: ConstraintSeverity
    links_are_the_answer: bool  # explicit flag — the key product decision
    headline: str = Field(..., max_length=150)  # the stated-as-headline primary constraint
    competitive_context: str = Field(..., max_length=200)  # one-sentence competitor comparison
    constraint_breakdown: list[ConstraintBreakdown]  # ordered by weight descending
    recommended_action: str = Field(..., max_length=250)
    recommended_action_priority: str = Field(..., pattern="^(immediate|high|medium|low)$")
    confidence: str = Field(..., pattern="^(low|medium|high)$")
    confidence_rationale: str = Field(..., max_length=300)
    data_quality: dict[str, bool]
    # Pre-calculated gap data (stored for UI rendering, not produced by LLM)
    authority_gap_rds: Optional[int] = None  # target_RDs - median_competitor_RDs
    content_gap_words: Optional[int] = None
```

### 6.3 Investment verdict schema (Opportunity module)

The Opportunity verdict schema has been redesigned to reflect the Investment Decision Engine architecture. The previous 4-dimension flat model is replaced by a cluster-scored model with explicit hard exclusion tracking.

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class InvestmentOutcome(str, Enum):
    RECOMMENDED = "recommended"
    WITH_CONDITIONS = "with_conditions"
    NOT_RECOMMENDED = "not_recommended"
    INSUFFICIENT_DATA = "insufficient_data"

class HardExclusionGate(str, Enum):
    PROHIBITED_CONTENT = "H1_prohibited_content"
    DEINDEXED_OR_PENALIZED = "H2_deindexed_or_penalized"
    MALWARE = "H3_malware"
    LANGUAGE_IMPOSSIBLE = "H4_language_impossible"
    MANUAL_ACTION_INDICATORS = "H5_manual_action_indicators"

class PlacementFeasibility(str, Enum):
    NATURAL = "natural"
    WORKABLE = "workable"
    FORCED = "forced"
    IMPLAUSIBLE = "implausible"

class PlacementPageSignals(BaseModel):
    url: str
    topical_relevance_score: Optional[float] = Field(None, ge=0, le=1)
    content_quality_score: Optional[float] = Field(None, ge=0, le=1)
    organic_traffic_tier: Optional[str] = Field(None, pattern="^(high|medium|low|none|unknown)$")
    obl_quality_score: Optional[float] = Field(None, ge=0, le=1)
    placement_feasibility: Optional[PlacementFeasibility] = None

class ClusterScores(BaseModel):
    relevance: float = Field(..., ge=0, le=1)
    authority: float = Field(..., ge=0, le=1)
    quality: float = Field(..., ge=0, le=1)
    risk: float = Field(..., ge=0, le=1)
    risk_multiplier: float = Field(..., ge=0, le=1)

class EditorialIntegrityScores(BaseModel):
    overall: float = Field(..., ge=0, le=1)
    authorship_quality: float = Field(..., ge=0, le=1)
    content_coherence: float = Field(..., ge=0, le=1)
    sponsored_ratio: float = Field(..., ge=0, le=1)
    obl_editorial_quality: float = Field(..., ge=0, le=1)

class InvestmentVerdict(BaseModel):
    # Gate result
    hard_exclusion_triggered: bool = False
    hard_exclusion_gate: Optional[HardExclusionGate] = None
    hard_exclusion_reason: Optional[str] = Field(None, max_length=200)

    # Scores (None if hard exclusion triggered)
    cluster_scores: Optional[ClusterScores] = None
    investment_score: Optional[float] = Field(None, ge=0, le=100)
    editorial_integrity: Optional[EditorialIntegrityScores] = None

    # Verdict
    outcome: InvestmentOutcome
    confidence: str = Field(..., pattern="^(low|medium|high)$")
    confidence_rationale: str = Field(..., max_length=300)

    # Verdict explanation — the "strategist memo" components
    headline: str = Field(..., max_length=150)           # primary verdict statement
    primary_reason: str = Field(..., max_length=200)     # single most decisive signal
    supporting_signals: list[str] = Field(default_factory=list, max_items=3)

    # Conditions (with_conditions only) — specific and named, not generic
    conditions: list[str] = Field(default_factory=list)

    # Placement page
    placement_page: Optional[PlacementPageSignals] = None
    placement_url_provided: bool = False

    # Signal availability map
    data_quality: dict[str, str]  # signal_code → "available" | "partial" | "missing"

    # LLM self-reported confidence (stored for audit, not surfaced in UI)
    llm_confidence: Optional[str] = None

    # ── Dual-mode fields ─────────────────────────────────────────────
    evaluation_mode: str = Field(..., pattern="^(specific_placement|guest_post_opportunity)$")
    mode_b_subtype: Optional[str] = Field(None, pattern="^(category_url|domain_inferred)$")

    # Mode B: articles sampled to approximate placement-page signals
    sampled_article_urls: list[str] = Field(default_factory=list)

    # Mode B, domain-only: which section the system inferred before sampling
    inferred_section: Optional[str] = None

    # Structural confidence ceiling enforced by mode (overrides LLM self-report if higher)
    confidence_ceiling: str = Field(..., pattern="^(high|medium|low)$")

    # Mode B only: surfaced in UI alongside the verdict
    mode_qualifier: Optional[str] = Field(None, max_length=300)

    # Populated if mode classification was ambiguous
    mode_detection_note: Optional[str] = Field(None, max_length=200)
```

**Business logic validation rules (applied post-schema, per §7.2):**

*Existing rules:*
- If `hard_exclusion_triggered = True` → `outcome` must be `not_recommended`; `cluster_scores` and `investment_score` must be `None`
- If `outcome = "recommended"` → `investment_score` must be ≥ 68; `conditions` must be empty
- If `outcome = "with_conditions"` → `conditions` list must be non-empty with at least one named condition
- If `outcome = "not_recommended"` → `primary_reason` must name the specific disqualifying signal
- If `editorial_integrity.overall < 0.30` → `investment_score` must be ≤ 45 (editorial integrity cap enforced deterministically)

*Mode-specific rules (added for dual-mode architecture):*
- If `evaluation_mode = "specific_placement"` → `mode_b_subtype` must be `None`; `sampled_article_urls` must be empty; `inferred_section` must be `None`; `confidence_ceiling` must be `"high"`
- If `evaluation_mode = "guest_post_opportunity"` → `mode_b_subtype` must be non-`None`; `mode_qualifier` must be non-`None` and non-empty
- If `mode_b_subtype = "domain_inferred"` → `inferred_section` must be non-`None`; `confidence_ceiling` must be `"low"`
- If `mode_b_subtype = "category_url"` → `confidence_ceiling` must be `"medium"`; `sampled_article_urls` must be non-empty (≥ 3 entries)
- `confidence` field value must not exceed `confidence_ceiling` (Low ≤ Medium ≤ High); if the LLM self-reports a higher confidence than the ceiling allows, the ceiling value is applied and the override is recorded in `validation_overrides` (see §9.2)

### 6.4 Execution plan schema

```python
class ExecutionPlan(BaseModel):
    anchor_strategy: str = Field(..., max_length=300)
    anchor_type_recommended: str = Field(..., pattern="^(branded|partial_match|topical|generic|contextual)$")
    article_format: str = Field(..., pattern="^(comparison|tutorial|case_study|guide|data_piece|opinion|interview)$")
    article_format_reason: str = Field(..., max_length=200)
    placement: str = Field(..., pattern="^(introduction|body|supporting_section|conclusion)$")
    placement_reason: str = Field(..., max_length=200)
    target_page_url: str  # may differ from original target if LLM recommends a different page
    target_page_confirmed: bool  # False if LLM recommended a different page
    target_page_change_reason: Optional[str] = Field(None, max_length=200)
    risk_warnings: list[str] = Field(default_factory=list)
    readiness_gate_warning: Optional[str] = None  # populated if target page is not_ready
```

---

## 7. Validation Layer

LLM outputs fail in predictable ways. The validation layer catches these failures before they reach the database or UI.

### 7.1 Schema validation (Pydantic)

All LLM outputs are parsed through Pydantic before being written to the database. Pydantic will raise a `ValidationError` on:
- Missing required fields
- Fields failing regex constraints (e.g., `confidence` not matching `low|medium|high`)
- Type mismatches
- Values outside numerical bounds (`weight` outside 0-1)
- Lists that violate `max_length`

On `ValidationError`: retry the LLM call once with the error appended to the prompt ("Your previous response failed validation with the following error: {error}. Correct it and try again."). On second failure: mark analysis as failed.

### 7.2 Business logic validation

After schema validation passes, apply business logic checks:

**Bottleneck:**
- `constraint_breakdown` weights must sum to 1.0 (±0.01 tolerance for floating point)
- If `links_are_the_answer = False`, `primary_constraint` must NOT be `link_authority`
- If `primary_severity = "mild"`, confidence should not be `high` (mild primary constraint is inherently uncertain)

**Readiness:**
- If `outcome = "ready"`, at minimum `indexing` dimension must be `passed = True`
- If `data_quality.gsc_connected = False`, confidence cannot be `high`

**Opportunity (Investment Decision Engine):**
- Mode-specific validation rules are defined in §6.3 (InvestmentVerdict schema) and applied here
- The confidence ceiling enforcement is the most critical post-LLM rule: `confidence` is overridden downward if it exceeds `confidence_ceiling`; the override is recorded in `validation_overrides`
- If `hard_exclusion_triggered = True`: `cluster_scores`, `investment_score`, and `editorial_integrity` must all be `None`
- If `outcome = "with_conditions"`: `conditions` must be non-empty; generic conditions ("verify site quality") are rejected — each condition must name a specific signal and a specific action

On business logic failure: do not retry the LLM. Log the inconsistency, apply the override rule (e.g., force `confidence` down), and write a `validation_override` flag to the database for auditing.

### 7.3 Data freshness validation

Before running an analysis, check if cached data meets freshness thresholds:

| Data type | Max age for use | Action if stale |
|---|---|---|
| GSC data | 24 hours | Re-fetch; if unavailable use stale + flag |
| SERP results | 48 hours | Re-fetch; if unavailable use stale + flag |
| Target page backlinks | 72 hours | Re-fetch; if unavailable use stale + flag |
| Prospect site backlinks | 24 hours | Re-fetch; fail opportunity eval if unavailable |
| Page crawl | 48 hours (or re-run triggers) | Re-crawl |

### 7.4 Confidence floor rules (deterministic overrides)

These rules apply regardless of what the LLM produced:

1. If `gsc_connected = False` → confidence cannot exceed `medium`
2. If `backlink_data_available = False` → confidence cannot exceed `low` for Bottleneck
3. If `competitor_count < 2` in Bottleneck → confidence cannot exceed `medium`
4. If the target page was created < 30 days ago → Readiness confidence cannot exceed `low`
5. If `page_crawl_success = False` → confidence is `low` regardless of other signals

These rules are applied in the Validation Layer after the LLM produces its output. They override the LLM's self-reported confidence field.

---

## 8. Confidence Scoring Model

### 8.1 Philosophy

Confidence in Serpnex is not a machine learning probability. It is a **data sufficiency score** — an honest statement about how much evidence supported the verdict. This is the right model for a B2B product where a professional user needs to know whether to trust the verdict before acting on it.

Three levels:
- **High:** All primary signals were available, fresh, and consistent. The conclusion is well-supported.
- **Medium:** One or two key signals were missing, stale, or inconsistent. The verdict direction is likely correct but may shift with better data.
- **Low:** Multiple key signals were unavailable, or the available signals were ambiguous or contradictory. Treat this as a preliminary indication, not a decision.

### 8.2 Scoring inputs

Each module has a set of inputs scored as Available / Partial / Missing. The score is computed as:

```python
def calculate_confidence(signals: dict[str, SignalStatus], module: str) -> ConfidenceLevel:
    weights = CONFIDENCE_WEIGHTS[module]  # defined per module
    score = 0.0
    for signal, status in signals.items():
        if signal not in weights:
            continue
        weight = weights[signal]
        if status == SignalStatus.AVAILABLE:
            score += weight * 1.0
        elif status == SignalStatus.PARTIAL:
            score += weight * 0.5
        elif status == SignalStatus.MISSING:
            score += weight * 0.0
    
    if score >= 0.80:
        return ConfidenceLevel.HIGH
    elif score >= 0.55:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW
```

### 8.3 Signal weights by module

**Readiness module weights:**

| Signal | Weight |
|---|---|
| Page crawl success | 0.25 |
| GSC data (any) | 0.30 |
| Page indexed | 0.20 |
| Internal link data | 0.25 |

**Bottleneck module weights:**

| Signal | Weight |
|---|---|
| GSC keyword data | 0.25 |
| Competitor crawls (≥2) | 0.25 |
| Target page backlink data | 0.20 |
| Competitor backlink data (≥2) | 0.20 |
| SERP results | 0.10 |

**Opportunity evaluation weights (Investment Decision Engine):**

Required signals — if unavailable, output is Insufficient Data regardless of mode:

| Signal | Code | Confidence weight | Treatment if missing |
|---|---|---|---|
| Placement page crawl (Mode A) or article sample crawl (Mode B) | P1–P5 | 0.40 | → Insufficient Data |
| Spam footprint check | D7 | 0.25 | → confidence -1 tier |
| Domain traffic + trend | D3 | 0.15 | → confidence -1 tier |
| Domain authority data | D2 | 0.10 | → confidence -1 tier |
| Domain history | D8 | 0.05 | No impact |
| Geo / country signals | D9 | 0.05 | No impact (approximate inference acceptable) |

Confidence tier formula: Start at the mode's ceiling (not always High). Each important signal missing: -1 tier. Two+ signals in same cluster missing: additional -1 tier. Conflicting signals: -1 tier. Investment Score 48–62 (borderline zone): -1 tier. Below Low = Insufficient Data.

**Confidence ceiling by mode (structural, enforced post-LLM — see §7.2):**

| Mode | Sub-type | Ceiling | Rationale |
|---|---|---|---|
| Mode A | Specific placement | High | All signals available from the actual page |
| Mode B | Category URL | Medium | Specific article unknown; signals sampled, not measured |
| Mode B | Domain only | Low | Section inferred; additional approximation layer |

If the LLM self-reports a confidence higher than the ceiling, the ceiling is applied deterministically. The override is recorded in `validation_overrides`. This is a hard structural constraint — not a soft nudge — reflecting genuine epistemic limits of each evaluation type.

### 8.4 LLM vs. deterministic confidence

The LLM is also asked to self-report a confidence level in its output. The **deterministic score takes precedence** — if the LLM says `high` but the signal weights produce `medium`, the final confidence shown in the UI is `medium`.

The LLM's self-reported confidence is retained in the database as `llm_confidence` for auditing. If there is persistent disagreement between LLM confidence and deterministic confidence on the same class of verdicts, it is a signal to adjust either the signal weights or the prompt.

### 8.5 Future: outcome-calibrated confidence

Once the Campaigns/Tracking module is live and outcome data exists (was the predicted bottleneck correct? Did the link produce the forecast lift?), confidence can be recalibrated against real outcomes. This is the product's long-term moat: a self-improving confidence model. Do not build this at MVP — design the data model to support it (outcome fields in the DB schema, prediction tracking fields on verdicts).

---

## 9. Database Schema

### 9.1 Core entity tables

```sql
-- Workspace (top-level billing and access unit)
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',           -- free | solo | agency | scale
    analyses_used_this_period INTEGER DEFAULT 0,
    analyses_limit INTEGER DEFAULT 10,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Workspace memberships
CREATE TABLE workspace_members (
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'strategist', 'viewer')),
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);

-- GSC integrations (one per workspace, potentially multiple properties)
CREATE TABLE gsc_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    property_url TEXT NOT NULL,           -- e.g. "https://example.com/"
    access_token_encrypted TEXT NOT NULL, -- encrypted at rest
    refresh_token_encrypted TEXT NOT NULL,
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, property_url)
);

-- Sites
CREATE TABLE sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    display_name TEXT,
    gsc_integration_id UUID REFERENCES gsc_integrations(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, domain)
);

-- Pages (the hero object)
CREATE TABLE pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    path TEXT,                -- extracted path for display
    title TEXT,               -- from last crawl
    last_analyzed_at TIMESTAMPTZ,
    analysis_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (site_id, url)
);
```

### 9.2 Analysis tables

```sql
-- Full page analysis runs (Readiness + Bottleneck together)
CREATE TABLE page_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id UUID REFERENCES pages(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'collecting_data', 'summarizing_content', 'running', 'complete', 'failed')),
    
    -- Prompt versioning (track both summarization and bottleneck prompt versions separately)
    summarization_prompt_version TEXT, -- e.g. "summarize-page/v1"
    prompt_version TEXT,               -- e.g. "bottleneck/v2"
    
    -- Raw collected data (stored for debugging and re-runs without re-fetching)
    raw_data JSONB,                    -- {gsc: {...}, serp: {...}, backlinks: {...}, crawl: {...}}
    
    -- Generated content summaries (stored to enable re-running Bottleneck without re-crawling)
    content_summaries JSONB,           -- {target: "...", competitors: ["...", "...", "..."]}
    
    -- Verdicts (structured, validated before storage)
    readiness_verdict JSONB,           -- ReadinessVerdict schema
    bottleneck_verdict JSONB,          -- BottleneckVerdict schema
    
    -- Confidence scores (deterministic, post-validation)
    readiness_confidence TEXT CHECK (readiness_confidence IN ('low', 'medium', 'high')),
    bottleneck_confidence TEXT CHECK (bottleneck_confidence IN ('low', 'medium', 'high')),
    
    -- Data quality flags
    data_quality JSONB,                -- {gsc_connected: bool, competitor_count: int, ...}
    
    -- Outcome tracking (future: populated when Campaigns module captures results)
    outcome_tracked BOOLEAN DEFAULT FALSE,
    bottleneck_confirmed BOOLEAN,      -- null until outcome data available
    
    -- Validation audit
    validation_overrides JSONB,        -- records any confidence floor overrides applied
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_page_analyses_page_id ON page_analyses(page_id);
CREATE INDEX idx_page_analyses_workspace_id ON page_analyses(workspace_id);
CREATE INDEX idx_page_analyses_status ON page_analyses(status);

-- Opportunity evaluations
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id UUID REFERENCES pages(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id),
    
    -- The prospect being evaluated
    prospect_url TEXT NOT NULL,
    prospect_domain TEXT NOT NULL,
    
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'complete', 'failed')),
    
    prompt_version TEXT,
    
    -- Raw data
    raw_prospect_data JSONB,           -- crawled content + authority signals
    
    -- Verdict
    opportunity_verdict JSONB,         -- OpportunityVerdict schema
    overall_outcome TEXT CHECK (overall_outcome IN ('recommended', 'with_conditions', 'avoid')),
    confidence TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    
    validation_overrides JSONB,
    
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_opportunities_page_id ON opportunities(page_id);
CREATE INDEX idx_opportunities_workspace_id ON opportunities(workspace_id);
CREATE INDEX idx_opportunities_outcome ON opportunities(overall_outcome);

-- Execution plans
CREATE TABLE execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE CASCADE,
    page_id UUID REFERENCES pages(id),
    workspace_id UUID REFERENCES workspaces(id),
    
    prompt_version TEXT,
    
    plan JSONB NOT NULL,               -- ExecutionPlan schema
    
    -- Tracking (future Campaigns module)
    outreach_status TEXT DEFAULT 'not_started'
        CHECK (outreach_status IN ('not_started', 'in_progress', 'placed', 'rejected')),
    link_placed_at TIMESTAMPTZ,
    link_url TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 9.3 Caching tables

```sql
-- Cached external API responses (avoid repeat billing)
CREATE TABLE api_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key TEXT UNIQUE NOT NULL,    -- hash of (provider, endpoint, params)
    provider TEXT NOT NULL,            -- "dataforseo_serp" | "ahrefs" | "firecrawl" | "gsc"
    response_data JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_cache_key ON api_cache(cache_key);
CREATE INDEX idx_api_cache_expires ON api_cache(expires_at);

-- TTL cleanup job: DELETE FROM api_cache WHERE expires_at < NOW();
-- Run every 6 hours via Celery beat.
```

### 9.4 Usage/billing tables

```sql
-- Per-workspace analysis usage tracking
CREATE TABLE analysis_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    user_id UUID REFERENCES users(id),
    analysis_type TEXT NOT NULL CHECK (analysis_type IN ('page_analysis', 'opportunity', 'execution_plan')),
    billed_at TIMESTAMPTZ DEFAULT NOW(),
    period_start DATE NOT NULL,        -- billing period
    period_end DATE NOT NULL
);

CREATE INDEX idx_usage_workspace_period ON analysis_usage(workspace_id, period_start);
```

---

## 10. Cost Per Analysis

### 10.1 Cost components

Every full page analysis (Readiness + Bottleneck) incurs costs across four categories:

| Category | Provider | Unit | Est. cost/unit |
|---|---|---|---|
| SERP query | DataForSEO | per query | $0.0006 |
| Backlink data (target + 3 competitors) | DataForSEO Links | per domain | $0.0050 |
| Page crawl (target) | Firecrawl | per page | $0.0010 |
| Competitor crawls (×3) | Firecrawl | per page | $0.0010 |
| LLM — Readiness (Haiku) | Anthropic | ~3k tokens | $0.0003 |
| LLM — Bottleneck (Sonnet) | Anthropic | ~6k tokens | $0.0250 |
| GSC API | Google | free | $0.0000 |

### 10.2 Cost per analysis type (non-cached)

**Full page analysis (Readiness + Bottleneck):**

| Item | Qty | Cost |
|---|---|---|
| SERP query (primary keyword) | 1 | $0.0006 |
| Backlink data (target + 3 competitors) | 4 domains | $0.0200 |
| Crawl target page | 1 | $0.0010 |
| Crawl competitor pages | 3 | $0.0030 |
| Haiku (content summarization — target + 3 competitors) | 4 calls | $0.0040 |
| Haiku (Readiness) | 1 call | $0.0003 |
| Sonnet 4 (Bottleneck) | 1 call | $0.0250 |
| **Total (non-cached)** | | **~$0.054** |

*Summarization adds ~$0.004 per full analysis. Summaries are cached in `page_analyses.content_summaries` and reused on re-runs without re-crawling, so the cost is incurred once per crawl cycle, not per re-analysis.*

**Opportunity evaluation (Investment Decision Engine):**

| Item | Qty | Cost |
|---|---|---|
| Crawl placement page | 1 page | $0.0010 |
| Crawl domain content sample | 2–3 pages | $0.0020 |
| Backlink data (prospect domain) | 1 domain | $0.0050 |
| DataForSEO URL-level traffic (placement page) | 1 URL | $0.0006 |
| Haiku call 1 — content classification + signal extraction | 1 call | $0.0005 |
| Haiku call 2 — investment verdict assembly | 1 call | $0.0004 |
| **Total (non-cached)** | | **~$0.010** |

*Increase vs. prior estimate ($0.008): IDE adds URL-level traffic check and a second Haiku call for the two-step LLM architecture. Net increase ~$0.002 per opportunity evaluation.*

**Execution plan:** ~$0.002 (Haiku only, uses already-cached data)

### 10.3 Cache impact on cost

Backlink data is the dominant recurring cost. With 72-hour caching on competitor domains, if the same competitor appears in multiple analyses (common for competitive niches), the cache hit rate can be 60-80%, reducing effective cost per analysis to ~$0.015-0.025 for full page analysis.

**Key assumption challenged:** The above assumes DataForSEO for both SERP and backlink data. Ahrefs API would reduce backlink data quality tradeoffs but increases cost by ~3-5x for the backlink component. At MVP scale (hundreds of analyses/month), the difference is ~$50-200/month. At scale (thousands/month), it becomes meaningful. Start with DataForSEO; switch if data quality proves insufficient.

### 10.4 Unit economics at scale

| Analyses/month | Gross cost (cached) | Gross cost (uncached) |
|---|---|---|
| 500 | ~$10 | ~$25 |
| 5,000 | ~$75 | ~$250 |
| 50,000 | ~$600 | ~$2,500 |
| 500,000 | ~$5,000 | ~$25,000 |

At volume, negotiate directly with DataForSEO and Anthropic for enterprise pricing. Both offer custom contracts at meaningful volume. Anthropic's batch API also reduces LLM costs by 50% for non-real-time analysis — evaluate this once job queue architecture is in place.

### 10.5 Analysis credit model

The platform's billing model (seat + analysis volume) must account for these unit costs with appropriate margins. A rough floor:
- Free tier: 10 analyses/month → cost ~$0.50; acceptable for acquisition
- Solo plan ($49/month): 200 analyses → cost ~$3-5; healthy margin
- Agency plan ($199/month): 2,000 analyses → cost ~$30-50; healthy margin
- Scale: custom pricing with volume discounts on both the platform side and the API side

**Risk:** LLM costs are controlled by Anthropic and can change. Lock in the unit economics assumption now and review quarterly. Mitigation: the job queue architecture allows swapping models (e.g., use Haiku for all tasks if Sonnet costs spike) with a single config change, without code changes.

---

## 11. API Provider Recommendations

### 11.1 SERP Data

**Primary recommendation: DataForSEO**

| Provider | Cost/query | Index freshness | Notes |
|---|---|---|---|
| DataForSEO | $0.0006 | Near-real-time | Pay-as-you-go, comprehensive |
| SerpAPI | $0.005 | Near-real-time | 10x more expensive; easier API |
| ValueSERP | $0.001 | Near-real-time | Simpler pricing, good for small scale |
| Bright Data SERP | $0.001–$0.003 | Real-time | Enterprise focus; complex setup |

**Reasoning:** DataForSEO offers the most complete SERP dataset at the lowest per-query cost. The API is more complex than SerpAPI but the cost differential at even moderate volume (5,000 queries/month = $3 vs $25) justifies the setup effort.

**Risk:** DataForSEO's API has somewhat erratic reliability (occasional timeouts, inconsistent error codes). Implement a retry decorator on all DataForSEO calls with exponential backoff.

**Tradeoff:** SerpAPI's developer experience is significantly better. If engineering velocity is the constraint at MVP (first 2-3 months), start with SerpAPI and migrate to DataForSEO once the pipeline is proven. The abstraction layer in the Data Fetcher Worker should make this swap trivial.

### 11.2 Backlink Data

**Primary recommendation: DataForSEO Backlinks API (with Ahrefs upgrade path)**

| Provider | Cost per domain check | Index size | Notes |
|---|---|---|---|
| DataForSEO Backlinks | $0.003–$0.007 | Large (Ahrefs-sourced data) | Same vendor as SERP; volume discounts |
| Ahrefs API | $0.02–$0.05 | Largest | Gold standard; expensive at API tier |
| Moz API | $0.01 | Smaller | Reliable DA scores; smaller index |
| Majestic | $0.005 | Large (different crawl) | Good trust flow signals; less popular |

**Reasoning:** DataForSEO's backlinks product sources data from multiple crawlers (including Ahrefs-adjacent data). For the signals we need (referring domain count, domain rating equivalent, anchor distribution), the data quality is sufficient at a fraction of Ahrefs API cost. The upgrade trigger: if users report systematic discrepancies between Serpnex's authority assessments and what they see in Ahrefs (their benchmark), switch the backlink provider.

**Critical note:** DataForSEO's Ahrefs-adjacent backlink data has a known lag of 7-30 days vs. Ahrefs' live index. For opportunity evaluation (where we're checking a prospect site), a 30-day lag is acceptable. For competitive gap analysis in Bottleneck, it is also acceptable — referring domain counts don't change dramatically week-to-week. This lag does not materially affect verdict quality.

**Majestic Trust Flow** is worth fetching alongside DataForSEO for opportunity evaluation — Trust Flow / Citation Flow ratio is one of the better spam indicators available without paying Ahrefs prices. Add it as a secondary signal in the opportunity evaluation prompt.

### 11.3 Web Crawling

**Primary recommendation: Firecrawl (MVP) → self-hosted Playwright (scale)**

| Provider | Cost/page | JS rendering | Notes |
|---|---|---|---|
| Firecrawl | $0.001 | Yes | Managed, returns clean markdown |
| Jina AI Reader | $0.001 | Partial | Simple HTTP reader; fast |
| Browserless | $0.005 | Yes | Self-hosted option available |
| Self-hosted Playwright | ~$0 variable | Yes | Infrastructure overhead |
| requests + BeautifulSoup | $0 | No | Fine for static pages |

**Reasoning:** Firecrawl handles JS rendering, rate limiting, and IP rotation invisibly. For MVP this is the right tradeoff: pay a small per-page fee to avoid operating a headless browser fleet. Most competitor pages are crawlable with clean Markdown output. Self-host Playwright when: (a) Firecrawl costs exceed $200/month, or (b) custom cookie/session handling is needed for specific analysis scenarios.

**Fallback chain:** Firecrawl → Jina AI Reader → requests. If Firecrawl times out or returns empty content, fall back to Jina (simpler, faster, lower quality). If Jina fails, use requests. Flag the crawl method used in `data_quality.crawl_method` for confidence scoring.

### 11.4 LLM Provider

**Primary: Anthropic (Claude Sonnet 4 + Haiku 4.5)**

See §4 for full reasoning. No other provider is recommended for the primary pipeline. However:

**Fallback provider (emergency only):** OpenAI GPT-4o-mini for Haiku-equivalent tasks if Anthropic has an outage. Implement this as a circuit-breaker pattern, not a default. The schemas must be identical (both support function calling with JSON output). Test this fallback during development — do not discover schema incompatibilities during a production incident.

**Do not use:** Open-source self-hosted models (Llama, Mistral) at MVP. The reasoning quality for multi-signal competitive analysis is meaningfully below GPT-4-class models for the Bottleneck task specifically. This assumption should be re-evaluated in 12 months as open-source reasoning improves.

### 11.5 GSC Integration

**Google Search Console API** — no alternative. This is a direct OAuth2 integration. Use `google-auth` Python library. Key permissions required: `https://www.googleapis.com/auth/webmasters.readonly`.

### 11.6 Provider summary and priority

| Provider | Service | Priority | MVP start |
|---|---|---|---|
| Anthropic | LLM | Critical | Day 1 |
| Google | GSC | Critical | Day 1 |
| DataForSEO | SERP + Backlinks | Critical | Day 1 |
| Firecrawl | Crawling | Critical | Day 1 |
| Majestic | Trust Flow (opportunity) | Useful | Sprint 2 |
| SerpAPI | SERP (dev fallback) | Optional | Dev only |

---

## 12. MVP Technical Scope

### 12.1 The MVP decision constraint

The product's value is proven when one user runs one analysis and receives one non-obvious verdict. Everything that must be built to enable that is MVP scope. Everything else is post-MVP.

**The aha moment (§4.4 of the Design Brief):** The first Bottleneck verdict that says something non-obvious. This is the target. Every technical decision should ask: does this get us to a reliable, accurate Bottleneck verdict faster?

### 12.2 In scope for MVP

**Authentication and workspace:**
- Email + Google OAuth sign-up/sign-in
- Single workspace per user (multi-workspace is post-MVP)
- Single role: owner (RBAC is post-MVP; do not build Viewer/Strategist roles until the product is working)

**Core analysis pipeline:**
- Full page analysis: Readiness + Bottleneck (the two modules that deliver the aha moment)
- Opportunity evaluation (the second-highest value module — agencies have immediate use for this)
- Execution plan (fast to build once opportunity evaluation is complete)

**GSC integration:**
- OAuth connect flow
- Data pull for connected properties
- Graceful degradation when not connected

**Data fetching:**
- DataForSEO: SERP + Backlinks
- Firecrawl: page and competitor crawling
- In-memory caching via Redis (do not skip this — it is the cost control mechanism)

**UI:**
- Page Workspace (Readiness + Bottleneck sections)
- Opportunity evaluation (single URL input + verdict)
- Analysis running state (the SSE-powered "strategist thinking" experience)
- Simple sites/pages list

**Not in MVP scope:**
- Client-facing share/export (post-MVP)
- Multi-workspace support (post-MVP)
- Role-based access (post-MVP)
- Campaigns/Tracking module (explicitly post-MVP per design brief)
- Forecast panel (post-MVP — requires outcome data or meaningful RD/position modeling)
- Bulk analysis (post-MVP)
- Mobile-optimized layouts (responsive but not mobile-first at MVP)
- RTL/Arabic support (post-MVP — design must accommodate it structurally, but implementation is post-MVP)
- Portfolio allocation view (post-MVP)
- Billing and payment integration (gated for closed beta; add in first post-MVP sprint)

### 12.3 The confidence-first principle for MVP

Do not ship analyses that consistently produce wrong verdicts confidently. A `low` confidence verdict with accurate underlying data is more valuable than a `high` confidence verdict that is wrong. The validation layer (§7) and confidence floor rules (§7.4) must be implemented before launch, even if this delays the ship date.

**Rationale:** The product's entire reputation depends on the quality of its first verdict per user. One wrong confident verdict (especially a false "links won't help" conclusion) destroys trust immediately. A low-confidence verdict that is honest about its uncertainty is recoverable.

### 12.4 MVP sprint sequence

**Sprint 1: Foundation**
- Project setup (FastAPI + Celery + PostgreSQL + Redis)
- Database schema (core tables only: workspaces, users, sites, pages, page_analyses)
- DataForSEO integration (SERP + Backlinks) with caching layer
- Firecrawl integration with fallback chain
- GSC OAuth integration

**Sprint 2: Analysis pipeline**
- Analysis orchestrator (state machine, Celery tasks, progress events via Redis)
- Data collection workers (crawl, GSC, SERP, backlinks — parallel)
- LLM workers (Readiness + Bottleneck)
- Pydantic schemas + validation layer
- Confidence scoring model
- SSE endpoint for analysis progress

**Sprint 3: Opportunity + Execution**
- Opportunity evaluation pipeline
- Execution plan generation
- Both with full schema + validation

**Sprint 4: Web UI**
- Auth flows
- Page Workspace (Readiness + Bottleneck)
- Analysis running state (SSE consumer)
- Opportunity detail and execution plan views
- Basic sites/pages list

**Sprint 5: Quality + Launch prep**
- End-to-end testing with real URLs
- Confidence calibration (manual review of 50+ verdicts)
- Prompt tuning based on real outputs
- Error handling and recovery
- Rate limiting and quota enforcement

### 12.5 Critical risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM produces confidently wrong Bottleneck verdicts | Medium | High | Validation layer, confidence floors, manual QA of 50 verdicts before launch |
| Backlink data lag produces stale verdicts | Medium | Medium | Clearly surface data freshness in UI; cache timestamps visible in verdict |
| SERP keyword identification fails for pages with no GSC | High (for free-trial users) | Medium | Content-based keyword inference as fallback; lower confidence appropriately |
| DataForSEO reliability issues delay analyses | Medium | Medium | Retry logic, timeout handling, user-visible "analysis took longer than expected" state |
| Competitor page crawls blocked (403/bot detection) | High | Medium | Firecrawl handles most; accept partial competitor data and lower confidence accordingly |
| Anthropic API outage during analysis | Low | High | Circuit breaker + GPT-4o-mini fallback for Haiku tasks; queue Sonnet tasks for retry |
| Cost overrun from low cache hit rates at launch | Medium | Low (initially) | Monitor cache hit rates daily; alert at 70% miss rate; tighten TTLs if needed |
| LLM outputs fail schema validation at high rate | Low | High | Retry with error feedback; test schema with 100+ synthetic prompts before launch |

---

## Appendix A — Technology Stack Summary

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12 | ML/AI ecosystem, async support |
| API Framework | FastAPI | Async, Pydantic native, auto OpenAPI |
| Job Queue | Celery + Redis | Reliable async jobs, retry, priority |
| Database | PostgreSQL 15 | Relational + JSONB verdicts |
| Cache | Redis | Celery backing + API response cache |
| LLM | Anthropic Claude | Sonnet 4 (Bottleneck), Haiku 4.5 (others) |
| SERP | DataForSEO | Cost-effective at scale |
| Backlinks | DataForSEO Backlinks | Same vendor, volume discounts |
| Crawling | Firecrawl (MVP) | Managed JS rendering |
| GSC | Google Search Console API | First-party, OAuth2 |
| Real-time | Server-Sent Events | One-directional progress, HTTP-native |
| Hosting | Railway / Render (MVP) | Managed, fast to ship |

## Appendix B — Decision Log

| Decision | Chosen | Alternative | Reason |
|---|---|---|---|
| Backend language | Python | Node.js | LLM/ML ecosystem, Pydantic |
| LLM primary | Claude Sonnet 4 | GPT-4o | Better calibrated uncertainty, structured output reliability |
| LLM secondary | Claude Haiku 4.5 | GPT-4o-mini | Consistency with primary; Anthropic volume pricing |
| Job queue | Celery + Redis | BullMQ / SQS | Python-native, proven, self-hostable |
| Confidence model | Deterministic signal weights | LLM self-report | Auditable, overridable, no hallucination risk |
| Backlink provider | DataForSEO | Ahrefs API | 3-5x cost difference; acceptable quality at MVP |
| Crawling | Firecrawl (managed) | Self-hosted Playwright | Faster MVP, avoid infra overhead |
| Real-time | SSE | WebSockets | One-directional, simpler, HTTP-native |
| Output validation | Pydantic + business rules | JSON Schema only | Type safety + domain rule enforcement together |
| Competitor keyword targeting | GSC top impression keyword | LLM inference from content | GSC data is ground truth when available |

---

*This document must be reviewed and approved before any implementation begins. Update it when decisions change; do not let the code diverge from the documented architecture without a corresponding update here.*
