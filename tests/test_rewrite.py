from mooltrace.config import (
    CLEAN_REWRITE_DOI,
    EOC_DOI,
    HEALTHLINE_CINNAMON_URL,
    HEALTHLINE_OLIVE_OIL_URL,
    KHAN_DOI,
    LANCET_HCQ_DOI,
    LANCET_RETRACTION_DOI,
)
from mooltrace.rewrite import propose_rewrite, rewrite_answer, still_cites, template_rewrite

LANCET_TEXT = (
    "A draft patient note says a 2020 Lancet registry analysis by Mehra and "
    "colleagues reported outcomes for hydroxychloroquine. "
    "DOI 10.1016/S0140-6736(20)31180-6. "
    "This note is not a recommendation to start or stop a medicine."
)
DISCLAIMER = "This note is not a recommendation to start or stop a medicine."
HEALTHLINE_TEXT = (
    "Cinnamon may help blood sugar in some people. "
    f"{HEALTHLINE_CINNAMON_URL}"
)
CLEAN_TEXT = f"A checked paper is DOI {CLEAN_REWRITE_DOI}."


def _warn_payload() -> dict:
    return {
        "decision": "warn",
        "exit_code": 2,
        "reasons": [
            {
                "code": "expression_of_concern",
                "notice_doi": "10.2337/dc25-ec09",
                "notice_date": "2025-08-20",
                "root_doi": "10.2337/diacare.26.12.3215",
                "source_url": HEALTHLINE_CINNAMON_URL,
                "steps": [{"url": HEALTHLINE_CINNAMON_URL}],
            }
        ],
    }


def _lancet_payload() -> dict:
    return {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": "10.1016/s0140-6736(20)31324-6",
                "notice_date": "2020-06-05",
                "root_doi": LANCET_HCQ_DOI,
                "root_author": "Mehra",
                "root_year": 2020,
                "steps": [{"doi": LANCET_HCQ_DOI, "first_author": "Mehra", "year": 2020}],
            }
        ],
    }


def test_template_rewrite_keeps_untouched_lancet_sentence():
    payload = _lancet_payload()
    out = template_rewrite(payload, LANCET_TEXT, [])
    assert DISCLAIMER in out["text"]
    assert out["text"].endswith(DISCLAIMER) or DISCLAIMER in out["text"]
    assert CLEAN_REWRITE_DOI not in out["text"]
    assert "Diabetes mellitus and oxidative stress" not in out["text"]
    assert "under review" not in out["text"].lower()
    assert "was retracted on" in out["text"]
    assert "so that source was removed." in out["text"]
    assert "Mehra et al. 2020" in out["text"]
    assert "This claim:" not in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert "10.1016/s0140-6736(20)31324-6" not in out["text"]
    leading, _, trailing = out["text"].partition(DISCLAIMER)
    assert trailing == ""
    assert DISCLAIMER not in leading
    assert not still_cites(out["text"], out["urls"], payload)


def test_template_rewrite_replaces_healthline_named_claim():
    payload = _warn_payload()
    text = "Cinnamon may modestly lower fasting blood sugar, according to Healthline."
    out = template_rewrite(payload, text, [HEALTHLINE_CINNAMON_URL])
    assert "according to Healthline" not in out["text"]
    assert "Cinnamon may modestly lower fasting blood sugar" not in out["text"]
    assert "Expression of Concern" in out["text"]
    assert "so that source was removed." in out["text"]
    assert "This claim:" not in out["text"]
    assert HEALTHLINE_CINNAMON_URL not in (out.get("urls") or [])
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_unchanged_text_sets_rewritten_false(monkeypatch):
    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        return {**_warn_payload(), "exit_code": 2}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    monkeypatch.setattr(
        "mooltrace.rewrite.propose_rewrite",
        lambda *args, **kwargs: {
            "text": CLEAN_TEXT,
            "urls": [],
            "method": "template",
            "dropped": [],
        },
    )
    out = rewrite_answer(CLEAN_TEXT, [], "clean-check", 2)
    assert out["rewritten"] is False
    assert out["text"] == CLEAN_TEXT


