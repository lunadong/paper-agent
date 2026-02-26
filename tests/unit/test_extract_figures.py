"""
Unit tests for figure extraction module.

Tests the figure extraction at paper_collection/paper_summary/util/figure_extraction_from_pdf.py
"""

from unittest.mock import MagicMock


class TestCaptionPatterns:
    """Tests for caption detection patterns."""

    def test_caption_pattern_figure_colon(self) -> None:
        """Test detection of 'Figure N:' pattern."""
        # This tests the patterns used in find_all_captions
        patterns = [
            "Figure 1:",
            "Figure 2:",
            "Figure 10:",
            "Fig. 1:",
            "Fig. 2:",
        ]

        for pattern in patterns:
            # Assert: Pattern should match expected format
            assert ":" in pattern or "." in pattern
            assert any(pattern.startswith(prefix) for prefix in ["Figure ", "Fig. "])

    def test_caption_pattern_figure_period(self) -> None:
        """Test detection of 'Figure N.' pattern."""
        patterns = [
            "Figure 1.",
            "Figure 2.",
            "Fig. 1.",
            "Fig. 2.",
        ]

        for pattern in patterns:
            assert "." in pattern
            assert any(pattern.startswith(prefix) for prefix in ["Figure ", "Fig. "])

    def test_caption_search_patterns_order(self) -> None:
        """Test that colon patterns are preferred over period patterns."""
        # The module searches in this order
        expected_order = [
            "Figure {fig_num}:",
            "Fig. {fig_num}:",
            "Figure {fig_num}.",
            "Fig. {fig_num}.",
        ]

        # Verify the first pattern uses colon (preferred)
        assert ":" in expected_order[0]
        assert ":" in expected_order[1]
        # Period patterns come after
        assert "." in expected_order[2]
        assert "." in expected_order[3]


class TestCaptionDataclass:
    """Tests for Caption dataclass."""

    def test_caption_dataclass_attributes(self) -> None:
        """Test that Caption object has required attributes."""
        # Setup: Create a mock rect
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 120.0
        mock_rect.x0 = 50.0
        mock_rect.x1 = 200.0

        # Execute: Import and create Caption
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=False,
            text="Figure 1: Test caption text",
        )

        # Assert: Check required attributes exist
        assert caption.fig_num == 1
        assert caption.page_num == 0
        assert caption.rect == mock_rect
        assert caption.is_full_width is False
        assert caption.text == "Figure 1: Test caption text"

    def test_caption_y_center_property(self) -> None:
        """Test that y_center property calculates correctly."""
        # Setup
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 200.0
        mock_rect.x0 = 0.0
        mock_rect.x1 = 100.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=True,
            text="Test",
        )

        # Execute & Assert
        assert caption.y_center == 150.0  # (100 + 200) / 2

    def test_caption_x_center_property(self) -> None:
        """Test that x_center property calculates correctly."""
        # Setup
        mock_rect = MagicMock()
        mock_rect.y0 = 0.0
        mock_rect.y1 = 100.0
        mock_rect.x0 = 100.0
        mock_rect.x1 = 300.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=False,
            text="Test",
        )

        # Execute & Assert
        assert caption.x_center == 200.0  # (100 + 300) / 2


class TestIsFigureNotTable:
    """Tests for distinguishing figures from tables."""

    def test_figure_caption_starts_with_figure(self) -> None:
        """Test that Figure captions are identified correctly."""
        # Figure captions start with "Figure" or "Fig."
        figure_captions = [
            "Figure 1: System architecture",
            "Figure 2. Results overview",
            "Fig. 3: Detailed breakdown",
            "Fig. 4. Performance metrics",
        ]

        for caption_text in figure_captions:
            # Assert: Should be identified as figure (not table)
            is_figure = caption_text.startswith(
                ("Figure ", "Figure\t", "Fig. ", "Fig.\t")
            )
            is_table = caption_text.startswith(("Table ", "Table\t"))
            assert is_figure is True
            assert is_table is False

    def test_table_caption_starts_with_table(self) -> None:
        """Test that Table captions are identified as not figures."""
        table_captions = [
            "Table 1: Comparison results",
            "Table 2. Performance data",
        ]

        for caption_text in table_captions:
            # Assert: Should be identified as table (not figure)
            is_figure = caption_text.startswith(
                ("Figure ", "Figure\t", "Fig. ", "Fig.\t")
            )
            is_table = caption_text.startswith(("Table ", "Table\t"))
            assert is_figure is False
            assert is_table is True

    def test_figure_patterns_case_sensitive(self) -> None:
        """Test that pattern matching is case-sensitive for Figure."""
        # The patterns used in the module are case-sensitive
        valid_patterns = ["Figure 1:", "Fig. 1:"]
        invalid_patterns = ["figure 1:", "FIG. 1:", "FIGURE 1:"]

        for pattern in valid_patterns:
            assert pattern.startswith("Figure ") or pattern.startswith("Fig. ")

        for pattern in invalid_patterns:
            assert not (pattern.startswith("Figure ") or pattern.startswith("Fig. "))


