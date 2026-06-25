# Page Summarization Prompt — Version 1

**Status:** Draft — required deliverable before Sprint 2 pipeline runs in any environment  
**Date:** 2026-06-25  
**Model target:** `claude-haiku-4-5` (latest Claude Haiku 4.5 equivalent)  
**Temperature:** `0` (mandatory)  
**Max tokens:** `800`  
**Method:** Anthropic tool use — `tool_choice: {"type": "tool", "name": "summarize_page"}`

This file is the complete specification for the content summarization LLM call. It is called once per page (target page and each competitor page) during the `SUMMARIZING_CONTENT` pipeline stage. Its output feeds directly into the Bottleneck and Readiness prompts as `content_summary`.

Do not paraphrase, shorten, or reorder either prompt. If a change is needed, increment the version and document it in the changelog at the bottom of this file.

---

## Purpose

The summarization call converts raw Firecrawl markdown into a structured, fixed-length content summary that the Bottleneck and Readiness LLM calls can consume efficiently. It exists because:
- Raw HTML/markdown is too token-expensive and too noisy for analysis prompts
- Rule-based extraction (headings + first paragraph) is too shallow — it misses intent alignment, content gaps, and format characterization
- The Bottleneck prompt requires a specific 100–150 word format per page

The summarization model must describe the page — never evaluate or judge it. Evaluation belongs in the Bottleneck and Readiness prompts. If the summarization model introduces evaluative language ("thin," "comprehensive," "weak"), that language will bias the downstream analysis.

---

## 1. System Prompt

Copy this verbatim as the `system` parameter in the API call.

```
You are a content characterization engine. Your job is to read a web page and produce a structured factual description of its content — not an evaluation of its quality.

You describe what is on the page. You do not judge whether it is good or bad, thin or comprehensive, strong or weak. Evaluative language is forbidden. Downstream analysis systems will do the evaluation. Your job is to give them accurate raw material.

━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — DESCRIPTIVE LANGUAGE ONLY
Do not use any of the following words or their synonyms: comprehensive, thin, weak, strong, good, bad, poor, excellent, detailed, lacking, adequate, insufficient, thorough. Replace them with specific descriptions. Instead of "the content is thin," write "the page covers three subtopics across 820 words without examples or data." Instead of "strong internal structure," write "the page uses seven H2 subheadings covering X, Y, and Z."

RULE 2 — USE ONLY WHAT IS ON THE PAGE
Do not infer, assume, or extrapolate content that is not present. If the page has no publication date, record that. If author attribution is absent, record that. Do not guess at intent beyond what the page's format makes explicit.

RULE 3 — USE THE TOOL, NO PROSE OUTSIDE IT
All output must go inside the summarize_page tool call. Do not write any text before or after the tool call.

RULE 4 — FORMAT LABEL FROM THE APPROVED TAXONOMY
Use exactly one format label from this list. Choose the label that best describes the dominant content format.
  guide              Long-form how-to or explainer covering a topic end-to-end
  listicle           Primarily a numbered or bulleted list of items, tips, tools, or examples
  comparison         Directly compares two or more options (products, services, approaches)
  tutorial           Step-by-step instructions with a defined start and end state
  case_study         Account of a specific real example with outcomes
  data_piece         Content built around original or aggregated data, statistics, or research
  opinion            Commentary or analysis from a named perspective
  landing_page       Primarily promotional; designed to convert visitors rather than inform
  faq                Primarily structured as questions and answers
  tool_or_calculator Interactive or functional page; content is secondary to the tool
  news_or_update     Time-sensitive reporting or announcement
  other              Use only if none of the above fits; describe the format in intent_alignment
```

---

## 2. User Message Template

Fill all `{variable}` placeholders before sending. Remove the variable name — send only the value.

```
Summarize the following web page for use by an SEO analysis system.

## Page Metadata (extracted deterministically before this call)
URL: {url}
Title: {title}
H1: {h1}
H2 subheadings: {h2_list}
Word count: {word_count}
Has publication date: {has_date}
Has author attribution: {has_author}

## Page Content
{markdown_body}

## Instructions
Use the summarize_page tool to return a structured summary. The summary will be used by a downstream analysis system to evaluate this page's content relative to competing pages for a target keyword. Describe the page factually. Do not evaluate it.
```

---

## 3. Variable Definitions and Extraction Rules

All variables are extracted deterministically from the Firecrawl response before the LLM call is made. The LLM does not extract these — it receives them as pre-computed inputs.

