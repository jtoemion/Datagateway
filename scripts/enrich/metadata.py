"""
Datagateway — Enrich Metadata (CODE)
Full-text article enrichment: sections, keywords, entities, word_count, reading_time.
Import from taxonomy.SECTION_KEYWORDS; zero lateral imports.
"""

import re
from collections import Counter

from scripts.database import (
    get_scraped_article,
    save_article_metadata,
)

# Synonym map for entity extraction (canonical, merged from both sources)
SYNONYM_MAP = {
    "AS": ["Amerika Serikat", "United States", "USA", "U.S.", "America"],
    "RI": ["Indonesia", "Republik Indonesia", "NKRI"],
    "UK": ["Inggris", "United Kingdom", "Britain", "Great Britain", "GB"],
    "UAE": ["Uni Emirat Arab", "United Arab Emirates", "Emirat", "Dubai"],
    "Korsel": ["Korea Selatan", "South Korea", "ROK"],
    "Korut": ["Korea Utara", "North Korea", "DPRK"],
    "RRT": ["Republik Rakyat Tiongkok", "China", "Tiongkok", "PRC"],
    "Jep": ["Jepang", "Japan"],
    "Aus": ["Australia"],
    "NZ": ["New Zealand", "Selandia Baru"],
    "Pak": ["Pakistan"],
    "Afg": ["Afghanistan"],
    "Mes": ["Mesir", "Egypt"],
    "Iran": ["Iran", "Persia"],
    "Irak": ["Irak", "Iraq"],
    "Suriah": ["Siria", "Syria"],
    "Myanmar": ["Burma", "Mianmar"],
    "Prabowo": ["Presiden Prabowo", "Prabowo Subianto", "Menhan", "Menanti"],
    "Gibran": ["Gibran Rakabuming", "Wapres", "Wakil Presiden"],
    "Mega": ["Megawati", "Megawati Sukarnoputri", "Ketua Umum PDI-P", "PDI-P"],
    "SBY": ["Susilo Bambang Yudhoyono", "SBY", "President SBY"],
    "Jkw": ["Joko Widodo", "Jokowi", "President Jokowi"],
    "PDIP": ["PDI-P", "PDI Perjuangan", "Partai Demokrasi Indonesia Perjuangan"],
    "Golkar": ["Partai Golkar", "Golkar"],
    "Gerindra": ["Partai Gerinda", "Gerindra"],
    "Nasdem": ["Partai NasDem", "NasDem"],
    "PKS": ["Partai Keadilan Sejahtera", "PKS"],
    "PKB": ["Partai Kebangkitan Bangsa", "PKB"],
    "PAN": ["Partai Amanat Nasional", "PAN"],
    "Demokrat": ["PD", "Partai Demokrat"],
    "PPP": ["Partai Persatuan Pembangunan", "PPP"],
    "B": ["Partai Bulan Bintang", "PBB"],
    "Hanura": ["Partai Hanura"],
    "Gar": ["Partai Gelombang Rakyat Indonesia", "Gelombang Rakyat", "Gar"],
    "MPR": ["Majelis Permusyawaratan Rakyat"],
    "DPR": ["Dewan Perwakilan Rakyat"],
    "DPRD": ["DPRD Provinsi", "DPRD Kota", "DPRD Kabupaten"],
    "MK": ["Mahakam Konstitusi"],
    "KY": ["Komisi Yudisial"],
    "MA": ["Mahakam Agung"],
    "KPK": ["Komisi Pemberantasan Korupsi"],
    "BMKG": ["Badan Meteorologi Klimatologi dan Geofisika"],
    "BUMN": ["Badan Usaha Milik Negara"],
    "BPJS": ["BPJS Kesehatan", "BPJS Ketenagakerjaan"],
    "BNN": ["Badan Narkotika Nasional"],
    "BNPT": ["Badan Nasional Penanggulangan Terorisme"],
    "POLRI": ["Kepolisian Republik Indonesia"],
    "TNI": ["Tentara Nasional Indonesia"],
    "US$": ["dollar AS", "dolar AS", "US dollar", "USD"],
    "Rp": ["Rupiah", "IDR"],
    "Rp T": ["Rupiah Triliunan", "triliunan rupiah"],
    "Rp M": ["Rupiah Miliaran", "miliaran rupiah"],
}

