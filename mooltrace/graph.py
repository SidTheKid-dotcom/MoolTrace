"""Persistent FalkorDB graph. The same file is reused across processes.

FalkorDBLite 0.10 ships its embedded client as the ``redislite`` module
inside the wheel. Import ``falkordblite`` when a future wheel exposes it.
"""

from __future__ import annotations

import atexit
import fcntl
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mooltrace.clients import InfraError
from mooltrace.config import GRAPH_NAME, RO_QUERY_TIMEOUT_MS, clamp_depth
from mooltrace import cypher as C
from mooltrace.ids import cochrane_withdrawal
from mooltrace.reliance import UNJUDGED_COST, hop_cost

_WORK_FIELDS = frozenset(
    {
        "title",
        "year",
        "openalex_id",
        "is_retracted",
        "openalex_cited_by",
        "work_type",
        "first_author",
        "pmcid",
        "expanded",
        "notice_checked",
        "notice_checked_at",
    }
)

_INDEXES = (
    "CREATE INDEX FOR (w:Work) ON (w.doi)",
    "CREATE INDEX FOR (w:Work) ON (w.openalex_id)",
    "CREATE INDEX FOR (a:Answer) ON (a.id)",
    "CREATE INDEX FOR (n:Notice) ON (n.doi)",
    "CREATE INDEX FOR (s:Source) ON (s.url)",
)


