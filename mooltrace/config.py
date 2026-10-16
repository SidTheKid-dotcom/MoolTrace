"""Paths and public-API identity for MoolTrace."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("MOOLTRACE_DB", ROOT / "data" / "mooltrace.db"))
MAILTO = os.environ.get("MOOLTRACE_MAILTO", "mooltrace-demo@example.com")
GRAPH_NAME = os.environ.get("MOOLTRACE_GRAPH", "mooltrace")
API_HOST = os.environ.get("MOOLTRACE_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("MOOLTRACE_API_PORT", "4317"))
def _cors_origins() -> list[str]:
    raw = os.environ.get(
        "MOOLTRACE_CORS_ORIGINS",
        "http://127.0.0.1:4318,http://localhost:4318",
    )
    origins = []
    for origin in raw.split(","):
        item = origin.strip()
        if not item or item == "*":
            continue
        origins.append(item)
    return origins or ["http://127.0.0.1:4318"]


CORS_ORIGINS = _cors_origins()

USER_AGENT = f"MoolTrace/0.1 (mailto:{MAILTO}) WeMakeDevs-GraphHacks-Track1"
PAGE_USER_AGENT = (
    "Mozilla/5.0 (compatible; MoolTrace/0.1; research demo; "
    f"+mailto:{MAILTO})"
)

# Demo cases. Used by the seeded regression and UI presets, not as
# production judgment priority.
KHAN_DOI = "10.2337/diacare.26.12.3215"
EOC_DOI = "10.2337/dc25-ec09"
LANCET_HCQ_DOI = "10.1016/s0140-6736(20)31180-6"
LANCET_RETRACTION_DOI = "10.1016/s0140-6736(20)31324-6"
DIABETES_CARE_ISSNS = ("0149-5992", "1935-5548")
EVERYDAY_HEALTH_URL = "https://www.everydayhealth.com/diabetes/cinnamon-for-diabetes/"
HEALTHLINE_CINNAMON_URL = "https://www.healthline.com/nutrition/cinnamon-and-diabetes"
# Clean rewrite target: in the labelled clean set, no notice at depth 2.
CLEAN_REWRITE_DOI = "10.1016/j.jsps.2015.03.013"

# Depth 3 is implemented (seeds plus a few review neighbours). Depth 4 is
# not a distinct walk, so the product caps here instead of pretending.
MAX_DEPTH = 3
DEFAULT_DEPTH = 2
MAX_SEEDS_TO_EXPAND = 15
MAX_DEPTH3_REVIEWS = 8
CROSSREF_BATCH = 20
OPENALEX_BATCH = 50
RO_QUERY_TIMEOUT_MS = 3000
RO_QUERY_LIMIT = 50
HTTP_MAX_BYTES = 2_000_000
HTTP_MAX_DECOMPRESS = 4_000_000
CACHE_MAX = 256
OPENALEX_MAX_RPS = float(os.environ.get("MOOLTRACE_OPENALEX_RPS", "8"))
CROSSREF_MAX_RPS = float(os.environ.get("MOOLTRACE_CROSSREF_RPS", "8"))
NCBI_MAX_RPS = float(os.environ.get("MOOLTRACE_NCBI_RPS", "5"))
HTTP_RETRY_ATTEMPTS = int(os.environ.get("MOOLTRACE_HTTP_RETRIES", "4"))
HTTP_RETRY_AFTER_CAP_S = float(os.environ.get("MOOLTRACE_RETRY_AFTER_CAP_S", "60"))
NOTICE_REFRESH_TTL_S = int(os.environ.get("MOOLTRACE_NOTICE_TTL_S", str(24 * 60 * 60)))
MAX_REDIRECTS = 5


def clamp_depth(depth: int | None) -> int:
    try:
        value = int(depth) if depth is not None else DEFAULT_DEPTH
    except (TypeError, ValueError):
        value = DEFAULT_DEPTH
    return max(1, min(MAX_DEPTH, value))
