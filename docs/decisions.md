# Decision Log

This file records every significant architectural or product decision made during Serpnex development.

---

## 2026-06-25 — Investment Decision Engine: Dual-Mode Architecture

### Decision: The IDE supports two evaluation modes, detected automatically from the input URL

**Context:** The original IDE design required a specific placement page URL as a mandatory input, producing `insufficient_data` if only a domain was provided. This fails the most common guest post evaluation workflow: a user has identified a domain for outreach but no article exists yet. At the point the investment decision must be made, the placement URL does not exist.

**Decision:** The IDE supports two evaluation modes — Mode A (Specific Placement) and Mode B (Guest Post Opportunity) — sharing a single aggregation model, schema, validation layer, and hard exclusion gate set. The mode is detected automatically from the input URL. Users never select a mode.

---

### Mode A — Specific Placement Evaluation

Triggered when: the input URL resolves to a specific crawlable article or page with substantive content.

Detection signals (all must pass to classify as Mode A):
- Response body contains >500 characters of article content
- At least one of: article/BlogPosting schema markup, publication date, byline/author attribution
- NOT a listing or index page (no article-card grid, no pagination controls to sibling articles)

Data collection: crawl the specific placement page. P1–P5 signals derived from that page.

Confidence ceiling: **High** — all signals can be fully populated.

---

### Mode B — Guest Post Opportunity Evaluation

Triggered when: the input URL does not resolve to a specific article. Covers:
- Bare domain (`example.com` or `https://example.com/`)
- Category or section URL (`https://example.com/blog/`, `https://example.com/resources/seo/`)
- Any URL returning non-200 status (domain used as fallback)
- Any URL classified as a listing/index/pagination page

Category URLs are first-class inputs, not second-class domain inputs with a path. When a category URL is provided, the system samples articles exclusively from that section without inference.

**Sub-type: Category URL**
Path identifies a content section. Sample 3–5 articles from that section only.
Confidence ceiling: **Medium**

**Sub-type: Domain only**
No section path is provided. System infers the most relevant section before sampling.
Confidence ceiling: **Low**

Exception to ceiling: if the user provides a target pitch topic alongside the URL, P1 and P5 approximations become more precise. The ceiling tier does not change, but the score achievable within that tier is higher.

---

### Section Inference (Mode B, Domain-only sub-type)

When only a domain is provided:
1. Fetch `robots.txt` and `sitemap.xml` to enumerate primary content sections
2. Crawl the homepage; extract main navigation sections and their topic labels
3. LLM classification (Haiku): match navigation sections to the target page topic
4. If clear match found → sample 3–5 articles from that section
5. If no clear match (broad domain, unrelated sections) → sample from the section with highest estimated organic traffic (DataForSEO URL pattern matching or sitemap priority values)
6. Record the inferred section in `inferred_section` field of the verdict for user transparency

If section inference fails entirely (no sitemap, no clear navigation, no content pattern) → fallback to sampling homepage-linked articles and note the limitation in `data_quality`.

---

### Mode Detection Logic

```
Input URL
  │
  ├─ Fetch URL (HEAD → GET)
  │
  ├─ Non-200 response → MODE B, Domain-only (use domain from URL)
  │
  ├─ Is it a single article page?
  │     All true: body > 500 chars, has date/byline/schema, not a listing
  │     → MODE A (Specific Placement)
  │
  ├─ Is it a listing/index/category page?
  │     URL has non-root path → MODE B, Category URL sub-type
  │     URL is bare domain or root path → MODE B, Domain-only sub-type
  │
  └─ Ambiguous classification → MODE B (safer default), log mode_detection_note
```

If the system detects a potential misclassification (e.g., homepage is article-like, or a category page has article signals), it records `mode_detection_note` in `data_quality` rather than silently proceeding.

---

### Signal Approximation in Mode B

| Signal | Mode A | Mode B |
|---|---|---|
| P1 (topical relevance) | Specific page vs. target | Averaged across 3–5 sampled articles vs. target |
| P2 (content quality) | Specific page quality | Averaged across sampled articles |
| P3 (organic traffic) | URL-level DataForSEO | Sum of sampled article URL traffic (category-level proxy) |
| P4 (OBL quality) | Specific page OBLs | Averaged OBLs from sampled articles |
| P5 (placement feasibility) | Can this link fit in this existing article? | Could we write an article for this site in this topic/section that accommodates this link? |

P5 in Mode B evaluates against the editorial patterns visible in the sampled articles rather than a specific article's content.

All domain-level signals (D1–D9) are identical across both modes — they are not affected by the input URL type.

---

### Confidence Ceiling Rules

| Mode | Sub-type | Ceiling |
|---|---|---|
| Mode A | Specific placement | High |
| Mode B | Category URL | Medium |
| Mode B | Domain only | Low |