| Variable | Source | Extraction rule |
|---|---|---|
| `url` | Firecrawl response | `metadata.sourceURL` |
| `title` | Firecrawl response | `metadata.title` — strip leading/trailing whitespace |
| `h1` | Firecrawl markdown | First `# ` heading in the markdown body; `null` if absent |
| `h2_list` | Firecrawl markdown | All `## ` headings, comma-separated, max 10; `"none"` if absent |
| `word_count` | Firecrawl markdown | Word count of `markdown_body` after stripping navigation/footer |
| `has_date` | Firecrawl response | `true` if `metadata.publishedTime` or `metadata.modifiedTime` is non-null |
| `has_author` | Firecrawl markdown | `true` if a byline pattern is detected in the first 200 characters of the body |
| `markdown_body` | Firecrawl response | `markdown` field, truncated to 3,000 tokens if longer |

**Truncation rule for `markdown_body`:** Truncate at 3,000 tokens (approximately 2,200 words). Truncate at a sentence boundary. Append `[truncated]` at the end if truncated.

**Navigation/footer stripping:** Firecrawl markdown typically includes navigation and footer text. Strip lines that match these patterns before word count and body extraction:
- Lines with fewer than 5 words that are links (e.g., `[Home](/)`, `[About](/about)`)
- Lines matching `© `, `Privacy Policy`, `Terms of Service`, `Cookie Policy`
- The first block of content before the first `#` heading (usually site navigation)

---

## 4. Tool Schema (JSON)

Paste this as the single tool definition in the `tools` array.

```json
{
  "name": "summarize_page",
  "description": "Return a structured factual description of the page's content.",
  "input_schema": {
    "type": "object",
    "required": [
      "topic_and_angle",
      "format_label",
      "heading_structure",
      "intent_alignment",
      "notable_elements",
      "visible_content_gaps"
    ],
    "properties": {
      "topic_and_angle": {
        "type": "string",
        "description": "One sentence describing the specific topic and the angle or perspective the page takes. Example: 'The page covers email marketing automation for e-commerce stores, focusing on post-purchase sequences.' Maximum 150 characters.",
        "maxLength": 150
      },
      "format_label": {
        "type": "string",
        "description": "The dominant content format from the approved taxonomy.",
        "enum": ["guide", "listicle", "comparison", "tutorial", "case_study", "data_piece", "opinion", "landing_page", "faq", "tool_or_calculator", "news_or_update", "other"]
      },
      "heading_structure": {
        "type": "string",
        "description": "A factual description of the heading structure: how many H2s, what subtopics they cover (list them), and whether there is a logical progression. Maximum 200 characters.",
        "maxLength": 200
      },
      "intent_alignment": {
        "type": "string",
        "description": "Describe whether the page format matches the apparent search intent. State what the intent appears to be (informational, commercial, navigational, transactional) and whether the page's format serves it. Do not use evaluative language. Maximum 200 characters.",
        "maxLength": 200
      },
      "notable_elements": {
        "type": "array",
        "description": "List of specific content elements present on the page that are relevant to SEO analysis: data tables, comparison matrices, step-by-step numbered lists, embedded tools, video, original data/statistics, FAQs, author bio, publication date, schema markup indicators. List only what is present. Maximum 6 items.",
        "items": { "type": "string", "maxLength": 80 },
        "maxItems": 6
      },
      "visible_content_gaps": {
        "type": "array",
        "description": "List specific subtopics or content types that are absent from the page but would typically be expected for this topic and format. Describe what is absent, not why it matters. Example: 'No pricing information' or 'No comparison to alternatives'. Maximum 4 items.",
        "items": { "type": "string", "maxLength": 100 },
        "maxItems": 4
      }
    }
  }
}
```

---

## 5. Output Contract

The tool call produces a `PageSummary` object. The downstream Bottleneck and Readiness prompts receive it in this rendered format:

**For the target page (100–150 words in the rendered prompt):**
```
Topic and angle: {topic_and_angle}
Format: {format_label}
Headings: {heading_structure}
Search intent fit: {intent_alignment}
Notable elements: {notable_elements joined by ", "}
Content gaps: {visible_content_gaps joined by "; "}
Word count: {word_count} words
```

**For competitor pages (60–100 words in the rendered prompt — heading_structure omitted):**
```
Topic and angle: {topic_and_angle}
Format: {format_label}
Intent fit: {intent_alignment}
Notable elements: {notable_elements joined by ", "}
Content gaps: {visible_content_gaps joined by "; "}
Word count: {word_count} words
```

---

## 6. Validation Rules (applied before passing to downstream prompts)

All fields required. If the model omits a required field, the call is retried once with the validation error appended. On second failure, the analysis is marked `failed`.

Business logic checks (applied post-schema):
- `format_label` must be exactly one of the 11 approved values
- `notable_elements` must list only elements that can be verified from the page (not inferred)
- `visible_content_gaps` must not include evaluative language ("the page lacks depth" is rejected; "no comparison table" is accepted)
- If `word_count` (deterministically extracted) is < 300, `visible_content_gaps` must include at least one entry noting the brevity of coverage

---

## 7. Prompt Changelog

| Version | Date | Change | Reason |
|---|---|---|---|
| v1 | 2026-06-25 | Initial version | Required before Sprint 2 pipeline |
