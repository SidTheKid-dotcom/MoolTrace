"""Scale: path queries stay answer-anchored; WCC must not walk the whole graph."""

from __future__ import annotations

from pathlib import Path

from mooltrace import cypher as C
from mooltrace.clients import InfraError
from mooltrace.config import RO_QUERY_TIMEOUT_MS
from mooltrace.graph import Graph


def _seed_wide_component(graph: Graph, *, answers: int = 12, reviews: int = 8, refs: int = 40) -> None:
    """One connected citation component plus an isolated flagged work.

    Reviews share a hub and each other so RESTS_ON*1..3 from every answer
    fans out across the whole component. That is the WCC join that timed
    out on the prevalence graph (5k works, 12 answers).
    """
    graph.merge_work("10.scale/hub", title="Hub")
    for r in range(reviews):
        review = f"10.scale/review-{r}"
        graph.merge_work(review, title=f"Review {r}", work_type="review")
        graph.rest_on(review, "10.scale/hub")
        for k in range(refs):
            paper = f"10.scale/paper-{r}-{k}"
            graph.merge_work(paper, title=f"Paper {r}-{k}")
            graph.rest_on(review, paper)
            graph.rest_on(paper, "10.scale/hub")
    graph.merge_notice(
        "10.scale/n-hub",
        "10.scale/hub",
        "expression_of_concern",
        "EoC",
        "publisher",
        "2025-01-01",
    )
    for i in range(answers):
        aid = f"ans-{i}"
        url = f"https://example.com/scale/{i}"
        graph.merge_answer(aid, f"eng-{i}", "h", "2026-10-15T00:00:00+00:00")
        graph.merge_source(url, f"Draft {i}", "example.com", True)
        graph.cite(aid, url)
        graph.source_rests_on(url, f"10.scale/review-{i % reviews}")
    graph.merge_answer("isolated", "other", "h2", "2026-10-15T00:00:00+00:00")
    graph.merge_source("https://example.com/scale/isolated", "Iso", "example.com", True)
    graph.cite("isolated", "https://example.com/scale/isolated")
    graph.merge_work("10.scale/iso", title="Isolated")
    graph.source_rests_on("https://example.com/scale/isolated", "10.scale/iso")
    graph.merge_notice(
        "10.scale/n-iso",
        "10.scale/iso",
        "retraction",
        "Retracted",
        "publisher",
        "2024-01-01",
    )


def test_wcc_answer_join_is_not_variable_length():
    """The prevalence timeout was WCC's unanchored RESTS_ON*1..3 join."""
    assert "RESTS_ON*1..3" not in C.WCC_CLUSTERS
    assert "[:RESTS_ON]->(w:Work)" in C.WCC_CLUSTERS or "[:RESTS_ON]->(w)" in C.WCC_CLUSTERS


def test_paths_cypher_expands_from_the_answer_before_notices():
    executed = C.paths_to_notice(3)
    answer_at = executed.index("MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)")
    path_at = executed.index("MATCH p = (s)-[:RESTS_ON*1..3]->(w)")
    notice_at = executed.index("MATCH (n:Notice)-[:FLAGS]->(w:Work)")
    assert answer_at < path_at < notice_at
    assert "(w)<-[:FLAGS]" not in executed
    assert "shortestPath" not in executed


def test_what_rests_on_walks_from_the_flagged_work_not_every_answer():
    executed = C.what_rests_on(3)
    notice_at = executed.index("MATCH (n:Notice)-[:FLAGS]->(w:Work)")
    path_at = executed.index("OPTIONAL MATCH p = (s:Source)-[:RESTS_ON*1..3]->(w)")
    answer_at = executed.index("OPTIONAL MATCH (a:Answer)-[:CITES]->(s)")
    assert notice_at < path_at < answer_at
    prefix = executed[:path_at]
    assert "OPTIONAL MATCH (a:Answer)-[:CITES]->(s:Source)" not in prefix


def test_shared_hubs_filters_answers_before_expansion():
    executed = C.SHARED_HUBS
    assert executed.index("WHERE a.id IN $answer_ids") < executed.index(
        "[:RESTS_ON*1..3]->(hub:Work)"
    )


def test_wcc_and_paths_stay_under_timeout_on_a_wide_component(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        _seed_wide_component(graph)
        clusters = graph.wcc_clusters()
        assert clusters.elapsed_ms < RO_QUERY_TIMEOUT_MS
        assert clusters.elapsed_ms < 500
        grouped = {tuple(sorted(row.get("answer_ids") or [])) for row in clusters.rows}
        isolated = [row for row in clusters.rows if "isolated" in (row.get("answer_ids") or [])]
        wide = [row for row in clusters.rows if "ans-0" in (row.get("answer_ids") or [])]
        assert isolated and isolated[0]["answer_ids"] == ["isolated"]
        assert wide and "isolated" not in (wide[0].get("answer_ids") or [])
        assert len(grouped) == 2
        run = graph.paths("ans-0", depth=3)
        assert run.elapsed_ms < 300
        assert run.rows
        assert any(row.get("root_doi") == "10.scale/hub" for row in run.rows)
        citation = graph.citation_edges("ans-0", depth=3)
        assert citation.elapsed_ms < 300
    finally:
        graph.close()


def test_wcc_timeout_is_infra(tmp_path: Path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    try:

        def boom(*_args, **_kwargs):
            raise TimeoutError("Query timed out")

        monkeypatch.setattr(graph, "_execute", boom)
        try:
            graph.wcc_clusters()
        except InfraError as exc:
            assert "timed out" in str(exc).lower()
        else:
            raise AssertionError("WCC timeout was not InfraError")
    finally:
        graph.close()
