#!/usr/bin/env python3
"""
Datagateway — Auto Metadata Generator
Auto-detect new/unenriched articles and generate metadata (sections, keywords,
entities, word count, reading time). Can run as one-shot, pipeline-integrated,
or as a file watcher.

Usage:
  python3 scripts/auto-meta.py                  # Enrich all missing
  python3 scripts/auto-meta.py --watch          # Watch for new .md files
  python3 scripts/auto-meta.py --pipeline       # Pipeline mode (quiet)
  python3 scripts/auto-meta.py <article_id>     # Single article
"""

import json
import os
import re
import sys
import time
import hashlib
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

WIB = timezone(timedelta(hours=7))
REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT))
from scripts.database import get_db, get_article_metadata, save_article_metadata


# ── Section keywords ──────────────────────────────────────────────────────────

SECTION_MAP = {
    "POLITIK": [
        "presiden", "prabowo", "jokowi", "dpr", "mpr", "kpk", "pemerintah",
        "kabinet", "menteri", "gubernur", "bupati", "walikota", "pilkada",
        "pemilu", "partai", "koalisi", "oposisi", "fraksi", "sidang",
        "undang-undang", "uu", "konstitusi", "amendemen", "politik",
        "demo", "unjuk rasa", "kebijakan", "anggaran", "apbn", "apbd",
    ],
    "EKONOMI": [
        "ekonomi", "inflasi", "saham", "rupiah", "dolar", "pasar modal",
        "bank", "bumn", "biz", "bisnis", "investasi", "ekspor", "impor",
        "pajak", "neraca", "defisit", "utang", "cadangan devisa",
        "kurs", "valas", "obligasi", "sukuk", "reksadana", "finansial",
        "asuransi", "kpr", "kredit", "pinjaman", "likuiditas",
        "lab bersih", "pendapatan", "omzet", "produsen", "konsumen",
    ],
    "TEKNOLOGI": [
        "teknologi", "digital", "AI", "kecerdasan buatan", "robot",
        "aplikasi", "software", "hardware", "chip", "semikonduktor",
        "startup", "unicorn", "decacorn", "blockchain", "kripto",
        "bitcoin", "cyber", "siber", "keamanan siber", "data center",
        "cloud", "komputer", "smartphone", "gadget", "5g", "internet",
        "platform", "e-commerce", "fintech", "iot", "machine learning",
        "big data", "metaverse", "vr", "ar", "automasi",
    ],
    "OLAHRAGA": [
        "olahraga", "sepak bola", "football", "piala dunia", "world cup",
        "ligue", "epl", "premier league", "liga", "champions league",
        "bulutangkis", "badminton", "bulu tangkis", "tinju", "boxing",
        "mma", "ufc", "moto gp", "moto3", "motogp", "f1", "formula 1",
        "basket", "nba", "ibl", "voli", "volleyball", "atletik",
        "olimpiade", "asian games", "sea games", "atlet", "pelatih",
        "stadion", "gol", "skor", "pertandingan", "turnamen",
        "timnas", "garuda", "pelatnas", "pencak silat",
    ],
    "HUKUM": [
        "hukum", "pidana", "perdata", "tata negara", "tipikor",
        "korupsi", "suap", "gratifikasi", "money laundering",
        "pencucian uang", "narkoba", "narkotika", "psikotropika",
        "terorisme", "radikalisme", "kekerasan", "kriminal",
        "kejahatan", "tindak pidana", "vonis", "hukuman", "denda",
        "penjara", "sel", "tahanan", "tersangka", "terdakwa",
        "terpidana", "jaksa", "hakim", "pengadilan", "putusan",
        "banding", "kasasi", "grasi", "amnesti", "aborsi",
    ],
    "INTERNASIONAL": [
        "internasional", "dunia", "global", "asing", "mancanegara",
        "PBB", "UN", "NATO", "WTO", "IMF", "bank dunia", "world bank",
        "perang", "konflik", "invasi", "sanksi", "embargo",
        "diplomasi", "kedutaan", "duta besar", "perjanjian",
        "kerjasama internasional", "hubungan bilateral",
        "amerika", "china", "tiongkok", "rusia", "ukraina",
        "eropa", "asia", "timur tengah", "afrika",
        "pengungsi", "krisis kemanusiaan", "perdamaian",
    ],
    "KESEHATAN": [
        "kesehatan", "rumah sakit", "rs", "puskesmas", "dokter",
        "perawat", "pasien", "obat", "vaksin", "imunisasi",
        "covid", "pandemi", "epidemi", "wabah", "penyakit",
        "demam", "gejala", "diagnosis", "pengobatan", "terapi",
        "operasi", "bedah", "gizi", "nutrisi", "kalori",
        "stunting", "ASI", "imt", "obesitas", "diabetes",
        "hipertensi", "jantung", "kanker", "stroke", "mental",
        "bpjs", "jaminan kesehatan", "rumah sakit jiwa",
    ],
    "PENDIDIKAN": [
        "pendidikan", "sekolah", "madrasah", "pesantren", "kampus",
        "universitas", "univ", "institut", "sekolah tinggi",
        "siswa", "mahasiswa", "pelajar", "guru", "dosen",
        "beasiswa", "kurikulum", "ujian", "SNBP", "SNBT",
        "PPDB", "spp", "bantuan pendidikan", "perpustakaan",
        "laboratorium", "riset", "penelitian", "akademik",
        "sekolah rakyat", "putus sekolah", "buta huruf",
    ],
    "LINGKUNGAN": [
        "lingkungan", "alam", "hutan", "laut", "sungai", "danau",
        "polusi", "pencemaran", "limbah", "sampah", "plastik",
        "daur ulang", "recycle", "karbon", "emisi", "gas rumah kaca",
        "pemanasan global", "climate change", "perubahan iklim",
        "green", "hijau", "ekosistem", "biodiversitas",
        "hewan", "satwa", "flora", "fauna", "konservasi",
        "bencana alam", "gempa", "tsunami", "banjir", "longsor",
        "kekeringan", "cuaca ekstrem", "gunung meletus",
    ],
    "BUDAYA": [
        "budaya", "seni", "musik", "film", "drama", "teater",
        "tari", "tarian", "wayang", "batik", "kain tradisional",
        "lagu daerah", "kesenian", "sastra", "puisi", "novel",
        "pameran", "festival", "konser", "pertunjukan",
        "museum", "cagar budaya", "warisan budaya",
        "tradisi", "adat", "upacara", "ritual", "kerajinan",
        "kuliner", "makanan tradisional", "wisata budaya",
    ],
}

