"""In-app POST /agent: tool loop, validation, fallback, limits, grounding."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.config import HARVARD_VITAMIN_D_URL, ROOT
from mooltrace.graph import Graph
from mooltrace.public_demo import seed_offline_presets


UI = ROOT / "web" / "src" / "components" / "pre-ship.tsx"
HARVARD_DRAFT = (
    "Hand hygiene is discussed separately. "
    f"A nutrition coach cites {HARVARD_VITAMIN_D_URL}."
)
HARVARD_QUESTION = "Does vitamin D help prevent fractures in older adults?"
FAKE_KEY = "sk-test-KEY-MUST-NOT-LEAK-9f3a"
EVIL_URL = "https://evil.example/not-allowed"
FAKE_DOI = "10.9999/invented-citation"


def _seed(tmp_path: Path, monkeypatch) -> Graph:
    monkeypatch.setenv("MOOLTRACE_AGENT_SPEND", str(tmp_path / "agent_spend.json"))
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    graph = Graph(tmp_path / "agent.db")
    seed_offline_presets(graph)
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.graph.get_graph", lambda: graph)
    monkeypatch.setattr("mooltrace.api.get_graph", lambda: graph)
    from mooltrace import agent as agent_mod

    agent_mod.reset_agent_state()
    monkeypatch.setattr("mooltrace.agent.get_graph", lambda: graph)
    return graph


def _message(content=None, tool_calls=None, prompt=12, completion=8) -> dict:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        "model": "gpt-5.4-mini",
    }


def _tool_call(name: str, args: dict, ident: str = "call_1") -> dict:
    return {
        "id": ident,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _enable_model(monkeypatch, handler):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.test")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini")
    monkeypatch.setattr("mooltrace.agent._azure_post", handler)


def test_fallback_when_key_missing(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    try:
        client = TestClient(app)
        response = client.post(
            "/agent",
            json={
                "question": HARVARD_QUESTION,
                "draft": HARVARD_DRAFT,
                "urls": [HARVARD_VITAMIN_D_URL],
                "depth": 2,
                "engine": "nutrition-coach",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["model"] == "fallback"
        assert body["label"] == "rule-based fallback, no model"
        assert body["mode"] == "fallback"
        tools = [step["tool"] for step in body["steps"]]
        assert tools[0] == "check_answer"
        assert "rewrite_answer" in tools
        assert body["steps"][0]["summary"]["verdict"] == "block"
        assert body["steps"][0]["summary"]["exit_code"] == 1
        assert "Ishida" in body["shipped"]
        assert body["without_mooltrace"]["text"] == HARVARD_DRAFT
        assert body["without_mooltrace"]["note"] == "Without MoolTrace: this draft ships as written"
        assert FAKE_KEY not in json.dumps(body)
        assert "budget" in body
        assert "limit_usd" in body["budget"]
        assert "spent_usd" in body["budget"]
    finally:
        graph.close()


def test_fallback_on_azure_http_error(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)

    def boom(_payload, timeout_s=15.0):
        request = httpx.Request("POST", "https://example.test/openai/v1/chat/completions")
        response = httpx.Response(500, request=request, text="upstream")
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    _enable_model(monkeypatch, boom)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question=HARVARD_QUESTION,
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        assert out["model"] == "fallback"
        assert out["label"] == "rule-based fallback, no model"
        assert out["fallback_reason"] == "http_error"
        assert out["steps"][0]["tool"] == "check_answer"
        assert "Ishida" in out["shipped"]
        blob = json.dumps(out)
        assert FAKE_KEY not in blob
        assert "api-key" not in blob.lower()
    finally:
        graph.close()


def test_tool_loop_calls_existing_tools(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    calls: list[dict] = []

    def fake_post(payload, timeout_s=15.0):
        calls.append(payload)
        if len(calls) == 1:
            return _message(
                tool_calls=[
                    _tool_call(
                        "check_answer",
                        {
                            "text": HARVARD_DRAFT,
                            "urls": [HARVARD_VITAMIN_D_URL],
                            "engine": "nutrition-coach",
                            "depth": 2,
                        },
                    )
                ]
            )
        if len(calls) == 2:
            return _message(
                tool_calls=[
                    _tool_call(
                        "explain_path",
                        {
                            "text": HARVARD_DRAFT,
                            "urls": [HARVARD_VITAMIN_D_URL],
                            "engine": "nutrition-coach",
                            "depth": 2,
                        },
                        "call_2",
                    )
                ]
            )
        if len(calls) == 3:
            return _message(
                tool_calls=[
                    _tool_call(
                        "rewrite_answer",
                        {
                            "text": HARVARD_DRAFT,
                            "urls": [HARVARD_VITAMIN_D_URL],
                            "engine": "nutrition-coach",
                            "depth": 2,
                        },
                        "call_3",
                    )
                ]
            )
        return _message(
            content=(
                "Ship the rewrite. An earlier version of this answer cited "
                "Ishida et al. 2004; that paper was retracted in May 2025, "
                "so that source was removed."
            )
        )

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question=HARVARD_QUESTION,
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        assert out["model"] == "gpt-5.4-mini"
        assert out["label"] != "rule-based fallback, no model"
        names = [step["tool"] for step in out["steps"]]
        assert names == ["check_answer", "explain_path", "rewrite_answer"]
        assert out["steps"][0]["summary"]["verdict"] == "block"
        assert out["steps"][0]["summary"]["exit_code"] == 1
        assert out["steps"][0]["ms"] >= 0
        assert "Ishida" in out["shipped"]
        assert not out["shipped"].startswith("Ship the rewrite"), "model free text must never ship"
        assert out["shipped_verdict"]["verdict"] == "pass"
        assert out["agent_note"].startswith("Ship the rewrite")
        assert out["without_mooltrace"]["source"] == "draft"
        assert out["without_mooltrace"]["text"] == HARVARD_DRAFT
        assert out["without_mooltrace"]["note"] == "Without MoolTrace: this draft ships as written"
        assert all(call.get("tools") for call in calls)
        blob = json.dumps(out)
        assert FAKE_KEY not in blob
        assert "CREATE" not in json.dumps(calls)
    finally:
        graph.close()


def test_arg_validation_rejects_url_not_on_allow_list(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_post(payload, timeout_s=15.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return _message(
                tool_calls=[
                    _tool_call(
                        "check_answer",
                        {"text": "hi", "urls": [EVIL_URL], "depth": 2},
                    )
                ]
            )
        return _message(content="I cannot check that URL.")

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question="x",
            draft="hi",
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        step = out["steps"][0]
        assert step["tool"] == "check_answer"
        assert step["ok"] is False
        assert "allow" in (step["summary"].get("error") or "").lower()
        assert EVIL_URL in json.dumps(step["args"])
    finally:
        graph.close()


def test_arg_validation_rejects_doi_not_in_graph(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_post(payload, timeout_s=15.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return _message(
                tool_calls=[_tool_call("what_rests_on", {"doi": "not a doi"}, "call_bad")]
            )
        return _message(content="stopped")

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question="x",
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        step = out["steps"][0]
        assert step["tool"] == "what_rests_on"
        assert step["ok"] is False
        assert "doi" in (step["summary"].get("error") or "").lower()
    finally:
        graph.close()


def test_max_tool_calls_cap(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    azure_calls = {"n": 0}

    def fake_post(payload, timeout_s=15.0):
        azure_calls["n"] += 1
        if payload.get("tools"):
            ident = f"call_{azure_calls['n']}"
            return _message(
                tool_calls=[
                    _tool_call(
                        "explain_path",
                        {
                            "text": HARVARD_DRAFT,
                            "urls": [HARVARD_VITAMIN_D_URL],
                            "depth": 2,
                        },
                        ident,
                    )
                ]
            )
        return _message(content="contrast")

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import AGENT_MAX_TOOL_CALLS, run_agent

        out = run_agent(
            question=HARVARD_QUESTION,
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        tool_steps = [
            step for step in out["steps"] if step["tool"] != "contrast" and not step.get("guard")
        ]
        guards = [step["tool"] for step in out["steps"] if step.get("guard")]
        assert guards == ["check_answer", "rewrite_answer"], "model never checked, so MoolTrace did"
        assert len(tool_steps) == AGENT_MAX_TOOL_CALLS
        assert AGENT_MAX_TOOL_CALLS == 6
    finally:
        graph.close()


def test_grounding_replaces_invented_citation(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_post(payload, timeout_s=15.0):
        calls["n"] += 1
        if calls["n"] == 1:
            return _message(
                tool_calls=[
                    _tool_call(
                        "check_answer",
                        {
                            "text": HARVARD_DRAFT,
                            "urls": [HARVARD_VITAMIN_D_URL],
                            "engine": "nutrition-coach",
                            "depth": 2,
                        },
                    )
                ]
            )
        if payload.get("tools"):
            return _message(
                content=(
                    f"Vitamin D prevents fractures (Smith 2019; doi:{FAKE_DOI}; "
                    f"{EVIL_URL})."
                )
            )
        return _message(content="without tools the model ships the Harvard URL.")

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question=HARVARD_QUESTION,
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        assert FAKE_DOI not in out["shipped"]
        assert EVIL_URL not in out["shipped"]
        assert "Smith 2019" not in out["shipped"]
        assert "Ishida" in out["shipped"]
        assert out["grounding"]["replaced"] is True
        assert "tool results" in out["grounding"]["reason"].lower()
    finally:
        graph.close()


def test_rate_limit_public_demo(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    from mooltrace import agent as agent_mod

    agent_mod.reset_agent_state()
    try:
        client = TestClient(app)
        body = {
            "question": HARVARD_QUESTION,
            "draft": HARVARD_DRAFT,
            "urls": [HARVARD_VITAMIN_D_URL],
            "depth": 2,
            "engine": "nutrition-coach",
        }
        codes = []
        for _ in range(7):
            codes.append(client.post("/agent", json=body).status_code)
        assert codes[:6] == [200] * 6
        assert codes[6] == 429
    finally:
        graph.close()


def test_key_never_appears_in_response_or_logs(tmp_path, monkeypatch, caplog):
    graph = _seed(tmp_path, monkeypatch)
    caplog.set_level(logging.DEBUG)

    def fake_post(payload, timeout_s=15.0):
        logging.getLogger("mooltrace.agent").info("azure ok %s", list(payload))
        return _message(content="ok, no citations")

    _enable_model(monkeypatch, fake_post)
    try:
        client = TestClient(app)
        response = client.post(
            "/agent",
            json={
                "question": HARVARD_QUESTION,
                "draft": HARVARD_DRAFT,
                "urls": [HARVARD_VITAMIN_D_URL],
                "depth": 2,
                "engine": "nutrition-coach",
            },
        )
        blob = response.text + json.dumps(response.json()) + caplog.text
        assert FAKE_KEY not in blob
        assert "api-key" not in blob.lower()
        headers = json.dumps(dict(response.headers)).lower()
        assert FAKE_KEY.lower() not in headers
    finally:
        graph.close()


def test_budget_cap_uses_fallback(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    spend = tmp_path / "agent_spend.json"
    spend.write_text(
        json.dumps(
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 40.0,
                "runs_today": 0,
                "day": "2099-01-01",
            }
        )
    )
    monkeypatch.setenv("MOOLTRACE_AGENT_SPEND", str(spend))
    called = {"n": 0}

    def fake_post(payload, timeout_s=15.0):
        called["n"] += 1
        return _message(content="should not run")

    _enable_model(monkeypatch, fake_post)
    try:
        from mooltrace.agent import run_agent

        out = run_agent(
            question=HARVARD_QUESTION,
            draft=HARVARD_DRAFT,
            urls=[HARVARD_VITAMIN_D_URL],
            depth=2,
            engine="nutrition-coach",
        )
        assert called["n"] == 0
        assert out["model"] == "fallback"
        assert out["fallback_reason"] == "model budget reached"
        assert out["budget"]["spent_usd"] >= 40
        assert "Ishida" in out["shipped"]
    finally:
        graph.close()


def test_ui_has_run_the_agent_panel():
    src = UI.read_text()
    assert "Run the agent" in src
    assert 'data-testid="run-the-agent"' in src
    assert "/nw/agent" in src
    assert "rule-based fallback, no model" in src
    assert "without MoolTrace" in src or "without-mooltrace" in src
    assert "harvard-vitamin-d" in src


FORBIDDEN_IN_BLIND_DRAFT = ("mooltrace", "retract", "notice", "concern", "harvard", "vitamin")


def test_blind_draft_prompt_is_blind(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    calls: list[dict] = []
    question = "Is fish oil good for the heart?"

    def fake_post(payload, timeout_s=15.0):
        calls.append(payload)
        return _message(content="Fish oil may help some people. See https://www.webmd.com/heart.")

    _enable_model(monkeypatch, fake_post)
    monkeypatch.setattr("mooltrace.agent.probe_cited_url", lambda url: 200)
    monkeypatch.setattr("mooltrace.agent.check_answer", lambda *a, **k: {"decision": "pass", "exit_code": 0})
    try:
        from mooltrace.agent import blind_draft_system, run_agent
        from mooltrace.public_demo import LIVE_HOSTS

        system = blind_draft_system().lower()
        instructions = system
        for host in LIVE_HOSTS:
            instructions = instructions.replace(host, "")
        for word in FORBIDDEN_IN_BLIND_DRAFT:
            assert word not in instructions, word
        out = run_agent(question=question, draft="", urls=[], depth=2)
        first = calls[0]
        assert "tools" not in first
        assert first["messages"][0]["content"].lower() == system
        assert first["messages"][1]["content"] == question
        assert out["question_only"] is True
        assert "It was not told about MoolTrace." in out["disclosure"]
        assert out["without_mooltrace"]["source"] == "blind_draft"
    finally:
        graph.close()


def test_question_only_reports_off_list_and_missing_urls(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    ok_url = HARVARD_VITAMIN_D_URL
    missing = "https://www.healthline.com/nutrition/page-that-does-not-exist"
    draft = f"Some answer. Sources: {ok_url} {EVIL_URL} {missing}"
    replies = iter([_message(content=draft)])

    def fake_post(payload, timeout_s=15.0):
        return next(replies, _message(content="Done."))

    _enable_model(monkeypatch, fake_post)
    monkeypatch.setattr("mooltrace.agent.probe_cited_url", lambda url: 404 if url == missing else 200)
    try:
        from mooltrace.agent import URL_NOT_FOUND, URL_NOT_ON_LIST, run_agent

        out = run_agent(question="Does vitamin D prevent fractures?", draft="", urls=[], depth=2)
        statuses = {item["url"]: item["status"] for item in out["cited_urls"]}
        assert statuses == {ok_url: "ok", EVIL_URL: URL_NOT_ON_LIST, missing: URL_NOT_FOUND}
        assert out["without_mooltrace"]["text"] == draft
    finally:
        graph.close()


def test_question_only_needs_model_without_key(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    try:
        from mooltrace.agent import QUESTION_ONLY_NEEDS_MODEL, run_agent

        out = run_agent(question="Is coffee healthy?", draft="", urls=[], depth=2)
        assert out["mode"] == "fallback"
        assert out["steps"] == []
        assert out["without_mooltrace"]["note"] == QUESTION_ONLY_NEEDS_MODEL
    finally:
        graph.close()


def test_retraction_landed_lists_affected_answers(tmp_path, monkeypatch):
    graph = _seed(tmp_path, monkeypatch)
    try:
        from mooltrace.agent import ISHIDA_2004_DOI, run_agent

        out = run_agent(action="retraction_landed", doi=ISHIDA_2004_DOI, depth=2)
        assert out["action"] == "retraction_landed"
        assert [step["tool"] for step in out["steps"]] == ["what_rests_on", "recheck_affected"]
        assert out["affected_answers"], "the seeded Harvard preset rests on Ishida 2004"
        assert any("Ishida" in (item.get("rewrite") or "") for item in out["affected_answers"])
        keys = [(item["engine"], tuple(item["urls"]), item["rewrite"]) for item in out["affected_answers"]]
        assert len(keys) == len(set(keys)), "identical stored answers are grouped"
        assert all(item["count"] >= 1 for item in out["affected_answers"])
        assert "read-only" not in out["note"]
    finally:
        graph.close()


def test_ui_has_question_and_retraction_actions():
    source = UI.read_text(encoding="utf-8")
    assert "Ask the agent" in source
    assert "A retraction just landed" in source
    assert "HARVARD_AGENT_DRAFT" in source
