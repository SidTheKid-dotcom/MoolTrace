"""Read-only hosted demo: three presets, no live HTTP, no arbitrary URLs.

Set MOOLTRACE_PUBLIC_DEMO=1. Live catalog calls stay off. Arbitrary URL
fetching stays off unless MOOLTRACE_PUBLIC_LIVE=1, and then only with the
SSRF guard plus the in-process rate limit.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from mooltrace.config import (
    CLEAN_REWRITE_DOI,
    HEALTHLINE_CINNAMON_URL,
    KHAN_DOI,
    LANCET_HCQ_DOI,
    LANCET_RETRACTION_DOI,
    EOC_DOI,
)
NOW = "2026-10-16T08:00:00+00:00"
SILVA = "10.3390/nu14132773"
PUBLIC_LIVE_PER_MIN = int(os.environ.get("MOOLTRACE_PUBLIC_LIVE_PER_MIN", "10"))

_lock = threading.Lock()
_hits: list[float] = []


def public_demo_enabled() -> bool:
    return os.environ.get("MOOLTRACE_PUBLIC_DEMO", "").strip() == "1"


def public_live_enabled() -> bool:
    return os.environ.get("MOOLTRACE_PUBLIC_LIVE", "").strip() == "1"


def _norm_urls(urls: list[str] | None) -> list[str]:
    return [item.strip() for item in (urls or []) if item and item.strip()]


def preset_key(engine: str, text: str, urls: list[str] | None) -> tuple[str, str, tuple[str, ...]]:
    return (
        (engine or "").strip().lower(),
        (text or "").strip(),
        tuple(_norm_urls(urls)),
    )


def load_preset_rows() -> list[dict[str, Any]]:
    from mooltrace.seed import load_demo_fixtures

    return load_demo_fixtures()


def is_preset(engine: str, text: str, urls: list[str] | None) -> bool:
    key = preset_key(engine, text, urls)
    for row in load_preset_rows():
        if preset_key(str(row.get("engine") or ""), str(row.get("text") or ""), row.get("urls") or []) == key:
            return True
    return False


def rate_limited() -> bool:
    now = time.monotonic()
    with _lock:
        while _hits and now - _hits[0] > 60:
            _hits.pop(0)
        if len(_hits) >= PUBLIC_LIVE_PER_MIN:
            return True
        _hits.append(now)
        return False


def seed_offline_presets(graph: Any) -> list[dict[str, str]]:
    """Write the three UI presets into graph with no HTTP."""
    from mooltrace.trace import _answer_id, _text_hash

    rows = load_preset_rows()
    seeded: list[dict[str, str]] = []
    for row in rows:
        engine = str(row.get("engine") or "draft")
        text = str(row.get("text") or "")
        urls = _norm_urls(row.get("urls") or [])
        ident = str(row.get("id") or engine)
        answer_id = _answer_id(engine, text, urls)
        graph.merge_answer(answer_id, engine, _text_hash(text), NOW)
        if ident == "nutrition-healthline":
            url = urls[0] if urls else HEALTHLINE_CINNAMON_URL
            graph.merge_source(url, "Cinnamon and Diabetes", "healthline.com", True, fetched_at=NOW)
            graph.cite(answer_id, url)
            graph.merge_work(
                SILVA,
                title="Cinnamon as a Complementary Therapeutic Approach",
                year=2022,
                expanded=True,
                notice_checked=True,
                notice_checked_at=NOW,
            )
            graph.merge_work(
                KHAN_DOI,
                title="Cinnamon Improves Glucose and Lipids of People with Type 2 Diabetes",
                year=2003,
                expanded=True,
                notice_checked=True,
                notice_checked_at=NOW,
            )
            graph.source_rests_on(url, SILVA)
            graph.rest_on(SILVA, KHAN_DOI)
            graph.set_reliance(
                None,
                url,
                SILVA,
                reliance="uses_data_or_method",
                weight=0.85,
                sentence="The Healthline page cites Silva 2022 on cinnamon and blood sugar.",
                evidence_from="page",
            )
            graph.set_reliance(
                SILVA,
                None,
                KHAN_DOI,
                reliance="uses_data_or_method",
                weight=0.85,
                sentence="Silva 2022 included Khan 2003 among the reviewed trials.",
                evidence_from="pmc",
            )
            graph.merge_notice(
                EOC_DOI,
                KHAN_DOI,
                "expression_of_concern",
                "Expression of Concern",
                "publisher",
                "2025-08-20",
            )
            seeded.append({"id": ident, "decision": "warn"})
        elif ident == "lancet-hcq":
            paste = f"urn:mooltrace:paste:{answer_id}"
            graph.merge_source(paste, "Pasted draft", "paste", True, fetched_at=NOW)
            graph.cite(answer_id, paste)
            graph.merge_work(
                LANCET_HCQ_DOI,
                title="Hydroxychloroquine or chloroquine with or without a macrolide",
                year=2020,
                expanded=True,
                notice_checked=True,
                notice_checked_at=NOW,
            )
            graph.source_rests_on(paste, LANCET_HCQ_DOI)
            graph.set_reliance(
                None,
                paste,
                LANCET_HCQ_DOI,
                reliance="relies",
                weight=1.0,
                sentence="A draft patient note cites the 2020 Lancet registry analysis.",
                evidence_from="draft",
            )
            graph.merge_notice(
                LANCET_RETRACTION_DOI,
                LANCET_HCQ_DOI,
                "retraction",
                "Retraction",
                "publisher",
                "2020-06-05",
            )
            seeded.append({"id": ident, "decision": "block"})
        else:
            paste = f"urn:mooltrace:paste:{answer_id}"
            graph.merge_source(paste, "Pasted draft", "paste", True, fetched_at=NOW)
            graph.cite(answer_id, paste)
            graph.merge_work(
                CLEAN_REWRITE_DOI,
                title="Cinnamon in glycaemic control",
                year=2015,
                expanded=True,
                notice_checked=True,
                notice_checked_at=NOW,
            )
            graph.source_rests_on(paste, CLEAN_REWRITE_DOI)
            graph.set_reliance(
                None,
                paste,
                CLEAN_REWRITE_DOI,
                reliance="relies",
                weight=1.0,
                sentence="The draft cites 10.1016/j.jsps.2015.03.013.",
                evidence_from="draft",
            )
            seeded.append({"id": ident, "decision": "pass"})
    graph.persist()
    return seeded


