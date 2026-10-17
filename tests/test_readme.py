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
    assert text.find("MATCH p = (s)-[:RESTS_ON*1..2]->(w)") < text.find(
        "MATCH (n:Notice)-[:FLAGS]->(w:Work)"
    )
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


TRACK = "Agents That Act on Connected Data"
DEMO = "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/"
TAGLINE = (
    "MoolTrace catches when your health AI's sources quietly rest on a flagged "
    "or retracted study, even three links deep."
)
WHAT_IT_DOES = (
    "Paste a health-AI answer or the URL it cites; MoolTrace walks page → review "
    "→ trial in FalkorDB and returns pass, warn, or block when a counted path "
    "rests on a publisher notice."
)
MCP_ONE = ".venv/bin/python -m mooltrace mcp"
HERO_STEM = "assets/demo-harvard-depth-toggle"
HERO_GIF = ROOT / "assets" / "demo-harvard-depth-toggle.gif"
HERO_PNG = ROOT / "assets" / "demo-harvard-vitamin-d-block.png"
HERO_LIVE = (
    "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/"
    "?preset=harvard-vitamin-d"
)
BASELINE_JSON = ROOT / "results" / "baseline_2026-10-16.json"


def _gif_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:6] in {b"GIF87a", b"GIF89a"}, path
    return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _first(text: str, needle: str) -> int:
    index = text.find(needle)
    assert index >= 0, needle
    return index


def test_ai_use_disclosure_is_solo_and_names_tools():
    text = (ROOT / "README.md").read_text()
    assert "## AI-use disclosure" in text
    section = text.split("## AI-use disclosure", 1)[1].split("\n## ", 1)[0]
    lowered = section.lower()
    assert "teammate" not in lowered
    assert "Cursor agents" in section
    assert "Grok 4.6" in section
    assert "Claude" in section
    assert "Anthropic" in section
    assert "Azure OpenAI" in section
    assert "gpt-5.4-mini" in section
    assert "Siddhant Vishnu" in section
    assert "algo.SPpaths" in section
    assert "OpenAlex" in section
    assert "Expression of Concern" in section or "EoC" in section
    assert "AZURE_OPENAI" not in section
    assert "Azure AI Foundry" not in section


def test_readme_names_no_sources_and_fixture_recheck():
    text = (ROOT / "README.md").read_text()
    assert "no_sources" in text
    assert "fresh fixture recheck" in text
    assert "not persistent monitoring" in text
    assert text.splitlines()[2].startswith("MoolTrace catches when your health AI's sources quietly rest")
    assert DEMO in "\n".join(text.splitlines()[:8])
    assert "rewrite_answer" in text
    assert "algo.SPpaths" in text
    assert "Azure AI Foundry" not in text
    assert "LLM rewrit" not in text.lower()
    assert "`cost` is `-ln(weight)`" in text


def test_readme_top_follows_p3_13():
    text = (ROOT / "README.md").read_text()
    order = [
        TAGLINE,
        WHAT_IT_DOES,
        DEMO,
        HERO_STEM,
        MCP_ONE,
        "python3 -m venv .venv",
        "symptom checkers, nutrition coaches, patient chatbots",
        "| pass | 0 |",
        "| block | 1 |",
        "| error | 3 |",
        "```mermaid",
        "Answer -->|CITES| Source",
        "CALL algo.SPpaths",
        "mooltrace batch examples/answers.jsonl --fail-on block",
        "mooltrace.mcp_server",
        "0.8974",
        "## Limits",
        "## Prior art",
    ]
    assert TRACK in text
    last = -1
    for marker in order:
        index = _first(text, marker)
        assert index > last, marker
        last = index
    assert "| warn" in text
    assert "exit 2" in text or "| 2 |" in text
    first_bash = text.split("```bash", 1)[1].split("```", 1)[0].strip()
    run_lines = [line for line in first_bash.splitlines() if line.strip()]
    assert len(run_lines) == 3, run_lines
    assert "mention-only multi-hop paths do not count" not in text


def test_readme_top_is_ten_second_fold():
    text = (ROOT / "README.md").read_text()
    fold = text.split("\n## ", 1)[0]
    for needle in (TAGLINE, WHAT_IT_DOES, DEMO, HERO_STEM, MCP_ONE):
        assert needle in fold, needle
    assert TAGLINE not in WHAT_IT_DOES
    assert fold.index(TAGLINE) < fold.index(WHAT_IT_DOES) < fold.index(DEMO)
    assert fold.index(DEMO) < fold.index(HERO_STEM) < fold.index(MCP_ONE)
    assert "python3 -m venv" not in fold
    assert "```mermaid" not in fold
    assert "Who it is for" not in fold
    assert "depth 1" in fold.lower()
    assert "block" in fold.lower()
    heroes = list((ROOT / "assets").glob("demo-harvard-depth-toggle.*"))
    assert heroes, "hero image or GIF missing from assets/"
    assert all(path.suffix.lower() in {".gif", ".png", ".webp"} for path in heroes)
    caption = fold.split(HERO_STEM, 1)[1]
    assert "signed-out" in caption.lower() or "signed out" in caption.lower()
    assert "synthetic" not in fold.lower()


