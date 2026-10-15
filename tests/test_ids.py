from mooltrace.ids import clean_doi, extract_identifiers, has_verifiable_source, is_publisher_flag


def test_expression_of_concern_is_a_flag():
    assert is_publisher_flag("expression_of_concern")
    assert is_publisher_flag("Expression of Concern")


def test_retraction_and_withdrawal_are_flags():
    assert is_publisher_flag("retraction")
    assert is_publisher_flag("partial_retraction")
    assert is_publisher_flag("withdrawal")


def test_new_version_and_correction_are_not_flags():
    assert not is_publisher_flag("new_version")
    assert not is_publisher_flag("correction")
    assert not is_publisher_flag("erratum")
    assert not is_publisher_flag("")
    assert not is_publisher_flag(None)


def test_doi_cleanup():
    assert clean_doi("https://doi.org/10.2337/diacare.26.12.3215.") == "10.2337/diacare.26.12.3215"
    assert clean_doi("10.1016/0197-2456(86)90046-2&amp;") == "10.1016/0197-2456(86)90046-2"


def test_extract_page_identifiers():
    text = """
    <a href="https://doi.org/10.2337/diacare.26.12.3215">Khan</a>
    https://pubmed.ncbi.nlm.nih.gov/37818728/
    PMC3767714
    https://diabetesjournals.org/care/article/26/12/3215/21858/Cinnamon
    """
    found = extract_identifiers(text)
    assert "10.2337/diacare.26.12.3215" in found.dois
    assert "37818728" in found.pmids
    assert "PMC3767714" in found.pmcids
    assert ("26", "12", "3215") in found.diabetes_care


def test_has_verifiable_source_accepts_inline_and_explicit_ids():
    assert not has_verifiable_source("")
    assert not has_verifiable_source("   ")
    assert not has_verifiable_source("Cinnamon may help blood sugar in some people.")
    assert has_verifiable_source("See 10.2337/diacare.26.12.3215 for the trial.")
    assert has_verifiable_source("PMID: 14633847")
    assert has_verifiable_source("Full text PMC3767714")
    assert has_verifiable_source(
        "https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"
    )
    assert has_verifiable_source(
        "",
        ["https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"],
    )
