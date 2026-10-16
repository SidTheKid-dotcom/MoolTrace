"""Fetch evidence a judge can re-check: URL, UTC fetch date, SHA-256 of the body."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_TRAILS: dict[str, dict[str, str]] = {}


def content_sha256(body: str | bytes) -> str:
    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hashable_body(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def utc_iso(stamp: datetime | float | None = None) -> str:
    if stamp is None:
        when = datetime.now(timezone.utc)
    elif isinstance(stamp, (int, float)):
        when = datetime.fromtimestamp(float(stamp), tz=timezone.utc)
    elif stamp.tzinfo is None:
        when = stamp.replace(tzinfo=timezone.utc)
    else:
        when = stamp.astimezone(timezone.utc)
    return when.replace(microsecond=0).isoformat()


def record_fetch_trail(
    url: str,
    body: Any,
    fetched_at: str | None = None,
    *,
    content_hash: str | None = None,
) -> dict[str, str]:
    trail = {
        "source_url": url or "",
        "fetched_at": fetched_at or utc_iso(),
        "content_hash": content_hash or content_sha256(hashable_body(body)),
    }
    if url:
        with _lock:
            _TRAILS[url] = trail
    return trail


def fetch_trail(url: str) -> dict[str, str] | None:
    if not url:
        return None
    with _lock:
        found = _TRAILS.get(url)
        return dict(found) if found else None


def clear_fetch_trails() -> None:
    with _lock:
        _TRAILS.clear()


def public_hop_trail(hop: dict[str, Any] | None) -> dict[str, str]:
    row = hop or {}
    return {
        "source_url": str(row.get("source_url") or row.get("evidence_url") or ""),
        "fetched_at": str(row.get("fetched_at") or row.get("evidence_fetched_at") or ""),
        "content_hash": str(row.get("content_hash") or row.get("evidence_sha256") or ""),
    }


def attach_hop_trail(hop: Any) -> Any:
    if not isinstance(hop, dict):
        return hop
    out = dict(hop)
    out.update(public_hop_trail(out))
    return out
