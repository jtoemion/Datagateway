#!/usr/bin/env python3
"""
Article metadata enrichment — section tagging, keyword extraction, entity recognition.

Usage:
    python3 scripts/enrich-metadata.py        # enrich all articles
    python3 scripts/enrich-metadata.py [id]   # enrich single article
"""

import sys
import re
import json
from collections import Counter
from pathlib import Path

# ── project local imports ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.database import (
    init_db, get_db, get_scraped_article,
    save_article_metadata, get_article_metadata,
)


# ── Section taxonomy ─────────────────────────────────────────────────────────

SECTION_KEYWORDS = {
    "POLITIK": [
        "presiden", "presiden prabowo", "pemerintah", "dpr", "dprd",
        "menteri", "kabinet", "partai", "politik", "pemilu", "pilkada",
        "koalisi", "oposisi", "voting", "sidang", "undang-undang", "uu",
        "peraturan pemerintah", "pp", "presidential", "executive", "legislative",
        "governor", "walikota", "bupati", "kemente", "raiban", "kpk",
        "hak angket", "interpelasi", "mosi tidak percaya", "impeachment",
        "mpr", "dpr", "dpd", "mk", "ky", "mahkamah", "hak", "uu cipta kerja",
        "omnibus", "revisi", "tnic", "pencalonan", "kandidat",
    ],
    "EKONOMI": [
        "ekonomi", "saham", "idx", "idx80", "inflasi", "rupiah", "dollar", "usd",
        "bank", "bjb", "bni", "bri", "btn", "mandiri", "bi rate", "suku bunga",
        "odb", "ocr", "g20", "freeport", "neraca perdagangan", "ekspor", "impor",
        "cadangan devisa", "dbnc", "pemda", "apbd", "apbn", "belanja negara",
        "pajak", "ppn", "pph", "pttp", "penerimaan negara", "defisit",
        "investor", "investasi", "green bond", "sbn", "obligasi", "surat utang",
        "kredit", "kpr", "kmm", "umkm", "kmnp", "korporasi", "indu", "industri",
        " Pertambangan", "batubara", "emas", "n kel", "agr", "migas", "cpo",
        "kakao", "kopi", "sawit", "property", "real estat", "btn", "wika",
        "pt unilever", "unilever", "adaro", "sinar mas", "sampoerna", "gudang garam",
        "bUMN", "swasta", "fta", "wto", "bpom", "food", "minuman", "farmasi",
        "phs", "ksehatan", "textil", "aviation", "pariwisata", "transportasi",
        "logistik", "startup", "unicorn", "decacorn", "fintech", "crypto", "bitcoin",
        " blk", "lps", "ock", "freeport", "newmont", "antam", "timah",
    ],
    "TEKNOLOGI": [
        "teknologi", "digital", "internet", "software", "hardware", "ai",
        " kecerdasan buatan", "otomatisasi", "robot", "cyber", "siber",
        "data", "cloud", "server", " startup", " Unicorn", "app", "aplikasi",
        "platform", "e-commerce", " e-", "iot", "5g", "6g", "semiconductor",
        "chip", "processor", "nvidia", "amd", "intel", "apple", "google", "meta",
        "microsoft", "amazon", "tesla", "spacex", "openai", "chatgpt", "llm",
        "gensim", "transformer", "langchain", "big data", "analytics",
        "cybersecurity", "ransomware", "malware", "phishing", "hack", "breach",
        "developer", "programming", "python", "javascript", "java", "golang",
        "api", "sdk", "SaaS", "paas", "iaas", "devops", "agile",
    ],
    "OLAHRAGA": [
        "olahraga", "sepak bola", "bola", "basket", "voli", "renang",
        "atlet", "pial", "world cup", "cup", "liga", "champions", "premier",
        "serie", "la liga", "bundesliga", "league", "turnamen", "olimpiade",
        "sea games", "asi games", "asiad", "aff", "piala", "final",
        "gol", "score", "skor", "hasil", "pertandingan", "tim", "timnas",
        "indonesia", "persib", "persija", "arema", "pss", "psm", "persebaya",
        "bola dunia", "fifa", "pssi", "pSSI", "wasit", "offside", "var",
        "ferrari", "mclaren", "mercedes", "f1", "motogp", "tenis", "badminton",
        "bwf", "all england", "krl", "pb djarum", "jakarta", "surabaya",
    ],
    "HUKUM": [
        "hukum", "kriminal", "police", "polisi", "kejaksaan", "jaksa",
        "pengadilan", "hakim", "vonis", "pidana", "perdata", "pasal",
        "kpk", "ott", "suap", "gratifikasi", "penyuapan", "bribery", "corruption",
        "narkoba", "ngan", "ganja", "extasy", "fentanil", "penyelundupan",
        "perampokan", "pencurian", "pembunuhan", "penipuan", "scam", "hoax",
        "pencemaran nama baik", "defamation", "libel", "slander", "spam",
        "penyelewengan", "manipulasi", "fraud", "Money laundry", "TpPU",
        "terorisme", "extremism", "radikal", "_POL", "_ter", "_jih",
        "app", "app", "gacran", "g cac", "kejati", "kejaksaan tinggi",
        "poli", "mabes", "kepolisian", "polri", "tni", "adh", "pengadilan",
        "mk", "mahkamah konstitusi", "praperadilan", "gugatan", "class action",
    ],
    "INTERNASIONAL": [
        "internasional", "dunia", "global", "asing", "luar negeri", "foreign",
        "amerika serikat", "amerika", "as", "china", "cina", "tiongkok",
        "rusia", "ukraina", "eropa", "eropa", "asia", "asia tenggara",
        "australia", "jepang", "korea", "inggris", "prancis", "jerman",
        "brasil", "argentina", "mesir", "arab saudi", "saudi", "uni emirat",
        "india", "pakistan", "Afghanistan", "iran", "irak", "suriah", "palestina",
        "israel", "hamas", "hezbollah", " PBB", "UN", "NATO", "asean",
        "who", "WHO", "bank dunia", "imf", "IMF", "WTO", "WTO", "FAO",
        "summit", "g20", "g7", "bilateral", "multilateral", "diplomacy",
        "diplomat", "duta besar", "KJRI", "KBRI", "konsulat",
        "pengungsi", "refugee", "migrant", "black lives matter", "war",
        "conflict", "military", "army", "navy", "air force", "troops",
        "sanctions", "sanksi", "embargo", "trading war", "perang dagang",
    ],
    "KESEHATAN": [
        "kesehatan", "medical", "medis", "rumah sakit", "rsup", "rsud", "rs",
        "dokter", "dokter", "bidan", "perawat", "farmasi", "apotek", "obat",
        "vaccine", "vaksin", "sinovac", "astrazeneca", "pfizer", "moderna",
        "booster", "pandemi", "epidemi", "outbreak", "wabah", "covid", "covid-19",
        "flub", "kolera", "dbd", "demam berdarah", "tbc", "tuberculosis",
        "hiv", "aids", "malaria", "chikungunya", "gizi", "stunting", "obesitas",
        "diet", "nutrition", "herbal", "tradisional", "jamu", "suplemen", "vitamin",
        "BPJS", "bpjs", "asuransi", "rumah sakit", "klinik", "puskesmas",
        "mental health", "depresi", "stres", "anxiety", "schizophrenia",
        "cancer", "kanker", "tumor", "diabetes", "jantung", "stroke", "cardiac",
        "kidney", "ginjal", "liver", "hati", "paru", "pulmon", "eye", "mata",
        "dental", "gigi", "ortopedi", "beds", "ICU", "ICC", "operasi", "surgery",
        "transplant", "donor", "darah", "blood", "stem cell", "sel punca",
    ],
    "PENDIDIKAN": [
        "pendidikan", "sekolah", "sd", "smp", "sma", "smk", "ptn", "pts",
        "universitas", "universitas", "university", "uin", "itb", "ui", "ugm",
        "ipb", "undip", "unpad", "unair", "ITS", "telkom", "、工艺",
        "guru", "dosen", "murid", "siswa", "mahasiswa", "pendidik",
        "kampus", "fakultas", "jurusan", "prodi", "akreditasi", "ban-pt",
        "beasiswa", "lang", "bidikmisi", "proret", "kinian", "kompete",
        "ajar", "ajar", "belajar", "pembelajaran", "kurikulum", "k13", "kemerdekaan belajar",
        "ujian", "unas", "utbk", "snbt", "snpm", "snmptn", "seleksi",
        "naik kelas", "lulus", "wisuda", "ijazah", "diploma", "sarjana",
        "magister", "doktor", "postgraduate", "research", "penelitian",
        "sitasi", "jurnal", "conference", "seminar", "webinar", "workshop",
        "Mooc", "online learning", "digital learning", "edtech",
    ],
    "LINGKUNGAN": [
        "lingkungan", "iklim", "climate", "global warming", "pemanasan global",
        "emisi", "carbon", "karbon", "co2", "gas rumah kaca", "greenhouse",
        "polusi", "polusi air", "polusi udara", "lind", " asap", "smog",
        "deforestasi", "hutan", "gundul", "illegal logging", "penebangan liar",
        "flash flood", "banjir", " Tanah Longsor", "gempa", "tsunami",
        "自然灾害", "cuaca ekstrem", "kemarau", "kekeringan", "el nino",
        "la nina", "strain", "acidification", "coral", "terumbu karang",
        "bleaching", "bahari", "laut", "samudera", "maritime", "fishing",
        "overfishing", "illegal fishing", "penangkapan ikan ilegal",
        "plastic pollution", "sampah plastik", "microplastic", "daur ulang",
        "recycling", "waste", "limbah", "toxic", "b3", "bahan berbahaya",
        "keanekaragaman hayati", "biodiversity", "es", "glacier", "ice cap",
        "endangered", "langka", "penyu", "orang utan", "fauna", "flora",
        "ekosistem", "tropical rainforest", "hutan hujan tropis", "kalimantan",
        "sumatera", "papua", "borneo", "sumatra", "rafflesia", "komodo",
    ],
    "BUDAYA": [
        "budaya", "cultural", "seni", "art", "museum", "galeri", "ekspresi",
        "tradisi", "adat", "_UPacara", "ritual", "hari besar", "national holiday",
        " Hari Raya", "idul fitri", "idul adha", "lebaran", "natal", "tahun baru",
        "waisak", "nyepi", "garb", "sedekah", "祭祀", "节日",
        "musik", "music", "lagu", "song", "konser", "concert", "festival",
        "film", "movie", "bioskop", "cinema", "drama", "teater", "teatre",
        "dance", "tari", "balet", "koreografi", "folk", "tradisional",
        "sastra", "literature", "buku", "novel", "cerpen", "puisi", "pantun",
        "bahasa", "language", "linguistic", "dialek", "javanese", "sunda",
        "batak", "minang", "bugis", "dayak", "papua", "asmat", "merah putih",
        " heritage", "cagar budaya", "heritage site", "monumen", "monument",
        "candi", "temple", " pura", "mesjid", "gereja", "church", "vihara",
        "pagoda", "langgar", "surau", "tourism", "pariwisata", "cultural tourism",
        "warisan dunia", "UNESCO", "angkasa", "space", "antariksa", "bintang",
        "zodiac", "rasi", "galaxy", "bimasakti", "universe", "kosmos",
        "fashion", "mode", "gaya hidup", "lifestyle", "kuliner", "food culture",
        "masakan", "resep", "挽回了", "ramen", "sushi", "martabak", "rendang",
        " Gudeg", "sate", "rendang", "rawon", "soto", "papeda", "cenil",
        "fashion", "OOTD", "clothing", "batik", "tenun", "songket", "kain",
    ],
}


