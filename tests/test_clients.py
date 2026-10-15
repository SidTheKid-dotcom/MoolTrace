from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from mooltrace.clients import (
    CallStats,
    InfraError,
    MoolTraceError,
    _get_json,
    close_client,
    crossref_work,
    openalex_by_ids,
    openalex_work_doi,
    request_json,
    reset_http_state,
    resolve_diabetes_care,
)
from mooltrace.config import OPENALEX_MAX_RPS
from mooltrace.graph import Graph
from mooltrace.trace import check_answer


def test_resolve_diabetes_care_uses_crossref_not_openalex(monkeypatch):
    calls = []

    def fake_crossref(doi, stats):
        calls.append(("crossref", doi))
        return {"DOI": doi, "ISSN": ["0149-5992", "1935-5548"]}

    def fake_openalex(volume, issue, page, stats):
        calls.append(("openalex", volume, issue, page))
        raise AssertionError("OpenAlex must not run when Crossref confirms ISSN")

    monkeypatch.setattr("mooltrace.clients.crossref_work", fake_crossref)
    monkeypatch.setattr("mooltrace.clients.openalex_diabetes_care", fake_openalex)
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"
    assert calls == [("crossref", "10.2337/diacare.26.12.3215")]


def test_resolve_diabetes_care_falls_back_when_crossref_misses(monkeypatch):
    monkeypatch.setattr("mooltrace.clients.crossref_work", lambda doi, stats: None)
    monkeypatch.setattr(
        "mooltrace.clients.openalex_diabetes_care",
        lambda volume, issue, page, stats: "10.2337/diacare.26.12.3215",
    )
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"


def test_resolve_diabetes_care_rejects_wrong_issn(monkeypatch):
    monkeypatch.setattr(
        "mooltrace.clients.crossref_work",
        lambda doi, stats: {"DOI": doi, "ISSN": ["0000-0000"]},
    )
    monkeypatch.setattr(
        "mooltrace.clients.openalex_diabetes_care",
        lambda volume, issue, page, stats: "10.2337/diacare.26.12.3215",
    )
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"


@pytest.fixture(autouse=True)
def _http_tmp(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_HTTP_CACHE", str(tmp_path / "http-cache"))
    monkeypatch.setenv("MOOLTRACE_MAILTO", "siddhant.m.vishnu@gmail.com")
    reset_http_state()
    yield
    reset_http_state()
    close_client()


def _transport(handler):
    return httpx.MockTransport(handler)


def test_get_json_capped_retry_after_fails_fast(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("mooltrace.clients.time.sleep", lambda s: sleeps.append(float(s)))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "14463"}, text="daily window")

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats = CallStats()
    try:
        _get_json("https://api.openalex.org/works?filter=openalex_id:W1", stats)
    except InfraError:
        pass
    else:
        raise AssertionError("capped Retry-After 429 was not InfraError")
    assert stats.api_calls == 1
    assert sleeps == []


def test_openalex_by_ids_falls_back_to_per_id_when_filter_is_429(monkeypatch):
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        hits.append(url)
        if "filter=" in url:
            return httpx.Response(429, headers={"Retry-After": "14463"}, text="slow")
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/x",
                "display_name": "Fallback",
            },
        )

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    rows = openalex_by_ids(["https://openalex.org/W1"], CallStats())
    assert rows and rows[0]["id"].endswith("W1")
    assert any("filter=" in url for url in hits)
    assert any("/works/W1" in url for url in hits)


def test_get_json_exhausted_429_is_infra(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("mooltrace.clients.time.sleep", lambda s: sleeps.append(float(s)))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "slow down"})

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats = CallStats()
    try:
        _get_json("https://api.openalex.org/works/doi:10.1/x", stats)
    except InfraError as exc:
        assert "429" in str(exc) or "giving up" in str(exc)
    else:
        raise AssertionError("exhausted 429 was not InfraError")
    assert not isinstance(InfraError("x"), MoolTraceError)
    assert any(s >= 2.0 for s in sleeps)
    assert stats.api_calls >= 3


def test_get_json_honours_retry_after_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("mooltrace.clients.time.sleep", lambda s: sleeps.append(float(s)))
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"}, text="wait")
        return httpx.Response(200, json={"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x"})

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats = CallStats()
    payload = _get_json("https://api.openalex.org/works/doi:10.1/x", stats)
    assert payload["id"].endswith("W1")
    assert sleeps and sleeps[0] >= 1.5
    assert stats.api_calls == 2


def test_get_json_5xx_uses_backoff_then_infra(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("mooltrace.clients.time.sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr("mooltrace.clients.random.uniform", lambda a, b: 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats = CallStats()
    try:
        _get_json("https://api.crossref.org/works/10.1/x", stats)
    except InfraError:
        pass
    else:
        raise AssertionError("exhausted 503 was not InfraError")
    backoff = [s for s in sleeps if s >= 0.4]
    assert len(backoff) >= 2
    assert backoff[1] > backoff[0]


def test_disk_cache_makes_a_second_call_free(monkeypatch, tmp_path: Path):
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(
            200,
            json={"id": "https://openalex.org/W9", "doi": "https://doi.org/10.1/cached"},
        )

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats1 = CallStats()
    first = openalex_work_doi("10.1/cached", stats1)
    assert first and first["id"].endswith("W9")
    assert hits["n"] == 1
    assert stats1.api_calls == 1
    close_client()
    reset_http_state()
    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    stats2 = CallStats()
    second = openalex_work_doi("10.1/cached", stats2)
    assert second == first
    assert hits["n"] == 1
    assert stats2.api_calls == 0
    assert stats2.cache_hits >= 1
    cache_files = list((tmp_path / "http-cache").glob("*"))
    assert cache_files


def test_request_json_still_returns_429_for_semantic_scholar(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow")

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    code, payload = request_json("https://api.semanticscholar.org/graph/v1/paper/DOI:10.1/x", CallStats())
    assert code == 429
    assert payload is None


def test_openalex_limiter_is_at_most_eight_per_second():
    from mooltrace.clients import _limiter_for

    assert OPENALEX_MAX_RPS <= 8
    limiter = _limiter_for("https://api.openalex.org/works/doi:10.1/x")
    assert limiter.interval >= 1.0 / 8.0


def test_check_answer_exhausted_openalex_is_infra(tmp_path: Path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise InfraError("429 from api.openalex.org")

    monkeypatch.setattr("mooltrace.trace.openalex_work_doi", boom)
    monkeypatch.setattr("mooltrace.trace.crossref_work", boom)
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="A draft citing 10.1234/infra-case.",
            engine="scale-infra",
            depth=2,
            graph=graph,
        )
    finally:
        graph.close()
    assert payload["exit_code"] == 3
    assert payload["decision"] == "incomplete"
    assert payload.get("error_code") == "infra"
    assert payload["decision"] != "pass"


def test_crossref_404_is_cached_not_infra(monkeypatch):
    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(404, text="missing")

    monkeypatch.setattr(
        "mooltrace.clients._http",
        lambda: httpx.Client(transport=_transport(handler)),
    )
    assert crossref_work("10.1/missing", CallStats()) is None
    assert crossref_work("10.1/missing", CallStats()) is None
    assert hits["n"] == 1
