#!/usr/bin/env python3
"""
Unit tests for the ACM Digital Library fetcher module.

Tests paper_collection/paper_metadata/acm_fetcher.py
"""

from unittest.mock import MagicMock, patch

import pytest
from paper_collection.paper_metadata.acm_fetcher import (
    convert_acm_pdf_to_abs,
    extract_abstract,
    extract_acm_doi,
    extract_date,
    extract_paper_info,
    fetch_acm_html,
)


class TestExtractAcmDoi:
    """Tests for extract_acm_doi function."""

    def test_extract_acm_doi(self):
        """Extract DOI from ACM URL."""
        # Setup
        url = "https://dl.acm.org/doi/abs/10.1145/3787466"

        # Execute
        result = extract_acm_doi(url)

        # Assert
        assert result == "10.1145/3787466"

    def test_extract_acm_doi_with_full_path(self):
        """Extract DOI from ACM URL with additional path segments."""
        # Setup
        url = "https://dl.acm.org/doi/10.1145/3639476.3639781"

        # Execute
        result = extract_acm_doi(url)

        # Assert
        assert result == "10.1145/3639476.3639781"

    def test_extract_acm_doi_pdf_url(self):
        """Extract DOI from ACM PDF URL."""
        # Setup
        url = "https://dl.acm.org/doi/pdf/10.1145/3787466"

        # Execute
        result = extract_acm_doi(url)

        # Assert
        assert result == "10.1145/3787466"

    def test_extract_acm_doi_invalid(self):
        """Return None for invalid URL without DOI."""
        # Setup
        invalid_urls = [
            "https://example.com/paper",
            "https://dl.acm.org/",
            "not-a-url",
        ]

        # Execute & Assert
        for url in invalid_urls:
            result = extract_acm_doi(url)
            assert result is None, f"Expected None for URL: {url}"


class TestConvertAcmPdfToAbs:
    """Tests for convert_acm_pdf_to_abs function."""

    def test_convert_acm_pdf_to_abs(self):
        """Convert /pdf/ URLs to /abs/ URLs."""
        # Setup
        pdf_url = "https://dl.acm.org/doi/pdf/10.1145/3787466"

        # Execute
        result = convert_acm_pdf_to_abs(pdf_url)

        # Assert
        assert result == "https://dl.acm.org/doi/abs/10.1145/3787466"

    def test_convert_acm_direct_doi_to_abs(self):
        """Convert direct DOI URLs to /abs/ URLs."""
        # Setup
        direct_url = "https://dl.acm.org/doi/10.1145/3787466"

        # Execute
        result = convert_acm_pdf_to_abs(direct_url)

        # Assert
        assert result == "https://dl.acm.org/doi/abs/10.1145/3787466"

    def test_convert_acm_abs_unchanged(self):
        """Leave /abs/ URLs unchanged."""
        # Setup
        abs_url = "https://dl.acm.org/doi/abs/10.1145/3787466"

        # Execute
        result = convert_acm_pdf_to_abs(abs_url)

        # Assert
        assert result == abs_url


class TestExtractAbstract:
    """Tests for extract_abstract function."""

    def test_extract_abstract(self):
        """Parse abstract from HTML with abstractSection class."""
        # Setup
        html_content = """
        <html>
        <body>
        <div class="abstractSection abstractInFull">
        <p>This paper presents a novel system for managing large-scale
        data processing pipelines with improved efficiency and reliability.</p>
        </div>
        </body>
        </html>
        """

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is not None
        assert "novel system" in result
        assert "data processing" in result

    def test_extract_abstract_doc_role(self):
        """Parse abstract from section with role='doc-abstract'."""
        # Setup
        html_content = """
        <html>
        <body>
        <section role="doc-abstract">
        <p>We present a comprehensive study of machine learning techniques
        applied to natural language understanding tasks.</p>
        </section>
        </body>
        </html>
        """

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is not None
        assert "machine learning techniques" in result

    def test_extract_abstract_not_found(self):
        """Return None when abstract is not found."""
        # Setup
        html_content = "<html><body>No abstract here</body></html>"

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is None

    def test_extract_abstract_too_short(self):
        """Return None when abstract is too short (< 50 chars)."""
        # Setup
        html_content = """
        <div class="abstractSection">
        <p>Short text.</p>
        </div>
        """

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is None


class TestExtractDate:
    """Tests for extract_date function."""

    def test_extract_date(self):
        """Parse publication date from HTML."""
        # Setup
        html_content = """
        <html>
        <body>
        <div class="published">Published: 15 March 2024</div>
        </body>
        </html>
        """

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "3/2024"

    def test_extract_date_publication_format(self):
        """Parse Publication Date: Month YYYY format."""
        # Setup
        html_content = """
        <html>
        <body>
        <span>Publication Date: June 2023</span>
        </body>
        </html>
        """

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "6/2023"

    def test_extract_date_json_ld(self):
        """Parse datePublished from JSON-LD format."""
        # Setup
        html_content = """
        <html>
        <body>
        <script type="application/ld+json">
        {"@type": "ScholarlyArticle", "datePublished": "2024-03-15"}
        </script>
        </body>
        </html>
        """

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "3/2024"

    def test_extract_date_not_found(self):
        """Return None when date is not found."""
        # Setup
        html_content = "<html><body>No date information</body></html>"

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result is None


class TestExtractPaperInfo:
    """Tests for extract_paper_info function."""

    def test_extract_paper_info(self):
        """Return dict with date and abstract fields."""
        # Setup
        html_content = """
        <html>
        <body>
        <div class="published">Published: 10 January 2024</div>
        <div class="abstractSection abstractInFull">
        <p>This paper introduces a groundbreaking approach to distributed
        systems design that improves scalability and fault tolerance.</p>
        </div>
        </body>
        </html>
        """

        # Execute
        result = extract_paper_info(html_content)

        # Assert
        assert isinstance(result, dict)
        assert "date" in result
        assert "abstract" in result
        assert result["date"] == "1/2024"
        assert result["abstract"] is not None
        assert "distributed systems" in result["abstract"]

    def test_extract_paper_info_empty(self):
        """Return dict with None values when nothing found."""
        # Setup
        html_content = "<html><body></body></html>"

        # Execute
        result = extract_paper_info(html_content)

        # Assert
        assert isinstance(result, dict)
        assert result["date"] is None
        assert result["abstract"] is None


class TestFetchAcmHtml:
    """Tests for fetch_acm_html function."""

    def test_fetch_acm_html_invalid_url(self):
        """Raise ValueError for non-ACM URL."""
        # Setup
        invalid_url = "https://example.com/paper/123"

        # Execute & Assert
        with pytest.raises(ValueError) as excinfo:
            fetch_acm_html(invalid_url)

        assert "Invalid ACM URL" in str(excinfo.value)

    @patch("paper_collection.paper_metadata.acm_fetcher.requests.Session")
    def test_fetch_acm_html_success(self, mock_session_class):
        """Successfully fetch HTML from ACM."""
        # Setup
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "<html>ACM content</html>"
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        url = "https://dl.acm.org/doi/abs/10.1145/3787466"

        # Execute
        result = fetch_acm_html(url)

        # Assert
        assert result == "<html>ACM content</html>"

    @patch("paper_collection.paper_metadata.acm_fetcher.requests.Session")
    def test_fetch_acm_html_request_failure(self, mock_session_class):
        """Return None on request failure."""
        # Setup
        import requests

        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("Error")
        mock_session_class.return_value = mock_session

        url = "https://dl.acm.org/doi/abs/10.1145/3787466"

        # Execute
        result = fetch_acm_html(url)

        # Assert
        assert result is None
