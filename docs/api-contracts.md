# API Contracts

This document defines the stable public API contracts for Serpnex endpoints. Frontend and integration clients should rely on these contracts. Breaking changes require a version increment and will be documented here.

**Base URL:** `/api/v1`  
**Content-Type:** `application/json` (all requests and responses)

---

## Opportunities

### `POST /opportunities`

Submit a prospect URL for Investment Decision Engine evaluation against a target page.

The API does not require the caller to specify a mode (Mode A vs Mode B). Mode is detected automatically by the pipeline from the structure and content of the submitted URL. All three URL types are accepted through the same endpoint with the same request shape.

#### Request Body

```json
{
  "page_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "prospect_url": "https://example.com/seo-guide"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `page_id` | UUID string | Yes | The target page to build a link to. Must reference an existing `pages` record. |
| `prospect_url` | string | Yes | The prospect site URL to evaluate. See accepted URL types below. |

#### Accepted URL Types

All three URL types are submitted as `prospect_url`. No field or flag is needed to distinguish them — the pipeline infers the type automatically.

| URL Type | Example | Pipeline behaviour |
|---|---|---|
| **Specific article** | `https://example.com/seo-fundamentals-guide` | Triggers Mode A (Specific Placement Evaluation). The article is crawled as the direct placement candidate. |
| **Category / section** | `https://example.com/category/seo/` or `https://example.com/resources/` | Triggers Mode B / category_url. Articles are sampled from the listed section. |
| **Bare domain or root** | `https://example.com` or `https://example.com/` | Triggers Mode B / domain_inferred. The pipeline infers the best matching section via sitemap + Haiku classification before sampling articles. |

The pipeline records its mode detection decision in `evaluation_mode` and `mode_b_subtype` on the opportunity record. If mode detection is ambiguous, the pipeline defaults to `guest_post_opportunity / domain_inferred` (the safer, lower-confidence option) and records a note in `data_quality.mode_detection_note`.

#### Validation Rules

All rules are evaluated in order. The first failing rule produces the error response.

| Rule | Error code | HTTP status |
|---|---|---|
| `page_id` is a valid UUID | `invalid_uuid` | 422 |
| `page_id` references an existing page | `page_not_found` | 404 |
| `prospect_url` is non-empty | `required_field` | 422 |
| `prospect_url` is a valid URL (parseable, has host) | `invalid_url` | 422 |
| `prospect_url` scheme is `http` or `https` | `invalid_scheme` | 422 |
| `prospect_url` domain differs from the target page domain | `same_domain` | 422 |

No workspace quota check is enforced at the API layer in Sprint 3 (deferred to post-MVP billing pass). Quota enforcement will be added without changing the request schema.

Each successful `POST /opportunities` creates a new evaluation record. Re-submitting the same `(page_id, prospect_url)` pair is allowed and creates a new independent evaluation — there is no deduplication. If two identical evaluations are submitted within seconds, both proceed independently.

#### Success Response — 202 Accepted

