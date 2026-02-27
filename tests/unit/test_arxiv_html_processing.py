"""
Unit tests for arXiv HTML processing module.

Tests the arXiv HTML extraction at paper_collection/paper_summary/util/arxiv_html_processing.py
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestIsArxivUrl:
    """Tests for is_arxiv_url function."""

    def test_arxiv_abs_url(self) -> None:
        """Test detection of arXiv abstract URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("https://arxiv.org/abs/2601.06798")

        assert result is True

    def test_arxiv_pdf_url(self) -> None:
        """Test detection of arXiv PDF URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("https://arxiv.org/pdf/2601.06798.pdf")

        assert result is True

    def test_arxiv_html_url(self) -> None:
        """Test detection of arXiv HTML URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("https://arxiv.org/html/2601.06798")

        assert result is True

    def test_arxiv_url_case_insensitive(self) -> None:
        """Test that URL check is case insensitive."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("https://ARXIV.ORG/abs/2601.06798")

        assert result is True

    def test_non_arxiv_url(self) -> None:
        """Test detection of non-arXiv URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("https://example.com/paper.pdf")

        assert result is False

    def test_empty_url(self) -> None:
        """Test handling of empty URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            is_arxiv_url,
        )

        result = is_arxiv_url("")

        assert result is False


class TestGetArxivIdFromUrl:
    """Tests for get_arxiv_id_from_url function."""

    def test_extract_from_abs_url(self) -> None:
        """Test extracting arXiv ID from abstract URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://arxiv.org/abs/2601.06798")

        assert result == "2601.06798"

    def test_extract_from_pdf_url(self) -> None:
        """Test extracting arXiv ID from PDF URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://arxiv.org/pdf/2601.06798.pdf")

        assert result == "2601.06798"

    def test_extract_from_html_url(self) -> None:
        """Test extracting arXiv ID from HTML URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://arxiv.org/html/2601.06798")

        assert result == "2601.06798"

    def test_extract_with_version_suffix(self) -> None:
        """Test extracting arXiv ID from URL with version suffix."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://arxiv.org/abs/2601.06798v1")

        assert result == "2601.06798"

    def test_extract_old_format_id(self) -> None:
        """Test extracting older format arXiv ID (YYMM.NNNNN)."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://arxiv.org/abs/2401.12345")

        assert result == "2401.12345"

    def test_non_arxiv_url_returns_none(self) -> None:
        """Test that non-arXiv URL returns None."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("https://example.com/paper.pdf")

        assert result is None

    def test_invalid_url_returns_none(self) -> None:
        """Test that invalid URL returns None."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_arxiv_id_from_url,
        )

        result = get_arxiv_id_from_url("not-a-url")

        assert result is None


class TestGetHtmlUrlFromArxivUrl:
    """Tests for get_html_url_from_arxiv_url function."""

    def test_convert_abs_to_html(self) -> None:
        """Test converting abstract URL to HTML URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_html_url_from_arxiv_url,
        )

        result = get_html_url_from_arxiv_url("https://arxiv.org/abs/2601.06798")

        assert result == "https://arxiv.org/html/2601.06798"

    def test_convert_pdf_to_html(self) -> None:
        """Test converting PDF URL to HTML URL."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_html_url_from_arxiv_url,
        )

        result = get_html_url_from_arxiv_url("https://arxiv.org/pdf/2601.06798.pdf")

        assert result == "https://arxiv.org/html/2601.06798"

    def test_html_url_unchanged(self) -> None:
        """Test that HTML URL returns same format."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_html_url_from_arxiv_url,
        )

        result = get_html_url_from_arxiv_url("https://arxiv.org/html/2601.06798")

        assert result == "https://arxiv.org/html/2601.06798"

    def test_non_arxiv_returns_none(self) -> None:
        """Test that non-arXiv URL returns None."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            get_html_url_from_arxiv_url,
        )

        result = get_html_url_from_arxiv_url("https://example.com/paper.pdf")

        assert result is None


class TestCheckHtmlAvailable:
    """Tests for check_html_available function."""

    def test_html_available_returns_true(self) -> None:
        """Test that available HTML returns True."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            check_html_available,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("requests.head", return_value=mock_response):
            result = check_html_available("2601.06798")

        assert result is True

    def test_html_not_available_returns_false(self) -> None:
        """Test that 404 response returns False."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            check_html_available,
        )

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.head", return_value=mock_response):
            result = check_html_available("2601.06798")

        assert result is False

    def test_connection_error_returns_false(self) -> None:
        """Test that connection error returns False."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            check_html_available,
        )

        with patch("requests.head", side_effect=Exception("Connection error")):
            result = check_html_available("2601.06798")

        assert result is False


class TestDownloadHtml:
    """Tests for download_html function."""

    def test_successful_download(self) -> None:
        """Test successful HTML download."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_html,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"

        with patch("requests.get", return_value=mock_response):
            result = download_html("https://arxiv.org/html/2601.06798")

        assert result == "<html><body>Test content</body></html>"

    def test_404_raises_exception(self) -> None:
        """Test that 404 response raises exception."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_html,
        )

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(Exception) as exc_info:
                download_html("https://arxiv.org/html/2601.06798")

        assert "404" in str(exc_info.value)

    def test_non_200_raises_exception(self) -> None:
        """Test that non-200/404 response raises exception."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_html,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(Exception) as exc_info:
                download_html("https://arxiv.org/html/2601.06798")

        assert "500" in str(exc_info.value)


