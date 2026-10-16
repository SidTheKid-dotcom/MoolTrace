"""Remote streamable-HTTP MCP: three read-only tools, public-demo guards."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp.client.client import Client

from mooltrace.config import ROOT
from mooltrace.graph import Graph
from mooltrace.public_demo import seed_offline_presets
from mooltrace.seed import load_demo_fixtures


REMOTE_TOOLS = {"what_rests_on", "check_answer", "recheck_affected"}
OLIVE_NOTICE = "10.1056/nejmc1806491"


def _loopback_ready() -> bool:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = int(sock.getsockname()[1])
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _ensure_loopback() -> None:
    if _loopback_ready():
        return
    subprocess.run(["ip", "link", "set", "lo", "up"], check=False, capture_output=True)
    if not _loopback_ready():
        pytest.skip("loopback is unavailable in this network namespace")


def test_remote_mcp_module_exists():
    from mooltrace.mcp_http import remote_server

    assert remote_server is not None


def test_remote_mcp_lists_only_three_tools(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mcp-http.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    from mooltrace.mcp_http import remote_server

    async def run() -> list[str]:
        async with Client(remote_server) as client:
            listed = await client.list_tools()
            return [tool.name for tool in listed.tools]

    try:
        names = asyncio.run(run())
        assert set(names) == REMOTE_TOOLS
        assert "rewrite_answer" not in names
        assert "ro_cypher" not in names
        assert "trace_answer" not in names
    finally:
        graph.close()


def test_remote_mcp_presets_never_429_after_rate_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    from mooltrace import public_demo
    from mooltrace.mcp_http import remote_server

    public_demo._hits.clear()
    graph = Graph(tmp_path / "mcp-http.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    cap = int(getattr(public_demo, "PUBLIC_LIVE_PER_MIN", 10))

    async def run() -> None:
        async with Client(remote_server) as client:
            for i in range(cap):
                burned = await client.call_tool(
                    "check_answer",
                    {
                        "text": f"not a preset {i}",
                        "urls": [f"https://example.com/other-{i}"],
                        "engine": "other",
                        "depth": 1,
                    },
                )
                assert burned.is_error
                text = (burned.content[0].text if burned.content else "").lower()
                assert "rate limit" in text or "preset" in text or "too large" in text
            extra = await client.call_tool(
                "check_answer",
                {
                    "text": "still not a preset",
                    "urls": ["https://example.com/other-extra"],
                    "engine": "other",
                    "depth": 1,
                },
            )
            assert extra.is_error
            assert "rate limit" in (extra.content[0].text if extra.content else "").lower()
            warn = load_demo_fixtures()[1]
            preset = await client.call_tool(
                "check_answer",
                {
                    "text": warn["text"],
                    "urls": warn["urls"],
                    "engine": warn["engine"],
                    "depth": 2,
                },
            )
            assert not preset.is_error, preset.content[0].text if preset.content else preset
            payload = json.loads(preset.content[0].text)
            assert payload["decision"] == "warn"

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_remote_mcp_rejects_oversized_draft(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    from mooltrace import public_demo
    from mooltrace.mcp_http import remote_server

    public_demo._hits.clear()
    graph = Graph(tmp_path / "mcp-http.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    async def run() -> None:
        async with Client(remote_server) as client:
            result = await client.call_tool(
                "check_answer",
                {
                    "text": "a" * 100_001,
                    "urls": ["https://www.healthline.com/nutrition/cinnamon-and-diabetes"],
                    "engine": "oversize",
                    "depth": 1,
                },
            )
            assert result.is_error
            assert "too large" in (result.content[0].text if result.content else "").lower()

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_remote_mcp_ssrf_url_is_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.setenv("MOOLTRACE_PUBLIC_LIVE", "1")
    from mooltrace import public_demo
    from mooltrace.mcp_http import remote_server

    public_demo._hits.clear()
    graph = Graph(tmp_path / "mcp-http.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    async def run() -> None:
        async with Client(remote_server) as client:
            result = await client.call_tool(
                "check_answer",
                {
                    "text": "ssrf probe",
                    "urls": ["http://127.0.0.1/secret"],
                    "engine": "ssrf",
                    "depth": 1,
                },
            )
            assert result.is_error
            text = (result.content[0].text if result.content else "").lower()
            assert "not public" in text or "refused" in text or "loopback" in text or "host" in text

    try:
        asyncio.run(run())
    finally:
        graph.close()


def test_api_mounts_mcp_route():
    from mooltrace.api import app

    mounted = any("/mcp" in str(getattr(route, "path", route)) for route in app.routes)
    assert mounted
    with TestClient(app, follow_redirects=False) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={"accept": "application/json, text/event-stream"},
        )
        assert response.status_code not in {307, 308}, response.headers.get("location")
        assert response.status_code != 404
        assert response.status_code < 500


def test_next_config_rewrites_mcp():
    text = (ROOT / "web" / "next.config.ts").read_text()
    assert 'source: "/mcp"' in text or 'source: "/mcp/:path*"' in text
    assert "/mcp" in text


def test_readme_and_judges_document_remote_and_local_mcp():
    readme = (ROOT / "README.md").read_text()
    judges = (ROOT / "JUDGES.md").read_text()
    assert "/mcp" in readme
    assert "mooltrace.mcp_server" in readme
    assert "what_rests_on" in readme
    assert "/mcp" in judges
    assert "check_answer" in judges
    assert "mooltrace.mcp_server" in judges


def test_remote_mcp_http_client_check_answer_and_what_rests_on(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    monkeypatch.setenv("MOOLTRACE_MAILTO", "mcp-http-test@example.com")
    db = tmp_path / "mcp-http.db"
    monkeypatch.setattr("mooltrace.config.DB_PATH", db)
    from mooltrace import public_demo
    from mooltrace.api import app

    public_demo._hits.clear()
    graph = Graph(db)
    seed_offline_presets(graph)
    graph.persist()
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.graph.get_graph", lambda: graph)

    import uvicorn

    _ensure_loopback()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not getattr(server, "started", False) and time.time() < deadline:
        time.sleep(0.05)
    if not getattr(server, "started", False):
        pytest.fail("uvicorn did not start")
    url = f"http://127.0.0.1:{port}/mcp"
    warn = load_demo_fixtures()[1]

    async def run() -> tuple[dict, dict]:
        async with Client(url, read_timeout_seconds=30) as client:
            listed = await client.list_tools()
            names = [tool.name for tool in listed.tools]
            assert set(names) == REMOTE_TOOLS
            checked = await client.call_tool(
                "check_answer",
                {
                    "text": warn["text"],
                    "urls": warn["urls"],
                    "engine": warn["engine"],
                    "depth": 2,
                },
            )
            assert not checked.is_error, checked.content[0].text if checked.content else checked
            rests = await client.call_tool("what_rests_on", {"doi": OLIVE_NOTICE})
            assert not rests.is_error, rests.content[0].text if rests.content else rests
            return json.loads(checked.content[0].text), json.loads(rests.content[0].text)

    try:
        health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert health.status_code == 200
        checked, rests = asyncio.run(run())
        assert checked["decision"] == "warn"
        assert rests["query_doi"] == OLIVE_NOTICE
        assert "stored" in (rests.get("summary") or "").lower()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        graph.close()
