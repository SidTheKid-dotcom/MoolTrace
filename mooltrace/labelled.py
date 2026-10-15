"""Labelled health-answer set on isolated throwaway graphs.

This is not the seeded gate. Each JSONL row has an expected pass / warn /
block. Precision and recall treat warn and block as the positive class
(flagged). Exact decision match is reported separately. Live scores are
not hardcoded. The configured MOOLTRACE_DB file is never deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mooltrace import config
from mooltrace.clients import InfraError, MoolTraceError, close_client
from mooltrace.graph import Graph
from mooltrace.ssrf import UnsafeURL
from mooltrace.trace import check_answer

FAMILIES = ("eoc", "retraction", "hedged", "clean", "no_sources", "depth")
DECISIONS = ("pass", "warn", "block")
DEFAULT_FILE = config.ROOT / "examples" / "labelled.jsonl"
POSITIVE = frozenset({"warn", "block"})


def load_labelled(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DEFAULT_FILE
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(target.read_text().splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        item = json.loads(raw)
        if not isinstance(item, dict):
            raise ValueError(f"{target}:{index} is not a JSON object")
        ident = str(item.get("id") or "").strip()
        family = str(item.get("family") or "").strip()
        expected = str(item.get("expected") or "").strip()
        if not ident:
            raise ValueError(f"{target}:{index} missing id")
        if family not in FAMILIES:
            raise ValueError(f"{target}:{index} unknown family {family}")
        if expected not in DECISIONS:
            raise ValueError(f"{target}:{index} unknown expected {expected}")
        item["_line"] = index
        item["_file"] = str(target)
        rows.append(item)
    ids = [str(row["id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{target} has duplicate ids")
    return rows


def _fresh_graph() -> Graph:
    return Graph(Path(tempfile.mkdtemp(prefix="mooltrace-labelled-")) / "mooltrace.db")


def _urls(row: dict[str, Any]) -> list[str]:
    values = row.get("urls") or []
    if isinstance(values, str):
        return [values]
    return [str(item).strip() for item in values if str(item).strip()]


def run_case(row: dict[str, Any], *, graph: Graph | None = None) -> dict[str, Any]:
    own = graph is None
    if own:
        graph = _fresh_graph()
    assert graph is not None
    t0 = time.perf_counter()
    try:
        payload = check_answer(
            text=str(row.get("text") or ""),
            urls=_urls(row),
            engine=str(row.get("engine") or row["id"])[:64],
            depth=int(row["depth"]) if row.get("depth") is not None else config.DEFAULT_DEPTH,
            graph=graph,
        )
    except InfraError as exc:
        payload = {
            "decision": "incomplete",
            "exit_code": 3,
            "summary": str(exc),
            "elapsed_ms": 0,
            "api_calls": 0,
            "errors": [str(exc)],
            "reasons": [],
        }
    except (MoolTraceError, UnsafeURL) as exc:
        payload = {
            "decision": "incomplete",
            "exit_code": 2,
            "summary": str(exc),
            "elapsed_ms": 0,
            "api_calls": 0,
            "errors": [str(exc)],
            "reasons": [],
        }
    finally:
        if own:
            graph.close()
    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    decision = str(payload.get("decision") or "incomplete")
    exit_code = int(payload.get("exit_code") or 2)
    expected = str(row["expected"])
    infra = exit_code == 3
    scored = (not infra) and decision in DECISIONS
    return {
        "id": row["id"],
        "family": row["family"],
        "expected": expected,
        "decision": decision,
        "exit_code": exit_code,
        "match": scored and decision == expected,
        "expected_flagged": expected in POSITIVE,
        "predicted_flagged": decision in POSITIVE,
        "scored": scored,
        "infra": infra,
        "summary": payload.get("summary"),
        "api_calls": payload.get("api_calls"),
        "query_ms": payload.get("elapsed_ms"),
        "wall_ms": wall_ms,
        "errors": (payload.get("errors") or [])[:6],
        "reasons": [
            {
                "code": reason.get("code"),
                "root_doi": reason.get("root_doi"),
                "notice_doi": reason.get("notice_doi"),
                "notice_type": reason.get("notice_type"),
                "path_score": reason.get("path_score"),
            }
            for reason in (payload.get("reasons") or [])[:6]
        ],
    }


def _ratio(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return round(num / den, 4)


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("scored")]
    tp = sum(1 for row in scored if row["expected_flagged"] and row["predicted_flagged"])
    fp = sum(1 for row in scored if (not row["expected_flagged"]) and row["predicted_flagged"])
    fn = sum(1 for row in scored if row["expected_flagged"] and (not row["predicted_flagged"]))
    tn = sum(1 for row in scored if (not row["expected_flagged"]) and (not row["predicted_flagged"]))
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    walls = [float(row["wall_ms"]) for row in rows if row.get("wall_ms") is not None]
    queries = [float(row["query_ms"] or 0) for row in rows if row.get("query_ms") is not None]
    by_family: dict[str, dict[str, Any]] = {}
    for family in FAMILIES:
        group = [row for row in scored if row.get("family") == family]
        if not group:
            continue
        g_tp = sum(1 for row in group if row["expected_flagged"] and row["predicted_flagged"])
        g_fp = sum(1 for row in group if (not row["expected_flagged"]) and row["predicted_flagged"])
        g_fn = sum(1 for row in group if row["expected_flagged"] and (not row["predicted_flagged"]))
        by_family[family] = {
            "n": len(group),
            "exact_match": sum(1 for row in group if row.get("match")),
            "precision": _ratio(g_tp, g_tp + g_fp),
            "recall": _ratio(g_tp, g_tp + g_fn),
        }
    return {
        "n": len(rows),
        "scored": len(scored),
        "infra": sum(1 for row in rows if row.get("infra")),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_match": sum(1 for row in scored if row.get("match")),
        "exact_match_rate": _ratio(sum(1 for row in scored if row.get("match")), len(scored)),
        "timing": {
            "mean_wall_ms": round(sum(walls) / len(walls), 1) if walls else None,
            "mean_query_ms": round(sum(queries) / len(queries), 1) if queries else None,
            "max_wall_ms": round(max(walls), 1) if walls else None,
        },
        "by_family": by_family,
        "rule": (
            "Binary positive class is warn or block. Exact match is the "
            "three-way decision. Infra rows are excluded from scored metrics."
        ),
    }


def run_labelled(
    path: Path | None = None,
    *,
    limit: int | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    cases = load_labelled(path)
    if family:
        cases = [row for row in cases if row["family"] == family]
    if limit is not None:
        cases = cases[: max(0, int(limit))]
    started = time.perf_counter()
    results = []
    for row in cases:
        print(f"  {row['id']} expected={row['expected']}", file=sys.stderr, flush=True)
        result = run_case(row)
        results.append(result)
        print(
            f"    decision={result['decision']} match={result['match']} "
            f"wall_ms={result['wall_ms']} api={result['api_calls']}",
            file=sys.stderr,
            flush=True,
        )
    metrics = compute_metrics(results)
    return {
        "product": "MoolTrace",
        "kind": "labelled_eval",
        "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "file": str(path or DEFAULT_FILE),
        "selection": (
            "Thirty health-AI drafts on isolated graphs. Clean DOIs had no "
            "Crossref retraction/withdrawal/removal/EoC on the work itself "
            "and no flagged ancestor within depth 2 as of 15 Oct 2026. "
            "They are not a random sample."
        ),
        "metrics": metrics,
        "results": results,
        "wall_s": round(time.perf_counter() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mooltrace labelled")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--family", choices=FAMILIES, default=None)
    args = parser.parse_args(argv)
    if Path(config.DB_PATH).exists():
        print(f"leaving configured DB untouched: {config.DB_PATH}", file=sys.stderr, flush=True)
    print("MoolTrace labelled set (isolated graphs)", file=sys.stderr, flush=True)
    report = run_labelled(args.file, limit=args.limit, family=args.family)
    close_client()
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    metrics = report["metrics"]
    print(
        f"LABELLED scored {metrics['scored']}/{metrics['n']} "
        f"precision={metrics['precision']} recall={metrics['recall']} "
        f"exact={metrics['exact_match_rate']} wall_s={report['wall_s']}",
        file=sys.stderr,
        flush=True,
    )
    if metrics["infra"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
