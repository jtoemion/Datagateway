# Datagateway

OSINT Daily News Aggregator — kumpulan berita terbaru dari portal Indonesia & internasional, disimpan sebagai dokumen Markdown terstruktur dengan HTML dashboard.

## Struktur

```
Datagateway/
├── config.yaml                 # Sumber RSS & pengaturan
├── run.sh                      # Pipeline: fetch → dashboard
├── scripts/
│   ├── fetch-news.py           # Ambil berita dari RSS feeds
│   └── build-dashboard.py      # Generate HTML dashboard
├── news/                       # Berita sebagai .md
│   └── YYYY-MM-DD/
│       └── source-slug.md
└── dashboard/
    └── index.html              # Dashboard HTML statis
```

## Cara Pakai

```bash
# Fetch berita terbaru + build dashboard
bash run.sh

# Atau step by step:
python3 scripts/fetch-news.py
python3 scripts/build-dashboard.py
```

## Sumber Berita

| Sumber | Bahasa | Kategori |
|--------|--------|----------|
| Kompas | id | umum |
| Detik | id | umum |
| CNN Indonesia | id | umum |
| Tempo | id | umum |
| Antara | id | umum |
| Liputan6 | id | umum |
| Okezone | id | umum |
| Republika | id | umum |
| BBC Indonesia | id | internasional |
| BBC News | en | internasional |
| Reuters | en | internasional |

## Format Berita (.md)

Setiap artikel disimpan dengan frontmatter YAML:

```markdown
---
id: a1b2c3d4e5f6
source: "Kompas"
title: "Judul Berita"
url: "https://..."
date: "2026-06-26T08:30:00+07:00"
category: umum
lang: id
---

# Judul Berita
```

## Dashboard

Dashboard HTML statis di `dashboard/index.html` — grid card, filter by source, search, stats. Bisa di-serve pake apa aja:

```bash
# Python
python3 -m http.server 8080 -d dashboard/

# Atau npx serve
npx serve dashboard/
```
