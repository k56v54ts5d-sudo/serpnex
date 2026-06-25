# Bottleneck Validation — Documented Assumptions

**Document type:** Pre-validation assumption register  
**Date:** 2026-06-24  
**Scope:** All assumptions underlying the Bottleneck prompt (v1) and the 10-URL evaluation methodology  
**Status:** Locked before validation begins. Changes to assumptions after validation requires a new validation run.

---

## Purpose

Every decision in the prompt design and evaluation methodology rests on assumptions. Documenting them serves three purposes:

1. If the validation fails, the assumption list is the first place to look for root causes.
2. If results are surprising in either direction, the assumptions explain why the test may not generalize.
3. Post-launch, when real user data challenges a verdict, these assumptions tell us where to look for systemic bias.

Each assumption is documented with: what is assumed, why it was assumed, what would falsify it, and what the consequence of being wrong is.

---

## Category 1 — Model assumptions

### A1: Claude Sonnet 4 at temperature=0 produces deterministic or near-deterministic output

**What is assumed:** Running the same prompt with the same inputs at `temperature=0` will produce the same or functionally equivalent output across multiple runs.

**Why assumed:** Temperature=0 sets the sampling distribution to be maximally concentrated on the highest-probability token at each step. This is required for validation reproducibility — if two runs of the same URL produce different primary constraints, the evaluation cannot be trusted.

**What would falsify it:** Running the same completed prompt twice and receiving meaningfully different `primary_constraint` or `links_are_the_answer` values.

**Consequence of being wrong:** Evaluation scores are unreliable. The validation would need to be run 3× per URL and take the majority verdict. Prompt confidence intervals would need to be wider.

**Risk level:** Low. Anthropic's temperature=0 behavior is well-documented and consistent in practice. Small token-level variation can occur but does not typically change top-level categorization decisions.

---

### A2: Claude Sonnet 4 can follow complex, multi-rule system prompts reliably

**What is assumed:** The model reads and applies all six rules in the system prompt, not just the most recent or most salient one. In particular: Rule 2 (anti-link-bias) is applied even when the prompt signals — by the product's domain context — that link building is the user's goal.

**Why assumed:** Claude Sonnet-class models have demonstrated reliable instruction-following on structured multi-rule prompts in independent benchmarks. The concern is not instruction comprehension but instruction compliance when rules conflict with prior training associations.

**What would falsify it:** FM-2 (link bias) appearing on more than 1 of the 3 Archetype B URLs, indicating the model is preferring link authority as an answer because Serpnex is a link intelligence product.

**Consequence of being wrong:** The prompt's Rule 2 is insufficient. The fix is either (a) adding a few-shot example of a correct Archetype B verdict, or (b) restructuring the prompt to not identify the product as link-focused in the system prompt, instead identifying it as a "ranking bottleneck diagnostic tool."

**Risk level:** Medium. This is the failure mode most likely to appear. Documented in the validation plan as FM-2.

---

### A3: The tool use / function calling schema enforces output structure reliably

**What is assumed:** When `tool_choice: {"type": "tool", "name": "analyze_bottleneck"}` is set, the model will always produce output in the tool schema format, not in prose. Schema fields with enum constraints will only contain valid enum values.

**Why assumed:** Anthropic's tool use implementation at Sonnet level is well-tested and documented. The `tool_choice` forced call mode eliminates the ambiguity of "you may or may not call the tool."

**What would falsify it:** Any URL producing output outside the tool call (prose in the response content), or enum fields containing values not in the schema (e.g., `"moderate"` instead of `"medium"`).

**Consequence of being wrong:** Schema compliance failures appear (FM-4). The fix is either (a) strengthening the Rule 6 instruction, or (b) simplifying enum sets to reduce the model's choices.