Ceiling is enforced deterministically after LLM self-report, overriding any higher confidence the LLM produces. This is a structural constraint, not a score adjustment. The `confidence_ceiling` field in the verdict records the applicable ceiling for auditability.

---

### Verdict Qualifier (Mode B only)

The `mode_qualifier` field in `InvestmentVerdict` must be populated in all Mode B verdicts with a plain-language statement surfacing the evaluation's reliance on sampled content. Example: "Assessment based on 4 articles sampled from example.com/seo/. Link value depends on the quality and eventual ranking of the article published. Run a Specific Placement evaluation once the article is live to confirm investment value."

This qualifier surfaces in the UI prominently alongside the verdict, not buried in metadata.

---

**Reasoning:** The two-mode architecture preserves the IDE's analytical integrity while accommodating the full guest post evaluation lifecycle. Before outreach: Mode B gives a directional verdict with an honest confidence ceiling. After article publication: Mode B can be upgraded to Mode A with a fresh evaluation of the specific page. The product supports the complete workflow without requiring a placement URL that may not exist for weeks.

**Alternatives considered:**

*Two separate evaluation engines:* Rejected. Domain-level signals (D1–D9) plus hard exclusion gates are identical across both modes — approximately 70% of the analytical work. Two engines means two prompts to version, two schemas to maintain, two validation layers to update in sync. They will inevitably drift. One engine with a branching data collection step is architecturally cleaner and cheaper to maintain.

*User-selectable mode:* Rejected. Cognitive load on the user; incorrect selection is likely (a user may select "domain evaluation" while pasting a specific article URL). The URL type is objectively determinable — automatic detection is more reliable.

*Domain Screen as a separate lightweight product:* Rejected for MVP. Adds a third product surface (its own schema, prompt, maintenance burden). The Mode B confidence ceiling + mode qualifier achieves the same effect within the unified engine without adding complexity.

*Require placement URL (original design):* Rejected. Fails the most common workflow for new guest post evaluation, which is the primary use case for agencies.

**Risks:**

*Mode detection misclassification:* Some URLs are structurally ambiguous (a long product page that reads like an article; a multi-page article with a listing structure). Mitigation: default to Mode B on ambiguity (the safer output); surface `mode_detection_note` in the verdict so the user can identify and override if needed.

*Section inference error:* The inferred section may not match what the user intends to pitch. Mitigation: surface `inferred_section` explicitly in the verdict; provide a clear path to resubmit with a category URL for a more precise evaluation.

*Mode B confidence ceiling frustrating users:* A user who submits a domain for quick evaluation may receive a Low confidence verdict. Mitigation: the UI must explain why confidence is capped ("No placement article exists yet — verdict is based on site editorial patterns") and offer the upgrade path to Mode A after publication.

**Impact:**
- `intelligence-architecture.md §3.5` rewritten with full dual-mode pipeline, mode detection logic, and category URL / section inference documentation
- `intelligence-architecture.md §6.3` updated: `InvestmentVerdict` gains `evaluation_mode`, `mode_b_subtype`, `sampled_article_urls`, `inferred_section`, `confidence_ceiling`, `mode_qualifier`, `mode_detection_note` fields; business logic validation rules updated
- `intelligence-architecture.md §7.2` updated: mode-specific validation rules added
- `intelligence-architecture.md §8.3` updated: confidence ceiling rules added
- `docs/validation/assumptions.md` updated: A21 (mode detection accuracy), A22 (section inference quality)
- `docs/prompts/opportunity-v1.md` (pending deliverable, Sprint 3): must accept `evaluation_mode` and `mode_b_subtype` as parameters; Call 1 prompt handles both single-page and multi-article-sample input formats within the same tool schema

---

## 2026-06-25 — Investment Decision Engine Design

### Decision: Replace the 4-dimension Opportunity Evaluation with a gated, clustered Investment Decision Engine

**Context:** The original Opportunity Evaluation module (§3.5) assessed link prospects across four flat dimensions: relevance_fit, placement_quality, authority_value, risk. This was a first-pass design. Before Sprint 3, the module was redesigned as a full Investment Decision Engine (IDE) answering the question: *"Is this website worth investing money in for a guest post or backlink?"* The redesign was driven by the need to behave like an experienced SEO strategist — forming a composite judgment — not a metrics dashboard outputting four separate scores.

**Decision:** The IDE uses a three-tier architecture: hard exclusion gates → scored signal clusters → verdict mapping. Placement-page signals are weighted more heavily than domain-level signals. Risk is applied as a score multiplier, not an additive cluster. The Editorial Integrity signal is a first-class load-bearing signal that can cap the overall Investment Score at 45 regardless of other factors.

---

### Signal Architecture

