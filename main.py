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

app = FastAPI(title="Cloudsufi Agentic Search", version="0.1.0")
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
    "You are a research assistant. Use the web_search and web_fetch tools to "
    "gather up-to-date, authoritative information before answering. Always "
    "cite the URLs you actually used. Prefer primary sources. If you cannot "
    "find reliable info, say so and lower the confidence."
)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's natural-language query.")
    max_searches: int = Field(5, ge=1, le=15)


class Source(BaseModel):
    url: str
    title: str
    snippet: str | None = None


class QueryResponse(BaseModel):
    answer: str
    key_points: list[str]
    sources: list[Source]
    confidence: str
    usage: dict[str, Any]


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
@limiter.limit(RATE_LIMIT)
def query(
    request: Request,
    req: QueryRequest,
    x_api_key: str | None = Header(default=None),
) -> QueryResponse:
    _verify_api_key(x_api_key)

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
                },
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            output_config={
                "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
            },
            messages=[{"role": "user", "content": req.query}],
        )
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {e}")

    parsed = _extract_structured_output(response.content)
    if parsed is None:
        raise HTTPException(
            status_code=502,
            detail="Model did not return parseable structured output.",
        )

    return QueryResponse(
        **parsed,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
        },
    )
