#!/usr/bin/env python3
"""
Unit tests for the PDF processing module.

Tests paper_collection/paper_summary/util/pdf_processing.py
"""

from paper_collection.paper_summary.util.pdf_processing import (
    get_pdf_cache,
    MAX_PDF_CHARS,
    PDFCache,
    set_pdf_cache,
)


class TestPDFCacheInit:
    """Tests for PDFCache initialization."""

    def test_pdf_cache_init(self, tmp_path):
        """Initialize cache with directory."""
        # Setup
        cache_dir = tmp_path / "pdf_cache"

        # Execute
        cache = PDFCache(cache_dir=str(cache_dir))

        # Assert
        assert cache.enabled is True
        assert cache.cache_dir == cache_dir
        assert cache_dir.exists()

    def test_pdf_cache_disabled(self):
        """No caching when dir=None."""
        # Setup & Execute
        cache = PDFCache(cache_dir=None)

        # Assert
        assert cache.enabled is False
        assert cache.cache_dir is None

    def test_pdf_cache_creates_directory(self, tmp_path):
        """Cache creates directory if it doesn't exist."""
        # Setup
        cache_dir = tmp_path / "nested" / "pdf_cache"
        assert not cache_dir.exists()

        # Execute
        pdf_cache = PDFCache(cache_dir=str(cache_dir))

        # Assert
        assert pdf_cache.enabled is True
        assert cache_dir.exists()


class TestPDFCacheOperations:
    """Tests for PDFCache get/set operations."""

    def test_pdf_cache_set_get(self, tmp_path):
        """Cache roundtrip - set and get."""
        # Setup
        cache_dir = tmp_path / "pdf_cache"
        cache = PDFCache(cache_dir=str(cache_dir))
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        text = "This is the extracted PDF text content."

        # Execute
        cache.set(url, text)
        result = cache.get(url)

        # Assert
        assert result == text

    def test_pdf_cache_miss(self, tmp_path):
        """Return None on cache miss."""
        # Setup
        cache_dir = tmp_path / "pdf_cache"
        cache = PDFCache(cache_dir=str(cache_dir))
        url = "https://arxiv.org/pdf/9999.99999.pdf"

        # Execute
        result = cache.get(url)

        # Assert
        assert result is None

    def test_pdf_cache_disabled_get(self):
        """Return None when cache is disabled."""
        # Setup
        cache = PDFCache(cache_dir=None)
        url = "https://arxiv.org/pdf/2401.12345.pdf"

        # Execute
        result = cache.get(url)

        # Assert
        assert result is None

    def test_pdf_cache_disabled_set(self):
        """No-op when cache is disabled."""
        # Setup
        cache = PDFCache(cache_dir=None)
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        text = "This is the extracted PDF text content."

        # Execute - should not raise
        cache.set(url, text)

        # Assert - get should still return None
        result = cache.get(url)
        assert result is None

    def test_pdf_cache_multiple_urls(self, tmp_path):
        """Cache different URLs independently."""
        # Setup
        cache_dir = tmp_path / "pdf_cache"
        cache = PDFCache(cache_dir=str(cache_dir))
        url1 = "https://arxiv.org/pdf/2401.00001.pdf"
        url2 = "https://arxiv.org/pdf/2401.00002.pdf"
        text1 = "Content of paper 1"
        text2 = "Content of paper 2"

        # Execute
        cache.set(url1, text1)
        cache.set(url2, text2)

        # Assert
        assert cache.get(url1) == text1
        assert cache.get(url2) == text2

    def test_pdf_cache_overwrite(self, tmp_path):
        """Overwrite existing cache entry."""
        # Setup
        cache_dir = tmp_path / "pdf_cache"
        cache = PDFCache(cache_dir=str(cache_dir))
        url = "https://arxiv.org/pdf/2401.12345.pdf"
        text1 = "Original content"
        text2 = "Updated content"

        # Execute
        cache.set(url, text1)
        cache.set(url, text2)

        # Assert
        assert cache.get(url) == text2


class TestMaxPdfChars:
    """Tests for MAX_PDF_CHARS constant."""

    def test_max_pdf_chars_constant(self):
        """MAX_PDF_CHARS is 50000."""
        # Assert
        assert MAX_PDF_CHARS == 50000

    def test_max_pdf_chars_is_int(self):
        """MAX_PDF_CHARS is an integer."""
        # Assert
        assert isinstance(MAX_PDF_CHARS, int)


class TestGlobalPdfCache:
    """Tests for global PDF cache functions."""

    def test_get_set_pdf_cache(self, tmp_path):
        """Test global get/set pdf cache functions."""
        # Setup
        cache_dir = tmp_path / "global_cache"
        cache = PDFCache(cache_dir=str(cache_dir))

        # Execute
        set_pdf_cache(cache)
        result = get_pdf_cache()

        # Assert
        assert result is cache
        assert result.enabled is True

    def test_set_pdf_cache_to_none(self):
        """Allow setting global cache to None."""
        # Setup
        set_pdf_cache(None)

        # Execute
        result = get_pdf_cache()

        # Assert
        assert result is None
