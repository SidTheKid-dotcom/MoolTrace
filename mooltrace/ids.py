"""Identifier extraction and publisher-flag classification."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>\\]+)", re.I)
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


def clean_doi(raw: str) -> str:
    text = html.unescape(raw or "").strip()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = text.split("?")[0].split("#")[0]
    text = text.rstrip(".,;:)]}>\"'")
    # HTML pages often append &amp; to a DOI inside an href.
    text = re.sub(r"&(?:amp;)?$", "", text, flags=re.I)
    return text.lower()


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


def extract_identifiers(text: str) -> Identifiers:
    if not text:
        return Identifiers()
    raw = html.unescape(text)
    dois = _dedupe(
        [doi for match in DOI_RE.findall(raw) if valid_doi(doi := clean_doi(match))]
    )
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
    return Identifiers(dois, pmids, pmcids, diabetes_care, urls)


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
