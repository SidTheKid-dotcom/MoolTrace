from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

from mooltrace.clients import InfraError
from mooltrace.graph import Graph
from mooltrace.mcp_server import ToolError, ro_cypher, server


def test_mcp_ro_cypher_write_raises_tool_error(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        try:
            ro_cypher("CREATE (:Work {doi: '10.1/nope'})")
        except ToolError as exc:
            assert "read-only" in str(exc).lower()
            return
        raise AssertionError("MCP write was not a ToolError")
    finally:
        graph.close()


def test_mcp_ro_cypher_allows_set_in_string(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        payload = ro_cypher("MATCH (w:Work) WHERE w.title CONTAINS 'set' RETURN w.doi")
        assert "rows" in payload
        assert "LIMIT" in payload["cypher"].upper()
    finally:
        graph.close()


def test_mcp_client_inprocess_lists_tools_and_rejects_writes(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    async def run() -> None:
        async with Client(server) as client:
            listed = await client.list_tools()
            names = [tool.name for tool in listed.tools]
            assert "check_answer" in names
            assert "rewrite_answer" in names
            assert "ro_cypher" in names
            bad = await client.call_tool("ro_cypher", {"query": "CREATE (:Work {doi: '10.1/nope'})"})
            assert bad.is_error
            good = await client.call_tool(
                "ro_cypher",
                {"query": "MATCH (w:Work) WHERE w.title CONTAINS 'set' RETURN w.doi"},
            )
            assert not good.is_error

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_mcp_stdio_client_check_answer_and_ro_cypher(tmp_path: Path):
    db = tmp_path / "mooltrace.db"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "MOOLTRACE_DB": str(db),
        "MOOLTRACE_MAILTO": "mcp-test@example.com",
        "PYTHONUNBUFFERED": "1",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mooltrace.mcp_server"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    async def run() -> None:
        async with Client(params) as client:
            listed = await client.list_tools()
            names = [tool.name for tool in listed.tools]
            assert "check_answer" in names
            assert "rewrite_answer" in names
            ssrf = await client.call_tool(
                "check_answer",
                {
                    "text": "ssrf probe",
                    "urls": ["http://127.0.0.1/secret"],
                    "engine": "ssrf",
                    "depth": 1,
                },
            )
            assert not ssrf.is_error
            text = ssrf.content[0].text
            payload = json.loads(text)
            assert payload["decision"] == "warn"
            assert payload["exit_code"] == 2
            prose = await client.call_tool(
                "check_answer",
                {
                    "text": "Cinnamon may help blood sugar in some people.",
                    "engine": "prose",
                    "depth": 1,
                },
            )
            assert not prose.is_error
            prose_payload = json.loads(prose.content[0].text)
            assert prose_payload["decision"] == "warn"
            assert prose_payload["exit_code"] == 2
            assert prose_payload["error_code"] == "no_sources"
            assert prose_payload["reasons"][0]["code"] == "no_sources"
            assert prose_payload["works_cited"] == 0
            assert prose_payload["pitch"] is None
            write = await client.call_tool("ro_cypher", {"query": "MERGE (:Work {doi: '10.1/x'})"})
            assert write.is_error

    asyncio.run(run())


def _tool_schema(tool) -> dict:
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}


def _read_only(tool) -> bool | None:
    ann = tool.annotations
    if ann is None:
        return None
    if hasattr(ann, "read_only_hint"):
        return ann.read_only_hint
    if isinstance(ann, dict):
        return ann.get("readOnlyHint", ann.get("read_only_hint"))
    dumped = ann.model_dump(by_alias=True) if hasattr(ann, "model_dump") else {}
    return dumped.get("readOnlyHint", dumped.get("read_only_hint"))


def test_mcp_tool_schema_descriptions_depth_and_readonly(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    async def run() -> None:
        async with Client(server) as client:
            listed = await client.list_tools()
            by_name = {tool.name: tool for tool in listed.tools}
            assert set(by_name) >= {
                "check_answer",
                "rewrite_answer",
                "trace_answer",
                "check_study",
                "what_rests_on",
                "recheck_affected",
                "explain_path",
                "shared_ancestors",
                "ro_cypher",
            }
            for tool in listed.tools:
                props = (_tool_schema(tool).get("properties") or {})
                for name, spec in props.items():
                    assert spec.get("description"), f"{tool.name}.{name} missing description"
            for name in ("check_answer", "trace_answer"):
                depth = (_tool_schema(by_name[name]).get("properties") or {}).get("depth") or {}
                assert depth.get("minimum") == 1
                assert depth.get("maximum") == 3
            assert _read_only(by_name["ro_cypher"]) is True
            assert _read_only(by_name["shared_ancestors"]) is True
            assert _read_only(by_name["check_answer"]) is not True
            assert _read_only(by_name["rewrite_answer"]) is not True
            assert _read_only(by_name["trace_answer"]) is not True
            too_deep = await client.call_tool("check_answer", {"text": "x", "depth": 4})
            assert too_deep.is_error

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_mcp_graph_unavailable_is_error(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    def boom(*_args, **_kwargs):
        raise InfraError("graph backend unavailable")

    monkeypatch.setattr(graph, "work_row", boom)

    async def run() -> None:
        async with Client(server) as client:
            result = await client.call_tool("check_study", {"doi_or_pmid": "10.1234/unavailable"})
            assert result.is_error
            text = (result.content[0].text if result.content else "").lower()
            assert "graph backend unavailable" in text or "infra" in text

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_mcp_three_stdio_clients_share_one_db(tmp_path: Path):
    db = tmp_path / "mooltrace.db"
    seed = Graph(db)
    seed.merge_work("10.1/shared", title="keep")
    seed.close()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "MOOLTRACE_DB": str(db),
        "MOOLTRACE_MAILTO": "mcp-test@example.com",
        "PYTHONUNBUFFERED": "1",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mooltrace.mcp_server"],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    async def one() -> dict:
        async with Client(params) as client:
            hit = await client.call_tool(
                "ro_cypher",
                {"query": "MATCH (w:Work {doi: '10.1/shared'}) RETURN w.title AS title"},
            )
            assert not hit.is_error
            return json.loads(hit.content[0].text)

    async def run() -> None:
        payloads = await asyncio.gather(one(), one(), one())
        for payload in payloads:
            assert payload["rows"][0]["title"] == "keep"

    asyncio.run(run())
