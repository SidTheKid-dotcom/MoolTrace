from pathlib import Path

from mooltrace.gate import CLEAN
from mooltrace.ids import extract_identifiers, has_verifiable_source
from mooltrace.labelled import (
    DEFAULT_FILE,
    FAMILIES,
    compute_metrics,
    load_labelled,
)


ROOT = Path(__file__).resolve().parents[1]


def test_labelled_file_schema_and_balance():
    rows = load_labelled()
    assert Path(DEFAULT_FILE).resolve() == (ROOT / "examples" / "labelled.jsonl").resolve()
    assert len(rows) == 52
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    families = {row["family"] for row in rows}
    assert families == set(FAMILIES)
    counts = {family: sum(1 for row in rows if row["family"] == family) for family in FAMILIES}
    assert counts["eoc"] == 8
    assert counts["retraction"] == 4
    assert counts["hedged"] == 6
    assert counts["clean"] == 6
    assert counts["no_sources"] == 4
    assert counts["depth"] == 3
    assert counts["page"] == 8
    assert counts["identifier"] == 9
    assert counts["i18n"] == 4
    for row in rows:
        assert row["expected"] in {"pass", "warn", "block"}
        assert isinstance(row.get("urls"), list)
        assert int(row["depth"]) in {1, 2, 3}


def test_labelled_clean_matches_gate_and_expects_pass():
    rows = [row for row in load_labelled() if row["family"] == "clean"]
    dois = []
    for row in rows:
        assert row["expected"] == "pass"
        found = extract_identifiers(row["text"]).dois
        assert len(found) == 1
        dois.append(found[0])
        assert not row["urls"]
    assert set(dois) == set(CLEAN)


def test_labelled_hedges_keep_the_flagged_citation():
    rows = [row for row in load_labelled() if row["family"] == "hedged"]
    assert rows
    for row in rows:
        text = row["text"].lower()
        assert (
            "expression of concern" in text
            or "we excluded" in text
            or "retracted" in text
        )
        assert has_verifiable_source(row["text"], row["urls"])
        if "lancet" in row["id"]:
            assert row["expected"] == "block"
        else:
            assert row["expected"] == "warn"


def test_labelled_no_sources_have_no_identifiers():
    for row in load_labelled():
        if row["family"] != "no_sources":
            continue
        assert row["expected"] == "warn"
        assert not has_verifiable_source(row["text"], row["urls"])
        found = extract_identifiers(row["text"])
        assert found.dois == []
        assert found.pmids == []
        assert found.pmcids == []
        assert found.urls == []


def test_labelled_depth_cases_do_not_expand():
    rows = [row for row in load_labelled() if row["family"] == "depth"]
    assert len(rows) == 3
    for row in rows:
        assert int(row["depth"]) == 1
        assert row["expected"] == "pass"
        assert extract_identifiers(row["text"]).dois


def test_labelled_positives_and_retractions():
    rows = load_labelled()
    eoc = [row for row in rows if row["family"] == "eoc"]
    retract = [row for row in rows if row["family"] == "retraction"]
    assert all(row["expected"] == "warn" for row in eoc)
    assert all(row["expected"] == "block" for row in retract)
    assert any("everydayhealth.com/diabetes/cinnamon-for-diabetes" in (row["urls"] or [""])[0] for row in eoc)
    assert any("10.1016/s0140-6736(20)31180-6" in row["text"].lower() or any(
        "10.1016/s0140-6736(20)31180-6" in url.lower() for url in row["urls"]
    ) for row in retract)


def test_compute_metrics_binary_and_timing():
    rows = [
        {
            "family": "eoc",
            "expected_flagged": True,
            "predicted_flagged": True,
            "match": True,
            "scored": True,
            "infra": False,
            "wall_ms": 10,
            "query_ms": 2,
        },
        {
            "family": "clean",
            "expected_flagged": False,
            "predicted_flagged": True,
            "match": False,
            "scored": True,
            "infra": False,
            "wall_ms": 20,
            "query_ms": 4,
        },
        {
            "family": "retraction",
            "expected_flagged": True,
            "predicted_flagged": False,
            "match": False,
            "scored": True,
            "infra": False,
            "wall_ms": 30,
            "query_ms": 6,
        },
        {
            "family": "eoc",
            "expected_flagged": True,
            "predicted_flagged": False,
            "match": False,
            "scored": False,
            "infra": True,
            "wall_ms": 40,
            "query_ms": 0,
        },
    ]
    metrics = compute_metrics(rows)
    assert metrics["n"] == 4
    assert metrics["scored"] == 3
    assert metrics["infra"] == 1
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["tn"] == 0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["exact_match"] == 1
    assert metrics["timing"]["mean_wall_ms"] == 25.0
    assert metrics["by_family"]["eoc"]["n"] == 1
    assert metrics["by_family"]["clean"]["precision"] == 0.0
