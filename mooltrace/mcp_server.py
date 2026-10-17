"""MCP server. CI over JSONL fixtures is the primary product workflow.

check_answer remains available for editors. Errors raise ToolError so the
host sees is_error rather than a successful result dictionary.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field

from mooltrace import TAGLINE
from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.graph import get_graph
from mooltrace.ssrf import UnsafeURL
from mooltrace.rewrite import rewrite_answer as run_rewrite
from mooltrace.trace import (
    check_answer as run_check_answer,
    check_study as run_check_study,
    explain_path as run_explain,
    recheck_affected as run_recheck,
    ro_cypher as run_ro_cypher,
    shared_ancestors as run_shared,
    trace_answer as run_trace,
    what_rests_on as run_rests,
)

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover
    try:
        from mcp.shared.exceptions import McpError as ToolError
    except ImportError:  # pragma: no cover
        class ToolError(Exception):
            """Fallback when the installed MCP SDK has no ToolError."""


_READ_ONLY = ToolAnnotations(read_only_hint=True)

server = MCPServer(
    "mooltrace",
    title="MoolTrace",
    instructions=(
        f"{TAGLINE} Pre-merge check for health-AI answer fixtures. "
        "Prefer the CLI `mooltrace batch` in CI. "
        "check_answer returns pass, warn, or block with the FalkorDB path "
        "and the Cypher that produced it. "
        "Flag reliance on a publisher notice. Do not call the draft wrong, "
        "and do not call an Expression of Concern a retraction. "
        "Depth is 1..3. Depth 4 is not implemented."
    ),
)


def _raise(exc: Exception) -> None:
    if isinstance(exc, InfraError):
        raise ToolError(f"infra: {exc}") from exc
    raise ToolError(str(exc)) from exc


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except (MoolTraceError, UnsafeURL, InfraError) as exc:
        _raise(exc)
        raise
    except Exception as exc:
        reason = str(exc).splitlines()[0].strip()[:180] or type(exc).__name__
        raise ToolError(reason) from exc


@server.tool(
    description=(
        "Call this before shipping a health-AI draft. Pass the draft text and "
        "cited URLs. Returns pass (ships), warn (human review), or block "
        "(fail the build), plus the FalkorDB algo.SPpaths route and Cypher. "
        "warn: counted path to an Expression of Concern, unverified hop, "
        "unfinished check, or no verifiable source. "
        "block: counted path to a retraction, withdrawal, or removal. "
        "exit_code 3 is infrastructure failure. Depth 1-3."
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
    payload = _call(run_check_answer, text=text, urls=urls, engine=engine, depth=depth)
    if payload.get("exit_code") == 3:
        raise ToolError(payload.get("summary") or "infrastructure failure")
    return payload


@server.tool(
    description=(
        "Ingest a draft or its source URLs, expand RESTS_ON in FalkorDB, and "
        "return every path that ends on a publisher notice, plus the Cypher. "
        "Does not decide pass/warn/block."
    )
)
def trace_answer(
    text: Annotated[str, Field(description="Draft or fixture text to ingest.")] = "",
    urls: Annotated[
        list[str] | None, Field(description="Cited source URLs to walk from.")
    ] = None,
    engine: Annotated[
        str, Field(description="Engine or fixture name for this draft.")
    ] = "draft",
    depth: Annotated[
        int, Field(ge=1, le=3, description="Hop budget from 1 to 3.")
    ] = 2,
) -> dict:
    return _call(run_trace, text=text, urls=urls, engine=engine, depth=depth)


@server.tool(
    description=(
        "After check_answer returns warn or block, rewrite only the sentences "
        "whose citations reach the flagged study, then re-run the check. "
        "Keeps every other sentence. Discloses the publisher notice or an "
        "on-topic sibling already in this answer's graph. Never invents a "
        "citation. Returns the first check, the rewritten text, the recheck, "
        "and exit_code matching the recheck."
    )
)
def rewrite_answer(
    text: Annotated[str, Field(description="Draft that already failed the check.")] = "",
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
    return _call(run_rewrite, text=text, urls=urls, engine=engine, depth=depth, graph=get_graph())


@server.tool(
    description=(
        "Look up one DOI or PMID. Returns publisher notices on that study and "
        "works/sources already in the graph that cite it. "
        "OpenAlex is_retracted can be false for an Expression of Concern."
    )
)
def check_study(
    doi_or_pmid: Annotated[str, Field(description="DOI or PMID of one study.")],
) -> dict:
    return _call(run_check_study, identifier=doi_or_pmid)


@server.tool(
    description=(
        "Reverse impact after a notice changes. Given a notice DOI or a study "
        "DOI, return 'This Expression of Concern affects N stored answers' "
        "plus the counted answer ids (weighted PATH_RULE paths only). "
        "Then call recheck_affected to re-run those answers. "
        "This is not a monitoring or alert scheduler."
    )
)
def what_rests_on(
    doi: Annotated[str, Field(description="Notice DOI or study DOI to reverse from.")],
) -> dict:
    return _call(run_rests, doi=doi)


@server.tool(
    description=(
        "After what_rests_on, re-run check_answer on just the counted answers "
        "that rest on this notice. Use when a publisher notice changed and "
        "you need to know which shipped answers to revisit."
    )
)
def recheck_affected(
    doi: Annotated[str, Field(description="Notice DOI or study DOI to recheck from.")],
    depth: Annotated[
        int, Field(ge=1, le=3, description="Hop budget from 1 to 3.")
    ] = 2,
) -> dict:
    return _call(run_recheck, doi=doi, depth=depth)


@server.tool(
    description=(
        "Explain the deciding citation path. Same inputs as check_answer. "
        "Returns the algo.SPpaths call, path strength, hop sentences, and "
        "the Cypher that produced the verdict."
    )
)
def explain_path(
    text: Annotated[str, Field(description="Draft or fixture text to explain.")] = "",
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
    return _call(run_explain, text=text, urls=urls, engine=engine, depth=depth)


@server.tool(
    annotations=_READ_ONLY,
    description=(
        "Compare two drafts (by answer id or engine name) and return hub works "
        "that both use on a path to a publisher notice. First-hop counts are "
        "not a node-disjoint flow."
    ),
)
def shared_ancestors(
    answer_a: Annotated[str, Field(description="First answer id already in the graph.")] = "",
    answer_b: Annotated[str, Field(description="Second answer id already in the graph.")] = "",
    engine_a: Annotated[str, Field(description="Engine name if answer_a is omitted.")] = "",
    engine_b: Annotated[str, Field(description="Engine name if answer_b is omitted.")] = "",
) -> dict:
    return _call(
        run_shared,
        answer_a=answer_a,
        answer_b=answer_b,
        engine_a=engine_a,
        engine_b=engine_b,
    )


@server.tool(
    annotations=_READ_ONLY,
    description=(
        "Run read-only OpenCypher against the MoolTrace graph using FalkorDB "
        "GRAPH.RO_QUERY. Writes are rejected. A LIMIT is added when the query "
        "has RETURN and no LIMIT outside string literals. Rows are sliced to 50. "
        "timeout_ms is 100-15000."
    )
)
def ro_cypher(
    query: Annotated[str, Field(description="Read-only OpenCypher to run.")],
    timeout_ms: Annotated[
        int, Field(ge=100, le=15000, description="Query timeout in milliseconds, 100-15000.")
    ] = 3000,
) -> dict:
    return _call(run_ro_cypher, statement=query, timeout_ms=timeout_ms)


def main() -> None:
    try:
        get_graph()
    except Exception:
        pass
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
