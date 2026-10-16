"""No-graph direct-DOI baseline checker.

Looks up DOIs and doi.org URLs that are literally in the draft (and the
explicit URL list) on Crossref. It does not fetch consumer pages, does
not walk RESTS_ON, and does not open a graph. An Expression of Concern
is not a retraction. Live scores are not hardcoded.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mooltrace import config
from mooltrace.clients import InfraError, MoolTraceError, close_client, crossref_work, CallStats
from mooltrace.decision import EXIT_BLOCK, EXIT_INFRA, EXIT_PASS, EXIT_WARN
from mooltrace.ids import (
    clean_doi,
    extract_identifiers,
    has_verifiable_source,
    is_publisher_flag,
    normalize_update_type,
    valid_doi,
)
from mooltrace.labelled import (
    DEFAULT_FILE,
    DECISIONS,
    POSITIVE,
    compute_metrics,
    load_labelled,
)

DEFAULT_CROSSREF = config.ROOT / "examples" / "baseline_crossref.json"
DEFAULT_MOOLTRACE = config.ROOT / "examples" / "baseline_mooltrace.json"
PREVIOUS_LABELLED = config.ROOT / "results" / "labelled_2026-10-15.json"

Lookup = Callable[[str], dict[str, Any] | None]

PASS_NO_DOI = (
    "Direct-DOI check (no graph): no DOI or doi.org URL was present in the "
    "draft. Pages are not fetched."
)
PASS_NO_NOTICE = (
    "Direct-DOI check (no graph): Crossref lists no retraction, withdrawal, "
    "removal, or Expression of Concern on the cited DOI itself."
)
WARN_EOC = (
    "Direct-DOI check (no graph): the cited DOI itself has an Expression of "
    "Concern on Crossref."
)
BLOCK_RETRACTION = (
    "Direct-DOI check (no graph): the cited DOI itself has a retraction on "
    "Crossref."
)
BLOCK_WITHDRAWAL = (
    "Direct-DOI check (no graph): the cited DOI itself has a withdrawal or "
    "removal on Crossref."
)


def _urls(row: dict[str, Any]) -> list[str]:
    values = row.get("urls") or []
    if isinstance(values, str):
        return [values]
    return [str(item).strip() for item in values if str(item).strip()]


def literal_dois(text: str, urls: list[str] | None = None) -> list[str]:
    """DOIs written in the draft or in the URL list. Does not fetch pages."""
    parts = [text or ""]
    parts.extend(urls or [])
    return extract_identifiers("\n".join(parts)).dois


def labelling_rule(path: Path | None = None) -> str:
    target = path or DEFAULT_FILE
    lines: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            lines.append(line[1:].strip())
    return "\n".join(lines).strip()


def load_crossref_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_CROSSREF
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("works"), dict):
        raise ValueError(f"{target} is not a Crossref catalog")
    return payload


def recorded_lookup(catalog: dict[str, Any]) -> Lookup:
    works = catalog.get("works") or {}

    def lookup(doi: str) -> dict[str, Any] | None:
        entry = works.get(doi) or works.get(doi.lower())
        if not isinstance(entry, dict):
            return None
        if int(entry.get("status") or 0) != 200:
            return None
        message = entry.get("message")
        return message if isinstance(message, dict) else None

    return lookup


def live_lookup(stats: CallStats | None = None) -> Lookup:
    tally = stats or CallStats()

    def lookup(doi: str) -> dict[str, Any] | None:
        return crossref_work(doi, tally)

    return lookup


def _notice_date(update: dict[str, Any]) -> str:
    updated = update.get("updated") or {}
    if updated.get("date-time"):
        return str(updated["date-time"])[:10]
    parts = (updated.get("date-parts") or [[]])[0]
    if not parts:
        return ""
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _kind(notice_type: str | None) -> str:
    raw = normalize_update_type(notice_type)
    if raw == "expression_of_concern":
        return "expression_of_concern"
    if "retract" in raw:
        return "retraction"
    if "withdraw" in raw or raw == "removal":
        return "withdrawal"
    return raw or "notice"


def notices_on_work(message: dict[str, Any] | None, work_doi: str) -> list[dict[str, Any]]:
    if not message:
        return []
    rows: list[dict[str, Any]] = []
    for update in message.get("updated-by") or []:
        if not is_publisher_flag(update.get("type")):
            continue
        notice_doi = clean_doi(update.get("DOI") or "")
        if not valid_doi(notice_doi):
            continue
        code = _kind(update.get("type"))
        rows.append(
            {
                "code": code,
                "root_doi": work_doi,
                "notice_doi": notice_doi,
                "notice_type": normalize_update_type(update.get("type")),
                "notice_label": update.get("label") or update.get("type") or "",
                "notice_source": update.get("source") or "publisher",
                "notice_date": _notice_date(update),
                "hops": 1,
                "path_score": 1.0,
            }
        )
    return rows


def _lead(notices: list[dict[str, Any]]) -> dict[str, Any]:
    def rank(item: dict[str, Any]) -> tuple[int, int]:
        kind_rank = {"retraction": 0, "withdrawal": 1, "expression_of_concern": 2}.get(
            item.get("code") or "", 3
        )
        source = str(item.get("notice_source") or "").lower()
        source_rank = 0 if "retraction-watch" in source else 1
        return (kind_rank, source_rank)

    return sorted(notices, key=rank)[0]


def check_direct_doi(
    text: str,
    urls: list[str] | None = None,
    *,
    lookup: Lookup | None = None,
) -> dict[str, Any]:
    """Pass / warn / block from Crossref notices on literal DOIs only."""
    finder = lookup if lookup is not None else recorded_lookup(load_crossref_catalog())
    dois = literal_dois(text, urls)
    notices: list[dict[str, Any]] = []
    resolved: list[str] = []
    unresolved: list[str] = []
    try:
        for doi in dois:
            message = finder(doi)
            if message is None:
                unresolved.append(doi)
                continue
            resolved.append(doi)
            notices.extend(notices_on_work(message, doi))
    except InfraError as exc:
        return {
            "decision": "incomplete",
            "exit_code": EXIT_INFRA,
            "summary": str(exc),
            "graph": False,
            "checker": "direct_doi_crossref",
            "dois": dois,
            "resolved": resolved,
            "unresolved": unresolved,
            "reasons": [],
            "errors": [str(exc)],
        }
    except MoolTraceError as exc:
        return {
            "decision": "incomplete",
            "exit_code": 2,
            "summary": str(exc),
            "graph": False,
            "checker": "direct_doi_crossref",
            "dois": dois,
            "resolved": resolved,
            "unresolved": unresolved,
            "reasons": [],
            "errors": [str(exc)],
        }

    kinds = {item["code"] for item in notices}
    if "retraction" in kinds:
        decision = "block"
        exit_code = EXIT_BLOCK
        summary = BLOCK_RETRACTION
    elif "withdrawal" in kinds:
        decision = "block"
        exit_code = EXIT_BLOCK
        summary = BLOCK_WITHDRAWAL
    elif "expression_of_concern" in kinds:
        decision = "warn"
        exit_code = EXIT_WARN
        summary = WARN_EOC
    else:
        decision = "pass"
        exit_code = EXIT_PASS
        summary = PASS_NO_DOI if not dois else PASS_NO_NOTICE

    reasons = [_lead(notices)] if notices else []
    return {
        "decision": decision,
        "exit_code": exit_code,
        "summary": summary,
        "graph": False,
        "checker": "direct_doi_crossref",
        "dois": dois,
        "resolved": resolved,
        "unresolved": unresolved,
        "reasons": reasons,
        "errors": [],
    }


def miss_kind(row: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """Why a labelled positive was missed. None if not a miss."""
    expected_flagged = str(row.get("expected") or "") in POSITIVE
    predicted_flagged = str(payload.get("decision") or "") in POSITIVE
    if not expected_flagged or predicted_flagged:
        return None
    text = str(row.get("text") or "")
    urls = _urls(row)
    if not has_verifiable_source(text, urls):
        return "no_sources"
    dois = list(payload.get("dois") or [])
    if not dois:
        return "multihop"
    if payload.get("resolved"):
        return "multihop"
    return "unresolved"


def run_case(
    row: dict[str, Any],
    *,
    lookup: Lookup,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    payload = check_direct_doi(
        str(row.get("text") or ""),
        _urls(row),
        lookup=lookup,
    )
    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    decision = str(payload.get("decision") or "incomplete")
    exit_code = int(payload.get("exit_code") or 2)
    expected = str(row["expected"])
    infra = exit_code == EXIT_INFRA
    scored = (not infra) and decision in DECISIONS
    kind = miss_kind(row, payload)
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
        "miss_kind": kind,
        "summary": payload.get("summary"),
        "dois": payload.get("dois") or [],
        "resolved": payload.get("resolved") or [],
        "unresolved": payload.get("unresolved") or [],
        "wall_ms": wall_ms,
        "query_ms": wall_ms,
        "errors": (payload.get("errors") or [])[:6],
        "reasons": payload.get("reasons") or [],
        "graph": False,
        "checker": "direct_doi_crossref",
    }


def _multihop_rows(
    baseline_rows: list[dict[str, Any]],
    mooltrace_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in baseline_rows:
        if row.get("miss_kind") != "multihop":
            continue
        if mooltrace_by_id is None:
            if row.get("expected_flagged") and not row.get("predicted_flagged"):
                out.append(
                    {
                        "id": row["id"],
                        "family": row["family"],
                        "expected": row["expected"],
                        "baseline": row["decision"],
                        "dois": row.get("dois") or [],
                        "notes": "labelled expected flagged; literal DOI/URL has no own Crossref notice",
                    }
                )
            continue
        mt = mooltrace_by_id.get(str(row["id"]))
        if not mt:
            continue
        if mt.get("predicted_flagged") and not row.get("predicted_flagged"):
            out.append(
                {
                    "id": row["id"],
                    "family": row["family"],
                    "expected": row["expected"],
                    "baseline": row["decision"],
                    "mooltrace": mt.get("decision"),
                    "dois": row.get("dois") or [],
                    "notes": "MoolTrace flagged a chain the direct-DOI checker never walked",
                }
            )
    return out


def verdict_changes(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    older = {str(row["id"]): row for row in previous}
    changed: list[dict[str, Any]] = []
    for row in current:
        ident = str(row["id"])
        was = older.get(ident)
        if was is None:
            continue
        if was.get("decision") != row.get("decision"):
            changed.append(
                {
                    "id": ident,
                    "family": row.get("family"),
                    "previous": was.get("decision"),
                    "current": row.get("decision"),
                    "expected": row.get("expected"),
                }
            )
    return changed


def run_baseline_eval(
    path: Path | None = None,
    *,
    lookup: Lookup | None = None,
    catalog_path: Path | None = None,
    mooltrace_report: dict[str, Any] | None = None,
    previous_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = load_labelled(path)
    catalog = None
    finder = lookup
    if finder is None:
        catalog = load_crossref_catalog(catalog_path)
        finder = recorded_lookup(catalog)
    started = time.perf_counter()
    results = [run_case(row, lookup=finder) for row in cases]
    metrics = compute_metrics(results)
    mt_rows = list((mooltrace_report or {}).get("results") or [])
    mt_by_id = {str(row["id"]): row for row in mt_rows} if mt_rows else None
    only_multihop = _multihop_rows(results, mt_by_id)
    previous_rows = list((previous_report or {}).get("results") or [])
    changes = verdict_changes(mt_rows, previous_rows) if mt_rows and previous_rows else []
    new_ids = []
    if mt_rows and previous_rows:
        old_ids = {str(row["id"]) for row in previous_rows}
        new_ids = [str(row["id"]) for row in mt_rows if str(row["id"]) not in old_ids]
    report: dict[str, Any] = {
        "product": "MoolTrace",
        "kind": "baseline_eval",
        "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "file": str(path or DEFAULT_FILE),
        "labelling_rule": labelling_rule(path or DEFAULT_FILE),
        "checker": {
            "name": "direct_doi_crossref",
            "graph": False,
            "rule": (
                "Extract DOIs and doi.org URLs literally present in the draft "
                "text and URL list. Look each DOI up on Crossref updated-by. "
                "Retraction/withdrawal/removal → block. Expression of Concern "
                "→ warn. Corrections, errata, and new_version are not flags. "
                "Consumer pages are not fetched. Unresolved DOIs and drafts "
                "with no DOI pass."
            ),
            "crossref_catalog": str(catalog_path or DEFAULT_CROSSREF),
            "crossref_fetched_at": (catalog or {}).get("fetched_at") if catalog else None,
        },
        "n": len(results),
        "baseline": {"metrics": metrics, "results": results},
        "only_multihop_catches": only_multihop,
        "only_multihop_ids": [row["id"] for row in only_multihop],
        "other_baseline_misses": [
            {
                "id": row["id"],
                "family": row["family"],
                "expected": row["expected"],
                "baseline": row["decision"],
                "miss_kind": row.get("miss_kind"),
            }
            for row in results
            if row.get("miss_kind") and row.get("miss_kind") != "multihop"
        ],
        "wall_s": round(time.perf_counter() - started, 1),
    }
    if mooltrace_report:
        by_base = {str(row["id"]): row for row in results}
        disagreements = []
        graph_only = []
        for mt in mt_rows:
            base = by_base.get(str(mt["id"])) or {}
            if not mt.get("match"):
                disagreements.append(
                    {
                        "id": mt["id"],
                        "family": mt.get("family"),
                        "expected": mt.get("expected"),
                        "mooltrace": mt.get("decision"),
                        "baseline": base.get("decision"),
                        "summary": mt.get("summary"),
                        "reasons": mt.get("reasons") or [],
                        "errors": mt.get("errors") or [],
                    }
                )
            if mt.get("predicted_flagged") and not base.get("predicted_flagged"):
                graph_only.append(
                    {
                        "id": mt["id"],
                        "family": mt.get("family"),
                        "expected": mt.get("expected"),
                        "mooltrace": mt.get("decision"),
                        "baseline": base.get("decision"),
                        "multihop": str(mt["id"]) in {item["id"] for item in only_multihop},
                    }
                )
        report["mooltrace"] = {
            "ran_at": mooltrace_report.get("ran_at"),
            "kind": mooltrace_report.get("kind"),
            "wall_s": mooltrace_report.get("wall_s"),
            "metrics": mooltrace_report.get("metrics"),
            "results": mt_rows,
        }
        report["labelled_disagreements"] = disagreements
        report["graph_caught_baseline_missed"] = graph_only
        report["verdict_changes_vs_labelled_2026-10-15"] = changes
        report["new_since_labelled_2026-10-15"] = new_ids
    return report


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mooltrace baseline",
        description=(
            "No-graph direct-DOI baseline vs MoolTrace on the labelled set. "
            "Uses recorded Crossref (and recorded MoolTrace, if present) so "
            "the comparison reproduces offline."
        ),
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--crossref", type=Path, default=DEFAULT_CROSSREF)
    parser.add_argument("--mooltrace", type=Path, default=DEFAULT_MOOLTRACE)
    parser.add_argument("--previous", type=Path, default=PREVIOUS_LABELLED)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--live-crossref",
        action="store_true",
        help="Call Crossref instead of the recorded catalog (not the default).",
    )
    args = parser.parse_args(argv)
    lookup: Lookup | None = None
    catalog_path = args.crossref
    if args.live_crossref:
        lookup = live_lookup()
        catalog_path = None
    mooltrace_report = _load_json(args.mooltrace)
    previous_report = _load_json(args.previous)
    report = run_baseline_eval(
        args.file,
        lookup=lookup,
        catalog_path=catalog_path,
        mooltrace_report=mooltrace_report,
        previous_report=previous_report,
    )
    close_client()
    text = json.dumps(report, indent=2) + "\n"
    sys.stdout.write(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    base = report["baseline"]["metrics"]
    mt = (report.get("mooltrace") or {}).get("metrics") or {}
    print(
        f"BASELINE scored {base['scored']}/{base['n']} "
        f"precision={base['precision']} recall={base['recall']} "
        f"multihop_only={len(report['only_multihop_catches'])}",
        file=sys.stderr,
        flush=True,
    )
    if mt:
        print(
            f"MOOLTRACE scored {mt.get('scored')}/{mt.get('n')} "
            f"precision={mt.get('precision')} recall={mt.get('recall')}",
            file=sys.stderr,
            flush=True,
        )
    if base.get("infra"):
        return EXIT_INFRA
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