def test_rewrite_cli_summary_and_json(monkeypatch, capsys):
    from mooltrace.__main__ import main

    monkeypatch.setattr(
        "mooltrace.__main__.rewrite_answer",
        lambda *args, **kwargs: {
            "rewritten": True,
            "exit_code": 0,
            "recheck": {
                "decision": "pass",
                "exit_code": 0,
                "reasons": [],
            },
            "text": "disclosed",
        },
    )
    code = main(["rewrite", "--text", "flagged", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"rewritten": true' in out.lower() or '"rewritten": true' in out
    code = main(["rewrite", "--text", "flagged", "--summary"])
    assert code == 0
    summary = capsys.readouterr().out
    assert "REWRITE (exit 0)" in summary
    assert "rewritten=true" in summary


def test_template_rewrite_drops_flagged_url():
    payload = _warn_payload()
    out = template_rewrite(payload, HEALTHLINE_TEXT, [HEALTHLINE_CINNAMON_URL])
    assert CLEAN_REWRITE_DOI not in out["text"]
    assert "healthline" not in out["text"].lower()
    assert "Expression of Concern" in out["text"]
    assert "so that source was removed." in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)
    assert out["method"] == "template"
    assert HEALTHLINE_CINNAMON_URL not in (out.get("urls") or [])


def test_propose_rewrite_is_template(monkeypatch):
    payload = _warn_payload()
    out = propose_rewrite(HEALTHLINE_TEXT, [HEALTHLINE_CINNAMON_URL], payload)
    assert out["method"] == "template"
    assert CLEAN_REWRITE_DOI not in out["text"]
    assert DISCLAIMER not in out["text"]


def test_rewrite_answer_clean_draft_is_unchanged(monkeypatch):
    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        return {"decision": "pass", "exit_code": 0, "reasons": []}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    out = rewrite_answer(CLEAN_TEXT, [], "clean-check", 2)
    assert out["rewritten"] is False
    assert out["text"] == CLEAN_TEXT
    assert out["exit_code"] == 0
    assert out["recheck"]["exit_code"] == 0


def test_rewrite_exit_code_matches_recheck_pass(monkeypatch):
    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        if "so that source was removed" in (text or "") or "so this claim was removed" in (text or ""):
            return {"decision": "pass", "exit_code": 0, "reasons": []}
        return {**_warn_payload(), "exit_code": 2}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    out = rewrite_answer(HEALTHLINE_TEXT, [HEALTHLINE_CINNAMON_URL], "nutrition-coach", 2)
    assert out["rewritten"] is True
    assert out["recheck"]["decision"] == "pass"
    assert out["recheck"]["exit_code"] == 0
    assert out["exit_code"] == 0
    assert CLEAN_REWRITE_DOI not in out["text"]


def test_check_answer_retraction_disclosure_is_pass(tmp_path):
    from mooltrace.graph import Graph
    from mooltrace.trace import check_answer

    graph = Graph(tmp_path / "mooltrace.db")
    text = (
        "An earlier version of this answer cited Mehra et al. 2020; "
        "that paper was retracted on 5 Jun 2020, so that source was removed."
    )
    try:
        out = check_answer(text, [], "draft", 2, graph=graph)
        assert out["decision"] == "pass"
        assert out["exit_code"] == 0
        assert "removed" in (out.get("summary") or "").lower()
    finally:
        graph.close()


def test_rewrite_cli_zero_is_not_coerced_to_two(monkeypatch, capsys):
    from mooltrace.__main__ import main

    monkeypatch.setattr(
        "mooltrace.__main__.rewrite_answer",
        lambda *args, **kwargs: {
            "rewritten": True,
            "exit_code": 0,
            "recheck": {"decision": "pass", "exit_code": 0},
            "text": "disclosed",
        },
    )
    code = main(["rewrite", "--text", "flagged"])
    assert code == 0
    capsys.readouterr()


MEHRA_RETRACTED_TITLE = (
    "RETRACTED: Hydroxychloroquine or chloroquine with or without a macrolide "
    "for treatment of COVID-19: a multinational registry analysis"
)
HEALTHLINE_CLEAN_SENTENCE = "Vitamin D status is discussed separately. "


def _hcq_payload() -> dict:
    return {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": LANCET_RETRACTION_DOI,
                "notice_date": "2020-06-05",
                "root_doi": LANCET_HCQ_DOI,
                "root_author": "Mehra",
                "root_year": 2020,
                "root": {
                    "doi": LANCET_HCQ_DOI,
                    "title": MEHRA_RETRACTED_TITLE,
                    "year": 2020,
                    "first_author": "Mehra",
                },
                "steps": [
                    {
                        "doi": LANCET_HCQ_DOI,
                        "title": MEHRA_RETRACTED_TITLE,
                        "year": 2020,
                        "first_author": "Mehra",
                    }
                ],
            }
        ],
    }


