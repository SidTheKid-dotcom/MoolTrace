"""Sealed VITALITY Study I eval: same-trial recall vs a no-graph baseline.

Xu et al., BMJ 2025, is the answer key we did not write. A draft cites only
the review DOI. Direct-DOI looks that DOI up on Crossref. MoolTrace walks
depth 2 (headline) and depth 3 (separate recorded row). Recall is whether
a path reaches the SAME retracted trial VITALITY names. An OpenAlex 429
warn is not that recall. Labels are never rewritten after seeing verdicts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mooltrace import config
from mooltrace.baseline import (
    check_direct_doi,
    load_crossref_catalog,
    recorded_lookup,
)
from mooltrace.clients import CallStats, InfraError, MoolTraceError, close_client, crossref_work
from mooltrace.graph import Graph
from mooltrace.ids import clean_doi, valid_doi
from mooltrace.ssrf import UnsafeURL
from mooltrace.trace import check_answer

DEFAULT_FROZEN = config.ROOT / "examples" / "vitality.json"
DEFAULT_CROSSREF = config.ROOT / "examples" / "vitality_crossref.json"
DEFAULT_SNAPSHOT = config.ROOT / "examples" / "vitality_mooltrace.json"
COUNTED = frozenset({"retraction", "withdrawal", "expression_of_concern"})
FLAGGED = frozenset({"warn", "block"})


def load_frozen(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_FROZEN
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{target} is not a frozen VITALITY set")
    if not isinstance(payload.get("positives"), list) or not isinstance(
        payload.get("controls"), list
    ):
        raise ValueError(f"{target} needs positives and controls")
    if not str(payload.get("control_check") or "").strip():
        raise ValueError(f"{target} must state the control check")
    return payload


def cases(frozen: dict[str, Any]) -> list[dict[str, Any]]:
    """Sampled positives, then controls, then extra positives.

    Controls are the false-alarm set. Running them after the first 15
    sampled positives, and before the unpaired extra reviews, keeps the
    equal-n slice reachable if OpenAlex 429s later.
    """
    positives = list(frozen.get("positives") or [])
    controls = list(frozen.get("controls") or [])
    sampled = [row for row in positives if row.get("sampled")]
    extra = [row for row in positives if not row.get("sampled")]
    return sampled + controls + extra


def draft_for(row: dict[str, Any], frozen: dict[str, Any] | None = None) -> str:
    template = (frozen or {}).get("draft_template") or (
        "This health-information draft cites a single systematic review "
        "(DOI {doi}) and no other papers. It is not medical advice."
    )
    return template.format(doi=row["doi"])


def trial_dois(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in row.get("retracted_trials") or []:
        raw = item.get("doi") if isinstance(item, dict) else item
        doi = clean_doi(raw or "")
        if valid_doi(doi) and doi not in seen:
            seen.add(doi)
            out.append(doi)
    return out


def _norm(value: Any) -> str | None:
    doi = clean_doi(str(value or ""))
    return doi if valid_doi(doi) else None


def dois_in_payload(payload: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("doi", "root_doi", "notice_doi"):
                doi = _norm(node.get(key))
                if doi:
                    found.add(doi)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload.get("reasons") or [])
    return found


def same_trial(payload: dict[str, Any], vitality_dois: list[str]) -> dict[str, Any]:
    want = {_norm(doi) for doi in vitality_dois}
    want.discard(None)
    roots: list[str] = []
    notices: list[str] = []
    for reason in payload.get("reasons") or []:
        if not isinstance(reason, dict):
            continue
        root = _norm(reason.get("root_doi"))
        notice = _norm(reason.get("notice_doi"))
        if root and root in want:
            roots.append(root)
        if notice and notice in want:
            notices.append(notice)
        for step in reason.get("steps") or []:
            if isinstance(step, dict):
                doi = _norm(step.get("doi"))
                if doi and doi in want and doi not in roots:
                    roots.append(doi)
    return {
        "vitality_trial_dois": sorted(want),
        "matched_as_root": sorted(set(roots)),
        "matched_as_notice": sorted(set(notices)),
        "same_trial": bool(roots or notices),
    }


def _is_openalex_429(payload: dict[str, Any]) -> bool:
    blob = " ".join(str(item) for item in (payload.get("errors") or []))
    blob = blob.lower()
    if "api.openalex.org" in blob and "429" in blob:
        return True
    if "giving up on api.openalex.org" in blob:
        return True
    return False


def classify_run(payload: dict[str, Any], vitality_dois: list[str]) -> dict[str, Any]:
    hit = same_trial(payload, vitality_dois)
    decision = str(payload.get("decision") or "incomplete")
    reasons = [item for item in (payload.get("reasons") or []) if isinstance(item, dict)]
    codes = [str(item.get("code") or "") for item in reasons]
    counted = any(code in COUNTED for code in codes)
    unfinished = _is_openalex_429(payload) or (
        bool(payload.get("incomplete")) and not counted and not hit["same_trial"]
    )
    product_flagged = decision in FLAGGED
    miss = None
    if unfinished:
        miss = "openalex_429" if _is_openalex_429(payload) else "incomplete"
    elif not vitality_dois:
        miss = None if hit["same_trial"] else "no_vitality_trial_doi"
    elif not hit["same_trial"]:
        miss = "trial_not_reached"
    return {
        "decision": decision,
        "exit_code": int(payload.get("exit_code") or 2),
        "product_flagged": product_flagged,
        "counted_notice": counted,
        "finished_expansion": not unfinished,
        "unverified": "unverified" in codes,
        "same_trial": hit["same_trial"],
        "same_trial_detail": hit,
        "miss_reason": miss,
        "codes": codes,
    }


def _compact_reason(reason: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for step in reason.get("steps") or []:
        if not isinstance(step, dict):
            continue
        steps.append(
            {
                "kind": step.get("kind"),
                "doi": step.get("doi"),
                "title": step.get("title"),
                "year": step.get("year"),
            }
        )
    return {
        "code": reason.get("code"),
        "root_doi": reason.get("root_doi"),
        "notice_doi": reason.get("notice_doi"),
        "notice_type": reason.get("notice_type"),
        "hops": reason.get("hops"),
        "path_score": reason.get("path_score"),
        "steps": steps[:8],
    }


def compact_check(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    reasons = [_compact_reason(item) for item in (payload.get("reasons") or [])[:8]]
    scored = classify_run({**payload, "reasons": reasons}, trial_dois(row))
    return {
        "id": row["id"],
        "doi": row["doi"],
        "kind": row.get("kind"),
        "decision": payload.get("decision"),
        "exit_code": payload.get("exit_code"),
        "incomplete": bool(payload.get("incomplete")),
        "summary": payload.get("summary"),
        "errors": list(payload.get("errors") or [])[:8],
        "reasons": reasons,
        "api_calls": payload.get("api_calls"),
        "wall_ms": payload.get("elapsed_ms"),
        **scored,
    }


def _fresh_graph() -> Graph:
    return Graph(Path(tempfile.mkdtemp(prefix="mooltrace-vitality-")) / "mooltrace.db")


def _gentle_openalex() -> None:
    os.environ.setdefault("MOOLTRACE_MAILTO", config.MAILTO)
    os.environ["MOOLTRACE_OPENALEX_RPS"] = "3"
    from mooltrace import clients

    clients._HOST_RPS["api.openalex.org"] = 3.0
    with clients._limiters_lock:
        clients._limiters.clear()


def record_crossref(
    frozen: dict[str, Any],
    dest: Path,
) -> dict[str, Any]:
    stats = CallStats()
    works: dict[str, Any] = {}
    for row in cases(frozen):
        doi = row["doi"]
        try:
            message = crossref_work(doi, stats)
            works[doi] = {
                "status": 200 if message else 404,
                "message": message,
            }
        except InfraError as exc:
            works[doi] = {"status": 429, "error": str(exc), "message": None}
        except MoolTraceError as exc:
            works[doi] = {"status": 400, "error": str(exc), "message": None}
    catalog = {
        "kind": "direct_doi_crossref_catalog",
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "https://api.crossref.org/works/{doi}",
        "n": len(works),
        "api_calls": stats.api_calls,
        "cache_hits": stats.cache_hits,
        "works": works,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return catalog


def _normalize_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept the T19 flat depth-2 file or a by_depth map for 2 and 3."""
    payload.setdefault("kind", "vitality_mooltrace_snapshot")
    by_depth = payload.get("by_depth")
    if not isinstance(by_depth, dict):
        by_depth = {}
    if not by_depth:
        depth = int(payload.get("depth") or 2)
        by_depth = {
            str(depth): {
                "depth": depth,
                "cases": dict(payload.get("cases") or {}),
                "updated_at": payload.get("updated_at"),
                "cache": payload.get("cache"),
            }
        }
    for key, bucket in list(by_depth.items()):
        if not isinstance(bucket, dict):
            by_depth[key] = {"depth": int(key), "cases": {}}
            continue
        bucket.setdefault("depth", int(key))
        bucket.setdefault("cases", {})
    payload["by_depth"] = by_depth
    d2 = by_depth.get("2") or {}
    payload["depth"] = 2
    payload["cases"] = dict(d2.get("cases") or {})
    return payload


