#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch news → fetch football → build dashboard
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/4] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/4] Fetch news..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/4] Fetch football..."
PYTHONPATH=. python3 scripts/fetch-football.py

echo ""
echo "[4/7] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[5/7] Scrape full articles..."
PYTHONPATH=. python3 scripts/scrape-article.py

echo ""
echo "[6/7] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[7/7] Build article viewer..."
PYTHONPATH=. python3 scripts/build-article-viewer.py

echo ""
echo "=== Done ==="