def _healthline_payload() -> dict:
    return {
        "decision": "warn",
        "exit_code": 2,
        "reasons": [
            {
                "code": "expression_of_concern",
                "notice_doi": EOC_DOI,
                "notice_date": "2025-08-20",
                "root_doi": KHAN_DOI,
                "root_author": "Khan",
                "root_year": 2003,
                "source_url": HEALTHLINE_CINNAMON_URL,
                "steps": [
                    {
                        "url": HEALTHLINE_CINNAMON_URL,
                    },
                    {
                        "doi": KHAN_DOI,
                        "title": "Cinnamon improves glucose and lipids of people with type 2 diabetes",
                        "year": 2003,
                        "first_author": "Khan",
                    },
                ],
            }
        ],
    }


def _fake_check_for(payload: dict):
    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        if still_cites(text or "", list(urls or []), payload):
            return {**payload}
        return {"decision": "pass", "exit_code": 0, "reasons": []}

    return fake_check


def test_rewrite_hcq_mehra_2020_only_flagged_sentence(monkeypatch):
    payload = _hcq_payload()
    monkeypatch.setattr("mooltrace.rewrite.check_answer", _fake_check_for(payload))
    out = rewrite_answer(LANCET_TEXT, [], "lancet-hcq", 1)
    assert out["rewritten"] is True
    assert out["text"].endswith(DISCLAIMER)
    assert out["text"][out["text"].rfind(DISCLAIMER) :] == DISCLAIMER
    assert "Mehra et al. 2020" in out["text"]
    assert "This claim:" not in out["text"]
    assert "A draft patient note says" not in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert "RETRACTED" not in out["text"]
    assert LANCET_RETRACTION_DOI not in out["text"]
    assert LANCET_RETRACTION_DOI.lower() not in out["text"].lower()
    assert "reported outcomes for hydroxychloroquine" not in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_healthline_with_text_keeps_other_sentences(monkeypatch):
    claim = f"Cinnamon may help blood sugar ({HEALTHLINE_CINNAMON_URL})."
    text = HEALTHLINE_CLEAN_SENTENCE + claim
    payload = _healthline_payload()
    monkeypatch.setattr("mooltrace.rewrite.check_answer", _fake_check_for(payload))
    out = rewrite_answer(text, [HEALTHLINE_CINNAMON_URL], "nutrition-coach", 2)
    assert out["rewritten"] is True
    assert out["text"].startswith(HEALTHLINE_CLEAN_SENTENCE)
    assert out["text"][: len(HEALTHLINE_CLEAN_SENTENCE)] == HEALTHLINE_CLEAN_SENTENCE
    assert HEALTHLINE_CINNAMON_URL not in out["text"]
    assert HEALTHLINE_CINNAMON_URL not in (out.get("urls") or [])
    assert "Khan et al. 2003" in out["text"]
    assert "Cinnamon 2003" not in out["text"]
    assert "Expression of Concern" in out["text"]
    assert "retract" not in out["text"].lower()
    assert EOC_DOI not in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_clean_answer_byte_identical(monkeypatch):
    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        return {"decision": "pass", "exit_code": 0, "reasons": []}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    original = CLEAN_TEXT
    out = rewrite_answer(original, [], "clean-check", 2)
    assert out["rewritten"] is False
    assert out["text"] == original
    assert list(out["text"]) == list(original)


def test_rewrite_multi_claim_only_flagged_sentence(monkeypatch):
    flagged = (
        "A draft patient note says a 2020 Lancet registry analysis by Mehra and "
        f"colleagues reported outcomes for hydroxychloroquine (DOI {LANCET_HCQ_DOI}). "
    )
    clean = f"A checked paper is DOI {CLEAN_REWRITE_DOI}. "
    text = flagged + clean + DISCLAIMER
    payload = _hcq_payload()
    monkeypatch.setattr("mooltrace.rewrite.check_answer", _fake_check_for(payload))
    out = rewrite_answer(text, [], "multi-claim", 1)
    assert out["rewritten"] is True
    assert clean in out["text"]
    at = out["text"].find(clean)
    assert at >= 0
    assert out["text"][at : at + len(clean)] == clean
    assert out["text"].endswith(DISCLAIMER)
    assert out["text"][out["text"].rfind(DISCLAIMER) :] == DISCLAIMER
    assert "Mehra et al. 2020" in out["text"]
    assert "This claim:" not in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert LANCET_RETRACTION_DOI not in out["text"]
    assert "reported outcomes for hydroxychloroquine" not in out["text"]
    assert CLEAN_REWRITE_DOI in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)


