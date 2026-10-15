"""OpenCypher the MCP tools and CLI actually execute.

Relationship bounds are literals: FalkorDB rejects parameters there.
Depth is substituted from a clamped integer (1..3). shortestPath is not
used for verdicts: a weak short path must not hide a counted longer path.
"""

from __future__ import annotations

from mooltrace.config import MAX_DEPTH, clamp_depth

# Forward trace: every path from a cited source to a flagged work, with
# per-hop evidence and a product of RESTS_ON weights. ORDER BY path_score
# DESC so a weak short hop cannot occupy LIMIT ahead of a counted longer
# path. shortestPath is not used.
PATHS_TO_NOTICE = """
MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
MATCH p = (s)-[:RESTS_ON*1..3]->(w)
MATCH (n:Notice)-[:FLAGS]->(w:Work)
WITH s, w, n, p, relationships(p) AS rels
WITH s, w, n, p, rels,
     reduce(score = 1.0, r IN rels | score * coalesce(r.weight, 0.0)) AS path_score
RETURN s.url AS source_url,
       s.title AS source_title,
       w.doi AS root_doi,
       w.title AS root_title,
       w.year AS root_year,
       n.doi AS notice_doi,
       n.type AS notice_type,
       n.label AS notice_label,
       n.date AS notice_date,
       n.source AS notice_source,
       length(p) AS hops,
       path_score,
       [x IN nodes(p) | {doi: x.doi, title: x.title, url: x.url, year: x.year}] AS steps,
       [r IN rels | {weight: r.weight, reliance: r.reliance, sentence: r.sentence, evidence_from: r.evidence_from, judged: r.judged}] AS hops_evidence
ORDER BY path_score DESC, hops ASC
LIMIT 80
""".strip()

# Reverse impact: only answers whose cited sources reach this flagged work.
# Unrelated drafts in the same graph are dropped. Counted answers use the
# same hop rule as the forward verdict (PATH_RULE / STRONG_RELIANCE):
# every hop has a stored sentence and weight >= 0.5, and the path is one
# hop or has an included/relies/uses_data_or_method hop. Mention-only
# multi-hop paths do not count. shortestPath is not used.
WHAT_RESTS_ON = """
MATCH (n:Notice)-[:FLAGS]->(w:Work)
WHERE n.doi = $doi OR w.doi = $doi
OPTIONAL MATCH p = (s:Source)-[:RESTS_ON*1..3]->(w)
OPTIONAL MATCH (a:Answer)-[:CITES]->(s)
WITH n, w, a, s, p, relationships(p) AS rels
WHERE p IS NOT NULL OR a IS NULL
WITH n, w, a, s,
     CASE WHEN p IS NULL THEN false ELSE ALL(r IN rels WHERE coalesce(r.weight, 0.0) >= 0.5 AND coalesce(r.sentence, '') <> '') AND (size(rels) = 1 OR ANY(r IN rels WHERE r.reliance IN ['included', 'relies', 'uses_data_or_method'])) END AS counted
RETURN n.doi AS notice_doi,
       n.type AS notice_type,
       n.label AS notice_label,
       n.date AS notice_date,
       n.source AS notice_source,
       w.doi AS root_doi,
       w.title AS root_title,
       w.year AS root_year,
       [id IN collect(DISTINCT a.id) WHERE id IS NOT NULL] AS answer_ids,
       [e IN collect(DISTINCT a.engine) WHERE e IS NOT NULL] AS engines,
       [u IN collect(DISTINCT s.url) WHERE u IS NOT NULL] AS source_urls,
       [id IN collect(DISTINCT CASE WHEN counted THEN a.id END) WHERE id IS NOT NULL] AS counted_answer_ids,
       size([id IN collect(DISTINCT a.id) WHERE id IS NOT NULL]) AS answer_count,
       size([u IN collect(DISTINCT s.url) WHERE u IS NOT NULL]) AS source_count
""".strip()

# PageRank over Work nodes connected by RESTS_ON. Used to rank which
# counted notice is shown first. Validated on FalkorDBLite 0.10.0.
PAGERANK_WORKS = """
CALL algo.pageRank('Work', 'RESTS_ON')
YIELD node, score
RETURN node.doi AS doi, score
ORDER BY score DESC
LIMIT 50
""".strip()

# Weakly connected Work clusters that contain a publisher notice.
# Validated on FalkorDBLite 0.10.0: CALL algo.WCC({nodeLabels, relationshipTypes}).
# Join answers at one Source-RESTS_ON hop: WCC already collected every Work
# in the component, so RESTS_ON*1..3 here is a cartesian timeout, not extra
# membership. A source that reaches a flagged work at hop 2 still RESTS_ON a
# Work inside the same component.
WCC_CLUSTERS = """
CALL algo.WCC({nodeLabels: ['Work'], relationshipTypes: ['RESTS_ON']})
YIELD node, componentId
WITH node, componentId
OPTIONAL MATCH (flag:Notice)-[:FLAGS]->(node)
WITH componentId,
     collect(DISTINCT node.doi) AS work_dois,
     [d IN collect(DISTINCT flag.doi) WHERE d IS NOT NULL] AS notice_dois,
     [t IN collect(DISTINCT flag.type) WHERE t IS NOT NULL] AS notice_types
WHERE size(notice_dois) > 0
MATCH (a:Answer)-[:CITES]->(:Source)-[:RESTS_ON]->(w:Work)
WHERE w.doi IN work_dois
RETURN componentId,
       work_dois,
       notice_dois,
       notice_types,
       collect(DISTINCT a.id) AS answer_ids,
       collect(DISTINCT a.engine) AS engines
""".strip()