# ── Synonym map ───────────────────────────────────────────────────────────────

SYNONYM_MAP = {
    # Countries / regions
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
    # Indonesian political terms
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
    # Institutions
    "MPR": ["Majelis Permusyawaratan Rakyat"],
    "DPR": ["Dewan Perwakilan Rakyat"],
    "DPRD": ["DPRD Provinsi", "DPRD Kota", "DPRD Kabupaten"],
    "MK": ["Mahkamah Konstitusi"],
    "KY": ["Komisi Yudisial"],
    "MA": ["Mahkamah Agung"],
    "KPK": ["Komisi Pemberantasan Korupsi"],
    "BMKG": ["Badan Meteorologi Klimatologi dan Geofisika"],
    "BUMN": ["Badan Usaha Milik Negara"],
    "BPJS": ["BPJS Kesehatan", "BPJS Ketenagakerjaan"],
    "BNN": ["Badan Narkotika Nasional"],
    "BNPT": ["Badan Nasional Penanggulangan Terorisme"],
    "POLRI": ["Kepolisian Republik Indonesia"],
    "TNI": ["Tentara Nasional Indonesia"],
    # Money / finance
    "US$": ["dollar AS", "dolar AS", "US dollar", "USD"],
    "Rp": ["Rupiah", "IDR"],
    "Rp T": ["Rupiah Triliunan", "triliunan rupiah"],
    "Rp M": ["Rupiah Miliaran", "miliaran rupiah"],
}


