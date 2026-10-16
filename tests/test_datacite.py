"""Offline arXiv / Zenodo resolution from recorded DataCite fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from mooltrace.clients import (
    CallStats,
    close_client,
    datacite_work,
    reset_http_state,
)
from mooltrace.graph import Graph
from mooltrace.trace import check_answer, expand_work

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "datacite"
ARXIV = json.loads((FIXTURES / "arxiv_1706.03762.json").read_text(encoding="utf-8"))
ZENODO = json.loads((FIXTURES / "zenodo_3242074.json").read_text(encoding="utf-8"))
ARXIV_DOI = "10.48550/arxiv.1706.03762"
ZENODO_DOI = "10.5281/zenodo.3242074"


def _transport(hits: list[str]):
    bodies = {
        ARXIV_DOI: ARXIV["body"],
        ZENODO_DOI: ZENODO["body"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url)
        host = request.url.host or ""
        if host == "api.datacite.org":
            lowered = url.lower()
            for doi, body in bodies.items():
                encoded = doi.replace("/", "%2f")
                if doi in lowered or encoded in lowered:
                    return httpx.Response(200, json=body)
            return httpx.Response(404, text="datacite miss")
        if host in {"api.openalex.org", "api.crossref.org", "doi.org", "dx.doi.org"}:
            return httpx.Response(404, text="missing")
        return httpx.Response(404, text="missing")

    return httpx.MockTransport(handler)


def _install_http(monkeypatch, hits: list[str]) -> None:
    monkeypatch.setenv("MOOLTRACE_MAILTO", "siddhant.m.vishnu@gmail.com")
    reset_http_state()
    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(hits)),
    )


def test_datacite_work_parses_recorded_arxiv(monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    try:
        row = datacite_work(ARXIV_DOI, CallStats())
    finally:
        close_client()
        reset_http_state()
    assert row is not None
    assert row["doi"] == ARXIV_DOI
    assert row["title"] == "Attention Is All You Need"
    assert row["year"] == 2017
    assert row["publisher"] == "arXiv"
    assert row["source"] == "datacite"
    assert row["first_author"] == "Vaswani"
    assert any("api.datacite.org/dois/" in url for url in hits)
    assert any("%2F" in url or "/10.48550/arxiv" in url.lower() for url in hits)
    assert not any("api.openalex.org" in url for url in hits)


def test_datacite_work_parses_recorded_zenodo(monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    try:
        row = datacite_work(ZENODO_DOI, CallStats())
    finally:
        close_client()
        reset_http_state()
    assert row is not None
    assert row["doi"] == ZENODO_DOI
    assert row["title"] == "Simple requirements.txt based example for repo2docker"
    assert row["year"] == 2019
    assert row["publisher"] == "Zenodo"
    assert row["source"] == "datacite"
    assert row["first_author"] == "Binder"


def test_expand_work_resolves_arxiv_from_recorded_datacite(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        expand_work(graph, ARXIV_DOI, CallStats())
        row = graph.work_row(ARXIV_DOI)
        assert row is not None
        assert row.get("title") == "Attention Is All You Need"
        assert row.get("year") == 2017
        assert row.get("first_author") == "Vaswani"
        assert row.get("expanded")
        assert row.get("notice_checked")
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert any("api.datacite.org" in url for url in hits)


def test_expand_work_resolves_zenodo_from_recorded_datacite(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        expand_work(graph, ZENODO_DOI, CallStats())
        row = graph.work_row(ZENODO_DOI)
        assert row is not None
        assert row.get("title") == "Simple requirements.txt based example for repo2docker"
        assert row.get("year") == 2019
        assert row.get("first_author") == "Binder"
        assert row.get("expanded")
        assert row.get("notice_checked")
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert any("api.datacite.org" in url for url in hits)
    assert not any("doi.org/" in url and "api.datacite.org" not in url for url in hits)


def test_check_answer_arxiv_doi_resolves_end_to_end(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="Transformer weights follow 10.48550/arXiv.1706.03762.",
            engine="arxiv-datacite",
            depth=2,
            graph=graph,
        )
        row = graph.work_row(ARXIV_DOI)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert payload["decision"] == "pass"
    assert payload["exit_code"] == 0
    assert not payload.get("incomplete")
    joined = " ".join(payload.get("errors") or []).lower()
    assert "unresolved" not in joined
    assert row is not None
    assert row.get("title") == "Attention Is All You Need"
    assert row.get("year") == 2017
    assert row.get("first_author") == "Vaswani"
    assert any("api.datacite.org" in url for url in hits)


def test_check_answer_zenodo_doi_resolves_end_to_end(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="The binder example is 10.5281/zenodo.3242074.",
            engine="zenodo-datacite",
            depth=2,
            graph=graph,
        )
        row = graph.work_row(ZENODO_DOI)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert payload["decision"] == "pass"
    assert payload["exit_code"] == 0
    assert not payload.get("incomplete")
    joined = " ".join(payload.get("errors") or []).lower()
    assert "unresolved" not in joined
    assert row is not None
    assert row.get("title") == "Simple requirements.txt based example for repo2docker"
    assert row.get("first_author") == "Binder"
    assert any("api.datacite.org" in url for url in hits)


def test_check_answer_arxiv_doi_resolves_at_depth_one(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="See 10.48550/arXiv.1706.03762.",
            engine="arxiv-depth1",
            depth=1,
            graph=graph,
        )
        row = graph.work_row(ARXIV_DOI)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert payload["decision"] == "pass"
    assert payload["exit_code"] == 0
    joined = " ".join(payload.get("errors") or []).lower()
    assert "unresolved" not in joined
    assert row is not None
    assert row.get("title") == "Attention Is All You Need"
    assert row.get("year") == 2017
    assert row.get("first_author") == "Vaswani"
    assert row.get("notice_checked")
    assert any("api.datacite.org" in url for url in hits)