class TestExtractTextFromHtml:
    """Tests for extract_text_from_html function."""

    def test_extract_text_basic(self) -> None:
        """Test basic text extraction from HTML."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_text_from_html,
        )

        html_content = """
        <html>
        <body>
            <article class="ltx_document">
                <section class="ltx_section">
                    <h2 class="ltx_title">Introduction</h2>
                    <div class="ltx_para">
                        <p class="ltx_p">This is the introduction paragraph.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """

        result = extract_text_from_html(html_content)

        assert "Introduction" in result
        assert "introduction paragraph" in result

    def test_extract_text_removes_scripts(self) -> None:
        """Test that script elements are removed."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_text_from_html,
        )

        html_content = """
        <html>
        <body>
            <script>var x = 'should not appear';</script>
            <article class="ltx_document">
                <section class="ltx_section">
                    <div class="ltx_para">
                        <p class="ltx_p">Actual content.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """

        result = extract_text_from_html(html_content)

        assert "should not appear" not in result
        assert "Actual content" in result

    def test_extract_text_respects_max_chars(self) -> None:
        """Test that extraction respects max_chars limit."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_text_from_html,
        )

        html_content = """
        <html>
        <body>
            <article class="ltx_document">
                <section class="ltx_section">
                    <div class="ltx_para">
                        <p class="ltx_p">A very long paragraph that exceeds the limit.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """

        result = extract_text_from_html(html_content, max_chars=20)

        assert len(result) <= 20

    def test_extract_text_multiple_sections(self) -> None:
        """Test extraction from multiple sections."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_text_from_html,
        )

        html_content = """
        <html>
        <body>
            <article class="ltx_document">
                <section class="ltx_section">
                    <h2 class="ltx_title">Section 1</h2>
                    <div class="ltx_para">
                        <p class="ltx_p">Content 1.</p>
                    </div>
                </section>
                <section class="ltx_section">
                    <h2 class="ltx_title">Section 2</h2>
                    <div class="ltx_para">
                        <p class="ltx_p">Content 2.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """

        result = extract_text_from_html(html_content)

        assert "Section 1" in result
        assert "Content 1" in result
        assert "Section 2" in result
        assert "Content 2" in result


