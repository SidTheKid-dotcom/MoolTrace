"""Read-only hosted demo: four presets, no live HTTP, no arbitrary URLs.

Set MOOLTRACE_PUBLIC_DEMO=1. Live catalog calls stay off. Arbitrary URL
fetching stays off unless MOOLTRACE_PUBLIC_LIVE=1, and then only with the
SSRF guard plus the in-process rate limit.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from mooltrace.config import ROOT

PUBLIC_LIVE_PER_MIN = 10
MAX_DRAFT_CHARS = 32_000
MAX_URLS = 16
MAX_URL_CHARS = 2_048
MAX_DOI_CHARS = 256
RECORDED_PRESETS = ROOT / "examples" / "presets_recorded.json"


class PublicDemoRejected(Exception):
    """Public demo refused this input. status_code is the HTTP equivalent."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

_lock = threading.Lock()
_hits: list[float] = []


def public_demo_enabled() -> bool:
    return os.environ.get("MOOLTRACE_PUBLIC_DEMO", "").strip() == "1"


def public_live_enabled() -> bool:
    return os.environ.get("MOOLTRACE_PUBLIC_LIVE", "").strip() == "1"


def live_per_min() -> int:
    raw = os.environ.get("MOOLTRACE_PUBLIC_LIVE_PER_MIN", "").strip()
    if not raw:
        return PUBLIC_LIVE_PER_MIN
    try:
        return max(1, int(raw))
    except ValueError:
        return PUBLIC_LIVE_PER_MIN


def draft_too_large(text: str, urls: list[str] | None) -> bool:
    if len(text or "") > MAX_DRAFT_CHARS:
        return True
    items = _norm_urls(urls)
    if len(items) > MAX_URLS:
        return True
    return any(len(item) > MAX_URL_CHARS for item in items)


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


def load_recorded_presets() -> dict[str, Any]:
    payload = json.loads(RECORDED_PRESETS.read_text())
    if not isinstance(payload, dict) or not payload.get("presets"):
        raise SystemExit(f"recorded presets missing in {RECORDED_PRESETS}")
    return payload


def is_preset(engine: str, text: str, urls: list[str] | None) -> bool:
    key = preset_key(engine, text, urls)
    for row in load_preset_rows():
        if preset_key(str(row.get("engine") or ""), str(row.get("text") or ""), row.get("urls") or []) == key:
            return True
    return False


def doi_too_large(doi: str) -> bool:
    return len(doi or "") > MAX_DOI_CHARS


def is_preset_doi(doi: str) -> bool:
    raw = (doi or "").strip().lower()
    if not raw:
        return False
    for spec in load_recorded_presets().get("presets") or []:
        for notice in spec.get("notices") or []:
            if str(notice.get("doi") or "").strip().lower() == raw:
                return True
        for work in spec.get("works") or []:
            if str(work.get("doi") or "").strip().lower() == raw:
                return True
    return False


def guard_public_check(engine: str, text: str, urls: list[str] | None) -> None:
    """Refuse unsafe or non-preset drafts on the public demo.

    Presets return immediately so they never consume the rate limit.
    """
    if not public_demo_enabled():
        return
    if is_preset(engine, text, urls):
        return
    if draft_too_large(text, urls):
        raise PublicDemoRejected(413, "Draft or URL list is too large for the public demo.")
    if public_live_enabled():
        from mooltrace.ssrf import public_http_url

        for url in urls or []:
            public_http_url(url, reason="url")
    if rate_limited():
        raise PublicDemoRejected(429, "Public demo rate limit. Try the four presets.")
    if public_live_enabled():
        return
    raise PublicDemoRejected(
        400,
        (
            "This public demo only runs the four presets (Healthline olive oil block, "
            "Healthline cinnamon warn, clean pass, NHS not-in-the-graph) with no live "
            "page fetch. Clone the repo to check other URLs."
        ),
    )


def guard_remote_check(engine: str, text: str, urls: list[str] | None) -> None:
    """Size-cap and SSRF-guard the remote MCP check, then apply the public demo rules."""
    if is_preset(engine, text, urls):
        return
    if draft_too_large(text, urls):
        raise PublicDemoRejected(413, "Draft or URL list is too large for the public demo.")
    if public_demo_enabled():
        guard_public_check(engine, text, urls)
        return
    from mooltrace.ssrf import public_http_url

    for url in urls or []:
        public_http_url(url, reason="url")