#### Tier 0 — Hard Exclusion Gates

These run before scoring. One trigger produces `not_recommended` with no further analysis.

| Gate | Condition |
|---|---|
| H1 Prohibited content | Primary content is adult, escort, gambling-as-core-business, illegal activities, or scam |
| H2 Deindexed / penalized | Indexed page ratio <10% AND near-zero traffic despite meaningful backlink history |
| H3 Malware | Google Safe Browsing or equivalent flags the domain |
| H4 Language impossibility | Complete language mismatch with zero plausible audience overlap |
| H5 Manual action indicators | >80% organic traffic loss in 3 months + backlink profile intact (traffic loss not explained by link loss) |

Rationale: These are conditions where no amount of authority or relevance makes the investment defensible. The gate check is cheap (classification + traffic check) and prevents the scoring machinery from running on disqualified sites.

#### Tier 1 — Placement-Page Signals (Primary)

The evaluation prioritizes the specific page where the link will appear, not the domain in aggregate. A Forbes Technology article is evaluated as a technology article, not as "Forbes."

| Signal | Code | Data source |
|---|---|---|
| Placement page topical relevance | P1 | LLM semantic comparison: placement page vs. target page topic + audience |
| Placement page content quality | P2 | LLM assessment: originality, depth, editorial care |
| Placement page estimated organic traffic | P3 | DataForSEO URL-level organic estimate |
| Placement page outbound link quality | P4 | Crawl OBLs from placement page, classify destinations |
| Natural link placement feasibility | P5 | LLM assessment: could a link to target page sit here editorially? |

P5 output is an enum: `natural | workable | forced | implausible`. An `implausible` rating caps the Quality Cluster at 0.35 regardless of other signals.

#### Tier 2 — Domain-Level Signals (Context + Risk)

Domain signals inform authority and identify risk. They are secondary to placement-page signals for quality assessments but primary for risk assessments.

| Signal | Code | Data source |
|---|---|---|
| Site topical coherence | D1 | LLM topic distribution classification of top-traffic content |
| Domain authority signal | D2 | DataForSEO: referring domain count + domain authority estimate |
| Domain organic traffic + trend | D3 | DataForSEO historical: current traffic + 12-month trajectory |
| Editorial integrity (composite) | D4 | LLM + crawl: authorship, content coherence, sponsored ratio, OBL patterns |
| Content freshness | D5 | Last publication date from crawled content |
| Indexed page health | D6 | Submitted vs. indexed page ratio |
| Spam footprint indicators | D7 | PBN structural signals, link farm patterns, paid-link marketplace indicators |
| Domain history | D8 | Wayback Machine snapshots + backlink profile discontinuities |
| Geo / country targeting | D9 | TLD + content language + hreflang signals |

---

### Aggregation Model

**Step 1: Hard exclusion gates** — any trigger → verdict immediately.

**Step 2: Cluster scores**

*Relevance Cluster:*
```
Relevance = (P1 × 0.45) + (D1 × 0.25) + (D9 × 0.20) + (language_match × 0.10)
Minimum threshold: if (P1 × 0.45 + D1 × 0.25) < 0.30 → verdict cannot be "recommended" regardless of other scores
```

*Authority Cluster:*
```
Authority = (P3 × 0.35) + (P2 × 0.25) + (D2 × 0.25) + (D3_current × 0.15)
```

*Quality Cluster:*
```
Quality_raw = (D4 × 0.35) + (P4 × 0.25) + (P5 × 0.20) + (D5 × 0.10) + (D6 × 0.10)
Quality = Quality_raw
  if D4 < 0.30: Quality = min(Quality_raw, 0.40)  [editorial integrity floor]
  if P5 == "implausible": Quality = min(Quality_raw, 0.35)  [placement feasibility floor]
```

*Risk Cluster (minimum-biased average):*
```
Risk_signals = [D7 × 0.35, D3_trend × 0.25, D8 × 0.20, D1_consistency × 0.10, P4_obl_flags × 0.10]
Risk_score = (weighted_average × 0.60) + (min_individual_signal × 0.40)
```

Rationale for minimum-biased risk: one severe spam signal should dominate even if all other risk signals are clean. The 60/40 weighting reflects this without the minimum becoming a hard veto on its own.

**Step 3: Risk as multiplier**

```
Risk_multiplier:
  Risk_score ≥ 0.75 → 1.00
  Risk_score 0.55–0.74 → 0.80
  Risk_score 0.35–0.54 → 0.55
  Risk_score < 0.35 → 0.25
```

**Step 4: Investment Score**

```
Base_Score = (Relevance × 0.35) + (Authority × 0.30) + (Quality × 0.35)
Investment_Score = Base_Score × Risk_multiplier × 100  [0–100 scale]

Editorial integrity cap:
  if D4 < 0.30: Investment_Score = min(Investment_Score, 45)
```

