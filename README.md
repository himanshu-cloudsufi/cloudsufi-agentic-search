# Cloudsufi Agentic Search

A minimal FastAPI service that exposes Claude (Haiku 4.5) with web search + web fetch as a structured-data query API.

## Setup

```bash
cd cloudsufi-agentic-search
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export CLOUDSUFI_API_KEY=some-shared-secret      # optional; if set, clients must send X-Api-Key
export CLOUDSUFI_RATE_LIMIT="10/minute"           # optional; default 10/minute per key (or IP)
```

## Run

```bash
uvicorn main:app --reload --port 8080
```

## Usage

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: some-shared-secret" \
  -d '{"query": "What were the top open-source AI releases in the last 30 days?"}'
```

### Response shape

```json
{
  "answer": "...",
  "key_points": ["..."],
  "sources": [{"url": "...", "title": "...", "snippet": "..."}],
  "confidence": "high",
  "usage": {"input_tokens": 1234, "output_tokens": 567, "stop_reason": "end_turn"}
}
```

## Notes

- Uses `claude-haiku-4-5` with server-side `web_search` + `web_fetch` tools (no client-side tool execution loop needed).
- Output is constrained via `output_config.format` (JSON schema), so responses are structured by construction.
- `max_searches` (1–15) bounds web_search calls per request. Default 5.
- Rate limiting via `slowapi` — keyed on `X-Api-Key` if present, otherwise client IP. Configure with `CLOUDSUFI_RATE_LIMIT` (e.g. `"30/minute"`, `"1000/hour"`). In-memory only — for multi-instance deploys, point slowapi at Redis.
- POC only — no persistence, no auth beyond a shared static key.
