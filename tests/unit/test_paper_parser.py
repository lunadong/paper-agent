"""Unit tests for the paper parser from emails module.

Tests paper_collection/paper_parser_from_emails.py functionality including:
- Year extraction from venue strings
- URL extraction from Google Scholar redirect links
- arXiv URL parsing and normalization
- ACM URL detection
- Google Scholar email parsing
- Venue normalization
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection"))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection" / "paper_metadata"))

from paper_parser_from_emails import (
    extract_acm_url_from_link,
    extract_arxiv_url_from_link,
    extract_url_from_scholar_link,
    extract_year_from_venue,
    parse_scholar_papers,
    update_arxiv_venue,
)


class TestExtractYearFromVenue:
    """Tests for extract_year_from_venue function."""

    def test_extract_year_from_venue_with_year(self) -> None:
        """Extract year from venue string containing a 4-digit year."""
        # Setup: Various venue strings with years
        test_cases = [
            ("NeurIPS, 2024", "2024"),
            ("ACM Transactions, 2025", "2025"),
            ("ICML 2024", "2024"),
            ("arXiv preprint arXiv:2601.19225, 2026", "2026"),
            ("Nature, 2023", "2023"),
            ("arXiv, 1/2026", "2026"),
            ("Conference on AI - Proceedings 2022", "2022"),
        ]

        for venue, expected_year in test_cases:
            # Execute: Extract year from venue
            result = extract_year_from_venue(venue)

            # Assert: Year is extracted correctly
            assert result == expected_year, (
                f"Expected year '{expected_year}' from venue '{venue}', got '{result}'"
            )

    def test_extract_year_from_venue_no_year(self) -> None:
        """Return None when venue string contains no year."""
        # Setup: Venue strings without years
        test_cases = [
            "arXiv preprint",
            "Unknown venue",
            "Conference proceedings",
            "",
            "Nature Magazine",
            "ACM Digital Library",
        ]

        for venue in test_cases:
            # Execute: Extract year from venue
            result = extract_year_from_venue(venue)

            # Assert: None is returned for venues without years
            assert result is None, f"Expected None for venue '{venue}', got '{result}'"

    def test_extract_year_from_venue_none_input(self) -> None:
        """Handle None input gracefully."""
        # Setup: None input
        venue = None

        # Execute: Extract year from None venue
        result = extract_year_from_venue(venue)

        # Assert: None is returned
        assert result is None, "Should return None for None input"


class TestExtractUrlFromScholarLink:
    """Tests for extract_url_from_scholar_link function."""

    def test_extract_url_from_scholar_link(self) -> None:
        """Unwrap Google Scholar redirect URLs to get actual paper URLs."""
        # Setup: Google Scholar redirect URL
        scholar_link = (
            "https://scholar.google.com/scholar_url?"
            "url=https://dl.acm.org/doi/pdf/10.1145/3787466&hl=en&sa=X&d=12345"
        )
        expected_url = "https://dl.acm.org/doi/pdf/10.1145/3787466"

        # Execute: Extract the actual URL
        result = extract_url_from_scholar_link(scholar_link)

        # Assert: Actual URL is extracted
        assert result == expected_url, f"Expected '{expected_url}', got '{result}'"

    def test_extract_url_from_scholar_link_encoded(self) -> None:
        """Handle URL-encoded characters in Scholar redirect URLs."""
        # Setup: Scholar URL with encoded characters
        scholar_link = (
            "https://scholar.google.com/scholar_url?"
            "url=https%3A%2F%2Farxiv.org%2Fabs%2F2401.12345&hl=en"
        )
        expected_url = "https://arxiv.org/abs/2401.12345"

        # Execute: Extract and decode URL
        result = extract_url_from_scholar_link(scholar_link)

        # Assert: URL is decoded correctly
        assert result == expected_url, f"Expected '{expected_url}', got '{result}'"

    def test_extract_url_non_scholar_link(self) -> None:
        """Return original URL if not a Google Scholar redirect."""
        # Setup: Direct URLs (not Scholar redirects)
        test_cases = [
            "https://arxiv.org/abs/2401.12345",
            "https://dl.acm.org/doi/10.1145/1234567",
            "https://www.nature.com/articles/s41586-024-07487-w",
        ]

        for direct_url in test_cases:
            # Execute: Try to extract URL from non-Scholar link
            result = extract_url_from_scholar_link(direct_url)

            # Assert: Original URL is returned unchanged
            assert result == direct_url, (
                f"Expected original URL '{direct_url}' to be returned unchanged"
            )


class TestExtractArxivUrl:
    """Tests for extract_arxiv_url_from_link function."""

    def test_extract_arxiv_url_standard(self) -> None:
        """Parse standard arxiv.org/abs/ URLs."""
        # Setup: Standard arXiv abstract URL
        link = "https://arxiv.org/abs/2401.00000"
        expected = "https://arxiv.org/abs/2401.00000"

        # Execute: Extract arXiv URL
        result = extract_arxiv_url_from_link(link)

        # Assert: Correct arXiv URL is returned
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_extract_arxiv_url_pdf(self) -> None:
        """Convert PDF URL to abstract URL."""
        # Setup: arXiv PDF URL
        link = "https://arxiv.org/pdf/2401.12345"
        expected = "https://arxiv.org/abs/2401.12345"

        # Execute: Extract and convert to abs URL
        result = extract_arxiv_url_from_link(link)

        # Assert: PDF URL is converted to abs URL
        assert result == expected, (
            f"Expected PDF URL to be converted to '{expected}', got '{result}'"
        )

    def test_extract_arxiv_url_from_scholar_redirect(self) -> None:
        """Extract arXiv URL from Scholar redirect link."""
        # Setup: Scholar redirect containing arXiv URL
        link = (
            "https://scholar.google.com/scholar_url?"
            "url=https://arxiv.org/abs/2401.54321&hl=en"
        )
        expected = "https://arxiv.org/abs/2401.54321"

        # Execute: Extract arXiv URL from Scholar redirect
        result = extract_arxiv_url_from_link(link)

        # Assert: arXiv URL is extracted
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_extract_arxiv_url_not_arxiv(self) -> None:
        """Return None for non-arXiv links."""
        # Setup: Non-arXiv URLs
        test_cases = [
            "https://dl.acm.org/doi/10.1145/1234567",
            "https://www.nature.com/articles/s41586-024-07487-w",
            "https://ieeexplore.ieee.org/document/12345",
        ]

        for link in test_cases:
            # Execute: Try to extract arXiv URL
            result = extract_arxiv_url_from_link(link)

            # Assert: None is returned for non-arXiv links
            assert result is None, (
                f"Expected None for non-arXiv link '{link}', got '{result}'"
            )


class TestExtractAcmUrl:
    """Tests for extract_acm_url_from_link function."""

    def test_extract_acm_url_from_link(self) -> None:
        """Detect ACM Digital Library URLs."""
        # Setup: ACM Digital Library URL (mock the converter function)
        link = "https://dl.acm.org/doi/pdf/10.1145/3787466"

        patch_target = "paper_parser_from_emails.convert_acm_pdf_to_abs"
        with patch(patch_target) as mock_convert:
            mock_convert.return_value = "https://dl.acm.org/doi/abs/10.1145/3787466"

            # Execute: Extract ACM URL
            result = extract_acm_url_from_link(link)

            # Assert: ACM URL is detected and converted
            assert result == "https://dl.acm.org/doi/abs/10.1145/3787466", (
                f"Expected ACM abs URL, got '{result}'"
            )
            mock_convert.assert_called_once()

    def test_extract_acm_url_from_scholar_redirect(self) -> None:
        """Extract ACM URL from Google Scholar redirect."""
        # Setup: Scholar redirect containing ACM URL
        link = (
            "https://scholar.google.com/scholar_url?"
            "url=https://dl.acm.org/doi/pdf/10.1145/1234567&hl=en"
        )

        patch_target = "paper_parser_from_emails.convert_acm_pdf_to_abs"
        with patch(patch_target) as mock_convert:
            mock_convert.return_value = "https://dl.acm.org/doi/abs/10.1145/1234567"

            # Execute: Extract ACM URL from Scholar redirect
            result = extract_acm_url_from_link(link)

            # Assert: ACM URL is extracted from redirect
            assert result == "https://dl.acm.org/doi/abs/10.1145/1234567", (
                f"Expected ACM URL from redirect, got '{result}'"
            )

    def test_extract_acm_url_not_acm(self) -> None:
        """Return None for non-ACM links."""
        # Setup: Non-ACM URLs
        test_cases = [
            "https://arxiv.org/abs/2401.12345",
            "https://www.nature.com/articles/s41586-024-07487-w",
            "https://ieeexplore.ieee.org/document/12345",
        ]

        for link in test_cases:
            # Execute: Try to extract ACM URL
            result = extract_acm_url_from_link(link)

            # Assert: None is returned for non-ACM links
            assert result is None, (
                f"Expected None for non-ACM link '{link}', got '{result}'"
            )


class TestParseScholarPapers:
    """Tests for parse_scholar_papers function."""

    def test_parse_scholar_papers_single(self) -> None:
        """Parse email containing a single paper."""
        # Setup: Simple HTML with one paper
        html_content = """
        <html>
        <body>
        <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.12345">
            A Novel Approach to Machine Learning with Deep Neural Networks
        </a>
        <font color="#006621">A. Author, B. Researcher - arXiv preprint, 2024</font>
        <div>This paper presents a groundbreaking approach to ML using deep learning.</div>
        </body>
        </html>
        """

        patch_target = "paper_parser_from_emails.enrich_paper_with_arxiv"
        with patch(patch_target) as mock_enrich:
            # Make enrich return paper unchanged
            mock_enrich.side_effect = lambda p: p

            # Execute: Parse the HTML with enrichment disabled
            papers = parse_scholar_papers(html_content, enrich_arxiv=False)

            # Assert: One paper is parsed correctly
            assert len(papers) == 1, f"Expected 1 paper, got {len(papers)}"
            paper = papers[0]
            assert "Machine Learning" in paper["title"], (
                f"Title should contain 'Machine Learning', got '{paper['title']}'"
            )
            assert paper["authors"] == "A. Author, B. Researcher", (
                f"Authors mismatch: {paper['authors']}"
            )
            assert "arXiv" in paper["venue"], "Venue should contain 'arXiv'"
            assert paper["year"] == "2024", "Year should be 2024"

    def test_parse_scholar_papers_multiple(self) -> None:
        """Parse email containing multiple papers."""
        # Setup: HTML with multiple papers
        html_content = """
        <html>
        <body>
        <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.11111">
            First Paper Title on Reinforcement Learning and AI Systems
        </a>
        <font color="#006621">X. First, Y. Second - NeurIPS, 2024</font>
        <div>First paper abstract about reinforcement learning methods.</div>

        <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.22222">
            Second Paper on Natural Language Processing Tasks
        </a>
        <font color="#006621">Z. Third, W. Fourth - ICML, 2024</font>
        <div>Second paper abstract about NLP approaches.</div>

        <a href="https://scholar.google.com/scholar_url?url=https://dl.acm.org/doi/10.1145/3333333">
            Third Paper About Knowledge Graph Construction
        </a>
        <font color="#006621">M. Fifth, N. Sixth - ACM SIGMOD, 2024</font>
        <div>Third paper about knowledge graphs and databases.</div>
        </body>
        </html>
        """

        # Execute: Parse the HTML
        papers = parse_scholar_papers(html_content, enrich_arxiv=False)

        # Assert: All three papers are parsed
        assert len(papers) == 3, f"Expected 3 papers, got {len(papers)}"

        # Check each paper has required fields
        for i, paper in enumerate(papers):
            assert "title" in paper, f"Paper {i} missing title"
            assert "authors" in paper, f"Paper {i} missing authors"
            assert "venue" in paper, f"Paper {i} missing venue"
            assert "link" in paper, f"Paper {i} missing link"
            assert len(paper["title"]) > 15, f"Paper {i} title too short"

    def test_parse_scholar_papers_filters_non_papers(self) -> None:
        """Skip non-paper links like 'Unsubscribe' or 'Google Scholar' links."""
        # Setup: HTML with papers and non-paper links
        html_content = """
        <html>
        <body>
        <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.12345">
            Real Paper Title About Artificial Intelligence Methods
        </a>
        <font color="#006621">A. Author - arXiv, 2024</font>
        <div>Abstract of the real paper.</div>

        <a href="https://scholar.google.com/unsubscribe?token=abc123">
            Unsubscribe from this alert
        </a>

        <a href="https://scholar.google.com/scholar_alerts">
            Google Scholar Alerts Settings
        </a>

        <a href="https://scholar.google.com/manage">
            Manage your Google Scholar alerts and settings here
        </a>
        </body>
        </html>
        """

        # Execute: Parse the HTML
        papers = parse_scholar_papers(html_content, enrich_arxiv=False)

        # Assert: Only the real paper is parsed, non-paper links are filtered
        assert len(papers) == 1, (
            f"Expected 1 paper (filtering non-papers), got {len(papers)}: "
            f"{[p.get('title', 'NO TITLE')[:50] for p in papers]}"
        )
        assert "Artificial Intelligence" in papers[0]["title"], (
            "Should parse the real paper title"
        )


class TestUpdateArxivVenue:
    """Tests for update_arxiv_venue function."""

    def test_update_arxiv_venue(self) -> None:
        """Normalize arXiv venue to 'arXiv, M/YYYY' format."""
        # Setup: Original arXiv venue and date
        venue = "arXiv preprint arXiv:2601.19225, 2026"
        arxiv_date = "1/2026"
        expected = "arXiv, 1/2026"

        # Execute: Update venue with extracted date
        result = update_arxiv_venue(venue, arxiv_date)

        # Assert: Venue is normalized correctly
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_update_arxiv_venue_with_different_dates(self) -> None:
        """Handle various month/year combinations."""
        # Setup: Test cases with different dates
        test_cases = [
            ("arXiv, 2024", "5/2024", "arXiv, 5/2024"),
            ("arXiv preprint, 2025", "12/2025", "arXiv, 12/2025"),
            ("arXiv:2301.12345, 2023", "1/2023", "arXiv, 1/2023"),
        ]

        for venue, date, expected in test_cases:
            # Execute: Update venue
            result = update_arxiv_venue(venue, date)

            # Assert: Venue is updated correctly
            assert result == expected, (
                f"For venue '{venue}' with date '{date}', "
                f"expected '{expected}', got '{result}'"
            )

    def test_update_arxiv_venue_no_date(self) -> None:
        """Handle case when no arXiv date is available."""
        # Setup: arXiv venue without date
        venue = "arXiv preprint, 2026"
        arxiv_date = None
        expected = "arXiv, ??/2026"

        # Execute: Update venue without date
        result = update_arxiv_venue(venue, arxiv_date)

        # Assert: Unknown month is indicated
        assert result == expected, f"Expected '{expected}', got '{result}'"

    def test_update_arxiv_venue_non_arxiv(self) -> None:
        """Return original venue for non-arXiv venues."""
        # Setup: Non-arXiv venues
        test_cases = [
            ("NeurIPS, 2024", "1/2024", "NeurIPS, 2024"),
            ("ICML 2023", "5/2023", "ICML 2023"),
            ("ACM SIGMOD, 2025", None, "ACM SIGMOD, 2025"),
        ]

        for venue, date, expected in test_cases:
            # Execute: Try to update non-arXiv venue
            result = update_arxiv_venue(venue, date)

            # Assert: Original venue is returned
            assert result == expected, (
                f"Non-arXiv venue '{venue}' should be returned unchanged, "
                f"got '{result}'"
            )
