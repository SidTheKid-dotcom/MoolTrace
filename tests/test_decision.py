from mooltrace.decision import (
    EXIT_BLOCK,
    EXIT_PASS,
    EXIT_WARN,
    NO_SOURCES_SUMMARY,
    PRESHIP_EOC,
    UNVERIFIED_LABEL,
    _reason_rank,
    decide,
)
from mooltrace.reliance import PATH_RULE, WEIGHTS


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
    assert verdict["decided_by"] == "algo.SPpaths"


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


def test_mention_only_multi_hop_still_warns():
    path = _path("expression_of_concern")
    path.update(
        hops=3,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "The draft cites W1 as the first hop.",
                "evidence_from": "page",
            },
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "W1 mentions W2 in passing.",
                "evidence_from": "page",
            },
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "W2 mentions the flagged study.",
                "evidence_from": "page",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=3)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["reasons"][0]["code"] == "expression_of_concern"
    assert verdict["discounted"] == []
    assert verdict["path_rule"] == PATH_RULE
    assert "path_score_floor" not in verdict or verdict.get("path_score_floor") is None
    assert "strength_floor" not in verdict or verdict.get("strength_floor") is None


def test_two_hop_mention_only_still_warns():
    path = _path("expression_of_concern")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "This draft cites the review by DOI.",
                "evidence_from": "draft",
            },
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "The review names Abd-Elsalam 2020 in passing.",
                "evidence_from": "semantic_scholar",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "expression_of_concern"
    assert verdict["discounted"] == []


def test_mention_then_included_counts():
    path = _path("retraction")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "This health-information draft cites a single systematic review.",
                "evidence_from": "draft",
            },
            {
                "weight": 1.0,
                "judged": True,
                "reliance": "included",
                "sentence": "Listed among included studies (Table 1: Demographic data of the retained studies)",
                "evidence_from": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12510581/",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "block"
    assert verdict["reasons"][0]["reliance"] == "included"
    assert verdict["reasons"][0]["sentence"].startswith("Listed among included studies")
    assert verdict["path_rule"] == PATH_RULE


def test_three_hop_strong_path_counts_when_product_meets_floor():
    path = _path("expression_of_concern")
    path.update(
        hops=3,
        hops_evidence=[
            {
                "weight": WEIGHTS["included"],
                "judged": True,
                "reliance": "included",
                "sentence": "Listed among included studies (Table 1: Characteristics of included studies)",
                "evidence_from": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
            },
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "The page cites Allen as the review.",
                "evidence_from": "page",
            },
            {
                "weight": 1.0,
                "judged": True,
                "reliance": "relies",
                "sentence": "Khan and colleagues found that cinnamon reduced fasting glucose.",
                "evidence_from": "pmc_html",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=3)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "expression_of_concern"
    assert verdict["path_rule"] == PATH_RULE


def test_direct_mention_of_the_flagged_study_still_counts():
    path = _path("retraction")
    path.update(
        hops=1,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "A draft cites Mehra 2020, DOI 10.1016/s0140-6736(20)31180-6.",
                "evidence_from": "draft",
            }
        ],
    )
    verdict = decide([path], incomplete=False, depth=1)
    assert verdict["decision"] == "block"


def test_strong_two_hop_still_counts():
    path = _path("expression_of_concern")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "The page cites Allen as the review.",
                "evidence_from": "page",
            },
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "analyzing the results Khan and colleagues 6",
                "evidence_from": "pmc_html",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["path_score"] == 0.85 * 0.85
    assert verdict["decided_by"] == "algo.SPpaths"


def test_allen_2013_eoc_chain_warns_when_product_is_under_half():
    """Allen 2013 → Khan EoC: mention 0.55 × uses 0.85 = 0.4675.

    A multiplied 0.5 floor treats that product as in-passing and passes.
    A confirmed Expression of Concern on a counted chain must at least warn.
    """
    path = _path("expression_of_concern")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": (
                    "The review this draft relies on is Allen 2013 "
                    "(doi 10.1370/afm.1517)."
                ),
                "evidence_from": "draft",
            },
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": (
                    "Our results suggested a high likelihood for publication "
                    "bias on fasting plasma glucose, perhaps as a result of "
                    "analyzing the results Khan and colleagues 6 as 3 "
                    "separate comparisons."
                ),
                "evidence_from": "pmc_html",
            },
        ],
        steps=[
            {"doi": None, "url": "urn:mooltrace:paste:allen"},
            {"doi": "10.1370/afm.1517", "title": "Allen"},
            {"doi": "10.2337/diacare.26.12.3215", "title": "Khan"},
        ],
        root={"doi": "10.2337/diacare.26.12.3215", "title": "Khan"},
        notice={
            "doi": "10.2337/dc25-ec09",
            "type": "expression_of_concern",
            "label": "Expression of concern",
            "date": "2025-08-20",
        },
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN
    assert verdict["summary"] == PRESHIP_EOC
    assert verdict["reasons"][0]["code"] == "expression_of_concern"
    assert abs(verdict["reasons"][0]["path_score"] - 0.55 * 0.85) < 1e-12
    assert verdict["reasons"][0]["status"] == "count"
    assert verdict["discounted"] == []


