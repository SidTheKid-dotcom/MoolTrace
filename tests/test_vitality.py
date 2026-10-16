"""VITALITY Study I sealed eval: same-trial recall vs a no-graph baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


HERNANDEZ = "10.3390/jcm10112503"
ABD = "10.4269/ajtmh.20-0873"
ABD_NOTICE = "10.4269/ajtmh.1073ret"
LIU = "10.1111/jog.12393"
BADAWY = "10.1016/j.fertnstert.2008.06.013"
LIU_NOTICE = "10.1016/j.fertnstert.2020.08.1409"
CTRL = "10.1111/jog.12333"


def test_cli_vitality_help_documents_sealed_eval(capsys):
    from mooltrace.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["vitality", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    assert "vitality" in help_text
    assert "openalex" in help_text or "429" in help_text
    assert "direct-doi" in help_text or "no-graph" in help_text


def test_frozen_set_is_capped_and_states_the_control_check():
    from mooltrace.vitality import DEFAULT_FROZEN, load_frozen

    frozen = load_frozen()
    positives = frozen["positives"]
    controls = frozen["controls"]
    assert DEFAULT_FROZEN.name == "vitality.json"
    assert 1 <= len(positives) <= 40
    assert 1 <= len(controls) <= len(positives)
    assert frozen["control_check"]
    assert "osf" in frozen["control_check"].lower()
    assert "retracted" in frozen["control_check"].lower()
    dois = [row["doi"] for row in positives] + [row["doi"] for row in controls]
    assert len(dois) == len(set(dois))
    sampled = [row for row in positives if row.get("sampled")]
    assert len(sampled) == 15
    assert all(not row.get("review_is_retracted") for row in positives)
    assert any(row["doi"] == HERNANDEZ for row in positives)
    assert any(row["doi"] == CTRL for row in controls)
    carlisle = "10.1002/14651858.cd004125.pub2"
    assert carlisle not in dois


def test_same_trial_matches_vitality_doi_or_stored_notice():
    from mooltrace.vitality import same_trial

    counted = {
        "reasons": [
            {
                "code": "retraction",
                "root_doi": ABD,
                "notice_doi": ABD_NOTICE,
                "steps": [{"doi": HERNANDEZ}, {"doi": ABD}],
            }
        ],
        "errors": [],
    }
    hit = same_trial(counted, [ABD])
    assert hit["same_trial"] is True
    assert ABD in hit["matched_as_root"]

    notice_as_trial = {
        "reasons": [
            {
                "code": "unverified",
                "root_doi": BADAWY,
                "notice_doi": LIU_NOTICE,
                "steps": [{"doi": LIU}, {"doi": BADAWY}],
            }
        ],
        "errors": [],
    }
    via_notice = same_trial(notice_as_trial, [LIU_NOTICE])
    assert via_notice["same_trial"] is True
    assert LIU_NOTICE in via_notice["matched_as_notice"]


def test_openalex_429_warn_is_not_same_trial_recall():
    from mooltrace.vitality import classify_run, same_trial

    unfinished = {
        "decision": "warn",
        "exit_code": 2,
        "reasons": [{"code": "incomplete", "root_doi": None, "notice_doi": None, "steps": []}],
        "errors": [
            "10.1371/journal.pone.0248132: giving up on api.openalex.org: 429 from api.openalex.org"
        ],
        "incomplete": True,
    }
    hit = same_trial(unfinished, ["10.4269/ajtmh.20-0873"])
    assert hit["same_trial"] is False
    row = classify_run(unfinished, ["10.4269/ajtmh.20-0873"])
    assert row["finished_expansion"] is False
    assert row["same_trial"] is False
    assert row["product_flagged"] is True
    assert row["counted_notice"] is False
    assert row["miss_reason"] == "openalex_429"


def test_offline_vitality_scores_recorded_fixtures(tmp_path, capsys):
    from mooltrace.vitality import run_vitality_eval

    catalog = {
        "kind": "direct_doi_crossref_catalog",
        "fetched_at": "2026-10-17T00:00:00+00:00",
        "works": {
            HERNANDEZ: {
                "status": 200,
                "message": {"DOI": HERNANDEZ, "title": ["HCQ"], "updated-by": []},
            },
            CTRL: {
                "status": 200,
                "message": {"DOI": CTRL, "title": ["control"], "updated-by": []},
            },
        },
    }
    frozen = {
        "product": "MoolTrace",
        "kind": "vitality_frozen_set",
        "paper": "Xu et al. BMJ 2025",
        "control_check": "Same journal/year; not in OSF All-sheet; OpenAlex is_retracted=false; no retracted referenced_works in the first 80.",
        "draft_template": "This health-information draft cites a single systematic review (DOI {doi}) and no other papers. It is not medical advice.",
        "positives": [
            {
                "id": "pos-ref-35",
                "kind": "positive",
                "doi": HERNANDEZ,
                "sampled": True,
                "review_is_retracted": False,
                "retracted_trials": [{"doi": ABD}],
            }
        ],
        "controls": [
            {
                "id": "ctrl-02",
                "kind": "control",
                "doi": CTRL,
                "in_vitality_all_sheet": False,
                "openalex_is_retracted": False,
            }
        ],
    }
    snapshot = {
        "kind": "vitality_mooltrace_snapshot",
        "depth": 2,
        "cases": {
            "pos-ref-35": {
                "id": "pos-ref-35",
                "decision": "block",
                "exit_code": 1,
                "incomplete": False,
                "errors": [],
                "reasons": [
                    {
                        "code": "retraction",
                        "root_doi": ABD,
                        "notice_doi": ABD_NOTICE,
                        "hops": 2,
                        "path_score": 0.3025,
                        "steps": [{"doi": HERNANDEZ}, {"doi": ABD}],
                    }
                ],
                "summary": "retraction path",
                "wall_ms": 12.0,
                "api_calls": 4,
            },
            "ctrl-02": {
                "id": "ctrl-02",
                "decision": "pass",
                "exit_code": 0,
                "incomplete": False,
                "errors": [],
                "reasons": [],
                "summary": "no notice",
                "wall_ms": 8.0,
                "api_calls": 2,
            },
        },
    }
    frozen_path = tmp_path / "frozen.json"
    catalog_path = tmp_path / "crossref.json"
    snap_path = tmp_path / "mooltrace.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")

    report = run_vitality_eval(
        frozen_path=frozen_path,
        catalog_path=catalog_path,
        snapshot_path=snap_path,
    )
    mt = report["mooltrace"]["metrics"]
    base = report["baseline"]["metrics"]
    assert base["positives_flagged"] == "0/1"
    assert base["controls_flagged"] == "0/1"
    assert mt["same_trial_recall_finished"] == "1/1"
    assert mt["false_alarms_finished"] == "0/1"
    assert mt["openalex_429_positives"] == 0
    assert report["never_relabelled"] is True
