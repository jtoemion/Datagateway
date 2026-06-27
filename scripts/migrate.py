#!/usr/bin/env python3
"""
Datagateway — Migration Runner (CODE, idempotent DDL)
Applies CREATE TABLE IF NOT EXISTS and ALTER TABLE migrations.
Safe to run repeatedly — all operations are idempotent.
"""

import sqlite3
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "datagateway.db"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


# ── Migration list -------------------------------------------------------------
# Each entry is (version, description, sql_list).
# Versions are integers; the runner tracks which have been applied.
# New migrations APPEND to this list — never modify or remove entries.

MIGRATIONS = [
    (1, "Initial schema — sources, articles, cache, fetch_log, meta",
     [
         """CREATE TABLE IF NOT EXISTS sources (
             name        TEXT PRIMARY KEY,
             url         TEXT NOT NULL,
             lang        TEXT DEFAULT 'id',
             category    TEXT DEFAULT 'umum',
             last_fetched TEXT,
             etag        TEXT,
             created_at  TEXT DEFAULT (datetime('now'))
         );""",
         """CREATE TABLE IF NOT EXISTS articles (
             id          TEXT PRIMARY KEY,
             source      TEXT NOT NULL REFERENCES sources(name),
             title       TEXT NOT NULL,
             url         TEXT NOT NULL,
             description TEXT DEFAULT '',
             image_url   TEXT DEFAULT '',
             date        TEXT NOT NULL,
             date_wib    TEXT,
             category    TEXT DEFAULT 'umum',
             lang        TEXT DEFAULT 'id',
             filepath    TEXT,
             wikilink    TEXT,
             created_at  TEXT DEFAULT (datetime('now')),
             UNIQUE(url)
         );""",
         "CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date DESC);",
         "CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);",
         "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);",
         """CREATE TABLE IF NOT EXISTS cache (
             cache_key   TEXT PRIMARY KEY,
             body        TEXT,
             status_code INTEGER,
             fetched_at  REAL NOT NULL,
             expires_at  REAL NOT NULL,
             etag        TEXT
         );""",
         """CREATE TABLE IF NOT EXISTS fetch_log (
             id          INTEGER PRIMARY KEY AUTOINCREMENT,
             source      TEXT NOT NULL,
             fetched_at  TEXT NOT NULL,
             article_count INTEGER DEFAULT 0,
             status      TEXT DEFAULT 'ok',
             error_msg   TEXT
         );""",
         """CREATE TABLE IF NOT EXISTS meta (
             key   TEXT PRIMARY KEY,
             value TEXT
         );""",
     ]),

    (2, "Football events + odds tables",
     [
         """CREATE TABLE IF NOT EXISTS football_events (
             event_id      TEXT PRIMARY KEY,
             sport_id      INTEGER DEFAULT 18,
             event_date    TEXT NOT NULL,
             event_status  TEXT DEFAULT 'STATUS_SCHEDULED',
             status_detail TEXT DEFAULT 'Scheduled',
             team_away_id  INTEGER,
             team_away     TEXT,
             team_away_abbr TEXT,
             team_home_id  INTEGER,
             team_home     TEXT,
             team_home_abbr TEXT,
             score_away    INTEGER DEFAULT 0,
             score_home    INTEGER DEFAULT 0,
             venue_name    TEXT,
             venue_location TEXT,
             broadcast     TEXT,
             season_type   TEXT,
             attendance    TEXT,
             espn_uid      TEXT,
             fetched_at    TEXT DEFAULT (datetime('now'))
         );""",
         "CREATE INDEX IF NOT EXISTS idx_football_date ON football_events(event_date);",
         """CREATE TABLE IF NOT EXISTS football_odds (
             id            INTEGER PRIMARY KEY AUTOINCREMENT,
             event_id      TEXT NOT NULL REFERENCES football_events(event_id),
             market_id     INTEGER NOT NULL,
             market_name   TEXT,
             affiliate_id  INTEGER,
             affiliate_name TEXT,
             participant_type TEXT,
             participant_name TEXT,
             price_american INTEGER,
             price_decimal  REAL,
             is_main_line   INTEGER DEFAULT 0,
             line_value    REAL,
             updated_at    TEXT,
             UNIQUE(event_id, market_id, affiliate_id, participant_name, line_value)
         );""",
     ]),

    (3, "Scraped articles + article metadata tables",
     [
         """CREATE TABLE IF NOT EXISTS scraped_articles (
             article_id  TEXT PRIMARY KEY REFERENCES articles(id),
             url         TEXT NOT NULL,
             title       TEXT,
             author      TEXT DEFAULT '',
             full_html   TEXT,
             full_text   TEXT,
             images_json TEXT DEFAULT '[]',
             scraped_at  TEXT DEFAULT (datetime('now')),
             fetch_count INTEGER DEFAULT 1
         );""",
         """CREATE TABLE IF NOT EXISTS article_metadata (
             article_id   TEXT PRIMARY KEY REFERENCES articles(id),
             sections     TEXT DEFAULT '[]',
             keywords     TEXT DEFAULT '[]',
             entities     TEXT DEFAULT '[]',
             word_count   INTEGER DEFAULT 0,
             reading_time INTEGER DEFAULT 0,
             enriched_at  TEXT DEFAULT (datetime('now'))
         );""",
     ]),

    (4, "Entities, article_entities, entity_cooccurrence tables",
     [
         """CREATE TABLE IF NOT EXISTS entities (
             id           TEXT PRIMARY KEY,
             canonical    TEXT NOT NULL UNIQUE,
             type         TEXT NOT NULL,
             aliases_json TEXT DEFAULT '[]',
             first_seen   TEXT NOT NULL,
             last_seen    TEXT NOT NULL,
             article_count INTEGER DEFAULT 0
         );""",
         """CREATE TABLE IF NOT EXISTS article_entities (
             article_id    TEXT NOT NULL REFERENCES articles(id),
             entity_id     TEXT NOT NULL REFERENCES entities(id),
             mention_count INTEGER DEFAULT 1,
             PRIMARY KEY (article_id, entity_id)
         );""",
         """CREATE TABLE IF NOT EXISTS entity_cooccurrence (
             entity_a     TEXT NOT NULL REFERENCES entities(id),
             entity_b     TEXT NOT NULL REFERENCES entities(id),
             co_count     INTEGER DEFAULT 1,
             last_seen    TEXT NOT NULL,
             PRIMARY KEY (entity_a, entity_b)
         );""",
     ]),
    (5, "Provenance, clusters, signals + article ALTER columns",
     [
         "ALTER TABLE articles ADD COLUMN wire_origin TEXT DEFAULT ''",
         "ALTER TABLE articles ADD COLUMN provenance_group TEXT",
         "ALTER TABLE articles ADD COLUMN is_originator INTEGER DEFAULT 0",
         "ALTER TABLE articles ADD COLUMN minhash_sig TEXT",
         """CREATE TABLE IF NOT EXISTS provenance_groups (
             id         TEXT PRIMARY KEY,
             originator_article_id TEXT REFERENCES articles(id),
             match_type TEXT DEFAULT 'exact',
             group_size INTEGER DEFAULT 1,
             created_at TEXT DEFAULT (datetime('now'))
         );""",
         """CREATE TABLE IF NOT EXISTS clusters (
             id         TEXT PRIMARY KEY,
             lineage_id TEXT,
             article_count INTEGER DEFAULT 1,
             top_entities TEXT DEFAULT '[]',
             consistency REAL DEFAULT 1.0,
             created_at TEXT DEFAULT (datetime('now'))
         );""",
         "CREATE INDEX IF NOT EXISTS idx_clusters_lineage ON clusters(lineage_id);",
         """CREATE TABLE IF NOT EXISTS signals (
             id             TEXT PRIMARY KEY,
             cluster_id     TEXT REFERENCES clusters(id),
             title          TEXT,
             summary        TEXT,
             confidence     TEXT DEFAULT 'UNKNOWN',
             effective_sources REAL DEFAULT 0,
             source_count   INTEGER DEFAULT 0,
             originator_count INTEGER DEFAULT 0,
             is_contested   INTEGER DEFAULT 0,
             article_ids    TEXT DEFAULT '[]',
             entity_ids     TEXT DEFAULT '[]',
             lineage_id     TEXT,
             created_at     TEXT DEFAULT (datetime('now'))
         );""",
         "CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence);",
     ]),
]


