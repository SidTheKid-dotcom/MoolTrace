"""Propose a rewrite after warn/block, then re-run check_answer.

Only sentences whose citations reach a flagged study change. Every other
sentence stays byte-identical. Replacement DOIs come from unflagged
siblings already in this answer's graph. If none exist, the claim is
disclosed, not replaced with an off-topic paper. The graph decides.
Rewrite is the deterministic template only.
"""

from __future__ import annotations

import re
from typing import Any

from mooltrace.ids import clean_doi, extract_identifiers, site_of, strip_disclosures, valid_doi
from mooltrace.trace import check_answer

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_DISCLOSE_CHUNK = re.compile(
    r"Evidence for this claim is under review \([^)]{0,240}\)"
    r"|An earlier version of this answer cited .{0,320}?so (?:this claim|that source) was removed\.?",
    re.I,
)
_TITLE_PREFIX = re.compile(
    r"^(RETRACTED|RETRACTION|WITHDRAWN|WITHDRAWAL)\s*:?\s*",
    re.I,
)
_BAD_AUTHOR = frozenset(
    {
        "the",
        "this",
        "that",
        "doi",
        "a",
        "an",
        "retracted",
        "retraction",
        "withdrawn",
        "withdrawal",
        "expression",
        "concern",
        "notice",
        "publisher",
        "cinnamon",
        "primary",
        "prevention",
        "hydroxychloroquine",
        "olive",
        "mediterranean",
    }
)
PREDIMED_DOI = "10.1056/nejmoa1200303"
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
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


def _month_only(value: str) -> str:
    """Issue dates are stored as the 1st of the month; don't claim a day the source never gave."""
    text = (value or "").strip()[:10]
    return text[:7] if re.fullmatch(r"(?:19|20)\d{2}-\d{2}-01", text) else (value or "").strip()


def _pretty_date(value: str) -> str:
    text = _month_only(value)
    month_only = re.fullmatch(r"((?:19|20)\d{2})-(\d{2})$", text)
    if month_only:
        year, month = month_only.groups()
        try:
            return f"{_MONTHS[int(month) - 1]} {year}"
        except (IndexError, ValueError):
            return text
    text = text[:10]
    match = re.fullmatch(r"((?:19|20)\d{2})-(\d{2})-(\d{2})", text)
    if not match:
        return text
    year, month, day = match.groups()
    try:
        month_name = _MONTHS[int(month) - 1]
    except (IndexError, ValueError):
        return text
    return f"{int(day)} {month_name} {year}"


def _date_preposition(value: str) -> str:
    if re.fullmatch(r"((?:19|20)\d{2})-(\d{2})$", _month_only(value)):
        return "in"
    return "on"


def _cite_name(author: str, year: str) -> str:
    if author == "the authors":
        return "the authors" if year == "n.d." else f"the authors {year}"
    if year == "n.d.":
        return f"{author} et al."
    return f"{author} et al. {year}"


def _is_predimed(payload: dict[str, Any], root: str) -> bool:
    if clean_doi(root) == PREDIMED_DOI:
        return True
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    label = str(reason.get("notice_label") or "")
    title = str(reason.get("root_title") or (reason.get("root") or {}).get("title") or "")
    return "republication" in label.lower() or "predimed" in title.lower()


def _eoc_disclose(payload: dict[str, Any], span: str = "", graph=None) -> str:
    _label, _doi, date = _notice_label(payload)
    author, year, _root = _study_cite(payload, span, graph)
    who = _cite_name(author, year)
    when = _pretty_date(date)
    dated = f" dated {when}" if when else ""
    return (
        f"An earlier version of this answer cited {who}; "
        f"that paper is under an Expression of Concern{dated}, "
        f"so that source was removed."
    )


def _family_name(value: Any) -> str:
    raw = _TITLE_PREFIX.sub("", str(value or "").strip())
    if not raw:
        return ""
    parts = raw.split()
    if len(parts) > 3:
        return ""
    token = parts[0].strip(".,;:()[]\"'")
    if not token or token.lower() in _BAD_AUTHOR:
        return ""
    if token.endswith(":") or token.upper() == "RETRACTED":
        return ""
    return token


