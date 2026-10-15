import json
from pathlib import Path

from mooltrace.config import EVERYDAY_HEALTH_URL
from mooltrace.cypher import paths_to_notice
from mooltrace.gate import CLEAN


ROOT = Path(__file__).resolve().parents[1]


def test_readme_quotes_the_executed_path_query():
    text = (ROOT / "README.md").read_text()
    executed = paths_to_notice(2)
    assert "MATCH (n:Notice)-[:FLAGS]->(w:Work)" in text
    assert "MATCH p = (s)-[:RESTS_ON*1..2]->(w)" in text
    assert "(w)<-[:FLAGS]" not in text
    assert "shortestPath" in text
    for line in executed.splitlines():
        stripped = line.strip()
        if stripped:
            assert stripped in text, stripped


def test_ci_fixture_file_has_no_known_block_case():
    text = (ROOT / "examples" / "answers.jsonl").read_text()
    workflow = (ROOT / ".github" / "workflows" / "mooltrace-fixtures.yml").read_text()
    assert "examples/answers.jsonl" in workflow
    assert "reusable" in workflow.lower() or "Sample workflow" in workflow
    assert "push:" in workflow
    assert "main" in workflow
    assert "contents: read" in workflow
    assert "timeout-minutes:" in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "schedule:" in workflow
    assert "fresh fixture recheck" in workflow
    assert "10.1016/S0140-6736(20)31180-6" not in text
    assert "lancet" not in text.lower()
    first = json.loads(text.splitlines()[0])
    assert first["text"] == ""
    assert first["urls"] == [EVERYDAY_HEALTH_URL]


def test_readme_names_no_sources_and_fixture_recheck():
    text = (ROOT / "README.md").read_text()
    assert "no_sources" in text
    assert "fresh fixture recheck" in text
    assert "not persistent monitoring" in text


def test_clean_set_excludes_known_flagged_ancestors():
    assert "10.5114/amsad/184245" not in CLEAN
    assert "10.1093/jn/136.4.977" not in CLEAN
    assert "10.2174/1389557523666230725113446" not in CLEAN
    assert "10.1016/j.jsps.2015.03.013" in CLEAN
