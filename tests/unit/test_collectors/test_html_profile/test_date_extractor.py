"""Tests for date extractor module."""

from pathlib import Path

import pytest

from src.collectors.html_profile.date_extractor import DateExtractor
from src.collectors.html_profile.models import DateExtractionMethod, DateExtractionRule
from src.features.store.models import DateConfidence


# Path to HTML fixtures
FIXTURES_PATH = Path(__file__).parents[4] / "fixtures" / "html"


class TestDateExtractor:
    """Tests for DateExtractor class."""

    def test_extract_from_time_element(self) -> None:
        """Test date extraction from <time datetime> element."""
        html = """
        <article>
            <time datetime="2024-01-15T10:00:00Z">January 15, 2024</time>
            <h2>Test Article</h2>
        </article>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.year == 2024
        assert result.published_at.month == 1
        assert result.published_at.day == 15
        assert result.confidence == DateConfidence.HIGH
        assert result.method == DateExtractionMethod.TIME_ELEMENT
        assert result.raw_date == "2024-01-15T10:00:00Z"

    def test_extract_from_meta_published_time(self) -> None:
        """Test date extraction from meta article:published_time."""
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2024-02-20T14:30:00Z">
        </head>
        <body>
            <article><h2>Test Article</h2></article>
        </body>
        </html>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.year == 2024
        assert result.published_at.month == 2
        assert result.published_at.day == 20
        assert result.confidence == DateConfidence.HIGH
        assert result.method == DateExtractionMethod.META_PUBLISHED_TIME

    def test_extract_from_json_ld(self) -> None:
        """Test date extraction from JSON-LD datePublished."""
        html = """
        <article>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": "Test Article",
                "datePublished": "2024-03-10T09:30:00Z"
            }
            </script>
            <h2>Test Article</h2>
        </article>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.year == 2024
        assert result.published_at.month == 3
        assert result.published_at.day == 10
        assert result.confidence == DateConfidence.HIGH
        assert result.method == DateExtractionMethod.JSON_LD

    def test_extract_from_json_ld_date_modified_medium_confidence(self) -> None:
        """Test that dateModified gets medium confidence, not high."""
        html = """
        <article>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": "Test Article",
                "dateModified": "2024-03-10T09:30:00Z"
            }
            </script>
        </article>
        """
        # Custom rules that only check dateModified
        rules = DateExtractionRule(json_ld_keys=["dateModified"])
        extractor = DateExtractor(rules=rules)
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.confidence == DateConfidence.MEDIUM
        assert result.method == DateExtractionMethod.JSON_LD

    def test_extract_from_text_pattern(self) -> None:
        """Test date extraction from text patterns."""
        html = """
        <article>
            <h2>Test Article</h2>
            <span class="date">Published on 2024-04-25</span>
        </article>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.year == 2024
        assert result.published_at.month == 4
        assert result.published_at.day == 25
        assert result.confidence == DateConfidence.MEDIUM
        assert result.method == DateExtractionMethod.TEXT_PATTERN

    def test_no_date_found(self) -> None:
        """Test when no date is found."""
        html = """
        <article>
            <h2>Test Article Without Date</h2>
            <p>Just some content.</p>
        </article>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert result.published_at is None
        assert result.confidence == DateConfidence.LOW
        assert result.method == DateExtractionMethod.NONE

    def test_precedence_time_over_meta(self) -> None:
        """Test that <time> takes precedence over meta tags."""
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2024-01-01T00:00:00Z">
        </head>
        <body>
            <article>
                <time datetime="2024-02-02T00:00:00Z">Feb 2, 2024</time>
                <h2>Test Article</h2>
            </article>
        </body>
        </html>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        # <time> should be extracted, not meta
        assert result.published_at is not None
        assert result.published_at.month == 2
        assert result.published_at.day == 2
        assert result.method == DateExtractionMethod.TIME_ELEMENT

    def test_precedence_meta_over_json_ld(self) -> None:
        """Test that meta tags take precedence over JSON-LD."""
        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2024-03-03T00:00:00Z">
        </head>
        <body>
            <article>
                <script type="application/ld+json">
                {
                    "@type": "Article",
                    "datePublished": "2024-04-04T00:00:00Z"
                }
                </script>
            </article>
        </body>
        </html>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        # Meta should be extracted, not JSON-LD
        assert result.published_at is not None
        assert result.published_at.month == 3
        assert result.published_at.day == 3
        assert result.method == DateExtractionMethod.META_PUBLISHED_TIME

    def test_candidate_dates_tracking(self) -> None:
        """Test that candidate dates are tracked."""
        html = """
        <article>
            <time datetime="2024-01-15T10:00:00Z">January 15, 2024</time>
        </article>
        """
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        assert len(result.candidate_dates) >= 1
        assert any(c["source"] == "time_element" for c in result.candidate_dates)

    def test_extract_with_scope(self) -> None:
        """Test date extraction with limited scope."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <body>
            <article id="first">
                <time datetime="2024-01-01T00:00:00Z">Jan 1</time>
            </article>
            <article id="second">
                <time datetime="2024-02-02T00:00:00Z">Feb 2</time>
            </article>
        </body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        second_article = soup.select_one("#second")

        extractor = DateExtractor()
        result = extractor.extract_from_html(soup, scope=second_article)

        assert result.published_at is not None
        assert result.published_at.month == 2
        assert result.published_at.day == 2

    def test_extract_from_fixture_file(self) -> None:
        """Test extraction from fixture HTML file."""
        fixture_path = FIXTURES_PATH / "blog_list_with_time.html"
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        html = fixture_path.read_text()
        extractor = DateExtractor()
        result = extractor.extract_from_html(html)

        # Should find at least one date from the fixture
        assert result.published_at is not None
        assert result.method == DateExtractionMethod.TIME_ELEMENT


class TestDateExtractionRule:
    """Tests for DateExtractionRule configuration."""

    def test_custom_time_selector(self) -> None:
        """Test custom time selector."""
        html = """
        <article>
            <span class="custom-date" datetime="2024-05-05T12:00:00Z">May 5</span>
        </article>
        """
        rules = DateExtractionRule(time_selector="span.custom-date[datetime]")
        extractor = DateExtractor(rules=rules)
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.month == 5
        assert result.method == DateExtractionMethod.TIME_ELEMENT

    def test_custom_meta_properties(self) -> None:
        """Test custom meta property names."""
        html = """
        <html>
        <head>
            <meta property="custom:date" content="2024-06-06T00:00:00Z">
        </head>
        <body></body>
        </html>
        """
        rules = DateExtractionRule(meta_properties=["custom:date"])
        extractor = DateExtractor(rules=rules)
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        assert result.published_at.month == 6
        assert result.method == DateExtractionMethod.META_PUBLISHED_TIME

    def test_custom_text_patterns(self) -> None:
        """Test custom text patterns."""
        html = """
        <article>
            <p>Posted: 06/15/2024</p>
        </article>
        """
        rules = DateExtractionRule(text_patterns=[r"\d{2}/\d{2}/\d{4}"])
        extractor = DateExtractor(rules=rules)
        result = extractor.extract_from_html(html)

        assert result.published_at is not None
        # dateutil should parse 06/15/2024 as June 15
        assert result.published_at.month == 6
        assert result.published_at.day == 15
        assert result.method == DateExtractionMethod.TEXT_PATTERN