def _open_falkordb(path: str):
    """Open the embedded server. One process starts it; others wait on the lock."""
    try:
        from falkordblite import FalkorDB
    except ImportError:
        from redislite import FalkorDB
    db_path = Path(path)
    lock_path = Path(str(db_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            return FalkorDB(str(db_path))
        except Exception as exc:
            raise InfraError("graph backend failed to start") from exc


def _plain(value: Any) -> Any:
    if isinstance(value, OrderedDict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass
class QueryRun:
    name: str
    cypher: str
    params: dict[str, Any]
    elapsed_ms: float
    rows: list[dict[str, Any]] = field(default_factory=list)

    def as_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cypher": self.cypher,
            "params": _plain(self.params),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "rows": len(self.rows),
        }


class Graph:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = _open_falkordb(str(self.path))
            self.graph = self.db.select_graph(GRAPH_NAME)
        except InfraError:
            raise
        except Exception as exc:
            raise InfraError("graph backend failed to start") from exc
        self._lock = threading.RLock()
        self._schema_ready = False
        self._harden_persistence()
        self.ensure_schema()

    def _client(self):
        return getattr(self.db, "client", None)

    def _shared_clients(self) -> bool:
        """True when another process or Graph object is using this Redis."""
        client = self._client()
        if client is None:
            return False
        count_fn = getattr(client, "_connection_count", None)
        if callable(count_fn):
            try:
                return int(count_fn()) > 1
            except Exception:
                pass
        try:
            listed = client.client_list() or []
        except Exception:
            return False
        return len(listed) > 1

    def _harden_persistence(self) -> None:
        client = self._client()
        if client is None:
            return
        for key, value in (("appendonly", "yes"), ("save", "1 1")):
            try:
                client.config_set(key, value)
            except Exception:
                continue

    def persist(self) -> None:
        client = self._client()
        if client is None:
            return
        try:
            client.save()
        except Exception:
            return

    def close(self) -> None:
        self.persist()
        client = self._client()
        if client is None:
            return
        if self._shared_clients():
            try:
                pool = getattr(client, "connection_pool", None)
                if pool is not None:
                    pool.disconnect()
            except Exception:
                pass
            return
        shutdown = getattr(client, "shutdown", None)
        if shutdown is None:
            return
        try:
            shutdown(save=True)
        except Exception:
            return

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in _INDEXES:
            try:
                self._execute(statement, None, read_only=False, timeout=None)
            except Exception as exc:
                if "already indexed" not in str(exc).lower():
                    raise
        self._schema_ready = True

    def _names(self, header: list[Any]) -> list[str]:
        names: list[str] = []
        for column in header or []:
            if isinstance(column, (list, tuple)) and len(column) >= 2:
                names.append(str(column[1]))
            else:
                names.append(str(column))
        return names

    def _execute(
        self,
        statement: str,
        params: dict[str, Any] | None,
        *,
        read_only: bool,
        timeout: int | None,
    ):
        if read_only:
            return self.graph.ro_query(statement, params, timeout=timeout)
        if timeout is None:
            return self.graph.query(statement, params)
        return self.graph.query(statement, params, timeout=timeout)

    def run(
        self,
        name: str,
        statement: str,
        params: dict[str, Any] | None = None,
        *,
        read_only: bool = False,
        timeout: int | None = None,
    ) -> QueryRun:
        import time

        clean = {key: value for key, value in (params or {}).items() if value is not None}
        with self._lock:
            started = time.perf_counter()
            try:
                result = self._execute(
                    statement,
                    clean or None,
                    read_only=read_only,
                    timeout=timeout,
                )
            except InfraError:
                raise
            except Exception as exc:
                text = str(exc).lower()
                name = type(exc).__name__.lower()
                if "timed out" in text or "timeout" in text:
                    raise InfraError(f"graph query timed out: {exc}") from exc
                if "connection" in text or "connection" in name or "no such file" in text:
                    raise InfraError("graph backend unavailable") from exc
                raise
            elapsed = (time.perf_counter() - started) * 1000
        names = self._names(result.header)
        rows = [
            {names[index]: _plain(cell) for index, cell in enumerate(row)}
            for row in result.result_set
        ]
        return QueryRun(name, statement.strip(), clean, elapsed, rows)

    def merge_answer(self, answer_id: str, engine: str, text_hash: str, created_at: str) -> None:
        self.run(
            "merge_answer",
            """
            MERGE (a:Answer {id: $id})
            ON CREATE SET a.engine = $engine, a.text_hash = $text_hash, a.created_at = $created_at
            ON MATCH SET a.engine = $engine, a.text_hash = $text_hash, a.created_at = $created_at
            """,
            {"id": answer_id, "engine": engine, "text_hash": text_hash, "created_at": created_at},
        )

    def merge_source(
        self,
        url: str,
        title: str,
        site: str,
        fetched: bool,
        fetched_at: str | None = None,
    ) -> None:
        self.run(
            "merge_source",
            """
            MERGE (s:Source {url: $url})
            SET s.title = $title, s.site = $site, s.fetched = $fetched, s.fetched_at = $fetched_at
            """,
            {
                "url": url,
                "title": title or "",
                "site": site or "",
                "fetched": fetched,
                "fetched_at": fetched_at or "",
            },
        )

    def answer_inputs(self, answer_id: str) -> dict[str, Any]:
        run = self.run(
            "answer_inputs",
            """
            MATCH (a:Answer {id: $id})
            OPTIONAL MATCH (a)-[:CITES]->(s:Source)
            OPTIONAL MATCH (s)-[:RESTS_ON]->(w:Work)
            RETURN a.engine AS engine,
                   [u IN collect(DISTINCT s.url) WHERE u IS NOT NULL] AS urls,
                   [d IN collect(DISTINCT w.doi) WHERE d IS NOT NULL] AS dois
            """,
            {"id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )
        row = run.rows[0] if run.rows else {}
        return {
            "engine": row.get("engine") or "draft",
            "urls": row.get("urls") or [],
            "dois": row.get("dois") or [],
        }

    def cite(self, answer_id: str, url: str) -> None:
        self.run(
            "cite",
            """
            MATCH (a:Answer {id: $id}), (s:Source {url: $url})
            MERGE (a)-[:CITES]->(s)
            """,
            {"id": answer_id, "url": url},
        )

    def source_fetched(self, url: str) -> bool:
        run = self.run(
            "source_fetched",
            "MATCH (s:Source {url: $url}) RETURN s.fetched AS fetched",
            {"url": url},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )
        return bool(run.rows and run.rows[0].get("fetched"))

    def merge_work(self, doi: str, **fields: Any) -> None:
        assignments = []
        params: dict[str, Any] = {"doi": doi}
        for key, value in fields.items():
            if value is None:
                continue
            if key not in _WORK_FIELDS:
                raise ValueError(f"unsupported work field {key!r}")
            assignments.append(f"w.{key} = ${key}")
            params[key] = value
        set_clause = (" SET " + ", ".join(assignments)) if assignments else ""
        self.run("merge_work", f"MERGE (w:Work {{doi: $doi}}){set_clause}", params)

    def rest_on(self, source_doi: str, target_doi: str) -> None:
        if source_doi == target_doi:
            return
        self.run(
            "rest_on",
            """
            MATCH (a:Work {doi: $source}), (b:Work {doi: $target})
            MERGE (a)-[r:RESTS_ON]->(b)
            ON CREATE SET r.cost = $cost
            """,
            {"source": source_doi, "target": target_doi, "cost": UNJUDGED_COST},
        )

    def set_reliance(
        self,
        source_doi: str | None,
        source_url: str | None,
        target_doi: str,
        *,
        reliance: str,
        weight: float,
        sentence: str,
        evidence_from: str,
        evidence_url: str = "",
        evidence_fetched_at: str = "",
        evidence_sha256: str = "",
    ) -> None:
        """Store one judgment on a RESTS_ON edge. Later calls overwrite; callers skip judged edges."""
        params = {
            "target": target_doi,
            "reliance": reliance,
            "weight": float(weight),
            "cost": hop_cost(weight),
            "sentence": (sentence or "")[:800],
            "evidence_from": evidence_from or "",
            "evidence_url": evidence_url or "",
            "evidence_fetched_at": evidence_fetched_at or "",
            "evidence_sha256": evidence_sha256 or "",
        }
        from datetime import datetime, timezone

        params["judged_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        trail_set = (
            "r.evidence_url = $evidence_url, r.evidence_fetched_at = $evidence_fetched_at, "
            "r.evidence_sha256 = $evidence_sha256"
        )
        if source_doi:
            params["source"] = source_doi
            statement = f"""
            MATCH (a:Work {{doi: $source}})-[r:RESTS_ON]->(b:Work {{doi: $target}})
            SET r.reliance = $reliance, r.weight = $weight, r.cost = $cost, r.sentence = $sentence,
                r.evidence_from = $evidence_from, r.judged = true, r.judged_at = $judged_at,
                {trail_set}
            """
        else:
            params["url"] = source_url or ""
            statement = f"""
            MATCH (a:Source {{url: $url}})-[r:RESTS_ON]->(b:Work {{doi: $target}})
            SET r.reliance = $reliance, r.weight = $weight, r.cost = $cost, r.sentence = $sentence,
                r.evidence_from = $evidence_from, r.judged = true, r.judged_at = $judged_at,
                {trail_set}
            """
        self.run("set_reliance", statement, params)

    def source_rests_on(self, url: str, doi: str) -> None:
        self.merge_work(doi)
        self.run(
            "source_rests_on",
            """
            MATCH (s:Source {url: $url}), (w:Work {doi: $doi})
            MERGE (s)-[r:RESTS_ON]->(w)
            ON CREATE SET r.cost = $cost
            """,
            {"url": url, "doi": doi, "cost": UNJUDGED_COST},
        )

    def explored(self, answer_id: str, depth: int) -> list[dict[str, Any]]:
        """Every RESTS_ON chain the check could walk at this depth, for drawing the graph.

        Not used for the verdict; the verdict comes only from algo.SPpaths rows.
        """
        hops = max(1, min(int(depth), 3))
        run = self.run(
            "explored",
            f"""
            MATCH (a:Answer {{id: $answer_id}})-[:CITES]->(s:Source)
            OPTIONAL MATCH p = (s)-[:RESTS_ON*1..{hops}]->(w:Work)
            RETURN s.url AS source_url,
                   s.title AS source_title,
                   CASE WHEN p IS NULL THEN [] ELSE
                     [x IN tail(nodes(p)) | {{doi: x.doi, title: x.title, year: x.year, first_author: x.first_author}}]
                   END AS works,
                   CASE WHEN p IS NULL THEN [] ELSE [r IN relationships(p) | r.reliance] END AS reliances
            LIMIT 80
            """,
            {"answer_id": answer_id},
        )
        return [_plain(row) for row in run.rows]

    def merge_notice(
        self,
        notice_doi: str,
        work_doi: str,
        notice_type: str,
        label: str,
        source: str,
        date: str,
    ) -> None:
        notice_type, label = cochrane_withdrawal(work_doi, notice_type, label)
        self.merge_work(work_doi)
        self.run(
            "merge_notice",
            """
            MERGE (n:Notice {doi: $notice})
            SET n.type = $type, n.label = $label, n.source = $source, n.date = $date
            """,
            {
                "notice": notice_doi,
                "type": notice_type,
                "label": label,
                "source": source,
                "date": date,
            },
        )
        self.run(
            "flags",
            """
            MATCH (n:Notice {doi: $notice}), (w:Work {doi: $work})
            MERGE (n)-[:FLAGS]->(w)
            """,
            {"notice": notice_doi, "work": work_doi},
        )

    def work_row(self, doi: str) -> dict[str, Any] | None:
        run = self.run(
            "work_row",
            """
            MATCH (w:Work {doi: $doi})
            RETURN w.expanded AS expanded, w.notice_checked AS notice_checked,
                   w.notice_checked_at AS notice_checked_at,
                   w.title AS title, w.year AS year, w.openalex_id AS openalex_id,
                   w.is_retracted AS is_retracted, w.openalex_cited_by AS openalex_cited_by,
                   w.work_type AS work_type, w.first_author AS first_author,
                   w.pmcid AS pmcid
            """,
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )
        return run.rows[0] if run.rows else None

    def neighbor_dois(self, dois: list[str]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for doi in dois:
            run = self.run(
                "neighbors",
                """
                MATCH (:Work {doi: $doi})-[:RESTS_ON]->(r:Work)
                RETURN r.doi AS doi, r.work_type AS work_type, r.expanded AS expanded
                """,
                {"doi": doi},
                read_only=True,
                timeout=RO_QUERY_TIMEOUT_MS,
            )
            for row in run.rows:
                target = row.get("doi")
                if target and target not in seen:
                    seen.add(target)
                    found.append(target)
        return found

    def review_neighbors(self, dois: list[str], limit: int) -> list[str]:
        picked: list[str] = []
        for doi in self.neighbor_dois(dois):
            row = self.work_row(doi)
            if row and row.get("work_type") == "review" and not row.get("expanded"):
                picked.append(doi)
            if len(picked) >= limit:
                break
        return picked

    def seed_dois(self, answer_id: str) -> list[str]:
        run = self.run(
            "seed_dois",
            """
            MATCH (:Answer {id: $id})-[:CITES]->(:Source)-[:RESTS_ON]->(w:Work)
            RETURN DISTINCT w.doi AS doi
            """,
            {"id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )
        return [row["doi"] for row in run.rows if row.get("doi")]

    def paths(self, answer_id: str, depth: int | None = None) -> QueryRun:
        bound = clamp_depth(depth)
        return self.run(
            "paths_to_notice",
            C.paths_to_notice(bound),
            {"answer_id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def sp_paths(self, answer_id: str, depth: int | None = None) -> QueryRun:
        bound = clamp_depth(depth)
        return self.run(
            "sp_paths_to_notice",
            C.sp_paths_to_notice(bound),
            {"answer_id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def what_rests_on(self, doi: str, depth: int | None = None) -> QueryRun:
        bound = clamp_depth(depth)
        return self.run(
            "what_rests_on",
            C.what_rests_on(bound),
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def wcc_clusters(self) -> QueryRun:
        return self.run(
            "wcc_clusters",
            C.WCC_CLUSTERS,
            None,
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def upstream_works(self, doi: str) -> QueryRun:
        return self.run(
            "upstream_works",
            C.UPSTREAM_WORKS,
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def shared_hubs(self, answer_ids: list[str]) -> QueryRun:
        return self.run(
            "shared_hubs",
            C.SHARED_HUBS,
            {"answer_ids": answer_ids},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def first_hops(self, answer_id: str) -> QueryRun:
        return self.run(
            "first_hops",
            C.FIRST_HOPS,
            {"answer_id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def notices_for(self, doi: str) -> QueryRun:
        return self.run(
            "notices_for_work",
            C.NOTICES_FOR_WORK,
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def citers(self, doi: str) -> QueryRun:
        return self.run(
            "citers_in_graph",
            C.CITERS_IN_GRAPH,
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def sources_for(self, doi: str) -> QueryRun:
        return self.run(
            "sources_in_graph",
            C.SOURCES_IN_GRAPH,
            {"doi": doi},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def citation_edges(self, answer_id: str, depth: int | None = None) -> QueryRun:
        bound = clamp_depth(depth)
        return self.run(
            "citation_edges",
            C.citation_edges(bound),
            {"answer_id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def independent_citers(self, answer_id: str, depth: int | None = None) -> QueryRun:
        bound = clamp_depth(depth)
        return self.run(
            "independent_citers",
            C.independent_citers(bound),
            {"answer_id": answer_id},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def counts(self) -> QueryRun:
        return self.run(
            "graph_counts",
            C.GRAPH_COUNTS,
            None,
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )

    def latest_answer(self, engine: str) -> str | None:
        run = self.run(
            "latest_answer",
            """
            MATCH (a:Answer {engine: $engine})
            RETURN a.id AS id, a.created_at AS created_at
            ORDER BY a.created_at DESC
            LIMIT 1
            """,
            {"engine": engine},
            read_only=True,
            timeout=RO_QUERY_TIMEOUT_MS,
        )
        if not run.rows:
            return None
        return run.rows[0].get("id")

    def ro_cypher(self, statement: str, timeout_ms: int = RO_QUERY_TIMEOUT_MS) -> QueryRun:
        return self.run(
            "ro_cypher",
            statement,
            None,
            read_only=True,
            timeout=timeout_ms,
        )


_singleton: Graph | None = None
_singleton_lock = threading.Lock()


def get_graph(path: str | Path | None = None) -> Graph:
    global _singleton
    from mooltrace.config import DB_PATH

    target = Path(path) if path else DB_PATH
    with _singleton_lock:
        if _singleton is not None and _singleton.path != target:
            _singleton.close()
        if _singleton is None or _singleton.path != target:
            _singleton = Graph(target)
        return _singleton


def _shutdown_singleton() -> None:
    if _singleton is not None:
        _singleton.close()


atexit.register(_shutdown_singleton)
