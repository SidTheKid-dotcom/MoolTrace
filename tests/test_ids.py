from mooltrace.ids import (
    clean_doi,
    diabetes_care_doi,
    extract_identifiers,
    has_verifiable_source,
    is_disclosure_only,
    is_publisher_flag,
)


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
    assert clean_doi("https://doi.org/10.2337%2Fdiacare.26.12.3215") == "10.2337/diacare.26.12.3215"
    assert clean_doi("10.2337/diacare.26.12.3215\u200b") == "10.2337/diacare.26.12.3215"
    assert clean_doi("10.2337/diacare.26.12.3215।") == "10.2337/diacare.26.12.3215"
    assert clean_doi("10.3389/fendo.2019.00640/full") == "10.3389/fendo.2019.00640"
    assert (
        clean_doi("https://www.frontiersin.org/articles/10.3389/fendo.2019.00640/full")
        == "10.3389/fendo.2019.00640"
    )
    assert (
        clean_doi("https://onlinelibrary.wiley.com/doi/10.1002/ptr.8026/abstract")
        == "10.1002/ptr.8026"
    )
    assert (
        clean_doi("https://link.springer.com/article/10.1007/s00125-003-1116-6/full.pdf")
        == "10.1007/s00125-003-1116-6"
    )
    assert (
        clean_doi("https://www.tandfonline.com/doi/pdf/10.1080/07315724.2006.10719518")
        == "10.1080/07315724.2006.10719518"
    )
    assert (
        clean_doi("https://www.nejm.org/doi/full/10.1056/NEJMoa012512")
        == "10.1056/nejmoa012512"
    )
    assert (
        clean_doi("https://www.nejm.org/doi/pdf/10.1056/NEJMoa012512")
        == "10.1056/nejmoa012512"
    )
    assert clean_doi("10.1016/s0140-6736(20)31180-6/fulltext") == "10.1016/s0140-6736(20)31180-6"
    assert clean_doi("10.1056/nejmoa012512/full.pdf") == "10.1056/nejmoa012512"
    assert clean_doi("10.1002/ptr.8026/abstract?utm=1") == "10.1002/ptr.8026"
    assert (
        clean_doi("https://link.springer.com/content/pdf/10.1007/s00394-019-02128-6.pdf")
        == "10.1007/s00394-019-02128-6"
    )
    assert clean_doi("10.1007/s00394-019-02128-6.pdf") == "10.1007/s00394-019-02128-6"
    assert clean_doi("10.3389/fendo.2019.00640/full\\") == "10.3389/fendo.2019.00640"
    assert (
        clean_doi("https://www.nejm.org/doi/full/10.1056/NEJMoa012512#sec1")
        == "10.1056/nejmoa012512"
    )
    assert (
        clean_doi("https://www.tandfonline.com/doi/full/10.1080/07315724.2006.10719518?needAccess=true")
        == "10.1080/07315724.2006.10719518"
    )
    assert (
        clean_doi("https://www.frontiersin.org/articles/10.3389/fendo.2019.00640/epdf")
        == "10.3389/fendo.2019.00640"
    )


def test_extract_encoded_and_noisy_dois():
    encoded = extract_identifiers("See https://doi.org/10.2337%2Fdiacare.26.12.3215")
    assert "10.2337/diacare.26.12.3215" in encoded.dois
    zwsp = extract_identifiers("DOI 10.2337/diacare.26.12.3215\u200b is cited.")
    assert zwsp.dois == ["10.2337/diacare.26.12.3215"]
    danda = extract_identifiers("DOI 10.2337/diacare.26.12.3215।")
    assert danda.dois == ["10.2337/diacare.26.12.3215"]
    encoded = extract_identifiers("cite doi%3A10.2337%2Fdiacare.26.12.3215")
    assert "10.2337/diacare.26.12.3215" in encoded.dois
    broken = extract_identifiers("DOI 10.2337/diacare.\n26.12.3215 is the trial.")
    assert "10.2337/diacare.26.12.3215" in broken.dois
    wide = extract_identifiers("DOI １０．２３３７／diacare.26.12.3215")
    assert "10.2337/diacare.26.12.3215" in wide.dois
    slash_break = extract_identifiers("DOI 10.2337/\ndiacare.26.12.3215 is the trial.")
    assert "10.2337/diacare.26.12.3215" in slash_break.dois
    sentence_end = extract_identifiers("DOI 10.1056/NEJMoa012512.\nThe next sentence.")
    assert sentence_end.dois == ["10.1056/nejmoa012512"]
    assert "10.1056/nejmoa012512.the" not in sentence_end.dois


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
    assert diabetes_care_doi("26", "12", "3215") == "10.2337/diacare.26.12.3215"


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


def test_extract_skips_rewrite_disclosures():
    text = (
        "Hydroxychloroquine outcomes: the study this relied on "
        "(Mehra 2020, 10.1016/s0140-6736(20)31180-6) was retracted on "
        "2020-06-05 (notice 10.1016/s0140-6736(20)31324-6). This claim has been removed."
    )
    found = extract_identifiers(text)
    assert found.dois == []
    assert is_disclosure_only(text, [])
    assert not has_verifiable_source(text)
    eoc = (
        "Evidence for this claim is under review "
        "(Expression of Concern, 10.2337/dc25-ec09, 2025-08-20)."
    )
    assert extract_identifiers(eoc).dois == []
    assert is_disclosure_only(eoc, [])
    named = (
        "Hydroxychloroquine outcomes: the study this relied on "
        "(Mehra 2020) was retracted on 2020-06-05. This claim has been removed."
    )
    assert extract_identifiers(named).dois == []
    assert is_disclosure_only(named, [])
    eoc_named = "Evidence for this claim is under review (Khan 2003, Expression of Concern)."
    assert extract_identifiers(eoc_named).dois == []
    assert is_disclosure_only(eoc_named, [])
