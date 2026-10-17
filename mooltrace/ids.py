"""Identifier extraction and publisher-flag classification."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

DOI_RE = re.compile(r"\b(?:doi:\s*)?(10\.\d{4,9}/[^\s\"'<>\\]+)", re.I)
DOI_IN_URL_RE = re.compile(r"(10\.\d{4,9}/[^\s\"'<>?#]+)", re.I)
PMID_URL_RE = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d{5,9})",
    re.I,
)
PMID_LABEL_RE = re.compile(r"\bPMID\s*[:#]?\s*(\d{5,9})\b", re.I)
PMC_RE = re.compile(r"\b(PMC\d{4,10})\b", re.I)
DIABETES_CARE_RE = re.compile(
    r"https?://(?:care\.diabetesjournals\.org/content|"
    r"diabetesjournals\.org/care/article)/(\d+)/(\d+)/(\d+)",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
DOI_FULL_RE = re.compile(r"10\.\d{4,9}/\S+")
_EOC_DISCLOSE = re.compile(
    r"Evidence for this claim is under review \([^)]{0,240}\)\.?",
    re.I,
)
_RETRACT_DISCLOSE = re.compile(
    r"the study this relied on \((?:[^()]|\([^()]*\))*\) was retracted on "
    r".+?\. This claim has been removed\.?",
    re.I,
)
_PUBLISHER_SUFFIXES = (
    "/full.pdf",
    "/full.html",
    "/fulltext",
    "/abstract",
    "/epdf",
    "/pdf",
    "/html",
    "/full",
    "/xml",
)

# Crossref update types that are not a publisher flag on the study.
# new_version is how Cochrane points at an earlier review; a correction
# is not an Expression of Concern or a retraction.
_NOT_FLAGS = {
    "correction",
    "erratum",
    "new_version",
    "clarification",
    "addendum",
    "commentary",
}


def is_publisher_flag(update_type: str | None) -> bool:
    """True for retraction and Expression of Concern (and withdrawals)."""
    raw = (update_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not raw or raw in _NOT_FLAGS:
        return False
    if raw in {"expression_of_concern", "removal"}:
        return True
    return "retract" in raw or "withdraw" in raw


def _strip_invisible(text: str) -> str:
    """Drop format/control characters so a hidden ZWSP cannot mint a new DOI."""
    return "".join(ch for ch in text if unicodedata.category(ch) not in {"Cf", "Cc", "Zl", "Zp"})


def clean_doi(raw: str) -> str:
    text = unicodedata.normalize("NFKC", _strip_invisible(html.unescape(raw or ""))).strip()
    text = unquote(text)
    text = unquote(text)
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = re.sub(r"^doi:\s*", "", text, flags=re.I)
    embedded = DOI_IN_URL_RE.search(text)
    if embedded and ("/" in text[: embedded.start()] or text.startswith("http")):
        text = embedded.group(1)
    text = text.split("?")[0].split("#")[0]
    text = text.rstrip(".,;:)]}>\"'`\\\u0964\u0965")
    while text and unicodedata.category(text[-1]) in {"Po", "Pe", "Pf"}:
        text = text[:-1]
    text = re.sub(r"&(?:amp;)?$", "", text, flags=re.I)
    text = text.lower()
    changed = True
    while changed:
        changed = False
        for suffix in _PUBLISHER_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                changed = True
                break
        else:
            for ext in (".pdf", ".html", ".htm"):
                if text.endswith(ext):
                    text = text[: -len(ext)]
                    changed = True
                    break
    return text


def valid_doi(doi: str) -> bool:
    return bool(DOI_FULL_RE.fullmatch(doi)) and len(doi) < 200


def normalize_update_type(update_type: str | None) -> str:
    return (update_type or "").strip().lower().replace(" ", "_").replace("-", "_")


@dataclass
class Identifiers:
    dois: list[str] = field(default_factory=list)
    pmids: list[str] = field(default_factory=list)
    pmcids: list[str] = field(default_factory=list)
    diabetes_care: list[tuple[str, str, str]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def diabetes_care_doi(volume: str, issue: str, page: str) -> str:
    """ADA print-era Diabetes Care DOI from a care/article URL path.

    Example: /care/article/26/12/3215/... → 10.2337/diacare.26.12.3215.
    Callers must confirm the DOI against Crossref (ISSN) before trusting it.
    """
    return f"10.2337/diacare.{volume}.{issue}.{page}".lower()


def strip_disclosures(text: str) -> str:
    """Drop rewrite disclosure sentences so their DOIs are not re-ingested."""
    out = text or ""
    out = _EOC_DISCLOSE.sub(" ", out)
    out = _RETRACT_DISCLOSE.sub(" ", out)
    return out


def is_disclosure_only(text: str, urls: list[str] | None = None) -> bool:
    """True when the draft is only a rewrite disclosure and has no live URLs."""
    if any(str(url).strip() for url in (urls or [])):
        return False
    blob = text or ""
    if not blob.strip():
        return False
    if not (_EOC_DISCLOSE.search(blob) or _RETRACT_DISCLOSE.search(blob)):
        return False
    found = extract_identifiers(blob)
    return not (found.dois or found.pmids or found.pmcids or found.urls or found.diabetes_care)


def extract_identifiers(text: str) -> Identifiers:
    if not text:
        return Identifiers()
    raw = unicodedata.normalize("NFKC", html.unescape(strip_disclosures(text)))
    raw = unquote(unquote(raw))
    # Newline ends a sentence. Only join a DOI broken after / or -,
    # or after a mid-token period when the next character is a digit.
    raw = re.sub(
        r"(10\.\d{4,9}/(?:[^\s]*[/\-])?)\n+\s*([A-Za-z0-9])",
        r"\1\2",
        raw,
    )
    raw = re.sub(
        r"(10\.\d{4,9}/[^\s]*\.)\n+\s*(\d)",
        r"\1\2",
        raw,
    )
    dois = [
        doi for match in DOI_RE.findall(raw) if valid_doi(doi := clean_doi(match))
    ]
    pmids = _dedupe(PMID_URL_RE.findall(raw) + PMID_LABEL_RE.findall(raw))
    pmcids = _dedupe([pmc.upper() for pmc in PMC_RE.findall(raw)])
    diabetes_care: list[tuple[str, str, str]] = []
    seen_dc: set[tuple[str, str, str]] = set()
    for vol, issue, page in DIABETES_CARE_RE.findall(raw):
        key = (vol, issue, page)
        if key not in seen_dc:
            seen_dc.add(key)
            diabetes_care.append(key)
    urls = _dedupe([url.rstrip(".,);]") for url in URL_RE.findall(raw)])
    for url in urls:
        doi = clean_doi(url)
        if valid_doi(doi):
            dois.append(doi)
        for match in DOI_IN_URL_RE.findall(url):
            nested = clean_doi(match)
            if valid_doi(nested):
                dois.append(nested)
    return Identifiers(_dedupe(dois), pmids, pmcids, diabetes_care, urls)


def has_verifiable_source(text: str, urls: list[str] | None = None) -> bool:
    """True when the draft names a DOI, PMID, PMCID, scholarly id, or public URL."""
    for url in urls or []:
        if str(url).strip():
            return True
    found = extract_identifiers(text or "")
    return bool(found.dois or found.pmids or found.pmcids or found.diabetes_care or found.urls)


def page_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", re.I | re.S)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
    return title[:300]


def site_of(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host
