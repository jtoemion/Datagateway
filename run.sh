#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch → scrape → enrich → .md update → build
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/11] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/11] Fetch news..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/11] Fetch football..."
PYTHONPATH=. python3 scripts/fetch-football.py

echo ""
echo "[4/11] Build dashboard (initial)..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[5/11] Scrape full articles..."
PYTHONPATH=. python3 scripts/scrape-article.py

echo ""
echo "[6/11] Enrich metadata (sections, keywords, entities)..."
PYTHONPATH=. python3 scripts/enrich-metadata.py

echo ""
echo "[7/11] Auto-generate metadata (catch missing)..."
PYTHONPATH=. python3 scripts/auto-meta.py --pipeline

echo ""
echo "[8/11] Build BM25 search index..."
PYTHONPATH=. python3 scripts/search-index.py

echo ""
echo "[9/11] Update .md files with full article text..."
PYTHONPATH=. python3 scripts/update-md-content.py

echo ""
echo "[10/11] Rebuild dashboard with metadata..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[11/11] Build article viewer..."
PYTHONPATH=. python3 scripts/build-article-viewer.py

echo ""
echo "=== Done ==="