---

### Editorial Integrity — Full Signal Design

D4 answers: *Does this site publish because it has something to say, or because someone paid them to say it?*

Sub-signals and weights:

| Sub-signal | Weight | Positive indicators | Negative indicators |
|---|---|---|---|
| Authorship quality | 0.30 | Named authors with verifiable identities, topic specialization | "Admin," generic bylines, anonymous rotating authors |
| Content coherence + voice | 0.25 | Consistent niche, distinct editorial perspective | Wildly inconsistent topics, AI-pattern writing, content existing only to host links |
| Sponsored content ratio | 0.25 | <20% content labeled sponsored/paid | >60% sponsored labels; site primarily a placement vehicle |
| OBL editorial quality | 0.20 | Links to sources, citations, industry tools | Predominantly commercial landing pages with exact-match commercial anchors |

Interpretation scale:
- 0.8–1.0: Genuine editorial publication
- 0.6–0.8: Principally editorial with normal monetization (acceptable)
- 0.4–0.6: Mixed — significant commercial content; flag as condition
- 0.2–0.4: Primarily commercial; significant devaluation risk
- 0.0–0.2: Link marketplace; do not invest

**Why editorial integrity caps the score at 45 below 0.30:** A link placed in a link-selling marketplace context provides authority transfer today but carries meaningful future risk (Google identifying and discounting the pattern, site penalty, content deletion). The investment is not defensible regardless of current authority metrics.

---

### Conflicting Signal Resolution

Four defined patterns:

1. **High authority + declining trend** → authority is real but depreciating. Do not reduce authority cluster score. Instead: downgrade D3_trend, surface explicitly as a named condition ("Link value may reduce over 12 months as site traffic declines").

2. **Low domain authority + strong placement page signals** → emerging publication. The aggregation model handles this correctly (P3 and P1 carry 35% + 45% of their clusters). Verdict should name the dynamic explicitly rather than penalizing it as "low authority."

3. **Strong editorial integrity + visible sponsored content** → this is not a conflict. Some sponsored content is normal for legitimate editorial sites. The sponsored content ratio sub-signal handles proportionality. Do not penalize a site for having some commercial content.

4. **Clean placement page + domain-level risk signal** → domain risk cannot be overridden by placement page quality. The risk cluster applies to the whole investment including future devaluation risk at the domain level. The placement page quality can keep the verdict at "with_conditions" but cannot push it to "recommended" if the domain risk score is material.

**General rule:** Risk signals always floor the verdict below the quality/authority ceiling. When signals conflict, surface the conflict in the verdict explanation rather than silently resolving it in the score.

---

### Confidence Scoring

Updated Opportunity Evaluation signal weights:

| Signal | Weight | Treatment if missing |
|---|---|---|
| Placement page crawl (P1–P5) | 0.40 | Missing = Insufficient Data (cannot evaluate without it) |
| Spam footprint check (D7) | 0.25 | Missing = confidence -1 tier (cannot confirm clean) |
| Domain traffic + trend (D3) | 0.15 | Missing = confidence -1 tier |
| Domain authority data (D2) | 0.10 | Missing = confidence -1 tier |
| Domain history (D8) | 0.05 | Missing = no confidence impact |
| Geo signals (D9) | 0.05 | Missing = no confidence impact (approximate inference acceptable) |

**Required signals (missing = Insufficient Data):**
- Placement page crawl (P1, P2, P4) — cannot evaluate without reading the placement page
- Editorial integrity assessment (D4) — cannot evaluate without crawling domain content
- Hard exclusion checks (H1–H5) — must run before any verdict
- Language detection

**Confidence tier calculation:** Start at High. Each important signal missing: -1 tier. Two+ signals in same cluster missing: additional -1 tier. Conflicting signals: -1 tier. Borderline Investment Score (48–62): -1 tier. Below Low = Insufficient Data.

---

### Output Tier Definitions

**Recommended:** Investment Score ≥ 68, no hard exclusions, Relevance cluster ≥ 0.55, Risk multiplier ≥ 0.80, D4 ≥ 0.55, confidence Medium or High.

**Recommended with Conditions:** Investment Score 48–67 at Medium/High confidence, OR score ≥ 68 with one significant condition. Each condition is specific and named, not generic ("Organic traffic has declined 34% over 12 months — verify the placement page still ranks before committing budget").

**Not Recommended:** Any hard exclusion, OR Investment Score < 48, OR Risk multiplier < 0.55, OR D4 < 0.30, OR Relevance cluster < 0.30, OR P5 == "implausible". The verdict names the primary reason specifically.

