# Changelog

---

## 2026-06-27 — Pre-Sprint 3 deliverables complete

### Added
- `docs/prompts/opportunity-v1.md` — Complete two-call Haiku prompt specification for the Investment Decision Engine. Covers: shared system prompt (5 rules, anti-bias framing), Call 1 signal extraction (mode-aware user message templates for Mode A and Mode B, full variable definitions, tool schema for `extract_investment_signals` with 14 fields), Call 2 verdict assembly (user message template with all computed scores as inputs, tool schema for `assemble_investment_verdict`, instructions preventing LLM from overriding deterministic outcome), anti-bias rules (5 documented), signal scoring reference table, and prompt changelog.

### Modified
- `app/providers/base/search_data.py` — Added `DomainMetrics` dataclass (provider-agnostic domain intelligence model: `traffic_tier`, `traffic_trajectory`, `referring_domains`, `spam_risk`, `maturity_years`) and `get_domain_metrics(domain)` abstract method to `SearchDataProvider` ABC.
- `app/providers/implementations/dataforseo.py` — Implemented `get_domain_metrics()`: maps DataForSEO Domain Overview (traffic signals, trajectory, domain age) and Backlinks Summary (referring domains, spam score inverted to 0–1 clean scale) to `DomainMetrics`. Falls back gracefully if either API call fails.
- `docs/intelligence-architecture.md §9.2` — Synced both table schemas to match implementation: `page_analyses` status now shows full 10-state machine; `opportunities` table fully rewritten to match approved IDE design (9-state machine, `evaluation_mode`, `mode_b_subtype`, `inferred_section`, `investment_score`, `cluster_scores`, `confidence_ceiling`, `InvestmentVerdict` schema reference, `started_at`, `failed_reason`, `data_quality`).

### Test status
59 passing, 0 failing. Provider interface change is backward-compatible — existing call sites unchanged.

---

## 2026-06-27 — ContentSignals: planned post-Sprint 3 enhancement documented

### Added
- `intelligence-architecture.md §3.1b` — ContentSignals future enhancement: planned extension to the existing summarization stage that adds structured content signals (subtopics covered/missing, entity coverage, depth, expert attribution, original data, structural completeness) alongside the current prose `PageSummary`. Documents design intent, schema sketch, downstream consumers, and implementation trigger (post-Sprint 3 verdict audit).
- `decisions.md` — Decision entry: ContentSignals deferred to post-Sprint 3, with reasoning, alternatives considered, and implementation trigger.

### Unchanged
Current summarization implementation is unmodified. No code changes.

---

## 2026-06-27 — IDE Implementation Design

### Added
- `docs/ide-implementation-design.md` — Complete pre-Sprint-3 design for the Investment Decision Engine. Covers: 9-step execution flow, state machine (9 states), data flow between all 6 pipeline components, hard exclusion gate H1–H5 placement and logic, Mode A vs Mode B divergence and convergence points, full scoring formula (clusters + risk multiplier + editorial cap + outcome tiers), LLM/deterministic interaction invariant, failure handling per component, sequence diagrams for Mode A / Mode B / gate-triggered exit, migration 0003 schema, 8 new required files, and 8 documented risks with mitigations.

### Status
Awaiting user review and approval. No Sprint 3 code written.

---

## 2026-06-27 — Sprint 2: Final closure

### Added
- `tests/test_pipeline_e2e.py` — 7 E2E integration tests: happy path (all 8 state transitions verified), crawl failure → failed, missing page record, page crawl None, plus 3 Celery smoke tests (task registered, callable, module in include list)

### Modified
- `pyproject.toml` — added `[dependency-groups]` dev section (uv-native format) so `uv run pytest` works without `--extra dev`; `uv.lock` updated

### Sprint 2 status: COMPLETE
59 tests passing, 0 failing.

---

## 2026-06-25 — Sprint 2: Analysis Pipeline (Part 2)

