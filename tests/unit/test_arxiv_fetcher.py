#!/usr/bin/env python3
"""
Unit tests for the ArXiv fetcher module.

Tests paper_collection/paper_metadata/arxiv_fetcher.py
"""

from unittest.mock import MagicMock, patch

import pytest
from paper_collection.paper_metadata.arxiv_fetcher import (
    extract_abstract,
    extract_arxiv_id,
    extract_date,
    extract_paper_info,
    fetch_arxiv_html,
    get_arxiv_pdf_url,
    search_arxiv_by_title,
)


class TestExtractArxivId:
    """Tests for extract_arxiv_id function."""

    def test_extract_arxiv_id(self):
        """Extract arXiv ID from a valid URL."""
        # Setup
        url = "https://arxiv.org/abs/2401.12345"

        # Execute
        result = extract_arxiv_id(url)

        # Assert
        assert result == "2401.12345"

    def test_extract_arxiv_id_with_version(self):
        """Extract arXiv ID from URL with version suffix."""
        # Setup
        url = "https://arxiv.org/abs/2401.12345v2"

        # Execute
        result = extract_arxiv_id(url)

        # Assert
        assert result == "2401.12345"

    def test_extract_arxiv_id_invalid(self):
        """Return None for invalid URLs."""
        # Setup
        invalid_urls = [
            "https://example.com/paper/2401.12345",
            "https://arxiv.org/pdf/2401.12345",
            "not-a-url",
            "",
        ]

        # Execute & Assert
        for url in invalid_urls:
            result = extract_arxiv_id(url)
            assert result is None, f"Expected None for URL: {url}"


class TestExtractDate:
    """Tests for extract_date function."""

    def test_extract_date_standard(self):
        """Parse standard submission date format."""
        # Setup
        html_content = """
        <div class="submission-history">
        [Submitted on 15 Jan 2024]
        </div>
        """

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "1/2024"

    def test_extract_date_revised(self):
        """Handle revised version date format."""
        # Setup
        html_content = """
        <div class="submission-history">
        [Submitted on 4 Mar 2024 (v1), last revised 4 Jun 2024]
        </div>
        """

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "3/2024"

    def test_extract_date_full_month_name(self):
        """Parse date with full month name."""
        # Setup
        html_content = "[Submitted on 20 February 2024]"

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result == "2/2024"

    def test_extract_date_not_found(self):
        """Return None when date is not found."""
        # Setup
        html_content = "<html><body>No date here</body></html>"

        # Execute
        result = extract_date(html_content)

        # Assert
        assert result is None


class TestExtractAbstract:
    """Tests for extract_abstract function."""

    def test_extract_abstract(self):
        """Parse abstract from blockquote element."""
        # Setup
        html_content = """
        <blockquote class="abstract mathjax">
        <span class="descriptor">Abstract:</span>
        This paper presents a novel approach to machine learning.
        We demonstrate significant improvements over existing methods.
        </blockquote>
        """

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is not None
        assert "This paper presents a novel approach" in result
        assert "significant improvements" in result
        assert "Abstract:" not in result

    def test_extract_abstract_with_html_tags(self):
        """Remove HTML tags from abstract text."""
        # Setup
        html_content = """
        <blockquote class="abstract">
        <span class="descriptor">Abstract:</span>
        This paper uses <em>transformers</em> and <strong>attention</strong>.
        </blockquote>
        """

        # Execute
        result = extract_abstract(html_content)

        # Assert
        assert result is not None
        assert "transformers" in result
        assert "attention" in result
        assert "<em>" not in result
        assert "<strong>" not in result

    def test_extract_abstract_not_found(self):
        """Return None when abstract is not found."""
        # Setup
        html_content = "<html><body>No abstract here</body></html>"

        # Execute
        result = extract_abstract(html_content)

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
        <div class="submission-history">
        [Submitted on 15 Jan 2024]
        </div>
        <blockquote class="abstract mathjax">
        <span class="descriptor">Abstract:</span>
        This is the abstract of the paper describing our research.
        </blockquote>
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
        assert "This is the abstract" in result["abstract"]

    def test_extract_paper_info_partial(self):
        """Return dict with None for missing fields."""
        # Setup
        html_content = """
        <html>
        <body>
        <blockquote class="abstract mathjax">
        <span class="descriptor">Abstract:</span>
        Just an abstract, no date.
        </blockquote>
        </body>
        </html>
        """

        # Execute
        result = extract_paper_info(html_content)

        # Assert
        assert isinstance(result, dict)
        assert result["date"] is None
        assert result["abstract"] is not None


