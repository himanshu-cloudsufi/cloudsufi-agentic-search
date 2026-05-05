# Cloudsufi Agentic Search — Client Guide

> A client-facing reference for integrating with the Cloudsufi Agentic Search API. Submit a natural-language query, get back **structured JSON** built from authoritative web sources.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Quickstart](#quickstart)
3. [Authentication](#authentication)
4. [Base URL & endpoints](#base-url--endpoints)
5. [The `/query` endpoint](#the-query-endpoint)
6. [Default response schema](#default-response-schema)
7. [Bring your own schema (`output_schema`)](#bring-your-own-schema-output_schema)
8. [Schema authoring guide](#schema-authoring-guide)
9. [Code samples](#code-samples)
10. [Errors](#errors)
11. [Rate limits](#rate-limits)
12. [Best practices](#best-practices)
13. [FAQ](#faq)

---

## What it does

You send a natural-language query (and optionally a JSON Schema describing the shape of the answer you want). The service performs agentic web research on your behalf — multi-step web search, page fetch, synthesis — and returns a single structured JSON response.

Two modes:

- **Default mode** — return an answer, key points, sources, and a confidence rating. Great for general Q&A.
- **Schema-driven mode** — supply a JSON Schema and the response `data` field will conform to it exactly. Great for entity extraction, profile assembly, structured intelligence pipelines.

---

## Quickstart

```bash
curl -X POST https://YOUR-HOST/query \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_KEY" \
  -d '{"query": "What is the capital of France?"}'
```

Response:

```json
{
  "data": {
    "answer": "The capital of France is Paris.",
    "key_points": ["Paris is located in north-central France along the Seine River.", "..."],
    "sources": [],
    "confidence": "high"
  },
  "usage": {"input_tokens": 2808, "output_tokens": 76, "stop_reason": "end_turn"}
}
```

---

## Authentication

Every request must include your shared API key in the `X-Api-Key` header.

```
X-Api-Key: your-shared-secret
```

A missing or wrong key returns:

```json
{"detail": "Invalid or missing API key"}
```

with HTTP `401`. Treat the key like a password — keep it server-side, do not embed in mobile/web clients.

---

## Base URL & endpoints

Your account-specific base URL is provided by Cloudsufi at provisioning time. In the examples below, replace `https://YOUR-HOST` with the URL you were issued.

| Method | Path             | Purpose                              |
|--------|------------------|--------------------------------------|
| `GET`  | `/health`        | Liveness probe (no auth required)    |
| `POST` | `/query`         | Run an agentic research query        |
| `GET`  | `/docs`          | Interactive Swagger UI               |
| `GET`  | `/redoc`         | ReDoc reference                      |
| `GET`  | `/openapi.json`  | OpenAPI 3.1 spec (for SDK generation) |

---

## The `/query` endpoint

### Request body

| Field           | Type           | Required | Default | Description |
|-----------------|----------------|----------|---------|-------------|
| `query`         | string         | yes      | —       | Natural-language research query (≥ 1 char). |
| `max_searches`  | integer 1–15   | no       | `5`     | Upper bound on the number of web searches the agent may perform for this query. Higher = more thorough but slower and more expensive. |
| `output_schema` | object (JSON Schema) | no | `null` | Custom JSON Schema describing the desired response shape. When supplied, the response `data` field conforms to this schema. |

### Response envelope

Every successful response uses this envelope:

```json
{
  "data":  { /* either default schema or your output_schema */ },
  "usage": { "input_tokens": 0, "output_tokens": 0, "stop_reason": "end_turn" }
}
```

`usage` is always present and reports request accounting. `data` is whichever shape you asked for.

---

## Default response schema

When `output_schema` is omitted, `data` is shaped as:

```json
{
  "answer":      "string — concise answer to the query",
  "key_points":  ["string", "..."],
  "sources":     [
    {"url": "string", "title": "string", "snippet": "string (optional)"}
  ],
  "confidence":  "low | medium | high"
}
```

`confidence` reflects the agent's self-assessed reliability based on how authoritative and consistent the sources were. Treat `low` as "needs human review."

---

## Bring your own schema (`output_schema`)

For structured intelligence — profiles, comparisons, datasets — pass a JSON Schema describing exactly what you want. The service will populate every required field and return data conforming to your schema.

### Example — person profile with provenance

**Request:**

```json
{
  "query": "Find data on Jeremiah Smith, Ohio State wide receiver",
  "max_searches": 4,
  "output_schema": {
    "type": "object",
    "properties": {
      "full_name":  {"type": "string"},
      "occupation": {"type": "string"},
      "employer":   {"type": "string"},
      "physical": {
        "type": "object",
        "properties": {
          "height": {"type": "string"},
          "weight": {"type": "string"}
        },
        "required": ["height", "weight"],
        "additionalProperties": false
      },
      "career_stats": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "season":     {"type": "string"},
            "receptions": {"type": "integer"},
            "yards":      {"type": "integer"},
            "touchdowns": {"type": "integer"}
          },
          "required": ["season", "receptions", "yards", "touchdowns"],
          "additionalProperties": false
        }
      },
      "evidence": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "claim":      {"type": "string"},
            "source_url": {"type": "string"}
          },
          "required": ["claim", "source_url"],
          "additionalProperties": false
        }
      }
    },
    "required": ["full_name", "occupation", "employer", "physical", "career_stats", "evidence"],
    "additionalProperties": false
  }
}
```

**Response:**

```json
{
  "data": {
    "full_name": "Jeremiah Smith",
    "occupation": "College Football Player",
    "employer": "Ohio State University",
    "physical": {"height": "6'3\"", "weight": "223 lbs"},
    "career_stats": [
      {"season": "2024", "receptions": 76, "yards": 1315, "touchdowns": 15},
      {"season": "2025", "receptions": 87, "yards": 1243, "touchdowns": 12}
    ],
    "evidence": [
      {"claim": "...", "source_url": "https://..."}
    ]
  },
  "usage": {"input_tokens": 44417, "output_tokens": 716, "stop_reason": "end_turn"}
}
```

### Example — company profile

```json
{
  "query": "Find data on Acme Robotics, the industrial automation company",
  "max_searches": 3,
  "output_schema": {
    "type": "object",
    "properties": {
      "name":             {"type": "string"},
      "industry":         {"type": "string"},
      "headquarters":     {"type": "string"},
      "founded_year":     {"type": "integer"},
      "founders":         {"type": "array", "items": {"type": "string"}},
      "ceo":              {"type": "string"},
      "primary_products": {"type": "array", "items": {"type": "string"}},
      "evidence": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "claim":      {"type": "string"},
            "source_url": {"type": "string"}
          },
          "required": ["claim", "source_url"],
          "additionalProperties": false
        }
      }
    },
    "required": ["name", "industry", "headquarters", "founded_year", "founders", "ceo", "primary_products", "evidence"],
    "additionalProperties": false
  }
}
```

---

## Schema authoring guide

A few rules dramatically improve adherence and quality:

1. **Root must be an object.** `"type": "object"` at the top level — arrays or primitives at the root are rejected.
2. **List `required` fields on every object.** Optional fields are populated only sometimes; required fields are always populated.
3. **Set `"additionalProperties": false`** on every object. Without it, the agent may invent extra fields.
4. **Prefer concrete types over strings.** Use `integer`, `number`, `boolean`, and `enum` when the value is bounded — `"confidence": {"type": "string", "enum": ["low","medium","high"]}` is far more reliable than a free-form string.
5. **Write a `description` for each field.** The agent uses it to decide what to populate. `{"type": "string", "description": "Founder's full legal name"}` produces sharper outputs than a bare type.
6. **Model provenance explicitly.** Add an `evidence` or `sources` array of `{claim, source_url}` objects. This makes downstream verification trivial and forces the agent to ground its claims.
7. **Keep schemas focused.** A single rich schema (15–25 fields, deeply structured) outperforms a sprawling schema (60+ fields) — the agent has a fixed research budget per query.
8. **Use `format` hints sparingly.** `"format": "uri"`, `"format": "date"` are honored as soft hints, not strict validators.

---

## Code samples

### cURL

```bash
curl -X POST https://YOUR-HOST/query \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $CLOUDSUFI_KEY" \
  -d @request.json
```

### Python (`requests`)

```python
import os
import requests

resp = requests.post(
    "https://YOUR-HOST/query",
    headers={"X-Api-Key": os.environ["CLOUDSUFI_KEY"]},
    json={
        "query": "Find data on Acme Robotics",
        "max_searches": 3,
        "output_schema": {
            "type": "object",
            "properties": {
                "name":         {"type": "string"},
                "headquarters": {"type": "string"},
                "founded_year": {"type": "integer"},
            },
            "required": ["name", "headquarters", "founded_year"],
            "additionalProperties": False,
        },
    },
    timeout=120,
)
resp.raise_for_status()
payload = resp.json()
print(payload["data"])
print("tokens:", payload["usage"])
```

### Node.js (`fetch`)

```javascript
const res = await fetch("https://YOUR-HOST/query", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Api-Key": process.env.CLOUDSUFI_KEY,
  },
  body: JSON.stringify({
    query: "Find data on Acme Robotics",
    max_searches: 3,
    output_schema: {
      type: "object",
      properties: {
        name: { type: "string" },
        headquarters: { type: "string" },
        founded_year: { type: "integer" },
      },
      required: ["name", "headquarters", "founded_year"],
      additionalProperties: false,
    },
  }),
});
if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
const { data, usage } = await res.json();
console.log(data, usage);
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "net/http"
    "os"
)

func main() {
    body, _ := json.Marshal(map[string]any{
        "query":        "Find data on Acme Robotics",
        "max_searches": 3,
    })
    req, _ := http.NewRequest("POST", "https://YOUR-HOST/query", bytes.NewReader(body))
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("X-Api-Key", os.Getenv("CLOUDSUFI_KEY"))

    resp, err := http.DefaultClient.Do(req)
    if err != nil { panic(err) }
    defer resp.Body.Close()

    var out struct {
        Data  map[string]any `json:"data"`
        Usage map[string]any `json:"usage"`
    }
    json.NewDecoder(resp.Body).Decode(&out)
    fmt.Printf("%+v\n", out)
}
```

### Postman / Insomnia

Import the OpenAPI spec at `https://YOUR-HOST/openapi.json` to auto-generate a fully-typed collection with example requests for both default-schema and custom-schema flows.

---

## Errors

All errors follow the shape:

```json
{"detail": "human-readable message"}
```

| Status | Detail                                              | When you'll see it |
|--------|-----------------------------------------------------|---------------------|
| `400`  | `Invalid request.`                                   | Upstream rejected the request — usually a malformed `output_schema`. |
| `401`  | `Invalid or missing API key`                         | `X-Api-Key` header missing or wrong. |
| `422`  | (per-field validation errors)                        | Request body failed validation. The `detail` is an array of field errors. |
| `429`  | `Rate limit exceeded` *or* `Service is busy. Retry shortly.` | You exceeded your per-key rate limit, or the upstream is throttling. **Retry with backoff.** |
| `502`  | `Upstream service error.` *or* `Service did not return parseable structured output.` | Transient upstream failure. **Retry.** |

**No error message ever exposes the underlying model or vendor** — both successful responses and error payloads are fully vendor-agnostic.

### Recommended retry policy

- `429` and `502`: exponential backoff (e.g. 1s, 2s, 4s, 8s) with jitter, max 4 retries.
- `400`, `401`, `422`: do not retry — fix the request.

---

## Rate limits

Limits are applied **per API key** (or per source IP if no key is supplied). The default ceiling is `10 requests / minute` and is configurable per tenant.

When you hit the limit you receive `429 Rate limit exceeded`. The window is rolling — wait, then retry.

If you need a higher tier (bursts, batch jobs, monitoring workloads), contact Cloudsufi to upgrade your key.

---

## Best practices

- **Cache aggressively.** If you query the same entity repeatedly, cache the response — the data does not change between back-to-back calls.
- **Right-size `max_searches`.** Default `5` is good for general queries. Bump to `10–15` for hard-to-find or niche topics; drop to `1–2` for lookups you already know are well-indexed.
- **Always include an `evidence` array in custom schemas.** Per-claim citations make downstream review and compliance dramatically easier.
- **Validate the response** against your own JSON Schema client-side. The service makes a strong best-effort to conform, but defensive validation is cheap insurance.
- **Set request timeouts ≥ 120 seconds.** A deep `max_searches=15` query can take 60s+ to complete.
- **Never embed your API key in a browser/mobile app.** Proxy through your own backend.

---

## FAQ

**Q: What language model powers this?**
The service is intentionally vendor-agnostic — neither the API nor the documentation discloses the underlying model or provider. This insulates you from upstream changes; we may swap the engine over time without breaking your contract.

**Q: How fresh is the data?**
The agent searches the live web on every request, so results reflect the most recent indexed information available. There is no static knowledge cutoff baked into responses.

**Q: Can I get streaming responses?**
Not in this version. The endpoint is request/response. If you need streaming or long-running async jobs (with webhook callbacks), reach out — it's on the roadmap.

**Q: Can I supply multiple queries in one request?**
Not yet — one query per request. Issue them in parallel from your client (subject to your rate limit) for batch workloads.

**Q: What about PII / sensitive data?**
Queries are processed transiently and not retained for training. Do not include credentials, secrets, or restricted PII in the `query` field.

**Q: How do I generate a typed SDK?**
Pull `https://YOUR-HOST/openapi.json` and feed it to [openapi-generator](https://openapi-generator.tech/), [openapi-typescript](https://github.com/drwpow/openapi-typescript), or your tool of choice.

---

## Support

- **Interactive docs:** `https://YOUR-HOST/docs`
- **OpenAPI spec:** `https://YOUR-HOST/openapi.json`
- **Engineering contact:** engineering@cloudsufi.com
