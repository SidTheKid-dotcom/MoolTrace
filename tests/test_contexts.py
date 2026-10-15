from mooltrace.contexts import format_reference, reference_matches

KHAN = {
    "authorString": "Khan A, Safdar M, Ali Khan MM, Khattak KN, Anderson RA.",
    "title": "Cinnamon improves glucose and lipids of people with type 2 diabetes.",
    "journalAbbreviation": "Diabetes Care",
    "pubYear": 2003,
    "volume": "26",
    "pageInfo": "3215-3218",
}
KHAN_2010 = {
    "authorString": "Khan",
    "title": "Cinnamon May Reduce Glucose, Lipid and Cholesterol Level in Type 2 Diabetic Individuals",
    "pubYear": 2010,
    "doi": "10.3923/pjn.2010.430.433",
}


def test_reference_line_matches_khan_2003_and_skips_2010():
    assert reference_matches(
        KHAN,
        doi="10.2337/diacare.26.12.3215",
        title="Cinnamon improves glucose and lipids of people with type 2 diabetes",
        year="2003",
        author="Khan",
    )
    assert not reference_matches(
        KHAN_2010,
        doi="10.2337/diacare.26.12.3215",
        title="Cinnamon improves glucose and lipids of people with type 2 diabetes",
        year="2003",
        author="Khan",
    )


def test_reference_line_matches_on_doi_alone():
    ref = {"doi": "10.2337/diacare.26.12.3215", "pubYear": 1999, "title": "Something else"}
    assert reference_matches(
        ref,
        doi="10.2337/diacare.26.12.3215",
        title="Cinnamon improves glucose and lipids",
        year="2003",
        author="Khan",
    )


def test_format_reference_keeps_the_bibliographic_fields():
    line = format_reference(KHAN)
    assert line.startswith("Khan A, Safdar M")
    assert "2003" in line
    assert "3215-3218" in line
