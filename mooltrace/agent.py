"""In-app pre-ship agent: Azure tool loop with a deterministic fallback.

The model never writes Cypher. Tools are the existing MoolTrace functions.
Spend is persisted next to the graph so a process restart does not reset it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from mooltrace.config import ROOT, clamp_depth
from mooltrace.graph import get_graph
from mooltrace.ids import DOI_RE, URL_RE, clean_doi, valid_doi
from mooltrace.public_demo import (
    LIVE_ALLOW_LIST,
    LIVE_HOSTS,
    MAX_DRAFT_CHARS,
    MAX_URLS,
    PublicDemoRejected,
    live_host_allowed,
    load_preset_rows,
    public_demo_enabled,
)
from mooltrace.clients import CallStats, MoolTraceError, fetch_resource
from mooltrace.rewrite import rewrite_answer
from mooltrace.ssrf import UnsafeURL, public_http_url
from mooltrace.trace import check_answer, explain_path, recheck_affected, what_rests_on

log = logging.getLogger("mooltrace.agent")

AGENT_MAX_TOOL_CALLS = 6
AGENT_TIMEOUT_S = 45.0
AGENT_MAX_COMPLETION_TOKENS = 768
AGENT_CONTRAST_TOKENS = 384
AGENT_PER_IP = 6
AGENT_WINDOW_S = 10 * 60
AGENT_DAILY_CAP = 150
DEFAULT_BUDGET_USD = 40.0
DEFAULT_INPUT_USD_PER_M = 0.825
DEFAULT_OUTPUT_USD_PER_M = 4.95
FALLBACK_LABEL = "rule-based fallback, no model"
MODEL_NAME = "gpt-5.4-mini"
ISHIDA_2004_DOI = "10.1016/j.amjmed.2004.05.019"
URL_NOT_ON_LIST = "not checked: not on the allowed list"
URL_NOT_FOUND = "URL not found, not checked"
WITHOUT_DRAFT_NOTE = "Without MoolTrace: this draft ships as written"
QUESTION_ONLY_NEEDS_MODEL = (
    "Question-only mode needs the model. Try a preset "
    "(Harvard vitamin D, Healthline olive oil) or paste a draft with cited URLs."
)

_AUTHOR_YEAR = re.compile(
    r"\b([A-Z][A-Za-z'-]+)(?:\s+et\s+al\.?)?\s+\(?((?:19|20)\d{2})\)?"
)
_MONTHS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}
_SKIP_NAMES = _MONTHS | {
    "the",
    "this",
    "that",
    "doi",
    "http",
    "https",
    "depth",
    "exit",
    "block",
    "warn",
    "pass",
    "hand",
    "vitamin",
}

SYSTEM_PROMPT = (
    "You are a pre-ship checker for health-AI answers. Before shipping, call "
    "check_answer on the draft and its cited URLs. You never write Cypher. "
    "You never invent a citation, DOI, or URL. On BLOCK, call rewrite_answer "
    "and ship only after recheck is pass, or warn with the disclosure. Call "
    "explain_path to cite the deciding path. You may call what_rests_on on a "
    "DOI that already appeared in a tool result. Do not give medical advice. "
    "Do not call the draft wrong. An Expression of Concern is not a retraction. "
    "At most 6 tool calls."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_answer",
            "description": (
                "Check a health-AI draft against the evidence graph. Returns "
                "pass, warn, or block plus the algo.SPpaths path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "engine": {"type": "string"},
                    "depth": {"type": "integer", "minimum": 1, "maximum": 3},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_path",
            "description": "Explain the deciding citation path for the same draft.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "engine": {"type": "string"},
                    "depth": {"type": "integer", "minimum": 1, "maximum": 3},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rewrite_answer",
            "description": (
                "Rewrite only sentences that cite flagged work, then recheck. "
                "Deterministic template; does not invent citations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "engine": {"type": "string"},
                    "depth": {"type": "integer", "minimum": 1, "maximum": 3},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_rests_on",
            "description": (
                "Reverse lookup: how many stored answers rest on this notice "
                "or study DOI already in the graph."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doi": {"type": "string"}},
                "required": ["doi"],
            },
        },
    },
]

_lock = threading.Lock()
_hits_by_ip: dict[str, list[float]] = {}
_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "check_answer": check_answer,
    "explain_path": explain_path,
    "rewrite_answer": rewrite_answer,
    "what_rests_on": what_rests_on,
}


class AgentUnavailable(Exception):
    """Model cannot be used; caller should run the rule-based fallback."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def reset_agent_state() -> None:
    with _lock:
        _hits_by_ip.clear()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def input_usd_per_m() -> float:
    return _env_float("MOOLTRACE_AGENT_INPUT_USD_PER_M", DEFAULT_INPUT_USD_PER_M)


def output_usd_per_m() -> float:
    return _env_float("MOOLTRACE_AGENT_OUTPUT_USD_PER_M", DEFAULT_OUTPUT_USD_PER_M)


