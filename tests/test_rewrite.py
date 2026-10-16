from mooltrace.config import CLEAN_REWRITE_DOI, HEALTHLINE_CINNAMON_URL
from mooltrace.rewrite import propose_rewrite, rewrite_answer, still_cites, template_rewrite


def _warn_payload() -> dict:
    return {
        "decision": "warn",
        "reasons": [
            {
                "code": "expression_of_concern",
                "notice_doi": "10.2337/dc25-ec09",
                "root_doi": "10.2337/diacare.26.12.3215",
                "source_url": HEALTHLINE_CINNAMON_URL,
                "steps": [{"url": HEALTHLINE_CINNAMON_URL}],
            }
        ],
    }


def test_template_rewrite_drops_flagged_url():
    payload = _warn_payload()
    out = template_rewrite(payload)
    assert CLEAN_REWRITE_DOI in out["text"]
    assert "healthline" not in out["text"].lower()
    assert not still_cites(out["text"], out["urls"], payload)
    assert out["method"] == "template"


def test_propose_rewrite_falls_back_without_azure(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_MODEL", raising=False)
    payload = _warn_payload()
    out = propose_rewrite("", [HEALTHLINE_CINNAMON_URL], payload)
    assert out["method"] == "template"
    assert CLEAN_REWRITE_DOI in out["text"]


def test_rewrite_answer_rechecks_to_pass(monkeypatch):
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_INFERENCE_MODEL", raising=False)

    def fake_check(text, urls=None, engine="draft", depth=2, graph=None):
        if CLEAN_REWRITE_DOI in (text or ""):
            return {"decision": "pass", "exit_code": 0, "reasons": []}
        return {**_warn_payload(), "exit_code": 2}

    monkeypatch.setattr("mooltrace.rewrite.check_answer", fake_check)
    out = rewrite_answer(
        "Cinnamon may help. https://www.healthline.com/nutrition/cinnamon-and-diabetes",
        [HEALTHLINE_CINNAMON_URL],
        "nutrition-coach",
        2,
    )
    assert out["rewritten"] is True
    assert out["method"] == "template"
    assert CLEAN_REWRITE_DOI in out["text"]
    assert out["recheck"]["decision"] == "pass"
    assert out["recheck"]["exit_code"] == 0
