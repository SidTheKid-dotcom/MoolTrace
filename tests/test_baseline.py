"""No-graph direct-DOI baseline: Crossref notices on DOIs literally in the draft."""

from __future__ import annotations

import pytest

KHAN = "10.2337/diacare.26.12.3215"
EOC = "10.2337/dc25-ec09"
ALLEN = "10.1370/afm.1517"
LANCET = "10.1016/s0140-6736(20)31180-6"
LANCET_NOTICE = "10.1016/s0140-6736(20)31324-6"
HEALTHLINE = "https://www.healthline.com/nutrition/cinnamon-and-diabetes"

KHAN_MESSAGE = {
    "DOI": KHAN,
    "title": ["Cinnamon Improves Glucose and Lipids of People With Type 2 Diabetes"],
    "updated-by": [
        {
            "DOI": EOC,
            "type": "expression_of_concern",
            "label": "Expression of concern",
            "source": "publisher",
            "updated": {"date-time": "2025-08-20T00:00:00Z", "date-parts": [[2025, 8, 20]]},
        }
    ],
}
LANCET_MESSAGE = {
    "DOI": LANCET,
    "title": ["RETRACTED: Hydroxychloroquine or chloroquine"],
    "updated-by": [
        {
            "DOI": "10.1016/s0140-6736(20)31290-3",
            "type": "expression_of_concern",
            "label": "Expression of concern",
            "source": "retraction-watch",
            "updated": {"date-time": "2020-06-03T00:00:00Z"},
        },
        {
            "DOI": LANCET_NOTICE,
            "type": "retraction",
            "label": "Retraction",
            "source": "retraction-watch",
            "updated": {"date-time": "2020-06-05T00:00:00Z"},
        },
        {
            "DOI": "10.1016/s0140-6736(20)31249-6",
            "type": "correction",
            "label": "Correction",
            "source": "retraction-watch",
        },
    ],
}
ALLEN_MESSAGE = {
    "DOI": ALLEN,
    "title": ["Cinnamon Use in Type 2 Diabetes"],
    "updated-by": [],
}


def _lookup(doi: str):
    catalog = {
        KHAN: KHAN_MESSAGE,
        LANCET: LANCET_MESSAGE,
        ALLEN: ALLEN_MESSAGE,
    }
    return catalog.get(doi)


def test_baseline_warns_on_literal_khan_eoc():
    from mooltrace.baseline import check_direct_doi

    payload = check_direct_doi(
        f"A draft cites Khan 2003, DOI {KHAN}.",
        [],
        lookup=_lookup,
    )
    assert payload["decision"] == "warn"
    assert payload["exit_code"] == 2
    assert payload["graph"] is False
    assert payload["reasons"][0]["notice_doi"] == EOC
    assert payload["reasons"][0]["code"] == "expression_of_concern"
    assert payload["reasons"][0]["hops"] == 1
    assert "Expression of Concern" in payload["summary"]
    assert "retract" not in payload["summary"].lower()


def test_baseline_blocks_on_literal_lancet_retraction():
    from mooltrace.baseline import check_direct_doi

    payload = check_direct_doi(LANCET, [], lookup=_lookup)
    assert payload["decision"] == "block"
    assert payload["exit_code"] == 1
    assert payload["reasons"][0]["code"] == "retraction"
    assert payload["reasons"][0]["notice_doi"] == LANCET_NOTICE


def test_baseline_passes_allen_because_allen_has_no_own_notice():
    from mooltrace.baseline import check_direct_doi

    payload = check_direct_doi(
        f"A draft cites Allen 2013, DOI {ALLEN}.",
        [],
        lookup=_lookup,
    )
    assert payload["decision"] == "pass"
    assert payload["exit_code"] == 0
    assert payload["dois"] == [ALLEN]
    assert payload["reasons"] == []


def test_baseline_does_not_fetch_pages_or_walk_a_graph(monkeypatch):
    from mooltrace.baseline import check_direct_doi

    def boom(*_a, **_k):
        raise AssertionError("direct-DOI baseline must not fetch pages or catalogs beyond Crossref lookup")

    monkeypatch.setattr("mooltrace.clients.fetch_page", boom)
    monkeypatch.setattr("mooltrace.clients.openalex_work_doi", boom)
    monkeypatch.setattr("mooltrace.trace.check_answer", boom)
    looked: list[str] = []

    def lookup(doi: str):
        looked.append(doi)
        return _lookup(doi)

    payload = check_direct_doi("", [HEALTHLINE], lookup=lookup)
    assert payload["decision"] == "pass"
    assert payload["dois"] == []
    assert looked == []
    assert payload["graph"] is False


