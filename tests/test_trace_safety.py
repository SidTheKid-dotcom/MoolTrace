from datetime import datetime, timezone
from pathlib import Path

from mooltrace import config
from mooltrace.clients import CallStats, MoolTraceError
from mooltrace.graph import Graph
from mooltrace.decision import NO_SOURCES_SUMMARY
from mooltrace.trace import _page_urls, check_answer, expand_work, notice_check


def test_page_urls_reject_loopback(monkeypatch):
    monkeypatch.setattr("mooltrace.ssrf._host_ips", lambda host, port: ["93.184.216.34"])
    errors: list[str] = []
    pages = _page_urls(["http://127.0.0.1/secret", "https://example.com/ok"], "", errors)
    assert "https://example.com/ok" in pages
    assert all("127.0.0.1" not in page for page in pages)
    assert errors


def test_fresh_notice_skips_crossref(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_work(
            "10.1234/fresh",
            notice_checked=True,
            notice_checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        called: list[list[str]] = []

        def fake_works(dois, stats):
            called.append(list(dois))
            return []

        monkeypatch.setattr("mooltrace.trace.crossref_works", fake_works)
        monkeypatch.setattr(config, "NOTICE_REFRESH_TTL_S", 86_400)
        stats = CallStats()
        notice_check(graph, ["10.1234/fresh"], stats)
        assert called == []
        assert stats.cache_hits >= 1
    finally:
        graph.close()


def test_stale_notice_is_rechecked(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_work(
            "10.1234/stale",
            notice_checked=True,
            notice_checked_at="2000-01-01T00:00:00+00:00",
        )
        called: list[list[str]] = []

        def fake_works(dois, stats):
            called.append(list(dois))
            return []

        monkeypatch.setattr("mooltrace.trace.crossref_works", fake_works)
        monkeypatch.setattr(config, "NOTICE_REFRESH_TTL_S", 60)
        notice_check(graph, ["10.1234/stale"], CallStats())
        assert called == [["10.1234/stale"]]
        row = graph.work_row("10.1234/stale")
        assert row and row.get("notice_checked_at")
        assert not str(row.get("notice_checked_at")).startswith("2000-")
    finally:
        graph.close()


def test_expand_failure_does_not_mark_success(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        def boom(*_args, **_kwargs):
            raise MoolTraceError("upstream down")

        monkeypatch.setattr("mooltrace.trace.openalex_work_doi", boom)
        monkeypatch.setattr("mooltrace.trace.crossref_work", boom)
        try:
            expand_work(graph, "10.1234/down", CallStats())
        except MoolTraceError:
            pass
        else:
            raise AssertionError("expand_work should fail closed")
        row = graph.work_row("10.1234/down")
        assert row is None or not row.get("expanded")
        assert row is None or not row.get("notice_checked")
    finally:
        graph.close()


def test_gate_does_not_delete_configured_db(tmp_path: Path, monkeypatch):
    kept = tmp_path / "keep.db"
    kept.write_text("stay", encoding="utf-8")
    monkeypatch.setattr(config, "DB_PATH", kept)
    from mooltrace.gate import _fresh_graph

    graph = _fresh_graph()
    try:
        assert graph.path != kept
    finally:
        graph.close()
    assert kept.read_text(encoding="utf-8") == "stay"


def test_expand_partial_catalog_failure_does_not_mark_expanded(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    doi = "10.1234/partial"

    def fake_openalex(target, stats):
        return {
            "id": "https://openalex.org/W1",
            "doi": f"https://doi.org/{target}",
            "display_name": "Partial",
            "publication_year": 2000,
            "referenced_works": [],
            "authorships": [],
        }

    def boom(*_args, **_kwargs):
        raise MoolTraceError("crossref down")

    monkeypatch.setattr("mooltrace.trace.openalex_work_doi", fake_openalex)
    monkeypatch.setattr("mooltrace.trace.crossref_work", boom)
    monkeypatch.setattr("mooltrace.trace.notice_check", lambda *_a, **_k: None)
    try:
        try:
            expand_work(graph, doi, CallStats())
        except MoolTraceError:
            pass
        else:
            raise AssertionError("partial expand should fail closed")
        row = graph.work_row(doi)
        assert row is None or not row.get("expanded")
    finally:
        graph.close()


def test_notice_check_failure_does_not_mark_checked(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_work("10.1234/pending")

        def boom(*_args, **_kwargs):
            raise MoolTraceError("crossref down")

        monkeypatch.setattr("mooltrace.trace.crossref_works", boom)
        try:
            notice_check(graph, ["10.1234/pending"], CallStats())
        except MoolTraceError:
            pass
        else:
            raise AssertionError("notice_check should fail closed")
        row = graph.work_row("10.1234/pending")
        assert row is None or not row.get("notice_checked")
    finally:
        graph.close()


def test_expand_retries_after_partial_failure(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    doi = "10.1234/retry"
    calls = {"crossref": 0}

    def fake_openalex(target, stats):
        return {
            "id": "https://openalex.org/W1",
            "doi": f"https://doi.org/{target}",
            "display_name": "Retry",
            "publication_year": 2000,
            "referenced_works": [],
            "authorships": [],
        }

    def flaky_crossref(target, stats):
        calls["crossref"] += 1
        if calls["crossref"] == 1:
            raise MoolTraceError("crossref down")
        return {
            "DOI": target,
            "title": ["Retry"],
            "author": [],
            "issued": {"date-parts": [[2000]]},
            "updated-by": [],
            "reference": [],
        }

    monkeypatch.setattr("mooltrace.trace.openalex_work_doi", fake_openalex)
    monkeypatch.setattr("mooltrace.trace.crossref_work", flaky_crossref)
    monkeypatch.setattr("mooltrace.trace.notice_check", lambda *_a, **_k: None)
    try:
        try:
            expand_work(graph, doi, CallStats())
        except MoolTraceError:
            pass
        else:
            raise AssertionError("first expand should fail closed")
        row = graph.work_row(doi)
        assert row is None or not row.get("expanded")
        expand_work(graph, doi, CallStats())
        row = graph.work_row(doi)
        assert row and row.get("expanded") is True
        assert calls["crossref"] == 2
    finally:
        graph.close()


def test_notice_check_retries_after_failure(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    calls = {"n": 0}

    def flaky_works(dois, stats):
        calls["n"] += 1
        if calls["n"] == 1:
            raise MoolTraceError("crossref down")
        return [
            {
                "DOI": "10.1234/pending",
                "title": ["Pending"],
                "updated-by": [],
            }
        ]

    monkeypatch.setattr("mooltrace.trace.crossref_works", flaky_works)
    try:
        graph.merge_work("10.1234/pending")
        try:
            notice_check(graph, ["10.1234/pending"], CallStats())
        except MoolTraceError:
            pass
        else:
            raise AssertionError("first notice_check should fail closed")
        row = graph.work_row("10.1234/pending")
        assert row is None or not row.get("notice_checked")
        notice_check(graph, ["10.1234/pending"], CallStats())
        row = graph.work_row("10.1234/pending")
        assert row and row.get("notice_checked")
        assert row.get("notice_checked_at")
        assert calls["n"] == 2
    finally:
        graph.close()


def _traced_without_notice(**kwargs):
    return {
        "product": "MoolTrace",
        "answer_id": "stub",
        "engine": kwargs.get("engine") or "draft",
        "depth": kwargs.get("depth") or 2,
        "flagged": False,
        "summary": "No flagged study within 2 hops.",
        "pitch": None,
        "paths": [],
        "works_cited": 1,
        "api_calls": 0,
        "cache_hits": 0,
        "reused_graph": False,
        "incomplete": False,
        "errors": [],
        "queries": [],
        "cypher": None,
        "elapsed_ms": 0,
        "context_notes": [],
        "limits": "This check does not give medical advice.",
    }


def test_plain_prose_is_no_sources_warn(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="Cinnamon may help blood sugar in some people.",
            engine="prose",
            depth=1,
            graph=graph,
        )
        assert payload["decision"] == "warn"
        assert payload["exit_code"] == 2
        assert payload["error_code"] == "no_sources"
        assert payload["reasons"][0]["code"] == "no_sources"
        assert payload["summary"] == NO_SOURCES_SUMMARY
        assert payload["works_cited"] == 0
        assert payload["pitch"] is None
        assert "medical advice" in (payload.get("limits") or "").lower()
    finally:
        graph.close()


def test_empty_answer_is_no_sources_warn(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(text="", urls=[], engine="empty", depth=1, graph=graph)
        assert payload["decision"] == "warn"
        assert payload["exit_code"] == 2
        assert payload["error_code"] == "no_sources"
        assert payload["reasons"][0]["code"] == "no_sources"
        assert payload["summary"] == NO_SOURCES_SUMMARY
        assert payload["works_cited"] == 0
        assert payload["pitch"] is None
    finally:
        graph.close()


def test_inline_doi_is_not_no_sources(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.trace_answer", _traced_without_notice)
    monkeypatch.setattr(
        "mooltrace.trace._clusters",
        lambda _graph: {"algorithm": "algo.WCC", "clusters": [], "cypher": None},
    )
    try:
        payload = check_answer(
            text="See 10.2337/diacare.26.12.3215 for the trial.",
            engine="doi-inline",
            depth=1,
            graph=graph,
        )
        assert payload.get("error_code") != "no_sources"
        assert all(reason.get("code") != "no_sources" for reason in payload["reasons"])
        assert payload["decision"] == "pass"
        assert payload["works_cited"] == 1
    finally:
        graph.close()


def test_explicit_url_is_not_no_sources(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.trace_answer", _traced_without_notice)
    monkeypatch.setattr(
        "mooltrace.trace._clusters",
        lambda _graph: {"algorithm": "algo.WCC", "clusters": [], "cypher": None},
    )
    try:
        payload = check_answer(
            text="",
            urls=["https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"],
            engine="url-explicit",
            depth=1,
            graph=graph,
        )
        assert payload.get("error_code") != "no_sources"
        assert all(reason.get("code") != "no_sources" for reason in payload["reasons"])
        assert payload["decision"] == "pass"
        assert payload["works_cited"] == 1
    finally:
        graph.close()


def test_inline_url_is_not_no_sources(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.trace_answer", _traced_without_notice)
    monkeypatch.setattr(
        "mooltrace.trace._clusters",
        lambda _graph: {"algorithm": "algo.WCC", "clusters": [], "cypher": None},
    )
    try:
        payload = check_answer(
            text="https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/",
            engine="url-inline",
            depth=1,
            graph=graph,
        )
        assert payload.get("error_code") != "no_sources"
        assert all(reason.get("code") != "no_sources" for reason in payload["reasons"])
        assert payload["decision"] == "pass"
    finally:
        graph.close()


def test_loopback_url_warns_and_does_not_pass(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        payload = check_answer(
            text="ssrf probe",
            urls=["http://127.0.0.1/secret", "http://10.0.0.1/x"],
            engine="ssrf",
            depth=1,
            graph=graph,
        )
        assert payload["decision"] == "warn"
        assert payload["exit_code"] == 2
        assert payload.get("errors")
        joined = " ".join(payload["errors"]).lower()
        assert "not public" in joined or "refused" in joined
    finally:
        graph.close()
