"""Citation-context sentences for one edge.

Semantic Scholar citation contexts (with backoff), Europe PMC full text and
its reference list, the PMC OA package, legally open publisher HTML or PDF,
the citing page, the pasted draft, and an OpenAlex abstract. Intent labels
from Semantic Scholar are not requested and are not read. Every fetched
payload is cached in this process.
"""

from __future__ import annotations

import html as html_lib
import io
import re
import tarfile
import threading
import time
import xml.etree.ElementTree as ET
import zlib
from typing import Any
from urllib.parse import quote

from mooltrace.clients import (
    CallStats,
    MoolTraceError,
    fetch_page,
    fetch_resource,
    request_json,
)
from mooltrace.config import CACHE_MAX, HTTP_MAX_DECOMPRESS
from mooltrace.ids import clean_doi, valid_doi
from mooltrace.reliance import doi_markers, names_the_author, title_overlap

S2 = "https://api.semanticscholar.org/graph/v1"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"

_s2_lock = threading.Lock()
_s2_last = 0.0
_s2_strikes = 0
_s2_cache: dict[str, dict[str, list[str]] | None] = {}
_pmc_cache: dict[str, str | None] = {}
_pmc_id_cache: dict[str, str] = {}


def _cap(cache: dict) -> None:
    extra = len(cache) - CACHE_MAX
    if extra <= 0:
        return
    for _ in range(extra):
        cache.pop(next(iter(cache)))
_eupmc_work: dict[str, dict[str, Any] | None] = {}
_eupmc_refs: dict[str, list[dict[str, Any]] | None] = {}
PMC_OA = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


def s2_disabled() -> bool:
    """True after repeated Semantic Scholar 429s. Later papers still try once."""
    return _s2_strikes >= 3


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences. Short fragments are dropped."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", flat)
    sentences = [part.strip() for part in parts if len(part.strip()) >= 40]
    if not sentences:
        sentences = [flat[:800]]
    return sentences


def _window(text: str, needle: str, radius: int = 280) -> str:
    lowered = text.lower()
    at = lowered.find(needle.lower())
    if at < 0:
        return ""
    clip = text[max(0, at - radius) : at + len(needle) + radius]
    return re.sub(r"\s+", " ", clip).strip()


def _s2_get(url: str, stats: CallStats) -> tuple[int | None, Any]:
    """GET one Semantic Scholar URL, backing off on 429.

    After three rate limits in this process, further papers get one try
    and no long sleep. A cached caller never reaches this.
    """
    global _s2_last, _s2_strikes
    attempts = 1 if _s2_strikes >= 3 else 4
    delay = 1.15
    status: int | None = None
    payload: Any = None
    for attempt in range(attempts):
        with _s2_lock:
            wait = delay - (time.monotonic() - _s2_last)
            if wait > 0:
                time.sleep(wait)
            _s2_last = time.monotonic()
        try:
            status, payload = request_json(url, stats)
        except MoolTraceError:
            return None, None
        if status not in {429, 403}:
            _s2_strikes = 0
            return status, payload
        _s2_strikes += 1
        if attempt + 1 >= attempts:
            break
        pause = min(16.0, 2.0 * (2**attempt))
        time.sleep(pause)
        delay = pause
    return status, payload


def semantic_scholar_contexts(citing_doi: str, stats: CallStats) -> dict[str, list[str]] | None:
    """Map each cited DOI to Semantic Scholar context strings.

    ``None`` means Semantic Scholar did not answer. An empty dict means the
    citing paper was looked up and had no contexts, including when the
    publisher closed the context fields. The map is cached either way.
    """
    citing_doi = clean_doi(citing_doi)
    if citing_doi in _s2_cache:
        stats.hit()
        return _s2_cache[citing_doi]
    found: dict[str, list[str]] = {}
    offset = 0
    while offset < 800:
        url = (
            f"{S2}/paper/DOI:{quote(citing_doi, safe='')}/references"
            f"?fields=contexts,citedPaper.externalIds&limit=200&offset={offset}"
        )
        status, payload = _s2_get(url, stats)
        if status is None or status in {429, 403} or not isinstance(payload, dict):
            _s2_cache[citing_doi] = None
            return None
        if status == 404:
            _s2_cache[citing_doi] = {}
            return {}
        if status != 200:
            _s2_cache[citing_doi] = None
            return None
        # Closed papers come back 200 with data elided.
        if payload.get("data") is None:
            _s2_cache[citing_doi] = {}
            return {}
        rows = payload.get("data") or []
        for row in rows:
            cited = (row.get("citedPaper") or {}).get("externalIds") or {}
            doi = clean_doi(cited.get("DOI") or "")
            contexts = [item.strip() for item in (row.get("contexts") or []) if item and item.strip()]
            if valid_doi(doi) and contexts:
                found.setdefault(doi, []).extend(contexts)
        if len(rows) < 200:
            break
        offset += 200
    _s2_cache[citing_doi] = found
    _cap(_s2_cache)
    return found


