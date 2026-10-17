"""algo.pageRank is registered in FalkorDBLite but is not a product algorithm.

On the recorded 2-hop evidence webs it either ties every reference of a
review or repeats the flagged paper already shown by algo.SPpaths. The
stock CALL is global, not one answer's web. Skip it: do not claim or
wire unused PageRank.
"""

from pathlib import Path

from mooltrace import cypher as C
from mooltrace.config import ROOT
from mooltrace.graph import Graph
from mooltrace.summary import format_summary
from mooltrace.trace import check_answer

PAGE = "https://example.com/nutrition/olive-oil"
ENGINE = "pagerank-unused"
REVIEW = "10.1186/1476-511x-13-154"
TRIAL = "10.1056/nejmoa1200303"
NOTICE = "10.1056/nejmc1806491"
NOW = "2026-10-16T15:52:44+00:00"


def _seed_hero_chain(graph: Graph) -> None:
    from mooltrace.trace import _answer_id

    answer_id = _answer_id(ENGINE, "", [PAGE])
    graph.merge_answer(answer_id, ENGINE, "hash", NOW)
    graph.merge_source(PAGE, "Olive oil", "example.com", True, fetched_at=NOW)
    graph.cite(answer_id, PAGE)
    graph.merge_work(REVIEW, title="Schwingshackl", year=2014, expanded=True, notice_checked=True, notice_checked_at=NOW)
    graph.merge_work(TRIAL, title="Estruch", year=2013, expanded=False, notice_checked=True, notice_checked_at=NOW)
    graph.source_rests_on(PAGE, REVIEW)
    graph.rest_on(REVIEW, TRIAL)
    graph.set_reliance(
        None,
        PAGE,
        REVIEW,
        reliance="mention",
        weight=0.55,
        sentence="Schwingshackl 2014 is cited.",
        evidence_from="page",
        evidence_url=PAGE,
        evidence_fetched_at=NOW,
        evidence_sha256="a" * 64,
    )
    graph.set_reliance(
        REVIEW,
        None,
        TRIAL,
        reliance="mention",
        weight=0.55,
        sentence="Estruch 2013 is cited.",
        evidence_from="pmc_html",
        evidence_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC4198773/",
        evidence_fetched_at=NOW,
        evidence_sha256="b" * 64,
    )
    graph.merge_notice(NOTICE, TRIAL, "retraction", "Retraction", "publisher", "2018-06-13")


def test_readme_does_not_claim_unused_pagerank():
    text = (ROOT / "README.md").read_text()
    assert "CALL algo.pageRank" not in text
    assert "algo.pageRank is not the verdict" not in text


def test_cypher_and_graph_drop_unused_pagerank():
    assert not hasattr(C, "PAGERANK_WORKS")
    assert not hasattr(Graph, "page_rank")


def test_check_answer_and_summary_omit_pagerank(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        _seed_hero_chain(graph)
        payload = check_answer("", [PAGE], ENGINE, 3, graph=graph)
        names = [item.get("name") for item in payload.get("queries") or []]
        assert "page_rank" not in names
        assert "most_relied_on" not in payload
        assert "pagerank" not in payload
        for reason in payload.get("reasons") or []:
            assert "pagerank" not in reason
        summary = format_summary(payload)
        assert "pageRank" not in summary
        assert "pagerank" not in summary.lower()
        assert "most-relied" not in summary.lower()
        assert payload["decision"] == "warn"
        assert payload["exit_code"] == 2
        assert "did not appear to rely" in payload["summary"]
        assert (payload.get("reasons") or [])[0].get("root_doi") == TRIAL
    finally:
        graph.close()