# ── Synonym map ───────────────────────────────────────────────────────────────

SYNONYM_MAP = {
    "AS": ["amerika serikat", "united states", "usa", "america"],
    "RI": ["indonesia", "republik indonesia", "negara indonesia"],
    "Prabowo": ["presiden prabowo", "prabowo subianto", "menhan"],
    "Jokowi": ["joko widodo", "presiden joko widodo", "presiden jokowi"],
    "DPR": ["dewan perwakilan rakyat", "parlemen"],
    "KPK": ["komisi pemberantasan korupsi", "anti korupsi"],
    "POLRI": ["kepolisian republik indonesia", "polisi", "kepolisian"],
    "TNI": ["tentara nasional indonesia", "militer", "angkatan"],
    "BMKG": ["badan meteorologi klimatologi geofisika", "meteorologi"],
    "BUMN": ["badan usaha milik negara", "perusahaan negara"],
    "BPJS": ["bpjs kesehatan", "bpjs ketenagakerjaan", "jaminan sosial"],
    "PLN": ["perusahaan listrik negara", "listrik"],
    "Pertamina": ["minyak dan gas", "migas", "bbm"],
    "WHO": ["world health organization", "organisasi kesehatan dunia"],
    "PBB": ["perserikatan bangsa bangsa", "united nations"],
    "IMF": ["international monetary fund", "dana moneter internasional"],
    "NATO": ["north atlantic treaty organization", "pakta pertahanan"],
    "EU": ["european union", "uni eropa"],
    "ASEAN": ["association of southeast asian nations", "perbara"],
    "Piala Dunia": ["world cup", "piala dunia fifa"],
    "UCL": ["champions league", "liga champions"],
}


