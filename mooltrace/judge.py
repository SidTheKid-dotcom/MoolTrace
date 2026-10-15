"""Judge each RESTS_ON edge that lands on a flagged study. Once.

The citation edge in this graph is RESTS_ON (a work or a page citing a
work). Answer-[:CITES]->Source only records that the draft named the page.
A judged edge is never sent back to Semantic Scholar or the full text.
"""

from __future__ import annotations

from typing import Any

from mooltrace.clients import CallStats, MoolTraceError, openalex_context_record
from mooltrace.contexts import (
    abstract_candidates,
    draft_candidates,
    europepmc_pmcid,
    europepmc_reference_lines,
    europepmc_work,
    fetch_page_html,
    inverted_abstract,
    legally_open_links,
    open_access_candidates,
    page_candidates,
    pmc_author,
    pmc_html_sentences,
    pmc_included_studies,
    pmc_oa_xml,
    pmc_sentences_for,
    semantic_scholar_contexts,
    s2_disabled,
)
from mooltrace.graph import Graph
from mooltrace.reliance import (
    WEIGHT_FLOOR,
    Reliance,
    as_source_list,
    choose_reliance,
    prefer_included,
)


def _edge_key(row: dict[str, Any]) -> tuple[str, str]:
    citer = row.get("citer_doi") or row.get("citer_url") or ""
    return citer, row.get("root_doi") or ""


def _priority(row: dict[str, Any]) -> tuple[int, int]:
    page = 0 if row.get("citer_url") else 1
    return page, 0


def _store(graph: Graph, row: dict[str, Any], item: Reliance) -> None:
    graph.set_reliance(
        row.get("citer_doi") or None,
        row.get("citer_url") or None,
        row["root_doi"],
        reliance=item.reliance,
        weight=item.weight,
        sentence=item.sentence,
        evidence_from=item.evidence_from,
    )


def _store_unverified(
    graph: Graph,
    row: dict[str, Any],
    sentence: str = "",
    evidence_from: str = "",
) -> None:
    """A path was found and no in-text sentence qualified. This cannot pass."""
    graph.set_reliance(
        row.get("citer_doi") or None,
        row.get("citer_url") or None,
        row["root_doi"],
        reliance="unverified",
        weight=0.0,
        sentence=sentence,
        evidence_from=evidence_from,
    )