def test_baseline_catches_doi_org_url_but_not_consumer_html():
    from mooltrace.baseline import check_direct_doi

    encoded = check_direct_doi(
        "A draft cites a Diabetes Care trial.",
        ["https://doi.org/10.2337%2Fdiacare.26.12.3215"],
        lookup=_lookup,
    )
    assert encoded["decision"] == "warn"
    assert encoded["dois"] == [KHAN]

    page = check_direct_doi("", [HEALTHLINE], lookup=_lookup)
    assert page["decision"] == "pass"


def test_baseline_eval_lists_only_multihop_catches():
    from mooltrace.baseline import run_baseline_eval

    report = run_baseline_eval(lookup=_lookup)
    ids = {row["id"] for row in report["only_multihop_catches"]}
    assert "eoc-allen-2013" in ids
    assert "page-healthline-cinnamon" in ids
    assert "eoc-everyday-health-url" in ids
    assert "i18n-hi-healthline" in ids
    assert "eoc-khan-direct" not in ids
    assert "retract-lancet-draft" not in ids
    assert "ident-fake-doi" not in ids
    assert "nosrc-cinnamon-prose" not in ids
    metrics = report["baseline"]["metrics"]
    assert metrics["fp"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] is not None
    assert metrics["recall"] < 1.0
    assert report["n"] == 52


def test_recorded_catalog_eval_marks_deyno_as_multihop():
    from mooltrace.baseline import run_baseline_eval

    report = run_baseline_eval()
    ids = set(report["only_multihop_ids"])
    assert "eoc-deyno-2019" in ids
    assert "eoc-cochrane-2012" in ids
    assert "ident-fake-doi" not in ids
    assert report["baseline"]["metrics"]["n"] == 52
    assert report["baseline"]["metrics"]["fp"] == 0
    assert report["checker"]["graph"] is False


def test_recorded_catalog_covers_every_literal_labelled_doi():
    from mooltrace.baseline import DEFAULT_CROSSREF, load_crossref_catalog, literal_dois
    from mooltrace.labelled import load_labelled

    catalog = load_crossref_catalog()
    works = catalog["works"]
    missing = []
    for row in load_labelled():
        for doi in literal_dois(str(row.get("text") or ""), list(row.get("urls") or [])):
            if doi not in works:
                missing.append((row["id"], doi))
    assert missing == []
    assert catalog["fetched_at"].startswith("2026-10-16")
    assert DEFAULT_CROSSREF.name == "baseline_crossref.json"
    khan = works["10.2337/diacare.26.12.3215"]["message"]["updated-by"]
    assert any(item.get("type") == "expression_of_concern" for item in khan)


def test_recorded_mooltrace_snapshot_reproduces_metrics():
    from mooltrace.baseline import DEFAULT_MOOLTRACE, run_baseline_eval
    import json

    assert DEFAULT_MOOLTRACE.is_file()
    snapshot = json.loads(DEFAULT_MOOLTRACE.read_text(encoding="utf-8"))
    report = run_baseline_eval(mooltrace_report=snapshot)
    mt = report["mooltrace"]["metrics"]
    assert mt["n"] == 52
    assert mt["scored"] == 52
    assert mt["infra"] == 0
    assert mt["precision"] == 0.8974
    assert mt["recall"] == 1.0
    assert mt["tp"] == 35
    assert mt["fp"] == 4
    assert mt["fn"] == 0
    assert {row["id"] for row in report["labelled_disagreements"]} == {
        "page-nccih-cinnamon",
        "page-webmd-cinnamon-guide",
        "page-mnt-cinnamon-diabetes",
        "ident-mdpi-pdf-foods",
    }
    assert report["verdict_changes_vs_labelled_2026-10-15"] == []
    assert len(report["only_multihop_catches"]) == 15
    assert report["baseline"]["metrics"]["precision"] == 1.0
    assert report["baseline"]["metrics"]["recall"] == 0.4286


def test_baseline_results_md_quotes_recorded_metrics():
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parents[1]
    md = (root / "results" / "baseline_2026-10-16.md").read_text(encoding="utf-8")
    report = json.loads((root / "results" / "baseline_2026-10-16.json").read_text(encoding="utf-8"))
    assert str(report["baseline"]["metrics"]["recall"]) in md
    assert str(report["mooltrace"]["metrics"]["precision"]) in md
    assert ".venv/bin/python -m mooltrace baseline" in md
    assert "eoc-allen-2013" in md
    assert "page-healthline-cinnamon" in md
    assert "Expression of Concern" in md


def test_cli_baseline_help_documents_no_graph(capsys):
    from mooltrace.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["baseline", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    assert "direct-doi" in help_text or "no-graph" in help_text
    assert "crossref" in help_text
