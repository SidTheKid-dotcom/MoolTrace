"""Compact 'Why the graph decided' panel from a real SPpaths run."""

from __future__ import annotations

from typing import Any

from mooltrace.public_demo import load_recorded_presets, _norm_urls


def fill_cypher(cypher: str, params: dict[str, Any] | None) -> str:
    """Substitute $name parameters so the shown query is the one that ran."""
    filled = cypher or ""
    for key, value in (params or {}).items():
        token = f"${key}"
        if isinstance(value, str):
            rendered = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        elif value is None:
            rendered = "null"
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        filled = filled.replace(token, rendered)
    return filled


def _notice_word(notice_type: str | None) -> str:
    raw = (notice_type or "").strip().lower()
    if raw == "expression_of_concern":
        return "Expression of Concern"
    if raw == "retraction":
        return "retraction"
    if raw in {"withdrawal", "removal"}:
        return raw
    return raw or "notice"


def without_graph_from_direct(direct: dict[str, Any]) -> dict[str, Any]:
    notices = list(direct.get("reasons") or [])
    dois = list(direct.get("dois") or [])
    notice_count = len(notices)
    decision = str(direct.get("decision") or "pass")
    if notice_count == 0:
        line = "Direct DOI check: 0 notices → would ship"
    elif decision == "block":
        line = f"Direct DOI check: {notice_count} notices → BLOCK"
    elif decision == "warn":
        line = f"Direct DOI check: {notice_count} notices → WARN"
    else:
        line = f"Direct DOI check: {notice_count} notices → {decision.upper()}"
    return {
        "decision": decision,
        "exit_code": int(direct.get("exit_code") or 0),
        "notice_count": notice_count,
        "dois": dois,
        "line": line,
    }


def with_graph_line(
    *,
    depth: int,
    decision: str,
    notice_type: str | None,
    notice_doi: str | None,
    notice_date: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    verdict = (decision or "pass").upper()
    if error_code == "not_in_graph":
        body = "nothing in the graph"
    elif notice_doi:
        body = f"{_notice_word(notice_type)} {notice_doi}"
        stamp = str(notice_date or "").strip()
        if stamp:
            body += f" ({stamp})"
    else:
        body = "0 notice paths"
    return {
        "depth": depth,
        "decision": decision,
        "notice_type": notice_type,
        "notice_doi": notice_doi,
        "notice_date": notice_date,
        "line": f"Graph depth {depth}: {body} → {verdict}",
    }


def _snippet(text: str | None, limit: int = 140) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def path_from_reason(reason: dict[str, Any] | None) -> dict[str, Any]:
    hops_out: list[dict[str, Any]] = []
    nodes = ["Answer"]
    if not reason:
        return {"nodes": nodes, "hops": hops_out, "readable": "Answer"}
    for step in reason.get("steps") or []:
        kind = str(step.get("kind") or "")
        if kind == "Source" or (step.get("url") and not step.get("doi")):
            nodes.append("Source")
        else:
            nodes.append("Work")
    for hop in reason.get("hops_evidence") or []:
        hops_out.append(
            {
                "relation": hop.get("reliance") or "",
                "weight": hop.get("weight"),
                "sentence": hop.get("sentence") or "",
                "sentence_snippet": _snippet(str(hop.get("sentence") or "")),
                "source_url": hop.get("source_url") or "",
                "fetched_at": hop.get("fetched_at") or "",
            }
        )
    if reason.get("notice_doi") or reason.get("notice_type"):
        nodes.append("Notice")
    readable = " → ".join(nodes)
    return {"nodes": nodes, "hops": hops_out, "readable": readable}


def recorded_spec_for(engine: str, text: str, urls: list[str] | None) -> dict[str, Any] | None:
    """Match a recorded preset by URL-only hero or clean DOI draft."""
    listed = _norm_urls(urls)
    blob = (text or "").strip()
    for spec in load_recorded_presets().get("presets") or []:
        sources = [str(item.get("url") or "") for item in spec.get("sources") or [] if item.get("url")]
        if listed and sources and listed == sources and not blob:
            return spec
        works = [str(item.get("doi") or "") for item in spec.get("works") or []]
        if blob and any(doi and doi in blob for doi in works) and not listed:
            return spec
    return None


def live_sppaths_from_spec(spec: dict[str, Any] | None, depth: int) -> dict[str, Any] | None:
    if not spec:
        return None
    row = (spec.get("by_depth") or {}).get(str(depth)) or {}
    strength = row.get("live_sppaths_strength")
    if strength is None:
        return None
    return {
        "strength": strength,
        "root_doi": row.get("live_sppaths_root_doi"),
        "hops": list(row.get("live_sppaths_hops") or []),
    }


def build_why_graph(
    *,
    cypher: str,
    params: dict[str, Any] | None,
    reason: dict[str, Any] | None,
    decision: str,
    depth: int,
    text: str,
    urls: list[str] | None,
    engine: str = "",
    error_code: str | None = None,
) -> dict[str, Any]:
    spec = recorded_spec_for(engine, text, urls)
    if spec and spec.get("without_graph"):
        without = dict(spec["without_graph"])
    else:
        from mooltrace.baseline import check_direct_doi

        without = without_graph_from_direct(check_direct_doi(text, urls))
    notice_type = (reason or {}).get("notice_type")
    notice_doi = (reason or {}).get("notice_doi")
    notice_date = (reason or {}).get("notice_date")
    with_graph = with_graph_line(
        depth=depth,
        decision=decision,
        notice_type=notice_type,
        notice_doi=notice_doi,
        notice_date=notice_date,
        error_code=error_code,
    )
    return {
        "title": "Why the graph decided",
        "cypher": fill_cypher(cypher, params),
        "path": path_from_reason(reason),
        "without_graph": without,
        "with_graph": with_graph,
        "contrast": f"{without['line']}  |  {with_graph['line']}",
        "live_sppaths": live_sppaths_from_spec(spec, depth),
    }


def attach_why_graph(
    payload: dict[str, Any],
    *,
    text: str,
    urls: list[str] | None,
    engine: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add why_graph to any check payload. Mutates and returns payload."""
    reasons = list(payload.get("reasons") or [])
    reason = next((item for item in reasons if item.get("hops_evidence")), None)
    if reason is None:
        reason = next((item for item in reasons if item.get("notice_doi")), None)
    if reason is None and reasons:
        reason = reasons[0]
    payload["why_graph"] = build_why_graph(
        cypher=str(payload.get("cypher") or (payload.get("algorithm") or {}).get("cypher") or ""),
        params=params or {"answer_id": payload.get("answer_id") or ""},
        reason=reason,
        decision=str(payload.get("decision") or "pass"),
        depth=int(payload.get("depth") or 2),
        text=text,
        urls=urls,
        engine=engine,
        error_code=payload.get("error_code"),
    )
    return payload