def guard_remote_doi(doi: str) -> None:
    """Size-cap a reverse-lookup DOI. Preset notice DOIs never hit the rate limit."""
    if doi_too_large(doi):
        raise PublicDemoRejected(413, "DOI is too large for the public demo.")
    if not public_demo_enabled():
        return
    if is_preset_doi(doi):
        return
    if rate_limited():
        raise PublicDemoRejected(429, "Public demo rate limit. Try the four presets.")
    if public_live_enabled():
        return
    raise PublicDemoRejected(
        400,
        "This public demo only looks up notice DOIs from the four presets. Clone the repo for the full graph.",
    )


def rate_limited() -> bool:
    now = time.monotonic()
    with _lock:
        while _hits and now - _hits[0] > 60:
            _hits.pop(0)
        if len(_hits) >= live_per_min():
            return True
        _hits.append(now)
        return False


def _paste_url(answer_id: str) -> str:
    return f"urn:mooltrace:paste:{answer_id}"


def _source_url(spec: dict[str, Any], answer_id: str) -> str:
    raw = str(spec.get("url") or "")
    if raw == "paste":
        return _paste_url(answer_id)
    return raw


def seed_offline_presets(graph: Any) -> list[dict[str, str]]:
    """Write the four UI presets from recorded fetches, with no HTTP."""
    from mooltrace.trace import _answer_id, _text_hash

    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    seeded: list[dict[str, str]] = []
    for row in load_preset_rows():
        engine = str(row.get("engine") or "draft")
        text = str(row.get("text") or "")
        urls = _norm_urls(row.get("urls") or [])
        ident = str(row.get("id") or engine)
        spec = recorded.get(ident)
        if spec is None:
            raise SystemExit(f"recorded preset missing id {ident}")
        answer_id = _answer_id(engine, text, urls)
        created = str(spec.get("fetch_date") or "")
        for source in spec.get("sources") or []:
            created = str(source.get("fetched_at") or created)
            break
        graph.merge_answer(answer_id, engine, _text_hash(text), created)
        for source in spec.get("sources") or []:
            url = _source_url(source, answer_id)
            graph.merge_source(
                url,
                str(source.get("title") or ""),
                str(source.get("site") or ""),
                True,
                fetched_at=str(source.get("fetched_at") or created),
            )
            graph.cite(answer_id, url)
        for work in spec.get("works") or []:
            fields = {
                key: work[key]
                for key in (
                    "title",
                    "year",
                    "first_author",
                    "expanded",
                    "notice_checked",
                    "notice_checked_at",
                )
                if key in work
            }
            graph.merge_work(str(work["doi"]), **fields)
        for hop in spec.get("hops") or []:
            target = str(hop["to_doi"])
            source_doi = hop.get("from_doi")
            if source_doi:
                graph.rest_on(str(source_doi), target)
                graph.set_reliance(
                    str(source_doi),
                    None,
                    target,
                    reliance=str(hop["reliance"]),
                    weight=float(hop["weight"]),
                    sentence=str(hop.get("sentence") or ""),
                    evidence_from=str(hop.get("evidence_from") or ""),
                    evidence_url=str(hop.get("source_url") or ""),
                    evidence_fetched_at=str(hop.get("fetched_at") or hop.get("recorded_at") or ""),
                    evidence_sha256=str(hop.get("content_hash") or ""),
                )
                continue
            url = _source_url({"url": hop.get("from_url")}, answer_id)
            graph.source_rests_on(url, target)
            graph.set_reliance(
                None,
                url,
                target,
                reliance=str(hop["reliance"]),
                weight=float(hop["weight"]),
                sentence=str(hop.get("sentence") or ""),
                evidence_from=str(hop.get("evidence_from") or ""),
                evidence_url=str(hop.get("source_url") or hop.get("from_url") or url),
                evidence_fetched_at=str(hop.get("fetched_at") or hop.get("recorded_at") or ""),
                evidence_sha256=str(hop.get("content_hash") or ""),
            )
        for notice in spec.get("notices") or []:
            graph.merge_notice(
                str(notice["doi"]),
                str(notice["work_doi"]),
                str(notice["type"]),
                str(notice["label"]),
                str(notice.get("source") or "publisher"),
                str(notice.get("date") or ""),
            )
        seeded.append({"id": ident, "decision": str(spec.get("decision") or "")})
    graph.persist()
    return seeded