def europepmc_work(doi: str, stats: CallStats) -> dict[str, Any] | None:
    """Core Europe PMC record for a DOI.

    An empty dict means the search succeeded and the DOI is not indexed.
    ``None`` means the search failed. Both are cached.
    """
    doi = clean_doi(doi)
    if doi in _eupmc_work:
        stats.hit()
        return _eupmc_work[doi]
    url = (
        f"{EUROPE_PMC}/search?query=DOI:{quote(doi, safe='')}&format=json"
        "&resultType=core&pageSize=1"
    )
    try:
        status, payload = request_json(url, stats)
    except MoolTraceError:
        _eupmc_work[doi] = None
        return None
    if status != 200 or not isinstance(payload, dict):
        _eupmc_work[doi] = None
        return None
    results = ((payload.get("resultList") or {}).get("result")) or []
    record = results[0] if results else {}
    raw = (record.get("pmcid") or "") if record else ""
    match = re.search(r"PMC\d+", raw, re.I)
    _pmc_id_cache[doi] = match.group(0).upper() if match else ""
    _eupmc_work[doi] = record
    return record


def europepmc_pmcid(doi: str, stats: CallStats) -> str | None:
    """PMC id for a DOI. Empty string means the lookup succeeded and found none."""
    doi = clean_doi(doi)
    if doi in _pmc_id_cache and doi in _eupmc_work:
        stats.hit()
        return _pmc_id_cache[doi]
    record = europepmc_work(doi, stats)
    if record is None:
        return None
    return _pmc_id_cache.get(doi, "")


def format_reference(ref: dict[str, Any]) -> str:
    """One bibliographic line, in the order Europe PMC returns the fields."""
    bits: list[str] = []
    for key in ("authorString", "title", "journalAbbreviation", "pubYear", "volume", "pageInfo", "doi"):
        value = ref.get(key)
        if value in (None, ""):
            continue
        bits.append(str(value).strip().rstrip("."))
    return ". ".join(bits)


def reference_matches(
    ref: dict[str, Any],
    *,
    doi: str,
    title: str,
    year: str,
    author: str,
) -> bool:
    """Yes when this reference-list entry is the cited study, not a namesake."""
    ref_doi = clean_doi(str(ref.get("doi") or ""))
    if valid_doi(doi) and ref_doi and ref_doi == clean_doi(doi):
        return True
    ref_year = str(ref.get("pubYear") or "")
    if year and ref_year and ref_year != year:
        return False
    ref_title = str(ref.get("title") or "")
    if title and ref_title and title_overlap(ref_title, title) >= 0.72 and (not year or ref_year == year):
        return True
    if author and year and ref_year == year and names_the_author(
        f"{ref.get('authorString') or ''} {ref_title}", author
    ):
        if title and title_overlap(ref_title, title) >= 0.5:
            return True
    return False


def _match_references(
    refs: list[dict[str, Any]],
    targets: list[dict[str, str]],
) -> dict[str, str]:
    found: dict[str, str] = {}
    for target in targets:
        doi = clean_doi(target.get("doi") or "")
        if not doi or doi in found:
            continue
        year = target.get("year") or ""
        for ref in refs:
            if reference_matches(
                ref,
                doi=doi,
                title=target.get("title") or "",
                year=year,
                author=target.get("author") or "",
            ):
                line = format_reference(ref)
                if line:
                    found[doi] = line
                break
    return found


