from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_process_singletons(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("MOOLTRACE_HTTP_CACHE", str(tmp_path_factory.mktemp("http-cache")))
    from mooltrace.clients import reset_http_state

    reset_http_state()
    yield
    from mooltrace.clients import close_client
    from mooltrace import graph as graph_mod

    close_client()
    reset_http_state()
    if graph_mod._singleton is not None:
        graph_mod._singleton.close()
        graph_mod._singleton = None
