"""Depth 1 / 2 / 3 toggle: recorded live fixtures must match the shown verdicts."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.config import ROOT
from mooltrace.graph import Graph
from mooltrace.public_demo import load_recorded_presets, seed_offline_presets
from mooltrace.seed import load_demo_fixtures
from mooltrace.trace import check_answer

UI = ROOT / "web" / "src" / "components" / "pre-ship.tsx"

EXPECTED = {
    "nutrition-olive-oil": {
        1: {"decision": "pass", "exit_code": 0, "notice_paths": 0},
        2: {
            "decision": "block",
            "exit_code": 1,
            "notice_type": "retraction",
            "notice_doi": "10.1056/nejmc1806491",
        },
        3: {
            "decision": "block",
            "exit_code": 1,
            "notice_type": "retraction",
            "notice_doi": "10.1056/nejmc1806491",
        },
    },
    "nutrition-healthline": {
        1: {"decision": "pass", "exit_code": 0, "notice_paths": 0},
        2: {
            "decision": "warn",
            "exit_code": 2,
            "notice_type": "expression_of_concern",
            "notice_doi": "10.2337/dc25-ec09",
        },
        3: {
            "decision": "warn",
            "exit_code": 2,
            "notice_type": "expression_of_concern",
            "notice_doi": "10.2337/dc25-ec09",
        },
    },
    "clean-jsps": {
        1: {"decision": "pass", "exit_code": 0, "notice_paths": 0},
        2: {"decision": "pass", "exit_code": 0, "notice_paths": 0},
        3: {"decision": "pass", "exit_code": 0, "notice_paths": 0},
    },
    "not-in-graph": {
        1: {"decision": "warn", "exit_code": 2, "notice_paths": 0},
        2: {"decision": "warn", "exit_code": 2, "notice_paths": 0},
        3: {"decision": "warn", "exit_code": 2, "notice_paths": 0},
    },
}


def _notice_reasons(payload: dict) -> list[dict]:
    return [
        reason
        for reason in payload.get("reasons") or []
        if reason.get("notice_type")
    ]


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}"


def test_ui_has_depth_toggle_one_two_three():
    src = UI.read_text()
    assert 'data-testid="depth-toggle"' in src
    assert 'type="number"' not in src
    assert "aria-label=\"Depth\"" in src or "aria-label='Depth'" in src
    assert "const DEPTHS = [1, 2, 3]" in src
    assert "data-depth={item}" in src
    assert "PASS (0 notice paths)" in src
    assert "BLOCK" in src
    assert "olive-oil" in src


def test_recorded_presets_include_live_by_depth(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    assert set(EXPECTED) <= set(recorded)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    fixtures = {row["id"]: row for row in load_demo_fixtures()}
    for ident, depths in EXPECTED.items():
        spec = recorded[ident]
        by_depth = spec.get("by_depth") or {}
        assert set(str(d) for d in depths) <= set(by_depth), ident
        row = fixtures[ident]
        for depth, want in depths.items():
            live = by_depth[str(depth)]
            assert live.get("recorded_at"), f"{ident} depth {depth}"
            assert live.get("fetch_date") or spec.get("fetch_date"), ident
            assert live["decision"] == want["decision"], (ident, depth)
            assert int(live["exit_code"]) == want["exit_code"], (ident, depth)
            payload = check_answer(
                row["text"], row["urls"], row["engine"], depth, graph=graph
            )
            assert payload["api_calls"] == 0, (ident, depth)
            assert payload["decision"] == live["decision"] == want["decision"], (
                ident,
                depth,
            )
            assert payload["exit_code"] == int(live["exit_code"]) == want["exit_code"]
            notices = _notice_reasons(payload)
            if want.get("notice_paths") == 0:
                assert notices == [], (ident, depth, notices)
                assert int(live.get("notice_paths") or 0) == 0
            else:
                assert notices, (ident, depth)
                assert any(
                    n.get("notice_type") == want["notice_type"]
                    and n.get("notice_doi") == want["notice_doi"]
                    for n in notices
                ), (ident, depth, notices)
                assert live.get("notice_doi") == want["notice_doi"]
                assert live.get("notice_type") == want["notice_type"]
                strength = (payload.get("algorithm") or {}).get("strength")
                if live.get("strength") is not None:
                    assert strength == live["strength"]
                if ident == "nutrition-olive-oil" and depth >= 2:
                    assert _fmt(strength) == "0.30"
                    hops = {
                        hop.get("reliance")
                        for reason in payload.get("reasons") or []
                        for hop in reason.get("hops_evidence") or []
                    }
                    assert hops == {"mention"}
    graph.close()


def test_public_demo_olive_oil_depth_one_pass_depth_three_block(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.api.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    client = TestClient(app)
    body = {
        "text": "",
        "urls": ["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],
        "engine": "nutrition-coach",
    }
    shallow = client.post("/check-answer", json={**body, "depth": 1})
    deep = client.post("/check-answer", json={**body, "depth": 3})
    assert shallow.status_code == 200, shallow.text
    assert deep.status_code == 200, deep.text
    assert shallow.json()["decision"] == "pass"
    assert shallow.json()["exit_code"] == 0
    assert not _notice_reasons(shallow.json())
    assert deep.json()["decision"] == "block"
    assert deep.json()["exit_code"] == 1
    assert any(
        reason.get("notice_doi") == "10.1056/nejmc1806491"
        for reason in deep.json().get("reasons") or []
    )
    graph.close()
