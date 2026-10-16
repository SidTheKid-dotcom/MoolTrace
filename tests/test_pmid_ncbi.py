"""PMID resolution via NCBI idconv / esummary when OpenAlex has no DOI."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from mooltrace.clients import CallStats, close_client, reset_http_state
from mooltrace.graph import Graph
from mooltrace.trace import check_answer

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ncbi"
OLIVE_PMID = "30461730"
KHAN_PMID = "14633847"
KHAN_DOI = "10.2337/diacare.26.12.3215"
IDCONV_OLIVE = json.loads((FIXTURES / "idconv_30461730.json").read_text())["body"]
ESUMMARY_OLIVE = json.loads((FIXTURES / "esummary_30461730.json").read_text())["body"]
IDCONV_KHAN = json.loads((FIXTURES / "idconv_14633847.json").read_text())["body"]
ESUMMARY_KHAN = json.loads((FIXTURES / "esummary_14633847.json").read_text())["body"]


def _transport(hits: list[str], *, idconv: dict, esummary: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url)
        host = request.url.host or ""
        if host in {"www.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"} and "idconv" in url:
            return httpx.Response(200, json=idconv)
        if host == "eutils.ncbi.nlm.nih.gov":
            return httpx.Response(200, json=esummary)
        if host in {
            "api.openalex.org",
            "api.crossref.org",
            "api.datacite.org",
            "doi.org",
            "dx.doi.org",
        }:
            return httpx.Response(404, text="missing")
        return httpx.Response(404, text="missing")

    return httpx.MockTransport(handler)


def _install_http(monkeypatch, hits: list[str], *, idconv: dict, esummary: dict) -> None:
    monkeypatch.setenv("MOOLTRACE_MAILTO", "siddhant.m.vishnu@gmail.com")
    reset_http_state()
    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(hits, idconv=idconv, esummary=esummary)),
    )
    monkeypatch.setattr("mooltrace.trace.judge_citation_edges", lambda *a, **k: None)


def test_pmid_idconv_supplies_doi_when_openalex_has_none(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits, idconv=IDCONV_KHAN, esummary=ESUMMARY_KHAN)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text=f"PMID:{KHAN_PMID}",
            engine="pmid-idconv",
            depth=1,
            graph=graph,
        )
        row = graph.work_row(KHAN_DOI)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert payload["decision"] in {"pass", "warn", "block"}
    joined = " ".join(payload.get("errors") or []).lower()
    assert f"unresolved pmid:{KHAN_PMID}" not in joined
    assert row is not None
    assert any("idconv" in url for url in hits)


def test_pmid_esummary_supplies_doi_when_idconv_has_none(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    empty_idconv = {"status": "ok", "records": [{"pmid": KHAN_PMID, "requested-id": KHAN_PMID}]}
    _install_http(monkeypatch, hits, idconv=empty_idconv, esummary=ESUMMARY_KHAN)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text=f"PMID:{KHAN_PMID}",
            engine="pmid-esummary",
            depth=1,
            graph=graph,
        )
        row = graph.work_row(KHAN_DOI)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    joined = " ".join(payload.get("errors") or []).lower()
    assert f"unresolved pmid:{KHAN_PMID}" not in joined
    assert row is not None
    assert any("esummary" in url for url in hits)
    assert payload["decision"] in {"pass", "warn", "block"}


def test_olive_pmid_without_doi_is_not_unresolved_at_depth_one(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(monkeypatch, hits, idconv=IDCONV_OLIVE, esummary=ESUMMARY_OLIVE)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text=f"PMID:{OLIVE_PMID}",
            engine="pmid-olive",
            depth=1,
            graph=graph,
        )
    finally:
        graph.close()
        close_client()
        reset_http_state()
    joined = " ".join(payload.get("errors") or []).lower()
    assert f"unresolved pmid:{OLIVE_PMID}" not in joined
    assert payload["decision"] == "pass"
    assert payload["exit_code"] == 0
    assert not payload.get("incomplete")
    assert not any(
        (reason.get("code") or "") == "incomplete" for reason in payload.get("reasons") or []
    )
    assert any("idconv" in url for url in hits)
    assert any("esummary" in url for url in hits)


def test_unknown_pmid_stays_unresolved(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_http(
        monkeypatch,
        hits,
        idconv={"status": "ok", "records": [{"status": "error", "errmsg": "invalid id"}]},
        esummary={"header": {"type": "esummary"}, "result": {"uids": []}},
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="PMID:00000000",
            engine="pmid-miss",
            depth=1,
            graph=graph,
        )
    finally:
        graph.close()
        close_client()
        reset_http_state()
    joined = " ".join(payload.get("errors") or []).lower()
    assert "unresolved pmid:00000000" in joined
    assert payload["decision"] == "warn"
    assert payload["exit_code"] == 2
