"""Seed a demo graph from examples/ using live catalogs.

Never writes the shared repo file data/mooltrace.db. Healthline is
URL-only. Lancet is a short draft with a DOI. The third fixture cites a
clean DOI. None of the files hold full article text. An Expression of
Concern is not a retraction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mooltrace.config import (
    CLEAN_REWRITE_DOI,
    HARVARD_VITAMIN_D_URL,
    HEALTHLINE_CINNAMON_URL,
    HEALTHLINE_OLIVE_OIL_URL,
    NHS_HANDWASH_URL,
    ROOT,
)
from mooltrace.graph import Graph, get_graph
from mooltrace.trace import check_answer

SHARED_DB = (ROOT / "data" / "mooltrace.db").resolve()
BLOCK_ID = "nutrition-harvard-vitamin-d"
WARN_ID = "nutrition-healthline"
OLIVE_ID = "nutrition-olive-oil"
CLEAN_ID = "clean-jsps"
NOT_IN_GRAPH_ID = "not-in-graph"
LANCET_ID = "lancet-hcq"
HERO_ID = BLOCK_ID
DEMO_FILES = (
    ROOT / "examples" / "harvard_vitamin_d.jsonl",
    ROOT / "examples" / "olive_oil.jsonl",
    ROOT / "examples" / "healthline.jsonl",
    ROOT / "examples" / "clean.jsonl",
    ROOT / "examples" / "not_in_graph.jsonl",
)


def demo_db_path() -> Path:
    raw = os.environ.get("MOOLTRACE_DB", "").strip()
    if not raw:
        raise SystemExit(
            "Set MOOLTRACE_DB to a demo graph path. "
            "Refusing the shared data/mooltrace.db default."
        )
    path = Path(raw).expanduser().resolve()
    if path == SHARED_DB:
        raise SystemExit("Refusing to write the shared data/mooltrace.db.")
    return path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        item = json.loads(raw)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def load_demo_fixtures() -> list[dict[str, Any]]:
    wanted = {BLOCK_ID, WARN_ID, OLIVE_ID, CLEAN_ID, NOT_IN_GRAPH_ID}
    found: dict[str, dict[str, Any]] = {}
    for path in DEMO_FILES:
        for item in _load_jsonl(path):
            ident = str(item.get("id") or "")
            if ident in wanted:
                found[ident] = item
    missing = wanted - set(found)
    if missing:
        raise SystemExit(f"demo fixtures missing ids: {sorted(missing)}")
    block = found[BLOCK_ID]
    if block.get("text"):
        raise SystemExit("block fixture must be URL-only (empty text)")
    if block.get("urls") != [HARVARD_VITAMIN_D_URL]:
        raise SystemExit("block fixture must cite the Harvard vitamin D URL only")
    if int(block.get("depth") or 0) != 2:
        raise SystemExit("block fixture must request depth 2")
    warn = found[WARN_ID]
    if warn.get("text"):
        raise SystemExit("warn fixture must be URL-only (empty text)")
    if warn.get("urls") != [HEALTHLINE_CINNAMON_URL]:
        raise SystemExit("warn fixture must cite the Healthline cinnamon URL only")
    olive = found[OLIVE_ID]
    if olive.get("text"):
        raise SystemExit("olive-oil fixture must be URL-only (empty text)")
    if olive.get("urls") != [HEALTHLINE_OLIVE_OIL_URL]:
        raise SystemExit("olive-oil fixture must cite the Healthline olive oil URL only")
    if int(olive.get("depth") or 0) != 3:
        raise SystemExit("olive-oil fixture must request depth 3")
    clean = found[CLEAN_ID]
    if CLEAN_REWRITE_DOI not in str(clean.get("text") or ""):
        raise SystemExit("clean fixture must name the clean rewrite DOI")
    missing_row = found[NOT_IN_GRAPH_ID]
    if missing_row.get("text"):
        raise SystemExit("not-in-graph fixture must be URL-only (empty text)")
    if missing_row.get("urls") != [NHS_HANDWASH_URL]:
        raise SystemExit("not-in-graph fixture must cite the NHS handwashing URL only")
    return [block, warn, olive, clean, missing_row]


def _urls(row: dict[str, Any]) -> list[str]:
    values = row.get("urls") or []
    if isinstance(values, str):
        return [values]
    return [str(item).strip() for item in values if str(item).strip()]


def answer_count(graph: Graph) -> int:
    for row in graph.counts().rows:
        if row.get("label") == "Answer":
            return int(row.get("count") or 0)
    return 0


def seed_demo(graph: Graph) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in load_demo_fixtures():
        ident = str(item.get("id") or "demo")
        payload = check_answer(
            text=str(item.get("text") or ""),
            urls=_urls(item),
            engine=str(item.get("engine") or ident),
            depth=int(item.get("depth") or 2),
            graph=graph,
        )
        results.append(
            {
                "id": ident,
                "decision": payload.get("decision"),
                "exit_code": payload.get("exit_code"),
                "summary": payload.get("summary"),
                "notice_types": [
                    reason.get("notice_type")
                    for reason in payload.get("reasons") or []
                    if reason.get("notice_type")
                ],
                "errors": (payload.get("errors") or [])[:8],
            }
        )
    graph.persist()
    return results


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if_empty = "--if-empty" in args
    offline = "--offline" in args or os.environ.get("MOOLTRACE_PUBLIC_DEMO", "").strip() == "1"
    path = demo_db_path()
    graph = get_graph(path)
    try:
        if if_empty and answer_count(graph) > 0:
            print(json.dumps({"seeded": False, "reason": "graph already has answers", "db": str(path)}))
            return 0
        if offline:
            from mooltrace.public_demo import seed_offline_presets

            results = seed_offline_presets(graph)
        else:
            results = seed_demo(graph)
    finally:
        graph.persist()
    print(json.dumps({"seeded": True, "offline": offline, "db": str(path), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