**Insufficient Data:** Any required signal unavailable, OR placement URL not provided, OR confidence reaches the Insufficient Data tier. This is not a soft Not Recommended — it is a genuine inability to reach a verdict. Specifies exactly what is missing.

**Critical design rule:** When the placement page URL is not provided, the output must be Insufficient Data with the message "Provide the specific URL where the link or guest post will appear. Domain-level signals alone are insufficient to determine investment value." Do not produce a domain-only verdict and label it an investment recommendation.

---

**Reasoning:** The flat 4-dimension model treated all signals as independent and equally weighted, which does not match how an experienced strategist thinks. The cluster model mirrors the four questions a strategist actually asks — "Is this the right space? Is it authoritative? Is it legitimate? Is it risky?" — and reflects the load-bearing nature of each: relevance and quality carry equal weight, authority provides context, risk applies as a conditional multiplier.

**Alternatives considered:**
- *Simple weighted linear sum* — all signals in one pool with assigned weights → rejected because it doesn't capture the interaction effects (a high-authority link-farm should not be Recommended; a multiplicative risk model handles this correctly)
- *Pure LLM aggregation* — send all signals to the LLM and ask it to produce a verdict → rejected for the same reason as Bottleneck confidence: LLM aggregation is not auditable or deterministic; a B2B product staking money decisions on verdicts must have a traceable score
- *Keep the 4-dimension flat model* → rejected because it would never surface the "editorial integrity" conclusion that distinguishes this product from generic link quality checkers

**Risks:**
- Signal weights are hand-tuned. The relevance/quality split (0.35 each) and the authority weight (0.30) are informed by domain knowledge but not validated against outcome data. Revisit once the Campaigns module provides outcome tracking.
- Editorial integrity detection by LLM may be inconsistent across different site types (a newer niche publication may score lower than it deserves vs. a long-established one). The sub-signal weighting mitigates this but does not eliminate it.
- D3 trend data requires 12 months of historical DataForSEO data. For newer sites (<12 months), this signal will be partial.

**Impact:**
- `docs/intelligence-architecture.md §3.5`, `§5.5`, `§6.3`, `§8.3` updated with IDE specification
- `opportunities` table schema unchanged structurally; `opportunity_verdict` JSONB column will store the new `InvestmentVerdict` schema
- The Opportunity evaluation prompt (`docs/prompts/opportunity-v1.md`) is a new required deliverable before Sprint 3 — analogous to `bottleneck-v1.md`
- Opportunity evaluation LLM architecture: two Haiku calls (content classification + editorial integrity assessment) + one Haiku call for the investment verdict. Total Haiku cost per opportunity: ~$0.006–0.010 (up from ~$0.004). Final cost number to be confirmed in Sprint 3.

---

## 2026-06-24 — Automated Content Extraction Pipeline

### Decision: Production content summaries are generated by an automated crawl-and-summarize pipeline, not written by hand

**Context:** The Bottleneck prompt requires two types of content summary as input: a 100–150 word target page summary and three 60–100 word competitor summaries. During the 10-URL validation these are written manually by the evaluator. In production they must be generated automatically before the Bottleneck LLM call.

**Decision:** A dedicated content extraction and summarization pipeline runs as part of the data collection phase, prior to the Bottleneck prompt. Firecrawl (or the selected crawler) fetches the page HTML and renders it. A lightweight LLM call (Claude Haiku 4.5) then converts the rendered content into a structured summary matching the exact format defined in `docs/prompts/bottleneck-v1.md §3`.

**Reasoning:** Manual summaries are not scalable and introduce evaluator variance. The automated pipeline must produce summaries that are functionally equivalent to a disciplined human following the compression rules: descriptive, not evaluative; covering topic/angle, format, key headings, intent alignment, notable elements, and visible gaps.

**Tradeoffs:**
- A separate Haiku summarization call adds ~$0.001–0.002 and ~3–5 seconds per page to the pipeline cost and latency. Acceptable.
- The quality of Bottleneck verdicts is now dependent on the quality of the summarization call. A poorly prompted summarizer that produces vague or evaluative summaries will degrade Bottleneck verdict quality, even if the Bottleneck prompt itself is correct. This is the primary new risk introduced by this decision.
- Human-written summaries during validation are higher quality than automated summaries are likely to be initially. This creates a validation gap (see below).

**Validation gap created:** The 10-URL prompt validation confirms that *well-written human summaries* produce high-quality Bottleneck verdicts. It does not confirm that *automated summaries* will be good enough inputs. A second validation — the **Pipeline Validation** — is required before Sprint 1 ships to production. See risk entry below.

**Risk:** Automated summaries are systematically shallower, more generic, or evaluative ("the content covers X topic") rather than descriptive ("the page contains a 12-row comparison table and a calculator tool"). If so, verdict specificity (D3) and constraint identification accuracy (D1) will degrade at production relative to the validation results.