# ── Stopwords ─────────────────────────────────────────────────────────────────

STOPWORDS_ID = {
    "yang", "dan", "di", "dengan", "untuk", "pada", "adalah", "ini", "itu",
    "tersebut", "dari", "dalam", "tidak", "ke", "akan", "sudah", "oleh",
    "atau", "juga", "ada", "masih", "hanya", "lebih", "serta", "bisa",
    "karena", "saat", "sebagai", "namun", "tetapi", "jika", "tentang",
    "setelah", "melalui", "antara", "bagi", "hal", "kondisi", "setiap",
    "depan", "belakang", "atas", "bawah", "pihak", "demi", "guna",
    "the", "and", "that", "for", "with", "from", "have", "been", "being",
    "would", "could", "should", "may", "might", "shall", "can", "will",
}

IMPORTANT_BIGRAMS = {
    "pemerintah indonesia", "presiden prabowo", "presiden jokowi",
    "piala dunia", "tahun 2026", "tahun ini", "amerika serikat",
    "indonesia timur", "jakarta pusat", "jakarta utara", "jakarta selatan",
    "jakarta barat", "jakarta timur", "jawa barat", "jawa timur",
    "jawa tengah", "sumatera utara", "sumatera selatan",
    "kalimantan timur", "sulawesi selatan", "papua barat",
    "maluku utara", "nusa tenggara barat", "nusa tenggara timur",
    "bank indonesia", "kementerian keuangan", "kementerian",
    "sekretariat negara", "istana negara", "komisi pemberantasan",
    "pencak silat", "sepak bola", "bulu tangkis", "moto gp",
    "liga inggris", "liga italia", "liga spanyol", "liga jerman",
    "kejaksaan agung", "mahkamah agung", "mahkamah konstitusi",
    "badan usaha", "usaha mikro", "kecil menengah", "umkm",
}


