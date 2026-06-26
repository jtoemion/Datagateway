#!/usr/bin/env python3
"""
Datagateway — Database layer
SQLite cache for RSS responses, article dedup, and dashboard queries.
"""

import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "datagateway.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    name        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    lang        TEXT DEFAULT 'id',
    category    TEXT DEFAULT 'umum',
    last_fetched TEXT,
    etag        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL REFERENCES sources(name),
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    description TEXT DEFAULT '',
    date        TEXT NOT NULL,
    date_wib    TEXT,
    category    TEXT DEFAULT 'umum',
    lang        TEXT DEFAULT 'id',
    filepath    TEXT,
    wikilink    TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(url)
);

CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);

CREATE TABLE IF NOT EXISTS cache (
    cache_key   TEXT PRIMARY KEY,
    body        TEXT,
    status_code INTEGER,
    fetched_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    etag        TEXT
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    article_count INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'ok',
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Default sources — sync with config.yaml
DEFAULT_SOURCES = [
    ("CNN Indonesia", "https://www.cnnindonesia.com/rss", "id", "umum"),
    ("Detik", "https://news.detik.com/rss", "id", "umum"),
    ("CNBC Indonesia", "https://www.cnbcindonesia.com/rss", "id", "bisnis"),
    ("Antara", "https://www.antaranews.com/rss/terkini", "id", "umum"),
    ("Republika", "https://www.republika.co.id/rss", "id", "umum"),
    ("BBC Indonesia", "https://feeds.bbci.co.uk/indonesia/rss.xml", "id", "internasional"),
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "en", "internasional"),
    ("NY Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "en", "internasional"),
]


def get_db() -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """Initialize schema and seed sources."""
    db = get_db()
    db.executescript(SCHEMA)

    # Seed sources
    for name, url, lang, cat in DEFAULT_SOURCES:
        db.execute(
            """INSERT OR IGNORE INTO sources (name, url, lang, category)
               VALUES (?, ?, ?, ?)""",
            (name, url, lang, cat),
        )
    db.commit()
    db.close()


def cache_get(key: str, ttl_seconds: int = 1800) -> str | None:
    """Get cached response if not expired. ttl defaults to 30 min."""
    db = get_db()
    row = db.execute(
        "SELECT body, fetched_at FROM cache WHERE cache_key = ? AND expires_at > ?",
        (key, time.time()),
    ).fetchone()
    db.close()
    if row:
        return row["body"]
    return None


def cache_set(key: str, body: str, status_code: int = 200, ttl_seconds: int = 1800, etag: str = ""):
    """Store response in cache with TTL."""
    now = time.time()
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO cache (cache_key, body, status_code, fetched_at, expires_at, etag)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (key, body, status_code, now, now + ttl_seconds, etag),
    )
    db.commit()
    db.close()


def cache_clear():
    """Clear expired cache entries."""
    db = get_db()
    deleted = db.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),)).rowcount
    db.commit()
    db.close()
    return deleted


def article_upsert(art: dict) -> bool:
    """Insert or update article. Returns True if new, False if duplicate."""
    db = get_db()
    try:
        db.execute(
            """INSERT OR IGNORE INTO articles
               (id, source, title, url, description, date, date_wib, category, lang, filepath, wikilink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                art["id"],
                art["source"],
                art["title"],
                art["url"],
                art.get("description", ""),
                art["date"],
                art.get("date_wib", ""),
                art.get("category", "umum"),
                art.get("lang", "id"),
                art.get("filepath", ""),
                art.get("wikilink", ""),
            ),
        )
        db.commit()
        is_new = db.total_changes > 0
        db.close()
        return is_new
    except sqlite3.IntegrityError:
        db.close()
        return False


def article_exists(url: str) -> bool:
    """Check if article URL already stored."""
    db = get_db()
    row = db.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
    db.close()
    return row is not None


def get_articles(limit: int = 200, offset: int = 0) -> list[dict]:
    """Get articles for dashboard, newest first."""
    db = get_db()
    rows = db.execute(
        """SELECT id, source, title, url, description as excerpt,
                  date, date_wib, category, lang, filepath, wikilink
           FROM articles
           ORDER BY date DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_article_count() -> int:
    """Total article count."""
    db = get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM articles").fetchone()
    db.close()
    return row["cnt"] if row else 0


def get_today_count() -> int:
    """Article count for today."""
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM articles WHERE date LIKE ?", (f"{today}%",)
    ).fetchone()
    db.close()
    return row["cnt"] if row else 0


def get_source_stats() -> list[dict]:
    """Article count per source."""
    db = get_db()
    rows = db.execute(
        """SELECT source, COUNT(*) as count FROM articles
           GROUP BY source ORDER BY count DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_category_stats() -> list[dict]:
    """Article count per category."""
    db = get_db()
    rows = db.execute(
        """SELECT category, COUNT(*) as count FROM articles
           GROUP BY category ORDER BY count DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def log_fetch(source: str, count: int, status: str = "ok", error: str = ""):
    """Log a fetch event."""
    db = get_db()
    db.execute(
        "INSERT INTO fetch_log (source, fetched_at, article_count, status, error_msg) VALUES (?, ?, ?, ?, ?)",
        (source, datetime.now(WIB).isoformat(), count, status, error),
    )
    db.commit()
    db.close()


def get_last_fetch_times() -> dict:
    """Get last fetch time per source."""
    db = get_db()
    rows = db.execute(
        """SELECT source, MAX(fetched_at) as last_fetch
           FROM fetch_log WHERE status = 'ok'
           GROUP BY source"""
    ).fetchall()
    db.close()
    return {r["source"]: r["last_fetch"] for r in rows}


def get_latest_date() -> str:
    """Get latest article date."""
    db = get_db()
    row = db.execute("SELECT date FROM articles ORDER BY date DESC LIMIT 1").fetchone()
    db.close()
    return row["date"][:10] if row else "—"


def close():
    """Cleanup expired cache."""
    cache_clear()
