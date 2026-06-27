"""
Datagateway — Auto Enrich (CODE)
Title/description-only enrichment for articles without full scraped text.
Import from taxonomy.SECTION_KEYWORDS; zero lateral imports.
"""

import re
from collections import Counter

from scripts.database import save_article_metadata

# Section map (simplified for title+desc context)
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

# Synonym map for entity extraction
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
    "kejaksaan agung", "mahakam agung", "mahakam konstitusi",
    "badan usaha", "usaha mikro", "kecil menengah", "umkm",
}


def _clean_text(text: str) -> str:
    """Remove HTML, normalize whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
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

    threshold = max(1, text_len / 200)
    result = [s for s, sc in sorted(scored.items(), key=lambda x: -x[1]) if sc >= threshold]
    return [f"[{s}]" for s in result[:5]]


def extract_keywords(text: str, max_kw: int = 10) -> list[str]:
    """Extract keywords using TF scoring + bigram boosting."""
    text = _clean_text(text)
    words = text.lower().split()
    if len(words) < 10:
        return []

    unigrams = [w.strip(".,!?\"'();:[]{}/\\") for w in words]
    unigrams = [w for w in unigrams if len(w) > 2 and w not in STOPWORDS_ID and not w.isdigit()]

    bigrams = [f"{unigrams[i]} {unigrams[i+1]}" for i in range(len(unigrams) - 1)]

    freq = Counter(unigrams)
    bigram_freq = Counter(b for b in bigrams if b in IMPORTANT_BIGRAMS or len(b.split()) == 2)

    for bg, cnt in bigram_freq.items():
        for w in bg.split():
            if w in freq:
                freq[w] += cnt

    top_unigrams = [w for w, _ in freq.most_common(20) if len(w) > 2][:8]
    top_bigrams = [bg for bg, _ in bigram_freq.most_common(10)][:4]

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


def enrich_article(
    article_id: str,
    title: str = "",
    description: str = "",
    full_text: str = "",
    full_html: str = "",
) -> dict:
    """
    Enrich a single article from title/description only.
    Used for articles that haven't been scraped yet.
    Returns {sections, keywords, entities, word_count, reading_time}.
    """
    text = full_text or description or title
    if full_html and not full_text:
        text = _clean_text(full_html)

    sections = extract_sections(text)
    keywords = extract_keywords(text)
    entities = extract_entities(text)
    word_count = len(text.split()) if text else 0
    reading_time = max(1, round(word_count / 200))

    save_article_metadata(article_id, sections, keywords, entities, word_count)

    return {
        "article_id": article_id,
        "sections": sections,
        "keywords": keywords,
        "entities": entities,
        "word_count": word_count,
        "reading_time": reading_time,
    }
