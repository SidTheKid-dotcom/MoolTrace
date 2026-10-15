from mooltrace.decision import (
    EXIT_BLOCK,
    EXIT_PASS,
    EXIT_WARN,
    NO_SOURCES_SUMMARY,
    PRESHIP_EOC,
    UNVERIFIED_LABEL,
    decide,
)


def _path(notice_type: str, root: str = "10.1/root") -> dict:
    return {
        "hops": 2,
        "source_url": "https://example.com/a",
        "root": {"doi": root, "title": "Root"},
        "notice": {"doi": "10.1/notice", "type": notice_type, "label": notice_type, "date": "2025-08-20"},
        "steps": [],
    }


def test_expression_of_concern_is_warn_not_block():
    verdict = decide([_path("expression_of_concern")], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["summary"] == PRESHIP_EOC
    assert verdict["reasons"][0]["code"] == "expression_of_concern"


def test_retraction_blocks():
    verdict = decide([_path("retraction")], incomplete=False, depth=2)
    assert verdict["decision"] == "block"
    assert verdict["exit_code"] == EXIT_BLOCK


def test_eoc_does_not_outrank_a_retraction():
    verdict = decide(
        [_path("expression_of_concern"), _path("retraction", "10.1/other")],
        incomplete=False,
        depth=2,
    )
    assert verdict["decision"] == "block"


def test_clean_pass():
    verdict = decide([], incomplete=False, depth=2)
    assert verdict["decision"] == "pass"
    assert verdict["exit_code"] == EXIT_PASS
    assert verdict["reasons"] == []


def test_no_sources_is_warn_not_pass():
    verdict = decide([], incomplete=False, depth=2, has_sources=False)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["summary"] == NO_SOURCES_SUMMARY
    assert verdict["reasons"][0]["code"] == "no_sources"
    assert verdict["error_code"] == "no_sources"


def test_incomplete_without_a_notice_warns():
    verdict = decide([], incomplete=True, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "incomplete"


def test_background_retraction_does_not_block():
    path = _path("retraction")
    path.update(
        weight=0.2,
        judged=True,
        reliance="background",
        sentence="Khan A, Safdar M, et al. Cinnamon improves glucose and lipids. Diabetes Care. 2003;26(12):3215.",
        evidence_from="page_list",
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "pass"
    assert verdict["exit_code"] == EXIT_PASS
    assert verdict["reasons"] == []
    assert verdict["discounted"][0]["code"] == "retraction"
    assert verdict["independent_source_count"] == 0


def test_counted_concern_keeps_the_deciding_sentence():
    path = _path("expression_of_concern")
    path.update(
        weight=0.85,
        judged=True,
        reliance="uses_data_or_method",
        sentence="analyzing the results Khan and colleagues 6 as 3 separate comparisons",
        evidence_from="pmc_full_text",
        steps=[
            {"doi": "10.1370/afm.1517", "title": "Allen"},
            {"doi": "10.1/root", "title": "Root"},
        ],
    )
    low = _path("retraction", "10.1/other")
    low.update(weight=0.2, judged=True, sentence="A source list entry.", reliance="background")
    verdict = decide([low, path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["summary"] == PRESHIP_EOC
    assert verdict["reasons"][0]["sentence"].startswith("analyzing the results")
    assert verdict["reasons"][0]["weight"] == 0.85
    assert verdict["independent_source_count"] == 1
    assert verdict["independent_sources"][0]["id"] == "10.1370/afm.1517"


def test_missing_sentence_warns_and_does_not_pass():
    path = _path("expression_of_concern")
    path.update(weight=0.0, judged=True, reliance="unresolved", sentence="", evidence_from="")
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["summary"] == UNVERIFIED_LABEL
    assert verdict["reasons"][0]["code"] == "unverified"
    assert verdict["reasons"][0]["label"] == UNVERIFIED_LABEL
    assert verdict["independent_source_count"] == 0


def test_reference_list_only_is_unverified_not_a_pass():
    path = _path("expression_of_concern")
    path.update(
        weight=0.0,
        judged=True,
        reliance="unverified",
        sentence="Khan A, Safdar M. Cinnamon improves glucose and lipids of people with type 2 diabetes. 2003.",
        evidence_from="europepmc_references",
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["summary"] == UNVERIFIED_LABEL
    assert verdict["reasons"][0]["evidence_from"] == "europepmc_references"
    assert "Khan A" in verdict["reasons"][0]["sentence"]


def test_unverified_does_not_replace_a_counted_concern():
    counted = _path("expression_of_concern")
    counted.update(
        weight=0.85,
        judged=True,
        reliance="uses_data_or_method",
        sentence="analyzing the results Khan and colleagues 6 as 3 separate comparisons",
        evidence_from="pmc_html",
    )
    missing = _path("retraction", "10.1/other")
    missing.update(weight=0.0, judged=True, reliance="unverified", sentence="")
    verdict = decide([missing, counted], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["summary"] == PRESHIP_EOC
    assert verdict["reasons"][0]["code"] == "expression_of_concern"
    assert any(reason["code"] == "unverified" for reason in verdict["reasons"])


def test_unjudged_path_does_not_pass():
    path = _path("retraction")
    path.update(weight=None, judged=None, sentence="")
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "incomplete"


def test_weak_direct_path_does_not_mask_a_counted_longer_path():
    background = _path("expression_of_concern")
    background.update(
        hops=1,
        hops_evidence=[
            {
                "weight": 0.2,
                "judged": True,
                "reliance": "background",
                "sentence": "Khan A, Safdar M. Diabetes Care. 2003;26(12):3215.",
                "evidence_from": "page_list",
            }
        ],
    )
    counted = _path("expression_of_concern")
    counted.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "citing Allen 2013 as a review of cinnamon trials",
                "evidence_from": "page",
            },
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "analyzing the results Khan and colleagues 6 as 3 separate comparisons",
                "evidence_from": "pmc_html",
            },
        ],
        steps=[
            {"doi": None, "url": "https://example.com/page"},
            {"doi": "10.1370/afm.1517", "title": "Allen"},
            {"doi": "10.1/root", "title": "Root"},
        ],
    )
    verdict = decide([background, counted], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["summary"] == PRESHIP_EOC


def test_new_version_is_not_a_path_kind_here():
    # Callers must not pass new_version paths; the ingester drops that type.
    # If one arrives, it is a generic notice warn, not a retraction block.
    verdict = decide([_path("new_version")], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "new_version"
