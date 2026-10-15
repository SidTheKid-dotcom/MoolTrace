from pathlib import Path

from mooltrace.batch import run_batch
from mooltrace.clients import InfraError
from mooltrace.decision import NO_SOURCES_SUMMARY
from mooltrace.graph import Graph


def _jsonl(path: Path) -> Path:
    path.write_text(
        '{"id":"a","engine":"one","text":"alpha"}\n{"id":"b","engine":"two","text":"beta"}\n',
        encoding="utf-8",
    )
    return path


def test_batch_fails_on_block_not_warn(tmp_path: Path, monkeypatch):
    jsonl = _jsonl(tmp_path / "answers.jsonl")
    payloads = {
        "one": {"decision": "warn", "exit_code": 2, "summary": "eoc", "reasons": [], "errors": []},
        "two": {"decision": "block", "exit_code": 1, "summary": "retracted", "reasons": [], "errors": []},
    }

    monkeypatch.setattr(
        "mooltrace.batch.check_answer",
        lambda **kwargs: payloads[kwargs["engine"]],
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        blocked = run_batch(jsonl, graph=graph, fail_on="block")
        assert blocked["failed"] is True
        assert blocked["worst"] == "block"
        assert blocked["exit_code"] == 1
        assert blocked["remediation_clusters"]["algorithm"] == "algo.WCC"
    finally:
        graph.close()


def test_batch_warn_does_not_fail_by_default(tmp_path: Path, monkeypatch):
    jsonl = _jsonl(tmp_path / "answers.jsonl")
    payloads = {
        "one": {"decision": "warn", "exit_code": 2, "summary": "eoc", "reasons": [], "errors": []},
        "two": {"decision": "pass", "exit_code": 0, "summary": "ok", "reasons": [], "errors": []},
    }
    monkeypatch.setattr(
        "mooltrace.batch.check_answer",
        lambda **kwargs: payloads[kwargs["engine"]],
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        warned = run_batch(jsonl, graph=graph, fail_on="block")
        assert warned["failed"] is False
        assert warned["worst"] == "warn"
        assert warned["exit_code"] == 0
        fail_warn = run_batch(jsonl, graph=graph, fail_on="warn")
        assert fail_warn["failed"] is True
        assert fail_warn["exit_code"] == 2
    finally:
        graph.close()


def test_batch_annotations_and_stable_ids(tmp_path: Path, monkeypatch, capsys):
    jsonl = _jsonl(tmp_path / "answers.jsonl")
    payloads = {
        "one": {"decision": "warn", "exit_code": 2, "summary": "eoc", "reasons": [], "errors": []},
        "two": {"decision": "block", "exit_code": 1, "summary": "retracted", "reasons": [], "errors": []},
    }
    monkeypatch.setattr(
        "mooltrace.batch.check_answer",
        lambda **kwargs: payloads[kwargs["engine"]],
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        report = run_batch(jsonl, graph=graph, fail_on="block")
    finally:
        graph.close()
    assert [row["id"] for row in report["results"]] == ["a", "b"]
    err = capsys.readouterr().err
    assert "::warning file=" in err
    assert "::error file=" in err


def test_batch_no_sources_warns_and_respects_fail_on(tmp_path: Path, capsys):
    jsonl = tmp_path / "answers.jsonl"
    jsonl.write_text(
        '{"id":"prose","engine":"prose","text":"Cinnamon may help blood sugar."}\n',
        encoding="utf-8",
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        blocked = run_batch(jsonl, graph=graph, fail_on="block")
        assert blocked["failed"] is False
        assert blocked["worst"] == "warn"
        assert blocked["exit_code"] == 0
        assert blocked["results"][0]["decision"] == "warn"
        assert blocked["results"][0]["exit_code"] == 2
        assert blocked["results"][0]["reasons"][0]["code"] == "no_sources"
        assert blocked["results"][0]["summary"] == NO_SOURCES_SUMMARY
        fail_warn = run_batch(jsonl, graph=graph, fail_on="warn")
        assert fail_warn["failed"] is True
        assert fail_warn["worst"] == "warn"
        assert fail_warn["exit_code"] == 2
    finally:
        graph.close()
    err = capsys.readouterr().err
    assert "::warning file=" in err
    assert "no_sources" in err or "No verifiable citation" in err
    assert "::error file=" not in err


def test_batch_infra_is_exit_three(tmp_path: Path, monkeypatch):
    jsonl = tmp_path / "answers.jsonl"
    jsonl.write_text('{"id":"a","engine":"one","text":"alpha"}\n', encoding="utf-8")
    monkeypatch.setattr(
        "mooltrace.batch.check_answer",
        lambda **_k: (_ for _ in ()).throw(InfraError("graph timed out")),
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        report = run_batch(jsonl, graph=graph, fail_on="block")
        assert report["worst"] == "infra"
        assert report["exit_code"] == 3
        assert report["failed"] is True
        assert report["remediation_clusters"]["algorithm"] == "algo.WCC"
    finally:
        graph.close()


def test_batch_wcc_splits_disconnected_flagged_components(tmp_path: Path, monkeypatch):
    jsonl = _jsonl(tmp_path / "answers.jsonl")
    monkeypatch.setattr(
        "mooltrace.batch.check_answer",
        lambda **_k: {"decision": "pass", "exit_code": 0, "summary": "ok", "reasons": [], "errors": []},
    )
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "one", "h", "2026-10-15T00:00:00+00:00")
        graph.merge_answer("a2", "two", "h", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/a", "A", "example.com", True)
        graph.merge_source("https://example.com/b", "B", "example.com", True)
        graph.cite("a1", "https://example.com/a")
        graph.cite("a2", "https://example.com/b")
        graph.merge_work("10.1111/x", title="X")
        graph.merge_work("10.2222/y", title="Y")
        graph.source_rests_on("https://example.com/a", "10.1111/x")
        graph.source_rests_on("https://example.com/b", "10.2222/y")
        graph.merge_notice("10.1111/nx", "10.1111/x", "expression_of_concern", "EoC", "publisher", "2025-01-01")
        graph.merge_notice("10.2222/ny", "10.2222/y", "retraction", "Retracted", "publisher", "2024-01-01")
        report = run_batch(jsonl, graph=graph, fail_on="block")
        clusters = report["remediation_clusters"]["clusters"]
        assert len(clusters) == 2
        grouped = {tuple(sorted(row.get("answer_ids") or [])) for row in clusters}
        assert grouped == {("a1",), ("a2",)}
    finally:
        graph.close()
