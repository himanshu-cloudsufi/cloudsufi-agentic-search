# Cloudsufi Agentic Search

A FastAPI service that performs agentic web research and returns structured JSON. Clients can use the default response schema or supply their own JSON Schema per request to receive data in any shape they need.

## Features

- Agentic web research via server-side `web_search` + `web_fetch` (no client-side tool loop).
- Default structured response: `answer`, `key_points`, `sources`, `confidence`.
- **Bring-your-own schema**: clients pass a JSON Schema in the request and the response conforms to it.
- API-key auth (`X-Api-Key`) and per-key rate limiting.
- Provider-agnostic surface — the API does not expose the underlying model or vendor in any response or error.

## Setup

```bash
cd cloudsufi-agentic-search
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...                # required (server-side only, never returned to clients)
export CLOUDSUFI_API_KEY=some-shared-secret        # optional; if set, clients must send X-Api-Key
export CLOUDSUFI_RATE_LIMIT="10/minute"            # optional; default 10/minute per key (or IP)
```

A `.env` file in the project root is loaded automatically.

## Run

```bash
uvicorn main:app --reload --port 8080
```

## Interactive API docs

Once the service is running, the OpenAPI / Swagger documentation is available at:

| URL                          | Renders          |
|------------------------------|------------------|
| `http://localhost:8080/docs`     | Swagger UI    |
| `http://localhost:8080/redoc`    | ReDoc         |
| `http://localhost:8080/openapi.json` | Raw OpenAPI 3.1 spec |

A pre-generated copy of the spec is also committed at [`openapi.json`](./openapi.json) for offline use, Postman/Insomnia import, or client SDK generation.

## Endpoints

### `GET /health`

Liveness probe.

```json
{"status": "ok"}
```

### `POST /query`

Run an agentic web search and return structured data.

#### Request body

| Field           | Type           | Required | Description |
|-----------------|----------------|----------|-------------|
| `query`         | string         | yes      | Natural-language query. |
| `max_searches`  | integer (1–15) | no       | Max number of web searches the agent may perform. Default `5`. |
| `output_schema` | object         | no       | Optional JSON Schema describing the desired response shape. Must have `"type": "object"` at the root. When provided, `data` in the response conforms to this schema instead of the default. |

#### Response shape

All successful responses use this envelope:

```json
{
  "data": { ... },
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "stop_reason": "end_turn"
  }
}
```

`data` is either the **default schema** (below) or the schema the client supplied via `output_schema`.

#### Default `data` schema

```json
{
  "answer": "string — concise answer",
  "key_points": ["string", "..."],
  "sources": [
    {"url": "string", "title": "string", "snippet": "string (optional)"}
  ],
  "confidence": "low | medium | high"
}
```

## Usage

### Default schema

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: some-shared-secret" \
  -d '{"query": "What were the top open-source AI releases in the last 30 days?"}'
```

### Client-supplied schema

Pass a JSON Schema in `output_schema` and the response will be coerced to that shape. Example — a person profile with per-claim provenance:

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: some-shared-secret" \
  -d '{
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
  }'
```

Sample response:

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

### Schema authoring tips

- Root must be `"type": "object"`.
- Set `"additionalProperties": false` and list required fields on every object — this materially improves adherence.
- Prefer concrete types (`integer`, `string`, `boolean`) and `enum`s over free-form strings where possible.
- Describe each field with a `"description"` — the agent uses it to decide what to populate.
- For evidence/citations, model them as a `"sources"` or `"evidence"` array of `{claim, source_url}` objects so provenance is preserved.

## Errors

The API returns generic, provider-agnostic error messages. No upstream model name, provider name, or internal error text is leaked.

| Status | Detail                                              | Meaning |
|--------|-----------------------------------------------------|---------|
| 400    | `Invalid request.`                                   | Malformed request or rejected by upstream validation. |
| 401    | `Invalid or missing API key`                         | `CLOUDSUFI_API_KEY` is set on the server and the client did not send a matching `X-Api-Key`. |
| 429    | `Rate limit exceeded` / `Service is busy. Retry shortly.` | Local rate limit hit, or upstream throttling. |
| 502    | `Upstream service error.` / `Service did not return parseable structured output.` | Transient failure talking to the research backend. |

## Notes

- Output is constrained server-side via JSON Schema, so structured responses are guaranteed by construction (not by post-hoc parsing).
- `max_searches` (1–15) bounds the number of web searches per request. Default `5`.
- Rate limiting via `slowapi`, keyed on `X-Api-Key` if present, otherwise client IP. Configure with `CLOUDSUFI_RATE_LIMIT` (e.g. `"30/minute"`, `"1000/hour"`). In-memory only — for multi-instance deploys, point slowapi at Redis.
- The service identifies itself only as the "Cloudsufi Agentic Search assistant"; the underlying model and provider are never disclosed in responses or error messages.
- POC — no persistence, no auth beyond a shared static key, no per-tenant isolation.
