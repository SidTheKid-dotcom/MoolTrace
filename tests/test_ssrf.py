from mooltrace.config import HTTP_MAX_BYTES
from mooltrace.clients import _read_limited
from mooltrace.ssrf import UnsafeURL, public_http_url, redirect_target


def test_rejects_loopback():
    for url in (
        "http://127.0.0.1/",
        "http://localhost/secret",
        "http://[::1]/",
        "http://127.1/",
        "http://0/",
        "http://2130706433/",
        "http://[::ffff:127.0.0.1]/",
    ):
        try:
            public_http_url(url)
        except UnsafeURL:
            continue
        raise AssertionError(f"accepted {url}")


def test_rejects_private_and_link_local():
    for url in (
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.1.1/",
        "http://224.0.0.1/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "ftp://example.com/",
        "file:///etc/passwd",
    ):
        try:
            public_http_url(url)
        except UnsafeURL:
            continue
        raise AssertionError(f"accepted {url}")


def test_redirect_is_revalidated():
    try:
        redirect_target("https://example.com/a", "http://127.0.0.1/steal")
    except UnsafeURL:
        return
    raise AssertionError("loopback redirect accepted")


def test_public_https_example_passes(monkeypatch):
    monkeypatch.setattr("mooltrace.ssrf._host_ips", lambda host, port: ["93.184.216.34"])
    assert public_http_url("https://example.com/x") == "https://example.com/x"


def test_rejects_credentials_and_bad_port():
    for url in (
        "http://user:pass@example.com/x",
        "https://token@example.com/",
        "http://example.com:99999/",
    ):
        try:
            public_http_url(url)
        except UnsafeURL:
            continue
        raise AssertionError(f"accepted {url}")


def test_redirect_with_credentials_is_rejected():
    try:
        redirect_target("https://example.com/a", "https://user:pass@example.com/b")
    except UnsafeURL:
        return
    raise AssertionError("credentialed redirect accepted")


def test_response_stream_is_capped():
    class Fake:
        def iter_bytes(self):
            yield b"x" * (HTTP_MAX_BYTES + 2048)

    body = _read_limited(Fake())
    assert len(body) == HTTP_MAX_BYTES
