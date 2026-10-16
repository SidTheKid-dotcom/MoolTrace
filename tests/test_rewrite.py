from mooltrace.config import (
    CLEAN_REWRITE_DOI,
    EOC_DOI,
    HEALTHLINE_CINNAMON_URL,
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
    assert "This claim has been removed." in out["text"]
    assert "Mehra 2020" in out["text"]
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
    assert "under review" in out["text"]
    assert "Expression of Concern" in out["text"]
    assert HEALTHLINE_CINNAMON_URL not in (out.get("urls") or [])
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_unchanged_text_sets_rewritten_false(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)

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
    assert "under review" in out["text"]
    assert "Expression of Concern" in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)
    assert out["method"] == "template"
    assert HEALTHLINE_CINNAMON_URL not in (out.get("urls") or [])


def test_propose_rewrite_falls_back_without_azure(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_MODEL", raising=False)
    payload = _warn_payload()
    out = propose_rewrite(HEALTHLINE_TEXT, [HEALTHLINE_CINNAMON_URL], payload)
    assert out["method"] == "template"
    assert CLEAN_REWRITE_DOI not in out["text"]
    assert DISCLAIMER not in out["text"]


def test_rewrite_answer_clean_draft_is_unchanged(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)

    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        return {"decision": "pass", "exit_code": 0, "reasons": []}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    out = rewrite_answer(CLEAN_TEXT, [], "clean-check", 2)
    assert out["rewritten"] is False
    assert out["text"] == CLEAN_TEXT
    assert out["exit_code"] == 0
    assert out["recheck"]["exit_code"] == 0


def test_rewrite_exit_code_matches_recheck_pass(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)

    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        if "under review" in (text or ""):
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
        "Hydroxychloroquine outcomes: the study this relied on "
        "(Mehra 2020) was retracted on "
        "2020-06-05. This claim has been removed."
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
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
    payload = _hcq_payload()
    monkeypatch.setattr("mooltrace.rewrite.check_answer", _fake_check_for(payload))
    out = rewrite_answer(LANCET_TEXT, [], "lancet-hcq", 1)
    assert out["rewritten"] is True
    assert out["text"].endswith(DISCLAIMER)
    assert out["text"][out["text"].rfind(DISCLAIMER) :] == DISCLAIMER
    assert "Mehra 2020" in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert "RETRACTED" not in out["text"]
    assert LANCET_RETRACTION_DOI not in out["text"]
    assert LANCET_RETRACTION_DOI.lower() not in out["text"].lower()
    assert "reported outcomes for hydroxychloroquine" not in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_healthline_with_text_keeps_other_sentences(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
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
    assert "Khan 2003" in out["text"]
    assert "Expression of Concern" in out["text"]
    assert EOC_DOI not in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)


def test_rewrite_clean_answer_byte_identical(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)

    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        return {"decision": "pass", "exit_code": 0, "reasons": []}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    original = CLEAN_TEXT
    out = rewrite_answer(original, [], "clean-check", 2)
    assert out["rewritten"] is False
    assert out["text"] == original
    assert list(out["text"]) == list(original)


def test_rewrite_multi_claim_only_flagged_sentence(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
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
    assert "Mehra 2020" in out["text"]
    assert "RETRACTED:" not in out["text"]
    assert LANCET_RETRACTION_DOI not in out["text"]
    assert "reported outcomes for hydroxychloroquine" not in out["text"]
    assert CLEAN_REWRITE_DOI in out["text"]
    assert not still_cites(out["text"], out["urls"], payload)