def europepmc_reference_lines(
    citing_doi: str,
    targets: list[dict[str, str]],
    stats: CallStats,
) -> dict[str, str] | None:
    """Reference-list lines for the cited DOIs.

    These are bibliography entries, not in-text sentences. ``None`` means
    the references API failed. An empty dict means it answered and none matched.
    """
    citing_doi = clean_doi(citing_doi)
    if citing_doi in _eupmc_refs:
        stats.hit()
        cached = _eupmc_refs[citing_doi]
        if cached is None:
            return None
        return _match_references(cached, targets)
    record = europepmc_work(citing_doi, stats)
    if record is None:
        return None
    source = (record.get("source") or "").strip()
    ext = str(record.get("id") or "").strip()
    if not record or not source or not ext:
        _eupmc_refs[citing_doi] = []
        return {}
    refs: list[dict[str, Any]] = []
    page = 1
    while page <= 8:
        url = (
            f"{EUROPE_PMC}/{quote(source)}/{quote(ext)}/references"
            f"?format=json&pageSize=100&page={page}"
        )
        try:
            status, payload = request_json(url, stats)
        except MoolTraceError:
            if page == 1:
                _eupmc_refs[citing_doi] = None
                return None
            break
        if status != 200 or not isinstance(payload, dict):
            if page == 1:
                _eupmc_refs[citing_doi] = None
                return None
            break
        chunk = ((payload.get("referenceList") or {}).get("reference")) or []
        if isinstance(chunk, dict):
            chunk = [chunk]
        refs.extend(item for item in chunk if isinstance(item, dict))
        hit = int(payload.get("hitCount") or 0)
        if not chunk or len(refs) >= hit or len(chunk) < 100:
            break
        page += 1
    _eupmc_refs[citing_doi] = refs
    return _match_references(refs, targets)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _pmc_xml(pmcid: str, stats: CallStats) -> str | None:
    """XML text, ``''`` when Europe PMC has no full text, ``None`` on failure."""
    pmcid = pmcid.upper()
    if pmcid in _pmc_cache:
        stats.hit()
        return _pmc_cache[pmcid]
    url = f"{EUROPE_PMC}/{quote(pmcid)}/fullTextXML"
    try:
        status, payload = request_json(
            url,
            stats,
            headers={"Accept": "application/xml, text/xml, */*"},
            as_text=True,
        )
    except MoolTraceError:
        return None
    if status == 404:
        _pmc_cache[pmcid] = ""
        return ""
    if status != 200 or not isinstance(payload, str) or "<" not in payload:
        return None
    text = payload[:4_000_000]
    _pmc_cache[pmcid] = text
    return text


def _ref_index(root: ET.Element) -> dict[str, dict[str, str]]:
    """DOI → reference id, label, surname, year."""
    index: dict[str, dict[str, str]] = {}
    for ref in root.iter():
        if _local(ref.tag) != "ref":
            continue
        doi = ""
        surname = ""
        year = ""
        label = ""
        for child in ref.iter():
            name = _local(child.tag)
            if name == "label" and not label:
                label = "".join(child.itertext()).strip()
            elif name == "surname" and not surname:
                surname = "".join(child.itertext()).strip()
            elif name == "year" and not year:
                year = "".join(child.itertext()).strip()
            elif name == "pub-id" and (child.get("pub-id-type") or "").lower() == "doi":
                doi = clean_doi("".join(child.itertext()))
        if valid_doi(doi):
            index[doi] = {
                "rid": ref.get("id") or "",
                "label": label,
                "surname": surname,
                "year": year,
            }
    return index


