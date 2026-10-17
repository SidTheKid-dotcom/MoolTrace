"""Why-the-graph-decided panel equals fixture rows, not hard-coded copy."""

from __future__ import annotations

from pathlib import Path

from mooltrace.baseline import check_direct_doi
from mooltrace.graph import Graph
from mooltrace.public_demo import load_recorded_presets, seed_offline_presets
from mooltrace.seed import load_demo_fixtures
from mooltrace.summary import format_explain
from mooltrace.trace import check_answer

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "web" / "src" / "components" / "pre-ship.tsx"
HARVARD = "nutrition-harvard-vitamin-d"
OLIVE = "nutrition-olive-oil"
ISHIDA = "10.1016/j.amjmed.2004.05.019"
ISHIDA_NOTICE = "10.1016/j.amjmed.2025.03.001"
SATO = "10.1161/01.str.28.4.736"
ENGINE = "nutrition-coach"


def _recorded() -> dict:
    return {row["id"]: row for row in load_recorded_presets()["presets"]}


def _fixtures() -> dict:
    return {row["id"]: row for row in load_demo_fixtures()}


def _seed(tmp_path: Path) -> Graph:
    graph = Graph(tmp_path / "why.db")
    seed_offline_presets(graph)
    return graph


def test_why_graph_panel_matches_harvard_fixture_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    spec = _recorded()[HARVARD]
    row = _fixtures()[HARVARD]
    graph = _seed(tmp_path)
    payload = check_answer(row["text"], row["urls"], row["engine"], 2, graph=graph)
    graph.close()
    panel = payload["why_graph"]
    assert panel["title"] == "Why the graph decided"
    assert "CALL algo.SPpaths" in panel["cypher"]
    assert payload["answer_id"] in panel["cypher"]
    assert "$answer_id" not in panel["cypher"]
    hops = panel["path"]["hops"]
    fixture_hops = spec["hops"]
    assert len(hops) == len(fixture_hops)
    for got, want in zip(hops, fixture_hops):
        assert got["relation"] == want["reliance"]
        assert got["weight"] == want["weight"]
        assert got["sentence"] == want["sentence"]
        assert got["source_url"] == want["source_url"]
        assert got["fetched_at"] == want["fetched_at"]
    assert panel["path"]["nodes"][0] == "Answer"
    assert panel["path"]["nodes"][-1] == "Notice"
    direct = check_direct_doi(row["text"], row["urls"])
    recorded_direct = spec["without_graph"]
    assert panel["without_graph"]["notice_count"] == recorded_direct["notice_count"] == 0
    assert panel["without_graph"]["decision"] == recorded_direct["decision"] == direct["decision"]
    assert panel["without_graph"]["dois"] == recorded_direct["dois"] == direct["dois"]
    assert panel["without_graph"]["line"] == recorded_direct["line"]
    assert "0 notices" in panel["without_graph"]["line"]
    assert "would ship" in panel["without_graph"]["line"]
    assert panel["with_graph"]["depth"] == 2
    assert panel["with_graph"]["decision"] == "block"
    assert panel["with_graph"]["notice_doi"] == spec["by_depth"]["2"]["notice_doi"] == ISHIDA_NOTICE
    assert panel["with_graph"]["line"] == (
        f"Graph depth 2: retraction {ISHIDA_NOTICE} (2025-05) → BLOCK"
    )
    assert panel["contrast"] == f"{panel['without_graph']['line']}  |  {panel['with_graph']['line']}"
    assert payload["api_calls"] == 0


def test_hosted_harvard_strength_equals_recorded_live_strength(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    spec = _recorded()[HARVARD]
    row = _fixtures()[HARVARD]
    graph = _seed(tmp_path)
    payload = check_answer(row["text"], row["urls"], row["engine"], 2, graph=graph)
    graph.close()
    strength = (payload.get("algorithm") or {}).get("strength")
    live = spec["by_depth"]["2"]
    assert strength == live["strength"]
    assert strength == 0.4675
    extra = payload["why_graph"]["live_sppaths"]
    assert extra["strength"] == live["live_sppaths_strength"]
    assert extra["strength"] == 0.30250000000000005
    assert extra["root_doi"] == live["live_sppaths_root_doi"] == SATO
    assert extra["hops"] == live["live_sppaths_hops"] == ["mention", "mention"]


def test_why_graph_panel_matches_olive_oil_fixture_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    spec = _recorded()[OLIVE]
    row = _fixtures()[OLIVE]
    graph = _seed(tmp_path)
    payload = check_answer(row["text"], row["urls"], row["engine"], 3, graph=graph)
    graph.close()
    panel = payload["why_graph"]
    hops = panel["path"]["hops"]
    assert len(hops) == len(spec["hops"])
    for got, want in zip(hops, spec["hops"]):
        assert got["relation"] == want["reliance"]
        assert got["weight"] == want["weight"]
        assert got["sentence"] == want["sentence"]
        assert got["source_url"] == want["source_url"]
        assert got["fetched_at"] == want["fetched_at"]
    assert panel["without_graph"]["notice_count"] == spec["without_graph"]["notice_count"] == 0
    assert "would ship" in panel["without_graph"]["line"]
    assert panel["with_graph"]["decision"] == "warn"
    assert panel["with_graph"]["notice_doi"] == spec["by_depth"]["3"]["notice_doi"]
    assert (payload.get("algorithm") or {}).get("strength") == spec["by_depth"]["3"]["strength"]


def test_check_explain_prints_panel_from_payload():
    from mooltrace.__main__ import main
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["check", "--help"])
    assert exc.value.code == 0

    panel = {
        "title": "Why the graph decided",
        "cypher": "CALL algo.SPpaths({sourceNode: s, maxLen: 2})",
        "path": {
            "readable": "Answer → Source → Work → Work → Notice",
            "hops": [
                {
                    "relation": "mention",
                    "weight": 0.55,
                    "sentence": "included trial",
                    "source_url": "https://example.com/x",
                    "fetched_at": "2026-10-17T07:34:43+00:00",
                }
            ],
        },
        "without_graph": {"line": "Direct DOI check: 0 notices → would ship"},
        "with_graph": {"line": f"Graph depth 2: retraction {ISHIDA} → BLOCK"},
        "contrast": (
            f"Direct DOI check: 0 notices → would ship  |  "
            f"Graph depth 2: retraction {ISHIDA} → BLOCK"
        ),
        "live_sppaths": None,
    }
    text = format_explain(
        {
            "decision": "block",
            "exit_code": 1,
            "summary": "flagged",
            "why_graph": panel,
            "algorithm": {"explanation": "Decided by: algo.SPpaths, path strength 0.47"},
        }
    )
    assert "Why the graph decided" in text
    assert "CALL algo.SPpaths" in text
    assert "mention" in text
    assert "0.55" in text
    assert "included trial" in text
    assert "https://example.com/x" in text
    assert "2026-10-17T07:34:43+00:00" in text
    assert "Direct DOI check: 0 notices → would ship" in text
    assert f"Graph depth 2: retraction {ISHIDA} → BLOCK" in text


def test_ui_renders_why_the_graph_decided_from_payload():
    src = UI.read_text()
    assert 'data-testid="why-the-graph-decided"' in src
    assert "Why the graph decided" in src
    assert "why_graph" in src
    assert "without_graph" in src
    assert "max-h-20" in src
    assert 'data-testid="verdict-first"' in src
    assert src.index('data-testid="verdict-first"') < src.index("Draft answer")