**Mitigation:** The summarization prompt must be written to the same standard as the Bottleneck prompt — explicit, rule-based, with a required output structure. It is not a throw-away preprocessing call. It must be validated separately before the product ships.

**Impact:**
- A summarization prompt (`docs/prompts/summarize-page-v1.md`) is a required deliverable before Sprint 2 begins.
- A Pipeline Validation (3–5 URLs, comparing human vs. automated summary verdicts) is a required gate before production launch.
- `docs/intelligence-architecture.md §3.2` preprocessing step must be updated to reflect this as an explicit pipeline stage with its own LLM call.
- `docs/validation/assumptions.md` A12 and A13 must be updated with production notes.

**Alternatives considered:** Rule-based extraction only (extract headings + first paragraphs deterministically, no LLM summarization). Rejected: this produces structurally consistent but semantically shallow summaries that miss format and intent signals the model needs. The LLM summarization step is necessary to produce the qualitative content characterization (angle, intent alignment, notable gaps) that the Bottleneck prompt requires.

---

## 2026-06-24 — Bottleneck Prompt and Evaluation Package

### Decision: Use Anthropic tool use (forced function call) as the output mechanism, not JSON-mode prompt instruction

**Context:** Prompt architecture design — how to reliably get structured output from the LLM.  
**Decision:** `tool_choice: {"type": "tool", "name": "analyze_bottleneck"}` with a full JSON schema. The model cannot produce prose output — only a valid tool call.  
**Reasoning:** Tool use is more reliable than "respond with valid JSON" at Sonnet level for complex nested schemas. The weight-must-sum-to-1.0 constraint and multi-level nesting (constraint_breakdown array of objects) are exactly the kind of structure that causes JSON-mode prose outputs to fail silently. Tool use lets the SDK validate the response before it reaches application code.  
**Alternatives considered:** JSON mode with prompt instruction ("respond with JSON matching this schema"); custom XML tags. Both are less reliable for nested schemas with numeric constraints.  
**Risks:** Tool use is slightly more expensive (the schema definition counts toward input tokens). Negligible at ~500 schema tokens.  
**Impact:** All LLM calls in the pipeline use tool use, not JSON mode.

---

### Decision: Compress data to 100–150 words (target) and 60–100 words (competitors) rather than sending page content

**Context:** Prompt architecture — how to handle page content as LLM input.  
**Decision:** Human-written or programmatically-generated content summaries using a defined format, not raw HTML or extensive excerpts.  
**Reasoning:** Full HTML is token-expensive and noisy. The model needs structural and topical signals, not verbatim content. A well-structured summary within a defined format is more signal-dense per token than raw HTML.  
**Assumptions:** See A12 and A13 in `docs/validation/assumptions.md`. Evaluator must follow descriptive-not-evaluative instructions or summaries will bias the model.  
**Risks:** Summary quality is the highest-variance input in the manual validation. In production, the summary generation must be deterministic — this is Sprint 2 work (data compression preprocessing step).  
**Impact:** The preprocessing step that converts raw crawled content into prompt-ready summaries is a required Sprint 2 deliverable.

---

### Decision: Five-category constraint taxonomy is locked for the validation period

**Context:** Prompt design — constraint classification.  
**Decision:** `link_authority | content_depth | intent_mismatch | internal_links | technical` — exactly these five. No additions until post-validation.  
**Reasoning:** Adding categories now would invalidate the scoring rubric. The taxonomy is broad enough to cover the URL archetypes in scope. Edge cases (E-E-A-T, locale mismatch) are explicitly excluded from the validation URL set.  
**Risks:** See A16 in assumptions. Some verdicts may be forced into an imprecise category. Document these cases — they inform the post-MVP taxonomy expansion.  
**Impact:** Prompt changelog must be updated if taxonomy changes post-validation. A taxonomy change is a schema change and requires a pipeline version bump.

---

## 2026-06-24 — Bottleneck Validation Plan

### Decision: Validate Bottleneck prompt quality manually before building pipeline infrastructure

**Context:** Pre-Sprint 1. The Bottleneck module is the product's highest-value and highest-risk LLM task. Building a full pipeline before confirming the prompt produces useful verdicts would be wasteful and risky.  
**Decision:** Run a 10-URL manual validation before Sprint 1 begins. Sprint 1 is gated on a Go verdict from this validation.  
**Reasoning:** The cost of a wrong prompt discovered in Sprint 4 (after full pipeline is built) is 3-4 sprints of wasted infrastructure. The cost of a 2-3 hour manual validation is 2-3 hours. The expected value of running the validation is strongly positive.  
**Alternatives considered:** Skip validation, trust the prompt design, start Sprint 1 immediately (faster to first code, but risks building on a broken foundation); validate with synthetic/toy data instead of real URLs (faster but does not surface real-world failure modes like sparse data and ambiguous SERP landscapes).  
**Risks:** The validation may surface a No-Go condition that delays Sprint 1 by 1-2 days for prompt revision. This is a feature, not a risk.  
**Impact:** Sprint 1 start date is contingent on validation outcome. Expected validation duration: 4-6 hours to gather data and run 10 URLs.