def budget_usd() -> float:
    return _env_float("MOOLTRACE_AGENT_BUDGET_USD", DEFAULT_BUDGET_USD)


def _spend_path() -> Path:
    override = os.environ.get("MOOLTRACE_AGENT_SPEND", "").strip()
    if override:
        return Path(override)
    db = os.environ.get("MOOLTRACE_DB", "").strip()
    parent = Path(db).parent if db else (ROOT / "data")
    return parent / "agent_spend.json"


def _empty_spend() -> dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "usd": 0.0,
        "runs_today": 0,
        "day": time.strftime("%Y-%m-%d", time.gmtime()),
        "updated_at": "",
    }


def _load_spend() -> dict[str, Any]:
    path = _spend_path()
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    state = _empty_spend()
    for key in state:
        if key in payload:
            state[key] = payload[key]
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if state.get("day") != today:
        state["day"] = today
        state["runs_today"] = 0
    try:
        state["usd"] = float(state.get("usd") or 0)
        state["prompt_tokens"] = int(state.get("prompt_tokens") or 0)
        state["completion_tokens"] = int(state.get("completion_tokens") or 0)
        state["runs_today"] = int(state.get("runs_today") or 0)
    except (TypeError, ValueError):
        state = _empty_spend()
    return state


def _save_spend(state: dict[str, Any]) -> None:
    path = _spend_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def spend_snapshot() -> dict[str, Any]:
    with _lock:
        state = _load_spend()
        return {
            "spent_usd": round(float(state["usd"]), 6),
            "limit_usd": budget_usd(),
            "prompt_tokens": int(state["prompt_tokens"]),
            "completion_tokens": int(state["completion_tokens"]),
        }


def budget_reached() -> bool:
    with _lock:
        return float(_load_spend()["usd"]) >= budget_usd()