def test_hero_assets_are_live_signed_out_captures_not_localhost():
    text = (ROOT / "README.md").read_text()
    fold = text.split("\n## ", 1)[0]
    caption = fold.split(HERO_STEM, 1)[1]
    assert HERO_LIVE in caption
    assert "127.0.0.1:4318" not in caption
    assert "why the graph decided" in caption.lower()
    assert HERO_GIF.is_file()
    assert HERO_PNG.is_file()
    assert _gif_size(HERO_GIF) == (1280, 800)
    assert _png_size(HERO_PNG) == (1280, 800)
    claims = (ROOT / "CLAIMS.md").read_text()
    assert "assets/demo-harvard-depth-toggle.gif" in claims
    assert "assets/demo-harvard-vitamin-d-block.png" in claims
    assert HERO_LIVE in claims
    assert "127.0.0.1:4318" not in claims.split("assets/demo-harvard-depth-toggle.gif", 1)[1].split("\n", 1)[0]


def test_docs_name_the_connected_data_track():
    for name in (
        "README.md",
        "SUBMISSION.md",
        "JUDGES.md",
        "CLAIMS.md",
        "VIDEO_SCRIPT.md",
        "SHIP_CHECKLIST.md",
    ):
        body = (ROOT / name).read_text()
        assert TRACK in body, name
    submission = (ROOT / "SUBMISSION.md").read_text()
    track_line = next(line for line in submission.splitlines() if line.startswith("**Track:**"))
    assert TRACK in track_line
    assert "01 — Context for AI Agents" not in submission


def test_readme_baseline_matches_results_file():
    text = (ROOT / "README.md").read_text()
    payload = json.loads(BASELINE_JSON.read_text())
    base = payload["baseline"]["metrics"]
    product = payload["mooltrace"]["metrics"]
    hops = payload["only_multihop_ids"]
    for value in (
        str(base["precision"]),
        str(base["recall"]),
        str(product["precision"]),
        str(product["recall"]),
        f"{base['exact_match']}/{base['n']}",
        f"{product['exact_match']}/{product['n']}",
        str(len(hops)),
        "results/baseline_2026-10-16.json",
    ):
        assert value in text, value
    assert ".venv/bin/python -m mooltrace baseline --out results/baseline_2026-10-16.json" in text


def test_readme_prior_art_links_verified_repos():
    text = (ROOT / "README.md").read_text()
    prior = text.split("## Prior art", 1)[1]
    assert "https://github.com/aryangorde6/shaky-ground" in prior
    assert "shaky/retractionwatch.py" in prior
    assert "RetractionNature" in prior
    assert "https://github.com/ibnweb3/bedrock" in prior
    assert "https://github.com/musharna/ghostcite" in prior
    assert "scite.ai" in prior
    assert "expression of concern" in prior.lower() or "Expression of Concern" in prior


def test_readme_demo_is_compose_and_honest():
    text = (ROOT / "README.md").read_text()
    demo = text.split("## Demo", 1)[1].split("## ", 1)[0]
    assert "docker compose up --build" in demo
    assert "127.0.0.1:4318" in demo
    assert "127.0.0.1:4317" in demo
    assert "Healthline cinnamon" in demo
    assert "Healthline olive oil" in demo
    assert "Not in the graph" in demo
    assert "Five presets" in demo
    assert "counted 2-hop" in demo
    assert "path strength 0.30" in demo
    assert "algo.SPpaths" in demo
    assert "Rewrite and recheck" in demo
    assert "Expression of Concern is not a retraction" in demo
    assert "does not say olive oil, cinnamon, or the Mediterranean diet works or does not" in demo
    assert "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/" in demo
    assert "railway.app" not in demo.lower()


def test_docs_do_not_claim_lightsail_pin_is_stale_api13():
    pin = json.loads((ROOT / "deploy" / "lightsail-deployment.json").read_text())
    api = pin["containers"]["api"]["image"]
    web = pin["containers"]["web"]["image"]
    assert api.startswith(":mooltrace.api.")
    assert web.startswith(":mooltrace.web.")
    for name in ("README.md", "CLAIMS.md"):
        text = (ROOT / name).read_text()
        assert "Lightsail rebuild pending" not in text, name
        assert ":mooltrace.api.13" not in text, name
        assert ":mooltrace.web.14" not in text, name
        assert api in text, name
        assert web in text, name


def test_healthline_warn_screenshot_is_live_not_synthetic():
    text = (ROOT / "README.md").read_text()
    assert "](assets/healthline-warn.png)" in text
    caption = text.split("](assets/healthline-warn.png)", 1)[1].split("\n## ", 1)[0]
    assert "synthetic" not in caption.lower()
    assert "0.72" not in caption
    assert "0.55" in caption
    assert "signed-out" in caption.lower() or "signed out" in caption.lower()
    assert "Expression of Concern" in caption
    assert "10.2337/dc25-ec09" in caption


def test_clean_set_excludes_known_flagged_ancestors():
    assert "10.5114/amsad/184245" not in CLEAN
    assert "10.1093/jn/136.4.977" not in CLEAN
    assert "10.2174/1389557523666230725113446" not in CLEAN
    assert "10.1016/j.jsps.2015.03.013" in CLEAN