class TestFetchArxivHtml:
    """Tests for fetch_arxiv_html function."""

    def test_fetch_arxiv_html_invalid_url(self):
        """Return None or raise error for non-arxiv URL."""
        # Setup
        invalid_url = "https://example.com/paper/123"

        # Execute & Assert
        with pytest.raises(ValueError) as excinfo:
            fetch_arxiv_html(invalid_url)

        assert "Invalid arXiv URL" in str(excinfo.value)

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_fetch_arxiv_html_success(self, _mock_sleep, mock_get):
        """Successfully fetch HTML from arXiv."""
        # Setup
        mock_response = MagicMock()
        mock_response.text = "<html>arXiv content</html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        url = "https://arxiv.org/abs/2401.12345"

        # Execute
        result = fetch_arxiv_html(url)

        # Assert
        assert result == "<html>arXiv content</html>"
        mock_get.assert_called_once()

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_fetch_arxiv_html_request_failure(self, _mock_sleep, mock_get):
        """Return None on request failure after retries."""
        # Setup
        import requests

        mock_get.side_effect = requests.RequestException("Connection failed")
        url = "https://arxiv.org/abs/2401.12345"

        # Execute
        result = fetch_arxiv_html(url)

        # Assert
        assert result is None


class TestGetArxivPdfUrl:
    """Tests for get_arxiv_pdf_url function."""

    def test_get_arxiv_pdf_url(self):
        """Generate correct PDF URL from arXiv ID."""
        # Setup
        arxiv_id = "2601.12345"

        # Execute
        result = get_arxiv_pdf_url(arxiv_id)

        # Assert
        assert result == "https://arxiv.org/pdf/2601.12345.pdf"

    def test_get_arxiv_pdf_url_with_version(self):
        """Generate PDF URL without version suffix."""
        # Setup
        arxiv_id = "2401.67890"

        # Execute
        result = get_arxiv_pdf_url(arxiv_id)

        # Assert
        assert result == "https://arxiv.org/pdf/2401.67890.pdf"


class TestSearchArxivByTitle:
    """Tests for search_arxiv_by_title function."""

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_search_arxiv_by_title_found(self, _mock_sleep, mock_get):
        """Find paper on arXiv by title."""
        # Setup
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2601.12345v1</id>
            <title>Test Paper Title: A Study on Machine Learning</title>
          </entry>
        </feed>
        """
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Execute
        result = search_arxiv_by_title("Test Paper Title: A Study on Machine Learning")

        # Assert
        assert result == "2601.12345"
        mock_get.assert_called_once()

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_search_arxiv_by_title_not_found(self, _mock_sleep, mock_get):
        """Return None when paper is not on arXiv."""
        # Setup
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>
        """
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Execute
        result = search_arxiv_by_title("Nonexistent Paper That Does Not Exist")

        # Assert
        assert result is None

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_search_arxiv_by_title_fuzzy_match(self, _mock_sleep, mock_get):
        """Find paper with slightly different title (fuzzy match)."""
        # Setup - title must match at least 80% of search words
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2601.99999v2</id>
            <title>Improving RAG Systems with Multi Agent Learning Techniques</title>
          </entry>
        </feed>
        """
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Execute - search with title that shares most words
        result = search_arxiv_by_title(
            "Improving RAG Systems with Multi Agent Learning"
        )

        # Assert
        assert result == "2601.99999"

    @patch("paper_collection.paper_metadata.arxiv_fetcher.requests.get")
    @patch("paper_collection.paper_metadata.arxiv_fetcher.time.sleep")
    def test_search_arxiv_by_title_request_failure(self, _mock_sleep, mock_get):
        """Return None on request failure."""
        # Setup
        import requests

        mock_get.side_effect = requests.RequestException("Connection failed")

        # Execute
        result = search_arxiv_by_title("Some Paper Title")

        # Assert
        assert result is None