```json
{
  "opportunity_id": "7e3a9f41-1bc4-4f6a-a2d5-83c1e2f58b0d",
  "status": "queued",
  "page_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "prospect_url": "https://example.com/seo-guide",
  "prospect_domain": "example.com",
  "evaluation_mode": null,
  "stream_url": "/api/v1/opportunities/7e3a9f41-1bc4-4f6a-a2d5-83c1e2f58b0d/stream",
  "created_at": "2026-06-27T10:00:00Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `opportunity_id` | UUID string | Stable identifier for this evaluation. Use for polling and SSE. |
| `status` | string | Always `"queued"` on creation. |
| `page_id` | UUID string | Echo of the submitted `page_id`. |
| `prospect_url` | string | Echo of the submitted `prospect_url`. |
| `prospect_domain` | string | Extracted domain, normalised (no `www.`, no trailing slash). |
| `evaluation_mode` | string \| null | `null` until mode detection completes in the pipeline. |
| `stream_url` | string | Path to the SSE stream for real-time progress. |
| `created_at` | ISO 8601 timestamp | UTC. |

#### Error Responses

**Validation error (422):**
```json
{
  "error": "validation_error",
  "message": "Request validation failed.",
  "details": [
    {
      "field": "prospect_url",
      "code": "invalid_url",
      "message": "prospect_url must be a valid HTTP or HTTPS URL with a hostname."
    }
  ]
}
```

`details` is an array. Each element names the field that failed, the machine-readable error code, and a human-readable message. Multiple validation failures may appear in a single response.

**Business logic error (404):**
```json
{
  "error": "page_not_found",
  "message": "No page was found with the given page_id."
}
```

**Business logic error (422):**
```json
{
  "error": "same_domain",
  "message": "prospect_url must point to a different domain than the target page."
}
```

All error responses use the shape `{"error": "<code>", "message": "<description>"}`. Validation errors additionally include a `"details"` array.

---

### `GET /opportunities/{opportunity_id}`

Poll the current state of an opportunity evaluation.

#### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `opportunity_id` | UUID string | The `opportunity_id` returned by `POST /opportunities`. |

#### Error Responses

**Not found (404):**
```json
{
  "error": "opportunity_not_found",
  "message": "No opportunity was found with the given opportunity_id."
}
```

#### Success Response — 200 OK

The response schema is identical regardless of evaluation state. Fields that have not yet been populated are `null`.

```json
{
  "opportunity_id": "7e3a9f41-1bc4-4f6a-a2d5-83c1e2f58b0d",
  "status": "computing_score",
  "page_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "prospect_url": "https://example.com/seo-guide",
  "prospect_domain": "example.com",
  "evaluation_mode": "specific_placement",
  "mode_b_subtype": null,
  "inferred_section": null,
  "overall_outcome": null,
  "confidence": null,
  "confidence_ceiling": null,
  "investment_score": null,
  "cluster_scores": null,
  "verdict": null,
  "failed_reason": null,
  "data_quality": null,
  "created_at": "2026-06-27T10:00:00Z",
  "started_at": "2026-06-27T10:00:01Z",
  "completed_at": null
}
```

**Complete evaluation (status = `"complete"`):**

```json
{
  "opportunity_id": "7e3a9f41-1bc4-4f6a-a2d5-83c1e2f58b0d",
  "status": "complete",
  "page_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "prospect_url": "https://example.com/seo-guide",
  "prospect_domain": "example.com",
  "evaluation_mode": "specific_placement",
  "mode_b_subtype": null,
  "inferred_section": null,
  "overall_outcome": "recommended",
  "confidence": "high",
  "confidence_ceiling": "high",
  "investment_score": 74.2,
  "cluster_scores": {
    "relevance": 0.82,
    "authority": 0.71,
    "quality": 0.76,
    "risk": 0.88,
    "risk_multiplier": 1.00
  },
  "verdict": {
    "outcome": "recommended",
    "investment_score": 74.2,
    "evaluation_mode": "specific_placement",
    "mode_b_subtype": null,
    "hard_exclusion_triggered": false,
    "hard_exclusion_gate": null,
    "hard_exclusion_reason": null,
    "cluster_scores": {
      "relevance": 0.82,
      "authority": 0.71,
      "quality": 0.76,
      "risk": 0.88,
      "risk_multiplier": 1.00
    },
    "headline": "Strong investment — high topical relevance and clean editorial standards.",
    "primary_reason": "P1 topical relevance scored 0.85 and D4 editorial integrity scored 0.78, indicating this site publishes contextually aligned content with selective outbound linking.",
    "supporting_signals": [
      "Domain has 340 referring domains, supporting a meaningful authority transfer.",
      "Traffic trajectory is stable, indicating no recent algorithmic penalty."
    ],
    "conditions": [],
    "mode_qualifier": null,
    "confidence_rationale": "High — placement page crawled successfully, domain metrics available, all sampled pages reviewed.",
    "confidence": "high",
    "confidence_ceiling": "high",
    "data_quality": {}
  },
  "failed_reason": null,
  "data_quality": {
    "mode_detected": true,
    "placement_page_crawled": true,
    "article_samples": 0,
    "domain_samples": 3,
    "backlink_metrics_available": true,
    "domain_metrics_available": true,
    "section_inferred": false
  },
  "created_at": "2026-06-27T10:00:00Z",
  "started_at": "2026-06-27T10:00:01Z",
  "completed_at": "2026-06-27T10:00:47Z"
}
```

**Failed evaluation (status = `"failed"`):**

```json
{
  "opportunity_id": "...",
  "status": "failed",
  "failed_reason": "Data collection failed: Crawler timeout after 30s for https://example.com/seo-guide",
  "overall_outcome": null,
  "verdict": null,
  ...
}
```

#### Status Enum Values

| Status | Meaning |
|---|---|
| `queued` | Task created; pipeline not yet started |
| `detecting_mode` | Fetching prospect URL; classifying Mode A or B |
| `inferring_section` | Mode B / domain only: running Haiku section inference |
| `collecting_data` | Crawling pages and fetching DataForSEO signals |
| `classifying_signals` | Haiku Call 1: content classification and signal extraction |
| `computing_score` | Deterministic cluster scoring and Investment Score calculation |
| `assembling_verdict` | Haiku Call 2: investment verdict language assembly |
| `complete` | Evaluation finished; `verdict` and `overall_outcome` are populated |
| `failed` | Unrecoverable error; `failed_reason` describes the cause |

#### `overall_outcome` Enum Values

| Value | Meaning |
|---|---|
| `recommended` | Investment Score ≥ 68; Relevance ≥ 0.55; Risk multiplier ≥ 0.80; D4 ≥ 0.55 |
| `with_conditions` | Investment Score 48–67, or ≥ 68 with one named significant condition |
| `not_recommended` | Hard exclusion gate triggered, OR Score < 48, OR Risk < 0.55, OR D4 < 0.30, OR Relevance < 0.30 |
| `insufficient_data` | Required signals were unavailable; the `verdict` lists which signals are missing |

---

### `GET /opportunities/{opportunity_id}/stream`

Stream real-time progress events for an in-progress evaluation using Server-Sent Events (SSE).

#### Connection

Connect with `Accept: text/event-stream`. The connection stays open until the evaluation reaches a terminal state (`complete` or `failed`) or the stream timeout (300 seconds) is reached. Heartbeat events are sent every 2 seconds to keep the connection alive through proxies.

#### Event Types

| Event | When | `data` payload |
|---|---|---|
| `status_update` | On every state transition | `{"status": "<new_status>"}` |
| `complete` | When evaluation finishes | `{"outcome": "<outcome>", "investment_score": <float or null>}` |
| `failed` | On unrecoverable error | `{"reason": "<human-readable reason>"}` |
| `heartbeat` | Every 2 seconds | `{}` |

#### Example SSE Stream

```
event: status_update
data: {"status": "detecting_mode"}

event: status_update
data: {"status": "collecting_data"}

event: status_update
data: {"status": "classifying_signals"}

event: status_update
data: {"status": "computing_score"}

event: status_update
data: {"status": "assembling_verdict"}

event: complete
data: {"outcome": "recommended", "investment_score": 74.2}
```

#### Reconnection

The SSE endpoint does not support resumption from a specific event ID. On reconnect, the stream replays only future events. To get the current state, call `GET /opportunities/{id}` first, then connect to the stream.

---

## Stability Guarantee

Fields documented here will not be removed or renamed within a major API version. New optional fields may be added to responses without a version increment. Callers must ignore unknown fields.

Error codes documented here are stable. New error codes may be added for new validation rules, but existing codes will not be reassigned.
