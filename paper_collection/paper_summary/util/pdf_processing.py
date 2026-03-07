#!/usr/bin/env python3
"""
PDF Processing Module

Provides PDF downloading, text extraction, figure extraction, and caching.
Extracted from summary_generation.py for modularity.
"""

import io
from pathlib import Path
from typing import Optional

from .pdf_download import download_pdf_bytes

try:
    import PyPDF2

    PDF_SUPPORT = True
except ImportError:
    PyPDF2 = None
    PDF_SUPPORT = False


# PDF text extraction limits
# Note: Prompt template is ~50K chars, model context is ~128K tokens (~400K chars)
# Leaving room for template + response, limit paper text to 50K
MAX_PDF_CHARS = 50000

# Re-export download_pdf_bytes for backward compatibility
__all__ = [
    "download_pdf_bytes",
    "download_pdf_text",
    "download_pdf_with_figures",
    "extract_text_from_pdf_bytes",
    "extract_and_store_figures",
    "PDFCache",
    "get_pdf_cache",
    "set_pdf_cache",
    "store_figures_in_db",
    "PDF_SUPPORT",
    "MAX_PDF_CHARS",
]


# ==============================================================================
# PDF Cache - Avoid re-downloading PDFs
# ==============================================================================
class PDFCache:
    """
    Simple file-based cache for downloaded PDFs.

    Caches PDF text (not raw PDF) to avoid re-downloading and re-parsing.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize PDF cache.

        Args:
            cache_dir: Directory to store cached PDF text.
                      If None, caching is disabled.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.enabled = cache_dir is not None

        if self.enabled and self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key from URL."""
        import hashlib

        return hashlib.md5(url.encode()).hexdigest()

    def _get_cache_path(self, url: str) -> Optional[Path]:
        """Get the cache file path for a URL."""
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{self._get_cache_key(url)}.txt"

    def get(self, url: str) -> Optional[str]:
        """
        Get cached PDF text.

        Args:
            url: PDF URL.

        Returns:
            Cached text if found, None otherwise.
        """
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(url)
        if cache_path is not None and cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def set(self, url: str, text: str):
        """
        Cache PDF text.

        Args:
            url: PDF URL.
            text: Extracted text to cache.
        """
        if not self.enabled:
            return

        cache_path = self._get_cache_path(url)
        if cache_path is None:
            return
        try:
            cache_path.write_text(text, encoding="utf-8")
        except Exception as e:
            print(f"  Warning: Could not cache PDF: {e}")


# Global PDF cache (initialized in main)
_pdf_cache: Optional[PDFCache] = None


def get_pdf_cache() -> Optional[PDFCache]:
    """Get the global PDF cache instance."""
    return _pdf_cache


def set_pdf_cache(cache: PDFCache):
    """Set the global PDF cache instance."""
    global _pdf_cache
    _pdf_cache = cache


# ==============================================================================
# PDF Text Extraction Functions
# ==============================================================================
def extract_text_from_pdf_bytes(
    pdf_bytes: bytes,
    max_chars: int = MAX_PDF_CHARS,
) -> str:
    """
    Extract text from PDF bytes.

    Args:
        pdf_bytes: Raw PDF bytes.
        max_chars: Maximum characters to extract.

    Returns:
        Extracted text from the PDF.
    """
    if not PDF_SUPPORT:
        raise ImportError(
            "PyPDF2 is required for PDF extraction.\n"
            "Install it with: pip install PyPDF2"
        )

    pdf_file = io.BytesIO(pdf_bytes)
    pdf_reader = PyPDF2.PdfReader(pdf_file)

    text_parts = []
    total_chars = 0

    for page_num, page in enumerate(pdf_reader.pages):
        page_text = page.extract_text()
        if page_text:
            text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
            total_chars += len(page_text)

            if total_chars >= max_chars:
                print(f"  Reached {max_chars} char limit at page {page_num + 1}")
                break

    full_text = "\n\n".join(text_parts)
    print(f"  Extracted {len(full_text)} characters from {len(text_parts)} pages")
    return full_text[:max_chars]


