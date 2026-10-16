import importlib.util
from pathlib import Path


def test_agent_loop_check_rewrite_recheck_offline():
    path = Path(__file__).resolve().parents[1] / "examples" / "agent_loop.py"
    spec = importlib.util.spec_from_file_location("mooltrace_agent_loop", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.run()
    assert out["check"] == "warn"
    assert out["algorithm"] == "algo.SPpaths"
    assert out["affected"] == 1
