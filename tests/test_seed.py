from pathlib import Path

import pytest

from mooltrace.config import CLEAN_REWRITE_DOI, HEALTHLINE_CINNAMON_URL, ROOT
from mooltrace.seed import BLOCK_ID, CLEAN_ID, SHARED_DB, WARN_ID, demo_db_path, load_demo_fixtures


def test_demo_db_path_refuses_missing_env(monkeypatch):
    monkeypatch.delenv("MOOLTRACE_DB", raising=False)
    with pytest.raises(SystemExit, match="shared data/mooltrace.db"):
        demo_db_path()


def test_demo_db_path_refuses_shared_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MOOLTRACE_DB", str(ROOT / "data" / "mooltrace.db"))
    with pytest.raises(SystemExit, match="Refusing to write the shared"):
        demo_db_path()
    assert SHARED_DB == (ROOT / "data" / "mooltrace.db").resolve()
    other = tmp_path / "demo.db"
    monkeypatch.setenv("MOOLTRACE_DB", str(other))
    assert demo_db_path() == other.resolve()


def test_demo_fixtures_are_url_only_olive_oil_block_and_cinnamon_warn():
    block, warn, clean = load_demo_fixtures()
    assert block["id"] == BLOCK_ID
    assert block["text"] == ""
    assert block["urls"] == ["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"]
    assert int(block.get("depth") or 0) == 3
    assert warn["id"] == WARN_ID
    assert warn["text"] == ""
    assert warn["urls"] == [HEALTHLINE_CINNAMON_URL]
    assert clean["id"] == CLEAN_ID
    assert CLEAN_REWRITE_DOI in clean["text"]
    joined = block["text"] + warn["text"] + clean["text"]
    assert "Introduction" not in joined
    assert "<html" not in joined.lower()


def test_compose_documents_ports_and_demo_db():
    compose = (ROOT / "docker-compose.yml").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "127.0.0.1:4317:4317" in compose
    assert "127.0.0.1:4318:4318" in compose
    assert "MOOLTRACE_DB: /data/demo.db" in compose
    assert "mooltrace-demo:/data" in compose
    assert "./data" not in compose
    assert "target: api" in compose
    assert "target: web" in compose
    assert "*" not in compose.split("MOOLTRACE_CORS_ORIGINS")[1].splitlines()[0]
    assert "FROM python:3.14-slim-trixie" in dockerfile
    assert "EXPOSE 4317" in dockerfile
    assert "EXPOSE 4318" in dockerfile
    entry = Path(ROOT / "scripts" / "docker-entrypoint-api.sh").read_text()
    assert "mooltrace seed" in entry
    assert "MOOLTRACE_PUBLIC_DEMO" in entry
