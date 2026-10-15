"""Seeded regression against live OpenAlex and Crossref.

This is not an accuracy score. Each fixture runs on its own throwaway
graph at DEFAULT_DEPTH. warn/block on a clean fixture is an alarm.
The configured MOOLTRACE_DB file is never deleted.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from mooltrace import config
from mooltrace.clients import close_client
from mooltrace.graph import Graph
from mooltrace.trace import check_answer, check_study, what_rests_on

KHAN = config.KHAN_DOI
EOC = config.EOC_DOI
LANCET = config.LANCET_HCQ_DOI
LANCET_RETRACTION = config.LANCET_RETRACTION_DOI
LANCET_DRAFT = (
    "A draft patient note says a 2020 Lancet registry analysis by Mehra and colleagues "
    "reported outcomes for hydroxychloroquine. "
    "DOI 10.1016/S0140-6736(20)31180-6. "
    "This note is not a recommendation to start or stop a medicine."
)

POSITIVES = [
    {
        "n": 1,
        "name": "Everyday Health cinnamon page (URL only)",
        "urls": [config.EVERYDAY_HEALTH_URL],
        "engine": "nutrition-coach",
        "hero": True,
    },
    {
        "n": 2,
        "name": "Allen 2013",
        "text": "10.1370/afm.1517",
        "engine": "allen-2013",
    },
    {
        "n": 3,
        "name": "Deyno 2019",
        "text": "10.1016/j.diabres.2019.107815",
        "engine": "deyno-2019",
    },
    {
        "n": 4,
        "name": "Complementary Therapies in Medicine 2020",
        "text": "10.1016/j.ctim.2020.102571",
        "engine": "ctim-2020",
    },
    {
        "n": 5,
        "name": "Moridpour 2023",
        "text": "10.1002/ptr.8026",
        "engine": "moridpour-2023",
    },
    {
        "n": 6,
        "name": "Cochrane 2012 CD007170.pub2",
        "text": "10.1002/14651858.CD007170.pub2",
        "engine": "cochrane-2012",
    },
    {
        "n": 7,
        "name": "Lancet 2020 hydroxychloroquine registry",
        "text": LANCET_DRAFT,
        "engine": "patient-chatbot",
        "expect_retraction": True,
    },
]

# Works with no Crossref retraction / withdrawal / removal / EoC on the
# work itself and no flagged ancestor within DEFAULT_DEPTH on an isolated
# graph (live check 15 Oct 2026). Dropped from an earlier neighborhood
# list: 10.5114/amsad/184245 (counted path to a retracted rat study),
# 10.1093/jn/136.4.977 (cites Khan 2003), and
# 10.2174/1389557523666230725113446 (cites retracted papers). Those are
# true signals, not clean negatives. This is not a random sample.
CLEAN = [
    "10.1016/j.jsps.2015.03.013",
    "10.14252/foodsafetyfscj.d-21-00015",
    "10.3390/foods12030452",
    "10.1136/bmj.327.7414.557",
    "10.1016/0197-2456(86)90046-2",
    "10.1136/bmj.d5928",
]


def _fresh_graph() -> Graph:
    return Graph(Path(tempfile.mkdtemp(prefix="mooltrace-gate-")) / "mooltrace.db")


def _reaches_khan(payload: dict) -> dict | None:
    for path in payload.get("paths") or []:
        root = (path.get("root") or {}).get("doi")
        notice = (path.get("notice") or {}).get("doi")
        if root == KHAN and notice == EOC:
            return path
    return None


def _run_case(claim: dict) -> dict:
    graph = _fresh_graph()
    t0 = time.perf_counter()
    try:
        payload = check_answer(
            text=claim.get("text", ""),
            urls=claim.get("urls"),
            engine=claim["engine"],
            depth=config.DEFAULT_DEPTH,
            graph=graph,
        )
        hit = None if claim.get("expect_retraction") else _reaches_khan(payload)
        wall_ms = round((time.perf_counter() - t0) * 1000, 1)
        warm = check_answer(
            text=claim.get("text", ""),
            urls=claim.get("urls"),
            engine=claim["engine"],
            depth=config.DEFAULT_DEPTH,
            graph=graph,
        )
        reverse = None
        if hit or claim.get("expect_retraction"):
            doi = LANCET_RETRACTION if claim.get("expect_retraction") else EOC
            reverse = what_rests_on(doi, graph=graph)
        clusters = payload.get("remediation_clusters") or {}
        return {
            "n": claim["n"],
            "name": claim["name"],
            "engine": claim["engine"],
            "caught": bool(hit) or (
                claim.get("expect_retraction") and payload.get("decision") == "block"
            ),
            "decision": payload.get("decision"),
            "exit_code": payload.get("exit_code"),
            "hops": None if hit is None else hit.get("hops"),
            "api_calls": payload.get("api_calls"),
            "warm_api_calls": warm.get("api_calls"),
            "cache_hits": payload.get("cache_hits"),
            "query_ms": payload.get("elapsed_ms"),
            "wall_ms": wall_ms,
            "errors": (payload.get("errors") or [])[:6],
            "incomplete": payload.get("incomplete"),
            "cypher": payload.get("cypher"),
            "clusters": len(clusters.get("clusters") or []),
            "wcc_call": clusters.get("call"),
            "reverse_notices": len((reverse or {}).get("notices") or []),
            "sentence": (hit or {}).get("sentence") or None,
            "reliance": (hit or {}).get("reliance"),
            "weight": (hit or {}).get("weight"),
            "network_ok": payload.get("exit_code") != 3,
        }
    finally:
        graph.close()


def run_gate() -> dict:
    started = time.perf_counter()
    print("MoolTrace seeded regression (not accuracy)", file=sys.stderr, flush=True)
    positive_rows = []
    for claim in POSITIVES:
        print(f"  case {claim['n']}: {claim['name']}", file=sys.stderr, flush=True)
        row = _run_case(claim)
        positive_rows.append(row)
        print(
            f"    caught={row['caught']} decision={row['decision']} "
            f"api={row['api_calls']} warm_api={row['warm_api_calls']} "
            f"query_ms={row['query_ms']}",
            file=sys.stderr,
            flush=True,
        )

    clean_rows = []
    alarms = 0
    print("  clean works", file=sys.stderr, flush=True)
    for doi in CLEAN:
        graph = _fresh_graph()
        try:
            study = check_study(doi, graph=graph)
            draft = check_answer(
                text=doi,
                engine=f"clean-{doi[-8:]}",
                depth=config.DEFAULT_DEPTH,
                graph=graph,
            )
        finally:
            graph.close()
        alarm = draft.get("decision") in {"warn", "block"} or draft.get("exit_code") in {1, 2, 3}
        if alarm:
            alarms += 1
        clean_rows.append(
            {
                "doi": doi,
                "flagged": study.get("flagged"),
                "decision": draft.get("decision"),
                "alarm": alarm,
                "notices": study.get("notices"),
                "reasons": [
                    {
                        "code": reason.get("code"),
                        "root_doi": reason.get("root_doi"),
                        "notice_doi": reason.get("notice_doi"),
                        "notice_type": reason.get("notice_type"),
                    }
                    for reason in (draft.get("reasons") or [])[:4]
                ],
                "api_calls": (study.get("api_calls") or 0) + (draft.get("api_calls") or 0),
            }
        )
        print(
            f"    {doi} flagged={study.get('flagged')} decision={draft.get('decision')}",
            file=sys.stderr,
            flush=True,
        )

    caught = sum(1 for row in positive_rows if row["caught"])
    report = {
        "product": "MoolTrace",
        "kind": "seeded_regression",
        "ran_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "khan_doi": KHAN,
        "eoc_doi": EOC,
        "depth": config.DEFAULT_DEPTH,
        "selection": (
            "Clean DOIs had no Crossref retraction/withdrawal/removal/EoC on "
            "the work itself and no flagged ancestor within default depth 2 "
            "on an isolated graph as of 15 Oct 2026. They are not a random "
            "sample. Cleveland Clinic is not fetched."
        ),
        "gate": {
            "caught": caught,
            "positives": len(POSITIVES),
            "alarms": alarms,
            "clean": len(CLEAN),
            "rule": (
                "Seeded regression, not accuracy. caught = flagged ancestor "
                "found on a positive fixture. alarm = warn/review/block on a "
                "clean fixture at the same default depth."
            ),
        },
        "positives": positive_rows,
        "clean": clean_rows,
        "wall_s": round(time.perf_counter() - started, 1),
    }
    return report


def main() -> int:
    if Path(config.DB_PATH).exists():
        print(f"leaving configured DB untouched: {config.DB_PATH}", file=sys.stderr, flush=True)
    report = run_gate()
    close_client()
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    gate = report["gate"]
    print(
        f"REGRESSION caught {gate['caught']}/{gate['positives']} "
        f"alarms {gate['alarms']}/{gate['clean']} wall_s={report['wall_s']}",
        file=sys.stderr,
        flush=True,
    )
    if any(not row.get("network_ok", True) for row in report["positives"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
