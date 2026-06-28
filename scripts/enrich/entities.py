"""
Datagateway — Entity Extraction (CODE)
Regex+seed+gazetteer NER. No LLM, no ML.
Input: article full_text + title + description
Output: list of RawEntity(surface_form, type, start_pos, end_pos)
"""

import re
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Boilerplate blacklist — UI/nav text scraped from article bodies ────────
ENTITY_BLACKLIST: set[str] = {
    # Republika boilerplate
    "Pilihan Redaksi", "Kantor Berita", "Ikuti Whatsapp Channel Republika",
    "Ikuti Whatsapp Channel", "Baca Juga", "Next Article", "Previous Article",
    "Republika Co Id", "Ikuti Kami",
    # Generic news UI
    "Read More", "Read Also", "Also Read", "Related News", "More Stories",
    "Breaking News", "Latest News", "Top Stories", "Editor Choice",
    "Share This", "Follow Us", "Subscribe Now",
}
_BLACKLIST_LOWER: set[str] = {s.lower() for s in ENTITY_BLACKLIST}

# Prefix tokens that indicate a team/org, not a person
_NON_PERSON_PREFIXES: set[str] = {
    "timnas", "klub", "partai", "tim", "pasukan", "satuan", "komando",
    "dirjen", "ditjen", "badan", "lembaga", "kementerian", "kemenko",
}

# ── EVENT seed terms ───────────────────────────────────────────────────────
EVENT_TERMS: set[str] = {
    # Indonesian politics / governance
    "Pemilu", "Pilkada", "Pilpres", "Pileg", "Muktamar", "Musyawarah Nasional",
    "Sidang Paripurna", "Rapat Kabinet", "KTT ASEAN", "KTT G20",
    # International summits / geopolitics
    "G20 Summit", "G7 Summit", "ASEAN Summit", "COP29", "COP30",
    "World Economic Forum", "Davos",
    # Sports events
    "Piala Dunia", "World Cup", "Piala Asia", "Asian Cup",
    "Olimpiade", "Olympic Games", "Paralympics",
    "Champions League", "Europa League", "Conference League",
    "Copa Libertadores", "Copa America", "AFCON",
    # Crises / conflicts
    "Konflik Gaza", "Gaza War", "Perang Ukraine", "Ukraine War",
    "Gempa Bumi", "Banjir Bandang", "Tsunami",
}
_EVENT_LOWER: dict[str, str] = {t.lower(): t for t in EVENT_TERMS}

# ── Title prefixes for person extraction ──────────────────────────────────
TITLE_PREFIXES = r"""(?i:
    Presiden|Wakil\s+Presiden|Menteri|Wakil\s+Menteri|Jenderal|Letjen|Mayjen|Brigjen|
    Kolonel|Letkol|Mayor|Kapten|Lettu|Serda|Serka|Pelda|
    Dr\.?|Prof\.?|H\.|Hj\.|Rektor|Dekan|Ketua|Wakil\s+Ketua|Sekretaris|
    Gubernur|Wakil\s+Gubernur|Bupati|Wakil\s+Bupati|Walikota|Wakil\s+Walikota|
    Senator|Anggota\s+DPR|PM|Prime\s+Minister|President|King|Queen|Prince|Princess|
    Sultan|Raja|Kanjeng|Sri|Paduka|Yang\s+Terhormat|Al-?Ustadz|Ustadz|Kyai|
    Habib|Syekh|Imam|Khatib|Suhu|Mahaguru|Bapak|Ibu|Saudara|Saudari
)"""

PERSON_PATTERN = re.compile(
    r'(?<!\w)(?:' + TITLE_PREFIXES + r'[ \t]+)?'  # Optional title
    r'[A-Z][a-z]+[ \t]+[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*'  # At least 2 capitalized words
    r'(?=\W|$)',
    re.UNICODE,
)

# ── Known ORG acronyms (uppercase 2-6 letter combos) ──────────────────────
ORG_ACRONYM_PATTERN = re.compile(r'\b([A-Z]{2,6})\b')

