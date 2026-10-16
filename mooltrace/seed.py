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

from mooltrace.config import CLEAN_REWRITE_DOI, HEALTHLINE_CINNAMON_URL, ROOT
from mooltrace.graph import Graph, get_graph
from mooltrace.trace import check_answer

SHARED_DB = (ROOT / "data" / "mooltrace.db").resolve()
HERO_ID = "nutrition-healthline"
LANCET_ID = "lancet-hcq"
CLEAN_ID = "clean-jsps"
DEMO_FILES = (
    ROOT / "examples" / "healthline.jsonl",
    ROOT / "examples" / "lancet.jsonl",
    ROOT / "examples" / "clean.jsonl",
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
    wanted = {HERO_ID, LANCET_ID, CLEAN_ID}
    found: dict[str, dict[str, Any]] = {}
    for path in DEMO_FILES:
        for item in _load_jsonl(path):
            ident = str(item.get("id") or "")
            if ident in wanted:
                found[ident] = item
    missing = wanted - set(found)
    if missing:
        raise SystemExit(f"demo fixtures missing ids: {sorted(missing)}")
    hero = found[HERO_ID]
    if hero.get("text"):
        raise SystemExit("hero fixture must be URL-only (empty text)")
    if hero.get("urls") != [HEALTHLINE_CINNAMON_URL]:
        raise SystemExit("hero fixture must cite the Healthline cinnamon URL only")
    lancet = found[LANCET_ID]
    if "10.1016/S0140-6736(20)31180-6" not in str(lancet.get("text") or ""):
        raise SystemExit("Lancet fixture must name the retracted paper DOI")
    clean = found[CLEAN_ID]
    if CLEAN_REWRITE_DOI not in str(clean.get("text") or ""):
        raise SystemExit("clean fixture must name the clean rewrite DOI")
    return [hero, lancet, clean]


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
            depth=2,
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
    path = demo_db_path()
    graph = get_graph(path)
    try:
        if if_empty and answer_count(graph) > 0:
            print(json.dumps({"seeded": False, "reason": "graph already has answers", "db": str(path)}))
            return 0
        results = seed_demo(graph)
    finally:
        graph.persist()
    print(json.dumps({"seeded": True, "db": str(path), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