### Added
- `app/pipeline/readiness.py` — Readiness LLM worker: rules-based fast-fail (no-crawl, <200 words), Claude Haiku forced tool call, Pydantic validation with one retry, deterministic confidence override
- `app/pipeline/bottleneck.py` — Bottleneck LLM worker: Claude Sonnet 4.6, full competitive context in prompt, validation layer, deterministic confidence override
- `app/pipeline/orchestrator.py` — Celery task `serpnex.run_analysis`: 10-state machine, DB writes on each transition, Redis pub/sub progress events, `enqueue_analysis()` public API
- `app/api/v1/analysis.py` — Analysis API: `POST /analyses` (enqueue), `GET /analyses/{id}` (poll), `GET /analyses/{id}/stream` (SSE real-time progress)
- `tests/test_confidence.py` — 15 tests covering confidence scoring model and floor rules
- `tests/test_validation.py` — 8 tests covering readiness and bottleneck business logic validation
- `tests/test_summarizer.py` — 9 tests covering metadata extraction and summarize_page with retry

### Modified
- `app/main.py` — registered analysis router
- `app/worker/celery_app.py` — added `app.pipeline.orchestrator` to task include list

### Test status
32 tests passing, 0 failing.

---

## 2026-06-24

### Added
- `/docs/intelligence-architecture.md` — Complete 12-section intelligence architecture document covering system design, data sources, analysis pipeline, LLM architecture, prompt design, output schemas, validation, confidence scoring, database schema, cost modeling, API recommendations, and MVP scope
- `/docs/decisions.md` — Decision log with full rationale for all major architecture choices
- `/docs/progress.md` — Progress tracker
- `/docs/changelog.md` — This file
- `/docs/` directory created

### Status
Pre-implementation. No application code written. Architecture document pending review.

---

## 2026-06-24 (continued)

### Added
- `/docs/bottleneck-validation-plan.md` — 10-URL manual validation protocol for Bottleneck prompt quality. Includes URL archetype distribution, manual data-gathering procedure, 6-dimension scoring rubric, per-verdict evaluation sheet, Go/Conditional Go/No-Go criteria, failure mode taxonomy with fixes, reference example of good vs. poor verdict, and API call reference (Appendix B).
- `decisions.md` updated with validation gate decision

### Status
Sprint 1 gated on Bottleneck validation Go decision. Validation estimated 4-6 hours to complete.

---

## 2026-06-24 (continued)

### Added
- `/docs/prompts/bottleneck-v1.md` — Production-candidate Bottleneck prompt. System prompt with 6 rules (anti-bias, specificity, no fabrication, confidence calibration, single primary, tool-only output). User message template with 24 defined variables and compression rules. Full tool schema (JSON). Prompt changelog.
- `/docs/validation/evaluation-package.md` — Complete 10-URL evaluation execution package. Pre-flight checklist, 7-step per-URL instructions, API call script, 10 URL worksheets with data + scoring fields, aggregate tracker, Go/Conditional Go/No-Go decision checklist, final sign-off block.
- `/docs/validation/assumptions.md` — 19 documented assumptions across 8 categories: model behavior, keyword identification, competitor identification, authority proxy, content compression, ground truth proxy, taxonomy, and evaluation methodology. Each includes falsification criteria, consequence, and risk level.
- `/docs/prompts/` directory created
- `/docs/validation/` directory created
- `decisions.md` updated with 3 new entries: tool use decision, compression decision, taxonomy lock decision

### Status
All pre-validation documents complete. Validation ready to execute. No application code written.

---

## 2026-06-25 — Sprint 1: Foundation

### Added — Application Code (first code in the project)

**Project scaffold:**
- `pyproject.toml` — Python 3.11, dependencies: FastAPI, Celery, SQLAlchemy, Alembic, Pydantic, httpx, Google APIs, Anthropic SDK; dev extras: pytest, ruff, mypy
- `Dockerfile` — Python 3.11-slim image
- `docker-compose.yml` — PostgreSQL 15, Redis 7, API service, Celery worker
- `.env.example` — all required environment variables documented