def apply_migration(db, version: int, description: str, statements: list[str]):
    """Apply a single migration within a transaction."""
    print(f"  [M{version:03d}] {description}")
    for sql in statements:
        sql = sql.strip()
        if not sql:
            continue
        try:
            db.execute(sql)
        except sqlite3.OperationalError as e:
            # For ALTER TABLE ADD COLUMN, "duplicate column" is normal (idempotent)
            if "duplicate column" in str(e):
                print(f"    ⚠ column already exists: {e}")
            else:
                raise
    # Record migration
    db.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
        (f"migration_{version}", description),
    )
    db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


def run(up_to: int | None = None, verbose: bool = False):
    """Run all pending migrations up to `up_to` (None = all)."""
    db = get_db()

    # Ensure meta table exists for tracking
    db.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )

    # Get current schema version
    row = db.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    current = int(row["value"]) if row else 0

    applied = 0
    for version, description, statements in MIGRATIONS:
        if up_to is not None and version > up_to:
            break
        if version <= current:
            if verbose:
                print(f"  [M{version:03d}] ✓ already applied ({description})")
            continue

        apply_migration(db, version, description, statements)
        db.commit()
        applied += 1
        print(f"    ✓ applied")

    db.close()
    return applied


def main():
    """CLI entry point."""
    up_to = None
    verbose = False
    args = sys.argv[1:]
    if "--up-to" in args:
        idx = args.index("--up-to")
        up_to = int(args[idx + 1])
    if "--verbose" in args:
        verbose = True

    print(f"Datagateway — Migration Runner")
    print(f"  Current ver: ? (checking...)", end="\r")
    sys.stdout.flush()

    db = get_db()
    row = db.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    current = int(row["value"]) if row else 0
    db.close()

    print(f"  Current ver: {current}  ")
    print(f"  Total migrations: {len(MIGRATIONS)}")
    print()

    applied = run(up_to=up_to, verbose=verbose)

    if applied:
        print(f"\n  Applied: {applied} migration(s)")
    else:
        print(f"  Nothing to migrate — schema is up to date.")

    return 0


if __name__ == "__main__":
    main()
