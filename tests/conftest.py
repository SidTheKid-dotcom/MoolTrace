from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_process_singletons():
    yield
    from mooltrace.clients import close_client
    from mooltrace import graph as graph_mod

    close_client()
    if graph_mod._singleton is not None:
        graph_mod._singleton.close()
        graph_mod._singleton = None
