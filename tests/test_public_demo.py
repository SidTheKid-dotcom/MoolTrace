"""Public demo: four presets, no live HTTP, no arbitrary URLs."""

from pathlib import Path

from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.config import HEALTHLINE_CINNAMON_URL
from mooltrace.public_demo import is_preset, seed_offline_presets

OLIVE_OIL_URL = "https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"
from mooltrace.seed import load_demo_fixtures
from mooltrace.graph import Graph
from mooltrace.trace import check_answer, recheck_affected


def test_offline_presets_match_ui_and_skip_http(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seeded = seed_offline_presets(graph)
    assert {row["id"] for row in seeded} == {
        "nutrition-olive-oil",
        "nutrition-healthline",
        "clean-jsps",
        "not-in-graph",
    }
    block, warn, clean, missing = load_demo_fixtures()
    assert block["id"] == "nutrition-olive-oil"
    assert block["text"] == ""
    assert block["urls"] == [OLIVE_OIL_URL]
    assert warn["id"] == "nutrition-healthline"
    assert warn["urls"] == [HEALTHLINE_CINNAMON_URL]
    assert is_preset(block["engine"], block["text"], block["urls"])
    assert is_preset(warn["engine"], warn["text"], warn["urls"])
    assert is_preset(clean["engine"], clean["text"], clean["urls"])
    assert missing["id"] == "not-in-graph"
    assert is_preset(missing["engine"], missing["text"], missing["urls"])
    assert not is_preset("nutrition-coach", "", ["https://example.com/not-a-preset"])

    blocked = check_answer(block["text"], block["urls"], block["engine"], 3, graph=graph)
    assert blocked["decision"] == "block"
    assert blocked["exit_code"] == 1
    assert blocked["api_calls"] == 0
    assert (blocked.get("algorithm") or {}).get("name") == "algo.SPpaths"
    assert _fmt((blocked.get("algorithm") or {}).get("strength")) == "0.30"
    hop_words = {
        hop.get("reliance")
        for reason in blocked.get("reasons") or []
        for hop in reason.get("hops_evidence") or []
    }
    assert hop_words == {"mention"}
    assert any(
        (reason.get("notice_type") or "") == "retraction"
        and (reason.get("notice_doi") or "") == "10.1056/nejmc1806491"
        for reason in blocked.get("reasons") or []
    )

    warned = check_answer(warn["text"], warn["urls"], warn["engine"], 2, graph=graph)
    assert warned["decision"] == "warn"
    assert warned["exit_code"] == 2
    assert warned["api_calls"] == 0
    assert any(
        (reason.get("notice_type") or "") == "expression_of_concern"
        for reason in warned.get("reasons") or []
    )

    passed = check_answer(clean["text"], clean["urls"], clean["engine"], 2, graph=graph)
    assert passed["decision"] == "pass"
    assert passed["exit_code"] == 0
    assert passed["api_calls"] == 0


def test_presets_never_429_after_rate_limit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    from mooltrace import public_demo

    public_demo.reset_public_limits()
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.api.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    client = TestClient(app)
    cap = int(getattr(public_demo, "PUBLIC_LIVE_PER_MIN", 10))
    for _ in range(cap):
        burned = client.post(
            "/check-answer",
            json={
                "text": "not a preset",
                "urls": ["https://example.com/other"],
                "engine": "other",
                "depth": 1,
            },
        )
        assert burned.status_code in {400, 413, 429}
    extra = client.post(
        "/check-answer",
        json={
            "text": "still not a preset",
            "urls": ["https://example.com/other-2"],
            "engine": "other",
            "depth": 1,
        },
    )
    assert extra.status_code == 429
    warn = load_demo_fixtures()[1]
    preset = client.post(
        "/check-answer",
        json={
            "text": warn["text"],
            "urls": warn["urls"],
            "engine": warn["engine"],
            "depth": 2,
        },
    )
    assert preset.status_code == 200, preset.text
    assert preset.json()["decision"] == "warn"


def test_public_demo_rejects_oversized_draft(monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    from mooltrace import public_demo

    public_demo.reset_public_limits()
    client = TestClient(app)
    response = client.post(
        "/check-answer",
        json={
            "text": "a" * 100_001,
            "urls": ["https://www.healthline.com/nutrition/cinnamon-and-diabetes"],
            "engine": "oversize",
            "depth": 1,
        },
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_public_demo_recheck_affected_replays_olive_oil_block(tmp_path: Path, monkeypatch):
    """URL-only presets must recheck as block, not warn/incomplete.

    Injecting first-hop work DOIs as draft text mints a new answer_id, so
    the public-demo replay misses the seeded graph.
    """
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    block = load_demo_fixtures()[0]
    checked = check_answer(block["text"], block["urls"], block["engine"], 3, graph=graph)
    assert checked["decision"] == "block"
    assert checked["exit_code"] == 1
    out = recheck_affected("10.1056/nejmc1806491", graph=graph, depth=3)
    assert out["affected"] >= 1
    assert out["rechecks"], out
    rec = out["rechecks"][0]
    assert rec["decision"] == "block", rec
    assert rec["exit_code"] == 1
    assert "incomplete" not in (rec.get("summary") or "").lower()
    graph.close()


def test_entrypoint_documents_offline_seed():
    from pathlib import Path

    from mooltrace.config import ROOT

    entry = (ROOT / "scripts" / "docker-entrypoint-api.sh").read_text()
    assert "seed --if-empty --offline" in entry
    assert "MOOLTRACE_PUBLIC_DEMO" in entry


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}"
