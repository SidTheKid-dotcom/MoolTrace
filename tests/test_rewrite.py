from mooltrace.config import CLEAN_REWRITE_DOI, HEALTHLINE_CINNAMON_URL, LANCET_HCQ_DOI
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
                "steps": [{"doi": LANCET_HCQ_DOI}],
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
    assert "under review" in out["text"]
    assert "retraction" in out["text"].lower()
    assert "hydroxychloroquine" not in out["text"] or "under review" in out["text"]
    leading, _, trailing = out["text"].partition(DISCLAIMER)
    assert trailing == ""
    assert DISCLAIMER not in leading
    assert not still_cites(out["text"], out["urls"], payload)


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