**Risk level:** Low-medium. Forced tool use is reliable at Sonnet level; the risk is in complex nested schemas where the model might produce structurally valid but semantically wrong field values (e.g., assigning weights that don't sum to 1.0).

---

### A4: The 2,000 token output budget is sufficient for complete verdicts

**What is assumed:** All required fields — including `constraint_breakdown` with up to 3 entries and all `maxLength` character fields filled to their limits — fit within 2,000 output tokens.

**Why assumed:** Rough calculation: 6 top-level fields averaging 50 tokens each = 300 tokens. constraint_breakdown with 3 entries at ~60 tokens each = 180 tokens. Total: ~480 tokens. 2,000 token limit gives 4× headroom.

**What would falsify it:** Output truncation appearing in any URL test (response ending mid-field).

**Consequence of being wrong:** Increase `max_tokens` to 3,000. No prompt change needed.

**Risk level:** Very low. The schema is not large enough to approach 2,000 tokens under any realistic input.

---

### A5: Manually gathered data is sufficient signal for prompt quality validation

**What is assumed:** The validation is testing reasoning quality, not data precision. Approximate RD counts from free tools, manually estimated word counts, and human-written content summaries are sufficient inputs to evaluate whether the model reasons correctly.

**Why assumed:** The question being answered is: "does the model correctly identify the primary constraint given a realistic set of signals?" Not: "does the model produce correct verdicts when given perfect data?" Imprecise data is a feature of this test, not a bug — it reflects real-world conditions.

**What would falsify it:** If multiple verdicts fail specifically because the manually-gathered data was so imprecise that the model could not distinguish a link-limited page from a content-limited page. For example, if two pages appear identical in the prompt because the content summaries were too generic.

**Consequence of being wrong:** Data gathering instructions in Section 3 of the evaluation package need to be more specific, especially for content summaries.

**Risk level:** Medium. The quality of the content summaries is the highest-variance input in the manual process. The evaluation package instructs evaluators to be descriptive rather than evaluative — but this instruction can be ignored. Evaluator discipline is required.

---

## Category 2 — Keyword identification assumptions

### A6: A single "primary keyword" adequately represents the page's ranking challenge

**What is assumed:** Most pages have one dominant keyword cluster that accounts for the majority of their relevant impressions. Analyzing the page against that keyword's top 3 results is representative of the competitive landscape the page faces.

**Why assumed:** For the purposes of bottleneck diagnosis, the competitive environment is defined by the query the page is most trying to rank for. Even if a page ranks for 500 keywords, the primary keyword captures the strategic intent.

**What would falsify it:** A page where the top-impression keyword is different from the keyword the page owner actually cares about, leading to the model diagnosing a bottleneck that is irrelevant to the real business goal.

**Consequence of being wrong:** In production, the system must allow users to override the detected primary keyword. At validation time, if a URL's GSC primary keyword appears misaligned with the page's purpose, select a more appropriate keyword manually and note the override.

**Risk level:** Medium. This is a real limitation. URL selection guidance says to pick pages in positions 5–30 for the keyword — this implicitly filters for cases where the primary keyword is a reasonable match.

---

### A7: GSC average position is a reliable proxy for where the page ranks for the primary keyword

**What is assumed:** GSC average position for the primary keyword, averaged over 90 days, reflects the page's actual organic ranking well enough to establish the competitive gap.

**Why assumed:** GSC is the most authoritative first-party data source for this signal. 90-day averaging smooths out ranking volatility and SERP test periods.

**What would falsify it:** A page that ranks dramatically differently across devices, geographies, or in-SERP features — where the "average" position masks meaningful ranking variance.

**Consequence of being wrong:** For validation purposes, the consequences are minor: the model receives a position signal that is rougher than ideal, which may slightly affect confidence calibration. In production, consider segmenting GSC data by device type if mobile vs. desktop position variance is material.

**Risk level:** Low. Position averaging is standard practice. The validation is not sensitive to ±2 position accuracy.

---

## Category 3 — Competitor identification assumptions

### A8: The top 3 organic non-ad, non-local-pack results in an incognito Google search represent the competitive landscape

**What is assumed:** What appears in the first 3 organic positions in an incognito search from the evaluator's location is a reasonable proxy for the competitive set the target page is competing against.

**Why assumed:** These are the pages Google is currently ranking above the target. They are the direct competitive comparison the bottleneck analysis requires.

**What would falsify it:** Heavy localization, personalization, or freshness effects that produce a SERP meaningfully different from what the target page's typical audience sees.

**Consequence of being wrong — validation:** If the evaluator is in a different geography from the target page's primary audience (e.g., evaluating a US page from Dubai), the SERP may show different results. Use a VPN set to the target audience's geography for Archetype A/B/C URLs where intent may be geo-sensitive.

**Consequence of being wrong — production:** The pipeline must use a geo-targeted SERP API call matching the page's primary market. This is documented in the intelligence architecture. At validation, note if geo-targeting is likely to matter for any selected URL.

**Risk level:** Low-medium. For most B2B and general-information keywords, SERP results are broadly consistent across major markets. For local-intent or geo-specific queries, this assumption breaks.

---

### A9: Three competitors is sufficient to identify the primary bottleneck

**What is assumed:** The pattern of content quality, format, and authority across the top 3 results is representative of why the target page is underperforming. Looking at 5 or 10 competitors would not materially change the primary constraint identified.

**Why assumed:** The top 3 results are what Google has chosen to rank above the target. They set the bar the target must clear. Analyzing beyond 3 increases data gathering cost without proportionally improving diagnostic signal for the primary bottleneck.

**What would falsify it:** A case where #1-3 use different formats and the model fails to identify the dominant pattern, producing a noisy or hedged verdict. In practice, if competitors 1-3 split across two intent types, a Bottleneck verdict is inherently ambiguous.

**Consequence of being wrong:** In ambiguous cases, the validation will surface this as low confidence output, which is the correct behavior. No prompt change is needed. The URL selection guidance already recommends Archetype C (mixed) to test exactly this.

**Risk level:** Low.

---

## Category 4 — Authority proxy assumptions

### A10: Referring domain count is a sufficient proxy for page-level link authority

**What is assumed:** The number of unique referring domains to a URL (not the domain) is a good enough proxy for that URL's link authority to enable meaningful gap analysis.

**Why assumed:** Referring domain count is the most accessible, consistently measured, and well-understood backlink metric. It is less manipulable than raw link count and better correlated with ranking ability than domain-level metrics alone.

**What would falsify it:** A case where two pages have similar RD counts but very different actual authority (e.g., target has 50 RDs from high-authority domains, competitor has 50 RDs from low-authority domains). The model would see the same RD count and potentially misclassify the authority gap.

**Consequence of being wrong:** Link authority gap analysis is less precise than Ahrefs' URL Rating or Moz's Page Authority. For the purposes of identifying the direction of the authority gap (is the target materially behind?), RD count is sufficient. For precise gap quantification in production, URL Rating should supplement RD count.

**Risk level:** Low for gap direction; medium for gap magnitude. The prompt asks the model to identify which constraint is primary, not to estimate exact numerical lift. Direction accuracy is what matters here.

---

### A11: Backlink data from free tools (Ahrefs free, Moz, Semrush) is accurate enough for this validation

**What is assumed:** Free-tier backlink data from Ahrefs, Moz, or Semrush provides RD counts within ±50% of the true value, which is sufficient for identifying order-of-magnitude authority gaps (e.g., "target has ~40 RDs vs. competitor with ~400 RDs" is meaningful even if both numbers are ±50%).

**Why assumed:** Free tools provide sampling-based data that undercount the full link profile. However, the undercount is roughly proportional across domains — if tool X shows 40 RDs for the target and 400 for the competitor, the true ratio is approximately 1:10 regardless of the exact counts.

**What would falsify it:** A case where tool data significantly misrepresents the ratio. For example, showing 200 target RDs vs. 300 competitor RDs (implying a modest gap) when the true counts are 200 target vs. 5,000 competitor (a severe gap).

**Consequence of being wrong:** The model receives a misleadingly small authority gap and classifies a link-authority-primary page as content-primary. This would produce a false negative on Archetype A URLs.

**Risk level:** Low-medium. The undercount effect is generally proportional. The risk is highest for very large domains (10,000+ RDs) where free tools may severely undercount. Mitigate by noting which tool was used and flagging any URL where the tool count seems suspiciously low for an obviously authoritative domain.

---

## Category 5 — Content summary compression assumptions

### A12: A 100–150 word human-written content summary captures enough signal for LLM bottleneck reasoning

**What is assumed:** A trained evaluator reading a page and writing a 100–150 word descriptive summary provides enough content signal for the model to reason about content depth, format, and intent alignment — without sending full HTML or extensive excerpts.

**Why assumed:** The model needs to compare the page's content approach to competitors, not audit its full content. The summary captures the structural and topical signals that drive the comparison. Full HTML would be token-expensive and would overwhelm the analysis signal with markup noise.

**What would falsify it:** A verdict that incorrectly classifies a content-limited page as link-limited because the summary failed to convey how shallow the content was, OR incorrectly classifies a link-limited page as content-limited because the summary made the content sound less substantial than it is.

**Consequence of being wrong:** Content summary quality is the variable with the highest evaluator-to-evaluator variance. If summaries are consistently too positive (making thin pages sound richer than they are), the model will systematically under-diagnose content bottlenecks.

**Risk level:** Medium-high. This is the single most evaluator-dependent input in the process. The evaluation package instructions ("be descriptive, not evaluative") are the mitigation. A second reviewer seeing the same output can flag cases where the summary seems biased.

**Production note (2026-06-24):** In production, content summaries are generated automatically by a crawl-and-summarize pipeline (Firecrawl + Claude Haiku 4.5), not written by hand. This assumption applies only to the 10-URL prompt validation. A separate **Pipeline Validation** (see A20) is required before production launch to confirm that automated summaries are functionally equivalent to human-written ones as Bottleneck prompt inputs. The summarization prompt must encode the same compression rules defined in `docs/prompts/bottleneck-v1.md §3` and must explicitly prohibit evaluative language.

---

### A13: The summary author's judgment about format (guide / listicle / comparison / etc.) is consistent with how the model interprets those labels

**What is assumed:** When the evaluator calls a page a "guide" and a competitor a "listicle," the model interprets those labels in a way that enables meaningful comparison of format differences and their search-intent implications.

**Why assumed:** These are standard SEO content taxonomy terms with well-understood meanings that the model has encountered extensively in training data.

**What would falsify it:** A verdict that fails to draw an intent-mismatch conclusion even when the format difference between target and competitors is stark — suggesting the model is not using the format labels to reason about intent.

**Consequence of being wrong:** Add a brief format definition legend to the user message template, mapping each label to the searcher intent it typically serves. Example: "listicle → informational/navigational, typically wants a ranked list of options; landing page → commercial, typically wants a vendor-specific solution."

**Risk level:** Low. Format label interpretation is well within Claude Sonnet's capability.

**Production note (2026-06-24):** In production, format labels are assigned by the automated summarization pipeline. The summarization prompt must be explicit about the same label taxonomy. If the summarizer uses inconsistent labels (e.g., calling a comparison table a "guide"), the Bottleneck model's intent-mismatch reasoning degrades. Format label consistency is a required acceptance criterion for the Pipeline Validation.

---

## Category 6 — Ground truth assumptions

### A14: Expert judgment is a valid proxy for ground truth in the absence of outcome data

**What is assumed:** A verdict that a qualified SEO strategist evaluates as "correct and specific" is more likely to be actually correct than a verdict the strategist finds implausible or generic. In the absence of longitudinal A/B test data, expert judgment is the best available ground truth.

**Why assumed:** No outcome data exists before the product is built and deployed. Expert judgment is the standard proxy used in content quality evaluation, search quality rater guidelines, and similar applied ML settings. It is imperfect but the best available option.

**What would falsify it:** A subsequent longitudinal study showing that verdicts experts rated "correct" were not predictive of actual ranking improvements, while verdicts they rated "incorrect" were.

**Consequence of being wrong:** This is a known limitation of all pre-deployment LLM quality evaluation. The mitigation is the Campaigns/Tracking module (outcome data) described in the intelligence architecture. Once outcome data exists, the confidence model and prompt can be validated against actual results.

**Risk level:** Inherent, cannot be eliminated at this stage. Accepted.

---

### A15: The evaluator can remain neutral between their pre-test hypothesis and the model's verdict

**What is assumed:** The evaluator can fairly assess whether the model's verdict is correct even when it agrees or disagrees with their pre-test hypothesis. Specifically: if the model reaches a surprising conclusion, the evaluator will consider whether the model might be right before defaulting to "it's wrong."

**Why assumed:** The pre-test hypothesis requirement is designed to create a separation between evaluation and confirmation. A professional evaluator should be able to hold both simultaneously.

**What would falsify it:** Systematic score inflation when the model agrees with the evaluator's hypothesis and deflation when it disagrees, detectable by comparing scores when hypothesis = match vs. hypothesis = mismatch.

**Consequence of being wrong:** Results are biased toward confirming the evaluator's prior beliefs. Mitigation: the second reviewer (blind scoring) requirement in the evaluation package. If only one reviewer is available, the evaluator should flag all cases where the hypothesis did not match and have those reviewed by another person.

**Risk level:** Medium if single evaluator only. Low if two independent evaluators score separately.

---

## Category 7 — Taxonomy assumptions

### A16: Five constraint categories cover all meaningful ranking bottlenecks for the pages being tested

**What is assumed:** Every meaningful ranking bottleneck for a non-local, non-YMYL, English-language page in position 5–30 falls into one of: `link_authority`, `content_depth`, `intent_mismatch`, `internal_links`, `technical`.

**Why assumed:** This taxonomy was designed to cover the decision tree a senior SEO strategist would use. The five categories map to the five actionable levers available: earn links, improve content, change the page's approach, improve internal linking, fix technical issues.

**What would falsify it:** A URL where the evaluator's expert judgment is that the real bottleneck is something not capturable by any of the five categories. Possible examples:
- E-E-A-T or brand authority signals (the page lacks author credentials or brand recognition that competitors have)
- Language/locale mismatch (page is US English, ranking for a keyword with heavy UK search intent)
- Structural SEO issues that don't fit "technical" (e.g., the page is a subdomain when it should be a subfolder)

**Consequence of being wrong:** The verdict forces the model into an imprecise categorization, reducing specificity scores. In production, this signals a need to expand the taxonomy. Document any cases where the five-category taxonomy felt insufficient in the validation notes.

**Risk level:** Low-medium for the pages selected in this validation (deliberately filtered to avoid edge cases). Higher for YMYL, local, or highly specialized content — categories excluded from the MVP test set.

---

### A17: `links_are_the_answer` is a binary flag with sufficient precision

**What is assumed:** A boolean (true/false) is the right data type for "should this page build links?" at the verdict level. The nuance (e.g., "yes, but only after fixing the content") is captured in the `recommended_action` and `constraint_breakdown` fields.

**Why assumed:** The product's design principle is *Decision → Reason → Action*. The decision must be binary to be actionable. The reason and action fields provide the nuance.

**What would falsify it:** A set of verdicts where evaluators consistently find the binary flag misleading — for example, where `links_are_the_answer = false` on a page that does need links eventually (just not now), causing confusion.

**Consequence of being wrong:** Change `links_are_the_answer` to a three-value field: `primary_action` with values `fix_content_first` / `build_links_now` / `fix_and_link_simultaneously`. This would require a schema version bump and prompt revision.

**Risk level:** Low. The boolean maps cleanly to the product's UX — the Bottleneck verdict screen displays one of two headline states. The nuance is always in the action field.

---

## Category 8 — Evaluation methodology assumptions

### A18: 10 URLs is sufficient to detect systematic prompt failures

**What is assumed:** 10 URLs is enough data to identify the five failure modes (FM-1 through FM-5) if they are present at a rate that would matter in production. Specifically: if a failure mode affects 30%+ of verdicts, it will appear in at least 2-3 of the 10 test URLs, which is detectable.

**Why assumed:** Statistical power consideration: with 10 URLs and a failure rate of ≥30%, the expected number of failures is ≥3. This is enough to confidently diagnose a systemic issue. For rare failures (<10% rate), 10 URLs is insufficient — but rare failures are by definition low-impact.

**What would falsify it:** A failure mode that only appears on uncommon URL archetypes not well-represented in the 10-URL sample (e.g., a failure specific to ecommerce product pages that are excluded from the test set).

**Consequence of being wrong:** The validation passes, but a failure mode is discovered in production. Mitigation: the archetype distribution is designed to cover the most common scenarios. Edge cases (ecommerce, YMYL, local) are explicitly out of scope for this validation.

**Risk level:** Low for the scope of the validation as defined.

---

### A19: The validation evaluator has sufficient SEO expertise to score verdicts accurately

**What is assumed:** The evaluator (Jason) has enough SEO strategy experience to judge whether a primary constraint identification is correct and whether a recommended action is specific and actionable.

**Why assumed:** The evaluation methodology requires expert judgment. Non-expert scoring would be meaningless.

**What would falsify it:** The evaluator's background is primarily in areas other than SEO diagnosis (e.g., technical SEO vs. content strategy), creating systematic blind spots in scoring.

**Consequence of being wrong:** Bring in a second reviewer with complementary SEO expertise for at least the Archetype B URLs (the hardest test). The evaluation package already recommends this.

**Risk level:** Low. This is Jason's domain.

---

## Category 9 — Production pipeline assumptions

### A20: Automated content summaries are functionally equivalent to human-written summaries as Bottleneck prompt inputs

**What is assumed:** The summarization pipeline (Firecrawl crawl → Claude Haiku 4.5 summarization) produces content summaries that are sufficiently close in quality to the human-written summaries used in the 10-URL validation that Bottleneck verdict quality is not materially degraded in production.

**Why this assumption exists:** The 10-URL prompt validation confirms that the Bottleneck prompt works when given high-quality human summaries. It does not confirm that it works when given machine-generated summaries. These are different claims. The gap between them is the primary untested risk entering Sprint 2.

**Why it may not hold:** Human evaluators following the compression rules produce summaries that are structurally rich and intentionally descriptive. Automated summarization with a poorly designed prompt tends toward: generic topic descriptions ("this page covers CRM software"), missing structural observations (no mention of comparison tables, word count, heading structure), and occasionally evaluative language ("this is a comprehensive guide") that bypasses the model's reasoning. Each of these degrades a different verdict dimension — specificity (D3), constraint identification (D1), and confidence calibration (D4) respectively.

**What would falsify it:** Running the Bottleneck prompt on 3–5 of the same URLs used in the prompt validation, substituting automated summaries for human summaries, and observing that:
- `primary_constraint` changes on 2 or more URLs, OR
- D3 (specificity) scores drop by an average of 1+ point across the set, OR
- Any Archetype B URL flips from `links_are_the_answer = false` to `true`.

**Required mitigation — Pipeline Validation:** Before production launch, a **Pipeline Validation** must be run as follows:
1. Select 3–5 URLs from the completed 10-URL prompt validation (include at least 1 Archetype A, 1 Archetype B, 1 Archetype C).
2. Run the full automated pipeline for those URLs: Firecrawl crawl → Haiku summarization → Bottleneck prompt.
3. Record the automated verdicts.
4. Compare `primary_constraint`, `links_are_the_answer`, and D1/D3 scores against the human-summary verdicts for the same URLs.
5. If results are consistent: Pipeline Validation passes. If not: the summarization prompt must be revised before launch.

**Pipeline Validation gate:** The pipeline validation is a pre-launch gate, not a pre-Sprint-1 gate. It cannot be run until the summarization pipeline is built (Sprint 2). It must be completed before any production traffic is processed.

**Consequence of skipping this validation:** Verdicts in production are systematically worse than verdicts observed in pre-launch testing. User trust is damaged on first use. This is the highest-risk launch failure mode for the intelligence layer.

**Risk level:** High if the summarization prompt is not designed with the same rigor as the Bottleneck prompt. Medium if it is. The summarization prompt must be a first-class deliverable, not a utility script.

**Related decisions:** See `docs/decisions.md` — "Automated Content Extraction Pipeline" entry (2026-06-24).

---

---

## Category 10 — Investment Decision Engine assumptions

*These assumptions are not Bottleneck validation assumptions. They govern the Investment Decision Engine (Opportunity module) and are relevant starting Sprint 3.*

### A21: Mode detection correctly classifies ambiguous input URLs

**What is assumed:** The heuristics used to distinguish Mode A (specific placement page) from Mode B (guest post opportunity) reliably classify the URL type. A single article page is classified as Mode A; a domain or category URL is classified as Mode B.

**Why assumed:** The dual-mode architecture depends on correct mode detection. A misclassification sends the evaluation down the wrong data collection path: Mode A on a category page (crawling index content instead of article content) or Mode B on a specific article (sampling when a precise page evaluation is possible).

**What would falsify it:** A meaningful proportion of Mode A classifications applied to listing pages, or a meaningful proportion of Mode B/category classifications applied to single articles. In practice: if user feedback indicates verdicts are using the wrong data source for the input URL type.

**Consequence of being wrong:** Degraded verdict quality for that evaluation class. The default-to-Mode-B-on-ambiguity rule mitigates the worst case (the product never falsely claims a Mode A verdict when the specific page is unknown). But false Mode A classifications on listing pages would produce incorrect P1–P5 signals.

**Mitigation:** The `mode_detection_note` field surfaces ambiguous classifications to the user. If the user overrides (by providing a more specific URL), the evaluation can be rerun. Mode detection heuristics should be validated on a sample of 20–30 URLs across different site types before Sprint 3 ships.

**Risk level:** Medium. The heuristics cover the common cases cleanly. Ambiguous cases (long-form product pages, multi-page articles, content hubs) are the risk area.

---

### A22: Section inference selects the most relevant content section for the target topic

**What is assumed:** When a user submits a bare domain URL and the system must infer the most relevant section, the inference process (sitemap analysis + navigation classification + topic matching via Haiku) consistently identifies the section most relevant to the target page's topic.

**Why assumed:** In Mode B / domain-only sub-type, the quality of the signal approximation depends entirely on sampling from the right section. Sampling from the wrong section (e.g., inferring a "general business" section for a digital marketing target page instead of the more relevant "SEO" or "content marketing" section) degrades P1, P2, and P5 significantly.

**What would falsify it:** A set of domain evaluations where the inferred section is visibly misaligned with the target topic — e.g., a SaaS target page evaluated against the domain's "finance" articles because the navigation classifier matched "software ROI" to financial content.

**Consequence of being wrong:** The P1–P5 signal cluster is based on irrelevant article samples. The Relevance cluster score will be artificially low (or in pathological cases, artificially high). The `inferred_section` field surfaces the chosen section in the verdict, allowing the user to identify a misclassification and resubmit with a specific category URL.

**Mitigation:** Surface `inferred_section` prominently in the UI with a clear message: "Evaluation based on [section name] articles. If this is not the section where you intend to publish, paste the category URL directly for a more precise evaluation." This converts an assumption failure into a user-correctable state.

**Risk level:** Medium-low for sites with clear topic-aligned navigation (most editorial sites). Medium for broad authority sites with many unrelated sections (e.g., HubSpot, Forbes, Search Engine Journal — where multiple sections could plausibly match a digital marketing target page).

**Related decisions:** See `docs/decisions.md` — "2026-06-25 Investment Decision Engine: Dual-Mode Architecture" (section inference logic and section inference failure fallback).

---

## Assumption registry summary

| ID | Category | Risk level | Key falsification signal |
|---|---|---|---|
| A1 | Model | Low | Same prompt → different primary_constraint on re-run |
| A2 | Model | Medium | FM-2 on >1 Archetype B URL |
| A3 | Model | Low-medium | Enum values outside schema; output outside tool call |
| A4 | Model | Very low | Output truncation mid-field |
| A5 | Model/Method | Medium | Verdicts fail because summaries were too ambiguous |
| A6 | Keyword | Medium | GSC keyword ≠ page's strategic intent |
| A7 | Keyword | Low | Position variance renders avg position meaningless |
| A8 | Competitor | Low-medium | Geo-localized SERP ≠ target audience's SERP |
| A9 | Competitor | Low | 3 competitors is insufficient for ambiguous SERPs |
| A10 | Authority | Low (direction) / Medium (magnitude) | RD count misrepresents relative authority |
| A11 | Authority | Low-medium | Free tool severely undercounts large domains |
| A12 | Compression | Medium-high | Summaries consistently over/understate content quality |
| A13 | Compression | Low | Model misinterprets format labels |
| A14 | Ground truth | Inherent | Post-launch outcome data contradicts validation scores |
| A15 | Ground truth | Medium | Single-evaluator confirmation bias |
| A16 | Taxonomy | Low-medium | Verdicts regularly don't fit any of the five categories |
| A17 | Taxonomy | Low | Binary flag is consistently found misleading |
| A18 | Method | Low | Failure mode only appears on archetypes not in test set |
| A19 | Method | Low | Evaluator expertise insufficient for scoring |
| A20 | Pipeline | High (if summarization prompt is weak) / Medium (if rigorous) | Automated summaries degrade D1/D3 scores vs. human summaries on same URLs |
| A21 | IDE / Mode detection | Medium | Mode detection misclassifies listing pages as Mode A or articles as Mode B at meaningful rate |
| A22 | IDE / Section inference | Medium-low (broad sites) / Medium (large multi-section sites) | Inferred section is visibly misaligned with target topic |

---

*The Bottleneck validation assumptions (A1–A20) are locked before validation begins. Do not update them mid-validation — that would invalidate the test. If a new assumption is discovered during the test, note it in the URL worksheet's "Other notes" field and document it here after validation is complete. A21 and A22 are IDE architecture assumptions and are not locked to the Bottleneck validation cycle.*
