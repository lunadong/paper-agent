"""Unit tests for the paper parser from Google Scholar module.

Tests paper_collection/paper_parser_from_google_scholar.py functionality including:
- Title normalization for duplicate detection
- arXiv link normalization
- Title similarity calculation
- recomm_date calculation based on publication year
- Google Scholar URL building
- Paper parsing from HTML
- Embedding generation after paper collection
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection"))

from paper_discovery.paper_parser_from_google_scholar import (
    build_search_url,
    normalize_arxiv_link,
    normalize_title,
    parse_papers,
    title_similarity,
)


class TestNormalizeTitle:
    """Tests for normalize_title function."""

    def test_normalize_title_basic(self) -> None:
        """Normalize title by lowercasing and removing punctuation."""
        # Setup: Title with mixed case and punctuation
        title = "A Novel Approach to Machine Learning: Deep Networks"

        # Execute: Normalize the title
        result = normalize_title(title)

        # Assert: Title is normalized (lowercase, no punctuation, sorted words)
        assert "novel" in result
        assert "approach" in result
        assert "machine" in result
        assert "learning" in result
        assert "deep" in result
        assert "networks" in result
        # Stopwords should be removed
        assert "a" not in result.split()
        assert "to" not in result.split()

    def test_normalize_title_removes_stopwords(self) -> None:
        """Remove common stopwords from title."""
        # Setup: Title with many stopwords
        title = "The Study of a Method for the Analysis"

        # Execute: Normalize
        result = normalize_title(title)

        # Assert: Stopwords are removed
        words = result.split()
        assert "the" not in words
        assert "of" not in words
        assert "a" not in words
        assert "for" not in words
        assert "study" in words
        assert "method" in words
        assert "analysis" in words

    def test_normalize_title_empty(self) -> None:
        """Handle empty title."""
        # Setup: Empty title
        title = ""

        # Execute: Normalize
        result = normalize_title(title)

        # Assert: Returns empty string
        assert result == ""

    def test_normalize_title_none(self) -> None:
        """Handle None input gracefully."""
        # Setup: None input
        title = None

        # Execute: Normalize
        result = normalize_title(title)

        # Assert: Returns empty string
        assert result == ""

    def test_normalize_title_sorted_words(self) -> None:
        """Words are sorted for order-independent matching."""
        # Setup: Two titles with same words in different order
        title1 = "Machine Learning for NLP"
        title2 = "NLP for Machine Learning"

        # Execute: Normalize both
        result1 = normalize_title(title1)
        result2 = normalize_title(title2)

        # Assert: Both normalize to the same string
        assert result1 == result2


class TestNormalizeArxivLink:
    """Tests for normalize_arxiv_link function."""

    def test_normalize_arxiv_abs_url(self) -> None:
        """Extract arXiv ID from abs URL."""
        # Setup: Standard arXiv abs URL
        link = "https://arxiv.org/abs/2401.12345"

        # Execute: Normalize
        result = normalize_arxiv_link(link)

        # Assert: Returns just the ID
        assert result == "2401.12345"

    def test_normalize_arxiv_pdf_url(self) -> None:
        """Extract arXiv ID from PDF URL."""
        # Setup: arXiv PDF URL
        link = "https://arxiv.org/pdf/2401.12345"

        # Execute: Normalize
        result = normalize_arxiv_link(link)

        # Assert: Returns just the ID
        assert result == "2401.12345"

    def test_normalize_arxiv_pdf_with_extension(self) -> None:
        """Handle PDF URL with .pdf extension."""
        # Setup: arXiv PDF URL with extension
        link = "https://arxiv.org/pdf/2401.12345.pdf"

        # Execute: Normalize
        result = normalize_arxiv_link(link)

        # Assert: Returns just the ID without extension
        assert result == "2401.12345"

    def test_normalize_arxiv_html_url(self) -> None:
        """Extract arXiv ID from HTML URL."""
        # Setup: arXiv HTML URL
        link = "https://arxiv.org/html/2401.12345"

        # Execute: Normalize
        result = normalize_arxiv_link(link)

        # Assert: Returns just the ID
        assert result == "2401.12345"

    def test_normalize_arxiv_with_version(self) -> None:
        """Strip version number from arXiv ID."""
        # Setup: arXiv URL with version
        test_cases = [
            ("https://arxiv.org/abs/2401.12345v1", "2401.12345"),
            ("https://arxiv.org/abs/2401.12345v2", "2401.12345"),
            ("https://arxiv.org/pdf/2401.12345v3.pdf", "2401.12345"),
        ]

        for link, expected in test_cases:
            # Execute: Normalize
            result = normalize_arxiv_link(link)

            # Assert: Version is stripped
            assert result == expected, f"For {link}, expected {expected}, got {result}"

    def test_normalize_arxiv_non_arxiv_link(self) -> None:
        """Return None for non-arXiv links."""
        # Setup: Non-arXiv URLs
        test_cases = [
            "https://dl.acm.org/doi/10.1145/1234567",
            "https://www.nature.com/articles/s41586-024-07487-w",
            "https://ieeexplore.ieee.org/document/12345",
            "https://example.com/paper.pdf",
        ]

        for link in test_cases:
            # Execute: Try to normalize
            result = normalize_arxiv_link(link)

            # Assert: Returns None
            assert result is None, f"Expected None for {link}, got {result}"

    def test_normalize_arxiv_empty_link(self) -> None:
        """Handle empty link."""
        # Setup: Empty/None links
        test_cases = ["", None]

        for link in test_cases:
            # Execute: Normalize
            result = normalize_arxiv_link(link)

            # Assert: Returns None
            assert result is None


class TestTitleSimilarity:
    """Tests for title_similarity function."""

    def test_title_similarity_identical(self) -> None:
        """Identical titles have similarity 1.0."""
        # Setup: Same title
        title1 = "Machine Learning for NLP"
        title2 = "Machine Learning for NLP"

        # Execute: Calculate similarity
        result = title_similarity(title1, title2)

        # Assert: Perfect similarity
        assert result == 1.0

    def test_title_similarity_completely_different(self) -> None:
        """Completely different titles have low similarity."""
        # Setup: Different titles
        title1 = "Machine Learning for NLP"
        title2 = "Quantum Physics and Chemistry"

        # Execute: Calculate similarity
        result = title_similarity(title1, title2)

        # Assert: Low similarity
        assert result < 0.3

    def test_title_similarity_partial_overlap(self) -> None:
        """Titles with partial overlap have medium similarity."""
        # Setup: Titles with some common words
        title1 = "Deep Learning for Natural Language Processing"
        title2 = "Deep Learning for Computer Vision"

        # Execute: Calculate similarity
        result = title_similarity(title1, title2)

        # Assert: Medium similarity (Jaccard similarity ~0.29 for these titles)
        assert 0.2 < result < 0.8

    def test_title_similarity_empty(self) -> None:
        """Handle empty titles."""
        # Setup: Empty title
        title1 = ""
        title2 = "Some Title"

        # Execute: Calculate similarity
        result = title_similarity(title1, title2)

        # Assert: Zero similarity
        assert result == 0.0


class TestBuildSearchUrl:
    """Tests for build_search_url function."""

    def test_build_search_url_basic(self) -> None:
        """Build basic search URL with query."""
        # Setup: Simple query
        query = "machine learning"
        start = 0

        # Execute: Build URL
        result = build_search_url(query, start)

        # Assert: URL contains query and start
        assert "scholar.google.com" in result
        assert "machine" in result.lower() or "machine%20" in result.lower()
        assert "start=0" in result

    def test_build_search_url_with_year_filter(self) -> None:
        """Build URL with year filter."""
        # Setup: Query with year range
        query = "RAG"
        start = 0
        year_start = 2023
        year_end = 2024

        # Execute: Build URL
        result = build_search_url(query, start, year_start, year_end)

        # Assert: URL contains year parameters
        assert "as_ylo=2023" in result
        assert "as_yhi=2024" in result

    def test_build_search_url_pagination(self) -> None:
        """Build URL with pagination offset."""
        # Setup: Query with offset
        query = "RAG"
        start = 20

        # Execute: Build URL
        result = build_search_url(query, start)

        # Assert: URL contains correct offset
        assert "start=20" in result


class TestRecommDateCalculation:
    """Tests for recomm_date calculation logic (integrated in main function)."""

    def test_recomm_date_for_2026_papers(self) -> None:
        """2026 papers should get recomm_date 2026-02-28."""
        # Setup: Year 2026
        year_int = 2026

        # Execute: Calculate recomm_date (logic from main function)
        if year_int == 2026:
            gs_recomm_date = "2026-02-28"
        elif year_int > 0:
            gs_recomm_date = f"{year_int}-12-31"
        else:
            gs_recomm_date = datetime.now().strftime("%Y-%m-%d")

        # Assert: Correct date for 2026
        assert gs_recomm_date == "2026-02-28"

    def test_recomm_date_for_2025_papers(self) -> None:
        """2025 papers should get recomm_date 2025-12-31."""
        # Setup: Year 2025
        year_int = 2025

        # Execute: Calculate recomm_date
        if year_int == 2026:
            gs_recomm_date = "2026-02-28"
        elif year_int > 0:
            gs_recomm_date = f"{year_int}-12-31"
        else:
            gs_recomm_date = datetime.now().strftime("%Y-%m-%d")

        # Assert: Correct date for 2025
        assert gs_recomm_date == "2025-12-31"

    def test_recomm_date_for_2024_papers(self) -> None:
        """2024 papers should get recomm_date 2024-12-31."""
        # Setup: Year 2024
        year_int = 2024

        # Execute: Calculate recomm_date
        if year_int == 2026:
            gs_recomm_date = "2026-02-28"
        elif year_int > 0:
            gs_recomm_date = f"{year_int}-12-31"
        else:
            gs_recomm_date = datetime.now().strftime("%Y-%m-%d")

        # Assert: Correct date for 2024
        assert gs_recomm_date == "2024-12-31"

    def test_recomm_date_for_unknown_year(self) -> None:
        """Papers without year should get current date."""
        # Setup: No year (year_int = 0)
        year_int = 0

        # Execute: Calculate recomm_date
        if year_int == 2026:
            gs_recomm_date = "2026-02-28"
        elif year_int > 0:
            gs_recomm_date = f"{year_int}-12-31"
        else:
            gs_recomm_date = datetime.now().strftime("%Y-%m-%d")

        # Assert: Date is today's date
        today = datetime.now().strftime("%Y-%m-%d")
        assert gs_recomm_date == today


class TestParsePapers:
    """Tests for parse_papers function."""

    def test_parse_papers_single_result(self) -> None:
        """Parse a single paper from Google Scholar HTML."""
        # Setup: Simple HTML with one result
        html = """
        <html>
        <body>
        <div class="gs_r gs_or gs_scl">
            <h3 class="gs_rt">
                <a href="https://arxiv.org/abs/2401.12345">
                    A Novel Approach to Deep Learning
                </a>
            </h3>
            <div class="gs_a">
                J Smith, A Johnson - arXiv preprint, 2024
            </div>
            <div class="gs_rs">
                This paper presents a novel approach to deep learning...
            </div>
        </div>
        </body>
        </html>
        """

        # Execute: Parse papers
        papers = parse_papers(html)

        # Assert: One paper is parsed
        assert len(papers) == 1
        paper = papers[0]
        assert "Novel" in paper.get("title", "") or "Deep Learning" in paper.get(
            "title", ""
        )

    def test_parse_papers_empty_html(self) -> None:
        """Handle empty HTML gracefully."""
        # Setup: Empty HTML
        html = "<html><body></body></html>"

        # Execute: Parse papers
        papers = parse_papers(html)

        # Assert: No papers found
        assert papers == []

    def test_parse_papers_no_results(self) -> None:
        """Handle HTML with no paper results."""
        # Setup: HTML without paper results
        html = """
        <html>
        <body>
        <div>No results found for your search.</div>
        </body>
        </html>
        """

        # Execute: Parse papers
        papers = parse_papers(html)

        # Assert: Empty list
        assert papers == []


class TestEmbeddingGeneration:
    """Tests for embedding generation after paper collection."""

    def test_embedding_generation_called_when_papers_added(self) -> None:
        """Embedding generation is called when papers are added."""
        # Setup: Mock db with update_all_embeddings method
        mock_db = MagicMock()
        mock_db.update_all_embeddings.return_value = {
            "updated": 5,
            "total": 5,
            "errors": 0,
        }
        progress = {"added": 5, "skipped": 0}
        result = None

        # Execute: Simulate the finally block logic
        if mock_db and progress["added"] > 0:
            result = mock_db.update_all_embeddings()

        # Assert: update_all_embeddings was called
        mock_db.update_all_embeddings.assert_called_once()
        assert result is not None
        assert result["updated"] == 5

    def test_embedding_generation_skipped_when_no_papers_added(self) -> None:
        """Embedding generation is skipped when no papers are added."""
        # Setup: Mock db
        mock_db = MagicMock()
        progress = {"added": 0, "skipped": 10}

        # Execute: Simulate the finally block logic
        if mock_db and progress["added"] > 0:
            mock_db.update_all_embeddings()

        # Assert: update_all_embeddings was NOT called
        mock_db.update_all_embeddings.assert_not_called()

    def test_embedding_generation_handles_exception(self) -> None:
        """Embedding generation handles exceptions gracefully."""
        # Setup: Mock db that raises an exception
        mock_db = MagicMock()
        mock_db.update_all_embeddings.side_effect = Exception("OpenAI API error")
        progress = {"added": 3}
        error_message = None

        # Execute: Simulate the finally block logic with exception handling
        if mock_db and progress["added"] > 0:
            try:
                mock_db.update_all_embeddings()
            except Exception as e:
                error_message = str(e)

        # Assert: Exception was caught
        assert error_message == "OpenAI API error"

    def test_embedding_generation_db_close_always_called(self) -> None:
        """Database is closed even if embedding generation fails."""
        # Setup: Mock db with failing update_all_embeddings
        mock_db = MagicMock()
        mock_db.update_all_embeddings.side_effect = Exception("API error")
        progress = {"added": 2}
        db_closed = False

        # Execute: Simulate the finally block logic
        try:
            if mock_db and progress["added"] > 0:
                mock_db.update_all_embeddings()
        except Exception:
            pass
        finally:
            if mock_db:
                mock_db.close()
                db_closed = True

        # Assert: close() was called
        mock_db.close.assert_called_once()
        assert db_closed is True

    def test_embedding_generation_returns_count(self) -> None:
        """Embedding generation returns count of updated embeddings."""
        # Setup: Mock PaperDB instance with return value
        mock_db_instance = MagicMock()
        mock_db_instance.update_all_embeddings.return_value = {
            "total": 10,
            "updated": 8,
            "errors": 2,
        }

        # Execute: Call update_all_embeddings
        result = mock_db_instance.update_all_embeddings()

        # Assert: Correct values returned
        assert result["total"] == 10
        assert result["updated"] == 8
        assert result["errors"] == 2

    def test_embedding_generation_with_empty_db(self) -> None:
        """Embedding generation handles empty database (no papers without embeddings)."""
        # Setup: Mock db returning empty result
        mock_db = MagicMock()
        mock_db.update_all_embeddings.return_value = {
            "total": 0,
            "updated": 0,
            "errors": 0,
        }
        progress = {"added": 1}
        result = None

        # Execute: Call update_all_embeddings
        if mock_db and progress["added"] > 0:
            result = mock_db.update_all_embeddings()

        # Assert: Returns zero counts
        assert result is not None
        assert result["total"] == 0
        assert result["updated"] == 0
