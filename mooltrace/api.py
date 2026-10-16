"""HTTP API used by the demo UI. CI over JSONL fixtures is the primary workflow."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.routing import Route

from mooltrace import TAGLINE
from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.config import API_HOST, API_PORT, CORS_ORIGINS
from mooltrace.graph import get_graph
from mooltrace.mcp_http import mcp_asgi, mcp_lifespan
from mooltrace.public_demo import (
    PublicDemoRejected,
    execute_public_check,
    guard_public_check,
)
from mooltrace.ssrf import UnsafeURL
from mooltrace.rewrite import rewrite_answer
from mooltrace.trace import (
    check_answer,
    check_study,
    ro_cypher,
    shared_ancestors,
    trace_answer,
    what_rests_on,
)

app = FastAPI(
    title="MoolTrace",
    version="0.1.0",
    description=TAGLINE,
    lifespan=mcp_lifespan,
    redirect_slashes=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.router.routes.append(Route("/mcp", endpoint=mcp_asgi, methods=["GET", "POST", "DELETE"]))
app.router.routes.append(Route("/mcp/", endpoint=mcp_asgi, methods=["GET", "POST", "DELETE"]))


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


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _guard_public_demo(body: DraftIn, request: Request | None = None) -> None:
    client_ip = _client_ip(request) if request is not None else None
    try:
        guard_public_check(body.engine, body.text, body.urls, client_ip=client_ip)
    except PublicDemoRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except UnsafeURL as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/check-answer")
def post_check_answer(body: DraftIn, request: Request) -> dict:
    _guard_public_demo(body, request)

    def run() -> dict:
        return check_answer(body.text, body.urls, body.engine, body.depth)

    try:
        payload = execute_public_check(body.engine, body.text, body.urls, run)
    except PublicDemoRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc
    if payload.get("error_code") == "infra" or payload.get("exit_code") == 3:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "infra", "message": payload.get("summary"), "result": payload},
        )
    return payload


@app.post("/rewrite")
def post_rewrite(body: DraftIn, request: Request) -> dict:
    _guard_public_demo(body, request)
    try:
        return rewrite_answer(body.text, body.urls, body.engine, body.depth)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        raise _raise(exc) from exc


@app.post("/trace")
def post_trace(body: DraftIn, request: Request) -> dict:
    _guard_public_demo(body, request)
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
