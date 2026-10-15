from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

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
