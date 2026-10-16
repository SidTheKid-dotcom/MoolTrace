"""Offline agent loop: check → rewrite → recheck.

An MCP host would call the same tools (check_answer, rewrite_answer,
explain_path, what_rests_on, recheck_affected). This script uses the
Python API so it runs without a paid LLM and without live HTTP.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mooltrace.graph import Graph
from mooltrace.rewrite import rewrite_answer
from mooltrace.trace import check_answer, explain_path, recheck_affected, what_rests_on

NOW = "2026-10-16T08:00:00+00:00"
URL = "https://example.com/cinnamon"
ENGINE = "nutrition-coach"
SILVA = "10.3390/nu14132773"
KHAN = "10.2337/diacare.26.12.3215"
EOC = "10.2337/dc25-ec09"


def _seed(graph: Graph) -> None:
    from mooltrace.trace import _answer_id

    answer_id = _answer_id(ENGINE, "", [URL])
    graph.merge_answer(answer_id, ENGINE, "hash", NOW)
    graph.merge_source(URL, "Cinnamon page", "example.com", True, fetched_at=NOW)
    graph.cite(answer_id, URL)
    graph.merge_work(
        SILVA,
        title="Silva 2022",
        year=2022,
        expanded=True,
        notice_checked=True,
        notice_checked_at=NOW,
    )
    graph.merge_work(
        KHAN,
        title="Khan 2003",
        year=2003,
        expanded=True,
        notice_checked=True,
        notice_checked_at=NOW,
    )
    graph.source_rests_on(URL, SILVA)
    graph.rest_on(SILVA, KHAN)
    graph.set_reliance(
        None,
        URL,
        SILVA,
        reliance="uses_data_or_method",
        weight=0.85,
        sentence="The page cites Silva 2022 on cinnamon and blood sugar.",
        evidence_from="page",
    )
    graph.set_reliance(
        SILVA,
        None,
        KHAN,
        reliance="uses_data_or_method",
        weight=0.85,
        sentence="Silva included Khan 2003 among the reviewed trials.",
        evidence_from="pmc",
    )
    graph.merge_notice(
        EOC,
        KHAN,
        "expression_of_concern",
        "Expression of concern",
        "publisher",
        "2025-08-20",
    )


def _offline():
    import mooltrace.trace as trace

    originals = {
        "judge_citation_edges": trace.judge_citation_edges,
        "expand_work": trace.expand_work,
        "notice_check": trace.notice_check,
        "fetch_page": trace.fetch_page,
    }

    def restore() -> None:
        for name, fn in originals.items():
            setattr(trace, name, fn)

    trace.judge_citation_edges = lambda *a, **k: None  # type: ignore[assignment]
    trace.expand_work = lambda *a, **k: None  # type: ignore[assignment]
    trace.notice_check = lambda *a, **k: None  # type: ignore[assignment]
    trace.fetch_page = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
        AssertionError("agent_loop is offline")
    )
    return restore


def run() -> dict:
    restore = _offline()
    root = Path(tempfile.mkdtemp(prefix="mooltrace-agent-loop-"))
    graph = Graph(root / "mooltrace.db")
    try:
        _seed(graph)
        first = check_answer("", [URL], ENGINE, 2, graph=graph)
        explained = explain_path("", [URL], ENGINE, 2, graph=graph)
        impact = what_rests_on(EOC, graph=graph, depth=2)
        rewritten = rewrite_answer("", [URL], ENGINE, 2, graph=graph)
        rechecks = recheck_affected(EOC, graph=graph, depth=2)
        print(f"1. check_answer → {first.get('decision')} (exit {first.get('exit_code')})")
        print(f"   algorithm: {(first.get('algorithm') or {}).get('name')}")
        print(f"2. explain_path → {explained.get('decision')}")
        print(f"3. what_rests_on → {impact.get('summary')}")
        print(
            f"4. rewrite_answer → {rewritten.get('method')} "
            f"recheck { (rewritten.get('recheck') or {}).get('decision') }"
        )
        print(
            f"5. recheck_affected → {rechecks.get('affected')} counted answers"
        )
        return {
            "check": first.get("decision"),
            "recheck": (rewritten.get("recheck") or {}).get("decision"),
            "affected": rechecks.get("affected"),
            "algorithm": (first.get("algorithm") or {}).get("name"),
        }
    finally:
        graph.close()
        restore()


def main() -> int:
    out = run()
    if out.get("check") != "warn":
        print("expected first check to warn", flush=True)
        return 1
    if out.get("algorithm") != "algo.SPpaths":
        print("expected algo.SPpaths on the first check", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
