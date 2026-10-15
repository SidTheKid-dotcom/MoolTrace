from pathlib import Path

from mooltrace.clients import MoolTraceError
from mooltrace.graph import Graph
from mooltrace.trace import ro_cypher


def test_path_and_reverse_roundtrip(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "nutrition-coach", "hash", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/draft", "Draft", "example.com", True)
        graph.cite("a1", "https://example.com/draft")
        graph.merge_work("10.1370/afm.1517", title="Allen", year=2013, expanded=True, notice_checked=True)
        graph.merge_work(
            "10.2337/diacare.26.12.3215",
            title="Khan",
            year=2003,
            expanded=True,
            notice_checked=True,
            is_retracted=False,
        )
        graph.source_rests_on("https://example.com/draft", "10.1370/afm.1517")
        graph.rest_on("10.1370/afm.1517", "10.2337/diacare.26.12.3215")
        graph.merge_notice(
            "10.2337/dc25-ec09",
            "10.2337/diacare.26.12.3215",
            "expression_of_concern",
            "Expression of concern",
            "publisher",
            "2025-08-20",
        )
        paths = graph.paths("a1")
        assert paths.rows[0]["root_doi"] == "10.2337/diacare.26.12.3215"
        assert paths.rows[0]["notice_type"] == "expression_of_concern"
        assert paths.rows[0]["hops"] == 2
        assert "shortestPath" not in paths.cypher
        assert "*1.." in paths.cypher
        assert "MATCH (n:Notice)-[:FLAGS]->(w:Work)" in paths.cypher
        assert "(w)<-[:FLAGS]" not in paths.cypher
        reverse = graph.what_rests_on("10.2337/dc25-ec09")
        assert reverse.rows[0]["answer_count"] == 1
        hubs = graph.shared_hubs(["a1", "missing"])
        assert hubs.rows == []
        graph.set_reliance(
            "10.1370/afm.1517",
            None,
            "10.2337/diacare.26.12.3215",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence="analyzing the results Khan and colleagues 6",
            evidence_from="pmc_full_text",
        )
        again = graph.paths("a1")
        hops = again.rows[0].get("hops_evidence") or []
        last = hops[-1] if hops else again.rows[0]
        assert last["weight"] == 0.85
        assert last["sentence"] == "analyzing the results Khan and colleagues 6"
        assert last["judged"] is True
        edges = graph.citation_edges("a1")
        judged = [
            row
            for row in edges.rows
            if row.get("root_doi") == "10.2337/diacare.26.12.3215"
        ]
        assert judged and judged[0]["judged"] is True
        stored = judged[0]["sentence"]
        graph.set_reliance(
            "10.1370/afm.1517",
            None,
            "10.2337/diacare.26.12.3215",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence=stored,
            evidence_from="pmc_full_text",
        )
        repeat = graph.citation_edges("a1")
        again_judged = [
            row
            for row in repeat.rows
            if row.get("root_doi") == "10.2337/diacare.26.12.3215"
        ]
        assert again_judged[0]["sentence"] == stored
        independent = graph.independent_citers("a1")
        assert any(row.get("citer") == "10.1370/afm.1517" for row in independent.rows)
    finally:
        graph.close()


def test_ro_cypher_rejects_writes(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        try:
            ro_cypher("CREATE (:Work {doi: '10.1/nope'})", graph=graph)
        except MoolTraceError as exc:
            assert "read-only" in str(exc)
        else:
            raise AssertionError("write was accepted")
        allowed = ro_cypher(
            "MATCH (w:Work) WHERE w.title CONTAINS 'set' RETURN w.doi",
            graph=graph,
        )
        assert "rows" in allowed
        limited = ro_cypher(
            "MATCH (w:Work) RETURN w.doi LIMIT 2",
            graph=graph,
        )
        assert len(limited["rows"]) <= 2
        literal_limit = ro_cypher(
            "MATCH (w:Work) WHERE w.title CONTAINS 'limit' RETURN w.doi",
            graph=graph,
        )
        assert "LIMIT" in literal_limit["cypher"].upper()
    finally:
        graph.close()


def test_wcc_clusters_flagged_component(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "nutrition-coach", "hash", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/draft", "Draft", "example.com", True)
        graph.cite("a1", "https://example.com/draft")
        graph.merge_work("10.1370/afm.1517", title="Allen")
        graph.merge_work("10.2337/diacare.26.12.3215", title="Khan")
        graph.source_rests_on("https://example.com/draft", "10.1370/afm.1517")
        graph.rest_on("10.1370/afm.1517", "10.2337/diacare.26.12.3215")
        graph.merge_notice(
            "10.2337/dc25-ec09",
            "10.2337/diacare.26.12.3215",
            "expression_of_concern",
            "Expression of concern",
            "publisher",
            "2025-08-20",
        )
        graph.merge_answer("a2", "other", "hash2", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/other", "Other", "example.com", True)
        graph.cite("a2", "https://example.com/other")
        graph.merge_work("10.2222/isolated", title="Isolated")
        graph.source_rests_on("https://example.com/other", "10.2222/isolated")
        graph.merge_notice(
            "10.2222/n",
            "10.2222/isolated",
            "retraction",
            "Retracted",
            "publisher",
            "2024-01-01",
        )
        procs = graph.run(
            "procedures",
            "CALL dbms.procedures() YIELD name RETURN name",
            read_only=True,
        )
        assert any(row.get("name") == "algo.WCC" for row in procs.rows)
        raw = graph.run(
            "wcc_raw",
            """
            CALL algo.WCC({nodeLabels: ['Work'], relationshipTypes: ['RESTS_ON']})
            YIELD node, componentId
            RETURN node.doi AS doi, componentId
            """,
            read_only=True,
        )
        by_doi = {row["doi"]: row["componentId"] for row in raw.rows}
        assert by_doi["10.2337/diacare.26.12.3215"] != by_doi["10.2222/isolated"]
        clusters = graph.wcc_clusters()
        assert "algo.WCC" in clusters.cypher
        assert clusters.rows
        dois = set()
        answers = set()
        components = {}
        for row in clusters.rows:
            dois.update(row.get("work_dois") or [])
            answers.update(row.get("answer_ids") or [])
            components[row["componentId"]] = set(row.get("answer_ids") or [])
        assert "10.2337/diacare.26.12.3215" in dois
        assert "a1" in answers and "a2" in answers
        assert len(components) == 2
        naive = set().union(*components.values())
        assert naive == {"a1", "a2"}
        assert not any(components[left] == naive for left in components)
    finally:
        graph.close()


def test_weak_direct_path_does_not_hide_counted_longer_path(tmp_path: Path):
    from mooltrace.decision import decide
    from mooltrace.trace import _public_path

    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "nutrition-coach", "hash", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/page", "Page", "example.com", True)
        graph.cite("a1", "https://example.com/page")
        graph.merge_work("10.1370/afm.1517", title="Allen", year=2013, expanded=True, notice_checked=True)
        graph.merge_work(
            "10.2337/diacare.26.12.3215",
            title="Khan",
            year=2003,
            expanded=True,
            notice_checked=True,
        )
        graph.source_rests_on("https://example.com/page", "10.2337/diacare.26.12.3215")
        graph.source_rests_on("https://example.com/page", "10.1370/afm.1517")
        graph.rest_on("10.1370/afm.1517", "10.2337/diacare.26.12.3215")
        graph.merge_notice(
            "10.2337/dc25-ec09",
            "10.2337/diacare.26.12.3215",
            "expression_of_concern",
            "Expression of concern",
            "publisher",
            "2025-08-20",
        )
        graph.set_reliance(
            None,
            "https://example.com/page",
            "10.2337/diacare.26.12.3215",
            reliance="background",
            weight=0.2,
            sentence="Khan A, Safdar M. Diabetes Care. 2003;26(12):3215.",
            evidence_from="page_list",
        )
        graph.set_reliance(
            None,
            "https://example.com/page",
            "10.1370/afm.1517",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence="citing Allen 2013 as a review of cinnamon trials",
            evidence_from="page",
        )
        graph.set_reliance(
            "10.1370/afm.1517",
            None,
            "10.2337/diacare.26.12.3215",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence="analyzing the results Khan and colleagues 6 as 3 separate comparisons",
            evidence_from="pmc_html",
        )
        run = graph.paths("a1", depth=2)
        assert "shortestPath" not in run.cypher
        hops = {int(row["hops"]) for row in run.rows}
        assert 1 in hops and 2 in hops
        assert run.rows[0]["path_score"] >= run.rows[-1]["path_score"]
        paths = [_public_path(row) for row in run.rows]
        verdict = decide(paths, incomplete=False, depth=2)
        assert verdict["decision"] == "warn"
        assert verdict["exit_code"] == 2
        # Old shortestPath (WITH/RETURN form FalkorDB allows) keeps only the
        # 1-hop background edge. That policy would pass; all-paths must not.
        old = graph.run(
            "shortest_path_old",
            """
            MATCH (a:Answer {id: $answer_id})-[:CITES]->(s:Source)
            MATCH (n:Notice)-[:FLAGS]->(w:Work)
            WITH s, w, n, shortestPath((s)-[:RESTS_ON*1..2]->(w)) AS p
            WHERE p IS NOT NULL
            RETURN length(p) AS hops,
                   n.type AS notice_type,
                   w.doi AS root_doi,
                   [r IN relationships(p) | {weight: r.weight, reliance: r.reliance, sentence: r.sentence, evidence_from: r.evidence_from, judged: r.judged}] AS hops_evidence
            """,
            {"answer_id": "a1"},
            read_only=True,
        )
        assert {int(row["hops"]) for row in old.rows} == {1}
        old_verdict = decide(
            [
                {
                    "hops": row["hops"],
                    "hops_evidence": row["hops_evidence"],
                    "root": {"doi": row["root_doi"]},
                    "notice": {"type": row["notice_type"]},
                    "steps": [],
                }
                for row in old.rows
            ],
            incomplete=False,
            depth=2,
        )
        assert old_verdict["decision"] == "pass"
        shallow = graph.paths("a1", depth=1)
        assert {int(row["hops"]) for row in shallow.rows} == {1}
    finally:
        graph.close()


def test_cycle_and_duplicate_notices_stay_bounded(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "cycle", "hash", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/cycle", "Cycle", "example.com", True)
        graph.cite("a1", "https://example.com/cycle")
        graph.merge_work("10.1234/a", title="A")
        graph.merge_work("10.1234/b", title="B")
        graph.source_rests_on("https://example.com/cycle", "10.1234/a")
        graph.rest_on("10.1234/a", "10.1234/b")
        graph.rest_on("10.1234/b", "10.1234/a")
        graph.merge_notice("10.1234/n1", "10.1234/a", "retraction", "Retracted", "publisher", "2020-01-01")
        graph.merge_notice("10.1234/n2", "10.1234/a", "expression_of_concern", "EoC", "publisher", "2019-01-01")
        run = graph.paths("a1", depth=3)
        assert run.rows
        notices = {row["notice_doi"] for row in run.rows}
        assert "10.1234/n1" in notices and "10.1234/n2" in notices
        assert len(run.rows) <= 80
    finally:
        graph.close()


def test_merge_work_rejects_unknown_fields(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        try:
            graph.merge_work("10.1234/x", drop_graph="true")
        except ValueError:
            return
        raise AssertionError("unknown work field was accepted")
    finally:
        graph.close()


def test_depth_three_is_the_cap_and_returns_hop_evidence(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        graph.merge_answer("a1", "deep", "hash", "2026-10-15T00:00:00+00:00")
        graph.merge_source("https://example.com/deep", "Deep", "example.com", True)
        graph.cite("a1", "https://example.com/deep")
        graph.merge_work("10.1234/w1", title="W1")
        graph.merge_work("10.1234/w2", title="W2")
        graph.merge_work("10.1234/w3", title="W3")
        graph.source_rests_on("https://example.com/deep", "10.1234/w1")
        graph.rest_on("10.1234/w1", "10.1234/w2")
        graph.rest_on("10.1234/w2", "10.1234/w3")
        graph.merge_notice(
            "10.1234/n",
            "10.1234/w3",
            "expression_of_concern",
            "EoC",
            "publisher",
            "2025-01-01",
        )
        graph.set_reliance(
            None,
            "https://example.com/deep",
            "10.1234/w1",
            reliance="mention",
            weight=0.55,
            sentence="This draft cites W1 as the review that introduced the later trial.",
            evidence_from="page",
        )
        graph.set_reliance(
            "10.1234/w1",
            None,
            "10.1234/w2",
            reliance="mention",
            weight=0.55,
            sentence="W1 discusses W2 as the next hop in the same citation chain.",
            evidence_from="page",
        )
        graph.set_reliance(
            "10.1234/w2",
            None,
            "10.1234/w3",
            reliance="mention",
            weight=0.55,
            sentence="W2 cites W3 as the flagged study under publisher review.",
            evidence_from="page",
        )
        assert graph.paths("a1", depth=1).rows == []
        assert graph.paths("a1", depth=2).rows == []
        deep = graph.paths("a1", depth=3)
        assert "*1..3" in deep.cypher
        assert {int(row["hops"]) for row in deep.rows} == {3}
        hops = deep.rows[0].get("hops_evidence") or []
        assert len(hops) == 3
        assert all((edge.get("sentence") or "").strip() for edge in hops)
        capped = graph.paths("a1", depth=9)
        assert "*1..3" in capped.cypher
    finally:
        graph.close()


def test_cli_check_answer_warns_when_a_weak_direct_path_hides_a_counted_route(tmp_path: Path):
    import json
    import os
    import subprocess
    import sys
    from datetime import datetime, timezone

    graph = Graph(tmp_path / "mooltrace.db")
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        graph.merge_source("https://example.com/page", "Page", "example.com", True, stamp)
        graph.merge_work(
            "10.1370/afm.1517",
            title="Allen",
            year=2013,
            expanded=True,
            notice_checked=True,
            notice_checked_at=stamp,
        )
        graph.merge_work(
            "10.2337/diacare.26.12.3215",
            title="Khan",
            year=2003,
            expanded=True,
            notice_checked=True,
            notice_checked_at=stamp,
        )
        graph.source_rests_on("https://example.com/page", "10.2337/diacare.26.12.3215")
        graph.source_rests_on("https://example.com/page", "10.1370/afm.1517")
        graph.rest_on("10.1370/afm.1517", "10.2337/diacare.26.12.3215")
        graph.merge_notice(
            "10.2337/dc25-ec09",
            "10.2337/diacare.26.12.3215",
            "expression_of_concern",
            "Expression of concern",
            "publisher",
            "2025-08-20",
        )
        graph.set_reliance(
            None,
            "https://example.com/page",
            "10.2337/diacare.26.12.3215",
            reliance="background",
            weight=0.2,
            sentence="Khan A, Safdar M. Diabetes Care. 2003;26(12):3215.",
            evidence_from="page_list",
        )
        graph.set_reliance(
            None,
            "https://example.com/page",
            "10.1370/afm.1517",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence="citing Allen 2013 as a review of cinnamon trials",
            evidence_from="page",
        )
        graph.set_reliance(
            "10.1370/afm.1517",
            None,
            "10.2337/diacare.26.12.3215",
            reliance="uses_data_or_method",
            weight=0.85,
            sentence="analyzing the results Khan and colleagues 6 as 3 separate comparisons",
            evidence_from="pmc_html",
        )
        graph.persist()
    finally:
        graph.close()
    env = os.environ.copy()
    env["MOOLTRACE_DB"] = str(tmp_path / "mooltrace.db")
    env["MOOLTRACE_MAILTO"] = "mooltrace-test@example.com"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mooltrace",
            "check-answer",
            "--url",
            "https://example.com/page",
            "--engine",
            "nutrition-coach",
            "--depth",
            "2",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 2
    assert payload["decision"] == "warn"
    assert payload["exit_code"] == 2
    assert payload["api_calls"] == 0
    assert "shortestPath" not in (payload.get("cypher") or "")
    assert any(reason.get("code") == "expression_of_concern" for reason in payload.get("reasons") or [])
    assert payload.get("discounted")


def test_depth_cap_is_honored(tmp_path: Path):
    graph = Graph(tmp_path / "mooltrace.db")
    try:
        run = graph.paths("missing", depth=9)
        assert "*1..3" in run.cypher
        run = graph.paths("missing", depth=1)
        assert "*1..1" in run.cypher
    finally:
        graph.close()
