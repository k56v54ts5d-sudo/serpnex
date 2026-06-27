# Progress

Current phase: **Sprint 2 — COMPLETE**  
Last updated: 2026-06-27

---

## Completed

### Bottleneck Prompt v1 + Evaluation Package (2026-06-24)
- `/docs/prompts/bottleneck-v1.md` — Production-candidate prompt, ready to use:
  - System prompt with 6 explicit rules (anti-link-bias, specificity, no fabrication, confidence calibration, single primary, tool-only output)
  - User message template with all `{variable}` placeholders defined
  - Variable definitions and compression rules for all 24 input fields
  - Tool schema (JSON) ready to paste into API call
  - Prompt changelog
- `/docs/validation/evaluation-package.md` — Complete execution package:
  - Pre-flight checklist
  - 7-step execution instructions per URL
  - API call script (copy-paste Python)
  - All 10 URL worksheets with data gathering + scoring fields
  - Aggregate results tracker (score table, per-dimension summary, failure mode log)
  - Go / Conditional Go / No-Go decision checklist
  - Final decision record (sign-off block)
- `/docs/validation/assumptions.md` — 19 documented assumptions across 8 categories:
  - Model behavior (A1–A5)
  - Keyword identification (A6–A7)
  - Competitor identification (A8–A9)
  - Authority proxy (A10–A11)
  - Content compression (A12–A13)
  - Ground truth proxy (A14–A15)
  - Taxonomy (A16–A17)
  - Evaluation methodology (A18–A19)

### Intelligence Architecture (2026-06-24)
- Read and analyzed product design brief in full
- Produced `/docs/intelligence-architecture.md` covering all 12 sections
- Produced `/docs/decisions.md`, `/docs/progress.md`, `/docs/changelog.md`

---

## Sprint 1 — Complete (2026-06-25)

**Foundation — infrastructure only, no business logic.**

- Project scaffold: FastAPI + Celery + PostgreSQL + Redis + Docker Compose
- Database schema: `workspaces`, `users`, `sites`, `pages`, `page_analyses` (Alembic migration 0001)
- Provider abstraction layer: 4 ABCs (`CrawlerProvider`, `SearchDataProvider`, `LLMProvider`, `GSCProvider`)
- Provider implementations: Firecrawl, DataForSEO, Anthropic, Google GSC
- Provider registry: config-driven, LRU-cached singletons
- API: `GET /health`, `GET /auth/gsc/connect`, `GET /auth/gsc/callback`
- Celery worker: configured, no tasks registered yet
- Tests: 5/5 pass

**Architectural rule locked:** business logic never imports a concrete provider directly.

---

## Sprint 2 — In Progress (2026-06-25)

**Analysis pipeline — all core components written, tests passing.**

### Completed in Sprint 2

- **Migration 0002** — expanded `page_analyses` schema: 15 new columns, status values migrated to lowercase snake_case, new indexes
- **`app/pipeline/confidence.py`** — deterministic confidence scoring (§8): signal weights, `calculate_confidence`, `apply_confidence_floors` with floor rules
- **`app/pipeline/validation.py`** — business logic validation (§7.2): `validate_readiness_verdict`, `validate_bottleneck_verdict`
- **`app/pipeline/cache.py`** — Redis TTL cache: per-namespace TTLs, `APICache`, `get_cache` singleton
- **`app/pipeline/collectors.py`** — data collection orchestration (§3.2): `AnalysisContext`, 4-phase parallel collection
- **`app/pipeline/summarizer.py`** — content summarization stage (§3.1a): deterministic metadata extraction, Claude Haiku summarization with retry
- **`app/pipeline/readiness.py`** — Readiness LLM worker (§3.3, §5.3): rules-based fast-fail, Claude Haiku, validation + confidence floors
- **`app/pipeline/bottleneck.py`** — Bottleneck LLM worker (§3.4, §5.4): Claude Sonnet 4.6, validation + confidence floors
- **`app/pipeline/orchestrator.py`** — Celery task + state machine + Redis pub/sub progress events (10 states)
- **`app/api/v1/analysis.py`** — SSE endpoint: `POST /analyses`, `GET /analyses/{id}`, `GET /analyses/{id}/stream`
- **`docs/prompts/summarize-page-v1.md`** — prompt specification for summarization stage
- **Tests**: 32 passing — confidence scoring (15 tests), validation (8 tests), summarizer (9 tests)

### Sprint 2 — COMPLETE (2026-06-27)

All remaining Sprint 2 work completed:

- **`tests/test_pipeline_e2e.py`** — 7 E2E integration tests covering: happy path state transitions, crawl failure → failed state, missing page record, page crawl None (INSUFFICIENT_DATA), and 3 Celery registration smoke tests
- **`pyproject.toml`** — dev dependencies properly declared in both `[project.optional-dependencies]` and `[dependency-groups]` (uv-native format); `uv run pytest` works without flags
- **Self-review complete** — no architectural deviations, no shortcuts, no direct vendor imports

