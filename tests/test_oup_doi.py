"""OUP / academic.oup.com DOIs: strip the article-id path, verify on recorded Crossref."""

from __future__ import annotations

import json
from pathlib import Path

from mooltrace.ids import clean_doi, extract_identifiers

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "crossref"
OUP_PAGE = (
    "https://academic.oup.com/ajcn/article/10.1093/ajcn/nqac107/6572356"
)
REGISTERED = "10.1093/ajcn/nqac107"
WITH_ARTICLE_ID = "10.1093/ajcn/nqac107/6572356"


def _catalog() -> dict:
    return json.loads((FIXTURES / "oup_nqac107.json").read_text(encoding="utf-8"))


def test_oup_article_id_path_is_not_part_of_the_doi():
    assert clean_doi(WITH_ARTICLE_ID) == REGISTERED
    assert clean_doi(OUP_PAGE) == REGISTERED
    assert clean_doi(f"https://doi.org/{WITH_ARTICLE_ID}") == REGISTERED
    found = extract_identifiers(f"See {OUP_PAGE} for the vitamin D trial.")
    assert REGISTERED in found.dois
    assert WITH_ARTICLE_ID not in found.dois


def test_oup_registered_doi_matches_recorded_crossref_and_doi_org():
    catalog = _catalog()
    assert catalog["registered_doi"] == REGISTERED
    short = catalog["lookups"][REGISTERED]
    long = catalog["lookups"][WITH_ARTICLE_ID]
    assert short["crossref_status"] == 200
    assert str(short["crossref_doi"]).lower() == REGISTERED
    assert long["crossref_status"] == 404
    assert short["doi_org_status"] == 200
    assert str(short["doi_org_doi"]).lower() == REGISTERED
    assert long["doi_org_status"] in {404, 400}
    assert clean_doi(WITH_ARTICLE_ID) == catalog["registered_doi"]
    assert clean_doi(OUP_PAGE) == catalog["registered_doi"]
