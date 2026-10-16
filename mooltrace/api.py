"""HTTP API used by the demo UI. CI over JSONL fixtures is the primary workflow."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mooltrace import TAGLINE
from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.config import API_HOST, API_PORT, CORS_ORIGINS
from mooltrace.graph import get_graph
from mooltrace.ssrf import UnsafeURL, public_http_url
from mooltrace.public_demo import (
    draft_too_large,
    is_preset,
    public_demo_enabled,
    public_live_enabled,
    rate_limited,
)
from mooltrace.rewrite import rewrite_answer
from mooltrace.trace import (
    check_answer,
    check_study,
    ro_cypher,
    shared_ancestors,
    trace_answer,
    what_rests_on,
)

app = FastAPI(title="MoolTrace", version="0.1.0", description=TAGLINE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class DraftIn(BaseModel):
    text: str = ""
    urls: list[str] = Field(default_factory=list)
    engine: str = "draft"
    depth: int = Field(default=2, ge=1, le=3)


class StudyIn(BaseModel):
    doi_or_pmid: str


class SharedIn(BaseModel):
    answer_a: str = ""
    answer_b: str = ""
    engine_a: str = ""
    engine_b: str = ""


class CypherIn(BaseModel):
    query: str
    timeout_ms: int = Field(default=3000, ge=100, le=15000)


def _raise(exc: Exception) -> HTTPException:
    if isinstance(exc, InfraError):
        return HTTPException(
            status_code=503,
            detail={"error_code": "infra", "message": str(exc)},
        )
    if isinstance(exc, (MoolTraceError, UnsafeURL)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "product": "MoolTrace"}


@app.get("/stats")
def stats() -> dict:
    run = get_graph().counts()
    return {"counts": run.rows, "cypher": run.cypher, "elapsed_ms": round(run.elapsed_ms, 2)}


def _guard_public_demo(body: DraftIn) -> None:
    if not public_demo_enabled():
        return
    if is_preset(body.engine, body.text, body.urls):
        return
    if draft_too_large(body.text, body.urls):
        raise HTTPException(
            status_code=413,
            detail="Draft or URL list is too large for the public demo.",
        )
    if public_live_enabled():
        for url in body.urls or []:
            try:
                public_http_url(url, reason="url")
            except UnsafeURL as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    if rate_limited():
        raise HTTPException(status_code=429, detail="Public demo rate limit. Try the three presets.")
    if public_live_enabled():
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "This public demo only runs the three presets (Healthline olive oil block, "
            "Healthline cinnamon warn, clean pass) with no live page fetch. Clone the repo "
            "to check other URLs."
        ),
    )


@app.post("/check-answer")
def post_check_answer(body: DraftIn, request: Request) -> dict:
    _ = request
    _guard_public_demo(body)
    try:
        payload = check_answer(body.text, body.urls, body.engine, body.depth)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc
    if payload.get("error_code") == "infra" or payload.get("exit_code") == 3:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "infra", "message": payload.get("summary"), "result": payload},
        )
    return payload


@app.post("/rewrite")
def post_rewrite(body: DraftIn) -> dict:
    _guard_public_demo(body)
    try:
        return rewrite_answer(body.text, body.urls, body.engine, body.depth)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.post("/trace")
def post_trace(body: DraftIn) -> dict:
    _guard_public_demo(body)
    try:
        return trace_answer(body.text, body.urls, body.engine, body.depth)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.post("/check-study")
def post_check_study(body: StudyIn) -> dict:
    try:
        return check_study(body.doi_or_pmid)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.get("/rests-on")
def get_rests_on(doi: str) -> dict:
    try:
        return what_rests_on(doi)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.post("/shared")
def post_shared(body: SharedIn) -> dict:
    try:
        return shared_ancestors(body.answer_a, body.answer_b, body.engine_a, body.engine_b)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.post("/cypher")
def post_cypher(body: CypherIn) -> dict:
    try:
        return ro_cypher(body.query, body.timeout_ms)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
