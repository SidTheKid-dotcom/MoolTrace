from pathlib import Path

import pytest

from mooltrace.config import EVERYDAY_HEALTH_URL, ROOT
from mooltrace.seed import HERO_ID, LANCET_ID, SHARED_DB, demo_db_path, load_demo_fixtures


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


def test_demo_fixtures_are_url_only_hero_and_lancet_block():
    hero, lancet = load_demo_fixtures()
    assert hero["id"] == HERO_ID
    assert hero["text"] == ""
    assert hero["urls"] == [EVERYDAY_HEALTH_URL]
    assert lancet["id"] == LANCET_ID
    assert "10.1016/S0140-6736(20)31180-6" in lancet["text"]
    assert len(lancet["text"]) < 500
    assert "hydroxychloroquine" in lancet["text"].lower()
    joined = hero["text"] + lancet["text"]
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
