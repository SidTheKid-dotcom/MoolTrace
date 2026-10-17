"""Offline presets must replay recorded fetches, and docs must quote that run."""

from __future__ import annotations

import re
from pathlib import Path

from mooltrace.config import ROOT
from mooltrace.graph import Graph
from mooltrace.public_demo import load_recorded_presets, seed_offline_presets
from mooltrace.seed import load_demo_fixtures
from mooltrace.summary import format_summary
from mooltrace.trace import check_answer

DOCS = (
    ROOT / "README.md",
    ROOT / "VIDEO_SCRIPT.md",
    ROOT / "SUBMISSION.md",
)
RELATION_WORDS = (
    "included",
    "relies",
    "uses_data_or_method",
    "mention",
    "background",
    "critical",
)
HERO = re.compile(
    r"healthline|silva|khan|decided by|path strength|screenshot|caption",
    re.I,
)
STRENGTH = re.compile(r"(?i)(?:path\s+strength|strength)\s+([0-9]+(?:\.[0-9]+)?)")
HANDWRITTEN = re.compile(r"\b0\.72\b")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _synthetic(block: str) -> bool:
    return "synthetic example" in block.lower()


def quoted_demo_facts(text: str) -> tuple[set[str], set[str]]:
    """Numbers and hop-class words the hero path quotes, skipping synthetic labels."""
    numbers: set[str] = set()
    relations: set[str] = set()
    for block in _paragraphs(text):
        if _synthetic(block):
            continue
        for match in STRENGTH.finditer(block):
            numbers.add(match.group(1))
        for match in HANDWRITTEN.finditer(block):
            numbers.add(match.group(0))
        for sentence in SENTENCE.findall(block):
            if not HERO.search(sentence):
                continue
            lowered = sentence.lower()
            for word in RELATION_WORDS:
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    relations.add(word)
    return numbers, relations


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}"


def _run_presets(tmp_path: Path) -> list[dict]:
    graph = Graph(tmp_path / "demo.db")
    seed_offline_presets(graph)
    fixtures = {row["id"]: row for row in load_demo_fixtures()}
    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    out = []
    for ident, depth in (
        ("nutrition-harvard-vitamin-d", 2),
        ("nutrition-olive-oil", 3),
        ("nutrition-healthline", 2),
        ("clean-jsps", 2),
    ):
        row = fixtures[ident]
        payload = check_answer(row["text"], row["urls"], row["engine"], depth, graph=graph)
        payload["_id"] = ident
        payload["_expected"] = recorded[ident]["decision"]
        out.append(payload)
    return out


def test_recorded_presets_match_docs_and_captions(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    recorded = load_recorded_presets()
    assert recorded["presets"], "recorded presets are missing"
    for spec in recorded["presets"]:
        assert spec.get("fetch_date"), spec["id"]
        assert str(spec.get("label") or "").startswith("recorded live run on "), spec["id"]
        if spec["id"] == "not-in-graph":
            assert spec.get("hops") in ([], None)
            digest = str(
                (spec.get("sources") or [{}])[0].get("content_hash")
                or spec.get("content_hash")
                or ""
            )
            assert len(digest) == 64, spec["id"]
            assert set(digest) <= set("0123456789abcdef"), spec["id"]
            continue
        assert spec["hops"], spec["id"]
        assert all(hop.get("recorded_at") for hop in spec["hops"]), spec["id"]
        for hop in spec["hops"]:
            digest = str(hop.get("content_hash") or "")
            assert len(digest) == 64, spec["id"]
            assert set(digest) <= set("0123456789abcdef"), spec["id"]

    payloads = _run_presets(tmp_path)
    observed_numbers: set[str] = set()
    observed_relations: set[str] = set()
    by_id = {}
    for payload in payloads:
        by_id[payload["_id"]] = payload
        assert payload["decision"] == payload["_expected"], payload["_id"]
        assert payload["api_calls"] == 0, payload["_id"]
        strength = (payload.get("algorithm") or {}).get("strength")
        if strength is not None:
            observed_numbers.add(_fmt(strength))
            observed_numbers.add(f"{float(strength):g}")
        for reason in payload.get("reasons") or []:
            if reason.get("path_score") is not None:
                observed_numbers.add(_fmt(float(reason["path_score"])))
                observed_numbers.add(f"{float(reason['path_score']):g}")
            if reason.get("reliance"):
                observed_relations.add(str(reason["reliance"]))
            if reason.get("weight") is not None:
                observed_numbers.add(_fmt(float(reason["weight"])))
                observed_numbers.add(f"{float(reason['weight']):g}")
            for hop in reason.get("hops_evidence") or []:
                if hop.get("reliance"):
                    observed_relations.add(str(hop["reliance"]))
                if hop.get("weight") is not None:
                    observed_numbers.add(_fmt(float(hop["weight"])))
                    observed_numbers.add(f"{float(hop['weight']):g}")
        summary = format_summary(payload)
        for match in STRENGTH.finditer(summary):
            observed_numbers.add(match.group(1))

    blocked = by_id["nutrition-harvard-vitamin-d"]
    assert blocked["decision"] == "block"
    assert _fmt((blocked.get("algorithm") or {}).get("strength")) == "0.47"
    block_hops = {
        hop.get("reliance")
        for reason in blocked.get("reasons") or []
        for hop in reason.get("hops_evidence") or []
    }
    assert "uses_data_or_method" in block_hops
    assert "mention" in block_hops

    olive = by_id["nutrition-olive-oil"]
    assert olive["decision"] == "warn"
    assert olive["exit_code"] == 2
    assert _fmt((olive.get("algorithm") or {}).get("strength")) == "0.30"
    assert "Estruch 2013" in olive["summary"]
    assert "did not appear to rely" in olive["summary"]
    olive_hops = {
        hop.get("reliance")
        for reason in olive.get("reasons") or []
        for hop in reason.get("hops_evidence") or []
    }
    assert olive_hops == {"mention"}

    hero = by_id["nutrition-healthline"]
    assert hero["decision"] == "warn"
    assert _fmt((hero.get("algorithm") or {}).get("strength")) == "0.55"
    hop_words = {
        hop.get("reliance")
        for reason in hero.get("reasons") or []
        for hop in reason.get("hops_evidence") or []
    }
    assert "relies" in hop_words
    assert "mention" in hop_words

    caption = ""
    readme = (ROOT / "README.md").read_text()
    if "](assets/healthline-warn.png)" in readme:
        caption = readme.split("](assets/healthline-warn.png)", 1)[1]
        caption = caption.split("\n## ", 1)[0]
    texts = [path.read_text() for path in DOCS]
    texts.append(caption)
    for text in texts:
        numbers, relations = quoted_demo_facts(text)
        missing_n = sorted(numbers - observed_numbers)
        missing_r = sorted(relations - observed_relations)
        assert not missing_n, f"doc quotes numbers {missing_n} missing from preset run {sorted(observed_numbers)}"
        assert not missing_r, f"doc quotes relations {missing_r} missing from preset run {sorted(observed_relations)}"