def test_counted_retraction_chain_blocks_when_product_is_under_half():
    path = _path("retraction")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.55,
                "judged": True,
                "reliance": "mention",
                "sentence": "This draft cites the review by DOI.",
                "evidence_from": "draft",
            },
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "The review analyses the retracted trial.",
                "evidence_from": "pmc_html",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "block"
    assert verdict["exit_code"] == EXIT_BLOCK
    assert verdict["reasons"][0]["code"] == "retraction"
    assert abs(verdict["reasons"][0]["path_score"] - 0.55 * 0.85) < 1e-12


def test_strength_below_floor_passes_as_in_passing():
    path = _path("expression_of_concern")
    path.update(
        hops=2,
        hops_evidence=[
            {
                "weight": 0.85,
                "judged": True,
                "reliance": "uses_data_or_method",
                "sentence": "The page cites the review.",
                "evidence_from": "page",
            },
            {
                "weight": 0.2,
                "judged": True,
                "reliance": "background",
                "sentence": "Khan is listed in the bibliography.",
                "evidence_from": "pmc_html",
            },
        ],
    )
    verdict = decide([path], incomplete=False, depth=2)
    assert verdict["decision"] == "pass"
    assert verdict["discounted"]
    assert "cites a flagged study only in passing" in verdict["summary"]


def test_sp_cost_picks_the_deciding_notice():
    low = _path("expression_of_concern", "10.1/low")
    low.update(
        weight=0.85,
        judged=True,
        reliance="uses_data_or_method",
        sentence="low centrality flagged study",
        hops=1,
    )
    high = _path("expression_of_concern", "10.1/high")
    high.update(
        weight=0.85,
        judged=True,
        reliance="uses_data_or_method",
        sentence="high centrality flagged study",
        hops=1,
    )
    verdict = decide(
        [low, high],
        incomplete=False,
        depth=2,
        sp_cost={"10.1/high": 0.01, "10.1/low": 2.0},
    )
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["root_doi"] == "10.1/high"
    assert verdict["reasons"][0]["sp_cost"] == 0.01


def test_rank_is_counted_then_unverified_then_discounted():
    counted = _path("retraction")
    counted.update(
        weight=0.9,
        judged=True,
        reliance="included",
        sentence="the trial is included in this review",
        hops=2,
    )
    unverified = _path("expression_of_concern", "10.2/u")
    unverified.update(
        weight=0.0,
        judged=True,
        reliance="unverified",
        sentence="",
        hops=1,
    )
    discounted = _path("retraction", "10.3/d")
    discounted.update(
        weight=0.2,
        judged=True,
        reliance="background",
        sentence="Khan A, Safdar M. Diabetes Care. 2003;26(12):3215.",
        hops=1,
    )
    verdict = decide(
        [discounted, unverified, counted],
        incomplete=False,
        depth=2,
    )
    assert verdict["decision"] == "block"
    assert verdict["reasons"][0]["status"] == "count"
    assert verdict["reasons"][0]["code"] == "retraction"
    assert any(reason.get("status") == "unverified" for reason in verdict["reasons"])
    counted_pos = next(
        i for i, reason in enumerate(verdict["reasons"]) if reason.get("status") == "count"
    )
    unverified_pos = next(
        i for i, reason in enumerate(verdict["reasons"]) if reason.get("status") == "unverified"
    )
    assert counted_pos < unverified_pos
    combined = list(verdict["reasons"]) + list(verdict["discounted"])
    combined.sort(key=_reason_rank)
    statuses = [item.get("status") for item in combined]
    assert statuses == sorted(statuses, key=lambda s: {"count": 0, "unverified": 1, "discount": 2}.get(s, 9))
    assert statuses[0] == "count"
    assert "unverified" in statuses
    assert statuses[-1] == "discount"


def test_new_version_is_not_a_path_kind_here():
    # Callers must not pass new_version paths; the ingester drops that type.
    # If one arrives, it is a generic notice warn, not a retraction block.
    verdict = decide([_path("new_version")], incomplete=False, depth=2)
    assert verdict["decision"] == "warn"
    assert verdict["reasons"][0]["code"] == "new_version"
