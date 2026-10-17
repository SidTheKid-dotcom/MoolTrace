"""CLAIMS.md and JUDGES.md must prove README claims with commands."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
TRACK = "Agents That Act on Connected Data"
DEMO = "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/"
MCP = f"{DEMO}mcp"


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, flags=re.S)


def test_claims_md_exists():
    path = ROOT / "CLAIMS.md"
    assert path.is_file(), "CLAIMS.md is required (every README claim -> command)"


def test_claims_covers_every_readme_bash_command():
    claims = (ROOT / "CLAIMS.md").read_text()
    missing: list[str] = []
    for block in _bash_blocks(README):
        for raw in block.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                continue
            needle = line
            if "python3 -m venv" in line:
                needle = "python3 -m venv .venv"
            if needle not in claims:
                missing.append(line)
    assert not missing, missing


def test_claims_records_confirmed_outputs_and_quickstart_time():
    claims = (ROOT / "CLAIMS.md").read_text()
    for needle in (
        TRACK,
        DEMO,
        MCP,
        "WARN (exit 2)",
        "BLOCK (exit 1)",
        "pass | 0",
        "block | 1",
        "error | 3",
        "0.8974",
        "0.4286",
        "15",
        "algo.SPpaths",
        "10.1056/nejmc1806491",
        "10.2337/dc25-ec09",
        "examples/lancet.jsonl",
        "examples/answers.jsonl",
        "examples/agent_loop.py",
        "mooltrace baseline",
        "mooltrace vitality",
        "31/40",
        "Not in the graph",
        "expanded 0 of 0 cited works",
        "unshare --net --map-root-user",
        "fresh clone",
        "/tmp",
        "Confirmed",
    ):
        assert needle in claims, needle
    assert re.search(
        r"quickstart.*\b(\d+m\s*\d+(\.\d+)?s|\d+\.\d+\s*s|\d+\s*s)\b",
        claims,
        flags=re.I,
    ), "CLAIMS.md must state the timed fresh-clone quickstart"


def test_readme_states_fresh_clone_quickstart_time():
    assert "was not re-timed" not in README
    assert "fresh clone" in README.lower()
    assert "/tmp" in README
    assert re.search(
        r"(clone \+ `?pip install`?|quickstart).{0,160}\b(\d+m\s*\d+(\.\d+)?s|\d+\.\d+\s*s)\b",
        README,
        flags=re.I | re.S,
    ), "README must state the timed fresh-clone quickstart"


def test_judges_is_five_minute_path():
    judges = (ROOT / "JUDGES.md").read_text()
    for needle in (
        TRACK,
        DEMO,
        "Harvard vitamin D (block)",
        "Healthline olive oil (warn)",
        "BLOCK",
        "0.30",
        "10.1056/nejmc1806491",
        "examples/lancet.jsonl --fail-on block",
        MCP,
        "check_answer",
        "what_rests_on",
        "mooltrace.mcp_server",
        ".venv/bin/python -m mooltrace mcp",
        "Why the graph decided",
    ):
        assert needle in judges, needle
    assert "click" in judges.lower()
    assert "mcp" in judges.lower()
