"""Read-only streamable-HTTP MCP for the hosted demo.

Only what_rests_on, check_answer, and recheck_affected. Local stdio still
serves the full tool list from mooltrace.mcp_server.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.types import Receive, Scope, Send

from mooltrace import TAGLINE
from mooltrace.mcp_server import ToolError, _call
from mooltrace.public_demo import (
    PublicDemoRejected,
    execute_public_check,
    guard_remote_check,
    guard_remote_doi,
)
from mooltrace.ssrf import UnsafeURL
from mooltrace.trace import (
    check_answer as run_check_answer,
    recheck_affected as run_recheck,
    what_rests_on as run_rests,
)

PUBLIC_MCP_HOST = "mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com"

remote_server = MCPServer(
    "mooltrace",
    title="MoolTrace",
    instructions=(
        f"{TAGLINE} Read-only public MCP. Tools: check_answer, what_rests_on, "
        "recheck_affected. The hosted demo runs the four recorded presets and, "
        "when live fetch is on, one allow-listed consumer-health or scholarly "
        "URL. Flag reliance on a publisher notice. Do not call "
        "the draft wrong, and do not call an Expression of Concern a retraction. "
        "Depth is 1..3."
    ),
)


def _guarded(fn, **kwargs):
    try:
        return fn(**kwargs)
    except PublicDemoRejected as exc:
        raise ToolError(exc.detail) from exc
    except UnsafeURL as exc:
        raise ToolError(str(exc)) from exc


@remote_server.tool(
    description=(
        "Call this before shipping a health-AI draft. Pass the draft text and "
        "cited URLs. Returns pass (ships), warn (human review), or block "
        "(fail the build), plus the FalkorDB algo.SPpaths route and Cypher. "
        "The public endpoint runs the four recorded presets, or one allow-listed "
        "URL (healthline.com, everydayhealth.com, verywellhealth.com, "
        "medicalnewstoday.com, webmd.com, pubmed.ncbi.nlm.nih.gov, doi.org) "
        "when live fetch is on. Depth 1-3."
    )
)
def check_answer(
    text: Annotated[str, Field(description="Draft or fixture text to check.")] = "",
    urls: Annotated[
        list[str] | None, Field(description="Cited source URLs from the draft.")
    ] = None,
    engine: Annotated[
        str, Field(description="Engine or fixture name for this draft.")
    ] = "draft",
    depth: Annotated[
        int, Field(ge=1, le=3, description="Hop budget from 1 to 3.")
    ] = 2,
) -> dict:
    _guarded(guard_remote_check, engine=engine, text=text, urls=urls)
    payload = _guarded(
        lambda: execute_public_check(
            engine,
            text,
            urls,
            lambda: _call(run_check_answer, text=text, urls=urls, engine=engine, depth=depth),
        )
    )
    if payload.get("exit_code") == 3:
        raise ToolError(payload.get("summary") or "infrastructure failure")
    return payload


@remote_server.tool(
    description=(
        "Reverse impact after a notice changes. Given a notice DOI or a study "
        "DOI, return 'This Expression of Concern affects N stored answers' "
        "plus the counted answer ids. The public endpoint only looks up notice "
        "DOIs from the four recorded presets unless live fetch is on."
    )
)
def what_rests_on(
    doi: Annotated[str, Field(description="Notice DOI or study DOI to reverse from.")],
) -> dict:
    _guarded(guard_remote_doi, doi=doi)
    return _call(run_rests, doi=doi)


@remote_server.tool(
    description=(
        "After what_rests_on, re-run check_answer on just the counted answers "
        "that rest on this notice. The public endpoint only accepts notice DOIs "
        "from the four recorded presets unless live fetch is on."
    )
)
def recheck_affected(
    doi: Annotated[str, Field(description="Notice DOI or study DOI to recheck from.")],
    depth: Annotated[
        int, Field(ge=1, le=3, description="Hop budget from 1 to 3.")
    ] = 2,
) -> dict:
    _guarded(guard_remote_doi, doi=doi)
    return _call(run_recheck, doi=doi, depth=depth)


def transport_security() -> TransportSecuritySettings:
    host = PUBLIC_MCP_HOST
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "testserver",
            "testserver:*",
            host,
            f"{host}:*",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            f"https://{host}",
        ],
    )


class RemoteMCPASGI:
    """ASGI wrapper so each API lifespan gets a fresh session manager."""

    def __init__(self) -> None:
        self.manager: StreamableHTTPSessionManager | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.manager is None:
            from starlette.responses import PlainTextResponse

            await PlainTextResponse("MCP not ready", status_code=503)(scope, receive, send)
            return
        await self.manager.handle_request(scope, receive, send)


mcp_asgi = RemoteMCPASGI()


@asynccontextmanager
async def mcp_lifespan(_app: Any) -> AsyncIterator[None]:
    manager = StreamableHTTPSessionManager(
        app=remote_server._lowlevel_server,
        json_response=True,
        stateless=False,
        security_settings=transport_security(),
        max_request_body_size=200_000,
    )
    mcp_asgi.manager = manager
    async with manager.run():
        yield
    mcp_asgi.manager = None