def clean_text(text: str) -> str:
    """Remove HTML, normalize whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_sections(text: str) -> list[str]:
    """Detect article sections by keyword matching."""
    text_lower = text.lower()
    text_len = len(text_lower.split())
    if text_len < 10:
        return []

    scored = {}
    for section, keywords in SECTION_MAP.items():
        score = 0
        for kw in keywords:
            count = text_lower.count(kw.lower())
            if count > 0:
                score += count * (3 if len(kw.split()) > 1 else 1)
        if score > 0:
            scored[section] = score

    # Return sections with score above threshold, sorted by relevance
    threshold = max(1, text_len / 200)
    result = [s for s, sc in sorted(scored.items(), key=lambda x: -x[1]) if sc >= threshold]
    return [f"[{s}]" for s in result[:5]]


def extract_keywords(text: str, max_kw: int = 10) -> list[str]:
    """Extract keywords using TF-based scoring + bigram boosting."""
    text = clean_text(text)
    words = text.lower().split()
    if len(words) < 10:
        return []

    # Unigrams
    unigrams = [w.strip(".,!?\"'();:[]{}") for w in words]
    unigrams = [w for w in unigrams if len(w) > 2 and w not in STOPWORDS_ID and not w.isdigit()]

    # Bigrams
    bigrams = [f"{unigrams[i]} {unigrams[i+1]}" for i in range(len(unigrams)-1)]

    # Score
    freq = Counter(unigrams)
    bigram_freq = Counter(b for b in bigrams if b in IMPORTANT_BIGRAMS or len(b.split()) == 2)

    # Boost bigrams
    for bg, cnt in bigram_freq.items():
        for w in bg.split():
            if w in freq:
                freq[w] += cnt

    # Get top keywords, try to include meaningful bigrams
    top_unigrams = [w for w, _ in freq.most_common(20) if len(w) > 2][:8]
    top_bigrams = [bg for bg, _ in bigram_freq.most_common(10)][:4]

    # Merge interleaving: bigrams first, then unigrams, dedup
    result = []
    seen = set()
    for bg in top_bigrams:
        if bg not in seen:
            result.append(bg)
            seen.add(bg)
    for w in top_unigrams:
        if w not in seen:
            result.append(w)
            seen.add(w)

    return result[:max_kw]


def extract_entities(text: str) -> list[str]:
    """Extract known entities using synonym map."""
    text_lower = text.lower()
    found = []
    for entity, aliases in SYNONYM_MAP.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                found.append(entity)
                break
    return found


def enrich_article(article_id: str, title: str = "", description: str = "",
                   full_text: str = "", full_html: str = "") -> dict:
    """Enrich a single article with metadata."""
    text = full_text or description or title
    if full_html and not full_text:
        text = clean_text(full_html)

    sections = extract_sections(text)
    keywords = extract_keywords(text)
    entities = extract_entities(text)
    word_count = len(text.split()) if text else 0
    reading_time = max(1, round(word_count / 200))

    data = {
        "sections": sections,
        "keywords": keywords,
        "entities": entities,
        "word_count": word_count,
        "reading_time": reading_time,
    }

    save_article_metadata(article_id, sections, keywords, entities, word_count)
    return data


def enrich_all_missing(silent: bool = False) -> int:
    """Enrich all articles missing metadata. Returns count."""
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.title, a.description, s.full_text, s.full_html
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        LEFT JOIN article_metadata m ON a.id = m.article_id
        WHERE m.article_id IS NULL
    """).fetchall()
    db.close()

    count = 0
    for row in rows:
        art = row["id"]
        title = row["title"] or ""
        desc = row["description"] or ""
        full_text = row["full_text"] or ""
        full_html = row["full_html"] or ""
        enrich_article(art, title, desc, full_text, full_html)
        count += 1
        if not silent:
            print(f"  [{count}] {art[:12]} enriched")

    if not silent:
        print(f"  → {count} articles enriched")
    return count


def watch_news(directory: Path = None, interval: int = 60):
    """Watch news/ directory for new .md files and auto-enrich."""
    if directory is None:
        directory = REPO_ROOT / "news"

    print(f"Watching {directory} for new articles (interval={interval}s)...")
    seen = set()
    for f in directory.rglob("*.md"):
        seen.add(f.name)

    try:
        while True:
            new_files = []
            for f in directory.rglob("*.md"):
                if f.name not in seen:
                    new_files.append(f)
                    seen.add(f.name)

            for f in new_files:
                art_id = f.stem.split("_")[0]
                print(f"  New: {f.name}")
                enrich_article(art_id)
                print(f"    ✓ enriched")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Watcher stopped.")


def main():
    if "--watch" in sys.argv:
        watch_news()
        return

    if "--pipeline" in sys.argv:
        count = enrich_all_missing(silent=True)
        print(f"auto-meta: {count} enriched")
        return

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        art_id = sys.argv[1]
        print(f"Enriching {art_id}...")
        result = enrich_article(art_id)
        print(f"  sections: {result['sections']}")
        print(f"  keywords: {result['keywords'][:5]}")
        print(f"  entities: {result['entities'][:5]}")
        print(f"  words: {result['word_count']} (~{result['reading_time']} min)")
        return

    # Default: enrich all missing
    print(f"Auto Metadata Generator — {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}")
    print("=" * 50)
    enrich_all_missing()


if __name__ == "__main__":
    main()
