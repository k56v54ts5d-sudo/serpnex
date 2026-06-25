# Bottleneck Validation — Evaluation Package

**Version:** 1.0  
**Date:** 2026-06-24  
**Prompt under test:** `docs/prompts/bottleneck-v1.md`  
**Validation plan:** `docs/bottleneck-validation-plan.md`  
**Evaluator:** _______________  
**Second reviewer (optional):** _______________

This is the working document for the 10-URL Bottleneck validation. It contains everything needed in one place: pre-flight checks, step-by-step instructions, all 10 URL worksheets, and the aggregate results and decision record.

Complete each section in order. Do not skip ahead.

---

## SECTION 0 — Pre-flight checklist

Complete before running any URL.

```
□ Anthropic API key obtained and tested (can call claude-sonnet-4-5)
□ Python 3 installed (for the API call script in Section 2)
□ anthropic Python package installed: pip install anthropic
□ At least one free backlink tool accessible:
    □ Ahrefs (free — 1 domain check/day)
    □ Moz Link Explorer (free account — limited checks/day)
    □ Semrush (free account — 10 queries/day)
    □ Ubersuggest (free account)
□ Access to Google Search Console for at least 2 of the 10 target URLs
□ 10 URLs selected and recorded in Section 1 (with archetypes)
□ Pre-test hypotheses written for all 10 URLs BEFORE proceeding to data gathering
```

Do not proceed to Section 2 until all boxes are checked.

---

## SECTION 1 — URL selection worksheet

### Rules for selection