def record_usage(prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    added = (
        prompt_tokens / 1_000_000.0 * input_usd_per_m()
        + completion_tokens / 1_000_000.0 * output_usd_per_m()
    )
    with _lock:
        state = _load_spend()
        state["prompt_tokens"] = int(state["prompt_tokens"]) + prompt_tokens
        state["completion_tokens"] = int(state["completion_tokens"]) + completion_tokens
        state["usd"] = float(state["usd"]) + added
        _save_spend(state)
        return {
            "spent_usd": round(float(state["usd"]), 6),
            "limit_usd": budget_usd(),
            "prompt_tokens": int(state["prompt_tokens"]),
            "completion_tokens": int(state["completion_tokens"]),
        }


def azure_api_key() -> str:
    return (os.environ.get("AZURE_OPENAI_API_KEY") or "").strip()


def azure_endpoint() -> str:
    return (os.environ.get("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")


def azure_model() -> str:
    return (os.environ.get("AZURE_OPENAI_DEPLOYMENT") or MODEL_NAME).strip() or MODEL_NAME


def _call_azure(payload: dict[str, Any], timeout_s: float = 15.0) -> dict[str, Any]:
    try:
        return _azure_post(payload, timeout_s=timeout_s)
    except AgentUnavailable:
        raise
    except httpx.HTTPError:
        log.warning("azure chat completions failed")
        raise AgentUnavailable("http_error") from None


def _azure_post(payload: dict[str, Any], timeout_s: float = 15.0) -> dict[str, Any]:
    key = azure_api_key()
    endpoint = azure_endpoint()
    if not key or not endpoint:
        raise AgentUnavailable("missing_key")
    url = f"{endpoint}/openai/v1/chat/completions"
    headers = {"api-key": key, "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=min(10.0, timeout_s))) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError:
        log.warning("azure chat completions failed")
        raise AgentUnavailable("http_error") from None
    except (TypeError, ValueError, json.JSONDecodeError):
        log.warning("azure chat completions returned non-json")
        raise AgentUnavailable("http_error") from None
    if not isinstance(body, dict):
        raise AgentUnavailable("http_error")
    usage = body.get("usage") or {}
    record_usage(int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
    return body


def _preset_urls() -> set[str]:
    found: set[str] = set()
    for row in load_preset_rows():
        for url in row.get("urls") or []:
            item = str(url or "").strip()
            if item:
                found.add(item)
    return found


def agent_url_allowed(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        public_http_url(raw, reason="url", resolve_dns=False)
    except UnsafeURL:
        return False
    if live_host_allowed(raw):
        return True
    return raw in _preset_urls()


def _doi_in_graph(doi: str, graph) -> bool:
    if graph.work_row(doi):
        return True
    run = graph.run(
        "notice_present",
        "MATCH (n:Notice {doi: $doi}) RETURN n.doi AS doi LIMIT 1",
        {"doi": doi},
        read_only=True,
    )
    return bool(run.rows)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
    return {}


def _validate_draft_args(args: dict[str, Any]) -> str | None:
    urls = args.get("urls") or []
    if urls is None:
        urls = []
    if not isinstance(urls, list):
        return "urls must be a list"
    if len(urls) > MAX_URLS:
        return "too many URLs"
    text = args.get("text") or ""
    if not isinstance(text, str) or len(text) > MAX_DRAFT_CHARS:
        return "draft is too large"
    for url in urls:
        if not isinstance(url, str) or not agent_url_allowed(url):
            return (
                "URL is not on the public-demo allow-list "
                f"({LIVE_ALLOW_LIST}) and is not a seeded preset."
            )
    depth = args.get("depth", 2)
    try:
        clamp_depth(int(depth))
    except (TypeError, ValueError):
        return "depth must be 1, 2, or 3"
    return None


def _validate_doi_arg(args: dict[str, Any], graph) -> str | None:
    raw = str(args.get("doi") or "")
    doi = clean_doi(raw)
    if not valid_doi(doi):
        return f"not a DOI: {raw!r}"
    if not _doi_in_graph(doi, graph):
        return f"DOI is not in the graph: {doi}"
    args["doi"] = doi
    return None


def _compact(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"error": str(result)[:300]}
    out: dict[str, Any] = {}
    for key in (
        "decision",
        "exit_code",
        "summary",
        "text",
        "explanation",
        "rewritten",
        "method",
        "notice_doi",
        "affected",
    ):
        if key in result:
            out[key] = result[key]
    reasons = []
    for reason in result.get("reasons") or []:
        if not isinstance(reason, dict):
            continue
        reasons.append(
            {
                "code": reason.get("code"),
                "notice_doi": reason.get("notice_doi"),
                "notice_type": reason.get("notice_type"),
                "root_doi": reason.get("root_doi"),
                "root_author": reason.get("root_author")
                or (reason.get("root") or {}).get("first_author"),
                "root_year": reason.get("root_year") or (reason.get("root") or {}).get("year"),
                "source_url": reason.get("source_url"),
                "hops": [
                    hop.get("reliance")
                    for hop in (reason.get("hops_evidence") or [])
                    if isinstance(hop, dict)
                ],
            }
        )
    if reasons:
        out["reasons"] = reasons
    algo = result.get("algorithm") or {}
    if isinstance(algo, dict) and algo:
        out["algorithm"] = {
            "name": algo.get("name"),
            "strength": algo.get("strength"),
            "explanation": algo.get("explanation"),
        }
    path = (result.get("reason") or {}).get("steps") if isinstance(result.get("reason"), dict) else None
    if path:
        out["path"] = path
    recheck = result.get("recheck")
    if isinstance(recheck, dict):
        out["recheck"] = {
            "decision": recheck.get("decision"),
            "exit_code": recheck.get("exit_code"),
        }
    return out


def _step_summary(name: str, result: Any, error: str | None = None) -> dict[str, Any]:
    if error:
        return {"error": error}
    compact = _compact(result)
    hops = []
    for reason in (result.get("reasons") or []) if isinstance(result, dict) else []:
        for hop in reason.get("hops_evidence") or []:
            word = hop.get("reliance")
            if word:
                hops.append(word)
    path = " × ".join(hops) if hops else compact.get("explanation")
    return {
        "verdict": compact.get("decision") or (compact.get("recheck") or {}).get("decision"),
        "exit_code": compact.get("exit_code")
        if compact.get("exit_code") is not None
        else (compact.get("recheck") or {}).get("exit_code"),
        "path": path,
        "notice_doi": compact.get("notice_doi")
        or next(
            (
                item.get("notice_doi")
                for item in compact.get("reasons") or []
                if item.get("notice_doi")
            ),
            None,
        ),
        "summary": compact.get("summary") or compact.get("text") or compact.get("explanation"),
        "affected": compact.get("affected"),
        "rewritten": compact.get("rewritten"),
    }


def _execute_tool(name: str, args: dict[str, Any], graph, defaults: dict[str, Any]) -> dict[str, Any]:
    if name not in _HANDLERS:
        return {"ok": False, "error": f"unknown tool {name}", "result": None}
    if name in {"check_answer", "explain_path", "rewrite_answer"}:
        merged = {
            "text": defaults.get("draft") or "",
            "urls": list(defaults.get("urls") or []),
            "engine": defaults.get("engine") or "draft",
            "depth": defaults.get("depth") or 2,
        }
        merged.update({k: v for k, v in args.items() if v is not None})
        merged["depth"] = clamp_depth(merged.get("depth"))
        merged["engine"] = str(merged.get("engine") or "draft")[:80]
        if not isinstance(merged.get("urls"), list):
            merged["urls"] = list(defaults.get("urls") or [])
        err = _validate_draft_args(merged)
        if err:
            return {"ok": False, "error": err, "result": None, "args": merged}
        started = time.monotonic()
        if name == "rewrite_answer":
            payload = rewrite_answer(
                merged["text"],
                merged["urls"],
                merged["engine"],
                merged["depth"],
                graph=graph,
            )
        elif name == "explain_path":
            payload = explain_path(
                merged["text"],
                merged["urls"],
                merged["engine"],
                merged["depth"],
                graph=graph,
            )
        else:
            payload = check_answer(
                merged["text"],
                merged["urls"],
                merged["engine"],
                merged["depth"],
                graph=graph,
            )
        ms = round((time.monotonic() - started) * 1000, 2)
        return {"ok": True, "error": None, "result": payload, "args": merged, "ms": ms}
    doi_args = dict(args)
    err = _validate_doi_arg(doi_args, graph)
    if err:
        return {"ok": False, "error": err, "result": None, "args": {"doi": args.get("doi")}}
    started = time.monotonic()
    payload = what_rests_on(doi_args["doi"], graph=graph)
    ms = round((time.monotonic() - started) * 1000, 2)
    return {"ok": True, "error": None, "result": payload, "args": {"doi": doi_args["doi"]}, "ms": ms}


def _planner(defaults: dict[str, Any], graph) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    check = _execute_tool("check_answer", {}, graph, defaults)
    steps.append(_public_step("check_answer", check))
    decision = ""
    if check["ok"] and isinstance(check["result"], dict):
        decision = str(check["result"].get("decision") or "")
    if decision != "pass":
        explained = _execute_tool("explain_path", {}, graph, defaults)
        steps.append(_public_step("explain_path", explained))
        rewritten = _execute_tool("rewrite_answer", {}, graph, defaults)
        steps.append(_public_step("rewrite_answer", rewritten))
        notice = None
        if check["ok"] and isinstance(check["result"], dict):
            for reason in check["result"].get("reasons") or []:
                notice = reason.get("notice_doi") or reason.get("root_doi")
                if notice:
                    break
        if notice:
            rests = _execute_tool("what_rests_on", {"doi": notice}, graph, defaults)
            if rests["ok"] or rests.get("error"):
                steps.append(_public_step("what_rests_on", rests))
    return steps


def _public_step(name: str, executed: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": name,
        "args": executed.get("args") or {},
        "ms": executed.get("ms") if executed.get("ms") is not None else 0,
        "ok": bool(executed.get("ok")),
        "summary": _step_summary(name, executed.get("result"), executed.get("error")),
        "result": _compact(executed.get("result")) if executed.get("ok") else None,
    }


def _shipped_from_steps(steps: list[dict[str, Any]], draft: str) -> str:
    for step in reversed(steps):
        if step.get("tool") == "rewrite_answer" and step.get("ok"):
            text = (step.get("result") or {}).get("text")
            if text:
                return str(text)
    for step in steps:
        if step.get("tool") == "check_answer" and step.get("ok"):
            if (step.get("result") or {}).get("decision") == "pass":
                return draft
    return draft


def _citations_in(text: str) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    dois = [clean_doi(item) for item in DOI_RE.findall(text or "") if valid_doi(clean_doi(item))]
    urls = [item.rstrip(").,;") for item in URL_RE.findall(text or "")]
    authors: list[tuple[str, str]] = []
    for name, year in _AUTHOR_YEAR.findall(text or ""):
        if name.lower() in _SKIP_NAMES:
            continue
        authors.append((name, year))
    return dois, urls, authors


def _in_corpus(needle: str, corpus: str) -> bool:
    return needle.lower() in corpus.lower()


def grounding_problems(text: str, corpus: str) -> list[str]:
    problems: list[str] = []
    dois, urls, authors = _citations_in(text)
    for doi in dois:
        if doi and not _in_corpus(doi, corpus):
            problems.append(doi)
    for url in urls:
        host_ok = False
        try:
            host = (urlparse(url).hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if host and _in_corpus(host, corpus) and _in_corpus(url.split("://", 1)[-1][:40], corpus):
                host_ok = _in_corpus(url, corpus) or _in_corpus(url.rstrip("/"), corpus)
        except ValueError:
            host_ok = False
        if url and not (_in_corpus(url, corpus) or _in_corpus(url.rstrip("/"), corpus) or host_ok):
            problems.append(url)
    lowered = corpus.lower()
    for name, year in authors:
        if name.lower() in lowered and year in corpus:
            continue
        if f"{name.lower()} et al. {year}" in lowered:
            continue
        problems.append(f"{name} {year}")
    return problems


def _corpus_from(steps: list[dict[str, Any]], draft: str, urls: list[str], question: str) -> str:
    parts = [draft or "", question or "", " ".join(urls or [])]
    for step in steps:
        parts.append(json.dumps(step.get("result") or {}, sort_keys=True))
        parts.append(json.dumps(step.get("summary") or {}, sort_keys=True))
        parts.append(json.dumps(step.get("args") or {}, sort_keys=True))
    return "\n".join(parts)


def _apply_grounding(
    candidate: str,
    steps: list[dict[str, Any]],
    defaults: dict[str, Any],
    graph,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    corpus = _corpus_from(steps, defaults.get("draft") or "", defaults.get("urls") or [], defaults.get("question") or "")
    problems = grounding_problems(candidate, corpus)
    if not problems:
        return candidate, {"replaced": False, "reason": "all citations appear in tool results"}, steps
    already = any(step.get("tool") == "rewrite_answer" and step.get("ok") for step in steps)
    if not already:
        rewritten = _execute_tool("rewrite_answer", {}, graph, defaults)
        steps = steps + [_public_step("rewrite_answer", rewritten)]
    shipped = _shipped_from_steps(steps, defaults.get("draft") or "")
    reason = (
        "Final text cited "
        + ", ".join(problems[:6])
        + " which did not appear in the tool results, so the deterministic rewrite was shipped instead."
    )
    return shipped, {"replaced": True, "reason": reason, "problems": problems[:6]}, steps


def _ensure_checked_and_fixed(
    steps: list[dict[str, Any]], defaults: dict[str, Any], graph
) -> list[dict[str, Any]]:
    """The model may skip tools. The shipped text must still be checked, and fixed if not pass."""
    checks = [step for step in steps if step.get("tool") == "check_answer" and step.get("ok")]
    if not checks:
        executed = _execute_tool("check_answer", {}, graph, defaults)
        steps = steps + [{**_public_step("check_answer", executed), "guard": True}]
        checks = [steps[-1]] if executed.get("ok") else []
    decision = str(((checks[-1].get("result") or {}) if checks else {}).get("decision") or "")
    rewritten = any(step.get("tool") == "rewrite_answer" and step.get("ok") for step in steps)
    if decision != "pass" and not rewritten:
        executed = _execute_tool("rewrite_answer", {}, graph, defaults)
        steps = steps + [{**_public_step("rewrite_answer", executed), "guard": True}]
    return steps


def _finalize(
    final: str, steps: list[dict[str, Any]], defaults: dict[str, Any], graph
) -> tuple[str, dict[str, Any], list[dict[str, Any]], str]:
    """Ship tool output only. The model's own words become a note, dropped if they cite anything unseen."""
    steps = _ensure_checked_and_fixed(steps, defaults, graph)
    draft = defaults.get("draft") or ""
    shipped = _shipped_from_steps(steps, draft)
    note = (final or "").strip()
    corpus = _corpus_from(steps, draft, defaults.get("urls") or [], defaults.get("question") or "")
    problems = grounding_problems(note, corpus) if note else []
    if problems:
        reason = (
            "The model's text cited "
            + ", ".join(problems[:6])
            + " which did not appear in the tool results, so it was not shown or shipped."
        )
        return shipped, {"replaced": True, "reason": reason, "problems": problems[:6]}, steps, ""
    return shipped, {"replaced": False, "reason": "shipped text is tool output"}, steps, note


def drafting_disclosure() -> str:
    return (
        f"The drafting model was told to cite only from: {LIVE_ALLOW_LIST}. "
        "It was not told about MoolTrace."
    )


def blind_draft_system() -> str:
    hosts = ", ".join(sorted(LIVE_HOSTS))
    return (
        "Answer for a general audience. Cite 1-3 pages. "
        f"Cite only pages on these publisher hosts: {hosts}."
    )


def extract_cited_urls(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for item in URL_RE.findall(text or ""):
        url = item.rstrip(").,;")
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def probe_cited_url(url: str) -> int:
    status, _ctype, _body = fetch_resource(url, CallStats())
    return int(status)


def validate_cited_url(url: str) -> dict[str, Any]:
    raw = (url or "").strip()
    report: dict[str, Any] = {"url": raw, "ok": False, "status": URL_NOT_ON_LIST}
    if not raw:
        report["status"] = URL_NOT_FOUND
        return report
    if not live_host_allowed(raw):
        return report
    try:
        status = probe_cited_url(raw)
    except (MoolTraceError, UnsafeURL, OSError, ValueError, TypeError):
        report["status"] = URL_NOT_FOUND
        return report
    report["http_status"] = status
    if status >= 400:
        report["status"] = URL_NOT_FOUND
        return report
    report["ok"] = True
    report["status"] = "ok"
    return report


def validate_cited_urls(urls: list[str]) -> list[dict[str, Any]]:
    return [validate_cited_url(item) for item in urls]


def _without_draft(draft: str) -> dict[str, Any]:
    return {
        "text": draft,
        "source": "draft",
        "note": WITHOUT_DRAFT_NOTE,
    }


def _shipped_verdict(steps: list[dict[str, Any]]) -> dict[str, Any]:
    for step in reversed(steps):
        if step.get("tool") in {"rewrite_answer", "check_answer"} and step.get("ok"):
            summary = step.get("summary") or {}
            return {"verdict": summary.get("verdict"), "exit_code": summary.get("exit_code")}
    return {"verdict": None, "exit_code": None}


def _response(
    *,
    mode: str,
    model: str,
    steps: list[dict[str, Any]],
    shipped: str,
    without: dict[str, Any],
    grounding: dict[str, Any],
    fallback_reason: str | None,
    elapsed_ms: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label = FALLBACK_LABEL if mode == "fallback" else model
    payload = {
        "mode": mode,
        "model": model if mode == "model" else "fallback",
        "label": label,
        "fallback_reason": fallback_reason,
        "steps": [
            {
                "tool": step["tool"],
                "args": step.get("args") or {},
                "ms": step.get("ms") or 0,
                "ok": step.get("ok"),
                "summary": step.get("summary") or {},
                **({"guard": True} if step.get("guard") else {}),
            }
            for step in steps
        ],
        "shipped": shipped,
        "shipped_verdict": _shipped_verdict(steps),
        "without_mooltrace": without,
        "grounding": grounding,
        "budget": spend_snapshot(),
        "elapsed_ms": round(elapsed_ms, 2),
    }
    if extra:
        payload.update(extra)
    return payload


def _user_prompt(question: str, draft: str, urls: list[str], depth: int, engine: str) -> str:
    listed = "\n".join(urls) if urls else "(none)"
    return (
        f"Question: {question or '(none)'}\n"
        f"Draft:\n{draft}\n"
        f"Cited URLs:\n{listed}\n"
        f"Engine: {engine}\n"
        f"Depth: {depth}\n"
        "Check this draft against the evidence graph before shipping."
    )


def _model_loop(defaults: dict[str, Any], graph, deadline: float) -> tuple[list[dict[str, Any]], str]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _user_prompt(
                defaults["question"],
                defaults["draft"],
                defaults["urls"],
                defaults["depth"],
                defaults["engine"],
            ),
        },
    ]
    steps: list[dict[str, Any]] = []
    final = ""
    while len(steps) < AGENT_MAX_TOOL_CALLS:
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise AgentUnavailable("timeout")
        payload = {
            "model": azure_model(),
            "messages": messages,
            "tools": TOOLS,
            "max_completion_tokens": AGENT_MAX_COMPLETION_TOKENS,
        }
        if budget_reached():
            raise AgentUnavailable("model budget reached")
        body = _call_azure(payload, timeout_s=min(15.0, remaining))
        choice = ((body.get("choices") or [{}])[0].get("message")) or {}
        tool_calls = choice.get("tool_calls") or []
        if not tool_calls:
            final = str(choice.get("content") or "")
            break
        messages.append(
            {
                "role": "assistant",
                "content": choice.get("content") or None,
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            if len(steps) >= AGENT_MAX_TOOL_CALLS:
                break
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            args = _parse_args(fn.get("arguments"))
            executed = _execute_tool(name, args, graph, defaults)
            steps.append(_public_step(name or "unknown", executed))
            tool_body = executed.get("error") or _compact(executed.get("result"))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or "",
                    "content": json.dumps(tool_body)[:8000],
                }
            )
    return steps, final


def _question_only_extra(*, cited_urls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "question_only": True,
        "disclosure": drafting_disclosure(),
        "cited_urls": cited_urls or [],
    }


def _question_only_needs_model(started: float, reason: str) -> dict[str, Any]:
    return _response(
        mode="fallback",
        model="fallback",
        steps=[],
        shipped="",
        without={
            "text": "",
            "source": "none",
            "note": QUESTION_ONLY_NEEDS_MODEL,
        },
        grounding={"replaced": False, "reason": QUESTION_ONLY_NEEDS_MODEL},
        fallback_reason=reason,
        elapsed_ms=(time.monotonic() - started) * 1000,
        extra=_question_only_extra(),
    )


def _blind_draft(question: str, deadline: float) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 1:
        raise AgentUnavailable("timeout")
    if budget_reached():
        raise AgentUnavailable("model budget reached")
    payload = {
        "model": azure_model(),
        "messages": [
            {"role": "system", "content": blind_draft_system()},
            {"role": "user", "content": question},
        ],
        "max_completion_tokens": AGENT_CONTRAST_TOKENS,
    }
    body = _call_azure(payload, timeout_s=min(12.0, remaining))
    choice = ((body.get("choices") or [{}])[0].get("message")) or {}
    text = str(choice.get("content") or "").strip()
    if not text:
        raise AgentUnavailable("http_error")
    return text


def run_question_only(
    *,
    question: str,
    depth: int = 2,
    engine: str = "draft",
    graph=None,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + AGENT_TIMEOUT_S
    graph = graph or get_graph()
    asked = (question or "").strip()
    if not azure_api_key() or not azure_endpoint():
        return _question_only_needs_model(started, "missing_key")
    if budget_reached():
        return _question_only_needs_model(started, "model budget reached")
    try:
        draft = _blind_draft(asked, deadline)
        cited = extract_cited_urls(draft)
        reports = validate_cited_urls(cited)
        ok_urls = [item["url"] for item in reports if item.get("ok")]
        defaults = {
            "question": asked,
            "draft": draft,
            "urls": ok_urls,
            "depth": clamp_depth(depth),
            "engine": (engine or "draft")[:80],
        }
        steps = [
            {
                "tool": "draft",
                "args": {"question": asked},
                "ms": 0,
                "ok": True,
                "summary": {"summary": draft},
            },
            {
                "tool": "validate_urls",
                "args": {"urls": cited},
                "ms": 0,
                "ok": True,
                "summary": {"cited_urls": reports, "summary": reports},
            },
        ]
        loop_steps, final = _model_loop(defaults, graph, deadline)
        steps = steps + loop_steps
        shipped, grounding, steps, note = _finalize(final, steps, defaults, graph)
        without = {
            "text": draft,
            "source": "blind_draft",
            "note": "Blind model draft (no MoolTrace).",
        }
        return _response(
            mode="model",
            model=azure_model(),
            steps=steps,
            shipped=shipped,
            without=without,
            grounding=grounding,
            fallback_reason=None,
            elapsed_ms=(time.monotonic() - started) * 1000,
            extra={**_question_only_extra(cited_urls=reports), "agent_note": note},
        )
    except AgentUnavailable as exc:
        return _question_only_needs_model(started, exc.reason)


def run_retraction_landed(
    *,
    doi: str = "",
    depth: int = 2,
    graph=None,
) -> dict[str, Any]:
    started = time.monotonic()
    graph = graph or get_graph()
    cleaned = clean_doi((doi or "").strip() or ISHIDA_2004_DOI)
    if not valid_doi(cleaned):
        cleaned = ISHIDA_2004_DOI
    impact = what_rests_on(cleaned, graph=graph, depth=depth)
    rec = recheck_affected(cleaned, graph=graph, depth=depth)
    affected: list[dict[str, Any]] = []
    for item in rec.get("rechecks") or []:
        answer_id = str(item.get("answer_id") or "")
        inputs = graph.answer_inputs(answer_id) if answer_id else {}
        urls = [
            url
            for url in (inputs.get("urls") or [])
            if url and not str(url).startswith("urn:")
        ]
        dois = [entry for entry in (inputs.get("dois") or []) if entry]
        text = "" if urls else " ".join(f"DOI {entry}" for entry in dois)
        used_engine = str(inputs.get("engine") or "draft")
        explained = explain_path(text, urls, used_engine, depth, graph=graph)
        rewritten = rewrite_answer(text, urls, used_engine, depth, graph=graph)
        hops = []
        reason = explained.get("reason") if isinstance(explained.get("reason"), dict) else {}
        for hop in (reason or {}).get("hops_evidence") or []:
            word = hop.get("reliance")
            if word:
                hops.append(word)
        path = " × ".join(hops) or explained.get("explanation") or item.get("summary")
        affected.append(
            {
                "answer_id": answer_id,
                "engine": used_engine,
                "urls": urls,
                "decision": item.get("decision"),
                "exit_code": item.get("exit_code"),
                "path": path,
                "rewrite": rewritten.get("text"),
                "rewritten": rewritten.get("rewritten"),
                "recheck": {
                    "decision": (rewritten.get("recheck") or {}).get("decision")
                    or item.get("decision"),
                    "exit_code": (rewritten.get("recheck") or {}).get("exit_code")
                    or item.get("exit_code"),
                },
            }
        )
    grouped: dict[tuple, dict[str, Any]] = {}
    for item in affected:
        key = (item["engine"], tuple(item["urls"]), item["decision"], item["rewrite"])
        if key in grouped:
            grouped[key]["count"] += 1
        else:
            grouped[key] = {**item, "count": 1}
    affected = list(grouped.values())
    read_only = False
    note = (
        "Rechecked the stored answers that rest on this work and drafted a fix for each. "
        "Stored answers are not deleted or replaced."
    )
    return {
        "action": "retraction_landed",
        "mode": "reverse",
        "model": "none",
        "label": "A retraction just landed",
        "fallback_reason": None,
        "doi": cleaned,
        "what_rests_on": {
            "affected": impact.get("counted_answer_count"),
            "summary": impact.get("summary"),
            "counted_answer_ids": impact.get("counted_answer_ids") or [],
        },
        "recheck_affected": {
            "affected": rec.get("affected"),
            "summary": rec.get("summary"),
        },
        "affected_answers": affected,
        "read_only": read_only,
        "note": note,
        "steps": [
            {
                "tool": "what_rests_on",
                "args": {"doi": cleaned},
                "ms": 0,
                "ok": True,
                "summary": {
                    "affected": impact.get("counted_answer_count"),
                    "summary": impact.get("summary"),
                },
            },
            {
                "tool": "recheck_affected",
                "args": {"doi": cleaned},
                "ms": 0,
                "ok": True,
                "summary": {
                    "affected": rec.get("affected"),
                    "summary": rec.get("summary"),
                },
            },
        ],
        "shipped": "",
        "without_mooltrace": {"text": "", "source": "none", "note": note},
        "grounding": {"replaced": False},
        "budget": spend_snapshot(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
    }


def run_fallback(
    *,
    question: str,
    draft: str,
    urls: list[str],
    depth: int,
    engine: str,
    reason: str,
    graph=None,
) -> dict[str, Any]:
    started = time.monotonic()
    graph = graph or get_graph()
    defaults = {
        "question": question,
        "draft": draft,
        "urls": urls,
        "depth": clamp_depth(depth),
        "engine": engine or "draft",
    }
    steps = _planner(defaults, graph)
    candidate = _shipped_from_steps(steps, draft)
    shipped, grounding, steps = _apply_grounding(candidate, steps, defaults, graph)
    without = _without_draft(draft)
    return _response(
        mode="fallback",
        model="fallback",
        steps=steps,
        shipped=shipped,
        without=without,
        grounding=grounding,
        fallback_reason=reason,
        elapsed_ms=(time.monotonic() - started) * 1000,
    )


def run_agent(
    *,
    question: str = "",
    draft: str = "",
    urls: list[str] | None = None,
    depth: int = 2,
    engine: str = "draft",
    action: str = "check",
    doi: str = "",
    graph=None,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + AGENT_TIMEOUT_S
    url_list = [item.strip() for item in (urls or []) if item and item.strip()]
    graph = graph or get_graph()
    if (action or "check").strip() == "retraction_landed":
        return run_retraction_landed(doi=doi, depth=depth, graph=graph)
    question_only = bool((question or "").strip()) and not (draft or "").strip() and not url_list
    if question_only:
        return run_question_only(
            question=question.strip(),
            depth=depth,
            engine=engine,
            graph=graph,
        )
    defaults = {
        "question": question or "Check this health-AI draft before shipping.",
        "draft": draft or "",
        "urls": url_list,
        "depth": clamp_depth(depth),
        "engine": (engine or "draft")[:80],
    }
    if not azure_api_key() or not azure_endpoint():
        return run_fallback(
            question=defaults["question"],
            draft=defaults["draft"],
            urls=url_list,
            depth=defaults["depth"],
            engine=defaults["engine"],
            reason="missing_key",
            graph=graph,
        )
    if budget_reached():
        return run_fallback(
            question=defaults["question"],
            draft=defaults["draft"],
            urls=url_list,
            depth=defaults["depth"],
            engine=defaults["engine"],
            reason="model budget reached",
            graph=graph,
        )
    try:
        steps, final = _model_loop(defaults, graph, deadline)
        shipped, grounding, steps, note = _finalize(final, steps, defaults, graph)
        without = _without_draft(defaults["draft"])
        return _response(
            mode="model",
            model=azure_model(),
            steps=steps,
            shipped=shipped,
            without=without,
            grounding=grounding,
            fallback_reason=None,
            elapsed_ms=(time.monotonic() - started) * 1000,
            extra={"agent_note": note},
        )
    except AgentUnavailable as exc:
        return run_fallback(
            question=defaults["question"],
            draft=defaults["draft"],
            urls=url_list,
            depth=defaults["depth"],
            engine=defaults["engine"],
            reason=exc.reason,
            graph=graph,
        )


def guard_agent(
    engine: str,
    text: str,
    urls: list[str] | None,
    client_ip: str | None = None,
) -> None:
    if len(text or "") > MAX_DRAFT_CHARS:
        raise PublicDemoRejected(413, "Draft is too large for the agent.")
    items = [item.strip() for item in (urls or []) if item and item.strip()]
    if len(items) > MAX_URLS:
        raise PublicDemoRejected(413, "URL list is too large for the agent.")
    if not public_demo_enabled():
        return
    now = time.monotonic()
    key = (client_ip or "").strip() or "unknown"
    with _lock:
        hits = _hits_by_ip.setdefault(key, [])
        while hits and now - hits[0] > AGENT_WINDOW_S:
            hits.pop(0)
        if len(hits) >= AGENT_PER_IP:
            raise PublicDemoRejected(
                429,
                "Agent rate limit: 6 runs per 10 minutes per IP. Try again later.",
            )
        state = _load_spend()
        if int(state["runs_today"]) >= AGENT_DAILY_CAP:
            raise PublicDemoRejected(
                429,
                "Agent daily cap reached (150 runs). Try a preset check instead.",
            )
        hits.append(now)
        state["runs_today"] = int(state["runs_today"]) + 1
        _save_spend(state)