---

## 2026-06-24 — Intelligence Architecture

### Decision: Python + FastAPI as backend language and framework

**Context:** Pre-implementation. Choosing the backend stack before any code is written.  
**Decision:** Python 3.12 with FastAPI.  
**Reasoning:** The backend is primarily an analysis orchestration system, not a CRUD API. Python's ML/AI ecosystem (Anthropic SDK, Pydantic, asyncio) is the natural fit. FastAPI is async-native and integrates with Pydantic directly.  
**Alternatives considered:** Node.js with TypeScript (faster I/O concurrency but weaker AI ecosystem); Django REST Framework (heavier, not async-first).  
**Risks:** Python's GIL affects CPU-bound work — mitigated by Celery (separate worker processes). Deployment footprint is larger than Node.  
**Impact:** All backend development in Python. Frontend stack is separate and unaffected.

---

### Decision: Claude Sonnet 4 for Bottleneck, Claude Haiku 4.5 for all other LLM tasks

**Context:** Intelligence architecture design — LLM model selection.  
**Decision:** Anthropic Claude as the sole LLM provider. Sonnet 4 for the Bottleneck module; Haiku 4.5 for Readiness, Opportunity, Execution.  
**Reasoning:** Bottleneck requires multi-signal reasoning and calibrated uncertainty — Sonnet 4's reasoning quality and structured output reliability justify the cost. Haiku is sufficient and ~20x cheaper for single-dimension tasks.  
**Alternatives considered:** OpenAI GPT-4o (acceptable quality, worse structured output reliability on complex schemas); self-hosted Llama (quality insufficient for Bottleneck).  
**Risks:** Anthropic API outage; Anthropic pricing changes. Mitigated by GPT-4o-mini circuit-breaker fallback for Haiku tasks.  
**Impact:** All LLM calls go through Anthropic's API. Budget dependency on Anthropic pricing.

---

### Decision: Deterministic confidence scoring overrides LLM self-reported confidence

**Context:** Confidence scoring model design.  
**Decision:** Signal-weighted deterministic confidence calculation. LLM self-reports confidence but the deterministic score takes precedence. Hard floor rules applied post-validation.  
**Reasoning:** LLM confidence is known to be miscalibrated (overconfident when data is thin, underconfident when asked to hedge). For a B2B product where professionals stake decisions on verdicts, confidence must be auditable and predictable, not emergent.  
**Alternatives considered:** Pure LLM self-report (fast, but unreliable); ML-trained confidence regressor (requires outcome data not yet available).  
**Risks:** Signal weights are hand-tuned and may not reflect true predictive importance. Revisit once outcome data exists.  
**Impact:** Every verdict has a deterministic confidence score. The LLM's self-reported confidence is stored for auditing but not surfaced to users.

---

### Decision: DataForSEO for SERP + Backlinks (not Ahrefs API)

**Context:** API provider selection for competitive data.  
**Decision:** DataForSEO for both SERP queries and backlink data at MVP.  
**Reasoning:** 3-5x lower cost than Ahrefs API. Data quality sufficient for the gap signals used in Bottleneck. Same vendor for volume discounts.  
**Alternatives considered:** Ahrefs API (gold standard data quality, ~5x cost); Moz API (smaller index, accessible pricing); Majestic (good trust flow data, limited coverage).  
**Risks:** DataForSEO backlink data has 7-30 day lag vs. Ahrefs live index. Acceptable for comparative gap analysis.  
**Upgrade trigger:** User feedback indicating systematic discrepancy with Ahrefs benchmarks.  
**Impact:** All external competitive data flows through DataForSEO. Abstraction layer in Data Fetcher must allow provider swap.

---

### Decision: Firecrawl (managed crawling) over self-hosted Playwright for MVP

**Context:** Web crawling infrastructure for page content extraction.  
**Decision:** Firecrawl as managed crawling service for MVP.  
**Reasoning:** Eliminates headless browser infrastructure at MVP. JS-rendered pages handled without operating Playwright. Per-page cost (~$0.001) is negligible at MVP volume.  
**Alternatives considered:** Self-hosted Playwright (zero per-crawl cost, high infra overhead); Jina AI Reader (simpler, no JS rendering); requests + BeautifulSoup (no JS support).  
**Risks:** Cost scales linearly; if crawl volume grows, self-hosted is cheaper. Dependency on Firecrawl's reliability.  
**Upgrade trigger:** Firecrawl costs exceed $200/month or customization (cookies, sessions) becomes necessary.  
**Impact:** Crawl infrastructure is a managed service. Abstraction layer must allow swap to self-hosted.