# ── Keyword extraction ─────────────────────────────────────────────────────────

STOPWORDS = {
    "yang", "dan", "di", "dengan", "untuk", "pada", "adalah", "ini", "itu",
    "tersebut", "dari", "dalam", "tidak", "ke", "akan", "sudah", "oleh",
    "atau", "juga", "ada", "masih", "hanya", "lebih", "serta", "bisa",
    "karena", "saat", "sebagai", "namun", "tetapi", "jika", "tentang",
    "setelah", "melalui", "antara", "bagi", "hal", "kondisi", "dalam",
    "depan", "belakang", "atas", "bawah", "sebelah", "samping", "luar",
    "dalam", "antara", "pihak", "各样的", "demi", "guna", "untuk", "bp",
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
    "kak", "pak", "bu", "yang", "yg", "dgn", "di", "dr", "ke", "kt",
}


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract top-N keywords using simple TF scoring."""
    # Lowercase, strip punctuation, split
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = cleaned.split()
    # Filter stopwords and short tokens
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 3]
    if not tokens:
        return []
    counts = Counter(tokens)
    # Boost bigrams
    bigrams = [" ".join(tokens[i:i+2]) for i in range(len(tokens)-1)
               if tokens[i] not in STOPWORDS and tokens[i+1] not in STOPWORDS]
    bg_counts = Counter(bigrams)
    # Combine scores
    all_scores: dict[str, float] = {}
    for word, cnt in counts.items():
        all_scores[word] = cnt * 1.0
    for bg, cnt in bg_counts.items():
        all_scores[bg] = all_scores.get(bg, 0) + cnt * 1.5
    # Sort and return top_n
    sorted_words = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def extract_entities(text: str) -> list[str]:
    """Extract named entities using regex patterns."""
    entities = []
    # Capitalized multi-word names (Indonesian pattern: "Nama Nama")
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}\b", text):
        ent = match.group().strip()
        if len(ent) > 4 and ent not in STOPWORDS:
            entities.append(ent)
    # All-caps abbreviations (2-5 chars)
    for match in re.finditer(r"\b[A-Z]{2,5}\b", text):
        ent = match.group()
        if ent not in {"DI", "DII", "TV", "RS", "RSUP", "RSUD", "PLN", "BIM"}:
            entities.append(ent)
    # Unique, return top 20
    seen = set()
    unique = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique[:20]


def detect_sections(text: str) -> list[str]:
    """Detect which sections apply to an article based on keyword matching."""
    text_lower = text.lower()
    found = []
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(f"[{section}]")
                break
    return found


def enrich_article(article_id: str, scraped: dict | None = None) -> dict:
    """Enrich a single article with metadata."""
    if scraped is None:
        scraped = get_scraped_article(article_id)

    if scraped is None:
        return {}

    full_text = scraped.get("full_text") or scraped.get("full_html") or ""
    # Strip HTML tags from full_html if full_text is empty
    if not full_text and scraped.get("full_html"):
        from bs4 import BeautifulSoup
        full_text = BeautifulSoup(scraped["full_html"], "lxml").get_text(
            separator=" ", strip=True
        )

    word_count = len(full_text.split())
    keywords = extract_keywords(full_text)
    entities = extract_entities(full_text)
    sections = detect_sections(full_text)

    save_article_metadata(article_id, sections, keywords, entities, word_count)

    return {
        "article_id": article_id,
        "sections": sections,
        "keywords": keywords,
        "entities": entities,
        "word_count": word_count,
    }


def main():
    init_db()

    if len(sys.argv) > 1:
        article_id = sys.argv[1]
        print(f"Enriching single article: {article_id}")
        result = enrich_article(article_id)
        if result:
            print(f"  ✓ sections={result['sections']}")
            print(f"  ✓ keywords={result['keywords'][:5]}...")
            print(f"  ✓ word_count={result['word_count']}")
        else:
            print(f"  ✗ No data for {article_id}")
        return

    # Enrich all
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.title, s.full_text, s.full_html
        FROM articles a
        LEFT JOIN scraped_articles s ON a.id = s.article_id
        LEFT JOIN article_metadata m ON a.id = m.article_id
        WHERE m.article_id IS NULL
        ORDER BY a.date DESC
    """).fetchall()
    db.close()

    total = len(rows)
    if total == 0:
        print("All articles already enriched.")
        return

    print(f"Found {total} articles to enrich.\n")
    for i, row in enumerate(rows, 1):
        article_id = row["id"]
        title = (row["title"] or "")[:60]
        scraped = None
        if row["id"]:
            scraped = get_scraped_article(row["id"])
        result = enrich_article(article_id, scraped)
        secs = result.get("sections", [])
        kw = result.get("keywords", [])
        print(f"[{i}/{total}] {article_id} | {secs} | {kw[:3]} | {title}...")

    print(f"\n✓ Enriched {total} articles.")


if __name__ == "__main__":
    main()
