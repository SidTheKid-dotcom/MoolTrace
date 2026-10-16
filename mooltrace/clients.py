"""Thin wrappers over OpenAlex, Crossref, and the NCBI id converter.

These are the public APIs. MoolTrace does not keep its own citation index.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import httpx

from mooltrace.config import (
    CACHE_MAX,
    CROSSREF_MAX_RPS,
    DIABETES_CARE_ISSNS,
    HTTP_CACHE_TTL_S,
    HTTP_MAX_BYTES,
    HTTP_RETRY_AFTER_CAP_S,
    HTTP_RETRY_ATTEMPTS,
    MAILTO,
    MAX_REDIRECTS,
    NCBI_MAX_RPS,
    NOTICE_REFRESH_TTL_S,
    OPENALEX_MAX_RPS,
    PAGE_USER_AGENT,
    USER_AGENT,
)
from mooltrace.ids import clean_doi, diabetes_care_doi, page_title, valid_doi
from mooltrace.ssrf import UnsafeURL, public_http_url, redirect_target

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
DATACITE = "https://api.datacite.org"
DOI_ORG = "https://doi.org"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_NOTICE_HOSTS = {
    "api.crossref.org",
    "api.datacite.org",
    "doi.org",
    "dx.doi.org",
    "api.retractionwatch.com",
    "www.ebi.ac.uk",
}


class MoolTraceError(Exception):
    """A public API or product failure the caller should surface."""

    code = "error"


class InfraError(Exception):
    """Graph timeout, process crash, or exhausted upstream budget.

    Not a MoolTraceError: ingest catches those and turns them into a warn.
    Exhausted 429/5xx must leave the check as infra (exit 3).
    """

    code = "infra"


@dataclass
class CallStats:
    api_calls: int = 0
    cache_hits: int = 0
    by_host: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def bump(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            self.api_calls += 1
            self.by_host[host] = self.by_host.get(host, 0) + 1

    def hit(self, n: int = 1) -> None:
        with self._lock:
            self.cache_hits += n


class _Limiter:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self.interval - (now - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


def _rps_interval(rps: float) -> float:
    return 1.0 / max(0.1, float(rps))


_HOST_RPS = {
    "api.openalex.org": OPENALEX_MAX_RPS,
    "api.crossref.org": CROSSREF_MAX_RPS,
    "www.ncbi.nlm.nih.gov": NCBI_MAX_RPS,
}

_limiters: dict[str, _Limiter] = {}
_limiters_lock = threading.Lock()
_client_lock = threading.Lock()
_client: httpx.Client | None = None
_pages: OrderedDict[str, tuple[str, str]] = OrderedDict()
_resources: OrderedDict[str, tuple[int, str, bytes]] = OrderedDict()
_pages_lock = threading.Lock()
_resources_lock = threading.Lock()
_json_lock = threading.Lock()


def _limiter_for(url: str) -> _Limiter:
    host = urlparse(url).netloc.lower()
    with _limiters_lock:
        limiter = _limiters.get(host)
        if limiter is None:
            rps = _HOST_RPS.get(host, min(OPENALEX_MAX_RPS, 8.0))
            limiter = _Limiter(_rps_interval(rps))
            _limiters[host] = limiter
        return limiter


def _cache_dir() -> Path:
    raw = os.environ.get("MOOLTRACE_HTTP_CACHE")
    if raw:
        return Path(raw)
    from mooltrace.config import DB_PATH

    return Path(os.environ.get("MOOLTRACE_DB", str(DB_PATH))).parent / "http-cache"


def _cache_key(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "mailto"
    ]
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            "",
        )
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def _now_ts() -> float:
    return time.time()


def _is_notice_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host in _NOTICE_HOSTS:
        return True
    if host == "api.openalex.org" and "/works/doi:" in path:
        return True
    return False


def _ttl_for(url: str) -> float | None:
    """Seconds the cached body stays valid. None means do not use the cache."""
    if _is_notice_url(url):
        ttl = NOTICE_REFRESH_TTL_S
        if ttl <= 0:
            return None
        return float(ttl)
    return float(HTTP_CACHE_TTL_S)


def _disk_entry(url: str) -> dict[str, Any] | None:
    ttl = _ttl_for(url)
    if ttl is None:
        return None
    path = _cache_dir() / _cache_key(url)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or "status" not in payload:
        return None
    status = int(payload["status"])
    if status == 429 or status >= 500:
        return None
    cached_at = payload.get("cached_at")
    if cached_at is None and _is_notice_url(url):
        return None
    stamp = float(cached_at) if cached_at is not None else 0.0
    if _now_ts() - stamp > ttl:
        return None
    return payload


def _disk_get(url: str) -> tuple[int, Any] | None:
    payload = _disk_entry(url)
    if payload is None:
        return None
    return int(payload["status"]), payload.get("body")


def _record_cached_trail(url: str, payload: dict[str, Any]) -> None:
    from mooltrace.evidence import record_fetch_trail, utc_iso

    body = payload.get("body")
    if body is None:
        return
    stamp = payload.get("cached_at")
    fetched_at = utc_iso(float(stamp)) if stamp is not None else None
    record_fetch_trail(
        url,
        body,
        fetched_at,
        content_hash=payload.get("sha256") if isinstance(payload.get("sha256"), str) else None,
    )


def _disk_set(url: str, status: int, body: Any, sha256: str | None = None) -> None:
    from mooltrace.evidence import content_sha256, hashable_body, record_fetch_trail, utc_iso

    directory = _cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _cache_key(url)
    tmp = path.with_suffix(".tmp")
    stamp = _now_ts()
    digest = sha256 or (content_sha256(hashable_body(body)) if body is not None else "")
    blob = json.dumps(
        {"status": int(status), "body": body, "cached_at": stamp, "sha256": digest},
        ensure_ascii=True,
    )
    with _json_lock:
        tmp.write_text(blob, encoding="utf-8")
        tmp.replace(path)
    if body is not None and digest:
        record_fetch_trail(url, body, utc_iso(stamp), content_hash=digest)


def _retry_after_s(response: httpx.Response) -> float | None:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return min(HTTP_RETRY_AFTER_CAP_S, max(0.0, float(raw)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
        delay = when.timestamp() - time.time()
        return min(HTTP_RETRY_AFTER_CAP_S, max(0.0, delay))
    except (TypeError, ValueError, OverflowError):
        return None


def _backoff(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return retry_after
    base = 0.4 * (2**attempt)
    return min(30.0, base + random.uniform(0.0, 0.3 * base))


def reset_http_state() -> None:
    """Drop in-memory HTTP state. Tests use this between cases."""
    global _client
    from mooltrace.evidence import clear_fetch_trails

    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None
    with _pages_lock:
        _pages.clear()
    with _resources_lock:
        _resources.clear()
    with _limiters_lock:
        _limiters.clear()
    clear_fetch_trails()


def _lru_get(cache: OrderedDict, lock: threading.Lock, key: str):
    with lock:
        if key not in cache:
            return None
        cache.move_to_end(key)
        return cache[key]


def _lru_set(cache: OrderedDict, lock: threading.Lock, key: str, value: Any) -> None:
    with lock:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > CACHE_MAX:
            cache.popitem(last=False)


def _http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                timeout=httpx.Timeout(40.0, connect=15.0),
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        return _client


def close_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


def request_json(
    url: str,
    stats: CallStats,
    headers: dict[str, str] | None = None,
    *,
    as_text: bool = False,
) -> tuple[int, Any]:
    """GET a URL. 429 returns immediately (Semantic Scholar). 404 returns ``(404, None)``."""
    cached = _disk_entry(url)
    if cached is not None:
        stats.hit()
        _record_cached_trail(url, cached)
        status, body = int(cached["status"]), cached.get("body")
        if as_text and not isinstance(body, str):
            return status, json.dumps(body) if body is not None else ""
        return status, body
    last_error: Exception | None = None
    attempts = max(1, HTTP_RETRY_ATTEMPTS)
    for attempt in range(attempts):
        _limiter_for(url).wait()
        stats.bump(url)
        try:
            response = _http().get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(_backoff(attempt, None))
            continue
        code = response.status_code
        if code == 404:
            _disk_set(url, 404, None)
            return 404, None
        if code == 429:
            return 429, None
        if code in {500, 502, 503}:
            last_error = MoolTraceError(f"{code} from {urlparse(url).netloc}")
            if attempt + 1 < attempts:
                time.sleep(_backoff(attempt, _retry_after_s(response)))
            continue
        if code >= 400:
            raise MoolTraceError(
                f"{code} from {urlparse(url).netloc}: {response.text[:180]}"
            )
        from mooltrace.evidence import content_sha256

        raw_hash = content_sha256(response.content)
        if as_text:
            text = response.text
            _disk_set(url, code, text, sha256=raw_hash)
            return code, text
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        _disk_set(url, code, payload, sha256=raw_hash)
        return code, payload
    raise MoolTraceError(f"giving up on {urlparse(url).netloc}: {last_error}")


def _get_json(url: str, stats: CallStats, headers: dict[str, str] | None = None) -> Any:
    cached = _disk_entry(url)
    if cached is not None:
        stats.hit()
        _record_cached_trail(url, cached)
        status, body = int(cached["status"]), cached.get("body")
        if status == 404:
            return None
        return body
    last_error: Exception | None = None
    host = urlparse(url).netloc
    attempts = max(1, HTTP_RETRY_ATTEMPTS)
    for attempt in range(attempts):
        _limiter_for(url).wait()
        stats.bump(url)
        try:
            response = _http().get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(_backoff(attempt, None))
            continue
        code = response.status_code
        if code == 404:
            _disk_set(url, 404, None)
            return None
        if code in {429, 500, 502, 503}:
            last_error = InfraError(f"{code} from {host}")
            retry_after = _retry_after_s(response)
            # A Retry-After at the cap means the daily window is exhausted.
            # Waiting and hitting the same URL again will not recover it.
            if code == 429 and retry_after is not None and retry_after >= HTTP_RETRY_AFTER_CAP_S:
                break
            if attempt + 1 < attempts:
                time.sleep(_backoff(attempt, retry_after))
            continue
        if code >= 400:
            raise MoolTraceError(f"{code} from {host}: {response.text[:180]}")
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        _disk_set(url, code, payload)
        return payload
    raise InfraError(f"giving up on {host}: {last_error}")


def _oa(path_and_query: str, stats: CallStats) -> Any:
    join = "&" if "?" in path_and_query else "?"
    url = f"{OPENALEX}{path_and_query}{join}mailto={quote(MAILTO)}"
    return _get_json(url, stats)


def openalex_work_doi(doi: str, stats: CallStats) -> dict[str, Any] | None:
    data = _oa(
        f"/works/doi:{quote(doi, safe='')}"
        "?select=id,doi,display_name,publication_year,is_retracted,"
        "cited_by_count,referenced_works,type,ids,authorships",
        stats,
    )
    return data if isinstance(data, dict) and data.get("id") else None


def openalex_work_pmid(pmid: str, stats: CallStats) -> dict[str, Any] | None:
    data = _oa(f"/works/pmid:{pmid}?select=id,doi,display_name,publication_year", stats)
    return data if isinstance(data, dict) and data.get("id") else None


def openalex_context_record(doi: str, stats: CallStats) -> dict[str, Any] | None:
    """Abstract, ids, and open-access locations for a citing work."""
    data = _oa(
        f"/works/doi:{quote(doi, safe='')}"
        "?select=id,display_name,ids,abstract_inverted_index,open_access,"
        "primary_location,locations",
        stats,
    )
    return data if isinstance(data, dict) and data.get("id") else None


def _openalex_one(path: str, stats: CallStats) -> dict[str, Any] | None:
    data = _oa(path, stats)
    return data if isinstance(data, dict) and data.get("id") else None


def openalex_by_ids(openalex_ids: list[str], stats: CallStats) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ids = [item.rsplit("/", 1)[-1] for item in openalex_ids if item]
    select = "id,doi,display_name,publication_year,is_retracted,cited_by_count,type"
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        filt = "|".join(chunk)
        try:
            data = _oa(
                f"/works?filter=openalex_id:{filt}&per-page=50&select={select}",
                stats,
            )
        except InfraError:
            data = None
        if isinstance(data, dict):
            results.extend(data.get("results") or [])
            continue
        for item in chunk:
            record = _openalex_one(f"/works/{quote(item, safe='')}?select={select}", stats)
            if record:
                results.append(record)
    return results


def openalex_by_dois(dois: list[str], stats: CallStats) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    select = (
        "id,doi,display_name,publication_year,is_retracted,"
        "cited_by_count,referenced_works,type"
    )
    for start in range(0, len(dois), 25):
        chunk = dois[start : start + 25]
        # Slashes in DOIs must stay literal; OpenAlex rejects %2F inside filter.
        filt = "|".join(quote(doi, safe="/") for doi in chunk)
        try:
            data = _oa(
                f"/works?filter=doi:{filt}&per-page=25&select={select}",
                stats,
            )
        except InfraError:
            data = None
        if isinstance(data, dict):
            results.extend(data.get("results") or [])
            continue
        for doi in chunk:
            record = openalex_work_doi(doi, stats)
            if record:
                results.append(record)
    return results


def _diabetes_care_issn_match(message: dict[str, Any]) -> bool:
    raw: list[Any] = list(message.get("ISSN") or [])
    for item in message.get("issn-type") or []:
        if isinstance(item, dict):
            raw.append(item.get("value"))
        else:
            raw.append(item)
    found = {str(item).replace("-", "") for item in raw if item}
    expected = {issn.replace("-", "") for issn in DIABETES_CARE_ISSNS}
    return bool(found & expected)


def openalex_diabetes_care(
    volume: str, issue: str, page: str, stats: CallStats
) -> str | None:
    """Resolve a Diabetes Care landing URL (volume/issue/page) to one DOI."""
    for issn in DIABETES_CARE_ISSNS:
        data = _oa(
            "/works?filter="
            f"primary_location.source.issn:{issn},"
            f"biblio.volume:{volume},biblio.issue:{issue},biblio.first_page:{page}"
            "&per-page=1&select=id,doi,display_name",
            stats,
        )
        results = (data or {}).get("results") if isinstance(data, dict) else None
        if results:
            doi = clean_doi(results[0].get("doi") or "")
            if valid_doi(doi):
                return doi
    return None


def resolve_diabetes_care(
    volume: str, issue: str, page: str, stats: CallStats
) -> str | None:
    """Prefer Crossref on the ADA DOI pattern; OpenAlex is the fallback.

    Everyday Health cites Khan via diabetesjournals.org/care/article/26/12/3215
    with no DOI on the page. OpenAlex 429 must not strand that hop.
    """
    candidate = diabetes_care_doi(volume, issue, page)
    if valid_doi(candidate):
        message = crossref_work(candidate, stats)
        if isinstance(message, dict) and _diabetes_care_issn_match(message):
            doi = clean_doi(message.get("DOI") or candidate)
            if valid_doi(doi):
                return doi
    return openalex_diabetes_care(volume, issue, page, stats)


def crossref_works(dois: list[str], stats: CallStats) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for start in range(0, len(dois), 20):
        chunk = dois[start : start + 20]
        filt = ",".join(f"doi:{quote(doi, safe='/')}" for doi in chunk)
        url = (
            f"{CROSSREF}/works?rows={len(chunk)}"
            f"&select=DOI,title,author,updated-by,update-to,type,issued"
            f"&filter={filt}"
        )
        data = _get_json(url, stats)
        if isinstance(data, dict):
            items.extend((data.get("message") or {}).get("items") or [])
    return items


def crossref_work(doi: str, stats: CallStats) -> dict[str, Any] | None:
    url = f"{CROSSREF}/works/{quote(doi, safe='/')}"
    data = _get_json(url, stats)
    if not isinstance(data, dict):
        return None
    return data.get("message")


def datacite_registered(doi: str) -> bool:
    """True for arXiv (10.48550) and Zenodo (10.5281) DOIs DataCite registers."""
    text = (doi or "").strip().lower()
    return text.startswith("10.48550/") or text.startswith("10.5281/")


def _datacite_family(attrs: dict[str, Any]) -> str | None:
    creators = attrs.get("creators") or []
    if not creators or not isinstance(creators[0], dict):
        return None
    family = str(creators[0].get("familyName") or "").strip()
    if family:
        return family
    name = str(creators[0].get("name") or "").strip()
    if "," in name:
        left = name.split(",", 1)[0].strip()
        return left or None
    parts = [part for part in name.replace(".", " ").split() if len(part) > 2]
    return parts[-1] if parts else None


def datacite_work(doi: str, stats: CallStats) -> dict[str, Any] | None:
    """Resolve a DOI that Crossref and OpenAlex miss (arXiv, Zenodo, DataCite)."""
    url = f"{DATACITE}/dois/{quote(doi, safe='')}"
    data = _get_json(url, stats, headers={"Accept": "application/vnd.api+json"})
    if not isinstance(data, dict):
        return None
    attrs = ((data.get("data") or {}).get("attributes") or {})
    if not isinstance(attrs, dict) or not attrs:
        return None
    titles = attrs.get("titles") or []
    title = None
    if titles and isinstance(titles[0], dict):
        title = titles[0].get("title")
    elif titles:
        title = str(titles[0])
    year = attrs.get("publicationYear")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    resolved = clean_doi(str(attrs.get("doi") or doi))
    if not valid_doi(resolved):
        return None
    return {
        "doi": resolved,
        "title": title,
        "year": year,
        "publisher": attrs.get("publisher"),
        "first_author": _datacite_family(attrs),
        "source": "datacite",
    }


def doi_org_csl(doi: str, stats: CallStats) -> dict[str, Any] | None:
    """doi.org content negotiation. Last resolver after DataCite."""
    url = f"{DOI_ORG}/{quote(doi, safe='/')}"
    data = _get_json(
        url,
        stats,
        headers={"Accept": "application/vnd.citationstyles.csl+json"},
    )
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    year = None
    issued = data.get("issued") or data.get("published") or {}
    parts = (issued.get("date-parts") or [[]])[0] if isinstance(issued, dict) else []
    if parts:
        try:
            year = int(parts[0])
        except (TypeError, ValueError):
            year = None
    resolved = clean_doi(str(data.get("DOI") or data.get("doi") or doi))
    if not valid_doi(resolved):
        return None
    return {
        "doi": resolved,
        "title": title,
        "year": year,
        "container": data.get("container-title"),
        "source": "doi.org",
    }


def pmc_to_doi(pmcids: list[str], stats: CallStats) -> dict[str, str]:
    found: dict[str, str] = {}
    for start in range(0, len(pmcids), 40):
        chunk = pmcids[start : start + 40]
        ids = ",".join(chunk)
        url = (
            f"{IDCONV}?ids={ids}&format=json&tool=mooltrace&email={quote(MAILTO)}"
        )
        data = _get_json(url, stats)
        for record in (data or {}).get("records") or []:
            doi = clean_doi(record.get("doi") or "")
            if valid_doi(doi):
                found[record.get("requested-id", "").upper()] = doi
    return found


def _read_limited(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > HTTP_MAX_BYTES:
            chunks.append(chunk[: max(0, HTTP_MAX_BYTES - (size - len(chunk)))])
            break
        chunks.append(chunk)
    return b"".join(chunks)[:HTTP_MAX_BYTES]


def _public_get(
    url: str,
    stats: CallStats,
    headers: dict[str, str],
) -> tuple[str, int, str, bytes]:
    current = public_http_url(url, reason="fetch")
    last_error: Exception | None = None
    request_headers = {**headers, "Accept-Encoding": "identity"}
    for _hop in range(MAX_REDIRECTS + 1):
        # Re-resolve immediately before connect so a DNS change cannot
        # sneak a private hop past the first check.
        public_http_url(current, reason="fetch")
        _limiter_for(current).wait()
        stats.bump(current)
        try:
            with _http().stream(
                "GET",
                current,
                headers=request_headers,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    current = redirect_target(current, response.headers.get("location"))
                    continue
                body = _read_limited(response)
                ctype = response.headers.get("content-type") or ""
                return str(response.url), response.status_code, ctype, body
        except UnsafeURL:
            raise
        except httpx.HTTPError as exc:
            last_error = exc
            break
    if last_error is not None:
        raise MoolTraceError(f"could not fetch {url}: {last_error}") from last_error
    raise MoolTraceError(f"could not fetch {url}: too many redirects")


def fetch_page(url: str, stats: CallStats) -> tuple[str, str]:
    """Return (final_url, html). Raises MoolTraceError on a hard failure.

    The same process reuses the body, so a later citation judgment does not
    download the page again. Destinations are public http(s) only.
    """
    cached = _lru_get(_pages, _pages_lock, url)
    if cached is not None:
        stats.hit()
        final, text = cached[0], cached[1]
        fetched_at = cached[2] if len(cached) > 2 else None
        from mooltrace.evidence import record_fetch_trail

        record_fetch_trail(url, text, fetched_at)
        if final != url:
            record_fetch_trail(final, text, fetched_at)
        return final, text
    try:
        final, status, _ctype, body = _public_get(
            url,
            stats,
            {"User-Agent": PAGE_USER_AGENT, "Accept": "text/html"},
        )
    except UnsafeURL as exc:
        raise MoolTraceError(f"refused {url}: {exc}") from exc
    if status >= 400:
        raise MoolTraceError(f"could not fetch {url}: HTTP {status}")
    from mooltrace.evidence import record_fetch_trail, utc_iso

    text = body.decode("utf-8", "replace")
    fetched_at = utc_iso()
    record_fetch_trail(url, text, fetched_at)
    record_fetch_trail(final, text, fetched_at)
    stored = (final, text, fetched_at)
    _lru_set(_pages, _pages_lock, url, stored)
    _lru_set(_pages, _pages_lock, final, stored)
    return final, text


def fetch_resource(url: str, stats: CallStats) -> tuple[int, str, bytes]:
    """GET a page or file and cache the status, type, and body.

    A 403 or 404 is cached too, so a closed publisher page is not requested
    twice in the same process. Destinations are public http(s) only.
    """
    cached = _lru_get(_resources, _resources_lock, url)
    if cached is not None:
        stats.hit()
        status, ctype, body = cached[0], cached[1], cached[2]
        if body:
            from mooltrace.evidence import record_fetch_trail

            fetched_at = cached[3] if len(cached) > 3 else None
            record_fetch_trail(url, body, fetched_at)
        return status, ctype, body
    try:
        final, status, ctype, body = _public_get(
            url,
            stats,
            {
                "User-Agent": PAGE_USER_AGENT,
                "Accept": "text/html,application/pdf,application/xml,*/*",
            },
        )
    except (UnsafeURL, MoolTraceError):
        # Optional OA/PDF fetches must miss closed, not abort the check.
        stored = (0, "", b"")
        _lru_set(_resources, _resources_lock, url, stored)
        return stored
    from mooltrace.evidence import record_fetch_trail, utc_iso

    fetched_at = utc_iso()
    if body:
        record_fetch_trail(url, body, fetched_at)
        if final != url:
            record_fetch_trail(final, body, fetched_at)
    stored = (status, ctype, body, fetched_at)
    _lru_set(_resources, _resources_lock, url, stored)
    if final != url:
        _lru_set(_resources, _resources_lock, final, stored)
    return status, ctype, body


def reference_dois(message: dict[str, Any] | None) -> list[str]:
    dois: list[str] = []
    seen: set[str] = set()
    for ref in (message or {}).get("reference") or []:
        doi = clean_doi(ref.get("DOI") or ref.get("doi") or "")
        if valid_doi(doi) and doi not in seen:
            seen.add(doi)
            dois.append(doi)
    return dois


def openalex_doi(record: dict[str, Any]) -> str:
    return clean_doi(record.get("doi") or "")


def openalex_id(record: dict[str, Any]) -> str:
    raw = record.get("id") or ""
    return raw.rsplit("/", 1)[-1]


def html_title(html_text: str) -> str:
    return page_title(html_text)
