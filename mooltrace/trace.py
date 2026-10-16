"""Ingest a draft answer and walk RESTS_ON until a publisher notice or the depth cap."""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from mooltrace import config
from datetime import datetime, timezone, timedelta

from mooltrace.clients import (
    CallStats,
    InfraError,
    MoolTraceError,
    crossref_work,
    crossref_works,
    datacite_registered,
    datacite_work,
    doi_org_csl,
    fetch_page,
    html_title,
    openalex_by_ids,
    resolve_diabetes_care,
    openalex_doi,
    openalex_id,
    openalex_work_doi,
    openalex_work_pmid,
    pmid_record,
    pmc_to_doi,
    reference_dois,
)
from mooltrace import cypher as C
from mooltrace.decision import EXIT_INFRA, EXIT_PASS, EXIT_WARN, decide, path_score
from mooltrace.evidence import attach_hop_trail
from mooltrace.reliance import WEIGHT_FLOOR
from mooltrace.graph import Graph, get_graph
from mooltrace.reliance import PATH_RULE
from mooltrace.ssrf import UnsafeURL, public_http_url
from mooltrace.judge import judge_citation_edges
from mooltrace.ids import (
    clean_doi,
    extract_identifiers,
    has_verifiable_source,
    is_disclosure_only,
    is_publisher_flag,
    normalize_update_type,
    site_of,
    valid_doi,
)
from mooltrace import PITCH, TAGLINE
from mooltrace.progress import emit as progress

