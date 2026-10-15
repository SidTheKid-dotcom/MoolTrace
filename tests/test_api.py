from fastapi.testclient import TestClient

from mooltrace.api import app
from mooltrace.clients import CallStats, MoolTraceError, fetch_page, fetch_resource
from mooltrace.graph import Graph


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_optional_resource_dns_failure_is_a_miss_not_a_crash(monkeypatch):
    from mooltrace.ssrf import UnsafeURL

    def boom(*_args, **_kwargs):
        raise UnsafeURL("could not resolve host 'doi.org'")

    monkeypatch.setattr("mooltrace.clients._public_get", boom)
    code, _ctype, body = fetch_resource("https://doi.org/10.3390/foods12030452", CallStats())
    assert code == 0
    assert body == b""


def test_fetch_page_rejects_loopback():
    try:
        fetch_page("http://127.0.0.1/", CallStats())
    except MoolTraceError as exc:
        text = str(exc).lower()
        assert "refused" in text or "not public" in text
        return
    raise AssertionError("loopback fetch was allowed")


def test_cypher_write_is_rejected(tmp_path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        client = TestClient(app)
        response = client.post("/cypher", json={"query": "CREATE (:Work {doi: '10.1/nope'})"})
        assert response.status_code == 400
        assert "read-only" in response.json()["detail"].lower()
    finally:
        graph.close()


def test_check_answer_plain_prose_is_no_sources(tmp_path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        client = TestClient(app)
        response = client.post(
            "/check-answer",
            json={
                "text": "Cinnamon may help blood sugar in some people.",
                "urls": [],
                "engine": "prose",
                "depth": 1,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "warn"
        assert body["exit_code"] == 2
        assert body["error_code"] == "no_sources"
        assert body["reasons"][0]["code"] == "no_sources"
        assert body["works_cited"] == 0
        assert body["pitch"] is None
    finally:
        graph.close()


def test_check_answer_credential_url_is_warn(tmp_path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        client = TestClient(app)
        response = client.post(
            "/check-answer",
            json={
                "text": "ssrf creds",
                "urls": ["http://user:pass@example.com/secret"],
                "engine": "ssrf-creds",
                "depth": 1,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "warn"
        assert body["exit_code"] == 2
    finally:
        graph.close()


def test_check_answer_ssrf_is_warn_not_pass(tmp_path, monkeypatch):
    graph = Graph(tmp_path / "mooltrace.db")
    monkeypatch.setattr("mooltrace.trace.get_graph", lambda: graph)
    try:
        client = TestClient(app)
        response = client.post(
            "/check-answer",
            json={
                "text": "ssrf probe",
                "urls": ["http://127.0.0.1/secret", "http://10.0.0.1/x"],
                "engine": "ssrf",
                "depth": 1,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "warn"
        assert body["exit_code"] == 2
        assert body.get("errors")
    finally:
        graph.close()