ESTRUCH_DOI = "10.1056/nejmoa1200303"
ESTRUCH_NOTICE = "10.1056/nejmc1806491"
OLIVE_REWRITE_DRAFT = (
    "Vitamin D status is discussed separately. "
    f"A nutrition coach cites {HEALTHLINE_OLIVE_OIL_URL}."
)
ESTRUCH_REWRITE = (
    "An earlier version of this answer cited Estruch et al. 2013 (PREDIMED); "
    "that trial report was retracted and republished on 13 Jun 2018, "
    "so that source was removed."
)
KHAN_REWRITE = (
    "An earlier version of this answer cited Khan et al. 2003; "
    "that paper is under an Expression of Concern dated 20 Aug 2025, "
    "so that source was removed."
)
MEHRA_REWRITE = (
    "An earlier version of this answer cited Mehra et al. 2020; "
    "that paper was retracted on 5 Jun 2020, so that source was removed."
)


def _estruch_live_payload() -> dict:
    """Hosted olive-oil shape: year and title, no first_author on the reason."""
    return {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": ESTRUCH_NOTICE,
                "notice_date": "2018-06-13",
                "notice_label": "Retraction",
                "root_doi": ESTRUCH_DOI,
                "root_title": (
                    "RETRACTED: Primary Prevention of Cardiovascular Disease "
                    "with a Mediterranean Diet"
                ),
                "root_year": 2013,
                "source_url": HEALTHLINE_OLIVE_OIL_URL,
                "steps": [
                    {"url": HEALTHLINE_OLIVE_OIL_URL, "title": "11 Proven Benefits of Olive Oil"},
                    {
                        "doi": ESTRUCH_DOI,
                        "title": (
                            "RETRACTED: Primary Prevention of Cardiovascular "
                            "Disease with a Mediterranean Diet"
                        ),
                        "year": 2013,
                    },
                ],
            }
        ],
    }


def _khan_live_payload() -> dict:
    """Hosted cinnamon shape: title starts with Cinnamon, no first_author."""
    return {
        "decision": "warn",
        "exit_code": 2,
        "reasons": [
            {
                "code": "expression_of_concern",
                "notice_doi": EOC_DOI,
                "notice_date": "2025-08-20",
                "notice_label": "Expression of Concern",
                "root_doi": KHAN_DOI,
                "root_title": "Cinnamon Improves Glucose and Lipids of People With Type 2 Diabetes",
                "root_year": 2003,
                "source_url": HEALTHLINE_CINNAMON_URL,
                "steps": [
                    {"url": HEALTHLINE_CINNAMON_URL},
                    {
                        "doi": KHAN_DOI,
                        "title": "Cinnamon Improves Glucose and Lipids of People With Type 2 Diabetes",
                        "year": 2003,
                    },
                ],
            }
        ],
    }


def _mehra_live_payload() -> dict:
    return {
        "decision": "block",
        "exit_code": 1,
        "reasons": [
            {
                "code": "retraction",
                "notice_doi": LANCET_RETRACTION_DOI,
                "notice_date": "2020-06-05",
                "root_doi": LANCET_HCQ_DOI,
                "root_title": MEHRA_RETRACTED_TITLE,
                "root_year": 2020,
                "steps": [
                    {
                        "doi": LANCET_HCQ_DOI,
                        "title": MEHRA_RETRACTED_TITLE,
                        "year": 2020,
                    }
                ],
            }
        ],
    }


def _graph_with_authors(tmp_path):
    from mooltrace.graph import Graph

    graph = Graph(tmp_path / "rewrite-authors.db")
    graph.merge_work(ESTRUCH_DOI, title="PREDIMED", year=2013, first_author="Estruch")
    graph.merge_work(KHAN_DOI, title="Cinnamon Improves Glucose", year=2003, first_author="Khan")
    graph.merge_work(LANCET_HCQ_DOI, title=MEHRA_RETRACTED_TITLE, year=2020, first_author="Mehra")
    return graph


def _assert_untouched(original: str, rewritten: str, fragment: str) -> None:
    assert fragment in original
    assert fragment in rewritten
    at = rewritten.find(fragment)
    assert rewritten[at : at + len(fragment)] == fragment
    if original.startswith(fragment):
        assert rewritten.startswith(fragment)
        assert rewritten[: len(fragment)] == fragment