_LIMITS = (
    "MoolTrace reports a path to a publisher notice. "
    "An Expression of Concern is a different Crossref update type from a retraction. "
    "This check does not give medical advice."
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ago(iso: str | None) -> str | None:
    then = _parse_iso(iso)
    if then is None:
        return None
    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 90:
        return f"{seconds} s ago"
    if seconds < 90 * 60:
        return f"{seconds // 60} min ago"
    if seconds < 36 * 3600:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def _notice_stamp(graph: Graph, answer_id: str) -> dict[str, Any]:
    try:
        run = graph.run(
            "notice_stamp",
            """
            MATCH (a:Answer {id: $id})-[:CITES]->(:Source)-[:RESTS_ON*1..3]->(w:Work)
            WHERE w.notice_checked_at IS NOT NULL
            RETURN min(w.notice_checked_at) AS oldest, max(w.notice_checked_at) AS newest
            """,
            {"id": answer_id},
            read_only=True,
        )
    except Exception:
        return {}
    row = run.rows[0] if run.rows else {}
    oldest = row.get("oldest")
    if not oldest:
        return {}
    return {
        "notices_checked_at": oldest,
        "notices_checked_ago": _ago(str(oldest)),
    }


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _notice_fresh(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    checked_at = _parse_iso(row.get("notice_checked_at"))
    if checked_at is None:
        return bool(row.get("notice_checked")) and config.NOTICE_REFRESH_TTL_S <= 0
    age = datetime.now(timezone.utc) - checked_at
    return age <= timedelta(seconds=max(0, config.NOTICE_REFRESH_TTL_S))


def _answer_id(engine: str, text: str, urls: list[str]) -> str:
    blob = "\n".join([engine.strip().lower(), text.strip(), *sorted(urls)])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _notice_date(update: dict[str, Any]) -> str:
    updated = update.get("updated") or {}
    if updated.get("date-time"):
        return str(updated["date-time"])[:10]
    parts = (updated.get("date-parts") or [[]])[0]
    if not parts:
        return ""
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _family_name(message: dict[str, Any] | None) -> str | None:
    if not message:
        return None
    authors = message.get("author") or []
    if not authors or not isinstance(authors, list):
        return None
    first = authors[0] or {}
    family = (first.get("family") or "").strip()
    if family:
        return family
    name = (first.get("name") or "").strip()
    parts = [part for part in name.replace(".", " ").split() if len(part) > 2]
    return parts[-1] if parts else None


def _openalex_family(record: dict[str, Any]) -> str | None:
    authorships = record.get("authorships") or []
    if not authorships:
        return None
    display = ((authorships[0].get("author") or {}).get("display_name") or "").strip()
    parts = [part for part in display.replace(".", " ").split() if len(part) > 2]
    return parts[-1] if parts else None


def _openalex_pmcid(record: dict[str, Any]) -> str | None:
    raw = ((record.get("ids") or {}).get("pmcid")) or ""
    match = re.search(r"PMC\d+", str(raw), re.I)
    return match.group(0).upper() if match else None


def _issued_year(message: dict[str, Any] | None) -> int | None:
    parts = (((message or {}).get("issued") or {}).get("date-parts") or [[]])[0]
    if not parts:
        return None
    try:
        return int(parts[0])
    except (TypeError, ValueError):
        return None


def _notice_document(message: dict[str, Any] | None) -> bool:
    """True when this Crossref record is the notice, not the original article.

    A title that merely starts with "RETRACTED:" is the original article.
    """
    titles = (message or {}).get("title") or []
    title = (titles[0] if titles else "").strip().lower()
    return title.startswith(
        (
            "retraction",
            "notice of retraction",
            "expression of concern",
            "withdrawal",
            "removal",
        )
    )


def _apply_notices(graph: Graph, work_doi: str, message: dict[str, Any] | None) -> None:
    if not message:
        return
    for update in message.get("updated-by") or []:
        if not is_publisher_flag(update.get("type")):
            continue
        notice_doi = clean_doi(update.get("DOI") or "")
        if not valid_doi(notice_doi):
            continue
        graph.merge_notice(
            notice_doi,
            work_doi,
            normalize_update_type(update.get("type")),
            update.get("label") or update.get("type") or "",
            update.get("source") or "publisher",
            _notice_date(update),
        )
    if not _notice_document(message):
        return
    for update in message.get("update-to") or []:
        if not is_publisher_flag(update.get("type")):
            continue
        target = clean_doi(update.get("DOI") or "")
        if not valid_doi(target):
            continue
        graph.merge_notice(
            work_doi,
            target,
            normalize_update_type(update.get("type")),
            update.get("label") or update.get("type") or "",
            update.get("source") or "publisher",
            _notice_date(update),
        )


def _store_openalex(graph: Graph, record: dict[str, Any], **extra: Any) -> str:
    doi = openalex_doi(record)
    if not valid_doi(doi):
        return ""
    author = extra.pop("first_author", None) or _openalex_family(record)
    graph.merge_work(
        doi,
        title=record.get("display_name") or None,
        year=record.get("publication_year"),
        openalex_id=openalex_id(record) or None,
        is_retracted=record.get("is_retracted"),
        openalex_cited_by=record.get("cited_by_count"),
        work_type=record.get("type") or None,
        first_author=author,
        pmcid=_openalex_pmcid(record),
        **extra,
    )
    return doi


def notice_check(graph: Graph, dois: list[str], stats: CallStats) -> None:
    pending: list[str] = []
    for doi in _dedupe(dois):
        if not valid_doi(doi):
            continue
        row = graph.work_row(doi)
        if _notice_fresh(row):
            stats.hit()
            continue
        pending.append(doi)
    if not pending:
        return
    items = crossref_works(pending, stats)
    found: dict[str, dict[str, Any]] = {}
    for item in items:
        doi = clean_doi(item.get("DOI") or "")
        if valid_doi(doi):
            found[doi] = item
    checked_at = _now()
    for doi in pending:
        item = found.get(doi)
        if not item:
            row = graph.work_row(doi)
            already = bool(
                row
                and (
                    row.get("title")
                    or row.get("year")
                    or row.get("openalex_id")
                    or row.get("expanded")
                )
            )
            if already:
                graph.merge_work(doi, notice_checked=True, notice_checked_at=checked_at)
                continue
            if not datacite_registered(doi):
                continue
            try:
                datacite = datacite_work(doi, stats)
            except InfraError:
                raise
            except MoolTraceError:
                datacite = None
            if datacite:
                graph.merge_work(
                    doi,
                    title=datacite.get("title"),
                    year=datacite.get("year"),
                    first_author=datacite.get("first_author"),
                    notice_checked=True,
                    notice_checked_at=checked_at,
                )
            continue
        titles = item.get("title") or []
        graph.merge_work(
            doi,
            title=titles[0] if titles else None,
            first_author=_family_name(item),
            year=_issued_year(item),
            notice_checked=True,
            notice_checked_at=checked_at,
        )
        _apply_notices(graph, doi, item)


def expand_work(graph: Graph, doi: str, stats: CallStats) -> None:
    row = graph.work_row(doi)
    if row and row.get("expanded"):
        stats.hit()
        if not _notice_fresh(row):
            notice_check(graph, [doi], stats)
        return
    openalex = None
    crossref = None
    oa_failed = False
    cr_failed = False
    try:
        openalex = openalex_work_doi(doi, stats)
    except InfraError:
        raise
    except MoolTraceError:
        openalex = None
        oa_failed = True
    try:
        crossref = crossref_work(doi, stats)
    except InfraError:
        raise
    except MoolTraceError:
        crossref = None
        cr_failed = True
    datacite = None
    csl = None
    if oa_failed and cr_failed:
        raise MoolTraceError(f"could not expand {doi}: OpenAlex and Crossref both failed")
    if not openalex and not crossref:
        try:
            datacite = datacite_work(doi, stats)
        except InfraError:
            raise
        except MoolTraceError:
            datacite = None
        if not datacite:
            try:
                csl = doi_org_csl(doi, stats)
            except InfraError:
                raise
            except MoolTraceError:
                csl = None
    if not openalex and not crossref and not datacite and not csl:
        if oa_failed and cr_failed:
            raise MoolTraceError(f"could not expand {doi}: OpenAlex and Crossref both failed")
        raise MoolTraceError(f"could not resolve {doi}")
    family = _family_name(crossref) or (_openalex_family(openalex) if openalex else None)
    if openalex:
        _store_openalex(graph, openalex, first_author=family)
    elif crossref:
        titles = crossref.get("title") or []
        graph.merge_work(
            doi,
            title=titles[0] if titles else None,
            first_author=family,
            year=_issued_year(crossref),
        )
    elif datacite:
        graph.merge_work(
            doi,
            title=datacite.get("title"),
            year=datacite.get("year"),
            first_author=datacite.get("first_author") or family,
            notice_checked=True,
            notice_checked_at=_now(),
        )
    else:
        graph.merge_work(
            doi,
            title=(csl or {}).get("title"),
            year=(csl or {}).get("year"),
            notice_checked=True,
            notice_checked_at=_now(),
        )
    _apply_notices(graph, doi, crossref)

    ref_dois: list[str] = []
    cr_refs = reference_dois(crossref)
    referenced = (openalex or {}).get("referenced_works") or []
    # Crossref's reference list is enough to walk one hop. Skip the
    # OpenAlex id batch when those DOIs are already in hand.
    if referenced and not cr_refs:
        try:
            for record in openalex_by_ids(referenced, stats):
                ref = _store_openalex(graph, record)
                if ref and ref != doi:
                    graph.rest_on(doi, ref)
                    ref_dois.append(ref)
        except (MoolTraceError, InfraError):
            oa_failed = True
    for ref in cr_refs:
        if ref != doi:
            graph.merge_work(ref)
            graph.rest_on(doi, ref)
            ref_dois.append(ref)
    # Flags are written only after notices succeed. A one-sided catalog
    # failure stays retryable instead of a clean expanded state.
    notice_check(graph, [doi, *ref_dois], stats)
    if oa_failed or cr_failed:
        which = "OpenAlex" if oa_failed else "Crossref"
        raise MoolTraceError(f"could not finish expanding {doi}: {which} failed")
    graph.merge_work(doi, expanded=True)


def _resolve_loose(
    graph: Graph,
    text: str,
    stats: CallStats,
    errors: list[str],
) -> list[str]:
    found = extract_identifiers(text)
    dois = list(found.dois)
    if found.pmcids:
        try:
            mapping = pmc_to_doi(found.pmcids, stats)
        except MoolTraceError as exc:
            errors.append(str(exc))
            mapping = {}
        for pmcid in found.pmcids:
            doi = mapping.get(pmcid)
            if doi:
                dois.append(doi)
            else:
                errors.append(f"unresolved {pmcid}")
    for pmid in found.pmids:
        doi = ""
        identified = False
        meta: dict[str, Any] | None = None
        try:
            record = openalex_work_pmid(pmid, stats)
        except InfraError:
            raise
        except MoolTraceError:
            record = None
        if record and record.get("id"):
            identified = True
            doi = openalex_doi(record)
        if not valid_doi(doi):
            try:
                meta = pmid_record(pmid, stats)
            except InfraError:
                raise
            except MoolTraceError:
                meta = None
            if meta:
                identified = True
                ncbi_doi = clean_doi(str(meta.get("doi") or ""))
                if valid_doi(ncbi_doi):
                    doi = ncbi_doi
        if valid_doi(doi):
            if meta and (
                meta.get("title") or meta.get("year") or meta.get("first_author")
            ):
                graph.merge_work(
                    doi,
                    title=meta.get("title"),
                    year=meta.get("year"),
                    first_author=meta.get("first_author"),
                )
            dois.append(doi)
        elif not identified:
            errors.append(f"unresolved PMID:{pmid}")
    for volume, issue, page in found.diabetes_care:
        try:
            doi = resolve_diabetes_care(volume, issue, page, stats)
        except MoolTraceError as exc:
            errors.append(str(exc))
            doi = None
        if doi:
            dois.append(doi)
        else:
            errors.append(f"unresolved Diabetes Care {volume}({issue}):{page}")
    return _dedupe([doi for doi in dois if valid_doi(doi)])


def _page_urls(urls: list[str], text: str, errors: list[str]) -> list[str]:
    """HTTP sources to fetch. DOI, PubMed, and PMC links are resolved as ids."""
    candidates = list(urls)
    extracted = extract_identifiers(text)
    candidates.extend(extracted.urls)
    pages: list[str] = []
    for url in candidates:
        lower = url.lower()
        if lower.startswith("urn:"):
            continue
        if "doi.org/" in lower or "pubmed" in lower or "/pmc" in lower:
            continue
        try:
            public_http_url(url, reason="cited url", resolve_dns=False)
        except UnsafeURL as exc:
            errors.append(str(exc))
            continue
        if url not in pages:
            pages.append(url)
        if len(pages) >= 8:
            break
    return pages


def _ingest_pages(
    graph: Graph,
    answer_id: str,
    pages: list[str],
    stats: CallStats,
    errors: list[str],
) -> None:
    for url in pages:
        if graph.source_fetched(url):
            stats.hit()
            graph.cite(answer_id, url)
            continue
        try:
            final_url, body = fetch_page(url, stats)
        except (MoolTraceError, UnsafeURL) as exc:
            from_url = [
                doi for doi in extract_identifiers(url).dois if valid_doi(doi)
            ]
            if from_url:
                graph.merge_source(url, "", site_of(url), fetched=False)
                graph.cite(answer_id, url)
                for doi in from_url:
                    graph.merge_work(doi)
                    graph.source_rests_on(url, doi)
            else:
                errors.append(str(exc))
            continue
        title = html_title(body)
        fetched_at = _now()
        graph.merge_source(final_url, title, site_of(final_url), fetched=True, fetched_at=fetched_at)
        graph.cite(answer_id, final_url)
        if final_url != url:
            graph.merge_source(url, title, site_of(url), fetched=True, fetched_at=fetched_at)
            graph.cite(answer_id, url)
        for doi in _resolve_loose(graph, body, stats, errors):
            graph.source_rests_on(final_url, doi)


def _ingest_text(
    graph: Graph,
    answer_id: str,
    text: str,
    stats: CallStats,
    errors: list[str],
) -> None:
    if not text.strip():
        return
    paste = f"urn:mooltrace:paste:{answer_id}"
    if graph.source_fetched(paste):
        stats.hit()
        graph.cite(answer_id, paste)
        return
    before = len(errors)
    dois = _resolve_loose(graph, text, stats, errors)
    # Keep the paste unfetched when resolution failed so a later run can retry.
    graph.merge_source(paste, "Pasted draft", "paste", fetched=len(errors) == before)
    graph.cite(answer_id, paste)
    for doi in dois:
        graph.source_rests_on(paste, doi)


def _seed_resolved(row: dict[str, Any] | None) -> bool:
    """True when Crossref or OpenAlex actually returned the work.

    notice_checked with no title/year is a leftover 404 stamp, not a pass.
    """
    if not row or not _notice_fresh(row):
        return False
    return bool(
        row.get("title") or row.get("year") or row.get("openalex_id") or row.get("expanded")
    )


def _unresolved_seeds(graph: Graph, answer_id: str, errors: list[str]) -> bool:
    missing = [
        doi for doi in graph.seed_dois(answer_id) if not _seed_resolved(graph.work_row(doi))
    ]
    if not missing:
        return False
    errors.append(f"unresolved {missing[0]}")
    return True


def _deepen(graph: Graph, answer_id: str, depth: int, stats: CallStats, errors: list[str]) -> bool:
    """Return True when the walk stopped before the requested depth."""
    incomplete = False
    seeds = graph.seed_dois(answer_id)
    if depth < 2:
        try:
            notice_check(graph, seeds, stats)
        except InfraError:
            raise
        except MoolTraceError as exc:
            errors.append(str(exc))
            incomplete = True
        return incomplete or _unresolved_seeds(graph, answer_id, errors)
    expandable: list[str] = []
    stale: list[str] = []
    for doi in seeds:
        row = graph.work_row(doi)
        if row and row.get("expanded"):
            stats.hit()
            if not _notice_fresh(row):
                stale.append(doi)
        else:
            expandable.append(doi)
    leftover: list[str] = []
    if stale:
        try:
            notice_check(graph, stale, stats)
        except InfraError:
            raise
        except MoolTraceError as exc:
            errors.append(str(exc))
            incomplete = True
    if len(expandable) > config.MAX_SEEDS_TO_EXPAND:
        leftover = expandable[config.MAX_SEEDS_TO_EXPAND :]
        errors.append(
            f"expanded {config.MAX_SEEDS_TO_EXPAND} of {len(expandable)} cited works"
        )
        incomplete = True
        expandable = expandable[: config.MAX_SEEDS_TO_EXPAND]
    if leftover:
        try:
            notice_check(graph, leftover, stats)
        except InfraError:
            raise
        except MoolTraceError as exc:
            errors.append(str(exc))
            incomplete = True
    if expandable:
        progress(f"Checking notices 0/{len(expandable)}…")
    done = 0

    def _one(doi: str) -> None:
        expand_work(graph, doi, stats)

    workers = max(1, min(4, len(expandable)))
    if workers == 1:
        jobs = expandable
        for doi in jobs:
            try:
                _one(doi)
            except InfraError:
                raise
            except MoolTraceError as exc:
                errors.append(f"{doi}: {exc}")
                incomplete = True
            done += 1
            progress(f"Checking notices {done}/{len(expandable)}…")
    elif expandable:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_one, doi): doi for doi in expandable}
            for fut in as_completed(futs):
                doi = futs[fut]
                try:
                    fut.result()
                except InfraError:
                    raise
                except MoolTraceError as exc:
                    errors.append(f"{doi}: {exc}")
                    incomplete = True
                done += 1
                progress(f"Checking notices {done}/{len(expandable)}…")
    if depth >= 3:
        for doi in graph.review_neighbors(seeds, config.MAX_DEPTH3_REVIEWS):
            try:
                expand_work(graph, doi, stats)
            except InfraError:
                raise
            except MoolTraceError as exc:
                errors.append(f"{doi}: {exc}")
                incomplete = True
    return incomplete or _unresolved_seeds(graph, answer_id, errors)


