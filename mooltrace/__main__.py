"""CLI. `mooltrace check-answer` is the pre-ship check for CI and bot pipelines."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.graph import get_graph
from mooltrace.ssrf import UnsafeURL
from mooltrace.rewrite import rewrite_answer
from mooltrace.summary import format_explain, format_rewrite_summary, format_summary
from mooltrace.trace import (
    check_answer,
    check_study,
    recheck_affected,
    shared_ancestors,
    trace_answer,
    what_rests_on,
)


def _read(path: str | None, fallback: str) -> str:
    if not path:
        return fallback
    return Path(path).read_text()


def _urls_from_file(path: str | None, urls: list[str]) -> list[str]:
    if not path:
        return urls
    lines = [line.strip() for line in Path(path).read_text().splitlines()]
    return urls + [line for line in lines if line and not line.startswith("#")]


def _print(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mooltrace",
        description=(
            "Pre-ship citation check for health AI drafts. "
            "pass ships, warn needs a human, block fails the build."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser(
        "check-answer",
        aliases=["check"],
        help="pass / warn / block a draft",
    )
    check.add_argument("--text", default="", help="Draft text to check.")
    check.add_argument("--text-file", help="Read draft text from a file.")
    check.add_argument(
        "--url",
        action="append",
        default=[],
        help="Cited source URL. Repeat for more than one.",
    )
    check.add_argument("--urls-file", help="File of cited URLs, one per line.")
    check.add_argument("--engine", default="draft", help="Engine or fixture name.")
    check.add_argument("--depth", type=int, default=2, help="Hop budget from 1 to 3.")
    check.add_argument(
        "--summary",
        action="store_true",
        help="Print a 3-line plain-English verdict instead of JSON.",
    )
    check.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON payload (default when stdout is not a TTY).",
    )
    check.add_argument(
        "--explain",
        action="store_true",
        help="Print the verdict plus Why the graph decided (filled Cypher, path, direct-DOI contrast).",
    )

    trace = sub.add_parser("trace", help="return paths to publisher notices")
    trace.add_argument("--text", default="", help="Draft text to trace.")
    trace.add_argument("--text-file", help="Read draft text from a file.")
    trace.add_argument("--url", action="append", default=[], help="Cited source URL.")
    trace.add_argument("--urls-file", help="File of cited URLs, one per line.")
    trace.add_argument("--engine", default="draft", help="Engine or fixture name.")
    trace.add_argument("--depth", type=int, default=2, help="Hop budget from 1 to 3.")

    rewrite = sub.add_parser("rewrite", help="rewrite flagged sentences and recheck")
    rewrite.add_argument("--text", default="", help="Draft text to rewrite.")
    rewrite.add_argument("--text-file", help="Read draft text from a file.")
    rewrite.add_argument("--url", action="append", default=[], help="Cited source URL.")
    rewrite.add_argument("--urls-file", help="File of cited URLs, one per line.")
    rewrite.add_argument("--engine", default="draft", help="Engine or fixture name.")
    rewrite.add_argument("--depth", type=int, default=2, help="Hop budget from 1 to 3.")
    rewrite.add_argument(
        "--summary",
        action="store_true",
        help="Print a plain-English rewrite + recheck verdict instead of JSON.",
    )
    rewrite.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON payload (default when stdout is not a TTY).",
    )

    study = sub.add_parser("check-study", help="notices on one DOI or PMID")
    study.add_argument("doi_or_pmid", help="DOI or PubMed id of one study.")

    rests = sub.add_parser("rests-on", help="what in the graph rests on a DOI")
    rests.add_argument("doi", help="Notice DOI or study DOI.")
    rests.add_argument(
        "--summary",
        action="store_true",
        help="Print the affect-N-answers line instead of JSON.",
    )

    recheck = sub.add_parser(
        "recheck-affected",
        help="re-run the check on answers that rest on a flagged DOI",
    )
    recheck.add_argument("doi", help="Notice DOI or study DOI.")
    recheck.add_argument("--depth", type=int, default=2, help="Hop budget from 1 to 3.")

    shared = sub.add_parser("shared", help="shared hub works for two engines or answers")
    shared.add_argument("--answer-a", default="", help="First answer id already in the graph.")
    shared.add_argument("--answer-b", default="", help="Second answer id already in the graph.")
    shared.add_argument("--engine-a", default="", help="Engine name if answer-a is omitted.")
    shared.add_argument("--engine-b", default="", help="Engine name if answer-b is omitted.")

    batch = sub.add_parser("batch", help="check a JSONL file of answer fixtures")
    batch.add_argument("jsonl", help="JSONL of answer fixtures (id, engine, text, urls).")
    batch.add_argument(
        "--fail-on",
        choices=("block", "warn", "infra", "never"),
        default="block",
        help="Lowest severity that fails the job. Default: block.",
    )
    batch.add_argument("--depth", type=int, default=None, help="Hop budget from 1 to 3.")
    batch.add_argument("--db", help="Throwaway graph path. Default: a temp file.")

    labelled = sub.add_parser("labelled", help="run the labelled set on isolated graphs")
    labelled.add_argument("--file", default=None, help="JSONL of labelled cases.")
    labelled.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    labelled.add_argument("--family", default=None, help="Run one family only.")

    baseline = sub.add_parser(
        "baseline",
        help="no-graph direct-DOI baseline vs labelled set (recorded Crossref)",
        description=(
            "No-graph direct-DOI baseline vs MoolTrace on the labelled set. "
            "Uses recorded Crossref so the comparison reproduces offline."
        ),
    )
    baseline.add_argument("--file", default=None, help="JSONL of labelled cases.")
    baseline.add_argument("--crossref", default=None, help="Recorded Crossref catalog JSON.")
    baseline.add_argument("--mooltrace", default=None, help="Recorded MoolTrace labelled JSON.")
    baseline.add_argument("--previous", default=None, help="Prior labelled JSON for verdict diffs.")
    baseline.add_argument("--out", default=None, help="Write the report JSON here.")
    baseline.add_argument(
        "--live-crossref",
        action="store_true",
        help="Call Crossref instead of the recorded catalog.",
    )

    vitality = sub.add_parser(
        "vitality",
        help="sealed VITALITY Study I eval vs no-graph direct-DOI",
        description=(
            "Sealed VITALITY Study I eval. Direct-DOI (no graph) vs MoolTrace "
            "depth 2 on drafts that cite only a review DOI. Default is offline "
            "from recorded Crossref and recorded MoolTrace fixtures. --live "
            "walks one throwaway graph at a time, OpenAlex RPS<=3, shared HTTP "
            "cache, and resumes on 429."
        ),
    )
    vitality.add_argument("--frozen", default=None, help="Frozen VITALITY JSON.")
    vitality.add_argument("--crossref", default=None, help="Recorded Crossref catalog JSON.")
    vitality.add_argument("--snapshot", default=None, help="Recorded MoolTrace snapshot JSON.")
    vitality.add_argument("--out", default=None, help="Write the report JSON here.")
    vitality.add_argument("--md", default=None, help="Write the report markdown here.")
    vitality.add_argument("--limit", type=int, default=None, help="Live-run only the first N cases.")
    vitality.add_argument("--depth", type=int, default=2, help="Hop budget. Default 2.")
    vitality.add_argument(
        "--live",
        action="store_true",
        help="Run MoolTrace on throwaway graphs (writes the snapshot).",
    )
    vitality.add_argument(
        "--record-crossref",
        action="store_true",
        help="Fetch Crossref for every frozen DOI into the catalog.",
    )

    sub.add_parser("mcp", help="run the MCP server on stdio")
    sub.add_parser("api", help="run the demo HTTP API")
    sub.add_parser("gate", help="run the seeded live regression on throwaway graphs")
    seed = sub.add_parser("seed", help="seed a demo graph from examples/ (live catalogs)")
    seed.add_argument(
        "--if-empty",
        action="store_true",
        help="Skip when the demo graph already has Answer nodes.",
    )
    seed.add_argument(
        "--offline",
        action="store_true",
        help="Write the five presets with no live HTTP (public demo).",
    )

    args = parser.parse_args(argv)
    try:
        if args.cmd in {"check-answer", "check"}:
            if args.summary:
                os.environ.setdefault("MOOLTRACE_PROGRESS", "1")
            payload = check_answer(
                _read(args.text_file, args.text),
                _urls_from_file(args.urls_file, args.url),
                args.engine,
                args.depth,
            )
            want_summary = args.summary or (sys.stdout.isatty() and not args.json)
            if args.explain and not args.json:
                sys.stdout.write(format_explain(payload))
            elif want_summary and not args.json:
                sys.stdout.write(format_summary(payload))
            else:
                _print(payload)
            return int(payload["exit_code"])
        if args.cmd == "rewrite":
            payload = rewrite_answer(
                _read(args.text_file, args.text),
                _urls_from_file(args.urls_file, args.url),
                args.engine,
                args.depth,
                graph=get_graph(),
            )
            want_summary = args.summary or (sys.stdout.isatty() and not args.json)
            if want_summary and not args.json:
                sys.stdout.write(format_rewrite_summary(payload))
            else:
                _print(payload)
            code = payload.get("exit_code")
            if code is None:
                recheck = payload.get("recheck") or {}
                code = recheck.get("exit_code")
            return int(code) if code is not None else 2
        if args.cmd == "trace":
            _print(
                trace_answer(
                    _read(args.text_file, args.text),
                    _urls_from_file(args.urls_file, args.url),
                    args.engine,
                    args.depth,
                )
            )
            return 0
        if args.cmd == "check-study":
            _print(check_study(args.doi_or_pmid))
            return 0
        if args.cmd == "rests-on":
            payload = what_rests_on(args.doi)
            if args.summary:
                sys.stdout.write((payload.get("summary") or "") + "\n")
            else:
                _print(payload)
            return 0
        if args.cmd == "recheck-affected":
            _print(recheck_affected(args.doi, depth=args.depth))
            return 0
        if args.cmd == "shared":
            _print(shared_ancestors(args.answer_a, args.answer_b, args.engine_a, args.engine_b))
            return 0
        if args.cmd == "mcp":
            from mooltrace.mcp_server import main as mcp_main

            mcp_main()
            return 0
        if args.cmd == "api":
            from mooltrace.api import main as api_main

            api_main()
            return 0
        if args.cmd == "batch":
            from mooltrace.batch import main as batch_main

            argv_batch = [args.jsonl, "--fail-on", args.fail_on]
            if args.depth is not None:
                argv_batch.extend(["--depth", str(args.depth)])
            if args.db:
                argv_batch.extend(["--db", args.db])
            return batch_main(argv_batch)
        if args.cmd == "labelled":
            from mooltrace.labelled import main as labelled_main

            argv_labelled: list[str] = []
            if args.file:
                argv_labelled.extend(["--file", args.file])
            if args.limit is not None:
                argv_labelled.extend(["--limit", str(args.limit)])
            if args.family:
                argv_labelled.extend(["--family", args.family])
            return labelled_main(argv_labelled)
        if args.cmd == "baseline":
            from mooltrace.baseline import main as baseline_main

            argv_baseline: list[str] = []
            if args.file:
                argv_baseline.extend(["--file", args.file])
            if args.crossref:
                argv_baseline.extend(["--crossref", args.crossref])
            if args.mooltrace:
                argv_baseline.extend(["--mooltrace", args.mooltrace])
            if args.previous:
                argv_baseline.extend(["--previous", args.previous])
            if args.out:
                argv_baseline.extend(["--out", args.out])
            if args.live_crossref:
                argv_baseline.append("--live-crossref")
            return baseline_main(argv_baseline)
        if args.cmd == "vitality":
            from mooltrace.vitality import main as vitality_main

            argv_vitality: list[str] = []
            if args.frozen:
                argv_vitality.extend(["--frozen", args.frozen])
            if args.crossref:
                argv_vitality.extend(["--crossref", args.crossref])
            if args.snapshot:
                argv_vitality.extend(["--snapshot", args.snapshot])
            if args.out:
                argv_vitality.extend(["--out", args.out])
            if args.md:
                argv_vitality.extend(["--md", args.md])
            if args.limit is not None:
                argv_vitality.extend(["--limit", str(args.limit)])
            if args.depth != 2:
                argv_vitality.extend(["--depth", str(args.depth)])
            if args.live:
                argv_vitality.append("--live")
            if args.record_crossref:
                argv_vitality.append("--record-crossref")
            return vitality_main(argv_vitality)
        if args.cmd == "gate":
            from mooltrace.gate import main as gate_main

            return gate_main()
        if args.cmd == "seed":
            from mooltrace.seed import main as seed_main

            argv_seed = []
            if args.if_empty:
                argv_seed.append("--if-empty")
            if args.offline:
                argv_seed.append("--offline")
            return seed_main(argv_seed)
    except InfraError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (MoolTraceError, UnsafeURL) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