KNOWN_ORGS: set[str] = {
    "KPK", "DPR", "DPRD", "MPR", "MK", "KY", "MA", "BPK", "BPKP",
    "TNI", "POLRI", "BNN", "BRIN", "BPS", "BI", "OJK", "LPS", "KPU",
    "BASARNAS", "BMKG", "BNPB", "BPOM", "KKP", "KEMENKEU",
    "PSSI", "FIFA", "IOC", "WHO", "UNICEF", "UNHCR", "IMF", "ADB",
    "ASEAN", "EU", "NATO", "PBB", "G20", "G7", "OPEC",
    "MUI", "NU", "Muhammadiyah",
    "KAI", "PERTAMINA", "PLN", "TELKOM", "BRI", "MANDIRI", "BNI", "BJB", "BTN",
    "GOJEK", "TOKOPEDIA", "BUKALAPAK", "TRAVELOKA",
    "PDIP", "GOLKAR", "GERINDRA", "NASDEM", "PKS", "PKB", "DEMOKRAT", "PAN", "PPP",
    "PSI", "PERINDO",
}

# ── Static city/country gazetteer ──────────────────────────────────────────
PLACES: set[str] = {
    # Indonesia
    "Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Semarang",
    "Yogyakarta", "Denpasar", "Palembang", "Batam", "Pekanbaru",
    "Banjarmasin", "Manado", "Pontianak", "Balikpapan", "Mataram",
    "Padang", "Tangerang", "Bekasi", "Depok", "Bogor", "Malang",
    "Samarinda", "Solo", "Surakarta", "Cirebon", "Kediri", "Madiun",
    "Jayapura", "Ambon", "Kupang", "Ternate", "Sorong", "Merauke",
    # World capitals & major cities
    "Beijing", "Tokyo", "Seoul", "London", "Paris", "Berlin", "Rome",
    "Madrid", "Lisbon", "Moscow", "Washington DC", "Ottawa", "Canberra",
    "New Delhi", "Brasilia", "Buenos Aires", "Mexico City", "Cairo",
    "Riyadh", "Abu Dhabi", "Dubai", "Singapore", "Kuala Lumpur",
    "Manila", "Bangkok", "Hanoi", "Phnom Penh", "Vientiane", "Naypyidaw",
    "Colombo", "Dhaka", "Islamabad", "Tehran", "Baghdad", "Doha",
    "Kuwait City", "Muscat", "Sanaa", "Amman", "Beirut", "Ankara",
    "Istanbul", "Vienna", "Prague", "Warsaw", "Budapest", "Athens",
    "Stockholm", "Oslo", "Helsinki", "Copenhagen", "Brussels", "Amsterdam",
    "Zurich", "Geneva", "Dublin", "Edinburgh", "Jerusalem", "Tel Aviv",
    "Havana", "Caracas", "Lima", "Bogota", "Santiago", "Quito",
    "Nairobi", "Lagos", "Accra", "Cape Town", "Johannesburg", "Casablanca",
    # Countries
    "Indonesia", "Malaysia", "Singapore", "Thailand", "Vietnam", "Philippines",
    "Myanmar", "Cambodia", "Laos", "Brunei", "Timor Leste",
    "China", "Taiwan", "Japan", "South Korea", "North Korea", "India",
    "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan", "Maldives",
    "Saudi Arabia", "Iran", "Iraq", "Kuwait", "Oman", "Qatar",
    "United Arab Emirates", "Yemen", "Jordan", "Israel", "Palestine",
    "Turkey", "Syria", "Lebanon", "Afghanistan", "Turkmenistan",
    "United States", "Canada", "Mexico", "Brazil", "Argentina",
    "Chile", "Peru", "Colombia", "Venezuela", "Ecuador", "Bolivia",
    "Paraguay", "Uruguay", "Guyana", "Suriname",
    "United Kingdom", "France", "Germany", "Italy", "Spain",
    "Portugal", "Netherlands", "Belgium", "Switzerland", "Austria",
    "Poland", "Sweden", "Norway", "Denmark", "Finland", "Ireland",
    "Greece", "Hungary", "Czech Republic", "Romania", "Bulgaria",
    "Ukraine", "Russia", "Belarus", "Serbia", "Croatia",
    "Australia", "New Zealand", "Papua New Guinea", "Fiji",
    "Nigeria", "South Africa", "Egypt", "Kenya", "Ethiopia",
    "Ghana", "Morocco", "Algeria", "Tunisia", "Libya", "Sudan",
    "Cape Verde", "Senegal", "Angola", "Mozambique", "Tanzania",
}

