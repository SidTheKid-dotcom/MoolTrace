from mooltrace.contexts import abstract_candidates
from mooltrace.reliance import (
    WEIGHTS,
    citation_group_size,
    classify_sentence,
    choose_reliance,
)


KHAN_TITLE = "Cinnamon improves glucose and lipids of people with type 2 diabetes"


def test_grouped_citation_without_the_author_is_background():
    sentence = "Cinnamon lowered fasting glucose in several trials (6-9, 12, 13)."
    kind, weight = classify_sentence(sentence, cited_author="Khan", cited_title=KHAN_TITLE)
    assert citation_group_size(sentence) >= 3
    assert kind == "background"
    assert weight == WEIGHTS["background"]


def test_analyzing_named_results_uses_the_data():
    sentence = (
        "Allen and colleagues, analyzing the results Khan and colleagues 6 "
        "as 3 separate comparisons, which could result in an exaggerated lower effect size."
    )
    kind, weight = classify_sentence(
        sentence,
        cited_doi="10.2337/diacare.26.12.3215",
        cited_author="Khan",
        cited_title=KHAN_TITLE,
    )
    assert kind == "uses_data_or_method"
    assert weight == 0.85


def test_named_finding_relies():
    sentence = "Khan and colleagues found that cinnamon reduced fasting glucose."
    kind, weight = classify_sentence(sentence, cited_author="Khan", cited_title=KHAN_TITLE)
    assert kind == "relies"
    assert weight == 1.0


def test_disputed_form_is_critical():
    sentence = "Later trials disputed Khan 2003 after independent replication failed."
    kind, weight = classify_sentence(sentence, cited_author="Khan")
    assert kind == "critical"
    assert weight == 0.0


def test_exclusion_is_critical_and_does_not_count():
    sentence = "Khan 2003 was excluded after an expression of concern."
    kind, weight = classify_sentence(sentence, cited_author="Khan")
    assert kind == "critical"
    assert weight == 0.0


def test_reference_list_title_is_background_even_when_the_title_states_a_result():
    sentence = (
        "Khan A, Safdar M, Ali Khan MM, et al. "
        "Cinnamon improves glucose and lipids of people with type 2 diabetes. "
        "Diabetes Care. 2003;26(12):3215-3218."
    )
    kind, weight = classify_sentence(sentence, cited_author="Khan", cited_title=KHAN_TITLE)
    assert kind == "background"
    assert weight == WEIGHTS["background"]


def test_bare_mention_is_above_the_floor():
    kind, weight = classify_sentence(
        "See Khan et al., 2003 for the trial protocol and nothing further.",
        cited_author="Khan",
    )
    assert kind == "mention"
    assert weight == 0.55


def test_stronger_sentence_wins_over_a_grouped_context():
    picked = choose_reliance(
        [
            (
                "Fasting glucose fell across the pooled trials (6-9, 12, 13) without naming a single protocol.",
                "semantic_scholar",
            ),
            (
                "We pooled data from Khan and colleagues rather than treating every arm as one trial.",
                "pmc_full_text",
            ),
        ],
        cited_author="Khan",
        cited_doi="10.2337/diacare.26.12.3215",
    )
    assert picked is not None
    assert picked.reliance == "uses_data_or_method"
    assert picked.evidence_from == "pmc_full_text"
    assert "pooled data from Khan" in picked.sentence


def test_a_different_khan_year_is_not_the_2003_study():
    picked = choose_reliance(
        [
            ("Participant gender was not reported by Khan 2010.", "pmc_full_text"),
            (
                "Khan 2003 compared 1 g, 3 g and 6 g of cinnamon and reported fasting glucose.",
                "pmc_full_text",
            ),
        ],
        cited_author="Khan",
        cited_year=2003,
    )
    assert picked is not None
    assert "2003" in picked.sentence
    assert "2010" not in picked.sentence


