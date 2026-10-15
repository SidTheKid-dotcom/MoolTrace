from mooltrace.config import ROOT


def test_viewer_rewrite_uses_api_origin_env():
    text = (ROOT / "web" / "next.config.ts").read_text()
    assert "MOOLTRACE_API_ORIGIN" in text
    assert "http://127.0.0.1:4317" in text
