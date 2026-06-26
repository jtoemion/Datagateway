#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch → build dashboard
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/3] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/3] Fetch news..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/3] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "=== Done ==="
