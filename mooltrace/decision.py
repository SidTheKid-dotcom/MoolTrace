"""Pass, warn, or block for a draft health-AI answer.

The decision flags reliance on a publisher notice. It does not say the
draft is medically wrong. Verdicts come from algo.SPpaths path strength
(the product of RESTS_ON weights) on the strongest path to each flagged
Work. This module classifies those algorithm rows; it is not a second
Python verdict.
"""

from __future__ import annotations

from typing import Any

from mooltrace.ids import normalize_update_type
from mooltrace.reliance import PATH_RULE, STRONG_RELIANCE, WEIGHT_FLOOR

PASSING_NOTE = "cites a flagged study only in passing"

PRESHIP_EOC = (
    "Before your bot ships this answer, MoolTrace flags that a cited page "
    "or review reaches a study under an Expression of Concern."
)
PRESHIP_RETRACTION = (
    "Before your bot ships this answer, MoolTrace flags that a cited page "
    "or review reaches a retracted study."
)
PRESHIP_WITHDRAWAL = (
    "Before your bot ships this answer, MoolTrace flags that a cited page "
    "or review reaches a study the publisher has withdrawn."
)
UNVERIFIED_LABEL = "cites flagged study; reliance unverified"
NO_SOURCES_SUMMARY = (
    "No verifiable citation or source was provided. "
    "MoolTrace cannot inspect this answer's evidence chain."
)
NOT_IN_GRAPH_SUMMARY = (
    "Nothing in the graph connects this answer to a study. "
    "This is not proof it is safe; the source may not be modelled."
)

EXIT_PASS = 0
EXIT_BLOCK = 1
EXIT_WARN = 2
EXIT_INFRA = 3


def _kind(notice_type: str | None) -> str:
    raw = normalize_update_type(notice_type)
    if raw == "expression_of_concern":
        return "expression_of_concern"
    if "retract" in raw:
        return "retraction"
    if "withdraw" in raw or raw == "removal":
        return "withdrawal"
    return raw or "notice"


def _judged_flag(value: Any) -> bool | None:
    if value is True or value is False:
        return value
    if value in (1, "true", "True"):
        return True
    if value in (0, "false", "False"):
        return False
    return None


def _edge_status(edge: dict[str, Any]) -> str:
    judged = _judged_flag(edge.get("judged"))
    sentence = (edge.get("sentence") or "").strip()
    weight = edge.get("weight")
    reliance = (edge.get("reliance") or "").strip().lower()
    if reliance == "unverified" or (judged is True and not sentence):
        return "unverified"
    if judged is True:
        if weight is None or float(weight) < WEIGHT_FLOOR:
            return "discount"
        return "count"
    if weight is not None and sentence and float(weight) >= WEIGHT_FLOOR:
        return "count"
    if weight is not None and sentence and float(weight) < WEIGHT_FLOOR:
        return "discount"
    if weight is not None and not sentence:
        return "unverified"
    return "unknown"


def _worst_status(statuses: list[str]) -> str:
    """A path counts only when every hop counts. Weak or missing hops win."""
    order = {"unknown": 0, "unverified": 1, "discount": 2, "count": 3}
    worst = "count"
    for status in statuses:
        if order.get(status, 0) < order.get(worst, 3):
            worst = status
    return worst


def path_status(path: dict[str, Any]) -> str:
    """``count``, ``discount``, ``unverified``, or ``unknown``.

    Counted when every hop is evidenced (stored sentence) and each hop
    weight is at least WEIGHT_FLOOR. A multiplied path-strength floor is
    not applied: a confirmed retraction or Expression of Concern in a
    counted or unverified chain at least warns. An unverified hop is
    warn, never a silent pass. A hop below WEIGHT_FLOOR is discount:
    cites a flagged study only in passing. Decide() keeps the strongest
    path per flagged Work, so a weak short hop cannot hide a stronger
    counted path to the same work.
    """
    hops = path.get("hops_evidence") or []
    if hops:
        return _worst_status([_edge_status(edge) for edge in hops])
    weighted = "weight" in path or "judged" in path or "sentence" in path
    if not weighted:
        return "count"
    return _edge_status(path)


