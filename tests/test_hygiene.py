"""Public-repo hygiene: no personal Gmail, cache keys ignore identity query params."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mooltrace.clients import _cache_key


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAILTO = "mooltrace@users.noreply.github.com"
GMAIL = "@" + "gmail.com"


def test_tracked_files_contain_no_gmail_address():
    listed = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    hits: list[str] = []
    needle = GMAIL.encode("ascii")
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        path = ROOT / rel
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        if needle in blob:
            hits.append(rel)
    assert hits == [], hits


def test_cache_key_strips_mailto_and_email_query_params():
    idconv_a = _cache_key(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=30461730&format=json"
        "&tool=mooltrace&email=one@example.com"
    )
    idconv_b = _cache_key(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=30461730&format=json"
        "&tool=mooltrace&email=two@example.com"
    )
    oa_a = _cache_key("https://api.openalex.org/works?filter=doi:10.1/x&mailto=one@example.com")
    oa_b = _cache_key("https://api.openalex.org/works?filter=doi:10.1/x&mailto=two@example.com")
    assert idconv_a == idconv_b
    assert oa_a == oa_b
    bare = _cache_key(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=30461730&format=json"
        "&tool=mooltrace"
    )
    assert idconv_a == bare


def test_default_mailto_is_neutral_noreply():
    env = os.environ.copy()
    env.pop("MOOLTRACE_MAILTO", None)
    out = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from mooltrace.config import MAILTO; print(MAILTO)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    ).strip()
    assert out == DEFAULT_MAILTO
    assert GMAIL not in out


def test_unused_fly_and_render_files_are_gone():
    assert not (ROOT / "fly.toml").exists()
    assert not (ROOT / "render.yaml").exists()
    for path in (ROOT / "README.md", ROOT / "SUBMISSION.md", ROOT / "SHIP_CHECKLIST.md", ROOT / "JUDGES.md"):
        text = path.read_text(encoding="utf-8")
        assert "fly.toml" not in text
        assert "render.yaml" not in text


def test_lightsail_deployment_does_not_embed_mailto():
    text = (ROOT / "deploy" / "lightsail-deployment.json").read_text(encoding="utf-8")
    assert "MOOLTRACE_MAILTO" not in text
    ship = (ROOT / "SHIP_CHECKLIST.md").read_text(encoding="utf-8")
    assert "MOOLTRACE_MAILTO" in ship
    assert "deploy time" in ship.lower() or "at deploy" in ship.lower()


def test_docs_do_not_claim_shaky_ground_demo_is_down_from_head_501():
    for name in ("README.md", "CLAIMS.md", "JUDGES.md", "SUBMISSION.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        if "shaky-ground-production.up.railway.app" not in text:
            continue
        assert "501" in text
        assert "HEAD" in text
        assert "GET" in text
        assert "200" in text
        lowered = text.lower()
        assert "returned 501" not in lowered or "head" in lowered