def _year_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"none", "n.d.", "nd"}:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        match = re.search(r"((?:19|20)\d{2})", text)
        return match.group(1) if match else ""


def _study_cite(
    payload: dict[str, Any],
    span: str = "",
    graph=None,
) -> tuple[str, str, str]:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    root = clean_doi(str(reason.get("root_doi") or (reason.get("root") or {}).get("doi") or ""))
    year = _year_text(reason.get("root_year") or (reason.get("root") or {}).get("year"))
    author = _family_name(
        reason.get("root_author") or (reason.get("root") or {}).get("first_author")
    )
    for step in reason.get("steps") or []:
        if root and clean_doi(str(step.get("doi") or "")) != root:
            continue
        year = year or _year_text(step.get("year"))
        author = author or _family_name(step.get("first_author"))
        if author and year:
            break
    if graph is not None and root and (not author or not year):
        try:
            row = graph.work_row(root)
        except Exception:
            row = None
        if row:
            author = author or _family_name(row.get("first_author"))
            year = year or _year_text(row.get("year"))
    return author or "the authors", year or "n.d.", root


COCHRANE_PREFIX = "10.1002/14651858."

_SITE_NAMES = {
    "nutritionsource.hsph.harvard.edu": "Harvard Nutrition Source",
    "healthline.com": "Healthline",
    "webmd.com": "WebMD",
    "medicalnewstoday.com": "Medical News Today",
    "verywellhealth.com": "Verywell Health",
    "everydayhealth.com": "Everyday Health",
}

_HOP_VERBS = {
    "included": "includes",
    "relies": "relies on",
    "uses_data_or_method": "uses data from",
    "mention": "cites",
    "background": "mentions",
}


def _flag_phrase(payload: dict[str, Any], root: str, date: str) -> str:
    """'was retracted in May 2025' or 'was withdrawn by Cochrane on 30 Apr 2015'."""
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    withdrawn = str(reason.get("code") or "") == "withdrawal"
    when = _pretty_date(date)
    if withdrawn:
        verb = "was withdrawn by Cochrane" if clean_doi(root).startswith(COCHRANE_PREFIX) else "was withdrawn"
        return f"{verb} {_date_preposition(date)} {when}" if when else f"{verb} (withdrawal date not confirmed)"
    return f"was retracted {_date_preposition(date)} {when}" if when else "was retracted (retraction date not confirmed)"


def _page_chain(payload: dict[str, Any]) -> str:
    """'the Harvard Nutrition Source page "Vitamin D", which cites Avenell et al. 2014, which uses data from'.

    Only when the deciding path starts at a cited web page. Empty otherwise,
    so DOI-only drafts keep the short disclosure.
    """
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    steps = list(reason.get("steps") or [])
    hops = list(reason.get("hops_evidence") or [])
    if len(steps) < 2 or steps[0].get("doi") or not str(steps[0].get("url") or "").startswith("http"):
        return ""
    site = site_of(str(steps[0]["url"]))
    name = _SITE_NAMES.get(site, site)
    title = re.split(r"\s[\u2022|\u2013-]\s", str(steps[0].get("title") or ""))[0].strip()
    parts = [f'the {name} page "{title}"' if title else f"a {name} page"]
    for index, step in enumerate(steps[1:]):
        verb = _HOP_VERBS.get(str((hops[index] if index < len(hops) else {}).get("reliance") or ""), "cites")
        if index == len(steps) - 2:
            parts.append(f"which {verb}")
            break
        who = _cite_name(_family_name(step.get("first_author")) or "the authors", _year_text(step.get("year")) or "n.d.")
        parts.append(f"which {verb} {who}")
    return ", ".join(parts)


def _retraction_sentence(payload: dict[str, Any], span: str = "", graph=None) -> str:
    _label, _notice, date = _notice_label(payload)
    author, year, root = _study_cite(payload, span, graph)
    who = _cite_name(author, year)
    when = _pretty_date(date)
    if _is_predimed(payload, root):
        if not when:
            return (
                f"An earlier version of this answer cited {who} (PREDIMED); "
                f"that trial report was retracted and republished "
                f"(retraction date not confirmed), so that source was removed."
            )
        prep = _date_preposition(date)
        return (
            f"An earlier version of this answer cited {who} (PREDIMED); "
            f"that trial report was retracted and republished {prep} {when}, "
            f"so that source was removed."
        )
    flagged = _flag_phrase(payload, root, date)
    chain = _page_chain(payload)
    if chain:
        return (
            f"An earlier version of this answer cited {chain} {who}, "
            f"a paper that {flagged}, so that source was removed."
        )
    return f"An earlier version of this answer cited {who}; that paper {flagged}, so that source was removed."


