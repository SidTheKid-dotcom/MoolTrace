"""Public demo live URL: allow-list, SSRF, size cap, per-IP limit, concurrency, timeout."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.config import ROOT
from mooltrace.graph import Graph
from mooltrace.public_demo import (
    PublicDemoRejected,
    guard_public_check,
    is_preset,
    live_host_allowed,
    seed_offline_presets,
    skip_http_for,
)
from mooltrace.seed import load_demo_fixtures


UI = ROOT / "web" / "src" / "components" / "pre-ship.tsx"
NON_PRESET_HEALTHLINE = "https://www.healthline.com/nutrition/olive-oil"
PASS_PAYLOAD = {
    "decision": "pass",
    "exit_code": 0,
    "summary": "mocked live check",
    "reasons": [],
}


def _reset(monkeypatch, live: bool = True) -> None:
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    if live:
        monkeypatch.setenv("MOOLTRACE_PUBLIC_LIVE", "1")
    else:
        monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    from mooltrace import public_demo

    public_demo.reset_public_limits()


def test_live_allow_list_hosts_only():
    assert live_host_allowed("https://www.healthline.com/nutrition/olive-oil")
    assert live_host_allowed("https://healthline.com/nutrition/foo")
    assert live_host_allowed("https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/")
    assert live_host_allowed("https://www.verywellhealth.com/x")
    assert live_host_allowed("https://www.medicalnewstoday.com/x")
    assert live_host_allowed("https://www.webmd.com/x")
    assert live_host_allowed("https://pubmed.ncbi.nlm.nih.gov/30461730/")
    assert live_host_allowed("https://doi.org/10.1056/nejmoa1200303")
    assert not live_host_allowed("https://example.com/x")
    assert not live_host_allowed("https://www.nhs.uk/live-well/best-way-to-wash-your-hands/")
    assert not live_host_allowed("https://healthline.com.evil.example/x")
    assert not live_host_allowed("https://evilhealthline.com/x")
    assert not live_host_allowed("http://127.0.0.1/")
    assert not live_host_allowed("https://not-healthline.com/")


def test_live_api_rejects_host_not_on_allow_list(monkeypatch):
    _reset(monkeypatch, live=True)
    client = TestClient(app)
    response = client.post(
        "/check-answer",
        json={
            "text": "",
            "urls": ["https://example.com/not-allowed"],
            "engine": "other",
            "depth": 1,
        },
    )
    assert response.status_code == 400
    assert "healthline.com" in response.json()["detail"]


def test_live_guard_rejects_host_not_on_allow_list(monkeypatch):
    _reset(monkeypatch, live=True)
    with pytest.raises(PublicDemoRejected) as exc:
        guard_public_check("other", "", ["https://example.com/not-allowed"])
    assert exc.value.status_code == 400
    assert "allow" in exc.value.detail.lower() or "healthline.com" in exc.value.detail.lower()


def test_live_guard_accepts_non_preset_healthline(monkeypatch):
    _reset(monkeypatch, live=True)
    guard_public_check("nutrition-coach", "", [NON_PRESET_HEALTHLINE])
    assert not is_preset("nutrition-coach", "", [NON_PRESET_HEALTHLINE])


def test_live_guard_ssrf_still_rejects_loopback(monkeypatch):
    _reset(monkeypatch, live=True)
    from mooltrace.ssrf import UnsafeURL

    with pytest.raises(UnsafeURL):
        guard_public_check("ssrf", "ssrf probe", ["http://127.0.0.1/secret"])


def test_live_guard_size_cap_still_413(monkeypatch):
    _reset(monkeypatch, live=True)
    with pytest.raises(PublicDemoRejected) as exc:
        guard_public_check("oversize", "a" * 100_001, [NON_PRESET_HEALTHLINE])
    assert exc.value.status_code == 413
    assert "too large" in exc.value.detail.lower()


def test_skip_http_stays_on_for_presets_even_when_live(monkeypatch):
    _reset(monkeypatch, live=True)
    warn = load_demo_fixtures()[1]
    assert skip_http_for(warn["engine"], warn["text"], warn["urls"]) is True
    assert skip_http_for("nutrition-coach", "", [NON_PRESET_HEALTHLINE]) is False


def test_skip_http_on_for_non_preset_when_live_off(monkeypatch):
    _reset(monkeypatch, live=False)
    assert skip_http_for("nutrition-coach", "", [NON_PRESET_HEALTHLINE]) is True


def test_live_rate_limit_is_per_ip_and_presets_exempt(tmp_path: Path, monkeypatch):
    _reset(monkeypatch, live=True)
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.api.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.api.check_answer", lambda *a, **k: dict(PASS_PAYLOAD))
    from mooltrace import public_demo

    client = TestClient(app)
    cap = public_demo.live_per_min()
    for i in range(cap):
        burned = client.post(
            "/check-answer",
            json={
                "text": "",
                "urls": [f"https://www.healthline.com/nutrition/olive-oil-{i}"],
                "engine": "live-ip-a",
                "depth": 1,
            },
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        assert burned.status_code == 200, burned.text
    extra = client.post(
        "/check-answer",
        json={
            "text": "",
            "urls": ["https://www.healthline.com/nutrition/olive-oil-extra"],
            "engine": "live-ip-a",
            "depth": 1,
        },
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert extra.status_code == 429, extra.text
    other = client.post(
        "/check-answer",
        json={
            "text": "",
            "urls": ["https://www.webmd.com/diet/olive-oil"],
            "engine": "live-ip-b",
            "depth": 1,
        },
        headers={"X-Forwarded-For": "203.0.113.20"},
    )
    assert other.status_code == 200, other.text
    warn = load_demo_fixtures()[1]
    monkeypatch.setattr("mooltrace.api.check_answer", lambda *a, **k: {"decision": "warn", "exit_code": 2, "summary": "preset", "reasons": []})
    preset = client.post(
        "/check-answer",
        json={
            "text": warn["text"],
            "urls": warn["urls"],
            "engine": warn["engine"],
            "depth": 2,
        },
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert preset.status_code == 200, preset.text
    graph.close()


def test_live_global_concurrency_rejects_second(monkeypatch):
    from mooltrace import public_demo

    _reset(monkeypatch, live=True)
    public_demo.acquire_live_slot()
    with pytest.raises(PublicDemoRejected) as exc:
        public_demo.acquire_live_slot()
    assert exc.value.status_code == 429
    assert "already running" in exc.value.detail.lower() or "live" in exc.value.detail.lower()
    public_demo.release_live_slot()
    public_demo.acquire_live_slot()
    public_demo.release_live_slot()


def test_live_hard_timeout_is_120s(monkeypatch):
    from mooltrace import public_demo

    _reset(monkeypatch, live=True)
    assert public_demo.live_timeout_s() == 120

    def slow() -> str:
        time.sleep(2)
        return "done"

    started = time.monotonic()
    with pytest.raises(PublicDemoRejected) as exc:
        public_demo.run_live(slow, timeout_s=0.2)
    assert exc.value.status_code == 504
    assert "120" in exc.value.detail or "limit" in exc.value.detail.lower()
    assert time.monotonic() - started < 1.5
    # Worker still holds the slot until it finishes; wait it out.
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            public_demo.acquire_live_slot()
            public_demo.release_live_slot()
            break
        except PublicDemoRejected:
            time.sleep(0.05)
    else:
        raise AssertionError("live slot was not released after the timed-out worker finished")


def test_ui_has_running_live_state():
    src = UI.read_text()
    assert 'data-testid="live-running"' in src
    lowered = src.lower()
    assert "running live, about 60" in lowered
    for host in (
        "healthline.com",
        "everydayhealth.com",
        "verywellhealth.com",
        "medicalnewstoday.com",
        "webmd.com",
        "pubmed.ncbi.nlm.nih.gov",
        "doi.org",
    ):
        assert host in src, host


def test_judges_documents_live_url_or_says_off():
    text = (ROOT / "JUDGES.md").read_text()
    lowered = text.lower()
    assert "healthline.com" in lowered
    live_on = "running live" in lowered or "about 60" in lowered
    live_off = "live url" in lowered and ("off" in lowered or "cannot" in lowered or "micro" in lowered)
    assert live_on or live_off, "JUDGES.md must document live URL on, or that micro cannot run it"
