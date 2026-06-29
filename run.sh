#!/usr/bin/env bash
# Datagateway — Run pipeline: init-db → fetch → normalize → enrich → arc → signal → build
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Datagateway Pipeline ==="
echo ""

echo "[1/17] Init database..."
PYTHONPATH=. python3 -c "from scripts.database import init_db; init_db(); print('  DB: datagateway.db ready')"

echo ""
echo "[2/17] Fetch news + football..."
PYTHONPATH=. python3 scripts/fetch-news.py

echo ""
echo "[3/17] Fetch football (TheRundown)..."
PYTHONPATH=. python3 scripts/fetch-football.py

echo ""
echo "[4/17] Scrape full articles..."
PYTHONPATH=. python3 scripts/scrape-article.py

echo ""
echo "[5/17] Layer 1 — RSS normalize (≥250c contract)..."
PYTHONPATH=. python3 -c "from scripts.enrich.normalize import run_normalize_pipeline; r = run_normalize_pipeline(); print(f'  passthrough:{r[\"passthrough\"]} normalized:{r[\"normalized\"]} stub:{r[\"stub\"]}')"

echo ""
echo "[6/17] Enrich metadata (sections, keywords)..."
PYTHONPATH=. python3 scripts/enrich-metadata.py

echo ""
echo "[7/17] Auto-generate metadata (catch missing)..."
PYTHONPATH=. python3 scripts/auto-meta.py --pipeline

echo ""
echo "[8/17] Layer 2 — Entity enrichment (NER, wikilinks, entity pages)..."
PYTHONPATH=. python3 -c "from scripts.enrich.gateway import enrich_entity_pipeline; r = enrich_entity_pipeline(); print(f'  Processed: {r[\"processed\"]}, Tagged: {r[\"tagged\"]}, Entity pages: {r[\"entity_pages\"]}')"

echo ""
echo "[9/17] Layer 2 — Entity graph (nPMI + arc detection)..."
PYTHONPATH=. python3 -c "from scripts.enrich.layer2 import run_layer2; r = run_layer2(); print(f'  nPMI pairs:{r[\"npmi_pairs\"]} active entities:{r[\"active_entities\"]} arcs:{r[\"arcs_upserted\"]}')"

echo ""
echo "[10/17] Layer 3 — Arc maturation (on-demand fetch + FETCH_READY gate)..."
PYTHONPATH=. python3 -c "from scripts.signal.layer3 import run_layer3; r = run_layer3(); print(f'  processed:{r[\"arcs_processed\"]} fetched:{r[\"fetched\"]} ready:{r[\"fetch_ready\"]}')"

echo ""
echo "[11/17] Build BM25 search index..."
PYTHONPATH=. python3 scripts/search-index.py

echo ""
echo "[12/17] Update .md files with full article text..."
PYTHONPATH=. python3 scripts/update-md-content.py

echo ""
echo "[13/17] Signal pipeline (provenance → cluster → score)..."
PYTHONPATH=. python3 -c "from scripts.signal.gateway import run; r = run(); print(f'  Groups: {r[\"groups\"]}, Clusters: {r[\"clusters\"]}, Signals: {r[\"signals\"]}')"

echo ""
echo "[14/17] Hermes writer (signal briefs)..."
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
print(f'  Written: {written} Hermes signal briefs')
"

echo ""
echo "[14b/17] Layer 4 — Arc synthesis (conclusion articles)..."
PYTHONPATH=. python3 -c "from scripts.signal.layer4 import run_layer4; r = run_layer4(); print(f'  written:{r[\"written\"]} skipped:{r[\"skipped\"]}')"

echo ""
echo "[15/17] Build dashboard..."
PYTHONPATH=. python3 scripts/build-dashboard.py

echo ""
echo "[16/17] Build article viewer..."
PYTHONPATH=. python3 scripts/build-article-viewer.py

echo ""
echo "[17/17] Build entity viewer..."
PYTHONPATH=. python3 scripts/build-entity-viewer.py

echo ""
echo "Write health check..."
PYTHONPATH=. python3 -c "from scripts.health import write_success; write_success(steps=17)"

echo ""
echo "=== Done ==="
