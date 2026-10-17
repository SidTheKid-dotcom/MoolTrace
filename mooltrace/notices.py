"""Trust a publisher-notice date only when it is a separate record after publication.

Crossref in-place retractions copy updated-by {DOI == article DOI, updated =
the article publication date}. That date is not a retraction date.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any, Callable
from xml.etree import ElementTree as ET

from mooltrace.ids import clean_doi, valid_doi

NOTICE_DATE_GRACE_DAYS = 60
_DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/\S+")
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_RETRACTION_IN = {"retractionin", "partialretractionin"}
_ISO = re.compile(r"^((?:19|20)\d{2})(?:-(\d{2})(?:-(\d{2}))?)?$")


def parse_partial_date(value: str) -> tuple[int, int | None, int | None] | None:
    text = str(value or "").strip()
    match = _ISO.fullmatch(text)
    if not match:
        return ncbi_pubdate_parts(text)
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    day = int(match.group(3)) if match.group(3) else None
    if month is not None and not 1 <= month <= 12:
        month = None
        day = None
    if day is not None and month is not None:
        last = calendar.monthrange(year, month)[1]
        if not 1 <= day <= last:
            day = None
    return year, month, day


def iso_date(year: int, month: int | None = None, day: int | None = None) -> str:
    if month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def ncbi_pubdate_parts(value: str) -> tuple[int, int | None, int | None] | None:
    tokens = [
        part
        for part in str(value or "").replace("/", " ").replace("-", " ").replace(",", " ").split()
        if part
    ]
    year = None
    month = None
    day = None
    for token in tokens:
        lower = token.lower()
        if token.isdigit() and len(token) == 4 and token[:2] in {"19", "20"}:
            year = int(token)
        elif lower in _MONTHS:
            month = _MONTHS[lower]
        elif token.isdigit() and 1 <= int(token) <= 31 and day is None:
            day = int(token)
    if year is None:
        return None
    return year, month, day


def ncbi_pubdate_to_iso(value: str) -> str:
    parts = ncbi_pubdate_parts(value)
    if not parts:
        return ""
    year, month, day = parts
    return iso_date(year, month, day)


def date_parts_to_iso(parts: list[Any] | None) -> str:
    if not parts:
        return ""
    try:
        year = int(parts[0])
    except (TypeError, ValueError, IndexError):
        return ""
    month = None
    day = None
    if len(parts) > 1:
        try:
            month = int(parts[1])
        except (TypeError, ValueError):
            month = None
    if len(parts) > 2 and month:
        try:
            day = int(parts[2])
        except (TypeError, ValueError):
            day = None
    return iso_date(year, month, day)


def issued_date(message: dict[str, Any] | None) -> str:
    if not message:
        return ""
    for key in ("issued", "published-print", "published-online", "published"):
        blob = message.get(key) or {}
        if not isinstance(blob, dict):
            continue
        iso = date_parts_to_iso((blob.get("date-parts") or [[]])[0])
        if iso:
            return iso
    return ""


def notice_date_from_update(update: dict[str, Any] | None) -> str:
    if not update:
        return ""
    updated = update.get("updated") or {}
    if not isinstance(updated, dict):
        return ""
    if updated.get("date-time"):
        return str(updated["date-time"])[:10]
    return date_parts_to_iso((updated.get("date-parts") or [[]])[0])


def _as_date(iso: str, *, latest: bool) -> date | None:
    parts = parse_partial_date(iso)
    if not parts:
        return None
    year, month, day = parts
    if month and day:
        return date(year, month, day)
    if month:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, last if latest else 1)
    return date(year, 12, 31) if latest else date(year, 1, 1)


def clearly_after_publication(notice_date: str, work_date: str) -> bool:
    notice = _as_date(notice_date, latest=False)
    work = _as_date(work_date, latest=True)
    if notice is None or work is None:
        return False
    return (notice - work) > timedelta(days=NOTICE_DATE_GRACE_DAYS)


def same_record(notice_doi: str, work_doi: str) -> bool:
    left = clean_doi(notice_doi)
    right = clean_doi(work_doi)
    return bool(left and right and left == right)


def date_is_trusted(
    *,
    notice_doi: str,
    work_doi: str,
    notice_date: str,
    work_date: str,
) -> bool:
    if not valid_doi(notice_doi):
        return False
    if same_record(notice_doi, work_doi):
        return False
    if not notice_date or not work_date:
        return bool(notice_date) and not same_record(notice_doi, work_doi)
    return clearly_after_publication(notice_date, work_date)


def needs_resolve(
    *,
    notice_doi: str,
    work_doi: str,
    notice_date: str,
    work_date: str,
) -> bool:
    if same_record(notice_doi, work_doi):
        return True
    if notice_date and work_date and not clearly_after_publication(notice_date, work_date):
        return True
    return False


def relation_dois(message: dict[str, Any] | None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    relation = (message or {}).get("relation") or {}
    if not isinstance(relation, dict):
        return found
    for entries in relation.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("id-type") or "").lower() != "doi":
                continue
            doi = clean_doi(entry.get("id") or "")
            if valid_doi(doi) and doi not in seen:
                seen.add(doi)
                found.append(doi)
    return found


def other_updated_by(message: dict[str, Any] | None, work_doi: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for update in (message or {}).get("updated-by") or []:
        if not isinstance(update, dict):
            continue
        doi = clean_doi(update.get("DOI") or "")
        if not valid_doi(doi) or same_record(doi, work_doi) or doi in seen:
            continue
        seen.add(doi)
        rows.append((doi, notice_date_from_update(update)))
    return rows


def comments_corrections_from_pubmed_xml(xml: str) -> list[dict[str, str]]:
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", xml or "", count=1)
    if not raw.strip():
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out: list[dict[str, str]] = []
    for node in root.iter():
        tag = node.tag.split("}", 1)[-1]
        if tag != "CommentsCorrections":
            continue
        ref_type = str(node.attrib.get("RefType") or "").replace(" ", "").replace("_", "").lower()
        if ref_type not in _RETRACTION_IN:
            continue
        pmid = ""
        source = ""
        for child in list(node):
            child_tag = child.tag.split("}", 1)[-1]
            if child_tag == "PMID":
                pmid = str(child.text or "").strip()
            elif child_tag == "RefSource":
                source = str(child.text or "").strip()
        doi = ""
        match = _DOI_IN_TEXT.search(source)
        if match:
            doi = clean_doi(match.group(0).rstrip(".,;:)]}"))
        if pmid.isdigit() or valid_doi(doi):
            out.append({"pmid": pmid, "doi": doi if valid_doi(doi) else "", "ref_source": source})
    return out


def resolve_publisher_notice(
    *,
    work_doi: str,
    work_date: str,
    notice_doi: str,
    notice_date: str,
    message: dict[str, Any] | None = None,
    pubmed_lookup: Callable[[str], dict[str, Any] | None] | None = None,
    crossref_lookup: Callable[[str], dict[str, Any] | None] | None = None,
) -> tuple[str, str]:
    """Return (notice_doi, notice_date). Date is empty when unconfirmed."""
    cleaned_work = clean_doi(work_doi)
    cleaned_notice = clean_doi(notice_doi)
    date = str(notice_date or "").strip()
    if valid_doi(cleaned_notice) and not needs_resolve(
        notice_doi=cleaned_notice,
        work_doi=cleaned_work,
        notice_date=date,
        work_date=work_date,
    ):
        return cleaned_notice, date

    pubmed: dict[str, Any] | None = None
    if pubmed_lookup is not None:
        try:
            pubmed = pubmed_lookup(cleaned_work)
        except Exception:
            pubmed = None
    if isinstance(pubmed, dict):
        pubmed_doi = clean_doi(str(pubmed.get("notice_doi") or pubmed.get("doi") or ""))
        pubmed_date = str(pubmed.get("notice_date") or pubmed.get("date") or "").strip()
        if valid_doi(pubmed_doi) and not same_record(pubmed_doi, cleaned_work):
            if pubmed_date and (
                not work_date or clearly_after_publication(pubmed_date, work_date)
            ):
                return pubmed_doi, pubmed_date
            if pubmed_date:
                return pubmed_doi, pubmed_date
            return pubmed_doi, ""
        if pubmed_date and (
            not work_date or clearly_after_publication(pubmed_date, work_date)
        ):
            keep = pubmed_doi if valid_doi(pubmed_doi) else cleaned_notice
            return keep, pubmed_date

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for doi, cand_date in other_updated_by(message, cleaned_work):
        if doi not in seen:
            seen.add(doi)
            candidates.append((doi, cand_date))
    for doi in relation_dois(message):
        if doi not in seen and not same_record(doi, cleaned_work):
            seen.add(doi)
            candidates.append((doi, ""))

    for doi, cand_date in candidates:
        resolved_date = cand_date
        if (not resolved_date or not clearly_after_publication(resolved_date, work_date)) and (
            crossref_lookup is not None
        ):
            try:
                extra = crossref_lookup(doi)
            except Exception:
                extra = None
            if isinstance(extra, dict):
                resolved_date = issued_date(extra) or resolved_date
        if resolved_date and (
            not work_date or clearly_after_publication(resolved_date, work_date)
        ):
            return doi, resolved_date
        if valid_doi(doi) and not same_record(doi, cleaned_work) and resolved_date:
            return doi, resolved_date

    keep = cleaned_notice if valid_doi(cleaned_notice) else ""
    return keep, ""
