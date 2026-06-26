#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch → scrape → enrich → build
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/9] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/9] Fetch news..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/9] Fetch football..."
PYTHONPATH=. python3 scripts/fetch-football.py

echo ""
echo "[4/9] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[5/9] Scrape full articles..."
PYTHONPATH=. python3 scripts/scrape-article.py

echo ""
echo "[6/9] Enrich metadata (sections, keywords, entities)..."
PYTHONPATH=. python3 scripts/enrich-metadata.py

echo ""
echo "[7/10] Auto-generate metadata..."
PYTHONPATH=. python3 scripts/auto-meta.py --pipeline

echo ""
echo "[8/10] Build BM25 search index..."
PYTHONPATH=. python3 scripts/search-index.py

echo ""
echo "[9/10] Rebuild dashboard with metadata..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[10/10] Build article viewer..."
PYTHONPATH=. python3 scripts/build-article-viewer.py

echo ""
echo "=== Done ==="