# Stopwords for keyword extraction
STOPWORDS = {
    "yang", "dan", "di", "dengan", "untuk", "pada", "adalah", "ini", "itu",
    "tersebut", "dari", "dalam", "tidak", "ke", "akan", "sudah", "oleh",
    "atau", "juga", "ada", "masih", "hanya", "lebih", "serta", "bisa",
    "karena", "saat", "sebagai", "namun", "tetapi", "jika", "tentang",
    "setelah", "melalui", "antara", "bagi", "hal", "kondisi", "dalam",
    "depan", "belakang", "atas", "bawah", "sebelah", "samping", "luar",
    "dalam", "antara", "pihak", "demi", "guna", "untuk",
    "the", "and", "of", "in", "to", "is", "that", "for", "on", "with",
    "as", "at", "by", "from", "or", "an", "be", "are", "was", "were",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall", "can",
    "this", "these", "those", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "he", "she", "him", "her", "his",
    "nya", "nan", "lah", "pun", "kah", "tah", "si", "ku", "mu", "eng",
    "yg", "dgn", "utk", "pd", "dlm", "tdk", "sdh", "bs", "jg", "krn",
    "sm", "ttg", "stlh", "mlui", "dr", "spy", "dgn", "pd", "jd", "knp",
    "dpt", "sprti", "blm", "sdg", "sm", "msh", "lgi", "byk", "km",
    "dia", "mereka", "kami", "kita", "anda", "para", "pak", "bu",
    "kak",
}

# Lazy import to avoid circular — imported here to use in this module only
# NOTE: do NOT import from other scripts/* modules in this CODE module


def _get_taxonomy():
    """Lazy import SECTION_KEYWORDS from taxonomy to keep this module as CODE."""
    from scripts.enrich.taxonomy import SECTION_KEYWORDS
    return SECTION_KEYWORDS


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract top-N keywords using simple TF scoring + bigram boosting."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = cleaned.split()
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 3]
    if not tokens:
        return []
    counts = Counter(tokens)
    bigrams = [
        " ".join(tokens[i : i + 2])
        for i in range(len(tokens) - 1)
        if tokens[i] not in STOPWORDS and tokens[i + 1] not in STOPWORDS
    ]
    bg_counts = Counter(bigrams)
    all_scores: dict[str, float] = {}
    for word, cnt in counts.items():
        all_scores[word] = cnt * 1.0
    for bg, cnt in bg_counts.items():
        all_scores[bg] = all_scores.get(bg, 0) + cnt * 1.5
    sorted_words = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def extract_entities(text: str) -> list[str]:
    """Extract named entities using regex patterns."""
    entities = []
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", text):
        ent = match.group().strip()
        if len(ent) > 4 and ent not in STOPWORDS:
            entities.append(ent)
    for match in re.finditer(r"\b[A-Z]{2,5}\b", text):
        ent = match.group()
        if ent not in {"DI", "DII", "TV", "RS", "RSUP", "RSUD", "PLN", "BIM"}:
            entities.append(ent)
    seen = set()
    unique = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique[:20]


def detect_sections(text: str) -> list[str]:
    """Detect which sections apply based on keyword matching."""
    SECTION_KEYWORDS = _get_taxonomy()
    text_lower = text.lower()
    found = []
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(f"[{section}]")
                break
    return found


def enrich_article(article_id: str, scraped: dict | None = None) -> dict:
    """
    Enrich a single article with full-text metadata.
    Returns {sections, keywords, entities, word_count, reading_time}.
    """
    if scraped is None:
        scraped = get_scraped_article(article_id)

    if scraped is None:
        return {}

    full_text = scraped.get("full_text") or scraped.get("full_html") or ""
    if not full_text and scraped.get("full_html"):
        from bs4 import BeautifulSoup

        full_text = BeautifulSoup(scraped["full_html"], "lxml").get_text(
            separator=" ", strip=True
        )

    word_count = len(full_text.split())
    keywords = extract_keywords(full_text)
    entities = extract_entities(full_text)
    sections = detect_sections(full_text)
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