def _public_path(row: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for step in row.get("steps") or []:
        if step.get("url") and not step.get("doi"):
            kind = "Source"
        else:
            kind = "Work"
        steps.append(
            {
                "kind": kind,
                "doi": step.get("doi"),
                "title": step.get("title"),
                "url": step.get("url"),
                "year": step.get("year"),
            }
        )
    hops = [attach_hop_trail(hop) for hop in (row.get("hops_evidence") or [])]
    last = hops[-1] if hops else row
    return {
        "hops": row.get("hops"),
        "path_score": row.get("path_score") if row.get("path_score") is not None else path_score({"hops_evidence": hops, **row}),
        "source_url": row.get("source_url"),
        "source_title": row.get("source_title"),
        "root": {
            "doi": row.get("root_doi"),
            "title": row.get("root_title"),
            "year": row.get("root_year"),
        },
        "notice": {
            "doi": row.get("notice_doi"),
            "type": row.get("notice_type"),
            "label": row.get("notice_label"),
            "date": row.get("notice_date"),
            "source": row.get("notice_source"),
        },
        "steps": steps,
        "hops_evidence": hops,
        "weight": last.get("weight") if isinstance(last, dict) else row.get("weight"),
        "reliance": last.get("reliance") if isinstance(last, dict) else row.get("reliance"),
        "sentence": (last.get("sentence") if isinstance(last, dict) else row.get("sentence")) or "",
        "evidence_from": (last.get("evidence_from") if isinstance(last, dict) else row.get("evidence_from")) or "",
        "judged": last.get("judged") if isinstance(last, dict) else row.get("judged"),
    }


def _clusters(graph: Graph) -> dict[str, Any]:
    """Group answers that share a Work component containing a notice."""
    try:
        run = graph.wcc_clusters()
    except InfraError:
        raise
    except Exception as exc:
        return {
            "algorithm": "algo.WCC",
            "call": C.WCC_CLUSTERS,
            "clusters": [],
            "error": str(exc),
            "note": (
                "WCC groups Work nodes connected by RESTS_ON that sit in a "
                "component with a publisher notice. It is for remediation "
                "clusters, not the pass/warn/block verdict."
            ),
        }
    return {
        "algorithm": "algo.WCC",
        "call": C.WCC_CLUSTERS,
        "cypher": run.cypher,
        "clusters": run.rows,
        "elapsed_ms": round(run.elapsed_ms, 2),
        "note": (
            "Weakly connected Work components that contain a publisher notice. "
            "Use these clusters to group answers that share a contaminated "
            "citation component. The verdict classifies algo.SPpaths rows."
        ),
    }


def _infra_check(exc: Exception, *, depth: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "product": "MoolTrace",
        "tagline": TAGLINE,
        "decision": "incomplete",
        "exit_code": EXIT_INFRA,
        "error_code": "infra",
        "summary": f"Infrastructure failure: {exc}",
        "pitch": None,
        "reasons": [{"code": "infra", "detail": str(exc)}],
        "discounted": [],
        "unjudged_paths": 0,
        "independent_sources": [],
        "independent_source_count": 0,
        "answer_id": None,
        "engine": None,
        "depth": depth,
        "paths": [],
        "works_cited": 0,
        "api_calls": 0,
        "cache_hits": 0,
        "reused_graph": False,
        "incomplete": True,
        "errors": [str(exc)],
        "queries": [],
        "cypher": None,
        "elapsed_ms": 0,
        "limits": _LIMITS,
    }
    if extra:
        payload.update(extra)
    return payload


def trace_answer(
    text: str = "",
    urls: list[str] | None = None,
    engine: str = "draft",
    depth: int = config.DEFAULT_DEPTH,
    graph: Graph | None = None,
) -> dict[str, Any]:
    graph = graph or get_graph()
    depth = config.clamp_depth(depth)
    engine = (engine or "draft").strip()[:64] or "draft"
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    stats = CallStats()
    errors: list[str] = []
    answer_id = _answer_id(engine, text or "", url_list)
    graph.merge_answer(answer_id, engine, _text_hash(text or ""), _now())

    from mooltrace.public_demo import public_demo_enabled, public_live_enabled

    skip_http = public_demo_enabled() and not public_live_enabled()
    pages = _page_urls(url_list, text or "", errors)
    if skip_http:
        incomplete = False
        if not graph.seed_dois(answer_id):
            errors.append(
                "public demo graph has no seeds for this preset; run mooltrace seed --offline"
            )
            incomplete = True
    else:
        if pages:
            progress(f"Fetching {len(pages)} page{'s' if len(pages) != 1 else ''}…")
        _ingest_pages(graph, answer_id, pages, stats, errors)
        _ingest_text(graph, answer_id, "\n".join([text or "", *url_list]), stats, errors)
        incomplete = _deepen(graph, answer_id, depth, stats, errors) or bool(errors)
    context_notes: list[str] = []
    if not skip_http:
        try:
            judge_citation_edges(
                graph,
                answer_id,
                "\n".join([text or "", *url_list]),
                stats,
                context_notes,
                depth,
            )
        except (MoolTraceError, UnsafeURL) as exc:
            errors.append(str(exc))
            incomplete = True
    path_run = graph.paths(answer_id, depth)
    paths = [_public_path(row) for row in path_run.rows]
    flagged = bool(paths)
    summary = (
        f"No flagged study within {depth} hops."
        if not flagged
        else "A path from this draft reaches a publisher notice."
    )
    queries = [path_run.as_public()]
    graph.persist()
    return {
        "product": "MoolTrace",
        "answer_id": answer_id,
        "engine": engine,
        "depth": depth,
        "flagged": flagged,
        "summary": summary,
        "pitch": PITCH if flagged else None,
        "paths": paths,
        "works_cited": len(graph.seed_dois(answer_id)),
        "api_calls": stats.api_calls,
        "cache_hits": stats.cache_hits,
        "reused_graph": stats.api_calls == 0 and stats.cache_hits > 0,
        "incomplete": incomplete,
        "errors": errors,
        "queries": queries,
        "cypher": path_run.cypher,
        "elapsed_ms": round(path_run.elapsed_ms, 2),
        "context_notes": context_notes,
        "limits": _LIMITS,
    }


def _removed_claims_check(*, text: str, urls: list[str], engine: str, depth: int) -> dict[str, Any]:
    """Pass when the draft is only a rewrite disclosure (no live citations)."""
    engine = (engine or "draft").strip()[:64] or "draft"
    return {
        "product": "MoolTrace",
        "tagline": TAGLINE,
        "decision": "pass",
        "exit_code": EXIT_PASS,
        "summary": (
            "Flagged claims were removed. Pass is not a medical-accuracy check. "
            "Coverage is not shown beyond this depth."
        ),
        "pitch": None,
        "reasons": [],
        "discounted": [],
        "unjudged_paths": 0,
        "unverified_paths": 0,
        "independent_sources": [],
        "independent_source_count": 0,
        "weight_floor": WEIGHT_FLOOR,
        "remediation_clusters": {
            "algorithm": "algo.WCC",
            "clusters": [],
            "note": "No live citation graph remains after the rewrite disclosure.",
        },
        "algorithm": None,
        "answer_id": _answer_id(engine, text, urls),
        "engine": engine,
        "depth": depth,
        "paths": [],
        "works_cited": 0,
        "api_calls": 0,
        "cache_hits": 0,
        "reused_graph": False,
        "incomplete": False,
        "errors": [],
        "context_notes": [],
        "queries": [],
        "cypher": None,
        "elapsed_ms": 0,
        "limits": _LIMITS,
    }


def _no_sources_check(*, text: str, urls: list[str], engine: str, depth: int) -> dict[str, Any]:
    """Warn when the draft named nothing MoolTrace can inspect."""
    engine = (engine or "draft").strip()[:64] or "draft"
    verdict = decide([], incomplete=False, depth=depth, has_sources=False)
    return {
        "product": "MoolTrace",
        "tagline": TAGLINE,
        "decision": verdict["decision"],
        "exit_code": verdict["exit_code"],
        "error_code": "no_sources",
        "summary": verdict["summary"],
        "pitch": None,
        "reasons": [{**reason, "cypher": None} for reason in verdict["reasons"]],
        "discounted": [],
        "unjudged_paths": 0,
        "unverified_paths": 0,
        "independent_sources": [],
        "independent_source_count": 0,
        "weight_floor": verdict["weight_floor"],
        "remediation_clusters": {
            "algorithm": "algo.WCC",
            "clusters": [],
            "note": "No citation graph was built because no verifiable source was provided.",
        },
        "answer_id": _answer_id(engine, text, urls),
        "engine": engine,
        "depth": depth,
        "paths": [],
        "works_cited": 0,
        "api_calls": 0,
        "cache_hits": 0,
        "reused_graph": False,
        "incomplete": False,
        "errors": [],
        "context_notes": [],
        "queries": [],
        "cypher": None,
        "elapsed_ms": 0,
        "limits": _LIMITS,
    }


def check_answer(
    text: str = "",
    urls: list[str] | None = None,
    engine: str = "draft",
    depth: int = config.DEFAULT_DEPTH,
    graph: Graph | None = None,
) -> dict[str, Any]:
    """Pre-ship check. Returns pass, warn, block, or incomplete (infra)."""
    depth = config.clamp_depth(depth)
    url_list = [url.strip() for url in (urls or []) if url and url.strip()]
    if not has_verifiable_source(text or "", url_list):
        if is_disclosure_only(text or "", url_list):
            return _removed_claims_check(
                text=text or "", urls=url_list, engine=engine, depth=depth
            )
        return _no_sources_check(text=text or "", urls=url_list, engine=engine, depth=depth)
    try:
        traced = trace_answer(text=text, urls=urls, engine=engine, depth=depth, graph=graph)
    except InfraError as exc:
        return _infra_check(exc, depth=depth)
    except (MoolTraceError, UnsafeURL) as exc:
        return _infra_check(exc, depth=depth) | {
            "decision": "warn",
            "exit_code": EXIT_WARN,
            "error_code": "error",
            "summary": (
                "MoolTrace could not finish this pre-ship check, so the draft "
                f"is a warn rather than a pass. Depth requested: {depth}."
            ),
        }
    graph = graph or get_graph()
    costs: dict[str, float] = {}
    try:
        sp_run = graph.sp_paths(traced["answer_id"], traced["depth"])
    except Exception as exc:
        return _infra_check(
            exc,
            depth=traced["depth"],
            extra={
                "answer_id": traced["answer_id"],
                "engine": traced.get("engine"),
                "errors": list(traced.get("errors") or []) + [str(exc)],
                "algorithm": None,
            },
        )
    sp_paths = []
    for row in sp_run.rows:
        path = _public_path(row)
        doi = (row.get("root_doi") or "").lower()
        try:
            path["sp_cost"] = float(row.get("sp_cost"))
            if doi and doi not in costs:
                costs[doi] = path["sp_cost"]
        except (TypeError, ValueError):
            pass
        sp_paths.append(path)
    # algo.SPpaths must succeed (else exit 3). Classify only those rows.
    # Zero rows is a pass here: PATHS_TO_NOTICE is the trace listing, not
    # a second verdict. Strength is the product of RESTS_ON weights.
    verdict = decide(
        list(sp_paths),
        incomplete=traced["incomplete"],
        depth=traced["depth"],
        has_sources=True,
        sp_cost=costs,
    )
    counted = any(
        reason.get("code") not in {None, "incomplete", "no_sources"}
        for reason in verdict["reasons"]
    )
    pitch = PITCH if verdict["decision"] in {"warn", "block"} and counted else None
    clusters = _clusters(graph)
    queries = list(traced["queries"])
    deciding_cypher = traced["cypher"]
    algorithm = None
    if sp_run is not None:
        queries.append(sp_run.as_public())
        deciding_cypher = sp_run.cypher
        best = sp_run.rows[0] if sp_run.rows else None
        strength = None
        if verdict.get("reasons"):
            try:
                strength = float(verdict["reasons"][0].get("path_score"))
            except (TypeError, ValueError):
                strength = None
        if strength is None and best is not None and best.get("path_score") is not None:
            try:
                strength = float(best.get("path_score"))
            except (TypeError, ValueError):
                strength = None
        strength_txt = f"{strength:.2f}" if isinstance(strength, float) else "n/a"
        algorithm = {
            "name": "algo.SPpaths",
            "weight_prop": "cost",
            "cost_formula": "-ln(weight)",
            "strength": strength,
            "weight_floor": WEIGHT_FLOOR,
            "cypher": sp_run.cypher,
            "explanation": (
                f"Decided by: algo.SPpaths, path strength {strength_txt}"
            ),
        }
    if clusters.get("cypher"):
        queries.append(
            {
                "name": "wcc_clusters",
                "cypher": clusters["cypher"],
                "params": {},
                "elapsed_ms": clusters.get("elapsed_ms"),
                "rows": len(clusters.get("clusters") or []),
            }
        )
    impact = None
    notice_doi = next(
        (reason.get("notice_doi") for reason in verdict["reasons"] if reason.get("notice_doi")),
        None,
    )
    if notice_doi and verdict["decision"] in {"warn", "block"}:
        try:
            reverse = what_rests_on(str(notice_doi), graph=graph, depth=traced["depth"])
            counted_ids = reverse.get("counted_answer_ids") or []
            kind = reverse.get("notice_type") or "notice"
            if kind == "expression_of_concern":
                label = "Expression of Concern"
            elif "retract" in str(kind):
                label = "retraction"
            else:
                label = "publisher notice"
            n = len(counted_ids) or int(reverse.get("answer_count") or 0)
            impact = {
                "notice_doi": reverse.get("notice_doi") or notice_doi,
                "notice_type": reverse.get("notice_type"),
                "root_doi": reverse.get("root_doi"),
                "answer_count": reverse.get("answer_count") or 0,
                "counted_answer_count": len(counted_ids),
                "engines": reverse.get("engines") or [],
                "cypher": reverse.get("cypher"),
                "summary": (
                    f"This {label} affects {n} stored "
                    f"{'answer' if n == 1 else 'answers'}."
                ),
            }
            if reverse.get("queries"):
                queries.extend(reverse["queries"])
        except Exception:
            impact = None
    stamp = _notice_stamp(graph, traced["answer_id"])
    payload = {
        "product": "MoolTrace",
        "tagline": TAGLINE,
        "decision": verdict["decision"],
        "exit_code": verdict["exit_code"],
        "summary": verdict["summary"],
        "pitch": pitch,
        "reasons": [{**reason, "cypher": deciding_cypher} for reason in verdict["reasons"]],
        "discounted": verdict["discounted"],
        "unjudged_paths": verdict["unjudged_paths"],
        "unverified_paths": verdict.get("unverified_paths"),
        "independent_sources": verdict["independent_sources"],
        "independent_source_count": verdict["independent_source_count"],
        "weight_floor": verdict["weight_floor"],
        "strength_floor": verdict.get("strength_floor"),
        "path_rule": verdict.get("path_rule"),
        "decided_by": verdict.get("decided_by"),
        "coverage": verdict.get("coverage"),
        "not_shown": verdict.get("not_shown"),
        "remediation_clusters": clusters,
        "algorithm": algorithm,
        "impact": impact,
        "answer_id": traced["answer_id"],
        "engine": traced["engine"],
        "depth": traced["depth"],
        "paths": traced["paths"],
        "works_cited": traced["works_cited"],
        "api_calls": traced["api_calls"],
        "cache_hits": traced["cache_hits"],
        "reused_graph": traced["reused_graph"],
        "incomplete": traced["incomplete"],
        "errors": traced["errors"],
        "context_notes": traced.get("context_notes") or [],
        "queries": queries,
        "cypher": deciding_cypher,
        "elapsed_ms": traced["elapsed_ms"],
        "limits": traced["limits"],
        **stamp,
    }
    if verdict.get("error_code"):
        payload["error_code"] = verdict["error_code"]
    return payload


def check_study(identifier: str, graph: Graph | None = None) -> dict[str, Any]:
    graph = graph or get_graph()
    stats = CallStats()
    raw = identifier.strip()
    doi = clean_doi(raw)
    if raw.upper().startswith("PMC"):
        mapping = pmc_to_doi([raw.upper()], stats)
        doi = mapping.get(raw.upper(), "")
    elif raw.isdigit() or raw.lower().startswith("pmid:"):
        pmid = raw.split(":")[-1]
        record = openalex_work_pmid(pmid, stats)
        doi = openalex_doi(record) if record else ""
        if not valid_doi(doi):
            meta = pmid_record(pmid, stats)
            doi = clean_doi(str((meta or {}).get("doi") or ""))
    if not valid_doi(doi):
        raise MoolTraceError(f"could not resolve a DOI from {identifier!r}")
    row = graph.work_row(doi)
    if not row or not row.get("openalex_id"):
        record = openalex_work_doi(doi, stats)
        if record:
            _store_openalex(graph, record)
            row = graph.work_row(doi)
    if not _notice_fresh(row):
        notice_check(graph, [doi], stats)
    notices = graph.notices_for(doi)
    citers = graph.citers(doi)
    sources = graph.sources_for(doi)
    work = graph.work_row(doi) or {}
    flagged = bool(notices.rows)
    graph.persist()
    return {
        "doi": doi,
        "title": work.get("title"),
        "year": work.get("year"),
        "openalex_id": work.get("openalex_id"),
        "openalex_cited_by": work.get("openalex_cited_by"),
        "is_retracted": work.get("is_retracted"),
        "flagged": flagged,
        "notices": notices.rows,
        "citers_in_graph": citers.rows,
        "sources_in_graph": sources.rows,
        "api_calls": stats.api_calls,
        "cache_hits": stats.cache_hits,
        "queries": [notices.as_public(), citers.as_public(), sources.as_public()],
        "cypher": notices.cypher,
        "elapsed_ms": round(notices.elapsed_ms + citers.elapsed_ms + sources.elapsed_ms, 2),
        "note": (
            "OpenAlex is_retracted can stay false when Crossref carries an "
            "Expression of Concern. The notice list is the publisher flag."
        ),
    }


def what_rests_on(doi: str, graph: Graph | None = None, depth: int | None = None) -> dict[str, Any]:
    graph = graph or get_graph()
    stats = CallStats()
    target = clean_doi(doi)
    if not valid_doi(target):
        raise MoolTraceError(f"not a DOI: {doi!r}")
    row = graph.work_row(target)
    known = graph.run(
        "notice_present",
        "MATCH (n:Notice {doi: $doi}) RETURN n.doi AS doi LIMIT 1",
        {"doi": target},
        read_only=True,
    )
    if not known.rows and not _notice_fresh(row):
        message = crossref_work(target, stats)
        _apply_notices(graph, target, message)
        title = None
        if message:
            titles = message.get("title") or []
            title = titles[0] if titles else None
        graph.merge_work(
            target,
            title=title,
            notice_checked=True,
            notice_checked_at=_now(),
        )
    impact = graph.what_rests_on(target, depth)
    upstream = graph.upstream_works(target)
    notices = [
        {
            "notice_doi": item.get("notice_doi"),
            "notice_type": item.get("notice_type"),
            "notice_label": item.get("notice_label"),
            "notice_date": item.get("notice_date"),
            "notice_source": item.get("notice_source"),
            "root_doi": item.get("root_doi"),
            "counted_answer_ids": item.get("counted_answer_ids") or [],
            "answer_ids": item.get("answer_ids") or [],
        }
        for item in impact.rows
    ]
    head = impact.rows[0] if impact.rows else {}
    counted_ids = head.get("counted_answer_ids") or []
    n = len(counted_ids)
    kind = head.get("notice_type") or ""
    if kind == "expression_of_concern":
        label = "Expression of Concern"
    elif "retract" in str(kind):
        label = "retraction"
    elif "withdraw" in str(kind):
        label = "withdrawal"
    else:
        label = "publisher notice"
    impact_summary = f"This {label} affects {n} stored {'answer' if n == 1 else 'answers'}."
    graph.persist()
    return {
        "query_doi": target,
        "notice_doi": head.get("notice_doi"),
        "notice_type": head.get("notice_type"),
        "notice_label": head.get("notice_label"),
        "notice_date": head.get("notice_date"),
        "notice_source": head.get("notice_source"),
        "root_doi": head.get("root_doi"),
        "root_title": head.get("root_title"),
        "root_year": head.get("root_year"),
        "answer_ids": head.get("answer_ids") or [],
        "counted_answer_ids": head.get("counted_answer_ids") or [],
        "engines": head.get("engines") or [],
        "source_urls": head.get("source_urls") or [],
        "answer_count": head.get("answer_count") or 0,
        "counted_answer_count": n,
        "source_count": head.get("source_count") or 0,
        "summary": impact_summary,
        "notices": notices,
        "upstream_works": upstream.rows,
        "api_calls": stats.api_calls,
        "queries": [impact.as_public(), upstream.as_public()],
        "cypher": impact.cypher,
        "elapsed_ms": round(impact.elapsed_ms, 2),
        "upstream_elapsed_ms": round(upstream.elapsed_ms, 2),
        "path_rule": PATH_RULE,
        "note": (
            "Reverse lookup lists matching publisher notices and only the "
            "answers whose sources reach that work. counted_answer_ids uses "
            "the same hop gate as forward verdicts: every hop has a "
            "stored sentence and each hop weight is ≥ 0.5. A multiplied "
            "path-strength floor is not applied. This is not a monitoring "
            "or alert scheduler."
        ),
    }


def recheck_affected(
    doi: str,
    graph: Graph | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    """Re-run check_answer on every counted answer that rests on this notice."""
    graph = graph or get_graph()
    depth = config.clamp_depth(depth)
    impact = what_rests_on(doi, graph=graph, depth=depth)
    ids = list(impact.get("counted_answer_ids") or [])
    rechecks: list[dict[str, Any]] = []
    for answer_id in ids:
        inputs = graph.answer_inputs(answer_id)
        urls = [
            url
            for url in (inputs.get("urls") or [])
            if url and not str(url).startswith("urn:")
        ]
        dois = [item for item in (inputs.get("dois") or []) if item]
        # URL-only answers (the olive-oil BLOCK preset) had empty draft
        # text. First-hop work DOIs are not that draft; stuffing them into
        # text mints a new answer_id, so the public-demo replay misses the
        # seeded graph and warns incomplete.
        text = "" if urls else " ".join(f"DOI {item}" for item in dois)
        payload = check_answer(
            text=text,
            urls=urls,
            engine=str(inputs.get("engine") or "draft"),
            depth=depth,
            graph=graph,
        )
        rec = {
            "answer_id": answer_id,
            "engine": payload.get("engine"),
            "decision": payload.get("decision"),
            "exit_code": payload.get("exit_code"),
            "summary": payload.get("summary"),
            "incomplete": bool(payload.get("incomplete")),
        }
        if rec["incomplete"]:
            from mooltrace.public_demo import public_demo_enabled, public_live_enabled

            rec["errors"] = list(payload.get("errors") or [])[:8]
            rec["note"] = (
                "recheck incomplete in read-only demo"
                if public_demo_enabled() and not public_live_enabled()
                else "recheck could not finish this check"
            )
        rechecks.append(rec)
    return {
        "query_doi": impact.get("query_doi") or doi,
        "notice_doi": impact.get("notice_doi"),
        "notice_type": impact.get("notice_type"),
        "affected": len(ids),
        "counted_answer_ids": ids,
        "summary": impact.get("summary"),
        "rechecks": rechecks,
        "cypher": impact.get("cypher"),
        "impact": impact,
    }


def explain_path(
    text: str = "",
    urls: list[str] | None = None,
    engine: str = "draft",
    depth: int = config.DEFAULT_DEPTH,
    graph: Graph | None = None,
) -> dict[str, Any]:
    """Show the algorithm call and the deciding path for one check."""
    payload = check_answer(text, urls, engine, depth, graph=graph)
    reason = next((item for item in payload.get("reasons") or [] if item.get("steps")), None)
    if reason is None and payload.get("reasons"):
        reason = payload["reasons"][0]
    return {
        "decision": payload.get("decision"),
        "exit_code": payload.get("exit_code"),
        "algorithm": payload.get("algorithm"),
        "cypher": payload.get("cypher"),
        "reason": reason,
        "explanation": (payload.get("algorithm") or {}).get("explanation"),
        "notices_checked_ago": payload.get("notices_checked_ago"),
    }


def shared_ancestors(
    answer_a: str = "",
    answer_b: str = "",
    engine_a: str = "",
    engine_b: str = "",
    graph: Graph | None = None,
) -> dict[str, Any]:
    graph = graph or get_graph()
    first = answer_a or (graph.latest_answer(engine_a) if engine_a else None)
    second = answer_b or (graph.latest_answer(engine_b) if engine_b else None)
    if not first or not second:
        raise MoolTraceError("shared_ancestors needs two answer ids or two engine names already in the graph")
    hubs = graph.shared_hubs([first, second])
    hops_a = graph.first_hops(first)
    hops_b = graph.first_hops(second)
    return {
        "answer_a": first,
        "answer_b": second,
        "shared_hubs": hubs.rows,
        "first_hops": {
            first: (hops_a.rows[0].get("first_hops") if hops_a.rows else []) or [],
            second: (hops_b.rows[0].get("first_hops") if hops_b.rows else []) or [],
        },
        "queries": [hubs.as_public(), hops_a.as_public(), hops_b.as_public()],
        "cypher": hubs.cypher,
        "elapsed_ms": round(hubs.elapsed_ms + hops_a.elapsed_ms + hops_b.elapsed_ms, 2),
        "independence_note": (
            "Independent sources are direct citers of a flagged study whose "
            "citation weight is at least 0.5 and whose deciding sentence is stored. "
            "Distinct first-hop works are listed separately. "
            "algo.MaxFlow is not registered in FalkorDBLite 0.10.0 "
            "(dbms.procedures lists betweenness, BFS, labelPropagation, MSF, "
            "pageRank, SPpaths, SSpaths, WCC), so a node-disjoint count is not claimed."
        ),
    }


_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP|LOAD)\b",
    re.I,
)


