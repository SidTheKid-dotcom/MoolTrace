#!/bin/sh
set -eu
DB="${MOOLTRACE_DB:-/data/demo.db}"
mkdir -p "$(dirname "$DB")"
if [ "${MOOLTRACE_SEED:-1}" = "1" ]; then
  if [ "${MOOLTRACE_PUBLIC_DEMO:-0}" = "1" ]; then
    python -m mooltrace seed --if-empty --offline || echo "seed: offline presets did not finish; API still starts" >&2
  else
    python -m mooltrace seed --if-empty || echo "seed: live catalogs did not finish; API still starts" >&2
  fi
fi
exec python -m mooltrace.api
