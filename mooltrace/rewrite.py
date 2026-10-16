"""Propose a rewrite after warn/block, then re-run check_answer.

The graph decides. The model may draft prose. Code strips flagged URLs
and DOIs. Azure AI Foundry is optional; a template always works.
"""

from __future__ import annotations

from typing import Any

from mooltrace import config
from mooltrace.clients import MoolTraceError
from mooltrace.ids import clean_doi, extract_identifiers, valid_doi
from mooltrace.trace import check_answer


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
    blob = " ".join([text, *urls])
    found = extract_identifiers(blob)
    if any(clean_doi(doi) in dois for doi in found.dois):
        return True
    for url in list(found.urls) + urls:
        if url.rstrip("/") in flagged_urls:
            return True
    return False


def template_rewrite(payload: dict[str, Any]) -> dict[str, Any]:
    dois, urls = _flagged(payload)
    dropped = sorted(dois | urls)
    kind = next(
        (reason.get("code") for reason in payload.get("reasons") or [] if reason.get("code")),
        "notice",
    )
    if kind == "expression_of_concern":
        label = "Expression of Concern"
    elif kind in {"retraction", "withdrawal"}:
        label = kind
    else:
        label = "publisher notice"
    article = "an" if label[:1].lower() in "aeiou" else "a"
    text = (
        "This draft does not rely on the previously cited page or study. "
        f"Those citations reach {article} {label}, so they are not used here. "
        f"A source with no publisher notice in range at depth 2 is DOI {config.CLEAN_REWRITE_DOI}. "
        "This is not medical advice."
    )
    return {
        "text": text,
        "urls": [],
        "method": "template",
        "dropped": dropped,
        "clean_doi": config.CLEAN_REWRITE_DOI,
    }


def _azure_rewrite(text: str, urls: list[str], payload: dict[str, Any]) -> dict[str, Any] | None:
    from mooltrace.foundry import complete

    dois, flagged_urls = _flagged(payload)
    prompt = (
        "Rewrite this health-AI draft so it does not cite these URLs or DOIs:\n"
        f"{sorted(dois | flagged_urls)}\n\n"
        "You may cite this clean DOI instead: "
        f"{config.CLEAN_REWRITE_DOI}\n"
        "Name the publisher notice type if present, but do not call an "
        "Expression of Concern a retraction.\n\n"
        f"Draft:\n{text}\n\nCited URLs:\n" + "\n".join(urls)
    )
    try:
        drafted = complete(prompt)
    except MoolTraceError:
        return None
    proposal = {
        "text": drafted,
        "urls": [],
        "method": "azure-foundry",
        "dropped": sorted(dois | flagged_urls),
        "clean_doi": config.CLEAN_REWRITE_DOI,
    }
    if still_cites(proposal["text"], proposal["urls"], payload):
        return None
    if config.CLEAN_REWRITE_DOI not in proposal["text"].lower() and not extract_identifiers(
        proposal["text"]
    ).dois:
        proposal["text"] = (
            drafted.rstrip()
            + f" A checked source is DOI {config.CLEAN_REWRITE_DOI}."
        )
    return proposal


def propose_rewrite(
    text: str,
    urls: list[str] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    azure = _azure_rewrite(text, url_list, payload)
    if azure is not None:
        return azure
    return template_rewrite(payload)


def rewrite_answer(
    text: str = "",
    urls: list[str] | None = None,
    engine: str = "draft",
    depth: int = config.DEFAULT_DEPTH,
    graph=None,
) -> dict[str, Any]:
    """Check, rewrite if flagged, recheck. The recheck is the action."""
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    first = check_answer(text, url_list, engine, depth, graph=graph)
    if first.get("decision") == "pass":
        return {
            "rewritten": False,
            "reason": "already pass",
            "method": None,
            "text": text,
            "urls": url_list,
            "check": first,
            "recheck": first,
        }
    proposal = propose_rewrite(text, url_list, first)
    second = check_answer(
        proposal["text"],
        proposal.get("urls") or [],
        engine,
        depth,
        graph=graph,
    )
    return {
        "rewritten": True,
        "reason": first.get("decision"),
        "method": proposal.get("method"),
        "text": proposal["text"],
        "urls": proposal.get("urls") or [],
        "dropped": proposal.get("dropped") or [],
        "check": first,
        "recheck": second,
    }