def _in_ref_list(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    cursor: ET.Element | None = element
    while cursor is not None:
        if _local(cursor.tag) in {"ref-list", "ref"}:
            return True
        cursor = parents.get(cursor)
    return False


def pmc_sentences_for(
    pmcid: str,
    cited_dois: list[str],
    stats: CallStats,
    xml_text: str | None = None,
) -> dict[str, list[str]] | None:
    """Sentences in the citing paper that point at each cited DOI.

    ``None`` means the full text could not be fetched. A missing key means
    the full text was read and did not discuss that DOI. ``xml_text`` skips
    the Europe PMC download when the caller already has the XML.
    """
    if xml_text is None:
        xml_text = _pmc_xml(pmcid, stats)
    if xml_text is None:
        return None
    if not xml_text:
        return {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}
    refs = _ref_index(root)
    parents: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in list(parent):
            parents[child] = parent
    wanted = {clean_doi(doi): refs.get(clean_doi(doi)) for doi in cited_dois}
    found: dict[str, list[str]] = {doi: [] for doi, meta in wanted.items() if meta}
    if not found:
        return found
    for paragraph in root.iter():
        if _local(paragraph.tag) != "p" or _in_ref_list(paragraph, parents):
            continue
        xref_rids = {
            (child.get("rid") or "")
            for child in paragraph.iter()
            if _local(child.tag) == "xref" and child.get("rid")
        }
        text = re.sub(r"\s+", " ", " ".join(paragraph.itertext())).strip()
        if len(text) < 40:
            continue
        for doi, meta in wanted.items():
            if not meta:
                continue
            points = bool(meta["rid"] and meta["rid"] in xref_rids)
            if not points and meta["surname"]:
                points = names_the_author(text, meta["surname"]) and (
                    (meta["label"] and re.search(rf"\b{re.escape(meta['label'])}\b", text))
                    or (meta["year"] and meta["year"] in text)
                    or "colleague" in text.lower()
                )
            if not points:
                continue
            for sentence in split_sentences(text):
                if meta["surname"] and names_the_author(sentence, meta["surname"]):
                    found[doi].append(sentence)
                elif not meta["surname"] and meta["label"] and re.search(
                    rf"\b{re.escape(meta['label'])}\b", sentence
                ):
                    found[doi].append(sentence)
    return found


def pmc_html_sentences(
    pmcid: str,
    targets: list[dict[str, str]],
    stats: CallStats,
) -> dict[str, list[str]] | None:
    """Sentences from the PMC article HTML.

    Some publishers block the XML download. The article page is the full text
    those readers actually see. ``None`` means the page did not load.
    """
    pmcid = (pmcid or "").upper()
    if not pmcid:
        return None
    url = f"https://pmc.ncbi.nlm.nih.gov/articles/{quote(pmcid)}/"
    try:
        html_text = fetch_page_html(url, stats)
    except MoolTraceError:
        return None
    prose = re.sub(r"\s*\(#(?:b|ref|cit)[\w-]+\)", "", visible_page_text(html_text))
    found: dict[str, list[str]] = {}
    for target in targets:
        doi = clean_doi(target.get("doi") or "")
        author = target.get("author") or ""
        hits: list[str] = []
        for sentence in split_sentences(prose):
            names = bool(author) and names_the_author(sentence, author)
            marks = any(marker in sentence.lower() for marker in doi_markers(doi))
            if names or marks:
                hits.append(sentence)
        found[doi] = hits[:12]
    return found


def _xml_from_package(blob: bytes) -> str:
    """NXML member of a PMC OA tarball. Empty when the package has none."""
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as package:
            members = [
                member
                for member in package.getmembers()
                if member.isfile() and member.name.lower().endswith((".nxml", ".xml"))
            ]
            members.sort(key=lambda member: (0 if member.name.lower().endswith(".nxml") else 1, len(member.name)))
            for member in members:
                extracted = package.extractfile(member)
                if extracted is None:
                    continue
                text = extracted.read(4_000_000).decode("utf-8", "replace")
                if "<" in text:
                    return text
    except (tarfile.TarError, OSError, EOFError):
        return ""
    return ""


def pmc_oa_xml(pmcid: str, stats: CallStats) -> str | None:
    """Full text from the PMC OA service.

    ``None`` means the service failed. ``''`` means it answered and there is
    no open package. The XML is cached.
    """
    pmcid = (pmcid or "").upper()
    if not pmcid:
        return ""
    key = f"oa:{pmcid}"
    if key in _pmc_cache:
        stats.hit()
        return _pmc_cache[key]
    url = f"{PMC_OA}?id={quote(pmcid)}"
    try:
        status, payload = request_json(
            url,
            stats,
            headers={"Accept": "application/xml, text/xml, */*"},
            as_text=True,
        )
    except MoolTraceError:
        _pmc_cache[key] = None
        return None
    if status != 200 or not isinstance(payload, str):
        _pmc_cache[key] = "" if status == 404 else None
        return _pmc_cache[key]
    hrefs = re.findall(r'href="(https://[^"]+)"', payload)
    link = next((href for href in hrefs if href.endswith((".tar.gz", ".tgz"))), "")
    if not link:
        link = next((href for href in hrefs if "ftp" not in href), "")
    if not link:
        _pmc_cache[key] = ""
        return ""
    code, _ctype, body = fetch_resource(link, stats)
    if code != 200 or not body:
        _pmc_cache[key] = ""
        return ""
    xml_text = _xml_from_package(body)
    _pmc_cache[key] = xml_text
    if xml_text:
        _pmc_cache[pmcid] = xml_text
    return xml_text


def pdf_text(blob: bytes) -> str:
    """Plain text from a PDF body. Empty when the streams are not readable."""
    if not blob or not blob.startswith(b"%PDF"):
        return ""
    pieces: list[str] = []

    def absorb(raw: bytes) -> None:
        text = raw.decode("latin1", "replace")
        for match in re.finditer(r"\((?:\\.|[^\\)]){6,}\)", text):
            chunk = match.group(0)[1:-1]
            chunk = chunk.replace(r"\n", " ").replace(r"\r", " ").replace(r"\(", "(").replace(r"\)", ")")
            if re.search(r"[A-Za-z]{3}", chunk):
                pieces.append(chunk)

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", blob, re.S):
        raw = match.group(1).strip(b"\r\n")
        absorb(raw)
        try:
            decoder = zlib.decompressobj()
            absorb(decoder.decompress(raw, HTTP_MAX_DECOMPRESS))
        except zlib.error:
            continue
    return re.sub(r"\s+", " ", " ".join(pieces)).strip()


def legally_open_links(
    eupmc: dict[str, Any] | None,
    alex: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """URLs Europe PMC or OpenAlex mark as free or open access, with a kind."""
    links: list[tuple[str, str]] = []
    urls = ((eupmc or {}).get("fullTextUrlList") or {}).get("fullTextUrl") or []
    if isinstance(urls, dict):
        urls = [urls]
    for item in urls:
        availability = (item.get("availability") or "").lower()
        if availability not in {"free", "open access"}:
            continue
        url = item.get("url") or ""
        style = (item.get("documentStyle") or "").lower()
        if not url:
            continue
        kind = "publisher_pdf" if "pdf" in style or url.lower().endswith(".pdf") else "publisher_html"
        links.append((url, kind))
    oa = (alex or {}).get("open_access") or {}
    if oa.get("is_oa"):
        oa_url = oa.get("oa_url") or ""
        if oa_url:
            kind = "publisher_pdf" if oa_url.lower().endswith(".pdf") else "publisher_html"
            links.append((oa_url, kind))
        for loc in (alex or {}).get("locations") or []:
            if not loc.get("is_oa"):
                continue
            for key, kind in (("pdf_url", "publisher_pdf"), ("landing_page_url", "publisher_html")):
                url = loc.get(key) or ""
                if url:
                    links.append((url, kind))
    seen: set[str] = set()
    chosen: list[tuple[str, str]] = []
    for url, kind in links:
        if url in seen:
            continue
        seen.add(url)
        chosen.append((url, kind))
    return chosen[:4]


def _paywall(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "access through your institution",
        "purchase access",
        "sign in to access",
        "subscribe to access",
    )
    return any(marker in lowered for marker in markers)


def prose_candidates(
    text: str,
    *,
    cited_doi: str,
    cited_author: str,
    cited_title: str,
    source: str,
) -> list[tuple[str, str]]:
    """Sentences in plain text that point at the cited work."""
    chosen = [
        (sentence, source)
        for sentence in split_sentences(text)
        if _mentions_work(sentence, cited_doi, cited_author, cited_title)
    ]
    return chosen[:8]


def open_access_candidates(
    links: list[tuple[str, str]],
    targets: list[dict[str, str]],
    stats: CallStats,
) -> dict[str, list[tuple[str, str]]]:
    """Sentences from legally open HTML or PDF. Closed responses are cached misses."""
    found: dict[str, list[tuple[str, str]]] = {}
    for url, kind in links:
        try:
            code, ctype, body = fetch_resource(url, stats)
        except MoolTraceError:
            continue
        if code != 200 or not body:
            continue
        is_pdf = "pdf" in ctype.lower() or body.startswith(b"%PDF") or kind == "publisher_pdf"
        if is_pdf:
            text = pdf_text(body)
            source = "publisher_pdf"
        else:
            text = visible_page_text(body.decode("utf-8", "replace"))
            source = "publisher_html"
        if not text or _paywall(text):
            continue
        for target in targets:
            doi = clean_doi(target.get("doi") or "")
            hits = prose_candidates(
                text,
                cited_doi=doi,
                cited_author=target.get("author") or "",
                cited_title=target.get("title") or "",
                source=source,
            )
            if hits:
                found.setdefault(doi, []).extend(hits)
    return found


def pmc_author(pmcid: str, cited_doi: str, stats: CallStats) -> str:
    """Surname recorded on the reference entry, when the full text is cached."""
    xml_text = _pmc_cache.get((pmcid or "").upper())
    if not xml_text:
        return ""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    meta = _ref_index(root).get(clean_doi(cited_doi)) or {}
    return meta.get("surname") or ""


def visible_page_text(html_text: str) -> str:
    """Page prose with link targets kept inline and scripts removed."""

    def anchor(match: re.Match[str]) -> str:
        href = match.group(1)
        inner = re.sub(r"<[^>]+>", " ", match.group(2))
        return f"{inner} ({href})"

    text = re.sub(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        anchor,
        html_text or "",
        flags=re.I | re.S,
    )
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def script_blobs(html_text: str) -> str:
    parts = re.findall(r"<script\b[^>]*>(.*?)</script>", html_text or "", flags=re.I | re.S)
    return "\n".join(parts)


def _mentions_work(sentence: str, doi: str, author: str, title: str) -> bool:
    if any(marker in sentence.lower() for marker in doi_markers(doi)):
        return True
    if names_the_author(sentence, author) and (
        re.search(r"\b(?:19|20)\d{2}\b", sentence) or "colleague" in sentence.lower()
    ):
        return True
    # Nearly the whole title, so a shared topic word such as "glucose" is not enough.
    if title and title_overlap(sentence, title) >= 0.85:
        return True
    return False


def page_candidates(
    html_text: str,
    *,
    cited_doi: str,
    cited_author: str,
    cited_title: str,
) -> list[tuple[str, str]]:
    """Sentences on a web page that point at the cited work."""
    visible = visible_page_text(html_text)
    chosen: list[tuple[str, str]] = []
    for sentence in split_sentences(visible):
        if _mentions_work(sentence, cited_doi, cited_author, cited_title):
            chosen.append((sentence, "page"))
    if chosen:
        return chosen[:8]
    blobs = script_blobs(html_text)
    for marker in doi_markers(cited_doi):
        window = _window(re.sub(r"<[^>]+>", " ", blobs), marker)
        if window:
            # DOI only inside a script or data block: a source list, not prose.
            chosen.append((window, "page_list"))
            break
    return chosen[:4]


def draft_candidates(
    draft: str,
    *,
    cited_doi: str,
    cited_author: str,
    cited_title: str,
) -> list[tuple[str, str]]:
    """Sentences in the pasted draft that point at the cited work."""
    text = draft or ""
    chosen = [
        (sentence, "draft")
        for sentence in split_sentences(text)
        if _mentions_work(sentence, cited_doi, cited_author, cited_title)
    ]
    if chosen:
        return chosen[:6]
    for marker in doi_markers(cited_doi):
        window = _window(text, marker, radius=360)
        if window:
            return [(window, "draft")]
    return []


def abstract_candidates(
    abstract: str,
    *,
    cited_doi: str,
    cited_author: str,
    cited_title: str,
) -> list[tuple[str, str]]:
    """Abstract lines that name the cited study. Topic overlap is not a citation."""
    del cited_title
    chosen = []
    for sentence in split_sentences(abstract):
        if names_the_author(sentence, cited_author) or any(
            marker in sentence.lower() for marker in doi_markers(cited_doi)
        ):
            chosen.append((sentence, "openalex_abstract"))
    return chosen[:4]


def inverted_abstract(index: dict[str, Any] | None) -> str:
    if not isinstance(index, dict):
        return ""
    slots: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions or []:
            try:
                slots.append((int(position), str(word)))
            except (TypeError, ValueError):
                continue
    slots.sort()
    return " ".join(word for _, word in slots)


def fetch_page_html(url: str, stats: CallStats) -> str:
    _final, html_text = fetch_page(url, stats)
    return html_text