class TestExtractFiguresFromHtml:
    """Tests for extract_figures_from_html function."""

    def test_extract_figures_basic(self) -> None:
        """Test basic figure extraction from HTML."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_figures_from_html,
        )

        html_content = """
        <html>
        <body>
            <figure class="ltx_figure">
                <img src="x1.png" alt="Figure 1"/>
                <figcaption class="ltx_caption">Figure 1: Test figure caption.</figcaption>
            </figure>
        </body>
        </html>
        """

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"fake image data"
            mock_get.return_value = mock_response

            result = extract_figures_from_html(
                html_content,
                base_url="https://arxiv.org/html/2601.06798",
                download_images=True,
            )

        assert len(result) == 1
        assert result[0]["figure_num"] == 1
        assert "Test figure caption" in result[0]["caption"]
        assert result[0]["image_url"] == ("https://arxiv.org/html/2601.06798/x1.png")
        assert result[0]["image_data"] == b"fake image data"

    def test_extract_figures_multiple(self) -> None:
        """Test extraction of multiple figures."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_figures_from_html,
        )

        html_content = """
        <html>
        <body>
            <figure class="ltx_figure">
                <img src="x1.png"/>
                <figcaption class="ltx_caption">Figure 1</figcaption>
            </figure>
            <figure class="ltx_figure">
                <img src="x2.png"/>
                <figcaption class="ltx_caption">Figure 2</figcaption>
            </figure>
        </body>
        </html>
        """

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"fake image"
            mock_get.return_value = mock_response

            result = extract_figures_from_html(
                html_content,
                base_url="https://arxiv.org/html/2601.06798",
                download_images=True,
            )

        assert len(result) == 2
        assert result[0]["figure_num"] == 1
        assert result[1]["figure_num"] == 2

    def test_extract_figures_no_download(self) -> None:
        """Test extraction without downloading images."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_figures_from_html,
        )

        html_content = """
        <html>
        <body>
            <figure class="ltx_figure">
                <img src="x1.png"/>
                <figcaption class="ltx_caption">Figure 1</figcaption>
            </figure>
        </body>
        </html>
        """

        result = extract_figures_from_html(
            html_content,
            base_url="https://arxiv.org/html/2601.06798",
            download_images=False,
        )

        assert len(result) == 1
        assert result[0]["image_data"] is None
        assert result[0]["image_url"] == ("https://arxiv.org/html/2601.06798/x1.png")

    def test_extract_figures_skips_data_uris(self) -> None:
        """Test that data URIs (base64 images) are skipped."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_figures_from_html,
        )

        html_content = """
        <html>
        <body>
            <figure class="ltx_figure">
                <img src="data:image/png;base64,iVBORw0KGg..."/>
                <figcaption class="ltx_caption">Logo</figcaption>
            </figure>
            <figure class="ltx_figure">
                <img src="x1.png"/>
                <figcaption class="ltx_caption">Figure 1</figcaption>
            </figure>
        </body>
        </html>
        """

        result = extract_figures_from_html(
            html_content,
            base_url="https://arxiv.org/html/2601.06798",
            download_images=False,
        )

        assert len(result) == 1
        assert "x1.png" in result[0]["image_url"]

    def test_extract_figures_saves_to_output_dir(self, tmp_path: Path) -> None:
        """Test that figures are saved to output directory."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            extract_figures_from_html,
        )

        html_content = """
        <html>
        <body>
            <figure class="ltx_figure">
                <img src="x1.png"/>
                <figcaption class="ltx_caption">Figure 1</figcaption>
            </figure>
        </body>
        </html>
        """

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"fake image data"
            mock_get.return_value = mock_response

            result = extract_figures_from_html(
                html_content,
                base_url="https://arxiv.org/html/2601.06798",
                paper_id="2601.06798",
                output_dir=tmp_path,
                download_images=True,
            )

        assert len(result) == 1
        assert result[0]["path"] != ""
        saved_path = Path(result[0]["path"])
        assert saved_path.exists()
        assert saved_path.read_bytes() == b"fake image data"


class TestDownloadArxivHtmlWithFigures:
    """Tests for download_arxiv_html_with_figures function."""

    def test_successful_download_with_figures(self) -> None:
        """Test successful download and extraction."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_arxiv_html_with_figures,
        )

        html_content = """
        <html>
        <body>
            <article class="ltx_document">
                <section class="ltx_section">
                    <div class="ltx_para">
                        <p class="ltx_p">Test paragraph.</p>
                    </div>
                </section>
            </article>
            <figure class="ltx_figure">
                <img src="x1.png"/>
                <figcaption class="ltx_caption">Figure 1</figcaption>
            </figure>
        </body>
        </html>
        """

        with patch(
            "paper_collection.paper_summary.util.arxiv_html_processing.download_html",
            return_value=html_content,
        ):
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.content = b"image"
                mock_get.return_value = mock_response

                result = download_arxiv_html_with_figures(
                    "https://arxiv.org/abs/2601.06798"
                )

        assert result["source"] == "html"
        assert result["html_url"] == "https://arxiv.org/html/2601.06798"
        assert "Test paragraph" in result["text"]
        assert len(result["figures"]) == 1

    def test_download_without_figures(self) -> None:
        """Test download with extract_figures=False."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_arxiv_html_with_figures,
        )

        html_content = """
        <html>
        <body>
            <article class="ltx_document">
                <section class="ltx_section">
                    <div class="ltx_para">
                        <p class="ltx_p">Test paragraph.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """

        with patch(
            "paper_collection.paper_summary.util.arxiv_html_processing.download_html",
            return_value=html_content,
        ):
            result = download_arxiv_html_with_figures(
                "https://arxiv.org/abs/2601.06798",
                extract_figures=False,
            )

        assert result["source"] == "html"
        assert "Test paragraph" in result["text"]
        assert result["figures"] == []

    def test_invalid_url_raises_exception(self) -> None:
        """Test that invalid URL raises exception."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            download_arxiv_html_with_figures,
        )

        with pytest.raises(Exception) as exc_info:
            download_arxiv_html_with_figures("https://example.com/paper.pdf")

        assert "Could not extract arXiv ID" in str(exc_info.value)


class TestModuleConstants:
    """Tests for module constants and flags."""

    def test_max_html_chars_defined(self) -> None:
        """Test that MAX_HTML_CHARS is defined."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            MAX_HTML_CHARS,
        )

        assert isinstance(MAX_HTML_CHARS, int)
        assert MAX_HTML_CHARS > 0

    def test_bs4_available_flag(self) -> None:
        """Test that BS4_AVAILABLE flag is defined."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            BS4_AVAILABLE,
        )

        assert isinstance(BS4_AVAILABLE, bool)

    def test_retry_constants_defined(self) -> None:
        """Test that retry constants are defined."""
        from paper_collection.paper_summary.util.arxiv_html_processing import (
            RETRY_BASE_DELAY,
            RETRY_MAX_DELAY,
        )

        assert isinstance(RETRY_BASE_DELAY, int)
        assert isinstance(RETRY_MAX_DELAY, int)
        assert RETRY_MAX_DELAY >= RETRY_BASE_DELAY
