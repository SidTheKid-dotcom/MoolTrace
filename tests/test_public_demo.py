"""Public demo: three presets, no live HTTP, no arbitrary URLs."""

from pathlib import Path

from mooltrace.public_demo import is_preset, seed_offline_presets
from mooltrace.seed import load_demo_fixtures
from mooltrace.graph import Graph
from mooltrace.trace import check_answer


def test_offline_presets_match_ui_and_skip_http(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "demo.db")
    seeded = seed_offline_presets(graph)
    assert {row["id"] for row in seeded} == {"nutrition-healthline", "lancet-hcq", "clean-jsps"}
    hero, lancet, clean = load_demo_fixtures()
    assert is_preset(hero["engine"], hero["text"], hero["urls"])
    assert is_preset(lancet["engine"], lancet["text"], lancet["urls"])
    assert is_preset(clean["engine"], clean["text"], clean["urls"])
    assert not is_preset("nutrition-coach", "", ["https://example.com/not-a-preset"])

    warn = check_answer(hero["text"], hero["urls"], hero["engine"], 2, graph=graph)
    assert warn["decision"] == "warn"
    assert warn["exit_code"] == 2
    assert warn["api_calls"] == 0
    assert (warn.get("algorithm") or {}).get("name") == "algo.SPpaths"
    assert any(
        (reason.get("notice_type") or "") == "expression_of_concern"
        for reason in warn.get("reasons") or []
    )

    block = check_answer(lancet["text"], lancet["urls"], lancet["engine"], 1, graph=graph)
    assert block["decision"] == "block"
    assert block["exit_code"] == 1
    assert block["api_calls"] == 0

    passed = check_answer(clean["text"], clean["urls"], clean["engine"], 2, graph=graph)
    assert passed["decision"] == "pass"
    assert passed["exit_code"] == 0
    assert passed["api_calls"] == 0


def test_entrypoint_documents_offline_seed():
    from pathlib import Path

    from mooltrace.config import ROOT

    entry = (ROOT / "scripts" / "docker-entrypoint-api.sh").read_text()
    assert "seed --if-empty --offline" in entry
    assert "MOOLTRACE_PUBLIC_DEMO" in entry