def download_pdf_text(
    pdf_url: str,
    max_chars: int = MAX_PDF_CHARS,
    max_retries: int = 3,
    use_cache: bool = True,
) -> str:
    """
    Download a PDF from URL and extract its text content.

    Args:
        pdf_url: URL to the PDF file.
        max_chars: Maximum characters to extract (to avoid token limits).
        max_retries: Maximum retry attempts for download failures.
        use_cache: Whether to use PDF cache.

    Returns:
        Extracted text from the PDF.
    """
    if not PDF_SUPPORT:
        raise ImportError(
            "PyPDF2 is required for PDF extraction.\n"
            "Install it with: pip install PyPDF2"
        )

    # Check cache first
    cache = get_pdf_cache()
    if use_cache and cache:
        cached_text = cache.get(pdf_url)
        if cached_text:
            print(f"  Using cached PDF text ({len(cached_text)} chars)")
            return cached_text[:max_chars]

    # Download PDF bytes
    pdf_bytes = download_pdf_bytes(pdf_url, max_retries)

    # Extract text
    full_text = extract_text_from_pdf_bytes(pdf_bytes, max_chars)

    # Cache the full text
    if use_cache and cache:
        cache.set(pdf_url, full_text)

    return full_text[:max_chars]


def download_pdf_with_figures(
    pdf_url: str,
    paper_id: Optional[str] = None,
    max_chars: int = MAX_PDF_CHARS,
    max_retries: int = 3,
    use_cache: bool = True,
    extract_figures: bool = True,
    figures_output_dir: Optional[Path] = None,
) -> dict:
    """
    Download a PDF and extract both text and figures (Stage 0).

    This is the combined extraction function that downloads the PDF once
    and extracts both text content and figures.

    Args:
        pdf_url: URL to the PDF file.
        paper_id: Paper ID for organizing figure output.
        max_chars: Maximum characters to extract for text.
        max_retries: Maximum retry attempts for download failures.
        use_cache: Whether to use PDF cache for text.
        extract_figures: Whether to extract figures from the PDF.
        figures_output_dir: Directory to save extracted figures.

    Returns:
        Dictionary with:
        - text: Extracted text from the PDF
        - figures: List of extracted figure dicts (if extract_figures=True)
        - pdf_bytes: Raw PDF bytes (for further processing)
    """
    result = {
        "text": "",
        "figures": [],
        "pdf_bytes": None,
    }

    # Check text cache first
    cache = get_pdf_cache()
    cached_text = None
    if use_cache and cache:
        cached_text = cache.get(pdf_url)
        if cached_text:
            print(f"  Using cached PDF text ({len(cached_text)} chars)")
            result["text"] = cached_text[:max_chars]

    # Download PDF bytes (needed for figures or if text not cached)
    pdf_bytes = None
    if not cached_text or extract_figures:
        pdf_bytes = download_pdf_bytes(pdf_url, max_retries)
        result["pdf_bytes"] = pdf_bytes

    # Extract text if not cached
    if not cached_text and pdf_bytes:
        result["text"] = extract_text_from_pdf_bytes(pdf_bytes, max_chars)
        if use_cache and cache:
            cache.set(pdf_url, result["text"])

    # Extract figures if requested
    if extract_figures and pdf_bytes:
        try:
            from . import figure_extraction_from_pdf as fig_module

            if fig_module.PYMUPDF_AVAILABLE:
                if paper_id is None:
                    paper_id = fig_module.extract_paper_id_from_url(pdf_url)

                print(f"  Extracting figures for paper {paper_id}...")
                figures = fig_module.extract_figures_from_pdf_bytes(
                    pdf_bytes=pdf_bytes,
                    paper_id=paper_id,
                    output_dir=figures_output_dir,
                )
                result["figures"] = figures
                print(f"  Extracted {len(figures)} figures")
            else:
                print("  PyMuPDF not available, skipping figure extraction")
        except ImportError as e:
            print(f"  Could not import figure_extraction_from_pdf module: {e}")
        except Exception as e:
            print(f"  Error extracting figures: {e}")

    return result


