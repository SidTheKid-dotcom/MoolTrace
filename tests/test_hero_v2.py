"""Recorded Harvard vitamin-D BLOCK hero: Avenell 2014 pooled Ishida 2004."""

from __future__ import annotations

from pathlib import Path

from mooltrace.graph import Graph
from mooltrace.public_demo import _norm_urls, _source_url, load_recorded_presets
from mooltrace.trace import _answer_id, _text_hash, check_answer

HERO_ID = "nutrition-harvard-vitamin-d"
HERO_URL = "https://nutritionsource.hsph.harvard.edu/vitamin-d/"
AVENELL = "10.1002/14651858.cd000227.pub4"
ISHIDA = "10.1016/j.amjmed.2004.05.019"
ISHIDA_NOTICE = "10.1016/j.amjmed.2025.03.001"
OLIVE_ID = "nutrition-olive-oil"
ENGINE = "nutrition-coach"


def _hero() -> dict:
    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    assert HERO_ID in recorded, f"missing recorded preset {HERO_ID}"
    return recorded[HERO_ID]


def _seed_spec(graph: Graph, spec: dict, *, engine: str, text: str, urls: list[str]) -> None:
    urls = _norm_urls(urls)
    answer_id = _answer_id(engine, text, urls)
    created = str(spec.get("fetch_date") or "")
    for source in spec.get("sources") or []:
        created = str(source.get("fetched_at") or created)
        break
    graph.merge_answer(answer_id, engine, _text_hash(text), created)
    for source in spec.get("sources") or []:
        url = _source_url(source, answer_id)
        graph.merge_source(
            url,
            str(source.get("title") or ""),
            str(source.get("site") or ""),
            True,
            fetched_at=str(source.get("fetched_at") or created),
        )
        graph.cite(answer_id, url)
    for work in spec.get("works") or []:
        fields = {
            key: work[key]
            for key in (
                "title",
                "year",
                "first_author",
                "expanded",
                "notice_checked",
                "notice_checked_at",
            )
            if key in work
        }
        graph.merge_work(str(work["doi"]), **fields)
    for hop in spec.get("hops") or []:
        target = str(hop["to_doi"])
        source_doi = hop.get("from_doi")
        if source_doi:
            graph.rest_on(str(source_doi), target)
            graph.set_reliance(
                str(source_doi),
                None,
                target,
                reliance=str(hop["reliance"]),
                weight=float(hop["weight"]),
                sentence=str(hop.get("sentence") or ""),
                evidence_from=str(hop.get("evidence_from") or ""),
                evidence_url=str(hop.get("source_url") or ""),
                evidence_fetched_at=str(hop.get("fetched_at") or hop.get("recorded_at") or ""),
                evidence_sha256=str(hop.get("content_hash") or ""),
            )
            continue
        url = _source_url({"url": hop.get("from_url")}, answer_id)
        graph.source_rests_on(url, target)
        graph.set_reliance(
            None,
            url,
            target,
            reliance=str(hop["reliance"]),
            weight=float(hop["weight"]),
            sentence=str(hop.get("sentence") or ""),
            evidence_from=str(hop.get("evidence_from") or ""),
            evidence_url=str(hop.get("source_url") or hop.get("from_url") or url),
            evidence_fetched_at=str(hop.get("fetched_at") or hop.get("recorded_at") or ""),
            evidence_sha256=str(hop.get("content_hash") or ""),
        )
    for notice in spec.get("notices") or []:
        graph.merge_notice(
            str(notice["doi"]),
            str(notice["work_doi"]),
            str(notice["type"]),
            str(notice["label"]),
            str(notice.get("source") or "publisher"),
            str(notice.get("date") or ""),
        )
    graph.persist()


def test_olive_oil_preset_is_still_recorded():
    recorded = {row["id"]: row for row in load_recorded_presets()["presets"]}
    assert OLIVE_ID in recorded
    hops = recorded[OLIVE_ID]["hops"]
    assert [hop["reliance"] for hop in hops] == ["mention", "mention"]
    assert hops[1]["to_doi"] == "10.1056/nejmoa1200303"


