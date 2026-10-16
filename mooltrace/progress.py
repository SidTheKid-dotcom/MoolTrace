"""Stderr progress for a long cold check. Quiet in pytest (stderr is not a TTY)."""

from __future__ import annotations

import os
import sys

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def enabled() -> bool:
    raw = (os.environ.get("MOOLTRACE_PROGRESS") or "").strip().lower()
    if raw in _FALSE:
        return False
    if raw in _TRUE:
        return True
    return sys.stderr.isatty()


def emit(message: str) -> None:
    if not enabled() or not message:
        return
    print(message, file=sys.stderr, flush=True)
