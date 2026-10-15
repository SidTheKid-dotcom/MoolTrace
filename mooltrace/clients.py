"""Thin wrappers over OpenAlex, Crossref, and the NCBI id converter.

These are the public APIs. MoolTrace does not keep its own citation index.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from mooltrace.config import (
    CACHE_MAX,
    DIABETES_CARE_ISSNS,
    HTTP_MAX_BYTES,
    MAILTO,
    MAX_REDIRECTS,
    PAGE_USER_AGENT,
    USER_AGENT,
)
from mooltrace.ids import clean_doi, diabetes_care_doi, page_title, valid_doi
from mooltrace.ssrf import UnsafeURL, public_http_url, redirect_target

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"


class MoolTraceError(Exception):
    """A public API or product failure the caller should surface."""

    code = "error"


class InfraError(MoolTraceError):
    """Graph timeout, process crash, or exhausted upstream budget."""

    code = "infra"


@dataclass
class CallStats:
    api_calls: int = 0
    cache_hits: int = 0
    by_host: dict[str, int] = field(default_factory=dict)

    def bump(self, url: str) -> None:
        host = urlparse(url).netloc
        self.api_calls += 1
        self.by_host[host] = self.by_host.get(host, 0) + 1

    def hit(self, n: int = 1) -> None:
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


_limiter = _Limiter(0.1)
_client_lock = threading.Lock()
_client: httpx.Client | None = None
_pages: OrderedDict[str, tuple[str, str]] = OrderedDict()
_resources: OrderedDict[str, tuple[int, str, bytes]] = OrderedDict()
_pages_lock = threading.Lock()
_resources_lock = threading.Lock()


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
    """GET a URL. 429 returns immediately. 404 returns ``(404, None)``."""
    last_error: Exception | None = None
    for attempt in range(3):
        _limiter.wait()
        stats.bump(url)
        try:
            response = _http().get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
            continue
        code = response.status_code
        if code == 404:
            return 404, None
        if code == 429:
            return 429, None
        if code in {500, 502, 503}:
            last_error = MoolTraceError(f"{code} from {urlparse(url).netloc}")
            time.sleep(1.2 * (attempt + 1))
            continue
        if code >= 400:
            raise MoolTraceError(
                f"{code} from {urlparse(url).netloc}: {response.text[:180]}"
            )
        if as_text:
            return code, response.text
        try:
            return code, response.json()
        except ValueError:
            return code, response.text
    raise MoolTraceError(f"giving up on {urlparse(url).netloc}: {last_error}")


def _get_json(url: str, stats: CallStats, headers: dict[str, str] | None = None) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        _limiter.wait()
        stats.bump(url)
        try:
            response = _http().get(url, headers=headers, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
            continue
        if response.status_code == 404:
            return None
        if response.status_code in {429, 500, 502, 503}:
            last_error = MoolTraceError(f"{response.status_code} from {urlparse(url).netloc}")
            time.sleep(1.2 * (attempt + 1))
            continue
        if response.status_code >= 400:
            raise MoolTraceError(
                f"{response.status_code} from {urlparse(url).netloc}: {response.text[:180]}"
            )
        return response.json()
    raise MoolTraceError(f"giving up on {urlparse(url).netloc}: {last_error}")


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


def openalex_by_ids(openalex_ids: list[str], stats: CallStats) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ids = [item.rsplit("/", 1)[-1] for item in openalex_ids if item]
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        filt = "|".join(chunk)
        data = _oa(
            f"/works?filter=openalex_id:{filt}&per-page=50"
            "&select=id,doi,display_name,publication_year,is_retracted,cited_by_count,type",
            stats,
        )
        if isinstance(data, dict):
            results.extend(data.get("results") or [])
    return results


def openalex_by_dois(dois: list[str], stats: CallStats) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for start in range(0, len(dois), 25):
        chunk = dois[start : start + 25]
        # Slashes in DOIs must stay literal; OpenAlex rejects %2F inside filter.
        filt = "|".join(quote(doi, safe="/") for doi in chunk)
        data = _oa(
            f"/works?filter=doi:{filt}&per-page=25"
            "&select=id,doi,display_name,publication_year,is_retracted,"
            "cited_by_count,referenced_works,type",
            stats,
        )
        if isinstance(data, dict):
            results.extend(data.get("results") or [])
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
        _limiter.wait()
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
        return cached
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
    text = body.decode("utf-8", "replace")
    stored = (final, text)
    _lru_set(_pages, _pages_lock, url, stored)
    _lru_set(_pages, _pages_lock, final, stored)
    return stored


def fetch_resource(url: str, stats: CallStats) -> tuple[int, str, bytes]:
    """GET a page or file and cache the status, type, and body.

    A 403 or 404 is cached too, so a closed publisher page is not requested
    twice in the same process. Destinations are public http(s) only.
    """
    cached = _lru_get(_resources, _resources_lock, url)
    if cached is not None:
        stats.hit()
        return cached
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
    stored = (status, ctype, body)
    _lru_set(_resources, _resources_lock, url, stored)
    if final != url:
        _lru_set(_resources, _resources_lock, final, stored)
    return stored


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
