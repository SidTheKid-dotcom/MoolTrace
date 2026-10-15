from mooltrace.config import _cors_origins


def test_cors_star_is_ignored(monkeypatch):
    monkeypatch.setenv("MOOLTRACE_CORS_ORIGINS", "*")
    origins = _cors_origins()
    assert "*" not in origins
    assert origins == ["http://127.0.0.1:4318"]


def test_cors_keeps_local_origins(monkeypatch):
    monkeypatch.setenv(
        "MOOLTRACE_CORS_ORIGINS",
        "http://127.0.0.1:4318, http://localhost:4318, *",
    )
    origins = _cors_origins()
    assert origins == ["http://127.0.0.1:4318", "http://localhost:4318"]