def _disclose(payload: dict[str, Any], span: str = "", graph=None) -> str:
    reason = next((item for item in payload.get("reasons") or [] if item.get("code")), {})
    code = str(reason.get("code") or "")
    if code in {"retraction", "withdrawal"}:
        return _retraction_sentence(payload, span, graph)
    return _eoc_disclose(payload, span, graph)


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
        return _retraction_sentence(payload, span, graph)
    dois, _urls = _flagged(payload)
    sibling = _sibling_doi(graph, dois)
    if sibling:
        return (
            f"A related study already on this path, with no publisher notice "
            f"in range, is DOI {sibling}."
        )
    return _eoc_disclose(payload, span, graph)


UNSUPPORTED_NOTE = " (no checked source remains for this claim)"


def _soften_unsupported(pieces: list[str], replaced: set[int]) -> list[str]:
    """When every cited source was dropped, mark the claim the removed citation supported:
    the uncited sentence directly before it. Every other sentence stays byte-identical."""
    if any(_has_identifier(piece) for index, piece in enumerate(pieces) if index not in replaced):
        return pieces
    out = list(pieces)
    for index in sorted(replaced):
        prev = index - 1
        if prev < 0 or prev in replaced:
            continue
        piece = out[prev]
        body = piece.rstrip()
        tail = piece[len(body):]
        if not body or UNSUPPORTED_NOTE.strip() in body:
            continue
        stop = body[-1] if body[-1] in ".!?" else ""
        out[prev] = f"{body[:-1] if stop else body}{UNSUPPORTED_NOTE}{stop or '.'}{tail}"
    return out


def _has_identifier(text: str) -> bool:
    if text.lstrip().startswith("An earlier version of this answer"):
        return False
    found = extract_identifiers(text)
    return bool(found.dois or found.pmids or found.pmcids or found.urls)


def template_rewrite(
    payload: dict[str, Any],
    text: str = "",
    urls: list[str] | None = None,
    graph=None,
    soften_claims: bool = False,
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
    replaced: set[int] = set()
    for span in spans:
        if _span_hits(span, dois, flagged_urls):
            replacement = _replacement(payload, graph, span)
            replaced.add(len(pieces))
            pieces.append(replacement + (" " if span.endswith(" ") else ""))
        else:
            pieces.append(span)
    changed = bool(replaced)
    if changed and soften_claims and not kept_urls:
        pieces = _soften_unsupported(pieces, replaced)
    rewritten = original if not changed else "".join(pieces)
    return {
        "text": rewritten,
        "urls": kept_urls,
        "method": "template",
        "dropped": dropped,
        "untouched": not changed,
    }


def propose_rewrite(
    text: str,
    urls: list[str] | None,
    payload: dict[str, Any],
    graph=None,
    soften_claims: bool = False,
) -> dict[str, Any]:
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    return template_rewrite(payload, text, url_list, graph, soften_claims=soften_claims)


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
    soften_claims: bool = False,
) -> dict[str, Any]:
    """Check, rewrite flagged sentences, recheck. Recheck sets the exit code.

    soften_claims (agent drafts): also mark the claim the removed citation supported."""
    from mooltrace import config as _config

    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    first = check_answer(text, url_list, engine, depth, graph=graph)
    if first.get("decision") == "pass":
        code = _exit_code(first)
        return {
            "rewritten": False,
            "reason": "already pass",
            "method": None,
            "before": text,
            "text": text,
            "urls": url_list,
            "check": first,
            "recheck": first,
            "exit_code": code,
        }
    proposal = propose_rewrite(text, url_list, first, graph, soften_claims=soften_claims)
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
        "before": text,
        "text": new_text,
        "urls": proposal.get("urls") or [],
        "dropped": proposal.get("dropped") or [],
        "check": first,
        "recheck": second,
        "exit_code": code,
    }
