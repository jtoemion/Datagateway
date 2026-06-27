#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch → scrape → enrich → entity → signal → build
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/14] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/14] Fetch news + football..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/14] Fetch football (TheRundown)..."
PYTHONPATH=. python3 scripts/fetch-football.py

echo ""
echo "[4/14] Scrape full articles..."
PYTHONPATH=. python3 scripts/scrape-article.py

echo ""
echo "[5/14] Enrich metadata (sections, keywords)..."
PYTHONPATH=. python3 scripts/enrich-metadata.py

echo ""
echo "[6/14] Auto-generate metadata (catch missing)..."
PYTHONPATH=. python3 scripts/auto-meta.py --pipeline

echo ""
echo "[7/14] Entity enrichment (NER, wikilinks, entity pages)..."
PYTHONPATH=. python3 -c "from scripts.enrich.gateway import enrich_entity_pipeline; r = enrich_entity_pipeline(); print(f'  Processed: {r[\"processed\"]}, Tagged: {r[\"tagged\"]}, Entity pages: {r[\"entity_pages\"]}')"

echo ""
echo "[8/14] Build BM25 search index..."
PYTHONPATH=. python3 scripts/search-index.py

echo ""
echo "[9/14] Update .md files with full article text..."
PYTHONPATH=. python3 scripts/update-md-content.py

echo ""
echo "[10/14] Signal pipeline (provenance → cluster → score)..."
PYTHONPATH=. python3 -c "from scripts.signal.gateway import run; r = run(); print(f'  Groups: {r[\"groups\"]}, Clusters: {r[\"clusters\"]}, Signals: {r[\"signals\"]}')"

echo ""
echo "[11/14] Hermes writer (analytical briefs)..."
PYTHONPATH=. python3 -c "
from scripts.database import get_db
from scripts.signal.writer import write
db = get_db()
signals = db.execute(\"SELECT * FROM signals WHERE confidence != '' ORDER BY created_at DESC LIMIT 5\").fetchall()
db.close()
written = 0
for s in signals:
    result = write(dict(s))
    if result:
        written += 1
print(f'  Written: {written} Hermes articles')
"

echo ""
echo "[12/14] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[13/14] Build article viewer..."
PYTHONPATH=. python3 scripts/build-article-viewer.py

echo ""
echo "[14/14] Build entity viewer..."
PYTHONPATH=. python3 scripts/build-entity-viewer.py

echo ""
echo "[15/15] Write health check..."
PYTHONPATH=. python3 -c "from scripts.health import write_success; write_success(steps=15)"

echo ""
echo "=== Done ==="
