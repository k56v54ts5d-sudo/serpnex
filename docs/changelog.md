# Changelog

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
