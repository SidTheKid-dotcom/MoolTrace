"""Each verdict hop carries a source URL, UTC fetch date, and SHA-256 of the body."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from mcp.client.client import Client

from mooltrace.api import app
from mooltrace.clients import CallStats
from mooltrace.graph import Graph
from mooltrace.mcp_server import server
from mooltrace.trace import check_answer

PAGE_URL = "https://example.com/nutrition/olive-oil"
PAGE_HTML = (
    "<html><body><p>Olive oil benefits are reviewed in Estruch 2013 "
    "PREDIMED (10.1056/nejmoa1200303) among Mediterranean diet trials.</p></body></html>"
)
PAGE_FETCHED = "2026-10-16T13:43:11+00:00"
WORK_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML"
WORK_XML = "<article><body>Estruch et al. PREDIMED primary analysis.</body></article>"
WORK_FETCHED = "2026-10-15T15:27:28+00:00"
SILVA = "10.3390/nu14132773"
ESTRUCH = "10.1056/nejmoa1200303"
NOTICE = "10.1056/nejmc1806491"
ENGINE = "trail-test"
NOW = "2026-10-16T08:00:00+00:00"

PAGE_HASH = hashlib.sha256(PAGE_HTML.encode("utf-8")).hexdigest()
WORK_HASH = hashlib.sha256(WORK_XML.encode("utf-8")).hexdigest()


def _utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0
    return parsed


def _assert_hop_trail(hop: dict, *, url: str, fetched_at: str, content_hash: str) -> None:
    assert hop.get("source_url") == url
    assert hop.get("fetched_at") == fetched_at
    _utc_iso(str(hop.get("fetched_at")))
    assert hop.get("content_hash") == content_hash
    assert len(str(hop.get("content_hash"))) == 64
    assert set(str(hop.get("content_hash"))) <= set("0123456789abcdef")


def _offline_check(monkeypatch) -> None:
    monkeypatch.setattr("mooltrace.trace.judge_citation_edges", lambda *a, **k: None)
    monkeypatch.setattr("mooltrace.trace.expand_work", lambda *a, **k: None)
    monkeypatch.setattr("mooltrace.trace.notice_check", lambda *a, **k: None)

    def no_fetch(*_a, **_k):
        raise AssertionError("live HTTP is not allowed in this test")

    monkeypatch.setattr("mooltrace.trace.fetch_page", no_fetch)


def _seed_two_hop(graph: Graph) -> None:
    from mooltrace.trace import _answer_id

    answer_id = _answer_id(ENGINE, "", [PAGE_URL])
    graph.merge_answer(answer_id, ENGINE, "hash", NOW)
    graph.merge_source(PAGE_URL, "Olive oil page", "example.com", True, fetched_at=PAGE_FETCHED)
    graph.cite(answer_id, PAGE_URL)
    graph.merge_work(SILVA, title="Silva 2022", year=2022, expanded=True, notice_checked=True)
    graph.merge_work(ESTRUCH, title="Estruch 2013", year=2013, expanded=True, notice_checked=True)
    graph.source_rests_on(PAGE_URL, SILVA)
    graph.rest_on(SILVA, ESTRUCH)
    graph.set_reliance(
        None,
        PAGE_URL,
        SILVA,
        reliance="mention",
        weight=0.55,
        sentence="Olive oil benefits are reviewed in Estruch 2013 PREDIMED.",
        evidence_from="page",
        evidence_url=PAGE_URL,
        evidence_fetched_at=PAGE_FETCHED,
        evidence_sha256=PAGE_HASH,
    )
    graph.set_reliance(
        SILVA,
        None,
        ESTRUCH,
        reliance="mention",
        weight=0.55,
        sentence="Estruch et al. PREDIMED primary analysis.",
        evidence_from="europepmc_xml",
        evidence_url=WORK_URL,
        evidence_fetched_at=WORK_FETCHED,
        evidence_sha256=WORK_HASH,
    )
    graph.merge_notice(
        NOTICE,
        ESTRUCH,
        "retraction",
        "Retraction and Republication",
        "publisher",
        "2018-06-13",
    )


def test_check_answer_hops_include_source_url_fetch_date_and_sha256(tmp_path: Path, monkeypatch):
    _offline_check(monkeypatch)
    graph = Graph(tmp_path / "trail.db")
    try:
        _seed_two_hop(graph)
        payload = check_answer("", [PAGE_URL], ENGINE, 2, graph=graph)
        hops = (payload.get("reasons") or [{}])[0].get("hops_evidence") or []
        assert len(hops) == 2
        _assert_hop_trail(hops[0], url=PAGE_URL, fetched_at=PAGE_FETCHED, content_hash=PAGE_HASH)
        _assert_hop_trail(hops[1], url=WORK_URL, fetched_at=WORK_FETCHED, content_hash=WORK_HASH)
    finally:
        graph.close()


def test_cli_json_includes_hop_evidence_trail(tmp_path: Path, monkeypatch, capsys):
    from mooltrace.__main__ import main

    _offline_check(monkeypatch)
    graph = Graph(tmp_path / "cli.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        _seed_two_hop(graph)
        code = main(["check", "--json", "--url", PAGE_URL, "--engine", ENGINE, "--depth", "2"])
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        hops = (payload.get("reasons") or [{}])[0].get("hops_evidence") or []
        assert len(hops) == 2
        _assert_hop_trail(hops[0], url=PAGE_URL, fetched_at=PAGE_FETCHED, content_hash=PAGE_HASH)
        _assert_hop_trail(hops[1], url=WORK_URL, fetched_at=WORK_FETCHED, content_hash=WORK_HASH)
    finally:
        graph.close()


def test_api_check_answer_includes_hop_evidence_trail(tmp_path: Path, monkeypatch):
    _offline_check(monkeypatch)
    graph = Graph(tmp_path / "api.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        _seed_two_hop(graph)
        client = TestClient(app)
        response = client.post(
            "/check-answer",
            json={"text": "", "urls": [PAGE_URL], "engine": ENGINE, "depth": 2},
        )
        assert response.status_code == 200
        hops = (response.json().get("reasons") or [{}])[0].get("hops_evidence") or []
        assert len(hops) == 2
        _assert_hop_trail(hops[0], url=PAGE_URL, fetched_at=PAGE_FETCHED, content_hash=PAGE_HASH)
        _assert_hop_trail(hops[1], url=WORK_URL, fetched_at=WORK_FETCHED, content_hash=WORK_HASH)
    finally:
        graph.close()


def test_mcp_check_answer_includes_hop_evidence_trail(tmp_path: Path, monkeypatch):
    _offline_check(monkeypatch)
    graph = Graph(tmp_path / "mcp.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)

    async def run() -> dict:
        async with Client(server) as client:
            result = await client.call_tool(
                "check_answer",
                {"text": "", "urls": [PAGE_URL], "engine": ENGINE, "depth": 2},
            )
            assert not result.is_error
            return json.loads(result.content[0].text)

    try:
        _seed_two_hop(graph)
        payload = asyncio.run(run())
        hops = (payload.get("reasons") or [{}])[0].get("hops_evidence") or []
        assert len(hops) == 2
        _assert_hop_trail(hops[0], url=PAGE_URL, fetched_at=PAGE_FETCHED, content_hash=PAGE_HASH)
        _assert_hop_trail(hops[1], url=WORK_URL, fetched_at=WORK_FETCHED, content_hash=WORK_HASH)
    finally:
        graph.close()


def test_judge_page_hashes_the_fetched_body(tmp_path: Path, monkeypatch):
    from mooltrace.judge import judge_citation_edges
    from mooltrace.trace import _answer_id

    graph = Graph(tmp_path / "judge.db")
    answer_id = _answer_id("judge-page", "", [PAGE_URL])
    try:
        graph.merge_answer(answer_id, "judge-page", "hash", NOW)
        graph.merge_source(PAGE_URL, "Olive oil page", "example.com", True, fetched_at=PAGE_FETCHED)
        graph.cite(answer_id, PAGE_URL)
        graph.merge_work(
            ESTRUCH,
            title="Primary Prevention of Cardiovascular Disease with a Mediterranean Diet",
            year=2013,
            first_author="Estruch",
            expanded=True,
            notice_checked=True,
        )
        graph.source_rests_on(PAGE_URL, ESTRUCH)
        graph.merge_notice(
            NOTICE,
            ESTRUCH,
            "retraction",
            "Retraction and Republication",
            "publisher",
            "2018-06-13",
        )
        monkeypatch.setattr("mooltrace.judge.fetch_page_html", lambda url, stats: PAGE_HTML)
        notes: list[str] = []
        stored = judge_citation_edges(graph, answer_id, "", CallStats(), notes, depth=1)
        assert stored == 1
        hops = (graph.paths(answer_id, depth=1).rows or [{}])[0].get("hops_evidence") or []
        assert hops
        _assert_hop_trail(
            hops[0],
            url=PAGE_URL,
            fetched_at=hops[0].get("fetched_at") or "",
            content_hash=PAGE_HASH,
        )
        _utc_iso(str(hops[0]["fetched_at"]))
    finally:
        graph.close()


def test_path_view_shows_hop_trail_compactly():
    diagram = (Path(__file__).resolve().parents[1] / "web" / "src" / "components" / "path-diagram.tsx").read_text()
    assert "hopTrailLine" in diagram
    lib = (Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "path-diagram.ts").read_text()
    assert "content_hash" in lib
    assert "fetched_at" in lib
    assert "source_url" in lib
    assert "sha256" in lib