# Concept terms from taxonomy sections (seed)
CONCEPT_TERMS: set[str] = {
    "Inflasi", "Defisit", "Neraca Perdagangan", "Suku Bunga", "APBN", "APBD",
    "Hak Angket", "Impeachment", "Omnibus Law", "Pemilu", "Pilkada",
    "Kecerdasan Buatan", "AI", "Blockchain", "Kripto", "Metaverse",
    "Stunting", "Vaksinasi", "Pandemi", "Emisi Karbon", "Net Zero",
    "Reformasi Birokrasi", "Korupsi", "Tindak Pidana Korupsi", "Money Laundering",
    "Terrorism", "Radicalism", "Pencucian Uang", "Tipikor",
}


def _make_entity_id(canonical: str) -> str:
    return "ent-" + hashlib.md5(canonical.lower().encode()).hexdigest()[:12]


def _is_noise(surface: str) -> bool:
    """Return True if surface is boilerplate, too long, or malformed."""
    s = surface.strip()
    s_lower = s.lower()
    # Exact blacklist match
    if s_lower in _BLACKLIST_LOWER:
        return True
    # Prefix match — catches "Pilihan Redaksi Detik", "Baca Juga ini", etc.
    if any(s_lower.startswith(bl) for bl in _BLACKLIST_LOWER):
        return True
    # Non-person prefix (team names, orgs mistakenly matched as persons)
    first_word = s_lower.split()[0] if s else ""
    if first_word in _NON_PERSON_PREFIXES:
        return True
    if len(s.split()) > 6:
        return True
    if not s[0].isupper():
        return True
    # Reject strings that contain HTML artifacts or special chars
    if re.search(r'[<>&/\\]', s):
        return True
    return False


def extract_entities(title: str, text: str, description: str = "") -> list[dict]:
    """
    Extract entities from article text.

    Returns list of dicts:
        {surface, type, canonical_guess, entity_id (tentative), start, end}
    """
    combined = f"{title}\n{description}\n{text}"
    entities: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()

    # 0. EVENT: seed term matching (highest priority — checked before PERSON)
    for term_lower, term_canonical in _EVENT_LOWER.items():
        for m in re.finditer(r'(?i)\b' + re.escape(term_canonical) + r'\b', combined):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            entities.append({
                "surface": term_canonical,
                "type": "EVENT",
                "canonical_guess": term_canonical,
                "entity_id": _make_entity_id(term_canonical),
                "start": m.start(),
                "end": m.end(),
            })

    # 1. PERSON: capitalized name patterns
    for m in PERSON_PATTERN.finditer(combined):
        span = (m.start(), m.end())
        if span in seen_spans:
            continue
        surface = m.group().strip()
        if _is_noise(surface):
            continue
        seen_spans.add(span)
        entities.append({
            "surface": surface,
            "type": "PERSON",
            "canonical_guess": surface,
            "entity_id": _make_entity_id(surface),
            "start": m.start(),
            "end": m.end(),
        })

    # 2. ORG: known organization acronyms
    for m in ORG_ACRONYM_PATTERN.finditer(combined):
        acr = m.group()
        if acr in KNOWN_ORGS:
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            entities.append({
                "surface": acr,
                "type": "ORG",
                "canonical_guess": acr,
                "entity_id": _make_entity_id(acr),
                "start": m.start(),
                "end": m.end(),
            })

    # 3. PLACE: known locations
    for place in PLACES:
        for m in re.finditer(r'\b' + re.escape(place) + r'\b', combined):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            entities.append({
                "surface": place,
                "type": "PLACE",
                "canonical_guess": place,
                "entity_id": _make_entity_id(place),
                "start": m.start(),
                "end": m.end(),
            })

    # Deduplicate by surface (keep first occurrence per surface)
    seen_surfaces: set[str] = set()
    deduped = []
    for e in entities:
        key = e["surface"].lower()
        if key not in seen_surfaces:
            seen_surfaces.add(key)
            deduped.append(e)

    return deduped
