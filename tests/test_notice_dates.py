"""Notice dates must not copy an in-place Crossref publication date."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from mooltrace.clients import CallStats, close_client, reset_http_state
from mooltrace.graph import Graph
from mooltrace.rewrite import template_rewrite
from mooltrace.summary import format_summary
from mooltrace.trace import notice_check

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ncbi"
ISHIDA = "10.1016/j.amjmed.2004.05.019"
ISHIDA_NOTICE = "10.1016/j.amjmed.2025.03.001"
ESTRUCH = "10.1056/nejmoa1200303"
ESTRUCH_NOTICE = "10.1056/nejmc1806491"
FAKE_WORK = "10.9999/inplace-unresolvable"
IDCONV_ISHIDA = json.loads((FIXTURES / "idconv_ishida.json").read_text())["body"]
ESUMMARY_NOTICE = json.loads((FIXTURES / "esummary_40222753.json").read_text())["body"]
EFETCH_ISHIDA = (FIXTURES / "efetch_15465502.xml").read_text()
EFETCH_EMPTY = (FIXTURES / "efetch_unresolvable.xml").read_text()


def _ishida_crossref() -> dict:
    return {
        "DOI": ISHIDA,
        "title": ["Yamaguchi Osteoporosis Prevention Study"],
        "issued": {"date-parts": [[2004, 10, 15]]},
        "updated-by": [
            {
                "DOI": ISHIDA,
                "type": "retraction",
                "label": "Retraction",
                "source": "publisher",
                "updated": {"date-parts": [[2004, 10, 15]]},
            }
        ],
    }


def _estruch_crossref() -> dict:
    return {
        "DOI": ESTRUCH,
        "title": ["Primary Prevention of Cardiovascular Disease with a Mediterranean Diet"],
        "issued": {"date-parts": [[2013, 4, 4]]},
        "updated-by": [
            {
                "DOI": ESTRUCH_NOTICE,
                "type": "retraction",
                "label": "Retraction",
                "source": "publisher",
                "updated": {"date-parts": [[2018, 6, 13]]},
            }
        ],
    }


def _unresolvable_crossref() -> dict:
    return {
        "DOI": FAKE_WORK,
        "title": ["Synthetic in-place retraction"],
        "issued": {"date-parts": [[2001, 1, 1]]},
        "updated-by": [
            {
                "DOI": FAKE_WORK,
                "type": "retraction",
                "label": "Retraction",
                "source": "publisher",
                "updated": {"date-parts": [[2001, 1, 1]]},
            }
        ],
    }


def _ncbi_transport(hits: list[str], *, idconv: dict | None, efetch: str, esummary: dict | None):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url)
        host = request.url.host or ""
        if host in {"www.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"} and "idconv" in url:
            if idconv is None:
                return httpx.Response(404, text="missing")
            return httpx.Response(200, json=idconv)
        if host == "eutils.ncbi.nlm.nih.gov" and "efetch" in url:
            return httpx.Response(200, text=efetch)
        if host == "eutils.ncbi.nlm.nih.gov" and "esummary" in url:
            if esummary is None:
                return httpx.Response(404, text="missing")
            return httpx.Response(200, json=esummary)
        return httpx.Response(404, text="missing")

    return httpx.MockTransport(handler)


def _install_ncbi(monkeypatch, hits: list[str], *, idconv, efetch: str, esummary) -> None:
    monkeypatch.setenv("MOOLTRACE_MAILTO", "mooltrace-test@example.com")
    reset_http_state()
    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(
            transport=_ncbi_transport(hits, idconv=idconv, efetch=efetch, esummary=esummary)
        ),
    )


def _stored_notice(graph: Graph, work_doi: str) -> dict:
    rows = graph.notices_for(work_doi).rows
    assert rows, f"expected a notice on {work_doi}"
    return rows[0]


def test_inplace_retraction_same_doi_resolves_via_pubmed_to_2025_05(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_ncbi(
        monkeypatch,
        hits,
        idconv=IDCONV_ISHIDA,
        efetch=EFETCH_ISHIDA,
        esummary=ESUMMARY_NOTICE,
    )
    monkeypatch.setattr("mooltrace.trace.crossref_works", lambda dois, stats: [_ishida_crossref()])
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        notice_check(graph, [ISHIDA], CallStats())
        row = _stored_notice(graph, ISHIDA)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert row.get("doi") == ISHIDA_NOTICE
    assert str(row.get("date") or "") == "2025-05"
    assert row.get("type") == "retraction"
    assert any("idconv" in url for url in hits)
    assert any("efetch" in url for url in hits)
    assert any("40222753" in url for url in hits)


def test_unresolvable_inplace_retraction_prints_no_date(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    empty_idconv = {
        "records": [{"doi": FAKE_WORK, "pmid": "99999999", "requested-id": FAKE_WORK}]
    }
    _install_ncbi(
        monkeypatch,
        hits,
        idconv=empty_idconv,
        efetch=EFETCH_EMPTY,
        esummary=None,
    )
    monkeypatch.setattr(
        "mooltrace.trace.crossref_works", lambda dois, stats: [_unresolvable_crossref()]
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        notice_check(graph, [FAKE_WORK], CallStats())
        row = _stored_notice(graph, FAKE_WORK)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    date = str(row.get("date") or "")
    assert date == ""
    assert "2001" not in date
    payload = {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": FAKE_WORK,
                "notice_date": date,
                "root_doi": FAKE_WORK,
                "root_author": "Doe",
                "root_year": 2001,
            }
        ],
    }
    rewritten = template_rewrite(payload, "A draft cites DOI 10.9999/inplace-unresolvable.", [])
    assert "retraction date not confirmed" in rewritten["text"]
    assert "2001-01-01" not in rewritten["text"]
    assert "1 Jan 2001" not in rewritten["text"]
    assert "retracted on" not in rewritten["text"]
    summary = format_summary(payload)
    assert "retraction date not confirmed" in summary
    assert "2001-01-01" not in summary


def test_estruch_separate_notice_keeps_2018_06_13(tmp_path: Path, monkeypatch):
    hits: list[str] = []
    _install_ncbi(monkeypatch, hits, idconv=None, efetch="", esummary=None)
    monkeypatch.setattr("mooltrace.trace.crossref_works", lambda dois, stats: [_estruch_crossref()])
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        notice_check(graph, [ESTRUCH], CallStats())
        row = _stored_notice(graph, ESTRUCH)
    finally:
        graph.close()
        close_client()
        reset_http_state()
    assert row.get("doi") == ESTRUCH_NOTICE
    assert str(row.get("date") or "") == "2018-06-13"
    assert not any("eutils.ncbi.nlm.nih.gov" in url for url in hits)
    payload = {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": ESTRUCH_NOTICE,
                "notice_date": "2018-06-13",
                "notice_label": "Retraction and Republication",
                "root_doi": ESTRUCH,
                "root_author": "Estruch",
                "root_year": 2013,
            }
        ],
    }
    rewritten = template_rewrite(payload, "A draft cites DOI 10.1056/nejmoa1200303.", [])
    assert "13 Jun 2018" in rewritten["text"]
    assert "retraction date not confirmed" not in rewritten["text"]


def test_rewrite_month_year_says_retracted_in_may_2025():
    payload = {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": ISHIDA_NOTICE,
                "notice_date": "2025-05",
                "root_doi": ISHIDA,
                "root_author": "Ishida",
                "root_year": 2004,
            }
        ],
    }
    out = template_rewrite(
        payload,
        "A nutrition coach cites Ishida. DOI 10.1016/j.amjmed.2004.05.019.",
        [],
    )
    assert "Ishida et al. 2004" in out["text"]
    assert "retracted in May 2025" in out["text"]
    assert "15 Oct 2004" not in out["text"]
    assert "2004-10-15" not in out["text"]
    assert ISHIDA_NOTICE not in out["text"]