---

### Decision: Celery + Redis for analysis job queue

**Context:** Analysis jobs are long-running (30s-2min), must survive restarts, and require retry logic.  
**Decision:** Celery with Redis as broker and result backend.  
**Reasoning:** Python-native, battle-tested, handles retries/priorities/worker isolation. Aligns with Python stack decision.  
**Alternatives considered:** BullMQ (Node-only, misaligned with Python stack); AWS SQS (vendor lock-in, added latency, operational complexity); RQ (simpler but less feature-rich).  
**Risks:** Celery configuration complexity; requires Redis to be reliable. Redis failure = job queue failure.  
**Impact:** Redis becomes a critical service dependency (dual purpose: Celery + API response cache).

---

### Decision: Server-Sent Events (SSE) for analysis progress streaming

**Context:** The UI needs the "strategist thinking" progress steps in real-time.  
**Decision:** SSE over WebSockets.  
**Reasoning:** Analysis progress is one-directional (server → client). SSE is HTTP-native, simpler to implement, requires no special infrastructure, and works through load balancers without sticky sessions.  
**Alternatives considered:** WebSockets (bidirectional, overkill for one-way streaming); polling (adds latency, wastes requests).  
**Risks:** SSE connections can be dropped by proxies; client must implement reconnect. Standard EventSource API handles this automatically.  
**Impact:** API server must support long-lived SSE connections. Load balancer timeout must be set appropriately (>120s).

---

### Decision: MVP excludes Forecast, Share/Export, Multi-workspace, RBAC, RTL, Campaigns

**Context:** MVP scope definition.  
**Decision:** MVP delivers Readiness + Bottleneck + Opportunity + Execution. No Forecast, no Share/Export, no multi-workspace, no role-based access, no RTL, no Campaigns.  
**Reasoning:** The aha moment (first non-obvious Bottleneck verdict) is achievable with Readiness + Bottleneck alone. Every excluded feature is valuable but not necessary for the first user to experience the product's core value.  
**Risks:** Agency users who need multi-seat access will hit this quickly. Plan to ship RBAC in first post-MVP sprint.  
**Impact:** Scope is bounded. Do not add MVP features without updating this decision log.

---

## 2026-06-25 — Sprint 2 Pre-work: Schema and Status Value Decisions

### Decision: Analysis status values use lowercase snake_case; detailed state machine retained in DB

**Context:** §3.1 defines a 10-state machine with UPPERCASE names. §9.2 shows 6 simplified states. Sprint 1 implemented the detailed states in UPPERCASE. All three sources contradicted each other.

**Decision:** The detailed 10-state machine from §3.1 is the correct model — it exposes exactly where a job is for debugging. The §9.2 SQL was an illustrative simplification, not a constraint. All status values are written in lowercase snake_case to match PostgreSQL convention and the §9.2 direction.

**Canonical status values:** `queued` → `collecting_data` → `data_ready` → `summarizing_content` → `summaries_ready` → `running_readiness` → `running_bottleneck` → `assembling_verdict` → `complete` | `failed`

**Risks:** Migration 0002 updates the CHECK constraint and default value. No production data exists yet so this is safe.

---

### Decision: `workspace_members` and `gsc_integrations` deferred to post-MVP

**Context:** §9.1 shows a `workspace_members` join table and a `gsc_integrations` table. Sprint 1 put `workspace_id` directly on `users` and stored GSC tokens as JSONB on the user.

**Decision:** The Sprint 1 simplified schema is correct for MVP. Single workspace per user, single owner role — a join table adds complexity without enabling any MVP feature. `gsc_tokens` JSONB on `users` is sufficient for one GSC connection per user.

**Post-MVP migration path:** When multi-workspace and RBAC are added, create `workspace_members`, create `gsc_integrations`, migrate data. No data loss.

---

### Decision: `page_analyses` expanded in migration 0002 for Sprint 2 workers

**Context:** Sprint 1's `page_analyses` had only `raw_data`, `verdict`, `error`. Sprint 2 writes separate verdict columns, content summaries, prompt versions, confidence, and validation audit data per §9.2.

**Decision:** Migration 0002 adds `summarization_prompt_version`, `prompt_version`, `content_summaries`, `readiness_verdict`, `bottleneck_verdict`, `readiness_confidence`, `bottleneck_confidence`, `data_quality`, `validation_overrides`, `workspace_id`, `started_at`, `completed_at`, `failed_reason`. The legacy `verdict` and `error` columns are retained but deprecated — they will be dropped post-MVP.

---
