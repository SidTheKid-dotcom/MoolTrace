"""CI batch over JSONL answer fixtures.

Each line is one fixture: id, engine, text, and citations or urls.
The batch prints one JSON object and GitHub workflow annotations.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.graph import Graph
from mooltrace.ssrf import UnsafeURL
from mooltrace.trace import check_answer


def _urls(row: dict[str, Any]) -> list[str]:
    values = row.get("urls") or row.get("citations") or []
    if isinstance(values, str):
        return [values]
    return [str(item).strip() for item in values if str(item).strip()]


def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text().splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        item = json.loads(raw)
        if not isinstance(item, dict):
            raise MoolTraceError(f"{path}:{index} is not a JSON object")
        item["_line"] = index
        rows.append(item)
    return rows


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    rank = (pct / 100.0) * (len(values) - 1)
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    frac = rank - low
    return round(values[low] * (1.0 - frac) + values[high] * frac, 2)


def _annotate(level: str, file: str, line: int, message: str) -> None:
    safe = message.replace("\n", " ").replace("\r", " ")
    print(f"::{level} file={file},line={line}::{safe}", file=sys.stderr)


def run_batch(
    path: Path,
    *,
    graph: Graph,
    fail_on: str = "block",
    depth: int | None = None,
) -> dict[str, Any]:
    fixtures = _load(path)
    results = []
    worst = "pass"
    for item in fixtures:
        ident = str(item.get("id") or item.get("engine") or f"line-{item['_line']}")
        engine = str(item.get("engine") or ident)[:64]
        text = str(item.get("text") or "")
        urls = _urls(item)
        line = int(item["_line"])
        started = time.perf_counter()
        try:
            payload = check_answer(
                text=text,
                urls=urls,
                engine=engine,
                depth=int(item["depth"]) if item.get("depth") is not None else (depth or 2),
                graph=graph,
            )
        except InfraError as exc:
            payload = {
                "decision": "incomplete",
                "exit_code": 3,
                "summary": str(exc),
                "error_code": "infra",
                "paths": [],
                "errors": [str(exc)],
            }
        except (MoolTraceError, UnsafeURL) as exc:
            payload = {
                "decision": "incomplete",
                "exit_code": 2,
                "summary": str(exc),
                "paths": [],
                "errors": [str(exc)],
            }
        wall_ms = (time.perf_counter() - started) * 1000
        decision = payload.get("decision") or "incomplete"
        exit_code = int(payload.get("exit_code") or 2)
        row = {
            "id": ident,
            "engine": engine,
            "line": line,
            "decision": decision,
            "exit_code": exit_code,
            "summary": payload.get("summary"),
            "cypher": payload.get("cypher"),
            "api_calls": payload.get("api_calls") or 0,
            "cache_hits": payload.get("cache_hits") or 0,
            "elapsed_ms": payload.get("elapsed_ms"),
            "wall_ms": round(wall_ms, 2),
            "errors": (payload.get("errors") or [])[:8],
            "reasons": [
                {
                    "code": reason.get("code"),
                    "root_doi": reason.get("root_doi"),
                    "notice_doi": reason.get("notice_doi"),
                    "notice_type": reason.get("notice_type"),
                    "sentence": reason.get("sentence"),
                    "path_score": reason.get("path_score"),
                }
                for reason in payload.get("reasons") or []
            ],
        }
        results.append(row)
        if exit_code == 3:
            worst = "infra"
            _annotate("error", str(path), line, f"{ident}: infra {payload.get('summary')}")
        elif decision == "block":
            if worst != "infra":
                worst = "block"
            _annotate("error", str(path), line, f"{ident}: block {payload.get('summary')}")
        elif decision in {"warn", "incomplete"}:
            if worst == "pass":
                worst = "warn"
            _annotate("warning", str(path), line, f"{ident}: {decision} {payload.get('summary')}")
    clusters: dict[str, Any]
    try:
        cluster_run = graph.wcc_clusters()
        clusters = {
            "algorithm": "algo.WCC",
            "call": cluster_run.cypher,
            "clusters": cluster_run.rows,
            "elapsed_ms": round(cluster_run.elapsed_ms, 2),
        }
    except Exception as exc:
        clusters = {
            "algorithm": "algo.WCC",
            "clusters": [],
            "error": str(exc),
        }
    if fail_on == "never":
        failed = False
    elif fail_on == "infra":
        failed = worst == "infra"
    elif fail_on == "warn":
        failed = worst in {"warn", "block", "infra"}
    else:
        failed = worst in {"block", "infra"}
    if worst == "infra":
        exit_code = 3
    elif failed and worst == "block":
        exit_code = 1
    elif failed:
        exit_code = 2
    else:
        exit_code = 0
    query_ms = sorted(
        float(row["elapsed_ms"])
        for row in results
        if isinstance(row.get("elapsed_ms"), (int, float))
    )
    return {
        "product": "MoolTrace",
        "file": str(path),
        "fail_on": fail_on,
        "worst": worst,
        "failed": failed,
        "exit_code": exit_code,
        "timing": {
            "answers": len(results),
            "query_ms_p50": _percentile(query_ms, 50),
            "query_ms_p95": _percentile(query_ms, 95),
            "infra": sum(1 for row in results if int(row.get("exit_code") or 0) == 3),
            "api_calls": sum(int(row.get("api_calls") or 0) for row in results),
            "cache_hits": sum(int(row.get("cache_hits") or 0) for row in results),
        },
        "remediation_clusters": clusters,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mooltrace batch")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument(
        "--fail-on",
        choices=("block", "warn", "infra", "never"),
        default="block",
        help="CI fails when the worst fixture reaches this level. Default: block.",
    )
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--db", type=Path, default=None, help="Throwaway graph path. Default: a temp file.")
    args = parser.parse_args(argv)
    if args.db:
        graph = Graph(args.db)
    else:
        import tempfile

        graph = Graph(Path(tempfile.mkdtemp()) / "mooltrace.db")
    try:
        report = run_batch(args.jsonl, graph=graph, fail_on=args.fail_on, depth=args.depth)
    finally:
        graph.close()
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return int(report["exit_code"]) if report["failed"] or report["worst"] == "infra" else 0
