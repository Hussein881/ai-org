#!/usr/bin/env bash
# Fails if web/src/lib/api-types.ts is stale relative to the FastAPI OpenAPI schema.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
PYTHONPATH=. AIORG_SESSION_SECRET=x uv run python scripts/gen-openapi.py "$tmp/openapi.json"
(cd web && npx openapi-typescript "$tmp/openapi.json" -o "$tmp/api-types.ts" >/dev/null)
diff -q "$tmp/api-types.ts" web/src/lib/api-types.ts >/dev/null || { echo "API_TYPES_STALE"; exit 1; }
echo "API_TYPES_FRESH"