def strongest_per_flagged_work(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One strongest algo.SPpaths row per flagged Work (root DOI)."""
    best: dict[str, dict[str, Any]] = {}
    leftover: list[dict[str, Any]] = []
    for path in paths:
        doi = ((path.get("root") or {}).get("doi") or "").strip().lower()
        if not doi:
            leftover.append(path)
            continue
        current = best.get(doi)
        if current is None or path_score(path) > path_score(current):
            best[doi] = path
    return list(best.values()) + leftover


def _clears_hop_rule(hops: list[dict[str, Any]]) -> bool:
    """Single-hop mentions count. Multi-hop paths need a strong use."""
    if len(hops) <= 1:
        return True
    return any(
        (edge.get("reliance") or "").strip().lower() in STRONG_RELIANCE for edge in hops
    )


def path_score(path: dict[str, Any]) -> float:
    hops = path.get("hops_evidence") or []
    if hops:
        score = 1.0
        for edge in hops:
            try:
                score *= float(edge.get("weight") if edge.get("weight") is not None else 0.0)
            except (TypeError, ValueError):
                return 0.0
        return score
    try:
        return float(path["path_score"])
    except (KeyError, TypeError, ValueError):
        try:
            return float(path.get("weight") if path.get("weight") is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0


def _reason(path: dict[str, Any], kind: str) -> dict[str, Any]:
    notice = path.get("notice") or {}
    hops = path.get("hops_evidence") or []
    last = hops[-1] if hops else path
    reason = {
        "code": kind,
        "root_doi": (path.get("root") or {}).get("doi"),
        "root_title": (path.get("root") or {}).get("title"),
        "notice_doi": notice.get("doi"),
        "notice_type": notice.get("type"),
        "notice_label": notice.get("label"),
        "notice_date": notice.get("date"),
        "notice_source": notice.get("source"),
        "hops": path.get("hops"),
        "path_score": path_score(path),
        "steps": path.get("steps") or [],
        "hops_evidence": hops,
        "source_url": path.get("source_url"),
        "reliance": last.get("reliance") if isinstance(last, dict) else path.get("reliance"),
        "weight": last.get("weight") if isinstance(last, dict) else path.get("weight"),
        "sentence": ((last.get("sentence") if isinstance(last, dict) else path.get("sentence")) or "").strip()
        or None,
        "evidence_from": (last.get("evidence_from") if isinstance(last, dict) else path.get("evidence_from"))
        or None,
    }
    if kind == "unverified":
        reason["label"] = UNVERIFIED_LABEL
        reason["status"] = "unverified"
    else:
        reason["status"] = path_status(path)
    return reason


_STATUS_RANK = {"count": 0, "unverified": 1, "discount": 2, "unknown": 3}


def _reason_rank(reason: dict[str, Any]) -> tuple[int, int, int, float, int]:
    """Counted (verified reliance) before unverified before discounted."""
    status = reason.get("status")
    if not status:
        status = "unverified" if reason.get("code") == "unverified" else "count"
    status_rank = _STATUS_RANK.get(str(status), 3)
    kind_rank = {"retraction": 0, "withdrawal": 1, "expression_of_concern": 2}.get(
        reason.get("code") or "", 3
    )
    source = (reason.get("notice_source") or "").lower()
    source_rank = 0 if "retraction-watch" in source else 1
    hops = reason.get("hops")
    try:
        if reason.get("sp_cost") is not None:
            rank = float(reason.get("sp_cost"))
        else:
            rank = -float(reason.get("path_score") or 0.0)
    except (TypeError, ValueError):
        rank = 99.0
    return (
        status_rank,
        kind_rank,
        source_rank,
        rank,
        hops if isinstance(hops, int) else 99,
    )


def independent_sources(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct citers on counted paths. The citer is the node before the flagged study."""
    found: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path_status(path) != "count":
            continue
        steps = path.get("steps") or []
        if len(steps) < 2:
            continue
        citer = steps[-2]
        key = citer.get("doi") or citer.get("url")
        if not key:
            continue
        weight = path_score(path)
        current = found.get(key)
        if current and float(current.get("weight") or 0) >= weight:
            continue
        last = (path.get("hops_evidence") or [path])[-1]
        found[key] = {
            "id": key,
            "title": citer.get("title"),
            "reliance": last.get("reliance") if isinstance(last, dict) else path.get("reliance"),
            "weight": last.get("weight") if isinstance(last, dict) else path.get("weight"),
            "path_score": weight,
            "sentence": ((last.get("sentence") if isinstance(last, dict) else path.get("sentence")) or "").strip()
            or None,
            "evidence_from": (last.get("evidence_from") if isinstance(last, dict) else path.get("evidence_from"))
            or None,
            "root_doi": (path.get("root") or {}).get("doi"),
        }
    return list(found.values())


def coverage_line(expanded: int | None, cited: int | None, depth: int) -> str:
    """Always-visible coverage. Not a verdict. Missing counts keep depth_N."""
    if cited is None:
        return f"depth_{depth}"
    done = 0 if expanded is None else int(expanded)
    return f"expanded {done} of {int(cited)} cited works"


def decide(
    paths: list[dict[str, Any]],
    *,
    incomplete: bool,
    depth: int,
    has_sources: bool = True,
    sp_cost: dict[str, float] | None = None,
    works_cited: int | None = None,
    works_expanded: int | None = None,
    named_study: bool = False,
) -> dict[str, Any]:
    """Classify algo.SPpaths rows into pass, warn, or block.

    block — counted path reaches a retraction, withdrawal, or removal.
    warn  — counted path reaches an Expression of Concern, a reachable
            flagged path is unverified, the check stopped early, or the
            draft named no verifiable source.
    pass  — cited works were checked and no counted or unverified notice
            remains. Discounted paths (a hop below the 0.5 weight floor)
            pass with "cites a flagged study only in passing".
            This is not a claim that the draft is medically correct.

    Callers must feed algo.SPpaths rows. If the algorithm errors, do not
    call this function: return exit 3.
    """
    costs = sp_cost or {}
    counted: list[dict[str, Any]] = []
    discounted: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for path in paths:
        status = path_status(path)
        if status == "count":
            counted.append(path)
        elif status == "discount":
            discounted.append(path)
        elif status == "unverified":
            unverified.append(path)
        else:
            unknown.append(path)

    reasons = [
        _reason(path, _kind((path.get("notice") or {}).get("type"))) for path in counted
    ]
    for reason in reasons:
        doi = (reason.get("root_doi") or "").lower()
        if doi in costs:
            reason["sp_cost"] = costs[doi]
        reason["status"] = "count"
    reasons.sort(key=_reason_rank)
    kinds = {reason["code"] for reason in reasons}
    discounted_reasons = [
        _reason(path, _kind((path.get("notice") or {}).get("type"))) for path in discounted
    ]
    for item in discounted_reasons:
        item["status"] = "discount"

    if "retraction" in kinds:
        decision = "block"
        summary = PRESHIP_RETRACTION
    elif "withdrawal" in kinds:
        decision = "block"
        summary = PRESHIP_WITHDRAWAL
    elif "expression_of_concern" in kinds:
        decision = "warn"
        summary = PRESHIP_EOC
    elif kinds:
        decision = "warn"
        summary = (
            "Before your bot ships this answer, MoolTrace flags that a cited "
            "page or review reaches a study with a publisher notice."
        )
    elif unverified:
        decision = "warn"
        summary = UNVERIFIED_LABEL
        reasons = [_reason(path, "unverified") for path in unverified]
        reasons.sort(key=_reason_rank)
    elif unknown or incomplete:
        decision = "warn"
        summary = (
            "MoolTrace could not finish this pre-ship check, so the draft "
            f"is a warn rather than a pass. Depth requested: {depth}."
        )
        reasons.append(
            {
                "code": "incomplete",
                "root_doi": None,
                "notice_doi": None,
                "hops": None,
                "steps": [],
                "sentence": None,
            }
        )
    elif not has_sources:
        decision = "warn"
        summary = NO_SOURCES_SUMMARY
        reasons.append(
            {
                "code": "no_sources",
                "root_doi": None,
                "notice_doi": None,
                "hops": None,
                "steps": [],
                "sentence": None,
            }
        )
    elif works_cited == 0 and not named_study:
        decision = "warn"
        summary = NOT_IN_GRAPH_SUMMARY
        reasons.append(
            {
                "code": "not_in_graph",
                "root_doi": None,
                "notice_doi": None,
                "hops": None,
                "steps": [],
                "sentence": None,
            }
        )
    else:
        decision = "pass"
        if discounted:
            summary = (
                f"No counted reliance on a flagged study within {depth} hops "
                f"({PASSING_NOTE}). "
                f"{len(discounted)} citation path"
                f"{'s' if len(discounted) != 1 else ''} reached a notice with "
                "a hop below the 0.5 weight floor. Coverage is not shown "
                "beyond this depth."
            )
        else:
            summary = (
                f"No publisher notice was found within {depth} hops. "
                "Coverage is not shown beyond that depth."
            )

    if decision in {"warn", "block"} and kinds and unverified:
        extra = [_reason(path, "unverified") for path in unverified]
        reasons.extend(extra)
        reasons.sort(key=_reason_rank)

    exit_code = {"pass": EXIT_PASS, "warn": EXIT_WARN, "block": EXIT_BLOCK}[decision]
    sources = independent_sources(counted)
    payload = {
        "decision": decision,
        "exit_code": exit_code,
        "summary": summary,
        "reasons": reasons,
        "discounted": discounted_reasons,
        "unjudged_paths": len(unknown),
        "unverified_paths": len(unverified),
        "independent_sources": sources,
        "independent_source_count": len(sources),
        "weight_floor": WEIGHT_FLOOR,
        "path_rule": PATH_RULE,
        "decided_by": "algo.SPpaths",
        "coverage": coverage_line(works_expanded, works_cited, depth),
        "not_shown": "beyond requested depth",
    }
    if any(reason.get("code") == "no_sources" for reason in reasons):
        payload["error_code"] = "no_sources"
    if any(reason.get("code") == "not_in_graph" for reason in reasons):
        payload["error_code"] = "not_in_graph"
    return payload
