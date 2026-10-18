"""Cochrane withdrawals, chain disclosures, agent claim softening, explored graph per depth."""

from mooltrace.decision import _cochrane_reason
from mooltrace.ids import cochrane_withdrawal, is_disclosure_only
from mooltrace.rewrite import UNSUPPORTED_NOTE, template_rewrite

ZINC_URL = "https://nutritionsource.hsph.harvard.edu/zinc/"
VITD_URL = "https://nutritionsource.hsph.harvard.edu/vitamin-d/"


def _payload(code, root_doi, notice_date, steps, hops):
    return {
        "decision": "block",
        "reasons": [
            {
                "code": code,
                "root_doi": root_doi,
                "notice_doi": "10.9999/notice",
                "notice_type": code,
                "notice_date": notice_date,
                "steps": steps,
                "hops_evidence": hops,
            }
        ],
    }


def _zinc(code="withdrawal"):
    return _payload(
        code,
        "10.1002/14651858.cd001364.pub3",
        "2015-04-30",
        [
            {"url": ZINC_URL, "title": "Zinc and Your Health \u2022 The Nutrition Source"},
            {"doi": "10.1002/14651858.cd001364.pub3", "first_author": "Singh", "year": 2011},
        ],
        [{"reliance": "mention", "weight": 0.55}],
    )


def _vitd():
    return _payload(
        "retraction",
        "10.1016/j.amjmed.2004.05.019",
        "2025-05",
        [
            {"url": VITD_URL, "title": "Vitamin D \u2022 The Nutrition Source"},
            {"doi": "10.1002/14651858.cd000227.pub4", "first_author": "Avenell", "year": 2014},
            {"doi": "10.1016/j.amjmed.2004.05.019", "first_author": "Ishida", "year": 2004},
        ],
        [{"reliance": "mention"}, {"reliance": "uses_data_or_method"}],
    )


def test_cochrane_retraction_is_stored_as_withdrawal():
    assert cochrane_withdrawal("10.1002/14651858.cd001364.pub3", "retraction", "Retraction") == (
        "withdrawal",
        "Withdrawn by Cochrane",
    )
    assert cochrane_withdrawal("10.1016/j.amjmed.2004.05.019", "retraction", "Retraction") == (
        "retraction",
        "Retraction",
    )


def test_old_graph_cochrane_reason_reads_as_withdrawal():
    reason = {"code": "retraction", "root_doi": "10.1002/14651858.cd001364.pub3", "notice_type": "retraction"}
    _cochrane_reason(reason)
    assert reason["code"] == "withdrawal"
    assert reason["notice_label"] == "Withdrawn by Cochrane"


def test_withdrawal_disclosure_never_says_retracted():
    out = template_rewrite(_zinc(), f"Source: {ZINC_URL}", [ZINC_URL])["text"]
    assert "withdrawn by Cochrane on 30 Apr 2015" in out
    assert "retract" not in out.lower()
    assert is_disclosure_only(out, [])


def test_page_chain_disclosure_names_the_cited_page():
    out = template_rewrite(_vitd(), f"Harvard reviews it at {VITD_URL}.", [VITD_URL])["text"]
    assert out.startswith('An earlier version of this answer cited the Harvard Nutrition Source page "Vitamin D"')
    assert "Avenell et al. 2014, which uses data from Ishida et al. 2004" in out
    assert is_disclosure_only(out, [])


def test_agent_softens_only_the_claim_its_citation_supported():
    draft = f"Vitamin D helps prevent fractures in older adults. Harvard reviews the evidence at {VITD_URL}."
    plain = template_rewrite(_vitd(), draft, [VITD_URL])["text"]
    assert plain.startswith("Vitamin D helps prevent fractures in older adults. ")
    soft = template_rewrite(_vitd(), draft, [VITD_URL], soften_claims=True)["text"]
    assert soft.startswith(f"Vitamin D helps prevent fractures in older adults{UNSUPPORTED_NOTE}. ")


def test_explored_graph_grows_with_depth(tmp_path):
    from mooltrace.graph import Graph
    from mooltrace.public_demo import seed_offline_presets
    from mooltrace.trace import _answer_id

    graph = Graph(tmp_path / "g.db")
    seed_offline_presets(graph)
    answer = _answer_id("nutrition-coach", "", [VITD_URL])
    one = graph.explored(answer, 1)
    two = graph.explored(answer, 2)
    assert [len(row["works"]) for row in one] == [1]
    assert sorted(len(row["works"]) for row in two) == [1, 2]
    assert two and any(work.get("first_author") == "Ishida" for row in two for work in row["works"])
    graph.close()


def test_first_of_month_issue_date_is_said_as_a_month():
    payload = _vitd()
    payload["reasons"][0]["notice_date"] = "2025-05-01"
    out = template_rewrite(payload, f"Source: {VITD_URL}", [VITD_URL])["text"]
    assert "retracted in May 2025" in out
    assert "1 May" not in out
