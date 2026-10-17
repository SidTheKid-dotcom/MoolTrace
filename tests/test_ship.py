"""P3.16-17: VIDEO_SCRIPT ≤90 s, SUBMISSION final, SHIP_CHECKLIST human-only."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mooltrace.cypher import sp_paths_to_notice


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "VIDEO_SCRIPT.md"
SUBMISSION = ROOT / "SUBMISSION.md"
SHIP = ROOT / "SHIP_CHECKLIST.md"
BASELINE = ROOT / "results" / "baseline_2026-10-16.json"
TRACK = "Agents That Act on Connected Data"
DEMO = "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/"
CLOSE = "MoolTrace. Check the roots before you ship."
BEATS = (
    "Problem",
    "Paste AI answer",
    "No-graph check",
    "MoolTrace BLOCK and path",
    "Not in the graph",
    "Rewrite",
    "CI fails the PR",
    "Agent acting on connected data",
    "Baseline result",
    "Close",
)
AGENT_RUN = ROOT / "examples" / "agent_runs" / "2026-10-17"
BEAT_SECONDS = (5, 8, 5, 18, 8, 8, 8, 12, 8, 5)
HEADING = re.compile(r"^#{2,3} (.+?) \((\d+) s\)\s*$", re.M)


def _headings(text: str) -> list[tuple[str, int]]:
    return [(name, int(seconds)) for name, seconds in HEADING.findall(text)]


def test_video_script_is_ninety_seconds_with_mission_beats():
    text = VIDEO.read_text()
    found = _headings(text)
    names = [name for name, _ in found]
    seconds = [sec for _, sec in found]
    assert names == list(BEATS), names
    assert seconds == list(BEAT_SECONDS), seconds
    assert sum(seconds) <= 90, sum(seconds)
    assert TRACK in text
    assert CLOSE in text
    assert "≤3:00" not in text
    assert "under 180" not in text


def test_video_script_quotes_live_numbers_with_citations():
    text = VIDEO.read_text()
    payload = json.loads(BASELINE.read_text())
    base = payload["baseline"]["metrics"]
    product = payload["mooltrace"]["metrics"]
    hops = payload["only_multihop_ids"]
    for needle in (
        TRACK,
        DEMO,
        "Harvard",
        "https://nutritionsource.hsph.harvard.edu/vitamin-d/",
        "Avenell 2014",
        "Ishida 2004",
        "uses_data_or_method",
        "path strength 0.47",
        "Healthline olive oil",
        "https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil",
        "Schwingshackl 2014",
        "Estruch 2013",
        "mention",
        "path strength 0.30",
        "depth 1",
        "0 notice paths",
        "depth 3",
        "BLOCK (exit 1)",
        "10.1016/j.amjmed.2004.05.019",
        "10.1056/nejmc1806491",
        "Not in the graph",
        "https://www.nhs.uk/live-well/best-way-to-wash-your-hands/",
        "expanded 0 of 0 cited works",
        "31/40",
        "results/vitality_2026-10-17.json",
        "retracted and republished",
        "Direct-DOI check (no graph)",
        "pass",
        "Ishida et al. 2004",
        "Hand hygiene is discussed separately.",
        "retracted on 15 Oct 2004",
        "Rewrite and recheck",
        "examples/lancet.jsonl --fail-on block",
        "exit 1",
        "examples/agent_runs/2026-10-17/",
        "check_answer",
        str(base["recall"]),
        str(product["recall"]),
        str(len(hops)),
        "results/baseline_2026-10-16.json",
        "examples/presets_recorded.json",
        CLOSE,
    ):
        assert needle in text, needle
    assert "relies on" not in text.lower() or "never say the review" in text.lower()
    assert "Azure" not in text
    assert "LLM" not in text
    assert "recheck_affected" not in text
    assert "algo.pageRank" not in text or "not called" in text
    assert "0.72" not in text
    problem = text.split("## Problem", 1)[1].split("## Paste AI answer", 1)[0]
    assert "Harvard" in problem
    assert "Healthline" not in problem
    # First graph beat is the Harvard depth toggle; olive-oil may be shortened.
    block_section = text.split("## MoolTrace BLOCK and path", 1)[1].split("## Not in the graph", 1)[0]
    assert "uses_data_or_method" in block_section
    assert "Ishida 2004" in block_section
    assert "mention" in block_section
    assert "relies" not in block_section
    lowered_block = block_section.lower()
    assert lowered_block.find("depth 1") < lowered_block.find("depth 2")
    assert "pass" in lowered_block
    assert "block" in lowered_block
    assert "0 notice paths" in lowered_block
    assert "Why the graph decided" in block_section
    assert "would ship" in block_section
    assert "Graph depth 1: 0 notice paths → PASS" in block_section
    assert "Graph depth 2: retraction 10.1016/j.amjmed.2004.05.019 → BLOCK" in block_section
    not_in = text.split("## Not in the graph", 1)[1].split("## Rewrite", 1)[0]
    assert "expanded 0 of 0 cited works" in not_in
    assert "not proof it is safe" in not_in.lower() or "not proof" in not_in.lower()
    rewrite = text.split("## Rewrite", 1)[1].split("## CI fails the PR", 1)[0]
    assert "Rewrite and recheck" in rewrite
    assert "Ishida et al. 2004" in rewrite
    assert "Hand hygiene is discussed separately." in rewrite
    assert "A nutrition coach cites:" not in rewrite
    assert "This claim:" not in rewrite
    assert "paste this two-sentence draft" not in rewrite.lower()
    assert "unrelated" in rewrite.lower()
    assert "byte-identical" in rewrite.lower()
    run_a = (AGENT_RUN / "run_a_with_mooltrace.txt").read_text()
    run_b = (AGENT_RUN / "run_b_without_mooltrace.txt").read_text()
    shipped_a = run_a.split("SHIPPED:", 1)[1].strip()
    shipped_b = run_b.split("SHIPPED:", 1)[1].strip()
    agent = text.split("## Agent acting on connected data", 1)[1].split("## Baseline result", 1)[0]
    assert shipped_a in agent
    assert shipped_b in agent
    assert "check_answer" in agent
    assert "rewrite" in agent.lower()
    assert "BLOCK" in agent
    assert "what_rests_on" not in agent


def test_submission_has_track_links_cypher_algorithms_video_placeholder():
    text = SUBMISSION.read_text()
    payload = json.loads(BASELINE.read_text())
    assert TRACK in next(
        line for line in text.splitlines() if line.startswith("**Track:**")
    )
    assert "01 — Context for AI Agents" not in text
    assert DEMO in text
    assert "_paste after upload_" in text or "paste after upload" in text.lower()
    assert "github.com/SidTheKid-dotcom/MoolTrace" in text
    assert "CALL algo.SPpaths" in text
    assert "CALL algo.WCC" in text
    executed = sp_paths_to_notice(2)
    for line in executed.splitlines():
        stripped = line.strip()
        if stripped:
            assert stripped in text, stripped
    assert "CALL algo.WCC({nodeLabels: ['Work'], relationshipTypes: ['RESTS_ON']})" in text
    assert "algo.SPpaths" in text
    assert "algo.WCC" in text
    assert "algo.pageRank" in text
    assert "not called" in text.lower() or "is **not** called" in text
    assert "video" in text.lower()
    assert str(payload["baseline"]["metrics"]["recall"]) in text
    assert str(payload["mooltrace"]["metrics"]["recall"]) in text
    assert "rewrite_answer" not in text.split("## Links", 1)[0] or "local" in text.lower()
    assert "Azure AI Foundry" not in text
    assert "LLM rewrit" not in text.lower()
    assert "## AI-assistance disclosure" in text
    section = text.split("## AI-assistance disclosure", 1)[1].split("\n## ", 1)[0]
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
    assert "AZURE_OPENAI" not in section


def test_ship_checklist_is_human_only():
    text = SHIP.read_text()
    lowered = text.lower()
    order = [
        "record the video",
        "make the github repo public",
        "paste links",
        "final check",
    ]
    last = -1
    for needle in order:
        index = lowered.find(needle)
        assert index >= 0, needle
        assert index > last, needle
        last = index
    assert "VIDEO_SCRIPT.md" in text
    assert "SUBMISSION.md" in text
    assert DEMO in text
    assert TRACK in text
    assert "90" in text
    assert "depth 1" in lowered
    assert "not in the graph" in lowered
    assert "under 180" not in lowered
    assert "≤3 min" not in text
    assert "unshare --net" not in text
    assert "python -m mooltrace.gate" not in text
    assert "gh repo edit" in text
    assert "signed-out" in lowered or "signed out" in lowered
    assert "do not rewrite" in lowered or "do not rewrite history" in lowered


def test_lightsail_pin_is_public_demo_without_azure():
    payload = json.loads((ROOT / "deploy" / "lightsail-deployment.json").read_text())
    env = payload["containers"]["api"]["environment"]
    assert env.get("MOOLTRACE_PUBLIC_DEMO") == "1"
    assert env.get("MOOLTRACE_PUBLIC_LIVE") == "1"
    blob = json.dumps(payload)
    assert "AZURE" not in blob
    assert "OPENAI" not in blob
    api = payload["containers"]["api"]["image"]
    web = payload["containers"]["web"]["image"]
    assert api.startswith(":mooltrace.api.")
    assert web.startswith(":mooltrace.web.")
    ship = SHIP.read_text()
    assert api in ship
    assert web in ship