UPSTREAM_WORKS = """
MATCH (n:Notice)-[:FLAGS]->(w:Work)
WHERE n.doi = $doi OR w.doi = $doi
MATCH (u:Work)-[:RESTS_ON*1..3]->(w)
RETURN DISTINCT u.doi AS doi, u.title AS title, u.year AS year
ORDER BY u.year DESC
LIMIT 40
""".strip()

SHARED_HUBS = """
MATCH (a:Answer)
WHERE a.id IN $answer_ids
MATCH (a)-[:CITES]->(:Source)-[:RESTS_ON*1..3]->(hub:Work)
MATCH (hub)-[:RESTS_ON*1..3]->(root:Work)
MATCH (n:Notice)-[:FLAGS]->(root)
WITH hub, root, n, collect(DISTINCT a.id) AS answers, collect(DISTINCT a.engine) AS engines
WHERE size(answers) >= 2
RETURN hub.doi AS hub_doi,
       hub.title AS hub_title,
       hub.year AS hub_year,
       root.doi AS root_doi,
       root.title AS root_title,
       n.doi AS notice_doi,
       n.type AS notice_type,
       answers,
       engines
ORDER BY hub.year DESC
LIMIT 25
""".strip()

FIRST_HOPS = """
MATCH (a:Answer {id: $answer_id})-[:CITES]->(:Source)-[:RESTS_ON]->(first:Work)
MATCH (first)-[:RESTS_ON*0..3]->(root:Work)
MATCH (:Notice)-[:FLAGS]->(root)
RETURN collect(DISTINCT first.doi) AS first_hops
""".strip()

NOTICES_FOR_WORK = """
MATCH (n:Notice)-[:FLAGS]->(w:Work {doi: $doi})
RETURN n.doi AS doi, n.type AS type, n.label AS label, n.date AS date, n.source AS source,
       w.title AS title, w.year AS year, w.is_retracted AS is_retracted,
       w.openalex_cited_by AS openalex_cited_by, w.openalex_id AS openalex_id
""".strip()

CITERS_IN_GRAPH = """
MATCH (c:Work)-[:RESTS_ON]->(w:Work {doi: $doi})
RETURN c.doi AS doi, c.title AS title, c.year AS year
LIMIT 15
""".strip()

SOURCES_IN_GRAPH = """
MATCH (s:Source)-[:RESTS_ON]->(w:Work {doi: $doi})
RETURN s.url AS url, s.title AS title, s.site AS site
LIMIT 15
""".strip()

GRAPH_COUNTS = """
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
""".strip()

# Every RESTS_ON hop on a path from a cited source to a flagged work.
CITATION_EDGES = """
MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
MATCH p = (s)-[:RESTS_ON*1..3]->(w)
MATCH (:Notice)-[:FLAGS]->(w)
UNWIND relationships(p) AS r
WITH DISTINCT startNode(r) AS citer, r, endNode(r) AS dest
WHERE dest.doi IS NOT NULL
RETURN citer.doi AS citer_doi,
       citer.url AS citer_url,
       citer.title AS citer_title,
       citer.pmcid AS citer_pmcid,
       dest.doi AS root_doi,
       dest.title AS root_title,
       dest.year AS root_year,
       dest.first_author AS root_author,
       r.judged AS judged,
       r.weight AS weight,
       r.reliance AS reliance,
       r.sentence AS sentence,
       r.evidence_from AS evidence_from
""".strip()

INDEPENDENT_CITERS = """
MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
MATCH (s)-[:RESTS_ON*0..2]->(citer)-[r:RESTS_ON]->(root)
MATCH (n:Notice)-[:FLAGS]->(root)
WHERE r.judged = true AND r.weight >= 0.5 AND r.sentence <> ''
RETURN DISTINCT coalesce(citer.doi, citer.url) AS citer,
       citer.doi AS citer_doi,
       citer.url AS citer_url,
       citer.title AS citer_title,
       root.doi AS root_doi,
       n.doi AS notice_doi,
       n.type AS notice_type,
       r.reliance AS reliance,
       r.weight AS weight,
       r.sentence AS sentence,
       r.evidence_from AS evidence_from
""".strip()


def _bound(statement: str, old: str, new: str) -> str:
    if old not in statement:
        raise ValueError(f"depth bound {old!r} missing from query")
    return statement.replace(old, new, 1)


def paths_to_notice(depth: int) -> str:
    d = clamp_depth(depth)
    return _bound(PATHS_TO_NOTICE, "*1..3", f"*1..{d}")


def what_rests_on(depth: int = MAX_DEPTH) -> str:
    d = clamp_depth(depth)
    return _bound(WHAT_RESTS_ON, "*1..3", f"*1..{d}")


def citation_edges(depth: int) -> str:
    d = clamp_depth(depth)
    return _bound(CITATION_EDGES, "*1..3", f"*1..{d}")


def independent_citers(depth: int) -> str:
    inner = max(0, clamp_depth(depth) - 1)
    return _bound(INDEPENDENT_CITERS, "*0..2", f"*0..{inner}")