**Known deferred integration point:** `gsc_tokens` / `gsc_property` are hardcoded `None` in the orchestrator. GSC data collection requires the OAuth flow + token persistence layer (Sprint 3 scope). Not a bug — by design.

**Final test count: 59 passing, 0 failing.**

## In Progress

### IDE Implementation Design (2026-06-27)

`docs/ide-implementation-design.md` written and awaiting user approval. Covers:
- Complete 9-step execution flow with state machine (queued → detecting_mode → inferring_section → collecting_data → classifying_signals → computing_score → assembling_verdict → complete / failed)
- Exact processing order per mode (Mode A, Mode B/category, Mode B/domain)
- Data flow diagram between all 6 components (collector, gates, LLM call 1, scorer, LLM call 2, validation)
- Hard exclusion gates H1–H5 with evaluation order and trigger conditions
- Mode A vs Mode B divergence (mode detection, section inference, crawl targets, prompt variation) and convergence (gates, scoring, LLM calls, validation)
- Full scoring formula: Relevance, Authority, Quality clusters + Risk multiplier + editorial integrity cap + outcome tier thresholds
- LLM signal extraction → deterministic scoring → LLM verdict assembly interaction (LLM cannot change the outcome tier)
- Failure handling: per-component, `insufficient_data` vs `failed` distinction, retry protocol
- Sequence diagrams for Mode A, Mode B/domain, and gate-triggered exit
- Migration 0003: `opportunities` table schema
- All new files required (8 pipeline files + migration + schemas + tests)
- 8 risks documented with mitigations

**Status: Awaiting review and approval. No Sprint 3 code written.**

---

## Completed (continued)

### Investment Decision Engine — Full Architecture (2026-06-25)

IDE design fully specified and documented across two design sessions:

**IDE core design:**
- 5 hard exclusion gates (H1–H5)
- 14 signals: Placement-page tier (P1–P5) + Domain-level tier (D1–D9)
- 4 signal clusters: Relevance, Authority, Quality, Risk
- Cluster aggregation formulae with risk as a multiplier (not an additive cluster)
- Editorial Integrity composite signal (4 sub-signals; score cap at 0.30 → Investment Score max 45)
- Conflicting signal resolution rules (4 defined patterns)
- 4 output tiers: `recommended | with_conditions | not_recommended | insufficient_data`

**Dual-mode architecture (finalized):**
- Mode A: Specific Placement Evaluation (placement URL → single page crawl → all P1–P5 from that page → confidence ceiling: High)
- Mode B: Guest Post Opportunity Evaluation (domain or category URL → sample 3–5 articles)
  - Mode B / Category URL sub-type → confidence ceiling: Medium
  - Mode B / Domain-only sub-type → section inference → confidence ceiling: Low
- Automatic mode detection from input URL (users never select mode)
- Category URLs are first-class inputs — no section inference needed when category is specified
- Domain-only: inference via sitemap + navigation + Haiku topic matching
- Single aggregation model, schema, validation layer, and output tier definitions across both modes
- Branching only at data collection step

**Documents updated:**
- `decisions.md`: 2 new entries (IDE design + dual-mode architecture)
- `intelligence-architecture.md`: §3.5 (full rewrite), §5.5 (mode-aware prompt notes), §6.3 (InvestmentVerdict schema with 7 new fields), §7.2 (mode-specific validation rules), §8.3 (confidence ceiling by mode), §4.1 (2 Haiku calls), §10.2 (updated opportunity cost ~$0.010)
- `validation/assumptions.md`: A21 (mode detection accuracy), A22 (section inference quality)

Status: **Architecture finalized. Awaiting Sprint 3 implementation.**

---

## Next Steps

1. **Approve or revise the IDE design** — review `docs/decisions.md` (2026-06-25 entry) and updated §3.5/§5.5/§6.3 in `docs/intelligence-architecture.md`
2. Run the 10-URL Bottleneck validation using `docs/validation/evaluation-package.md`
   - Complete Section 0 pre-flight checklist
   - Select and record 10 URLs + write all 10 hypotheses (Section 1) BEFORE gathering data
   - Work through all 10 URL worksheets (Section 3) — budget 4–6 hours total
   - Complete aggregate tracker (Section 4) and Go/No-Go decision (Section 5–6)
   - Record decision in `docs/decisions.md` and update this file
3. If Go: Sign up for DataForSEO and Firecrawl sandbox accounts, then begin Sprint 1
4. Before Sprint 3: Write `docs/prompts/opportunity-v1.md` — the IDE prompt (2 Haiku calls; mode-aware; follow `bottleneck-v1.md` as template for rigor and structure)

---

## Risks Flagged

See `/docs/intelligence-architecture.md §12.5` for the full risk register.

Top 3 pre-implementation risks:
1. LLM produces confidently wrong Bottleneck verdicts → manual QA of 50 verdicts before launch
2. SERP keyword identification fails for pages without GSC → content-based fallback needed
3. DataForSEO reliability issues delay analyses → retry logic and timeout handling required from Sprint 1
