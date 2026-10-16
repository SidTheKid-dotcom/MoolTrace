"""Propose a rewrite after warn/block, then re-run check_answer.

Only sentences whose citations reach a flagged study change. Every other
sentence stays byte-identical. Replacement DOIs come from unflagged
siblings already in this answer's graph. If none exist, the claim is
disclosed, not replaced with an off-topic paper. The graph decides.
Azure AI Foundry is optional; the template always works.
"""

from __future__ import annotations

import re
from typing import Any

from mooltrace.clients import MoolTraceError
from mooltrace.ids import clean_doi, extract_identifiers, site_of, strip_disclosures, valid_doi
from mooltrace.trace import check_answer

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_DISCLOSE_CHUNK = re.compile(
    r"Evidence for this claim is under review \([^)]{0,240}\)",
    re.I,
)
_UNFLAGGED_SIBLING = """
MATCH (review)-[:RESTS_ON]->(flagged:Work {doi: $doi})
MATCH (review)-[r:RESTS_ON]->(sib:Work)
WHERE sib.doi <> $doi AND coalesce(r.weight, 0.0) >= 0.5
  AND coalesce(r.sentence, '') <> ''
OPTIONAL MATCH (n:Notice)-[:FLAGS]->(sib)
WITH sib, n
WHERE n IS NULL
RETURN sib.doi AS doi, sib.title AS title
LIMIT 1
""".strip()