def test_rewrite_estruch_names_author_no_splice(tmp_path):
    payload = _estruch_live_payload()
    graph = _graph_with_authors(tmp_path)
    try:
        out = template_rewrite(payload, OLIVE_REWRITE_DRAFT, [HEALTHLINE_OLIVE_OIL_URL], graph)
        assert out["text"].startswith(HEALTHLINE_CLEAN_SENTENCE)
        assert out["text"][: len(HEALTHLINE_CLEAN_SENTENCE)] == HEALTHLINE_CLEAN_SENTENCE
        _assert_untouched(OLIVE_REWRITE_DRAFT, out["text"], HEALTHLINE_CLEAN_SENTENCE)
        assert out["text"] == f"{HEALTHLINE_CLEAN_SENTENCE}{ESTRUCH_REWRITE}"
        assert "Estruch et al. 2013 (PREDIMED)" in out["text"]
        assert "retracted and republished" in out["text"]
        assert "13 Jun 2018" in out["text"]
        assert "This claim:" not in out["text"]
        assert "the authors" not in out["text"]
        assert "A nutrition coach cites:" not in out["text"]
        assert "RETRACTED:" not in out["text"]
        assert ESTRUCH_NOTICE not in out["text"]
        assert HEALTHLINE_OLIVE_OIL_URL not in out["text"]
    finally:
        graph.close()


def test_rewrite_khan_names_author_not_title_word(tmp_path):
    claim = f"Cinnamon may help blood sugar ({HEALTHLINE_CINNAMON_URL})."
    text = HEALTHLINE_CLEAN_SENTENCE + claim
    payload = _khan_live_payload()
    graph = _graph_with_authors(tmp_path)
    try:
        out = template_rewrite(payload, text, [HEALTHLINE_CINNAMON_URL], graph)
        _assert_untouched(text, out["text"], HEALTHLINE_CLEAN_SENTENCE)
        assert out["text"] == f"{HEALTHLINE_CLEAN_SENTENCE}{KHAN_REWRITE}"
        assert "Khan et al. 2003" in out["text"]
        assert "Cinnamon 2003" not in out["text"]
        assert "Expression of Concern" in out["text"]
        assert "retract" not in out["text"].lower()
        assert "This claim:" not in out["text"]
        assert "the authors" not in out["text"]
        assert "Cinnamon may help blood sugar" not in out["text"]
        assert EOC_DOI not in out["text"]
    finally:
        graph.close()


def test_rewrite_mehra_names_author_no_mid_sentence_splice(tmp_path):
    payload = _mehra_live_payload()
    graph = _graph_with_authors(tmp_path)
    try:
        out = template_rewrite(payload, LANCET_TEXT, [], graph)
        _assert_untouched(LANCET_TEXT, out["text"], DISCLAIMER)
        assert out["text"].endswith(DISCLAIMER)
        assert out["text"] == f"{MEHRA_REWRITE} {DISCLAIMER}"
        assert "Mehra et al. 2020" in out["text"]
        assert "A draft patient note says" not in out["text"]
        assert "This claim:" not in out["text"]
        assert "the authors" not in out["text"]
        assert "RETRACTED:" not in out["text"]
        assert "retracted and republished" not in out["text"]
        assert LANCET_RETRACTION_DOI not in out["text"]
        assert LANCET_HCQ_DOI.lower() not in out["text"].lower()
        assert not still_cites(out["text"], out["urls"], payload)
    finally:
        graph.close()


def test_rewrite_uses_the_authors_only_when_metadata_has_none():
    payload = _khan_live_payload()
    text = f"Cinnamon may help blood sugar ({HEALTHLINE_CINNAMON_URL})."
    out = template_rewrite(payload, text, [HEALTHLINE_CINNAMON_URL], graph=None)
    assert "Cinnamon 2003" not in out["text"]
    assert "the authors" in out["text"]
    assert "Expression of Concern" in out["text"]
    assert "retract" not in out["text"].lower()


def test_rewrite_says_source_was_removed_not_claim():
    payload = _lancet_payload()
    out = template_rewrite(payload, LANCET_TEXT, [])
    assert "so that source was removed." in out["text"]
    assert "this claim was removed" not in out["text"]
    eoc = template_rewrite(_warn_payload(), HEALTHLINE_TEXT, [HEALTHLINE_CINNAMON_URL])
    assert "so that source was removed." in eoc["text"]
    assert "this claim was removed" not in eoc["text"]