def test_harvard_vitamin_d_recorded_preset_has_uses_data_or_method():
    spec = _hero()
    assert spec["decision"] == "block"
    assert spec["fetch_date"] == "2026-10-17"
    assert str(spec.get("label") or "").startswith("recorded live run on 2026-10-17")
    sources = spec.get("sources") or []
    assert sources
    assert sources[0]["url"] == HERO_URL
    hops = spec["hops"]
    assert len(hops) == 2
    assert hops[0]["from_url"] == HERO_URL
    assert hops[0]["to_doi"] == AVENELL
    assert hops[0]["reliance"] == "mention"
    assert hops[0]["weight"] == 0.55
    assert hops[1]["from_doi"] == AVENELL
    assert hops[1]["to_doi"] == ISHIDA
    assert hops[1]["reliance"] == "uses_data_or_method"
    assert hops[1]["weight"] == 0.85
    assert "included trial" in hops[1]["sentence"]
    assert hops[1]["evidence_from"] == "pmc_html"
    for hop in hops:
        digest = str(hop.get("content_hash") or "")
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")
        assert hop.get("fetched_at")
        assert hop.get("recorded_at")
    notices = spec["notices"]
    assert notices
    assert notices[0]["work_doi"] == ISHIDA
    assert notices[0]["doi"] == ISHIDA_NOTICE
    assert notices[0]["type"] == "retraction"
    assert notices[0]["date"] == "2025-05"
    works = {row["doi"]: row for row in spec["works"]}
    assert works[AVENELL]["first_author"] == "Avenell"
    assert works[AVENELL]["year"] == 2014
    assert works[ISHIDA]["first_author"] == "Ishida"
    assert works[ISHIDA]["year"] == 2004
    by_depth = spec["by_depth"]
    assert by_depth["1"]["decision"] == "pass"
    assert int(by_depth["1"]["exit_code"]) == 0
    assert int(by_depth["1"]["notice_paths"] or 0) == 0
    assert by_depth["1"]["live_incomplete"] is False
    assert by_depth["2"]["decision"] == "block"
    assert int(by_depth["2"]["exit_code"]) == 1
    assert by_depth["2"]["notice_type"] == "retraction"
    assert by_depth["2"]["notice_doi"] == ISHIDA_NOTICE
    assert by_depth["3"]["decision"] == "block"
    assert int(by_depth["3"]["exit_code"]) == 1
    assert by_depth["3"]["notice_doi"] == ISHIDA_NOTICE


def test_harvard_seeded_replay_blocks_at_depth_2_and_3(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_PUBLIC_DEMO", "1")
    monkeypatch.delenv("MOOLTRACE_PUBLIC_LIVE", raising=False)
    spec = _hero()
    graph = Graph(tmp_path / "hero.db")
    _seed_spec(graph, spec, engine=ENGINE, text="", urls=[HERO_URL])
    shallow = check_answer("", [HERO_URL], ENGINE, 1, graph=graph)
    assert shallow["api_calls"] == 0
    assert shallow["decision"] == "pass"
    assert shallow["exit_code"] == 0
    assert not [
        reason
        for reason in shallow.get("reasons") or []
        if reason.get("notice_type")
    ]
    for depth in (2, 3):
        payload = check_answer("", [HERO_URL], ENGINE, depth, graph=graph)
        assert payload["api_calls"] == 0
        assert payload["decision"] == "block"
        assert payload["exit_code"] == 1
        hops = {
            hop.get("reliance")
            for reason in payload.get("reasons") or []
            for hop in reason.get("hops_evidence") or []
        }
        assert "uses_data_or_method" in hops
        assert "mention" in hops
        assert any(
            reason.get("root_doi") == ISHIDA
            and reason.get("notice_type") == "retraction"
            and reason.get("notice_doi") == ISHIDA_NOTICE
            and reason.get("notice_date") == "2025-05"
            and reason.get("root_author") == "Ishida"
            and reason.get("root_year") == 2004
            for reason in payload.get("reasons") or []
        )
        strength = (payload.get("algorithm") or {}).get("strength")
        assert strength == 0.4675
    graph.close()