def test_author_initials_line_is_background():
    sentence = "Liao J.C., Deng J.S., Chiu C.S., Hou W.C., Huang S.S., Shie P.H., Huang G.J."
    kind, weight = classify_sentence(
        sentence,
        cited_author="Liao",
        cited_doi="10.1155/2012/429320",
    )
    assert kind == "background"
    assert weight == WEIGHTS["background"]


def test_doi_bibliography_stub_is_background():
    sentence = (
        "2012;2012:429320. doi: 10.1155/2012/429320. "
        "[DOI] [PMC free article] [PubMed] [Google Scholar]"
    )
    kind, weight = classify_sentence(
        sentence,
        cited_doi="10.1155/2012/429320",
        cited_author="Khan",
    )
    assert kind == "background"
    assert weight == WEIGHTS["background"]


def test_nearby_fasting_sentence_is_not_reliance_on_khan():
    sentence = (
        "However, the sulfonylurea drugs taken daily by the participants can also "
        "help in the improvement of fasting blood glucose levels observed in these "
        "participants [15]."
    )
    kind, weight = classify_sentence(sentence, cited_author="Khan")
    assert kind == "background"
    assert weight < 0.5


def test_methods_sentence_is_not_an_abstract_citation():
    sentence = (
        "Included RCTs evaluated cinnamon compared with control in patients with "
        "type 2 diabetes and reported at least one of the following: glycated "
        "hemoglobin (A1c), fasting plasma glucose, total cholesterol."
    )
    assert abstract_candidates(
        sentence,
        cited_doi="10.2337/diacare.26.12.3215",
        cited_author="Khan",
        cited_title=KHAN_TITLE,
    ) == []


def test_retraction_note_does_not_erase_a_reported_finding():
    sentence = (
        "Mehra and colleagues reported outcomes for hydroxychloroquine "
        "in the retracted Lancet registry analysis 10.1016/s0140-6736(20)31180-6."
    )
    kind, weight = classify_sentence(
        sentence,
        cited_author="Mehra",
        cited_doi="10.1016/s0140-6736(20)31180-6",
    )
    assert kind == "relies"
    assert weight == 1.0


def test_draft_hedge_does_not_discount_a_named_study():
    picked = choose_reliance(
        [
            (
                "Khan 2003 (doi 10.2337/diacare.26.12.3215) reported fasting "
                "glucose changes, although the paper now carries an expression of concern.",
                "draft",
            )
        ],
        cited_doi="10.2337/diacare.26.12.3215",
        cited_author="Khan",
    )
    assert picked is not None
    assert picked.reliance != "critical"
    assert picked.weight >= 0.5
    assert picked.evidence_from == "draft"


def test_draft_exclusion_hedge_still_counts():
    picked = choose_reliance(
        [
            (
                "We excluded weaker data from Mehra "
                "10.1016/s0140-6736(20)31180-6.",
                "draft",
            )
        ],
        cited_doi="10.1016/s0140-6736(20)31180-6",
        cited_author="Mehra",
    )
    assert picked is not None
    assert picked.weight >= 0.5


def test_review_exclusion_is_still_critical():
    picked = choose_reliance(
        [
            (
                "Khan 2003 was excluded after an expression of concern.",
                "pmc_full_text",
            )
        ],
        cited_author="Khan",
    )
    assert picked is not None
    assert picked.reliance == "critical"
    assert picked.weight == 0.0


def test_page_source_list_is_a_counted_mention():
    picked = choose_reliance(
        [
            (
                "14. Khan A, Safdar M, Ali Khan MM, et al. "
                "Cinnamon improves glucose and lipids of people with type 2 diabetes. "
                "Diabetes Care. 2003;26(12):3215-3218.",
                "page_list",
            )
        ],
        cited_doi="10.2337/diacare.26.12.3215",
        cited_author="Khan",
        cited_title=KHAN_TITLE,
    )
    assert picked is not None
    assert picked.reliance == "mention"
    assert picked.weight == 0.55
