import os
from typing import Any

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

RATE_LIMIT = os.environ.get("CLOUDSUFI_RATE_LIMIT", "10/minute")


def _rate_limit_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"key:{api_key}"
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key, default_limits=[RATE_LIMIT])


API_DESCRIPTION = """
# Cloudsufi Agentic Search

An agentic web-research API. Submit a natural-language query and receive
**structured JSON** built from authoritative web sources.

## Highlights

- **Agentic research** — the service performs multi-step web search and
  page-fetch on your behalf; no client-side tool loop is needed.
- **Bring your own schema** — pass a JSON Schema in `output_schema` and the
  response `data` field will conform to your shape exactly. No schema?
  A sensible default (`answer`, `key_points`, `sources`, `confidence`)
  is used.
- **Provenance built-in** — design your schema with `evidence` / `sources`
  arrays of `{claim, source_url}` to keep per-claim citations.
- **Vendor-agnostic surface** — the API never reveals the underlying model
  or provider, neither in successful responses nor in error messages.

## Authentication

Send your shared key in the `X-Api-Key` header:

```
X-Api-Key: your-shared-secret
```

Requests without a valid key (when one is configured server-side) return
`401 Invalid or missing API key`.

## Rate limiting

Per-key (or per-IP if no key is sent). Default `10/minute`. Configurable
server-side via the `CLOUDSUFI_RATE_LIMIT` environment variable. Exceeding
the limit returns `429 Rate limit exceeded`.
"""


tags_metadata = [
    {
        "name": "system",
        "description": "Operational endpoints — health and readiness checks.",
    },
    {
        "name": "research",
        "description": (
            "Agentic web-research endpoints. Submit a natural-language "
            "query; receive structured JSON conforming to either the "
            "default schema or a client-supplied JSON Schema."
        ),
    },
]


app = FastAPI(
    title="Cloudsufi Agentic Search",
    version="0.1.0",
    summary="Agentic web research with bring-your-own-schema structured output.",
    description=API_DESCRIPTION,
    contact={
        "name": "Cloudsufi Engineering",
        "email": "engineering@cloudsufi.com",
    },
    license_info={"name": "Proprietary"},
    openapi_tags=tags_metadata,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

client = anthropic.Anthropic()

MODEL = "claude-haiku-4-5"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Concise answer to the user's query.",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bullet-point key facts supporting the answer.",
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "snippet": {"type": "string"},
                },
                "required": ["url", "title"],
                "additionalProperties": False,
            },
            "description": "Sources used to construct the answer.",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": ["answer", "key_points", "sources", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a research assistant for the Cloudsufi Agentic Search service. "
    "Use the web_search and web_fetch tools to gather up-to-date, "
    "authoritative information before answering. Always cite the URLs you "
    "actually used. Prefer primary sources. If you cannot find reliable info, "
    "say so and lower the confidence. "
    "Never identify, name, describe, or hint at the underlying model, model "
    "family, provider, vendor, or AI service in any output field. If asked "
    "what you are, say only that you are 'the Cloudsufi Agentic Search "
    "assistant'."
)


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="The user's natural-language research query.",
        examples=["What were the top open-source AI releases in the last 30 days?"],
    )
    max_searches: int = Field(
        5,
        ge=1,
        le=15,
        description="Upper bound on the number of web searches the agent may perform for this query.",
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional JSON Schema describing the desired response shape. "
            "When supplied, the response `data` field will conform to this "
            "schema rather than the default. The schema must be a valid "
            "JSON Schema with `\"type\": \"object\"` at the root. Set "
            "`additionalProperties: false` and list `required` fields on "
            "every object for best adherence."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Default schema",
                    "value": {
                        "query": "What is the capital of France?",
                        "max_searches": 1,
                    },
                },
                {
                    "summary": "Custom schema — person profile with provenance",
                    "value": {
                        "query": "Find data on Jeremiah Smith, Ohio State wide receiver",
                        "max_searches": 4,
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "full_name": {"type": "string"},
                                "occupation": {"type": "string"},
                                "employer": {"type": "string"},
                                "evidence": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "claim": {"type": "string"},
                                            "source_url": {"type": "string"},
                                        },
                                        "required": ["claim", "source_url"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": [
                                "full_name",
                                "occupation",
                                "employer",
                                "evidence",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
            ]
        }
    }


class UsageInfo(BaseModel):
    input_tokens: int = Field(..., description="Tokens consumed processing the request.")
    output_tokens: int = Field(..., description="Tokens generated in the response.")
    stop_reason: str = Field(..., description="Why the agent stopped (e.g. `end_turn`, `max_tokens`).")


