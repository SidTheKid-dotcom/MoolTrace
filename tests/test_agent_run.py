"""Recorded cursor-agent MCP check_answer must match today's seeded replay."""

from __future__ import annotations

import json
from pathlib import Path

from mooltrace.graph import Graph
from mooltrace.public_demo import seed_offline_presets
from mooltrace.trace import check_answer


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "examples" / "agent_runs"
HARVARD = "https://nutritionsource.hsph.harvard.edu/vitamin-d/"
ISHIDA = "10.1016/j.amjmed.2004.05.019"
MODEL = "cursor-grok-4.6-high-fast"


def _latest_run_dir() -> Path:
    dated = sorted(path for path in RUNS.glob("20*") if path.is_dir())
    assert dated, f"missing recorded agent runs under {RUNS}"
    return dated[-1]


def _stable_check(payload: dict) -> dict:
    reasons = list(payload.get("reasons") or [])
    hops = [
        hop.get("reliance")
        for reason in reasons
        for hop in reason.get("hops_evidence") or []
        if hop.get("reliance")
    ]
    notice = next((reason for reason in reasons if reason.get("notice_doi")), {})
    algo = payload.get("algorithm") or {}
    return {
        "decision": payload.get("decision"),
        "exit_code": payload.get("exit_code"),
        "notice_doi": notice.get("notice_doi"),
        "notice_type": notice.get("notice_type"),
        "root_doi": notice.get("root_doi"),
        "root_author": notice.get("root_author"),
        "root_year": notice.get("root_year"),
        "algorithm": algo.get("name"),
        "strength": algo.get("strength"),
        "reliances": hops,
    }


def test_recorded_agent_mcp_check_answer_matches_seeded_replay_today(tmp_path: Path):
    run_dir = _latest_run_dir()
    recorded = json.loads((run_dir / "run_a_mcp_calls.json").read_text())
    assert recorded.get("model") == MODEL
    calls = list(recorded.get("calls") or [])
    checks = [row for row in calls if row.get("tool") == "check_answer" and row.get("ok")]
    rewrites = [row for row in calls if row.get("tool") == "rewrite_answer" and row.get("ok")]
    assert checks, "Run A recording has no successful check_answer call"
    assert rewrites, "Run A recording has no successful rewrite_answer call"
    first = checks[0]
    args = first.get("arguments") or {}
    text = str(args.get("text") or "")
    urls = list(args.get("urls") or [])
    engine = str(args.get("engine") or "nutrition-coach")
    depth = int(args.get("depth") or 2)
    assert HARVARD in urls
    assert depth == 2
    recorded_stable = _stable_check(first.get("result") or {})
    assert recorded_stable["decision"] == "block"
    assert recorded_stable["exit_code"] == 1
    assert recorded_stable["notice_doi"] == ISHIDA
    assert recorded_stable["notice_type"] == "retraction"
    assert recorded_stable["root_author"] == "Ishida"
    assert recorded_stable["algorithm"] == "algo.SPpaths"
    assert recorded_stable["strength"] == 0.4675
    assert "uses_data_or_method" in recorded_stable["reliances"]
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        seed_offline_presets(graph)
        live = check_answer(text, urls, engine, depth, graph=graph)
    finally:
        graph.close()
    assert live.get("api_calls") == 0
    assert _stable_check(live) == recorded_stable
    rewrite = rewrites[0].get("result") or {}
    assert rewrite.get("rewritten") is True
    assert "Ishida et al. 2004" in str(rewrite.get("text") or "")
    assert (rewrite.get("check") or {}).get("decision") == "block"
    shipped = (run_dir / "run_a_with_mooltrace.txt").read_text()
    assert "SHIPPED:" in shipped
    shipped_body = shipped.split("SHIPPED:", 1)[1]
    assert "Ishida et al. 2004" in shipped_body
    without = (run_dir / "run_b_without_mooltrace.txt").read_text()
    assert "SHIPPED:" in without
    assert HARVARD in without.split("SHIPPED:", 1)[1]
    readme = (run_dir / "README.md").read_text()
    assert MODEL in readme
    assert "may vary" in readme.lower()
    assert "cursor-agent -p --model cursor-grok-4.6-high-fast" in readme
    assert "Agents That Act on Connected Data" in readme
    judges = (ROOT / "JUDGES.md").read_text()
    assert "Agent acting" in judges
    assert "examples/agent_runs/" in judges
    assert str(run_dir.relative_to(ROOT)) in (ROOT / "README.md").read_text()
