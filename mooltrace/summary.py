"""Plain-English --summary output for check-answer."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    if host and path:
        return f"{host}{path}"
    return host or url


def _step_name(step: dict[str, Any]) -> str:
    title = (step.get("title") or "").strip()
    year = step.get("year")
    doi = (step.get("doi") or "").strip()
    url = (step.get("url") or "").strip()
    if url and not doi:
        return _host(url)
    label = title or doi or url or "?"
    if year and title:
        short = title.split(":")[0].strip()
        if len(short) > 48:
            short = short[:45] + "…"
        return f"{short} ({year}) ({doi})" if doi else f"{short} ({year})"
    if doi:
        return f"{label} ({doi})" if label != doi else doi
    return label


def _path_line(reason: dict[str, Any]) -> str:
    steps = reason.get("steps") or []
    names = [_step_name(step) for step in steps if step]
    return " → ".join(names) if names else (reason.get("root_doi") or "no path")


def _headline(payload: dict[str, Any]) -> str:
    decision = payload.get("decision") or "warn"
    code = payload.get("exit_code")
    reasons = payload.get("reasons") or []
    kind = next((item.get("code") for item in reasons if item.get("code")), "")
    if decision == "block":
        return f"BLOCK (exit {code}) — your answer rests on a retracted study"
    if decision == "pass":
        return f"PASS (exit {code}) — no counted path to a flagged study within this depth"
    if kind == "expression_of_concern":
        return (
            f"WARN (exit {code}) — your answer rests on a study flagged with "
            "an Expression of Concern"
        )
    if kind == "unverified":
        return f"WARN (exit {code}) — a cited flagged study has unverified reliance"
    if kind == "no_sources":
        return f"WARN (exit {code}) — no verifiable citation or source was provided"
    return f"WARN (exit {code}) — {payload.get('summary') or 'review this draft before shipping'}"


def _flag_line(payload: dict[str, Any]) -> str:
    reason = next((item for item in payload.get("reasons") or [] if item.get("notice_doi")), None)
    if not reason:
        ago = payload.get("notices_checked_ago")
        return f"Notices checked {ago}." if ago else ""
    code = reason.get("code") or ""
    if code == "expression_of_concern":
        label = "Expression of Concern"
    elif code == "retraction":
        label = "retraction"
    elif code == "withdrawal":
        label = "withdrawal"
    else:
        label = reason.get("notice_label") or code or "publisher notice"
    doi = reason.get("notice_doi")
    date = reason.get("notice_date") or ""
    ago = payload.get("notices_checked_ago")
    bits = [f"Flag: {label} {doi}".strip()]
    if date:
        bits[0] += f" ({date})"
    if ago:
        bits.append(f"notices checked {ago}")
    return " · ".join(bits)


def _advice(payload: dict[str, Any]) -> str:
    decision = payload.get("decision")
    if decision == "pass":
        return "What to do: pass is not a medical-accuracy check. Coverage stops at this depth."
    if decision == "block":
        return (
            "What to do: do not ship. Disclose or replace this source. "
            "Run `mooltrace rewrite` to fix only the affected sentence."
        )
    return (
        "What to do: disclose or replace this source. "
        "Run `mooltrace rewrite` to fix only the affected sentence."
    )


def format_summary(payload: dict[str, Any]) -> str:
    lines = [_headline(payload)]
    reason = next((item for item in payload.get("reasons") or [] if item.get("steps")), None)
    if reason is None and payload.get("reasons"):
        reason = payload["reasons"][0]
    if reason:
        lines.append(_path_line(reason))
    flag = _flag_line(payload)
    if flag:
        lines.append(flag)
    lines.append(_advice(payload))
    algo = payload.get("algorithm") or {}
    decided = algo.get("explanation") or ""
    if decided:
        lines.append(decided)
    elif algo.get("name"):
        strength = algo.get("strength")
        strength_txt = f"{strength:.2f}" if isinstance(strength, float) else "n/a"
        lines.append(f"Decided by: {algo.get('name')}, path strength {strength_txt}")
    return "\n".join(lines) + "\n"
