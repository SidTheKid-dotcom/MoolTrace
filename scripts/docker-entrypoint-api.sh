#!/bin/sh
set -eu
DB="${MOOLTRACE_DB:-/data/demo.db}"
mkdir -p "$(dirname "$DB")"
if [ "${MOOLTRACE_SEED:-1}" = "1" ]; then
  python -m mooltrace seed --if-empty || echo "seed: live catalogs did not finish; API still starts" >&2
fi
exec python -m mooltrace.api