- Pages must rank in positions 5–30 in Google (not #1, not unranked)
- English-language pages only for this validation
- At least 2 URLs must have GSC access
- Archetypes must match the required distribution below
- Write your pre-test hypothesis for each URL before gathering any data

### Required archetype distribution

| Archetype | Required count | Description |
|---|---|---|
| A — Genuinely link-limited | 3 | Good content, clear authority gap vs. competitors |
| B — Content or intent bottleneck | 3 | Links won't help — content/format is the issue |
| C — Mixed (both factors weak) | 2 | Real ambiguity; model must identify the primary |
| D — No GSC, data-sparse | 1 | Tests confidence degradation with thin data |
| E — New/low-history page | 1 | Tests "insufficient signal" handling |

### URL selection table

```
URL 01: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Your pre-test hypothesis (write BEFORE gathering any data):
"I expect the primary bottleneck to be [category] because [reason]."
→ _______________________________________________

URL 02: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 03: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 04: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 05: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 06: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 07: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 08: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 09: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________

URL 10: _______________________________________________
Archetype: A / B / C / D / E
GSC access: Yes / No
Pre-test hypothesis:
→ _______________________________________________
```

---

## SECTION 2 — Execution instructions

### For each URL, follow these steps in order.

**Step 1 — Gather target page signals (10–15 min)**

Open the URL in a browser. Collect:
- Title tag: browser tab text or View Source → `<title>`
- H1: the main heading on the page
- Word count: paste main body into Google Docs → Tools → Word Count. Exclude nav/footer/sidebar.
- Content format: choose from `guide / listicle / comparison / tutorial / review / landing page / pillar page / news article / product page / other`
- Page indexed: run `site:https://full-url/path` in Google
- Internal link count: optional — count `<a href>` tags pointing to this page from the same domain (rough estimate is fine)

From GSC (if connected): Performance → Pages → filter to URL → Queries → sort by Impressions → primary keyword + average position + impressions (90d)

**Step 2 — Gather backlink data for target URL**

Use one free tool (Ahrefs / Moz / Semrush / Ubersuggest). Check the specific URL, not the domain. Record:
- Referring domains (approx)
- Tool used

**Step 3 — Find and profile competitors (15–20 min)**

Search Google in incognito for the primary keyword. Record the first 3 organic results (skip ads, local packs, featured snippets). For each:
- Visit the page
- Record: URL, title tag, word count, content format
- Read enough to write a 60–100 word content summary (what angle, what format, what structure, how it differs from the target)
- Pull backlink data for each competitor URL using the same tool

**Step 4 — Calculate gaps**

- Authority gap: competitor median RDs − target RDs
- Content gap: competitor median word count − target word count
- Note SERP features visible in the incognito search
- Note dominant competitor format

**Step 5 — Build the prompt**

Open `docs/prompts/bottleneck-v1.md`. Copy the user message template. Fill in every `{variable}` using the data collected. Replace unfilled variables with `not available`. Do not leave any `{variable}` placeholder in the final prompt.

Write the completed prompt to a file or text editor — you will need it in Step 6.

**Step 6 — Run the API call**

Use the script below. Paste your system prompt and completed user message into the script. Run it. Copy the full output into the URL worksheet.

```python
import anthropic
import json

SYSTEM_PROMPT = """[PASTE SYSTEM PROMPT FROM docs/prompts/bottleneck-v1.md HERE]"""

USER_MESSAGE = """[PASTE YOUR COMPLETED USER MESSAGE TEMPLATE HERE]"""

TOOL_SCHEMA = {
    "name": "analyze_bottleneck",
    "description": "Record the complete bottleneck analysis verdict for the target page. All fields are required. Weights in constraint_breakdown must sum to 1.0.",
    "input_schema": {
        "type": "object",
        "required": [
            "primary_constraint", "primary_severity", "links_are_the_answer",
            "headline", "competitive_context", "constraint_breakdown",
            "recommended_action", "recommended_action_priority",
            "confidence", "confidence_rationale"
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
            "links_are_the_answer": {"type": "boolean"},
            "headline": {"type": "string", "maxLength": 150},
            "competitive_context": {"type": "string", "maxLength": 220},
            "constraint_breakdown": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["category", "severity", "weight", "reason"],
                    "properties": {
                        "category": {"type": "string", "enum": ["link_authority", "content_depth", "intent_mismatch", "internal_links", "technical"]},
                        "severity": {"type": "string", "enum": ["mild", "significant", "severe"]},
                        "weight": {"type": "number", "minimum": 0.05, "maximum": 0.95},
                        "reason": {"type": "string", "maxLength": 280}
                    }
                }
            },
            "recommended_action": {"type": "string", "maxLength": 280},
            "recommended_action_priority": {"type": "string", "enum": ["immediate", "high", "medium", "low"]},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence_rationale": {"type": "string", "maxLength": 320}
        }
    }
}

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=2000,
    temperature=0,
    system=SYSTEM_PROMPT,
    tools=[TOOL_SCHEMA],
    tool_choice={"type": "tool", "name": "analyze_bottleneck"},
    messages=[{"role": "user", "content": USER_MESSAGE}]
)

# Extract and pretty-print the verdict
tool_block = next(b for b in response.content if b.type == "tool_use")
verdict = tool_block.input

print("=== VERDICT ===")
print(json.dumps(verdict, indent=2))
print(f"\n=== USAGE ===")
print(f"Input tokens:  {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")

# Validate weights sum to 1.0
weights = [c["weight"] for c in verdict.get("constraint_breakdown", [])]
weight_sum = sum(weights)
print(f"\n=== WEIGHT CHECK ===")
print(f"constraint_breakdown weights: {weights}")
print(f"Sum: {weight_sum:.3f} ({'OK' if abs(weight_sum - 1.0) < 0.02 else 'FAIL — does not sum to 1.0'})")
```

**Step 7 — Record and score**

Complete the URL worksheet for this URL (Section 3). Do this immediately after running the call, while the reasoning is fresh.

---

## SECTION 3 — Per-URL worksheets

Copy the block below for each URL. Work through all 10 before calculating aggregate scores.

---

### URL 01 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 01 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis (copied from Section 1):
→ _______________________________________________

TARGET PAGE SIGNALS:
  Title: _______________________________________________
  H1: _______________________________________________
  Word count: _______________
  Content format: _______________
  Primary keyword: _______________________________________________
  Keyword source: GSC — top impressions keyword / inferred from title+H1 / inferred from H1 only
  GSC avg position: _______________  (or: not available)
  GSC impressions (90d): _______________  (or: not available)
  Indexed: yes / no / uncertain
  Target RDs: _______________  (tool: _______________)
  Backlink source: _______________

COMPETITOR 1:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________
  Format: _______________
  RDs: _______________

COMPETITOR 2:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________
  Format: _______________
  RDs: _______________

COMPETITOR 3:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________
  Format: _______________
  RDs: _______________

GAPS:
  Competitor median RDs: _______________
  Authority gap: _______________  [ target is behind / ahead / roughly equal / not calculable ]
  Competitor median words: _______________
  Content gap: _______________  [ target is shorter / longer / roughly equal ]
  SERP features: _______________________________________________
  Dominant competitor format: _______________________________________________

DATA FLAGS:
  GSC connected: yes / no
  Competitors retrieved: ___ of 3
  Target backlinks available: yes / no
  Competitor backlinks available: all 3 / 2 of 3 / 1 of 3 / none
  Page crawled: yes / partial / no

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 01 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run timestamp: _______________
Input tokens: _______________  |  Output tokens: _______________

primary_constraint: _______________
primary_severity: _______________
links_are_the_answer: true / false
confidence: low / medium / high
weight sum check: _______________  (OK / FAIL)
Schema parsed cleanly: yes / no / partial — describe: _______________

headline (copy verbatim):
"_______________________________________________"

competitive_context (copy verbatim):
"_______________________________________________"

recommended_action (copy verbatim):
"_______________________________________________"

confidence_rationale (copy verbatim):
"_______________________________________________"

constraint_breakdown:
  1. category: ___________  severity: ___________  weight: _____
     reason: _______________________________________________
  2. category: ___________  severity: ___________  weight: _____
     reason: _______________________________________________
  3. category: ___________  severity: ___________  weight: _____
     reason: _______________________________________________

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 01 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score each dimension 0, 1, or 2. Refer to docs/bottleneck-validation-plan.md for rubric.

D1 — Constraint identification accuracy
  [ ] 2 — Correct and specific (matches expert judgment; reason cites this page's signals)
  [ ] 1 — Plausible but arguable (defensible but generic, or constraint right/reason weak)
  [ ] 0 — Wrong or misleading (clearly incorrect given the signals provided)
  Score: ___

D2 — "Links won't help" test  (Archetype B or C only — write N/A for A, D, E)
  [ ] 2 — Correctly defers links (links_are_the_answer = false; reason is correct)
  [ ] 1 — Partial deferral (right direction but hedged or diluted)
  [ ] 0 — False positive (link_authority named as primary on a content/intent-bottlenecked page)
  Score: ___ / N/A

D3 — Specificity
  [ ] 2 — Page-specific (cites concrete signals from THIS page and THESE competitors)
  [ ] 1 — Partially specific (some signal citation; verdict partly generic)
  [ ] 0 — Generic (could apply to any page; no specific signal cited)
  Score: ___

D4 — Confidence calibration
  [ ] 2 — Appropriately calibrated (confidence level matches actual data availability)
  [ ] 1 — Slightly off (one level too high/low, but rationale acknowledges the gap)
  [ ] 0 — Miscalibrated (high confidence on sparse data, or low confidence on complete data)
  Score: ___

D5 — Schema compliance
  [ ] 2 — Clean parse (all fields present, enums valid, weights sum to 1.0)
  [ ] 1 — Minor issues (one missing field or slightly malformed, verdict recoverable)
  [ ] 0 — Parse failure (critical fields missing or invalid; output unusable as-is)
  Score: ___

D6 — Actionability
  [ ] 2 — Specific next action (concrete, page-specific, could be briefed immediately)
  [ ] 1 — Direction without specifics (right direction, lacks concrete steps)
  [ ] 0 — Vague or circular (generic, repeats the constraint, not actionable)
  Score: ___

DIMENSION TOTAL:   D1:___ + D2:___ + D3:___ + D4:___ + D5:___ + D6:___ = _____ / 12 (or 10 if N/A)

EVALUATOR NOTES:
  Model agreed with pre-test hypothesis: yes / no / partially
  If no — was the model more likely right, or more likely wrong?
  → _______________________________________________
  
  Did the verdict say something genuinely non-obvious?
  → _______________________________________________
  
  Any hallucinated signals (model cited data NOT in the prompt)?
  → yes — describe: _______________________________________________
  → no

  Failure mode observed (if any — see FM-1 through FM-5 in validation plan):
  → _______________________________________________

  Other notes:
  → _______________________________________________
```

---

### URL 02 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 02 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET PAGE SIGNALS:
  Title: _______________________________________________
  H1: _______________________________________________
  Word count: _______________
  Content format: _______________
  Primary keyword: _______________________________________________
  Keyword source: GSC — top impressions keyword / inferred from title+H1 / inferred from H1 only
  GSC avg position: _______________
  GSC impressions (90d): _______________
  Indexed: yes / no / uncertain
  Target RDs: _______________  (tool: _______________)
  Backlink source: _______________

COMPETITOR 1:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________  |  Format: _______________  |  RDs: _______________

COMPETITOR 2:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________  |  Format: _______________  |  RDs: _______________

COMPETITOR 3:
  URL: _______________________________________________
  Title: _______________________________________________
  Word count: _______________  |  Format: _______________  |  RDs: _______________

GAPS:
  Competitor median RDs: _______________  |  Authority gap: _______________  [ behind / ahead / equal / N/A ]
  Competitor median words: _______________  |  Content gap: _______________  [ shorter / longer / equal ]
  SERP features: _______________________________________________
  Dominant competitor format: _______________________________________________

DATA FLAGS:
  GSC: yes/no  |  Competitors: ___ of 3  |  Target BL: yes/no  |  Comp BL: all3/2/1/none  |  Crawled: yes/partial/no

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 02 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run timestamp: _______________  |  Tokens in: _______________  out: _______________

primary_constraint: _______________  |  primary_severity: _______________
links_are_the_answer: true / false  |  confidence: low / medium / high
weight sum: _______________  (OK / FAIL)  |  Schema clean: yes / no / partial

headline: "_______________________________________________"
competitive_context: "_______________________________________________"
recommended_action: "_______________________________________________"
confidence_rationale: "_______________________________________________"

constraint_breakdown:
  1. ___________  ___________  _____  → _______________________________________________
  2. ___________  ___________  _____  → _______________________________________________
  3. ___________  ___________  _____  → _______________________________________________

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 02 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1 (constraint accuracy): ___   D2 (links test — N/A if Archetype A/D/E): ___
D3 (specificity): ___           D4 (confidence calibration): ___
D5 (schema compliance): ___     D6 (actionability): ___
TOTAL: _____ / _____

Hypothesis match: yes / no / partially
Hallucination: yes (describe: _______________) / no
Failure mode: _______________________________________________
Notes: _______________________________________________
```

---

### URL 03 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 03 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET PAGE SIGNALS:
  Title: _______________________________________________  |  H1: _______________________________________________
  Word count: _______________  |  Format: _______________
  Primary keyword: _______________________________________________
  Keyword source: GSC / inferred title+H1 / inferred H1 only
  GSC avg position: _______________  |  GSC impressions (90d): _______________
  Indexed: yes / no / uncertain  |  Target RDs: _______________  (tool: _______________)

COMPETITOR 1: _______________________________________________ | wc:___ | fmt:___________ | RDs:___
COMPETITOR 2: _______________________________________________ | wc:___ | fmt:___________ | RDs:___
COMPETITOR 3: _______________________________________________ | wc:___ | fmt:___________ | RDs:___

GAPS: Median RDs:___ | Auth gap:___ [behind/ahead/equal/N/A] | Median words:___ | Content gap:___ [shorter/longer/equal]
SERP features: _______________________________________________ | Dominant format: _______________

DATA FLAGS: GSC:y/n | Competitors:_/3 | TargetBL:y/n | CompBL:all3/2/1/none | Crawled:y/partial/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 03 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: _______________  |  Tokens in:_____ out:_____  |  Weights sum:_____ (OK/FAIL) | Schema:clean/issues/fail

primary_constraint: _______________  |  severity: _______________  |  links_are_the_answer: true/false  |  confidence: low/medium/high

headline: "_______________________________________________"
competitive_context: "_______________________________________________"
recommended_action: "_______________________________________________"
confidence_rationale: "_______________________________________________"

constraint_breakdown:
  1. ___________  ___________  _____  → _______________________________________________
  2. ___________  ___________  _____  → _______________________________________________
  3. ___________  ___________  _____  → _______________________________________________

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 03 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL: ___/___
Hypothesis: match/no/partial | Hallucination: yes(___)/no | FM: ___________ | Notes: _______________
```

---

### URL 04 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 04 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 04 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 04 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 05 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 05 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 05 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 05 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 06 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 06 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 06 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 06 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 07 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 07 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 07 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 07 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 08 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 08 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 08 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 08 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 09 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 09 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 09 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 09 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

### URL 10 Worksheet

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 10 — DATA GATHERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL: _______________________________________________
Archetype: A / B / C / D / E
Pre-test hypothesis:
→ _______________________________________________

TARGET: Title:_______________________________________________ | H1:_______________________________________________
wc:___ | fmt:___________ | keyword:_______________________________________________ | src:GSC/inf-title/inf-H1
GSC pos:___ | GSC imp:___ | Indexed:y/n/? | RDs:___ (tool:_____________)

C1: _______________________________________________ wc:___ fmt:___________ RDs:___
C2: _______________________________________________ wc:___ fmt:___________ RDs:___
C3: _______________________________________________ wc:___ fmt:___________ RDs:___

Gaps: medRDs:___ authGap:___ [b/a/eq/na] | medWords:___ contentGap:___ [shorter/longer/eq]
SERP:_______________ | DomFmt:_______________
Flags: GSC:y/n | Comp:_/3 | TBL:y/n | CBL:a3/2/1/0 | Crawl:y/p/n

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 10 — LLM OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run:___ | in:___ out:___ | wts:___ (OK/FAIL) | schema:clean/issues/fail
pc:___________ sev:___________ lata:t/f conf:l/m/h
headline:"_______________________________________________"
ctx:"_______________________________________________"
action:"_______________________________________________"
conf_rat:"_______________________________________________"
breakdown: 1.___ ___ ___→___ 2.___ ___ ___→___ 3.___ ___ ___→___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
URL 10 — SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1:___ D2:___ D3:___ D4:___ D5:___ D6:___  TOTAL:___/___
Hyp:match/no/partial | Hall:y(_______)/n | FM:___________ | Notes:_______________
```

---

## SECTION 4 — Aggregate results tracker

Complete this after all 10 URL worksheets are done.

### Score table

```
URL  | Arch | D1 | D2     | D3 | D4 | D5 | D6 | Raw  | Max  | %
-----|------|----|--------|----|----|----|----|----- |------|-----
01   |      |    |        |    |    |    |    |      |      |
02   |      |    |        |    |    |    |    |      |      |
03   |      |    |        |    |    |    |    |      |      |
04   |      |    |        |    |    |    |    |      |      |
05   |      |    |        |    |    |    |    |      |      |
06   |      |    |        |    |    |    |    |      |      |
07   |      |    |        |    |    |    |    |      |      |
08   |      |    |        |    |    |    |    |      |      |
09   |      |    |        |    |    |    |    |      |      |
10   |      |    |        |    |    |    |    |      |      |
-----|------|----|--------|----|----|----|----|----- |------|-----
TOT  |      |    |        |    |    |    |    |      |      |
AVG  |      |    |        |    |    |    |    |      |      |
```

**Scoring notes:**
- Raw = sum of all scored dimensions for that URL
- Max = 12 if D2 scored (Archetype B/C); 10 if D2 = N/A (Archetype A/D/E)
- % = Raw / Max × 100
- Average % is the primary aggregate metric

### Per-dimension summary

```
Dimension      | Total pts | Max pts | Avg score | % | Pattern observed
---------------|-----------|---------|-----------|---|------------------
D1 Accuracy    |           | 20      |           |   |
D2 Links test  |           | [varies]|           |   |
D3 Specificity |           | 20      |           |   |
D4 Confidence  |           | 20      |           |   |
D5 Schema      |           | 20      |           |   |
D6 Action      |           | 20      |           |   |
```

### Failure mode log

```
Failure mode  | # URLs affected | Affected URLs | Notes
--------------|-----------------|---------------|-------
FM-1 Generic  |                 |               |
FM-2 Link bias|                 |               |
FM-3 Over-hedge|                |               |
FM-4 Schema   |                 |               |
FM-5 Fab.     |                 |               |
```

### Hallucination log

```
URL | Signal hallucinated | Severity (minor/significant)
----|---------------------|-----------------------------
    |                     |
    |                     |
```

---

## SECTION 5 — Go / No-Go decision checklist

Work through each criterion in order. A single No-Go criterion blocks Sprint 1 regardless of all other scores.

### No-Go check (run first — any trigger stops Sprint 1)

```
N1 — Average score across all 10 URLs is below 60%
     Average % from score table: _______
     Triggered: YES / NO

N2 — Any Archetype B URL received D2 = 0 (false positive: model recommended links on content-bottlenecked page)
     D2 = 0 occurred on URL(s): _______ (or: none)
     Triggered: YES / NO

N3 — Schema failures (D5 = 0) on 3 or more URLs
     D5 = 0 count: _______
     Triggered: YES / NO

N4 — Hallucination on 3 or more URLs (model cited signals not in the prompt)
     Hallucination count: _______
     Triggered: YES / NO

ANY No-Go triggered: YES → STOP. Do not proceed to Sprint 1.
                     NO  → Continue to Go check.
```

### Go check (all must pass)

```
G1 — Average score ≥ 75%
     Average %: _______
     Passed: YES / NO

G2 — Zero D2 = 0 failures on any Archetype B URL
     Passed: YES / NO

G3 — At least 8 of 10 URLs score D3 ≥ 1 (specificity floor)
     D3 ≥ 1 count: _______
     Passed: YES / NO

G4 — At least 9 of 10 URLs score D5 = 2 (clean schema)
     D5 = 2 count: _______
     Passed: YES / NO

G5 — Hallucination on 2 or fewer URLs
     Hallucination count: _______
     Passed: YES / NO

ALL Go criteria passed: YES → PROCEED TO SPRINT 1
                        NO  → Check Conditional Go below.
```

### Conditional Go check (targeted fix, partial re-run)

```
C1 — Confidence miscalibration: D4 = 0 on 3+ URLs AND same direction (always too high / always too low)
     C1 triggered: YES / NO
     Fix required: Strengthen confidence calibration instruction in prompt (both directions)
     Re-run: The failing URLs only (_____)

C2 — Specificity pattern failure: D3 = 0 on 3+ URLs AND all from similar archetypes
     C2 triggered: YES / NO
     Fix required: Add explicit "cite specific signals" instruction with an example
     Re-run: The failing URLs only (_____)

C3 — Schema minor issues only: D5 = 1 on 3+ URLs, same field consistently
     C3 triggered: YES / NO
     Field consistently missing or malformed: _______
     Fix required: Simplify that field in the tool schema
     Re-run: The failing URLs only (_____)

Conditional Go: YES if only C1/C2/C3 triggered (no N triggers) and fix is clear
                Fix the prompt → re-run identified URLs → re-score → re-check G criteria
```

---

## SECTION 6 — Final decision record

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION DECISION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Date completed: _______________
Evaluator: _______________
Second reviewer (if applicable): _______________

Final average score: _______ %
Decision: GO / CONDITIONAL GO / NO-GO

If Conditional Go:
  Criteria triggered: _______________
  Prompt changes made (describe): _______________________________________________
  Prompt version after fix: _______________
  Re-run URLs: _______________
  Re-run score: _______ %
  Revised decision: GO / NO-GO

If No-Go:
  Criteria triggered: _______________
  Root cause analysis: _______________________________________________
  Required changes: _______________________________________________
  Next step: Re-architect prompt → full 10-URL re-run

If Go:
  Prompt version approved for Sprint 1: _______________
  Key observations to carry into Sprint 1:
  1. _______________________________________________
  2. _______________________________________________
  3. _______________________________________________

Signed: _______________   Date: _______________
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Record this decision in `docs/decisions.md` and update `docs/progress.md` before beginning Sprint 1.
