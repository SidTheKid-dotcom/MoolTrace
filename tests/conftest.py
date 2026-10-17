from __future__ import annotations

import os

import pytest

# Recorded fixtures carry fixed fetch dates. Tests check logic, not freshness, so pin a long
# notice-refresh window before mooltrace.config is imported; otherwise the suite starts
# going to the network (and failing offline) 24 h after the fixtures were recorded.
# Tests about refresh behaviour set their own TTL.
os.environ.setdefault("MOOLTRACE_NOTICE_TTL_S", str(10 * 365 * 24 * 60 * 60))


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