def _year(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _finish(candidates: list[tuple[str, str]], row: dict[str, Any]) -> Reliance | None:
    picked = choose_reliance(
        candidates,
        cited_doi=row.get("root_doi"),
        cited_author=row.get("root_author") or "",
        cited_title=row.get("root_title") or "",
        cited_year=row.get("root_year"),
    )
    if picked and candidates and all(source == "page_list" for _, source in candidates):
        picked = as_source_list(picked)
    return picked


def _judge_page(
    graph: Graph,
    row: dict[str, Any],
    draft: str,
    stats: CallStats,
    notes: list[str],
) -> bool:
    url = row.get("citer_url") or ""
    author = row.get("root_author") or ""
    title = row.get("root_title") or ""
    doi = row.get("root_doi") or ""
    if url.startswith("urn:mooltrace:paste:"):
        candidates = draft_candidates(draft, cited_doi=doi, cited_author=author, cited_title=title)
        picked = _finish(candidates, row)
        if picked:
            _store(graph, row, picked)
        else:
            _store_unverified(graph, row)
        return True
    try:
        html_text = fetch_page_html(url, stats)
    except MoolTraceError as exc:
        notes.append(f"page context unavailable for {url}: {exc}")
        return False
    candidates = page_candidates(html_text, cited_doi=doi, cited_author=author, cited_title=title)
    picked = _finish(candidates, row)
    if picked:
        _store(graph, row, picked)
    else:
        _store_unverified(graph, row)
    return True


def _counted(
    row: dict[str, Any],
    by_doi: dict[str, list[tuple[str, str]]],
    included_by_doi: dict[str, Reliance] | None = None,
) -> bool:
    doi = row.get("root_doi") or ""
    if included_by_doi and doi in included_by_doi:
        return True
    picked = _finish(by_doi.get(doi, []), row)
    return picked is not None and picked.weight >= WEIGHT_FLOOR


def _extend(bucket: dict[str, list[tuple[str, str]]], doi: str, sentences: list[str], source: str) -> None:
    for sentence in sentences:
        bucket.setdefault(doi, []).append((sentence, source))


def _judge_work_group(
    graph: Graph,
    rows: list[dict[str, Any]],
    stats: CallStats,
    notes: list[str],
) -> int:
    citer = rows[0].get("citer_doi") or ""
    answered = False
    by_doi: dict[str, list[tuple[str, str]]] = {}
    included_by_doi: dict[str, Reliance] = {}

    s2 = semantic_scholar_contexts(citer, stats)
    if s2 is None and s2_disabled() and not any(note.startswith("Semantic Scholar") for note in notes):
        notes.append("Semantic Scholar rate-limited citation contexts after retries")
    if s2 is not None:
        answered = True
        for row in rows:
            doi = row.get("root_doi") or ""
            _extend(by_doi, doi, s2.get(doi, []), "semantic_scholar")

    pmcid = (rows[0].get("citer_pmcid") or "") or ""
    eupmc = europepmc_work(citer, stats)
    if eupmc is not None:
        answered = True
    if not pmcid and eupmc is not None:
        found = europepmc_pmcid(citer, stats)
        pmcid = found or ""
        if pmcid:
            graph.merge_work(citer, pmcid=pmcid)

    targets = [
        {
            "doi": row.get("root_doi") or "",
            "author": row.get("root_author") or "",
            "title": row.get("root_title") or "",
            "year": _year(row.get("root_year")),
        }
        for row in rows
    ]
    dois = [item["doi"] for item in targets]
    if pmcid:
        xml_map = pmc_sentences_for(pmcid, dois, stats)
        if xml_map is not None:
            answered = True
            for doi, sentences in xml_map.items():
                _extend(by_doi, doi, sentences, "europepmc_xml")
        html_map = pmc_html_sentences(pmcid, targets, stats)
        if html_map is not None:
            answered = True
            for doi, sentences in html_map.items():
                _extend(by_doi, doi, sentences, "pmc_html")
        included_by_doi.update(pmc_included_studies(pmcid, dois, stats))
        if included_by_doi:
            answered = True
        if any(not _counted(row, by_doi, included_by_doi) for row in rows):
            oa_xml = pmc_oa_xml(pmcid, stats)
            if oa_xml is not None:
                answered = True
            if oa_xml:
                oa_map = pmc_sentences_for(pmcid, dois, stats, xml_text=oa_xml)
                if oa_map:
                    for doi, sentences in oa_map.items():
                        _extend(by_doi, doi, sentences, "pmc_oa")
                included_by_doi.update(pmc_included_studies(pmcid, dois, stats, xml_text=oa_xml))

    alex: dict[str, Any] | None = None
    weak = [row for row in rows if not _counted(row, by_doi, included_by_doi)]
    if weak:
        try:
            alex = openalex_context_record(citer, stats)
        except MoolTraceError as exc:
            notes.append(f"OpenAlex abstract unavailable for {citer}: {exc}")
            alex = None
        if alex is not None:
            answered = True
            abstract = inverted_abstract(alex.get("abstract_inverted_index"))
            if abstract:
                for row in weak:
                    by_doi.setdefault(row.get("root_doi") or "", []).extend(
                        abstract_candidates(
                            abstract,
                            cited_doi=row.get("root_doi") or "",
                            cited_author=row.get("root_author") or "",
                            cited_title=row.get("root_title") or "",
                        )
                    )
        links = legally_open_links(eupmc if isinstance(eupmc, dict) else None, alex)
        if links:
            try:
                opened = open_access_candidates(links, targets, stats)
            except MoolTraceError as exc:
                notes.append(f"open-access context unavailable: {exc}")
                opened = {}
            if opened:
                answered = True
                for doi, pairs in opened.items():
                    by_doi.setdefault(doi, []).extend(pairs)

    ref_lines: dict[str, str] | None = None
    still_open = [
        row
        for row in rows
        if not (
            (
                picked := prefer_included(
                    _finish(by_doi.get(row.get("root_doi") or "", []), row),
                    included_by_doi.get(row.get("root_doi") or ""),
                )
            )
            and picked.sentence
        )
    ]
    if still_open:
        ref_lines = europepmc_reference_lines(citer, targets, stats)
        if ref_lines is not None:
            answered = True

    stored = 0
    for row in rows:
        doi = row.get("root_doi") or ""
        if pmcid and not row.get("root_author"):
            author = pmc_author(pmcid, doi, stats)
            if author:
                row["root_author"] = author
        candidates = by_doi.get(doi, [])
        best = prefer_included(
            _finish(candidates, row) if candidates else None,
            included_by_doi.get(doi),
        )
        if best:
            _store(graph, row, best)
            notes.append(f"{citer} → {doi}: {best.evidence_from}")
            stored += 1
            continue
        line = (ref_lines or {}).get(doi) or ""
        if line:
            _store_unverified(graph, row, line, "europepmc_references")
            notes.append(f"{citer} → {doi}: europepmc_references")
            stored += 1
            continue
        if not answered:
            continue
        _store_unverified(graph, row)
        notes.append(f"{citer} → {doi}: no sentence")
        stored += 1
    return stored


def judge_citation_edges(
    graph: Graph,
    answer_id: str,
    draft_text: str,
    stats: CallStats,
    notes: list[str],
    depth: int | None = None,
) -> int:
    """Judge unjudged edges into a flagged work. Returns how many were stored."""
    rows = graph.citation_edges(answer_id, depth).rows
    pending: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("judged") is True:
            continue
        key = _edge_key(row)
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        pending.append(row)
    pending.sort(key=_priority)
    if len(pending) > 30:
        notes.append(f"judged 30 of {len(pending)} citation edges into flagged studies")
        pending = pending[:30]

    stored = 0
    works: dict[str, list[dict[str, Any]]] = {}
    for row in pending:
        if row.get("citer_doi"):
            works.setdefault(row["citer_doi"], []).append(row)
        elif _judge_page(graph, row, draft_text, stats, notes):
            stored += 1
    for group in works.values():
        stored += _judge_work_group(graph, group, stats, notes)
    return stored