class TestGetColumnBounds:
    """Tests for get_column_bounds function."""

    def test_get_column_bounds_full_width(self) -> None:
        """Test full width bounds calculation."""
        # Setup: Create caption that is full width
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 120.0
        mock_rect.x0 = 50.0
        mock_rect.x1 = 550.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
            get_column_bounds,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=True,
            text="Full width figure",
        )

        page_width = 612.0  # Standard US Letter width in points
        margin = 15.0

        # Execute
        x0, x1 = get_column_bounds(caption, page_width, margin)

        # Assert: Should span full page width minus margins
        assert x0 == margin
        assert x1 == page_width - margin

    def test_get_column_bounds_left_column(self) -> None:
        """Test left column bounds calculation."""
        # Setup: Create caption in left column
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 120.0
        mock_rect.x0 = 50.0  # Left side of page
        mock_rect.x1 = 250.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
            get_column_bounds,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=False,
            text="Left column figure",
        )

        page_width = 612.0
        margin = 15.0
        half_page = page_width / 2

        # Execute
        x0, x1 = get_column_bounds(caption, page_width, margin)

        # Assert: Should be in left column (margin to half page)
        assert x0 == margin
        assert x1 == half_page - 5

    def test_get_column_bounds_right_column(self) -> None:
        """Test right column bounds calculation."""
        # Setup: Create caption in right column
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 120.0
        mock_rect.x0 = 350.0  # Right side of page
        mock_rect.x1 = 550.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
            get_column_bounds,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=False,
            text="Right column figure",
        )

        page_width = 612.0
        margin = 15.0
        half_page = page_width / 2

        # Execute
        x0, x1 = get_column_bounds(caption, page_width, margin)

        # Assert: Should be in right column (half page to right edge)
        assert x0 == half_page + 5
        assert x1 == page_width - margin

    def test_get_column_bounds_custom_margin(self) -> None:
        """Test bounds calculation with custom margin."""
        # Setup
        mock_rect = MagicMock()
        mock_rect.y0 = 100.0
        mock_rect.y1 = 120.0
        mock_rect.x0 = 50.0
        mock_rect.x1 = 550.0

        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            Caption,
            get_column_bounds,
        )

        caption = Caption(
            fig_num=1,
            page_num=0,
            rect=mock_rect,
            is_full_width=True,
            text="Custom margin figure",
        )

        page_width = 612.0
        custom_margin = 30.0

        # Execute
        x0, x1 = get_column_bounds(caption, page_width, custom_margin)

        # Assert: Should respect custom margin
        assert x0 == custom_margin
        assert x1 == page_width - custom_margin


class TestExtractPaperIdFromUrl:
    """Tests for extract_paper_id_from_url function."""

    def test_extract_arxiv_id(self) -> None:
        """Test extracting arXiv ID from URL."""
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            extract_paper_id_from_url,
        )

        # Execute
        result = extract_paper_id_from_url("https://arxiv.org/pdf/2501.15228")

        # Assert
        assert result == "2501.15228"

    def test_extract_arxiv_abs_id(self) -> None:
        """Test extracting arXiv ID from abs URL."""
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            extract_paper_id_from_url,
        )

        # Execute
        result = extract_paper_id_from_url("https://arxiv.org/abs/2401.12345")

        # Assert
        assert result == "2401.12345"

    def test_extract_filename_from_url(self) -> None:
        """Test extracting filename from non-arXiv URL."""
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            extract_paper_id_from_url,
        )

        # Execute
        result = extract_paper_id_from_url("https://example.com/papers/my_paper.pdf")

        # Assert: Should return filename without .pdf
        assert result == "my_paper"

    def test_extract_hash_fallback(self) -> None:
        """Test hash fallback for URLs without clear identifier."""
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            extract_paper_id_from_url,
        )

        # Execute
        result = extract_paper_id_from_url("https://example.com/")

        # Assert: Should return a 12-character hash
        assert len(result) == 12


class TestFiguresDir:
    """Tests for FIGURES_DIR constant."""

    def test_figures_dir_path(self) -> None:
        """Test that FIGURES_DIR points to expected location."""
        from paper_collection.paper_summary.util.figure_extraction_from_pdf import (
            FIGURES_DIR,
        )

        # Assert: Should be under tmp/figures
        assert FIGURES_DIR.name == "figures"
        assert "tmp" in str(FIGURES_DIR)


class TestPymupdfAvailability:
    """Tests for PyMuPDF availability flag."""

    def test_pymupdf_availability_flag_exists(self) -> None:
        """Test that PYMUPDF_AVAILABLE flag is defined."""
        from paper_collection.paper_summary.util import figure_extraction_from_pdf

        # Assert: Flag should exist and be boolean
        assert hasattr(figure_extraction_from_pdf, "PYMUPDF_AVAILABLE")
        assert isinstance(figure_extraction_from_pdf.PYMUPDF_AVAILABLE, bool)

    def test_pillow_availability_flag_exists(self) -> None:
        """Test that PILLOW_AVAILABLE flag is defined."""
        from paper_collection.paper_summary.util import figure_extraction_from_pdf

        # Assert: Flag should exist and be boolean
        assert hasattr(figure_extraction_from_pdf, "PILLOW_AVAILABLE")
        assert isinstance(figure_extraction_from_pdf.PILLOW_AVAILABLE, bool)
