"""Owner forbids Azure/OpenAI. Rewrite is the deterministic template only."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from mooltrace.config import HEALTHLINE_CINNAMON_URL, ROOT
from mooltrace.rewrite import propose_rewrite


PRODUCT_PATHS = (
    ROOT / "mooltrace",
    ROOT / "web" / "src",
    ROOT / "README.md",
    ROOT / "SUBMISSION.md",
    ROOT / "JUDGES.md",
    ROOT / "CLAIMS.md",
    ROOT / "VIDEO_SCRIPT.md",
    ROOT / "SHIP_CHECKLIST.md",
)

BANNED = (
    "Azure AI Foundry",
    "azure-foundry",
    "AZURE_INFERENCE",
    "AZURE_OPENAI",
    "mooltrace.foundry",
    "openai.azure.com",
)


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


def test_foundry_module_is_gone():
    assert not (ROOT / "mooltrace" / "foundry.py").exists()
    assert not (ROOT / "mooltrace" / "foundry.pyi").exists()


def test_product_files_do_not_mention_azure_foundry():
    hits: list[str] = []
    files: list[Path] = []
    for path in PRODUCT_PATHS:
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix in {".py", ".ts", ".tsx", ".md", ".json"}
            )
    for path in files:
        text = path.read_text(errors="replace")
        for needle in BANNED:
            if needle in text:
                hits.append(f"{path.relative_to(ROOT)}:{needle}")
    assert hits == []


def test_propose_rewrite_is_template_even_if_foundry_would_respond(monkeypatch):
    calls: list[str] = []
    fake = types.ModuleType("mooltrace.foundry")

    def complete(prompt: str, **kwargs) -> str:
        calls.append(prompt)
        return (
            "Evidence for this claim is under review "
            "(Expression of Concern, 2025-08-20)."
        )

    fake.complete = complete
    fake.available = lambda: True
    monkeypatch.setitem(sys.modules, "mooltrace.foundry", fake)
    monkeypatch.setenv("AZURE_INFERENCE_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_INFERENCE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("AZURE_INFERENCE_MODEL", "not-a-model")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "not-a-model")
    payload = _warn_payload()
    text = f"Cinnamon may help blood sugar. {HEALTHLINE_CINNAMON_URL}"
    out = propose_rewrite(text, [HEALTHLINE_CINNAMON_URL], payload)
    assert out["method"] == "template"
    assert calls == []
    assert "azure" not in str(out.get("method") or "").lower()