class SourceItem(BaseModel):
    url: str
    title: str
    snippet: str | None = None


class DefaultData(BaseModel):
    answer: str = Field(..., description="Concise answer to the user's query.")
    key_points: list[str] = Field(..., description="Bullet-point key facts supporting the answer.")
    sources: list[SourceItem] = Field(..., description="Sources used to construct the answer.")
    confidence: str = Field(..., description="One of `low`, `medium`, `high`.")


class QueryResponse(BaseModel):
    data: dict[str, Any] = Field(
        ...,
        description=(
            "The structured payload. When `output_schema` was supplied in "
            "the request, `data` conforms to that schema. Otherwise it "
            "matches the default schema (see `DefaultData`)."
        ),
    )
    usage: UsageInfo

    model_config = {
        "json_schema_extra": {
            "example": {
                "data": {
                    "answer": "The capital of France is Paris.",
                    "key_points": [
                        "Paris is located in north-central France along the Seine River.",
                        "It is the largest city in France and the seat of government.",
                    ],
                    "sources": [],
                    "confidence": "high",
                },
                "usage": {
                    "input_tokens": 2808,
                    "output_tokens": 76,
                    "stop_reason": "end_turn",
                },
            }
        }
    }


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])


class ErrorResponse(BaseModel):
    detail: str = Field(..., examples=["Invalid or missing API key"])


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Malformed or rejected request."},
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid `X-Api-Key`.",
        "content": {
            "application/json": {"example": {"detail": "Invalid or missing API key"}}
        },
    },
    422: {"description": "Request body failed validation."},
    429: {
        "model": ErrorResponse,
        "description": "Rate limit exceeded for this key (or IP).",
        "content": {
            "application/json": {"example": {"detail": "Rate limit exceeded"}}
        },
    },
    502: {
        "model": ErrorResponse,
        "description": "Transient upstream failure.",
        "content": {
            "application/json": {"example": {"detail": "Upstream service error."}}
        },
    },
}


def _extract_structured_output(content_blocks: list[Any]) -> dict[str, Any] | None:
    import json

    for block in content_blocks:
        if getattr(block, "type", None) == "text":
            text = block.text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        continue
    return None


def _verify_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("CLOUDSUFI_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get(
    "/health",
    tags=["system"],
    summary="Liveness check",
    description="Simple readiness probe. Returns `{\"status\": \"ok\"}` when the service is up.",
    response_model=HealthResponse,
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/query",
    tags=["research"],
    summary="Run an agentic web-research query",
    description=(
        "Performs agentic web research for the supplied `query` and returns "
        "structured JSON. If `output_schema` is provided, the response `data` "
        "field conforms to that schema; otherwise the default schema "
        "(`answer`, `key_points`, `sources`, `confidence`) is used.\n\n"
        "**Authentication:** `X-Api-Key` header (when configured server-side).\n\n"
        "**Rate limit:** `10/minute` per key by default; configurable via "
        "the `CLOUDSUFI_RATE_LIMIT` environment variable."
    ),
    response_model=QueryResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit(RATE_LIMIT)
def query(
    request: Request,
    req: QueryRequest,
    x_api_key: str | None = Header(
        default=None,
        description="Shared-secret API key. Required when `CLOUDSUFI_API_KEY` is set on the server.",
    ),
) -> dict[str, Any]:
    _verify_api_key(x_api_key)

    schema = req.output_schema if req.output_schema is not None else RESPONSE_SCHEMA

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": req.max_searches,
                    "allowed_callers": ["direct"],
                },
                {
                    "type": "web_fetch_20260209",
                    "name": "web_fetch",
                    "allowed_callers": ["direct"],
                },
            ],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": req.query}],
        )
    except anthropic.APIStatusError as e:
        status = e.status_code if 400 <= e.status_code < 600 else 502
        if status == 400:
            raise HTTPException(status_code=400, detail="Invalid request.")
        if status == 401 or status == 403:
            raise HTTPException(status_code=502, detail="Upstream service error.")
        if status == 429:
            raise HTTPException(status_code=429, detail="Service is busy. Retry shortly.")
        raise HTTPException(status_code=502, detail="Upstream service error.")
    except anthropic.APIError:
        raise HTTPException(status_code=502, detail="Upstream service error.")

    parsed = _extract_structured_output(response.content)
    if parsed is None:
        raise HTTPException(
            status_code=502,
            detail="Service did not return parseable structured output.",
        )

    return {
        "data": parsed,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
        },
    }