def _cypher_without_strings(query: str) -> str:
    """Strip quoted literals so LIMIT/SET inside strings are not parsed as clauses."""
    out: list[str] = []
    i = 0
    length = len(query)
    while i < length:
        ch = query[i]
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            while i < length:
                if query[i] == "\\":
                    i += 2
                    continue
                if query[i] == quote:
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def ro_cypher(statement: str, timeout_ms: int = config.RO_QUERY_TIMEOUT_MS, graph: Graph | None = None) -> dict[str, Any]:
    """Read-only Cypher via FalkorDB GRAPH.RO_QUERY, with a timeout and a LIMIT."""
    graph = graph or get_graph()
    query = (statement or "").strip().rstrip(";")
    if not query:
        raise MoolTraceError("query is empty")
    bare = _cypher_without_strings(query)
    if _WRITE_RE.search(bare):
        raise MoolTraceError(
            "ro_cypher only accepts read-only Cypher. "
            "FalkorDB GRAPH.RO_QUERY is the write barrier; MoolTrace also rejects writes first."
        )
    if re.search(r"\bRETURN\b", bare, re.I) and not re.search(r"\bLIMIT\b", bare, re.I):
        query = f"{query}\nLIMIT {config.RO_QUERY_LIMIT}"
    timeout_ms = max(100, min(15000, int(timeout_ms)))
    run = graph.ro_cypher(query, timeout_ms=timeout_ms)
    rows = run.rows[: config.RO_QUERY_LIMIT]
    columns = list(rows[0].keys()) if rows else []
    return {
        "cypher": run.cypher,
        "columns": columns,
        "rows": rows,
        "elapsed_ms": round(run.elapsed_ms, 2),
        "timeout_ms": timeout_ms,
        "truncated_to": config.RO_QUERY_LIMIT,
        "row_count_before_cap": len(run.rows),
    }
