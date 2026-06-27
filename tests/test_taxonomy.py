"""Tests for enrichment taxonomy module."""

import pytest
from enrich.taxonomy import SECTION_KEYWORDS


class TestSectionKeywords:
    def test_returns_all_sections(self):
        """Should contain all 10 sections."""
        expected = {
            "POLITIK", "EKONOMI", "TEKNOLOGI", "OLAHRAGA", "HUKUM",
            "INTERNASIONAL", "KESEHATAN", "PENDIDIKAN", "LINGKUNGAN", "BUDAYA",
        }
        assert set(SECTION_KEYWORDS.keys()) == expected

    def test_each_section_has_keywords(self):
        """Every section should have at least 5 keywords."""
        for section, keywords in SECTION_KEYWORDS.items():
            assert len(keywords) >= 5, f"{section} has only {len(keywords)} keywords"

    def test_no_empty_keywords(self):
        """No empty or whitespace-only keywords."""
        for section, keywords in SECTION_KEYWORDS.items():
            for kw in keywords:
                assert kw.strip(), f"Empty keyword in {section}"

    def test_section_classify_known_text(self):
        """Known political text should match POLITIK."""
        from enrich.taxonomy import SECTION_KEYWORDS
        text = "presiden prabowo hari ini menghadiri sidang kabinet"
        matches = set()
        for section, keywords in SECTION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    matches.add(section)
        assert "POLITIK" in matches

    def test_section_classify_sports_text(self):
        """Known sports text should match OLAHRAGA."""
        text = "timnas indonesia berlaga di piala dunia"
        matches = set()
        for section, keywords in SECTION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    matches.add(section)
        assert "OLAHRAGA" in matches