def _load_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _normalize_snapshot(
            {
                "kind": "vitality_mooltrace_snapshot",
                "depth": 2,
                "cases": {},
            }
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a snapshot")
    return _normalize_snapshot(payload)


def _depth_bucket(snapshot: dict[str, Any], depth: int) -> dict[str, Any]:
    snapshot = _normalize_snapshot(snapshot)
    key = str(int(depth))
    bucket = snapshot["by_depth"].setdefault(key, {"depth": int(depth), "cases": {}})
    bucket.setdefault("depth", int(depth))
    bucket.setdefault("cases", {})
    return bucket


def _save_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _normalize_snapshot(snapshot)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot["updated_at"] = now
    d2 = snapshot["by_depth"].get("2") or {}
    snapshot["depth"] = 2
    snapshot["cases"] = dict(d2.get("cases") or {})
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def _needs_live(entry: dict[str, Any] | None, *, retry_429: bool) -> bool:
    if not entry:
        return True
    if retry_429 and not entry.get("finished_expansion"):
        return True
    return False


def run_live_case(row: dict[str, Any], frozen: dict[str, Any], *, depth: int = 2) -> dict[str, Any]:
    graph = _fresh_graph()
    t0 = time.perf_counter()
    try:
        payload = check_answer(
            text=draft_for(row, frozen),
            urls=[],
            engine=str(row["id"])[:64],
            depth=depth,
            graph=graph,
        )
    except InfraError as exc:
        payload = {
            "decision": "incomplete",
            "exit_code": 3,
            "incomplete": True,
            "summary": str(exc),
            "errors": [str(exc)],
            "reasons": [],
            "api_calls": 0,
        }
    except (MoolTraceError, UnsafeURL) as exc:
        payload = {
            "decision": "warn",
            "exit_code": 2,
            "incomplete": True,
            "summary": str(exc),
            "errors": [str(exc)],
            "reasons": [],
            "api_calls": 0,
        }
    finally:
        graph.close()
    payload["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    compact = compact_check(payload, row)
    compact["wall_ms"] = payload["elapsed_ms"]
    compact["db"] = str(graph.path)
    return compact


def run_live(
    frozen: dict[str, Any],
    snapshot_path: Path,
    *,
    depth: int = 2,
    limit: int | None = None,
    retry_429: bool = True,
    pause_s: float = 8.0,
) -> dict[str, Any]:
    _gentle_openalex()
    snapshot = _load_snapshot(snapshot_path)
    bucket = _depth_bucket(snapshot, depth)
    cache = os.environ.get("MOOLTRACE_HTTP_CACHE")
    snapshot.setdefault("cache", cache)
    bucket["cache"] = cache
    rows = cases(frozen)
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    for row in rows:
        entry = bucket["cases"].get(row["id"])
        if not _needs_live(entry, retry_429=retry_429):
            print(f"  skip d{depth} {row['id']}", file=sys.stderr, flush=True)
            continue
        print(f"  live d{depth} {row['id']} {row['doi']}", file=sys.stderr, flush=True)
        result = run_live_case(row, frozen, depth=depth)
        result["depth"] = depth
        bucket["cases"][row["id"]] = result
        bucket["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        snapshot["by_depth"][str(depth)] = bucket
        if depth == 2:
            snapshot["cases"] = bucket["cases"]
            snapshot["depth"] = 2
        _save_snapshot(snapshot_path, snapshot)
        print(
            f"    decision={result['decision']} finished={result['finished_expansion']} "
            f"same_trial={result['same_trial']} miss={result.get('miss_reason')} "
            f"wall_ms={result['wall_ms']}",
            file=sys.stderr,
            flush=True,
        )
        if not result["finished_expansion"] and pause_s > 0:
            time.sleep(pause_s)
    return snapshot


def _baseline_row(row: dict[str, Any], frozen: dict[str, Any], lookup) -> dict[str, Any]:
    t0 = time.perf_counter()
    payload = check_direct_doi(draft_for(row, frozen), [], lookup=lookup)
    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    decision = str(payload.get("decision") or "incomplete")
    return {
        "id": row["id"],
        "kind": row.get("kind"),
        "doi": row["doi"],
        "decision": decision,
        "exit_code": payload.get("exit_code"),
        "flagged": decision in FLAGGED,
        "dois": payload.get("dois") or [],
        "resolved": payload.get("resolved") or [],
        "unresolved": payload.get("unresolved") or [],
        "reasons": payload.get("reasons") or [],
        "errors": payload.get("errors") or [],
        "summary": payload.get("summary"),
        "wall_ms": wall_ms,
        "graph": False,
    }


def _frac(num: int, den: int) -> str:
    return f"{num}/{den}"


def _score_depth(
    frozen: dict[str, Any],
    case_payloads: dict[str, Any],
    *,
    depth: int,
) -> dict[str, Any]:
    positives = list(frozen["positives"])
    controls = list(frozen["controls"])
    mt_rows = []
    for row in positives + controls:
        payload = case_payloads.get(row["id"]) or {}
        if not payload:
            mt_rows.append(
                {
                    "id": row["id"],
                    "kind": row.get("kind"),
                    "doi": row["doi"],
                    "depth": depth,
                    "pending": True,
                    "finished_expansion": False,
                    "same_trial": False,
                    "product_flagged": False,
                    "counted_notice": False,
                    "miss_reason": "pending",
                }
            )
            continue
        scored = classify_run(payload, trial_dois(row))
        mt_rows.append(
            {
                "id": row["id"],
                "kind": row.get("kind"),
                "doi": row["doi"],
                "depth": depth,
                "pending": False,
                **scored,
                "summary": payload.get("summary"),
                "errors": payload.get("errors") or [],
                "reasons": payload.get("reasons") or [],
                "wall_ms": payload.get("wall_ms"),
                "api_calls": payload.get("api_calls"),
            }
        )

    def _kind(kind: str) -> list[dict[str, Any]]:
        return [row for row in mt_rows if row.get("kind") == kind]

    pos_mt = _kind("positive")
    ctrl_mt = _kind("control")
    pos_finished = [row for row in pos_mt if row.get("finished_expansion") and not row.get("pending")]
    ctrl_finished = [row for row in ctrl_mt if row.get("finished_expansion") and not row.get("pending")]
    same = [row for row in pos_finished if row.get("same_trial")]
    counted = [row for row in pos_finished if row.get("counted_notice")]
    false_alarms = [
        row
        for row in ctrl_finished
        if row.get("counted_notice") or (row.get("product_flagged") and row.get("decision") != "pass")
    ]
    pos_429 = sum(1 for row in pos_mt if row.get("miss_reason") == "openalex_429")
    ctrl_429 = sum(1 for row in ctrl_mt if row.get("miss_reason") == "openalex_429")
    by_frozen = {str(row["id"]): row for row in positives + controls}
    misses = []
    for row in pos_mt:
        if not row.get("miss_reason") or row.get("pending"):
            continue
        frozen_row = by_frozen.get(str(row["id"])) or {}
        want = trial_dois(frozen_row)
        found_roots = []
        found_notices = []
        for reason in row.get("reasons") or []:
            if not isinstance(reason, dict):
                continue
            if reason.get("root_doi"):
                found_roots.append(reason["root_doi"])
            if reason.get("notice_doi"):
                found_notices.append(reason["notice_doi"])
        note = row.get("miss_reason")
        summary = str(row.get("summary") or "")
        if row.get("miss_reason") == "no_vitality_trial_doi":
            note = (
                "OSF All-sheet stored no retracted-trial DOI for this review, "
                "so same-trial recall is undefined."
            )
            if row.get("counted_notice"):
                note += f" MoolTrace still reached a retraction ({found_roots[:3]})."
        elif row.get("miss_reason") == "trial_not_reached" and row.get("counted_notice"):
            note = (
                "MoolTrace reached a retraction, but not the VITALITY-named "
                f"trial DOI {want}. Found roots {found_roots[:4]}."
            )
        elif "below the 0.5 weight floor" in summary:
            note = (
                "A notice path existed but a hop was below the 0.5 counted "
                f"floor, so algo.SPpaths did not decide a flag. VITALITY named {want}."
            )
        elif row.get("decision") == "pass":
            note = (
                f"No notice path within {depth} hops. VITALITY named "
                f"{want}."
            )
        misses.append(
            {
                "id": row["id"],
                "doi": row["doi"],
                "depth": depth,
                "reason": row.get("miss_reason"),
                "note": note,
                "decision": row.get("decision"),
                "vitality_trial_dois": want,
                "found_roots": found_roots[:6],
                "found_notices": found_notices[:6],
                "errors": (row.get("errors") or [])[:3],
            }
        )
    sampled_ids = {str(row["id"]) for row in positives if row.get("sampled")}
    sampled_mt = [row for row in pos_mt if row["id"] in sampled_ids]
    sampled_finished = [row for row in sampled_mt if row.get("finished_expansion")]
    sampled_same = sum(1 for row in sampled_finished if row.get("same_trial"))
    walls = [float(row["wall_ms"]) for row in mt_rows if row.get("wall_ms") is not None]
    return {
        "depth": depth,
        "metrics": {
            "positives_n": len(pos_mt),
            "controls_n": len(ctrl_mt),
            "finished_positives": len(pos_finished),
            "finished_controls": len(ctrl_finished),
            "same_trial_recall_finished": _frac(len(same), len(pos_finished))
            if pos_finished
            else "unevaluable (0 finished)",
            "counted_notice_finished": _frac(len(counted), len(pos_finished))
            if pos_finished
            else "unevaluable (0 finished)",
            "false_alarms_finished": _frac(len(false_alarms), len(ctrl_finished))
            if ctrl_finished
            else "unevaluable (0 finished)",
            "openalex_429_positives": pos_429,
            "openalex_429_controls": ctrl_429,
            "pending": sum(1 for row in mt_rows if row.get("pending")),
            "pending_ids": [row["id"] for row in mt_rows if row.get("pending")],
            "sum_case_wall_s": round(sum(walls) / 1000, 1) if walls else None,
            "mean_case_wall_ms": round(sum(walls) / len(walls), 1) if walls else None,
            "sampled_15_same_trial_finished": _frac(sampled_same, len(sampled_finished))
            if sampled_finished
            else "unevaluable",
            "note": (
                f"Recall is same VITALITY trial on a finished depth-{depth} path. "
                "Product warn/block from OpenAlex 429 is not recall. "
                "A counted retraction on a different paper than VITALITY named "
                "is a same-trial miss, not a relabel."
            ),
        },
        "results": mt_rows,
        "misses": misses,
        "false_alarms": [
            {"id": row["id"], "doi": row["doi"], "decision": row.get("decision"), "depth": depth}
            for row in false_alarms
        ],
        "example_paths": [
            row
            for row in mt_rows
            if row["id"] in {"pos-ref-35", "pos-ref-87", "pos-ref-56"}
        ],
    }


def run_vitality_eval(
    *,
    frozen_path: Path | None = None,
    catalog_path: Path | None = None,
    snapshot_path: Path | None = None,
    lookup=None,
) -> dict[str, Any]:
    frozen = load_frozen(frozen_path)
    catalog = None
    finder = lookup
    if finder is None:
        catalog = load_crossref_catalog(catalog_path or DEFAULT_CROSSREF)
        finder = recorded_lookup(catalog)
    snapshot = _load_snapshot(snapshot_path or DEFAULT_SNAPSHOT)
    positives = list(frozen["positives"])
    controls = list(frozen["controls"])
    base_rows = [_baseline_row(row, frozen, finder) for row in positives + controls]
    pos_base = [row for row in base_rows if row["kind"] == "positive"]
    ctrl_base = [row for row in base_rows if row["kind"] == "control"]
    d2_cases = ((snapshot.get("by_depth") or {}).get("2") or {}).get("cases") or {}
    d3_cases = ((snapshot.get("by_depth") or {}).get("3") or {}).get("cases") or {}
    d2 = _score_depth(frozen, d2_cases, depth=2)
    d3 = _score_depth(frozen, d3_cases, depth=3)
    return {
        "product": "MoolTrace",
        "kind": "vitality_eval",
        "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "paper": frozen.get("paper"),
        "pmc": frozen.get("pmc"),
        "doi": frozen.get("doi"),
        "osf": frozen.get("osf"),
        "never_relabelled": True,
        "control_check": frozen.get("control_check"),
        "controls_frozen_at": frozen.get("controls_frozen_at"),
        "sampling": frozen.get("sampling"),
        "n_positives": len(positives),
        "n_controls": len(controls),
        "n_sampled_positives": sum(1 for row in positives if row.get("sampled")),
        "frozen": str(frozen_path or DEFAULT_FROZEN),
        "crossref_catalog": str(catalog_path or DEFAULT_CROSSREF),
        "crossref_fetched_at": (catalog or {}).get("fetched_at") if catalog else None,
        "mooltrace_snapshot": str(snapshot_path or DEFAULT_SNAPSHOT),
        "depth": 2,
        "live": {
            "snapshot_updated_at": snapshot.get("updated_at"),
            "depth_2_updated_at": ((snapshot.get("by_depth") or {}).get("2") or {}).get(
                "updated_at"
            ),
            "depth_3_updated_at": ((snapshot.get("by_depth") or {}).get("3") or {}).get(
                "updated_at"
            ),
            "http_cache": (
                ((snapshot.get("by_depth") or {}).get("3") or {}).get("cache")
                or ((snapshot.get("by_depth") or {}).get("2") or {}).get("cache")
                or snapshot.get("cache")
            ),
            "openalex_rps": 3,
            "throwaway_graphs": True,
            "configured_db": str(config.DB_PATH),
        },
        "baseline": {
            "checker": "direct_doi_crossref",
            "graph": False,
            "metrics": {
                "positives_n": len(pos_base),
                "controls_n": len(ctrl_base),
                "positives_flagged": _frac(sum(1 for row in pos_base if row["flagged"]), len(pos_base)),
                "controls_flagged": _frac(sum(1 for row in ctrl_base if row["flagged"]), len(ctrl_base)),
                "unresolved": [row["id"] for row in base_rows if row.get("unresolved")],
            },
            "results": base_rows,
        },
        "mooltrace": d2,
        "mooltrace_depth_3": d3,
        "misses": d2["misses"],
        "misses_depth_3": d3["misses"],
        "false_alarms": d2["false_alarms"],
        "false_alarms_depth_3": d3["false_alarms"],
        "example_paths": d2["example_paths"],
    }


def _numbers_table(mt: dict[str, Any], base: dict[str, Any], *, depth_label: str) -> list[str]:
    return [
        f"| Slice ({depth_label}) | Result |",
        "| --- | --- |",
        f"| Direct-DOI positives flagged | {base['positives_flagged']} |",
        f"| Direct-DOI controls flagged | {base['controls_flagged']} |",
        f"| MoolTrace same-trial recall (finished) | {mt['same_trial_recall_finished']} |",
        f"| MoolTrace counted notice (finished) | {mt['counted_notice_finished']} |",
        f"| False alarms on finished controls | {mt['false_alarms_finished']} |",
        f"| OpenAlex 429 positives | {mt['openalex_429_positives']} |",
        f"| OpenAlex 429 controls | {mt['openalex_429_controls']} |",
        f"| Pending live checks | {mt['pending']} |",
        f"| Sampled-15 same-trial (finished) | {mt.get('sampled_15_same_trial_finished')} |",
        f"| Sum of case walls | {mt.get('sum_case_wall_s')} s |",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    mt = report["mooltrace"]["metrics"]
    base = report["baseline"]["metrics"]
    d3 = (report.get("mooltrace_depth_3") or {}).get("metrics") or {}
    lines = [
        f"# VITALITY bench ({report['ran_at'][:10]})",
        "",
        report.get("paper") or "Xu et al., VITALITY Study I, BMJ 2025.",
        "",
        "Labels were frozen before this run and were **not** rewritten after seeing verdicts.",
        "",
        f"- Frozen positives: **{report['n_positives']}** (sampled 15 + extra; cap 40)",
        f"- Frozen controls: **{report['n_controls']}**",
        f"- Headline depth: 2 (depth 3 is a separate row below; it does not replace depth 2)",
        f"- Controls frozen at: {report.get('controls_frozen_at') or 'see control_check'}",
        f"- Ran at: {report['ran_at']}",
        "- Reproduce offline: `.venv/bin/python -m mooltrace vitality --out results/vitality_2026-10-17.json`",
        "",
        "## Control check",
        "",
        str(report.get("control_check") or ""),
        "",
        "## Numbers (depth 2 headline)",
        "",
    ]
    lines.extend(_numbers_table(mt, base, depth_label="depth 2"))
    lines.extend(
        [
            "",
            mt["note"],
            "",
            (
                f"n_controls is {report['n_controls']}. "
                "Controls were frozen before MoolTrace ran on the new rows. "
                "Do not invent matches after seeing verdicts."
            ),
            "",
            "## Depth 3 (separate row; does not replace depth 2)",
            "",
        ]
    )
    if d3:
        lines.extend(_numbers_table(d3, base, depth_label="depth 3"))
        lines.extend(["", d3.get("note") or "", ""])
        lines.append(
            f"Depth 3 false alarms (finished): **{d3.get('false_alarms_finished')}**. "
            f"Depth 2 false alarms (finished): **{mt.get('false_alarms_finished')}**."
        )
        pending_ids = d3.get("pending_ids") or []
        if d3.get("pending"):
            lines.extend(
                [
                    "",
                    (
                        f"Pending depth-3 live checks: **{d3['pending']}** "
                        f"({', '.join(str(item) for item in pending_ids)}). "
                        "Not started this session; marked pending, not relabelled."
                    ),
                ]
            )
    alarms = report.get("false_alarms") or []
    lines.extend(["", "## False alarms (depth 2)", ""])
    if alarms:
        lines.append("| id | DOI | decision |")
        lines.append("| --- | --- | --- |")
        for row in alarms:
            lines.append(f"| {row['id']} | `{row['doi']}` | {row.get('decision') or ''} |")
    else:
        lines.append("None recorded.")
    d3_alarms = report.get("false_alarms_depth_3") or []
    lines.extend(["", "## False alarms (depth 3)", ""])
    if d3_alarms:
        lines.append("| id | DOI | decision |")
        lines.append("| --- | --- | --- |")
        for row in d3_alarms:
            lines.append(f"| {row['id']} | `{row['doi']}` | {row.get('decision') or ''} |")
    elif d3.get("pending") and not d3.get("finished_controls"):
        lines.append("Unevaluable until depth-3 controls finish.")
    else:
        lines.append("None recorded among finished depth-3 controls.")
    lines.extend(["", "## Misses (depth 2)", ""])
    misses = report.get("misses") or []
    if not misses:
        lines.append("None recorded.")
    else:
        lines.append("| id | DOI | reason | decision | note |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in misses:
            note = (row.get("note") or row.get("reason") or "").replace("|", "/")
            lines.append(
                f"| {row['id']} | `{row['doi']}` | {row.get('reason')} | {row.get('decision') or ''} | {note} |"
            )
    d3_misses = report.get("misses_depth_3") or []
    lines.extend(["", "## Misses (depth 3)", ""])
    if not d3_misses:
        lines.append("None recorded or depth 3 still pending.")
    else:
        lines.append("| id | DOI | reason | decision | note |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in d3_misses:
            note = (row.get("note") or row.get("reason") or "").replace("|", "/")
            lines.append(
                f"| {row['id']} | `{row['doi']}` | {row.get('reason')} | {row.get('decision') or ''} | {note} |"
            )
    examples = report.get("example_paths") or []
    if examples:
        lines.extend(["", "## Example paths", ""])
        for row in examples:
            lead = (row.get("reasons") or [{}])[0] if row.get("reasons") else {}
            lines.append(
                f"- `{row['id']}` {row.get('decision')}: same_trial={row.get('same_trial')} "
                f"root `{lead.get('root_doi')}` notice `{lead.get('notice_doi')}` "
                f"score {lead.get('path_score')}."
            )
    lines.extend(["", "This is not a medical accuracy score.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mooltrace vitality",
        description=(
            "Sealed VITALITY Study I eval. A no-graph direct-DOI checker vs "
            "MoolTrace depth 2 (headline) and depth 3 (separate row) on drafts "
            "that cite only a review DOI. Default is offline from recorded "
            "Crossref and recorded MoolTrace fixtures. --live walks one "
            "throwaway graph at a time, OpenAlex RPS<=3, shared HTTP cache, "
            "and resumes on 429."
        ),
    )
    parser.add_argument("--frozen", type=Path, default=DEFAULT_FROZEN)
    parser.add_argument("--crossref", type=Path, default=DEFAULT_CROSSREF)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--md", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run MoolTrace on throwaway graphs (writes the snapshot at --depth).",
    )
    parser.add_argument(
        "--record-crossref",
        action="store_true",
        help="Fetch Crossref for every frozen DOI into the catalog.",
    )
    parser.add_argument("--depth", type=int, default=2, help="Live hop budget. 2 is headline; 3 is a separate row.")
    args = parser.parse_args(argv)
    os.environ.setdefault("MOOLTRACE_MAILTO", config.MAILTO)
    frozen = load_frozen(args.frozen)
    if args.record_crossref:
        print("recording Crossref catalog", file=sys.stderr, flush=True)
        record_crossref(frozen, args.crossref)
        close_client()
    if args.live:
        cache = os.environ.get("MOOLTRACE_HTTP_CACHE")
        if not cache:
            cache = str(Path(tempfile.mkdtemp(prefix="mt-vitality-cache-")))
            os.environ["MOOLTRACE_HTTP_CACHE"] = cache
        print(
            f"live depth={args.depth} cache={cache} "
            f"configured_db_untouched={config.DB_PATH}",
            file=sys.stderr,
            flush=True,
        )
        run_live(
            frozen,
            args.snapshot,
            depth=args.depth,
            limit=args.limit,
            retry_429=True,
        )
        close_client()
    report = run_vitality_eval(
        frozen_path=args.frozen,
        catalog_path=args.crossref,
        snapshot_path=args.snapshot,
    )
    text = json.dumps(report, indent=2) + "\n"
    sys.stdout.write(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        md_path = args.md or args.out.with_suffix(".md")
        md_path.write_text(render_markdown(report), encoding="utf-8")
    elif args.md:
        args.md.write_text(render_markdown(report), encoding="utf-8")
    mt = report["mooltrace"]["metrics"]
    d3 = report["mooltrace_depth_3"]["metrics"]
    base = report["baseline"]["metrics"]
    print(
        f"VITALITY baseline pos={base['positives_flagged']} "
        f"ctrl={base['controls_flagged']}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"VITALITY mooltrace d2 same_trial={mt['same_trial_recall_finished']} "
        f"false_alarms={mt['false_alarms_finished']} "
        f"oa429={mt['openalex_429_positives']}+{mt['openalex_429_controls']} "
        f"pending={mt['pending']}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"VITALITY mooltrace d3 same_trial={d3['same_trial_recall_finished']} "
        f"false_alarms={d3['false_alarms_finished']} "
        f"oa429={d3['openalex_429_positives']}+{d3['openalex_429_controls']} "
        f"pending={d3['pending']}",
        file=sys.stderr,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