**Database:**
- `app/db/models.py` — SQLAlchemy ORM models: `Workspace`, `User`, `Site`, `Page`, `PageAnalysis`
- `app/db/session.py` — async SQLAlchemy session factory; `get_db()` FastAPI dependency
- `alembic/` — Alembic migrations setup
- `alembic/versions/0001_initial_schema.py` — initial migration: all 5 core tables with indexes

**Provider abstraction layer (permanent architectural rule):**
- `app/providers/base/crawler.py` — `CrawlerProvider` ABC + `CrawlResult` + `CrawlError`
- `app/providers/base/search_data.py` — `SearchDataProvider` ABC + `SerpResult` + `BacklinkMetrics` + `SearchDataError`
- `app/providers/base/llm.py` — `LLMProvider` ABC + `LLMMessage` + `ToolDefinition` + `LLMResponse` + `LLMError`
- `app/providers/base/gsc.py` — `GSCProvider` ABC + `GSCPageMetrics` + `GSCProperty` + `GSCAuthUrl` + `GSCError`

**Provider implementations:**
- `app/providers/implementations/firecrawl.py` — `FirecrawlCrawlerProvider`
- `app/providers/implementations/dataforseo.py` — `DataForSEOSearchDataProvider`
- `app/providers/implementations/anthropic.py` — `AnthropicLLMProvider`
- `app/providers/implementations/google_gsc.py` — `GoogleGSCProvider`
- `app/providers/registry.py` — config-driven LRU-cached provider singletons

**API and worker:**
- `app/main.py`, `app/api/v1/health.py`, `app/api/v1/gsc.py`, `app/worker/celery_app.py`

**Tests:** 5/5 pass (provider abstraction contracts + health endpoint)

### Status
Sprint 1 complete. No business logic anywhere. Sprint 2 (analysis pipeline) can begin.

---

## 2026-06-25 (continued)

### Added / Updated — Dual-Mode Architecture
- `decisions.md` — New entry: "Investment Decision Engine: Dual-Mode Architecture" — documents the two-mode architecture (Mode A: Specific Placement, Mode B: Guest Post Opportunity), automatic mode detection logic (URL classification heuristics, default to Mode B on ambiguity), Category URL as a first-class input, domain-only section inference (sitemap + navigation + Haiku topic matching), signal approximation in Mode B (averaged across sampled articles), confidence ceiling rules by mode (High/Medium/Low), mode_qualifier field requirement for Mode B verdicts, and the decision to use one engine rather than two.
- `intelligence-architecture.md §3.5` — Complete rewrite: full dual-mode pipeline with mode detection pseudocode, Mode A (single page) and Mode B (Category URL + Domain-only sub-types) data collection, signal approximation comparison table, section inference steps, shared hard exclusion gates, shared cluster aggregation formulae, shared output tiers, and reference to prompt `evaluation_mode` parameter.
- `intelligence-architecture.md §6.3` — InvestmentVerdict schema updated: 7 new fields (`evaluation_mode`, `mode_b_subtype`, `sampled_article_urls`, `inferred_section`, `confidence_ceiling`, `mode_qualifier`, `mode_detection_note`). Business logic validation rules updated with mode-specific rules.
- `intelligence-architecture.md §7.2` — Business logic validation for Opportunity module updated: confidence ceiling enforcement documented as the primary post-LLM rule.
- `intelligence-architecture.md §8.3` — Confidence weights updated: crawl signal description now reflects Mode A vs. Mode B collection. Confidence ceiling table by mode added. Ceiling enforcement documented as a hard structural constraint.
- `validation/assumptions.md` — Category 10 added (Investment Decision Engine assumptions): A21 (mode detection accuracy — Medium risk) and A22 (section inference quality — Medium-low to Medium risk). Registry summary updated; duplicate A19 entry corrected. Locking note updated to clarify A21/A22 are not bound to the Bottleneck validation cycle.
- `progress.md` — IDE architecture status updated to "finalized, awaiting Sprint 3 implementation."

### Status
Full IDE architecture complete and committed. Bottleneck validation ready to execute. No application code written.

---

## 2026-06-25