def _flagged(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    dois: set[str] = set()
    urls: set[str] = set()
    for reason in payload.get("reasons") or []:
        for key in ("notice_doi", "root_doi"):
            doi = clean_doi(str(reason.get(key) or ""))
            if valid_doi(doi):
                dois.add(doi)
        url = str(reason.get("source_url") or "").strip()
        if url:
            urls.add(url.rstrip("/"))
        for step in reason.get("steps") or []:
            doi = clean_doi(str(step.get("doi") or ""))
            if valid_doi(doi):
                dois.add(doi)
            step_url = str(step.get("url") or "").strip()
            if step_url:
                urls.add(step_url.rstrip("/"))
    return dois, urls


def still_cites(text: str, urls: list[str], payload: dict[str, Any]) -> bool:
    dois, flagged_urls = _flagged(payload)
    blob = strip_disclosures(_DISCLOSE_CHUNK.sub("", " ".join([text, *urls])))
    found = extract_identifiers(blob)
    if any(clean_doi(doi) in dois for doi in found.dois):
        return True
    for url in list(found.urls) + urls:
        if url.rstrip("/") in flagged_urls:
            return True
    return False


def _split_spans(text: str) -> list[str]:
    if not text:
        return []
    parts = _SENTENCE_END.split(text)
    if len(parts) <= 1:
        return [text] if text else []
    spans: list[str] = []
    cursor = 0
    for index, part in enumerate(parts):
        start = text.find(part, cursor)
        if start < 0:
            start = cursor
        end = start + len(part)
        if index + 1 < len(parts):
            nxt = parts[index + 1]
            gap_at = text.find(nxt, end)
            if gap_at > end:
                part = text[start:gap_at]
                end = gap_at
        else:
            part = text[start:]
            end = len(text)
        spans.append(part)
        cursor = end
    return [span for span in spans if span]


def _citation_only(span: str) -> bool:
    found = extract_identifiers(span)
    if not found.dois and not found.urls and not found.pmids and not found.pmcids:
        return False
    leftover = span
    for doi in found.dois:
        leftover = re.sub(re.escape(doi), "", leftover, flags=re.I)
    for url in found.urls:
        leftover = leftover.replace(url, "")
    leftover = re.sub(
        r"\b(doi|pmid|pmcid|see|source|url|https?)\b",
        "",
        leftover,
        flags=re.I,
    )
    leftover = re.sub(r"[^\w]+", "", leftover)
    return len(leftover) < 12


def _span_hits(span: str, dois: set[str], urls: set[str]) -> bool:
    found = extract_identifiers(span)
    if any(clean_doi(doi) in dois for doi in found.dois):
        return True
    for url in found.urls:
        if url.rstrip("/") in urls:
            return True
    raw = span or ""
    for url in urls:
        if url and url.rstrip("/") in raw:
            return True
        host = site_of(url) if url else ""
        stem = host.split(".")[0] if host else ""
        if stem and len(stem) >= 4 and re.search(rf"\b{re.escape(stem)}\b", raw, re.I):
            return True
    return False


def _join_citation_tails(spans: list[str], dois: set[str], urls: set[str]) -> list[str]:
    if not spans:
        return []
    grouped: list[str] = [spans[0]]
    for span in spans[1:]:
        if _citation_only(span) and (
            _span_hits(grouped[-1], dois, urls) or _span_hits(span, dois, urls)
        ):
            grouped[-1] = grouped[-1] + span
        else:
            grouped.append(span)
    return grouped


def _notice_label(payload: dict[str, Any]) -> tuple[str, str, str]:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    code = str(reason.get("code") or "notice")
    if code == "expression_of_concern":
        label = "Expression of Concern"
    elif code in {"retraction", "withdrawal"}:
        label = code
    else:
        label = "publisher notice"
    doi = clean_doi(str(reason.get("notice_doi") or reason.get("root_doi") or ""))
    date = str(reason.get("notice_date") or "").strip()[:10]
    return label, doi, date


def _eoc_disclose(payload: dict[str, Any]) -> str:
    label, doi, date = _notice_label(payload)
    bits = [label]
    if valid_doi(doi):
        bits.append(doi)
    if date:
        bits.append(date)
    return f"Evidence for this claim is under review ({', '.join(bits)})."


def _claim_topic(span: str) -> str:
    leftover = re.sub(r"https?://\S+", "", span or "", flags=re.I)
    leftover = re.sub(r"10\.\d{4,9}/\S+", "", leftover)
    leftover = re.sub(r"\s+", " ", leftover).strip(" .,:;")
    if not leftover:
        return "This claim"
    words = leftover.split()[:8]
    return " ".join(words).rstrip(":,")


def _study_cite(payload: dict[str, Any], span: str) -> tuple[str, str, str]:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    root = clean_doi(str(reason.get("root_doi") or ""))
    year = ""
    author = ""
    for step in reason.get("steps") or []:
        if clean_doi(str(step.get("doi") or "")) == root:
            year = str(step.get("year") or "").strip()
            title = str(step.get("title") or "").strip()
            if title:
                author = title.split()[0]
            break
    if not author:
        match = re.search(r"\b([A-Z][a-z]{2,})\b(?:\s+and\s+colleagues)?", span or "")
        if match and match.group(1).lower() not in {"the", "this", "doi", "a"}:
            author = match.group(1)
    if not year:
        match = re.search(r"\b((?:19|20)\d{2})\b", span or "")
        if match:
            year = match.group(1)
    return author or "the authors", year or "n.d.", root


def _retraction_sentence(payload: dict[str, Any], span: str = "") -> str:
    label, notice, date = _notice_label(payload)
    author, year, root = _study_cite(payload, span)
    topic = _claim_topic(span)
    study = f"{author} {year}"
    if valid_doi(root):
        study = f"{study}, {root}"
    when = date or "an unknown date"
    notice_bit = f" (notice {notice})" if valid_doi(notice) else ""
    return (
        f"{topic}: the study this relied on ({study}) was retracted on "
        f"{when}{notice_bit}. This claim has been removed."
    )


def _disclose(payload: dict[str, Any], span: str = "") -> str:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    code = str(reason.get("code") or "")
    if code in {"retraction", "withdrawal"}:
        return _retraction_sentence(payload, span)
    return _eoc_disclose(payload)


def _sibling_doi(graph, flagged_dois: set[str]) -> str | None:
    if graph is None:
        return None
    for doi in sorted(flagged_dois):
        try:
            run = graph.run("unflagged_sibling", _UNFLAGGED_SIBLING, {"doi": doi})
        except Exception:
            continue
        for row in run.rows:
            sibling = clean_doi(str(row.get("doi") or ""))
            if valid_doi(sibling) and sibling not in flagged_dois:
                return sibling
    return None


def _replacement(payload: dict[str, Any], graph=None, span: str = "") -> str:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    code = str(reason.get("code") or "")
    if code in {"retraction", "withdrawal"}:
        return _retraction_sentence(payload, span)
    dois, _urls = _flagged(payload)
    sibling = _sibling_doi(graph, dois)
    if sibling:
        return (
            f"A related study already on this path, with no publisher notice "
            f"in range, is DOI {sibling}."
        )
    return _eoc_disclose(payload)


def template_rewrite(
    payload: dict[str, Any],
    text: str = "",
    urls: list[str] | None = None,
    graph=None,
) -> dict[str, Any]:
    dois, flagged_urls = _flagged(payload)
    dropped = sorted(dois | flagged_urls)
    original = text or ""
    spans = _join_citation_tails(_split_spans(original), dois, flagged_urls)
    kept_urls = [
        url
        for url in (urls or [])
        if url and url.rstrip("/") not in flagged_urls
    ]
    live = extract_identifiers(original)
    live_dois = {clean_doi(doi) for doi in live.dois if clean_doi(doi) not in dois}
    only_page = bool(flagged_urls) and not kept_urls and not live_dois
    if not original.strip():
        rewritten = _replacement(payload, graph)
        return {
            "text": rewritten,
            "urls": kept_urls,
            "method": "template",
            "dropped": dropped,
            "untouched": True,
        }
    pieces: list[str] = []
    changed = False
    for span in spans:
        hit = _span_hits(span, dois, flagged_urls) or (
            only_page and not _DISCLOSE_CHUNK.search(span)
        )
        if hit:
            replacement = _replacement(payload, graph, span)
            pieces.append(replacement + (" " if span.endswith(" ") else ""))
            changed = True
        else:
            pieces.append(span)
    if not changed:
        rewritten = original
    else:
        rewritten = "".join(pieces)
        rewritten = re.sub(r"[ \t]+\n", "\n", rewritten)
        rewritten = re.sub(r"  +", " ", rewritten).strip()
        if original.endswith("\n") and not rewritten.endswith("\n"):
            rewritten += "\n"
    return {
        "text": rewritten,
        "urls": kept_urls,
        "method": "template",
        "dropped": dropped,
        "untouched": not changed,
    }


def _azure_rewrite(
    text: str,
    urls: list[str],
    payload: dict[str, Any],
    graph=None,
) -> dict[str, Any] | None:
    from mooltrace.foundry import complete

    dois, flagged_urls = _flagged(payload)
    label, notice_doi, date = _notice_label(payload)
    prompt = (
        "Rewrite ONLY the sentences whose citations reach these flagged "
        "URLs or DOIs. Keep every other sentence byte-identical.\n"
        f"{sorted(dois | flagged_urls)}\n"
        f"Publisher notice: {label} {notice_doi} {date}\n"
        "If you cannot name an on-topic replacement already in the draft's "
        "own citation graph, replace the affected sentence with: "
        f"{_disclose(payload, text)}\n"
        "Never invent a citation. Never cite an unrelated paper. "
        "Never say a retraction is under review. "
        "Do not call an Expression of Concern a retraction.\n\n"
        f"Draft:\n{text}\n\nCited URLs:\n" + "\n".join(urls)
    )
    try:
        drafted = complete(prompt)
    except MoolTraceError:
        return None
    kept_urls = [url for url in urls if url.rstrip("/") not in flagged_urls]
    proposal = {
        "text": drafted,
        "urls": kept_urls,
        "method": "azure-foundry",
        "dropped": sorted(dois | flagged_urls),
    }
    if still_cites(proposal["text"], proposal["urls"], payload):
        return None
    return proposal


def propose_rewrite(
    text: str,
    urls: list[str] | None,
    payload: dict[str, Any],
    graph=None,
) -> dict[str, Any]:
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    azure = _azure_rewrite(text, url_list, payload, graph)
    if azure is not None:
        return azure
    return template_rewrite(payload, text, url_list, graph)


def _exit_code(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 2
    code = payload.get("exit_code")
    if code is None:
        return 2
    return int(code)


def rewrite_answer(
    text: str = "",
    urls: list[str] | None = None,
    engine: str = "draft",
    depth: int = 2,
    graph=None,
) -> dict[str, Any]:
    """Check, rewrite flagged sentences, recheck. Recheck sets the exit code."""
    from mooltrace import config as _config

    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    first = check_answer(text, url_list, engine, depth, graph=graph)
    if first.get("decision") == "pass":
        code = _exit_code(first)
        return {
            "rewritten": False,
            "reason": "already pass",
            "method": None,
            "text": text,
            "urls": url_list,
            "check": first,
            "recheck": first,
            "exit_code": code,
        }
    proposal = propose_rewrite(text, url_list, first, graph)
    second = check_answer(
        proposal["text"],
        proposal.get("urls") or [],
        engine,
        _config.clamp_depth(depth),
        graph=graph,
    )
    code = _exit_code(second)
    new_text = proposal.get("text") or ""
    changed = new_text != text
    return {
        "rewritten": changed,
        "reason": first.get("decision"),
        "method": proposal.get("method"),
        "text": new_text,
        "urls": proposal.get("urls") or [],
        "dropped": proposal.get("dropped") or [],
        "check": first,
        "recheck": second,
        "exit_code": code,
    }
