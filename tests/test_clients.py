from mooltrace.clients import CallStats, resolve_diabetes_care


def test_resolve_diabetes_care_uses_crossref_not_openalex(monkeypatch):
    calls = []

    def fake_crossref(doi, stats):
        calls.append(("crossref", doi))
        return {"DOI": doi, "ISSN": ["0149-5992", "1935-5548"]}

    def fake_openalex(volume, issue, page, stats):
        calls.append(("openalex", volume, issue, page))
        raise AssertionError("OpenAlex must not run when Crossref confirms ISSN")

    monkeypatch.setattr("mooltrace.clients.crossref_work", fake_crossref)
    monkeypatch.setattr("mooltrace.clients.openalex_diabetes_care", fake_openalex)
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"
    assert calls == [("crossref", "10.2337/diacare.26.12.3215")]


def test_resolve_diabetes_care_falls_back_when_crossref_misses(monkeypatch):
    monkeypatch.setattr("mooltrace.clients.crossref_work", lambda doi, stats: None)
    monkeypatch.setattr(
        "mooltrace.clients.openalex_diabetes_care",
        lambda volume, issue, page, stats: "10.2337/diacare.26.12.3215",
    )
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"


def test_resolve_diabetes_care_rejects_wrong_issn(monkeypatch):
    monkeypatch.setattr(
        "mooltrace.clients.crossref_work",
        lambda doi, stats: {"DOI": doi, "ISSN": ["0000-0000"]},
    )
    monkeypatch.setattr(
        "mooltrace.clients.openalex_diabetes_care",
        lambda volume, issue, page, stats: "10.2337/diacare.26.12.3215",
    )
    doi = resolve_diabetes_care("26", "12", "3215", CallStats())
    assert doi == "10.2337/diacare.26.12.3215"
