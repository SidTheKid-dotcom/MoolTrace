"""Honest negative: a sourced page with no scholarly works, plus coverage lines."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.config import ROOT
from mooltrace.decision import decide
from mooltrace.graph import Graph
from mooltrace.public_demo import is_preset, load_recorded_presets, seed_offline_presets
from mooltrace.seed import load_demo_fixtures
from mooltrace.summary import format_summary
from mooltrace.trace import check_answer

HONEST = (
    "Nothing in the graph connects this answer to a study. "
    "This is not proof it is safe; the source may not be modelled."
)

UI = ROOT / "web" / "src" / "components" / "pre-ship.tsx"
JUDGES = ROOT / "JUDGES.md"
NOT_IN_GRAPH_ID = "not-in-graph"


def _retraction_path() -> dict:
    return {
        "hops": 2,
        "source_url": "https://example.com/nutrition/olive-oil",
        "root": {"doi": "10.1056/nejmoa1200303", "title": "Estruch"},
        "notice": {
            "doi": "10.1056/nejmc1806491",
            "type": "retraction",
            "label": "Retraction",
            "date": "2018-06-13",
        },
        "steps": [],
        "hops_evidence": [
            {
                "reliance": "mention",
                "weight": 0.55,
                "sentence": "Schwingshackl review.",
                "judged": True,
            },
            {
                "reliance": "mention",
                "weight": 0.55,
                "sentence": "Estruch 2013.",
                "judged": True,
            },
        ],
    }


def test_not_in_graph_is_warn_not_pass():
    verdict = decide(
        [],
        incomplete=False,
        depth=2,
        has_sources=True,
        works_cited=0,
        works_expanded=0,
    )
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == 2
    assert verdict["summary"] == HONEST
    assert "Nothing in the graph connects this answer to a study" in verdict["summary"]
    assert "not proof it is safe" in verdict["summary"]
    assert "may not be modelled" in verdict["summary"]
    assert verdict["reasons"][0]["code"] == "not_in_graph"
    assert verdict["coverage"] == "expanded 0 of 0 cited works"


def test_coverage_line_on_every_verdict():
    blocked = decide(
        [_retraction_path()],
        incomplete=True,
        depth=3,
        works_cited=26,
        works_expanded=15,
    )
    assert blocked["decision"] == "block"
    assert blocked["coverage"] == "expanded 15 of 26 cited works"
    assert all(reason.get("code") != "incomplete" for reason in blocked["reasons"])

    clean = decide(
        [],
        incomplete=False,
        depth=2,
        works_cited=1,
        works_expanded=1,
    )
    assert clean["decision"] == "pass"
    assert clean["coverage"] == "expanded 1 of 1 cited works"


def test_notice_path_does_not_keep_incomplete_flag_when_expansion_capped(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    fixtures = {row["id"]: row for row in load_demo_fixtures()}
    row = fixtures["nutrition-olive-oil"]
    payload = check_answer(row["text"], row["urls"], row["engine"], 3, graph=graph)
    assert payload["decision"] == "block"
    assert payload["coverage"].startswith("expanded ")
    assert " cited works" in payload["coverage"]
    assert not payload.get("incomplete")
    assert not any(
        (reason.get("code") or "") == "incomplete" for reason in payload.get("reasons") or []
    )
    assert not any(
        str(err).startswith("expanded ") for err in payload.get("errors") or []
    )
    assert "Coverage:" in format_summary(payload)
    graph.close()


def test_ui_has_not_in_graph_preset():
    src = UI.read_text()
    assert 'id: "not-in-graph"' in src
    assert "Not in the graph" in src
    assert "Nothing in the graph connects this answer to a study" in src
    assert "not proof it is safe" in src
    assert "may not be modelled" in src
    assert "expanded " in src
    assert " cited works" in src


def test_judges_has_not_in_graph_beat():
    text = JUDGES.read_text()
    assert "Not in the graph" in text
    assert "Nothing in the graph connects this answer to a study" in text
    assert "expanded " in text
    assert " cited works" in text


def test_recorded_not_in_graph_preset_replays_offline(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    assert NOT_IN_GRAPH_ID in recorded
    spec = recorded[NOT_IN_GRAPH_ID]
    assert spec["decision"] == "warn"
    assert spec.get("works") in ([], None)
    assert spec.get("hops") in ([], None)
    assert spec.get("notices") in ([], None)
    sources = spec.get("sources") or []
    assert sources, spec
    url = str(sources[0].get("url") or "")
    assert url.startswith("https://")
    digest = str(sources[0].get("content_hash") or spec.get("content_hash") or "")
    assert len(digest) == 64
    assert str(spec.get("label") or "").startswith("recorded live run on ")
    assert spec.get("fetch_date")
    fixtures = {row["id"]: row for row in load_demo_fixtures()}
    assert NOT_IN_GRAPH_ID in fixtures
    row = fixtures[NOT_IN_GRAPH_ID]
    assert row["text"] == ""
    assert row["urls"] == [url]
    assert is_preset(row["engine"], row["text"], row["urls"])

    graph = Graph(tmp_path / "demo.db")
    seeded = seed_offline_presets(graph)
    assert any(item["id"] == NOT_IN_GRAPH_ID for item in seeded)
    payload = check_answer(row["text"], row["urls"], row["engine"], 2, graph=graph)
    assert payload["api_calls"] == 0
    assert payload["decision"] == "warn"
    assert payload["exit_code"] == 2
    assert payload["works_cited"] == 0
    assert payload["coverage"] == "expanded 0 of 0 cited works"
    assert "Nothing in the graph connects this answer to a study" in payload["summary"]
    assert "not proof it is safe" in payload["summary"]
    assert "may not be modelled" in payload["summary"]
    assert not payload.get("incomplete")
    text = format_summary(payload)
    assert "nothing in the graph connects this answer to a study" in text.lower()
    assert "Coverage: expanded 0 of 0 cited works" in text
    graph.close()


def test_public_demo_accepts_not_in_graph_preset(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.api.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    fixtures = {row["id"]: row for row in load_demo_fixtures()}
    row = fixtures[NOT_IN_GRAPH_ID]
    client = TestClient(app)
    response = client.post(
        "/check-answer",
        json={
            "text": row["text"],
            "urls": row["urls"],
            "engine": row["engine"],
            "depth": 2,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"] == "warn"
    assert payload["coverage"] == "expanded 0 of 0 cited works"
    assert "Nothing in the graph connects this answer to a study" in payload["summary"]
    graph.close()