### Added / Updated
- `decisions.md` — New entry: "Investment Decision Engine Design" — full specification of the IDE replacing the original 4-dimension Opportunity Evaluation model. Covers: 5 hard exclusion gates, 14 scored signals across Placement-Page (P1–P5) and Domain-Level (D1–D9) tiers, 4 signal clusters (Relevance/Authority/Quality/Risk), cluster aggregation formulas, Risk as a score multiplier, Editorial Integrity composite signal with 4 sub-signals and a 0.30 score cap at Investment Score 45, Confidence model with required/important/optional signal classification, 4 output tiers (Recommended / Recommended with Conditions / Not Recommended / Insufficient Data), conflicting signal resolution rules, and placement-page priority architecture (domain-only evaluation returns `insufficient_data`).
- `intelligence-architecture.md` §3.5 — Complete replacement: Opportunity Evaluation phase redesigned as the Investment Decision Engine. Documents gated architecture, both signal tiers, cluster aggregation formulae, processing steps, and output tiers.
- `intelligence-architecture.md` §5.5 — Updated: Opportunity prompt design redesigned for 2-call Haiku architecture. Documents Call 1 (content classification + signal extraction) and Call 2 (investment verdict assembly). Editorial Integrity sub-signals defined. Anti-bias rule (mirrors Bottleneck Rule 2) documented. `docs/prompts/opportunity-v1.md` identified as required deliverable before Sprint 3.
- `intelligence-architecture.md` §6.3 — Complete replacement: `OpportunityVerdict` schema replaced by `InvestmentVerdict` with new models: `InvestmentOutcome`, `HardExclusionGate`, `PlacementFeasibility`, `PlacementPageSignals`, `ClusterScores`, `EditorialIntegrityScores`. Business logic validation rules added.
- `intelligence-architecture.md` §8.3 — Updated: Opportunity confidence weights redesigned for IDE signal architecture (6 signals with required/important/optional classification).
- `intelligence-architecture.md` §4.1 — LLM task table updated: Opportunity evaluation split into 2 Haiku calls (~$0.005 + ~$0.004).
- `intelligence-architecture.md` §10.2 — Opportunity evaluation cost updated: ~$0.010 (up from ~$0.008) reflecting IDE's additional crawling and second Haiku call.
- `progress.md` — IDE design recorded as completed (pending approval); next steps updated.

### New required deliverables identified
- `docs/prompts/opportunity-v1.md` — Investment Decision Engine prompt (2 Haiku calls; required before Sprint 3)

### Status
IDE design complete. Pending review and approval before Sprint 3 implementation. No application code written.

---

## 2026-06-24 (continued)

### Added / Updated
- `decisions.md` — New entry: "Automated Content Extraction Pipeline" — documents the decision to replace manual content summaries with an automated Firecrawl + Haiku 4.5 summarization stage, the tradeoffs, the validation gap it creates, and the required mitigations.
- `validation/assumptions.md` — A12 and A13 updated with production notes. New assumption A20 added (Category 9 — Production pipeline): automated summaries must be validated as functionally equivalent to human summaries before production launch. Pipeline Validation procedure defined. Registry updated to 20 assumptions.
- `intelligence-architecture.md` — Pipeline state machine updated: new `SUMMARIZING_CONTENT` state and `SUMMARIES_READY` state added between data collection and analysis. New §3.1a documents the summarization stage (model, input, output, prompt requirements, validation gate, cost, latency). LLM task table updated with 2 new Haiku summarization rows. §10.2 cost table updated: full page analysis now ~$0.054 (up from ~$0.050). `page_analyses` schema updated: new `summarization_prompt_version` column and `content_summaries JSONB` column. Status enum updated to include `summarizing_content`.

### New required deliverables identified
- `docs/prompts/summarize-page-v1.md` — Summarization prompt (required before Sprint 2)
- Pipeline Validation (3–5 URLs, human vs. automated summary comparison) — required before production launch

### Status
Documentation updated. Validation ready to execute. Summarization prompt is a Sprint 2 prerequisite.