def store_figures_in_db(
    paper_db_id: int,
    figures: list[dict],
    store_image_data: bool = True,
    db=None,
) -> list[int]:
    """
    Store extracted figures in the paper_images database table.

    Args:
        paper_db_id: The paper's database ID (from papers table).
        figures: List of figure dicts from extract_figures_from_pdf_bytes().
            Each dict should have: filename, figure_num, page, caption, path
        store_image_data: Whether to store image binary data in DB.
        db: Optional existing PaperDB connection to reuse.

    Returns:
        List of created image IDs in the database.
    """
    try:
        import sys

        # Navigate up to paper_collection/ where util/paper_db.py is located
        # util/ -> paper_summary/ -> paper_collection/
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from core.paper_db import PaperDB
    except ImportError as e:
        print(f"  Could not import paper_db: {e}")
        return []

    image_ids = []
    should_close = db is None
    if db is None:
        db = PaperDB()

    try:
        for fig in figures:
            file_path = fig.get("path", "")
            figure_name = fig.get("filename", f"figure_{fig.get('figure_num', 0)}.png")
            caption = fig.get("caption", "")

            image_data = None
            if store_image_data:
                # First try to use image_data from figure dict (in-memory extraction)
                if fig.get("image_data"):
                    image_data = fig["image_data"]
                # Fall back to reading from file path if available
                elif file_path:
                    try:
                        with open(file_path, "rb") as f:
                            image_data = f.read()
                    except Exception as e:
                        msg = f"  Warning: Could not read image {file_path}: {e}"
                        print(msg)

            image_id = db.add_paper_image(
                paper_id=paper_db_id,
                file_path=file_path,
                figure_name=figure_name,
                caption=caption,
                image_data=image_data,
            )

            if image_id:
                image_ids.append(image_id)
                print(f"    Stored {figure_name} (id={image_id})")

            # Clear image data after storing to free memory
            image_data = None

    finally:
        if should_close:
            db.close()

    return image_ids


def extract_and_store_figures(
    pdf_url: str,
    paper_db_id: int,
    figures_output_dir: Optional[Path] = None,
    store_image_data: bool = True,
) -> dict:
    """
    Extract figures from a PDF and store them in the database.

    This is a convenience function that combines figure extraction
    and database storage.

    Args:
        pdf_url: URL to the PDF file.
        paper_db_id: The paper's database ID.
        figures_output_dir: Directory to save extracted figure files.
        store_image_data: Whether to store image binary data in DB.

    Returns:
        Dictionary with:
        - figures: List of extracted figure dicts
        - image_ids: List of database image IDs
    """
    result = {"figures": [], "image_ids": []}

    try:
        from . import figure_extraction_from_pdf as fig_module

        if not fig_module.PYMUPDF_AVAILABLE:
            print("  PyMuPDF not available, skipping figure extraction")
            return result

        paper_id = fig_module.extract_paper_id_from_url(pdf_url)
        print(f"  Extracting figures for paper {paper_id}...")

        pdf_bytes = download_pdf_bytes(pdf_url)

        figures = fig_module.extract_figures_from_pdf_bytes(
            pdf_bytes=pdf_bytes,
            paper_id=paper_id,
            output_dir=figures_output_dir,
        )
        result["figures"] = figures

        if figures:
            print(f"  Extracted {len(figures)} figures, storing in database...")
            image_ids = store_figures_in_db(
                paper_db_id=paper_db_id,
                figures=figures,
                store_image_data=store_image_data,
            )
            result["image_ids"] = image_ids

    except ImportError as e:
        print(f"  Could not import figure_extraction_from_pdf module: {e}")
    except Exception as e:
        print(f"  Error extracting/storing figures: {e}")

    return result
