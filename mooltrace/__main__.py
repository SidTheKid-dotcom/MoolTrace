"""CLI. `mooltrace check-answer` is the pre-ship check for CI and bot pipelines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mooltrace.clients import InfraError, MoolTraceError
from mooltrace.ssrf import UnsafeURL
from mooltrace.rewrite import rewrite_answer
from mooltrace.trace import (
    check_answer,
    check_study,
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
        description="Pre-ship citation check for health AI drafts.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check-answer", help="pass / warn / block a draft")
    check.add_argument("--text", default="")
    check.add_argument("--text-file")
    check.add_argument("--url", action="append", default=[])
    check.add_argument("--urls-file")
    check.add_argument("--engine", default="draft")
    check.add_argument("--depth", type=int, default=2)

    trace = sub.add_parser("trace", help="return paths to publisher notices")
    trace.add_argument("--text", default="")
    trace.add_argument("--text-file")
    trace.add_argument("--url", action="append", default=[])
    trace.add_argument("--urls-file")
    trace.add_argument("--engine", default="draft")
    trace.add_argument("--depth", type=int, default=2)

    rewrite = sub.add_parser("rewrite", help="rewrite a flagged draft and recheck")
    rewrite.add_argument("--text", default="")
    rewrite.add_argument("--text-file")
    rewrite.add_argument("--url", action="append", default=[])
    rewrite.add_argument("--urls-file")
    rewrite.add_argument("--engine", default="draft")
    rewrite.add_argument("--depth", type=int, default=2)

    study = sub.add_parser("check-study", help="notices on one DOI or PMID")
    study.add_argument("doi_or_pmid")

    rests = sub.add_parser("rests-on", help="what in the graph rests on a DOI")
    rests.add_argument("doi")

    shared = sub.add_parser("shared", help="shared hub works for two engines or answers")
    shared.add_argument("--answer-a", default="")
    shared.add_argument("--answer-b", default="")
    shared.add_argument("--engine-a", default="")
    shared.add_argument("--engine-b", default="")

    batch = sub.add_parser("batch", help="check a JSONL file of answer fixtures")
    batch.add_argument("jsonl")
    batch.add_argument("--fail-on", choices=("block", "warn", "infra", "never"), default="block")
    batch.add_argument("--depth", type=int, default=None)
    batch.add_argument("--db")

    labelled = sub.add_parser("labelled", help="run the labelled set on isolated graphs")
    labelled.add_argument("--file", default=None)
    labelled.add_argument("--limit", type=int, default=None)
    labelled.add_argument("--family", default=None)

    sub.add_parser("mcp", help="run the MCP server on stdio")
    sub.add_parser("api", help="run the demo HTTP API")
    sub.add_parser("gate", help="run the seeded live regression on throwaway graphs")
    seed = sub.add_parser("seed", help="seed a demo graph from examples/ (live catalogs)")
    seed.add_argument(
        "--if-empty",
        action="store_true",
        help="Skip when the demo graph already has Answer nodes.",
    )

    args = parser.parse_args(argv)
    try:
        if args.cmd == "check-answer":
            payload = check_answer(
                _read(args.text_file, args.text),
                _urls_from_file(args.urls_file, args.url),
                args.engine,
                args.depth,
            )
            _print(payload)
            return int(payload["exit_code"])
        if args.cmd == "rewrite":
            payload = rewrite_answer(
                _read(args.text_file, args.text),
                _urls_from_file(args.urls_file, args.url),
                args.engine,
                args.depth,
            )
            _print(payload)
            recheck = payload.get("recheck") or {}
            return int(recheck.get("exit_code") or 2)
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
            _print(what_rests_on(args.doi))
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
        if args.cmd == "gate":
            from mooltrace.gate import main as gate_main

            return gate_main()
        if args.cmd == "seed":
            from mooltrace.seed import main as seed_main

            argv_seed = ["--if-empty"] if args.if_empty else []
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
