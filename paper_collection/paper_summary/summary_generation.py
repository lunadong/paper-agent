#!/usr/bin/env python3
"""
Paper Summary Generation using LLM APIs

This script generates structured JSON summaries of research papers using
LLM APIs (Google Gemini via wearables-ape.io or Google AI Studio).

Setup:
    1. Install the required packages:
       pip install requests pyyaml PyPDF2
       # For Google API: pip install google-generativeai

    2. Set your API key in config.yaml or as environment variable:
       export GEMINI_API_KEY="your-api-key"

Usage:
    python summary_generation.py --pdf-url "https://arxiv.org/pdf/2501.15228"
    python summary_generation.py --pdf-url "URL" --model "gemini-1.5-pro"
    python summary_generation.py --help
"""

import argparse
import io
import json
import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: requests package not installed.")
    print("Install it with: pip install requests")
    exit(1)

try:
    import yaml
except ImportError:
    yaml = None

# Try to import PDF parsing libraries
try:
    import PyPDF2

    PDF_SUPPORT = True
except ImportError:
    PyPDF2 = None
    PDF_SUPPORT = False


# API configuration - read from config.yaml
# Limit PDF text to ~63K chars so final prompt stays under ~80K
# (accounts for ~17K template overhead)
MAX_PDF_CHARS = 63000

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds
RETRY_MAX_DELAY = 30  # seconds
# Rate limit and server errors
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ==============================================================================
# Rate Limiter - Controls API requests per minute
# ==============================================================================
class RateLimiter:
    """
    Token bucket rate limiter for controlling API request rate.

    Thread-safe implementation that limits requests per minute.
    """

    def __init__(self, requests_per_minute: int):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute.
                                 If 0 or negative, rate limiting is disabled.
        """
        self.requests_per_minute = requests_per_minute
        self.enabled = requests_per_minute > 0
        self.min_interval = 60.0 / requests_per_minute if self.enabled else 0
        self.last_request_time = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        """
        Wait until a request is allowed, then consume one token.

        This method blocks if necessary to maintain the rate limit.
        """
        if not self.enabled:
            return

        with self._lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            wait_time = self.min_interval - time_since_last

            if wait_time > 0:
                print(f"  [Rate limit] Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)

            self.last_request_time = time.time()


# Global rate limiter (initialized in main)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter):
    """Set the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


# ==============================================================================
# Checkpoint Manager - Saves/loads batch progress for resume capability
# ==============================================================================
class CheckpointManager:
    """
    Manages checkpointing for batch processing.

    Saves progress to a JSON file so processing can resume after interruption.
    """

    def __init__(self, checkpoint_file: Optional[str] = None):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_file: Path to checkpoint file.
                If None, checkpointing is disabled.
        """
        self.checkpoint_file = checkpoint_file
        self.enabled = checkpoint_file is not None
        self.data = {
            "started_at": None,
            "updated_at": None,
            "total_papers": 0,
            "completed_ids": [],
            "failed_ids": [],
            "in_progress_id": None,
        }
        self._lock = threading.Lock()

    def load(self) -> bool:
        """
        Load checkpoint from file.

        Returns:
            True if checkpoint was loaded, False otherwise.
        """
        if not self.enabled or self.checkpoint_file is None:
            return False
        if not os.path.exists(self.checkpoint_file):
            return False

        try:
            with open(self.checkpoint_file, "r") as f:
                self.data = json.load(f)
            completed = len(self.data.get("completed_ids", []))
            retryable = len(self.data.get("errors", {}))
            abstract_only = len(self.data.get("abstract_only", {}))
            # Legacy: also count permanent_errors (will be reprocessed)
            permanent = len(self.data.get("permanent_errors", {}))
            print(
                f"Loaded checkpoint: {completed} completed, "
                f"{retryable} retryable errors, {abstract_only} abstract_only"
            )
            if permanent > 0:
                print(
                    f"  Note: {permanent} legacy permanent_errors will be "
                    f"reprocessed with abstract fallback"
                )
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load checkpoint: {e}")
            return False

    def save(self):
        """Save checkpoint to file."""
        if not self.enabled:
            return

        with self._lock:
            self.data["updated_at"] = datetime.now().isoformat()
            if self.checkpoint_file is None:
                return
            try:
                with open(self.checkpoint_file, "w") as f:
                    json.dump(self.data, f, indent=2)
            except IOError as e:
                print(f"Warning: Could not save checkpoint: {e}")

    def start_batch(self, total_papers: int, paper_ids: list):
        """
        Initialize checkpoint for a new batch.

        Args:
            total_papers: Total number of papers to process.
            paper_ids: List of paper IDs in the batch.
        """
        if not self.enabled:
            return

        with self._lock:
            self.data["started_at"] = datetime.now().isoformat()
            self.data["total_papers"] = total_papers
            self.data["all_ids"] = paper_ids
            # Preserve completed/failed from previous run if resuming
            if "completed_ids" not in self.data:
                self.data["completed_ids"] = []
            if "failed_ids" not in self.data:
                self.data["failed_ids"] = []
        self.save()

    def mark_in_progress(self, paper_id: int):
        """Mark a paper as currently being processed."""
        if not self.enabled:
            return

        with self._lock:
            self.data["in_progress_id"] = paper_id
        self.save()

    def mark_completed(self, paper_id: int):
        """Mark a paper as successfully completed."""
        if not self.enabled:
            return

        with self._lock:
            if "completed_ids" not in self.data:
                self.data["completed_ids"] = []
            if paper_id not in self.data["completed_ids"]:
                self.data["completed_ids"].append(paper_id)
            self.data["in_progress_id"] = None
            # Remove from failed_ids if it was there
            if paper_id in self.data.get("failed_ids", []):
                self.data["failed_ids"].remove(paper_id)
            # Remove from errors dict if it was there (successful retry)
            str_id = str(paper_id)
            if str_id in self.data.get("errors", {}):
                del self.data["errors"][str_id]
        self.save()

    def mark_failed(self, paper_id: int, error: Optional[str] = None):
        """Mark a paper as failed."""
        if not self.enabled:
            return

        with self._lock:
            if paper_id not in self.data.get("failed_ids", []):
                self.data["failed_ids"].append(paper_id)
            self.data["in_progress_id"] = None
            # Store error message
            if "errors" not in self.data:
                self.data["errors"] = {}
            if error:
                self.data["errors"][str(paper_id)] = error
        self.save()

    def is_completed(self, paper_id: int) -> bool:
        """Check if a paper was already completed."""
        return paper_id in self.data.get("completed_ids", [])

    def get_remaining_ids(self, all_ids: list) -> list:
        """
        Get IDs that still need processing.

        Excludes completed IDs and abstract_only IDs (already processed with
        abstract fallback).

        Args:
            all_ids: List of all paper IDs to process.

        Returns:
            List of paper IDs not yet completed or processed with abstract.
        """
        completed = set(self.data.get("completed_ids", []))
        # Also exclude abstract_only (already processed with fallback)
        abstract_only = set(
            int(pid) for pid in self.data.get("abstract_only", {}).keys()
        )
        exclude = completed | abstract_only
        return [pid for pid in all_ids if pid not in exclude]

    def mark_abstract_only(self, paper_id: int, reason: Optional[str] = None):
        """
        Mark a paper as processed with abstract-only (PDF fetch failed).

        These papers had stage 1 run with abstract text and stage 2 skipped.

        Args:
            paper_id: Paper database ID.
            reason: Why PDF fetch failed (e.g., "HTTP 404", "EOF error").
        """
        if not self.enabled:
            return
        with self._lock:
            if "abstract_only" not in self.data:
                self.data["abstract_only"] = {}
            reason_msg = reason or "PDF fetch failed"
            self.data["abstract_only"][str(paper_id)] = reason_msg
            self.data["in_progress_id"] = None
            # Remove from failed_ids if present
            if paper_id in self.data.get("failed_ids", []):
                self.data["failed_ids"].remove(paper_id)
            # Remove from errors if present
            str_id = str(paper_id)
            if str_id in self.data.get("errors", {}):
                del self.data["errors"][str_id]
        self.save()

    def get_summary(self) -> dict:
        """Get summary of checkpoint status."""
        completed = len(self.data.get("completed_ids", []))
        failed = len(self.data.get("failed_ids", []))
        abstract_only = len(self.data.get("abstract_only", {}))
        total = self.data.get("total_papers", 0)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "abstract_only": abstract_only,
            "remaining": total - completed - abstract_only,
        }

    def _categorize_errors(
        self, errors: dict, patterns: list[tuple[str, list[str]]]
    ) -> dict[str, list]:
        """
        Categorize errors based on pattern matching.

        Args:
            errors: Dict of {paper_id: error_message}
            patterns: List of (category_name, [patterns_to_match])

        Returns:
            Dict of {category_name: [paper_ids]}
        """
        categories: dict[str, list] = {name: [] for name, _ in patterns}
        for pid, msg in errors.items():
            for name, match_patterns in patterns:
                if any(p in msg for p in match_patterns):
                    categories[name].append(pid)
                    break
        return categories

    def get_error_stats(self) -> dict:
        """
        Get detailed error statistics with bucketing.

        Returns:
            Dict with error categories and counts.
        """
        errors = self.data.get("errors", {})
        abstract_only = self.data.get("abstract_only", {})

        # Pattern definitions: (category_name, [patterns_to_match])
        retryable_patterns = [
            ("Rate Limit (429)", ["429", "RESOURCE_EXHAUSTED"]),
            ("Gateway Timeout (504)", ["504", "Gateway Time-out"]),
            ("API Error (500)", ["API call failed"]),
            ("JSON Parse Error", ["Could not parse", "JSON"]),
        ]
        abstract_only_patterns = [
            ("EOF (corrupted PDFs)", ["EOF"]),
            ("HTTP 403 (access denied)", ["HTTP 403"]),
            ("HTTP 404 (not found)", ["HTTP 404"]),
            ("HTTP 405", ["HTTP 405"]),
            ("SSL error", ["SSL", "Certificate"]),
            ("Connection errors", ["HTTPSConnectionPool", "Max retries"]),
        ]

        retryable_cats = self._categorize_errors(errors, retryable_patterns)
        abstract_cats = self._categorize_errors(
            abstract_only,
            abstract_only_patterns,
        )

        return {
            "retryable": {k: len(v) for k, v in retryable_cats.items() if v},
            "abstract_only": {k: len(v) for k, v in abstract_cats.items() if v},
            "retryable_total": len(errors),
            "abstract_only_total": len(abstract_only),
        }

    def print_stats(self):
        """Print formatted error statistics table."""
        summary = self.get_summary()
        error_stats = self.get_error_stats()

        print()
        print("=" * 70)
        print("PROGRESS STATISTICS")
        print("=" * 70)
        print()
        print(f"{'Field':<30} {'Count':>8}   Description")
        print("-" * 70)
        print(
            f"{'completed_ids':<30} {summary['completed']:>8}   "
            f"Successfully processed (full PDF)"
        )
        print(
            f"{'abstract_only':<30} {error_stats['abstract_only_total']:>8}   "
            f"Processed with abstract (PDF failed)"
        )
        print(
            f"{'errors (retryable)':<30} {error_stats['retryable_total']:>8}   "
            f"Can retry: rate limits, API errors, timeouts"
        )
        print()

        if error_stats["retryable"]:
            print("Retryable errors breakdown:")
            for cat, count in sorted(
                error_stats["retryable"].items(), key=lambda x: -x[1]
            ):
                print(f"  - {cat}: {count}")
            print()

        if error_stats["abstract_only"]:
            print("Abstract-only breakdown (PDF fetch failures):")
            for cat, count in sorted(
                error_stats["abstract_only"].items(), key=lambda x: -x[1]
            ):
                print(f"  - {cat}: {count}")
            print()

        print("=" * 70)


# Global checkpoint manager (initialized in main)
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> Optional[CheckpointManager]:
    """Get the global checkpoint manager instance."""
    return _checkpoint_manager


def set_checkpoint_manager(manager: CheckpointManager):
    """Set the global checkpoint manager instance."""
    global _checkpoint_manager
    _checkpoint_manager = manager


# ==============================================================================
# Graceful Shutdown Handler
# ==============================================================================
_shutdown_requested = False


def request_shutdown():
    """Request graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """Check if shutdown was requested."""
    return _shutdown_requested


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        print("\n\n[!] Shutdown requested. Finishing current paper...")
        print("   (Press Ctrl+C again to force quit)\n")
        request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


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


def download_pdf_bytes(
    pdf_url: str,
    max_retries: int = 3,
) -> bytes:
    """
    Download a PDF from URL and return raw bytes.

    Args:
        pdf_url: URL to the PDF file.
        max_retries: Maximum retry attempts for download failures.

    Returns:
        PDF bytes.

    Raises:
        Exception: If download fails after all retries.
    """
    print(f"Downloading PDF from: {pdf_url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.get(pdf_url, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.content
            elif response.status_code in {429, 503}:
                wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
                print(f"  HTTP {response.status_code}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                last_error = Exception(f"HTTP {response.status_code}")
            else:
                raise Exception(f"Failed to download PDF: HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            print(
                f"  Timeout, retrying in {wait_time}s... ({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
            last_error = Exception("Download timeout")
        except requests.exceptions.ConnectionError as e:
            wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            print(
                f"  Connection error, retrying in {wait_time}s... "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
            last_error = e

    if last_error:
        raise last_error
    raise Exception("Failed to download PDF after retries")


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
            from . import extract_figures as fig_module

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
            print(f"  Could not import extract_figures module: {e}")
        except Exception as e:
            print(f"  Error extracting figures: {e}")

    return result


def store_figures_in_db(
    paper_db_id: int,
    figures: list[dict],
    store_image_data: bool = True,
) -> list[int]:
    """
    Store extracted figures in the paper_images database table.

    Args:
        paper_db_id: The paper's database ID (from papers table).
        figures: List of figure dicts from extract_figures_from_pdf_bytes().
            Each dict should have: filename, figure_num, page, caption, path
        store_image_data: Whether to store image binary data in DB.

    Returns:
        List of created image IDs in the database.
    """
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from paper_db import PaperDB
    except ImportError as e:
        print(f"  Could not import paper_db: {e}")
        return []

    image_ids = []
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

    finally:
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
        from . import extract_figures as fig_module

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
        print(f"  Could not import extract_figures module: {e}")
    except Exception as e:
        print(f"  Error extracting/storing figures: {e}")

    return result


def load_config() -> dict:
    """
    Load configuration from config.yaml.

    Returns:
        Configuration dictionary with gemini settings.
    """
    config_paths = [
        Path(__file__).parent.parent / "config.yaml",
        Path.cwd() / "config.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            if yaml is None:
                print("Warning: PyYAML not installed. Using default config.")
                break
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                return config.get("gemini", {})

    return {}


def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a value from config, environment, or default.

    Args:
        key: Config key (e.g., 'api_key', 'api_url', 'model')
        default: Default value if not found

    Returns:
        Config value string.
    """
    config = load_config()
    env_key = f"GEMINI_{key.upper()}"
    return os.environ.get(env_key, config.get(key, default))


def get_api_key(api_key: Optional[str] = None) -> str:
    """
    Get the API key from parameter, environment, or config file.

    Args:
        api_key: API key. If None, reads from GEMINI_API_KEY env var or config.yaml.

    Returns:
        API key string.
    """
    if api_key is None:
        api_key = get_config_value("api_key", "")

    if not api_key:
        raise ValueError(
            "API key not found. Set it in config.yaml, GEMINI_API_KEY env var, "
            "or pass it directly."
        )

    return api_key


def get_api_url() -> str:
    """Get the API URL from config."""
    url = get_config_value("api_url")
    if not url:
        raise ValueError(
            "API URL not found. Set it in config.yaml under gemini.api_url"
        )
    return url


def get_default_model() -> str:
    """Get the default model from config."""
    model = get_config_value("model")
    if not model:
        raise ValueError("Model not found. Set it in config.yaml under gemini.model")
    return model


def get_lightweight_model() -> str:
    """Get lightweight model for abstract-only classification from config."""
    model = get_config_value("lightweight_model")
    if not model:
        raise ValueError(
            "Lightweight model not found. "
            "Set it in config.yaml under gemini.lightweight_model"
        )
    return model


def call_gemini_api(
    prompt: str,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
) -> str:
    """
    Call the Gemini API via wearables-ape.io with retry logic and rate limiting.

    Args:
        prompt: The prompt to send to the model.
        model_name: Model to use (default: from config or gemini-2.0-flash)
        api_key: API key. If None, uses default.
        max_retries: Maximum number of retry attempts for transient failures.

    Returns:
        Response text from the model.

    Raises:
        Exception: If all retries are exhausted or a non-retryable error occurs.
    """
    # Apply rate limiting before making request
    rate_limiter = get_rate_limiter()
    if rate_limiter:
        rate_limiter.acquire()

    api_key = get_api_key(api_key)
    if model_name is None:
        model_name = get_default_model()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    payload = {
        "name": "llm-text-gen",
        "outputVariableName": "last_output",
        "model_api_name": model_name,
        "stream": False,
        "user": prompt,
    }

    api_url = get_api_url()
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                api_url, headers=headers, json=payload, timeout=120
            )

            if response.status_code == 200:
                return _extract_api_response(response.json())

            # Check if error is retryable
            if response.status_code in RETRYABLE_STATUS_CODES:
                last_exception = Exception(
                    f"API Error: {response.status_code}\n{response.text}"
                )
                if attempt < max_retries:
                    _wait_with_backoff(
                        attempt, max_retries, f"HTTP {response.status_code}"
                    )
                    continue
            else:
                # Non-retryable error (e.g., 400, 401, 403)
                raise Exception(
                    f"API Error: {response.status_code}\n{response.text}\n"
                    f"Request body:\n{json.dumps(payload, indent=2)}"
                )

        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < max_retries:
                _wait_with_backoff(attempt, max_retries, "Timeout")
                continue

        except requests.exceptions.ConnectionError as e:
            last_exception = e
            if attempt < max_retries:
                _wait_with_backoff(attempt, max_retries, "Connection error")
                continue

    # All retries exhausted
    raise Exception(
        f"API call failed after {max_retries + 1} attempts. Last error: {last_exception}"
    )


def _extract_api_response(result: dict) -> str:
    """Extract response text from API response."""
    if "result" in result:
        return result["result"]
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0].get("message", {}).get("content", "")
    if "content" in result:
        return result["content"]
    if "response" in result:
        return result["response"]
    return json.dumps(result)


def _wait_with_backoff(attempt: int, max_retries: int, reason: str):
    """Wait with exponential backoff and print retry message."""
    delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
    print(f"  Retry {attempt + 1}/{max_retries}: {reason}, waiting {delay}s...")
    time.sleep(delay)


def load_topic_prompt(prompt_file: Optional[str] = None) -> str:
    """
    Load the topic classification prompt from file.

    Args:
        prompt_file: Path to prompt file. Defaults to prompts/prompt_topic.txt.

    Returns:
        Topic classification prompt string.
    """
    actual_path: Path
    if prompt_file is None:
        script_dir = Path(__file__).parent
        actual_path = script_dir / "prompts" / "prompt_topic.txt"
    else:
        actual_path = Path(prompt_file)

    with open(actual_path, "r") as f:
        return f.read()


def load_prompt_template(
    prompt_file: Optional[str] = None,
    topics: Optional[list] = None,
    primary_topic: Optional[str] = None,
) -> str:
    """
    Load the prompt template from file and populate placeholders.

    Replaces:
        - <json_template> with contents of summary_template.json
        - <json_example> with contents of summary_example.json
        - <topic_background> with contents of background files for matching topics
          (or removes the "Area Background" section if no topics match)

    Supported topics with background files:
        RAG, Factuality, Agent, Memory, P13N, Benchmark

    Args:
        prompt_file: Path to prompt file. Defaults to prompts/prompt.txt.
        topics: List of topic tags for the paper (e.g., ["RAG", "Agent"]).
                If None or empty, Area Background section is removed.
        primary_topic: The primary topic for this paper. If provided,
            its background is loaded first with emphasis.

    Returns:
        Prompt template string with placeholders replaced.
    """
    actual_path: Path
    if prompt_file is None:
        script_dir = Path(__file__).parent
        prompts_dir = script_dir / "prompts"
        actual_path = prompts_dir / "prompt.txt"
    else:
        actual_path = Path(prompt_file)
        prompts_dir = actual_path.parent

    with open(actual_path, "r") as f:
        prompt = f.read()

    # Load and replace <json_template>
    template_file = prompts_dir / "summary_template.json"
    if template_file.exists():
        with open(template_file, "r") as f:
            json_template = f.read()
        prompt = prompt.replace("<json_template>", json_template)

    # Load and replace <json_example>
    example_file = prompts_dir / "summary_example.json"
    if example_file.exists():
        with open(example_file, "r") as f:
            json_example = f.read()
        prompt = prompt.replace("<json_example>", json_example)

    # Map topic tags to background file names
    # Only these topics have background files
    TOPIC_BACKGROUND_FILES = {
        "RAG": "background_rag.txt",
        "Factuality": "background_factuality.txt",
        "Agent": "background_agent.txt",
        "Memory": "background_memory.txt",
        "P13N": "background_p13n.txt",
        "Benchmark": "background_benchmark.txt",
    }

    # Load backgrounds for matching topics
    backgrounds = []

    # First, load primary topic background with emphasis
    if primary_topic and primary_topic.strip() in TOPIC_BACKGROUND_FILES:
        primary_clean = primary_topic.strip()
        bg_file = prompts_dir / TOPIC_BACKGROUND_FILES[primary_clean]
        if bg_file.exists():
            with open(bg_file, "r") as f:
                bg_content = f.read().strip()
            if bg_content:
                backgrounds.append(
                    f"=== PRIMARY TOPIC: {primary_clean} ===\n"
                    f"(This is the main focus area for this paper. "
                    f"Focus sub_topic and primary_focus on this area.)"
                    f"\n\n{bg_content}"
                )

    # Then load other topic backgrounds as supplementary
    if topics:
        for topic in topics:
            topic_clean = topic.strip()
            # Skip if already added as primary
            if primary_topic and topic_clean == primary_topic.strip():
                continue
            if topic_clean in TOPIC_BACKGROUND_FILES:
                bg_file = prompts_dir / TOPIC_BACKGROUND_FILES[topic_clean]
                if bg_file.exists():
                    with open(bg_file, "r") as f:
                        bg_content = f.read().strip()
                    if bg_content:
                        backgrounds.append(
                            f"=== Supplementary: {topic_clean} ===\n{bg_content}"
                        )

    if backgrounds:
        # Combine all backgrounds with separators
        combined_background = "\n\n".join(backgrounds)
        prompt = prompt.replace("<topic_background>", combined_background)
    else:
        # Remove the entire "Area Background" section if no backgrounds
        prompt = prompt.replace(
            "\n========================\nArea Background"
            "\n========================\n\n<topic_background>",
            "",
        )

    return prompt


# Allowed topics for Stage 1 classification
ALLOWED_TOPICS = {
    "RAG",
    "Agent",
    "Memory",
    "P13N",
    "Factuality",
    "Benchmark",
    "Reasoning",
    "RL",
    "Pretraining",
    "KG",
    "QA",
    "Recommendation",
    "MM",
    "Speech",
}


def _validate_topics(result: dict) -> dict:
    """
    Validate that topics are in the allowed list.
    If primary_topic is not in the list, set it to None.
    Filter out invalid topics from the topic list.
    """
    topics = result.get("topic", [])
    primary_topic = result.get("primary_topic")

    # Filter topics to only include allowed ones
    valid_topics = [t for t in topics if t in ALLOWED_TOPICS]
    invalid_topics = [t for t in topics if t not in ALLOWED_TOPICS]

    if invalid_topics:
        print(f"  Warning: Removing invalid topics: {invalid_topics}")

    # Check if primary_topic is valid
    if primary_topic and primary_topic not in ALLOWED_TOPICS:
        print(f"  Warning: Invalid primary_topic '{primary_topic}', setting to None")
        primary_topic = None

    result["topic"] = valid_topics
    result["primary_topic"] = primary_topic
    return result


def classify_paper_topics(
    pdf_url: str,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    pdf_text: Optional[str] = None,
) -> dict:
    """
    Stage 1: Classify paper topics and determine primary topic.

    Args:
        pdf_url: URL to the paper PDF (e.g., arXiv PDF link)
        model_name: Gemini model to use (default: from config)
        api_key: API key. If None, uses default.
        pdf_text: Pre-extracted PDF text. If None, downloads and extracts.

    Returns:
        Dictionary with:
        - topic: list of topic tags (only from ALLOWED_TOPICS)
        - primary_topic: the main topic (None if invalid)
        - reasoning: explanation of the classification
    """
    if model_name is None:
        model_name = get_default_model()

    # Load topic classification prompt
    prompt_template = load_topic_prompt()

    # Use provided pdf_text or download
    print(f"Classifying topics for: {pdf_url}")
    if pdf_text is None:
        pdf_text = download_pdf_text(pdf_url)

    # Build the prompt with actual PDF content
    prompt = prompt_template.replace("<PDF_URL>", pdf_url)

    # Insert the PDF content after the URL line
    pdf_content_section = (
        "\n\n========================\n"
        "Paper Content (extracted from PDF)\n"
        f"========================\n\n{pdf_text}\n"
    )
    prompt = prompt.replace(
        "For the above paper,",
        f"{pdf_content_section}\nFor the above paper,",
    )

    print(f"  Using model: {model_name}")
    print(f"  Prompt length: {len(prompt)} characters")

    # Retry up to 3 times for LLM parsing errors
    max_llm_retries = 3
    response_text = ""
    for llm_attempt in range(max_llm_retries):
        response_text = call_gemini_api(prompt, model_name, api_key)

        # Try to parse as JSON
        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                # Validate topics are in the allowed list
                result = _validate_topics(result)
                print(f"  Topics: {result.get('topic', [])}")
                print(f"  Primary topic: {result.get('primary_topic', 'N/A')}")
                return result
            else:
                if llm_attempt < max_llm_retries - 1:
                    print(
                        f"  Warning: Could not find JSON in response, retrying... "
                        f"({llm_attempt + 1}/{max_llm_retries})"
                    )
                    continue
                print("  Warning: Could not find JSON in response after retries")
                return {
                    "topic": [],
                    "primary_topic": None,
                    "reasoning": response_text,
                }

        except json.JSONDecodeError as e:
            if llm_attempt < max_llm_retries - 1:
                print(
                    f"  Warning: Could not parse JSON: {e}, retrying... "
                    f"({llm_attempt + 1}/{max_llm_retries})"
                )
                continue
            print(f"  Warning: Could not parse JSON after retries: {e}")
            return {
                "topic": [],
                "primary_topic": None,
                "reasoning": response_text,
            }

    return {
        "topic": [],
        "primary_topic": None,
        "reasoning": response_text,
    }


def generate_paper_summary(
    pdf_url: str,
    prompt_template: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    pdf_text: Optional[str] = None,
) -> dict:
    """
    Generate a structured summary for a paper given its PDF URL.

    Args:
        pdf_url: URL to the paper PDF (e.g., arXiv PDF link)
        prompt_template: Custom prompt template. If None, loads from prompt.txt
        model_name: Gemini model to use (default: from config)
        api_key: API key. If None, uses default.
        pdf_text: Pre-extracted PDF text. If None, downloads and extracts.

    Returns:
        Parsed JSON summary dictionary.
    """
    if model_name is None:
        model_name = get_default_model()

    # Load prompt template if not provided
    if prompt_template is None:
        prompt_template = load_prompt_template()

    # Use provided pdf_text or download
    print(f"Generating summary for: {pdf_url}")
    if pdf_text is None:
        pdf_text = download_pdf_text(pdf_url)

    # Build the prompt with actual PDF content
    prompt = prompt_template.replace("<PDF_URL>", pdf_url)

    # Insert the PDF content after the URL line
    pdf_content_section = (
        "\n\n========================\n"
        "Paper Content (extracted from PDF)\n"
        f"========================\n\n{pdf_text}\n"
    )
    prompt = prompt.replace(
        "For the above paper in the given link,",
        f"{pdf_content_section}\nFor the above paper content,",
    )

    print(f"  Using model: {model_name}")
    print(f"  Prompt length: {len(prompt)} characters")

    response_text = call_gemini_api(prompt, model_name, api_key)

    # Try to parse as JSON
    try:
        # Find JSON in response (it might be wrapped in markdown code blocks)
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            return json.loads(json_str)
        else:
            print("  Warning: Could not find JSON in response")
            return {"raw_response": response_text}

    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse JSON: {e}")
        return {"raw_response": response_text}


def generate_summary_for_paper(
    paper_id: int,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    db=None,
    prompt_file: Optional[str] = None,
    output_file: Optional[str] = None,
    save_db: bool = False,
    overwrite: bool = False,
) -> dict:
    """
    Generate summary for a paper using multi-stage approach.

    Stages:
        Stage 0: PDF download (only if any later stage needs it)
        Stage 1: Figure extraction (only if figures don't exist in DB)
        Stage 2: Text extraction (only if Stage 3 or 4 need it)
        Stage 3: Topic classification (only if primary_topic doesn't exist)
        Stage 4: Summary generation (only if summary_generated_at doesn't exist)

    Conditional execution:
        - If overwrite=True, run all stages regardless of existing data
        - Skip PDF download (Stage 0) if no stages need it
        - Skip text extraction (Stage 2) if only figures are needed
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from paper_db import PaperDB

    if model_name is None:
        model_name = get_default_model()

    result = {"success": False, "summary": None}
    topics = []
    primary_topic = None
    stages_run = []

    should_close = db is None
    if db is None:
        db = PaperDB()

    try:
        paper = db.get_paper_by_id(paper_id)
        if not paper:
            result["error"] = f"Paper with ID {paper_id} not found"
            return result

        title, link = paper.get("title", ""), paper.get("link", "")
        if not title or not link:
            result["error"] = f"Missing title or link for paper {paper_id}"
            return result

        pdf_url = link.replace("/abs/", "/pdf/") if "arxiv.org/abs/" in link else link
        if "arxiv.org" in pdf_url and not pdf_url.endswith(".pdf"):
            pdf_url += ".pdf"

        print(f"Processing paper ID {paper_id}: {title}...")

        # =================================================================
        # Determine which stages to run
        # =================================================================
        existing_images = db.get_paper_images(paper_id) if save_db else []

        if save_db:
            run_figures = overwrite or not existing_images
            run_topics = overwrite or not paper.get("primary_topic")
            run_summary = overwrite or not paper.get("summary_generated_at")
        else:
            # Testing mode: always run topics and summary, skip figures
            run_figures = False
            run_topics = True
            run_summary = True

        # Derived indicators
        need_pdf = run_figures or run_topics or run_summary
        need_text = run_topics or run_summary

        print(
            f"  run_figures={run_figures}, run_topics={run_topics}, "
            f"run_summary={run_summary}"
        )
        print(f"  need_pdf={need_pdf}, need_text={need_text}")

        if not need_pdf:
            print("Nothing to do - all data already exists")
            result["success"] = True
            return result

        # =================================================================
        # Stage 0: PDF Download
        # =================================================================
        print("\n========== Stage 0: PDF Download ==========")
        stages_run.append("stage0_pdf_download")
        pdf_bytes = None
        pdf_text = None
        use_abstract_fallback = False

        try:
            pdf_bytes = download_pdf_bytes(pdf_url)
            print(f"  Downloaded {len(pdf_bytes)} bytes")
        except Exception as e:
            print(f"  PDF download failed: {e}")
            abstract = paper.get("abstract")
            if abstract and need_text:
                print("  Falling back to abstract for topic classification...")
                pdf_text = f"Title: {title}\n\nAbstract:\n{abstract}"
                use_abstract_fallback = True
            elif not need_text and run_figures:
                # Only needed figures, but PDF failed
                print("  Cannot extract figures without PDF")
                run_figures = False
            else:
                result["error"] = f"PDF download failed, no abstract: {e}"
                return result

        # =================================================================
        # Stage 1: Figure Extraction
        # =================================================================
        if run_figures and pdf_bytes:
            print("\n========== Stage 1: Figure Extraction ==========")
            stages_run.append("stage1_figures")
            try:
                try:
                    from . import extract_figures as fig_module
                except ImportError:
                    import extract_figures as fig_module

                if fig_module.PYMUPDF_AVAILABLE:
                    figures = fig_module.extract_figures_from_pdf_bytes(
                        pdf_bytes=pdf_bytes,
                        paper_id=str(paper_id),
                    )
                    if figures:
                        print(f"  Extracted {len(figures)} figures, storing...")
                        image_ids = store_figures_in_db(
                            paper_db_id=paper_id,
                            figures=figures,
                            store_image_data=True,
                        )
                        print(f"  Stored {len(image_ids)} figures in DB")
                    else:
                        print("  No figures found in PDF")
                else:
                    print("  PyMuPDF not available, skipping")
            except Exception as e:
                print(f"  Figure extraction error: {e}")
        elif run_figures:
            print("\n========== Stage 1: Figure Extraction (SKIPPED) ==========")
            print("  No PDF bytes available")

        # =================================================================
        # Stage 2: Text Extraction
        # =================================================================
        if need_text and pdf_bytes and not use_abstract_fallback:
            print("\n========== Stage 2: Text Extraction ==========")
            stages_run.append("stage2_text")
            pdf_text = extract_text_from_pdf_bytes(pdf_bytes)
            print(f"  Extracted {len(pdf_text)} characters")
        elif need_text and use_abstract_fallback:
            print("\n========== Stage 2: Text Extraction (ABSTRACT) ==========")
            stages_run.append("stage2_text_abstract")
            text_len = len(pdf_text) if pdf_text else 0
            print(f"  Using abstract fallback ({text_len} chars)")
        elif not need_text:
            print("\n========== Stage 2: Text Extraction (SKIPPED) ==========")
            print("  Not needed (only figures requested)")

        # =================================================================
        # Stage 3: Topic Classification
        # =================================================================
        if run_topics:
            print("\n========== Stage 3: Topic Classification ==========")
            stages_run.append("stage3_topics")

            if use_abstract_fallback:
                stage_model = get_lightweight_model()
                print(f"  Using lightweight model: {stage_model}")
            else:
                stage_model = model_name

            topic_result = classify_paper_topics(
                pdf_url, stage_model, api_key, pdf_text=pdf_text
            )
            topics = topic_result.get("topic", [])
            primary_topic = topic_result.get("primary_topic")
            print(f"  Topics: {topics}, Primary: {primary_topic}")

            if save_db:
                db.update_paper(
                    paper_id,
                    topic=", ".join(topics) if topics else None,
                    primary_topic=primary_topic,
                )
        else:
            topics_str = paper.get("topic", "")
            topics = topics_str.split(", ") if topics_str else []
            primary_topic = paper.get("primary_topic")
            print("\n========== Stage 3: Topic Classification (SKIPPED) ==========")
            print(f"  Using existing: {primary_topic}")

        # =================================================================
        # Stage 4: Summary Generation
        # =================================================================
        if run_summary and not use_abstract_fallback:
            print("\n========== Stage 4: Summary Generation ==========")
            stages_run.append("stage4_summary")

            prompt = load_prompt_template(topics=topics, primary_topic=primary_topic)

            if prompt_file:
                with open(prompt_file, "a") as f:
                    f.write(f"\n{'=' * 60}\nPaper ID: {paper_id}\n{'=' * 60}\n")
                    f.write(prompt)
                    f.write("\n")

            max_llm_retries = 3
            last_raw_response = None
            for llm_attempt in range(max_llm_retries):
                summary = generate_paper_summary(
                    pdf_url, prompt, model_name, api_key, pdf_text=pdf_text
                )

                if "raw_response" not in summary:
                    break

                last_raw_response = summary.get("raw_response", "")[:200]
                if llm_attempt < max_llm_retries - 1:
                    print(
                        f"  LLM returned invalid JSON, retrying... "
                        f"({llm_attempt + 1}/{max_llm_retries})"
                    )
            else:
                result["error"] = (
                    f"Could not parse summary JSON after {max_llm_retries} attempts. "
                    f"Last response: {last_raw_response}..."
                )
                return result

            result["summary"] = summary

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(summary, f, indent=2)
                print(f"  Summary saved to: {output_file}")

            if save_db:
                db.update_paper_summary(paper_id, summary)
        elif use_abstract_fallback and run_summary:
            print("\n========== Stage 4: Summary Generation (SKIPPED) ==========")
            print("  Cannot generate summary from abstract alone")
            result["abstract_only"] = True
        else:
            print("\n========== Stage 4: Summary Generation (SKIPPED) ==========")
            print("  Summary already exists")

        result["success"] = True
        if use_abstract_fallback:
            result["abstract_only"] = True
        print(f"\nCompleted stages: {stages_run}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  Error: {e}")
    finally:
        if should_close:
            db.close()

    return result


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Generate paper summaries using Google Gemini API"
    )
    parser.add_argument(
        "--pdf-url",
        type=str,
        help="URL to the paper PDF (e.g., https://arxiv.org/pdf/2501.15228)",
    )
    parser.add_argument(
        "--paper-id",
        type=int,
        help="Generate summary for a specific paper by database ID",
    )
    parser.add_argument(
        "--latest",
        type=int,
        help="Generate summaries for the latest N papers (by created_at)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate summaries for ALL papers in the database",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        help="Checkpoint file for resumable batch processing",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint file (requires --checkpoint)",
    )
    parser.add_argument(
        "--pdf-cache",
        type=str,
        help="Directory to cache downloaded PDFs (e.g., ./pdf_cache)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON summary",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        help="Output file path for generated prompts (for debugging)",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save topic and summary to database",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing summaries (default: skip existing)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (default: from config.yaml)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Google API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for batch processing (default: 1)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=0,
        help="Max API requests per minute (0 = no limit, recommended: 10-30)",
    )
    # TODO: add an argument to generate summaries for a particular topic

    args = parser.parse_args()

    # --resume with --checkpoint implies batch processing of remaining papers
    if args.resume and args.checkpoint:
        args.all = True

    # Check that at least one input source is specified
    if not any([args.all, args.latest, args.paper_id, args.pdf_url]):
        print("Error: No input specified. Provide one of the following:")
        print("  --all              Process ALL papers in the database")
        print("  --latest N         Process the latest N papers")
        print("  --paper-id ID      Process a specific paper by database ID")
        print("  --pdf-url URL      Process a single PDF from URL")
        print()
        print("For resuming from a checkpoint, use:")
        print("  --checkpoint FILE --resume")
        return

    # Process all papers or latest N papers
    if args.all or args.latest:
        import sys
        from concurrent.futures import as_completed, ThreadPoolExecutor

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from paper_db import PaperDB

        # Set up signal handlers for graceful shutdown
        setup_signal_handlers()

        # Initialize rate limiter
        if args.rate_limit > 0:
            print(f"Rate limiting enabled: {args.rate_limit} requests/minute")
            set_rate_limiter(RateLimiter(args.rate_limit))
        else:
            set_rate_limiter(RateLimiter(0))  # Disabled

        # Initialize checkpoint manager
        checkpoint = CheckpointManager(args.checkpoint)
        set_checkpoint_manager(checkpoint)

        # Initialize PDF cache
        if args.pdf_cache:
            print(f"PDF caching enabled: {args.pdf_cache}")
            set_pdf_cache(PDFCache(args.pdf_cache))
        else:
            set_pdf_cache(PDFCache(None))  # Disabled

        # Load existing checkpoint if resuming
        if args.resume:
            if not args.checkpoint:
                print("Error: --resume requires --checkpoint <file>")
                return
            if checkpoint.load():
                print(f"Resuming from checkpoint: {args.checkpoint}")
            else:
                print("No checkpoint found, starting fresh")

        db = PaperDB()
        papers = db.get_all_papers(order_by="created_at", order_dir="DESC")

        # Limit papers if --latest is specified, otherwise process all
        if args.latest:
            papers = papers[: args.latest]
            print(
                f"\nProcessing latest {len(papers)} papers (workers={args.workers})..."
            )
        else:
            print(f"\nProcessing ALL {len(papers)} papers (workers={args.workers})...")

        if not papers:
            print("No papers found in database")
            db.close()
            return

        # Get paper IDs
        all_paper_ids = [p["id"] for p in papers]
        paper_map = {p["id"]: p for p in papers}

        # Filter out already completed papers if resuming
        if args.resume and checkpoint.enabled:
            remaining_ids = checkpoint.get_remaining_ids(all_paper_ids)
            papers_to_process = [paper_map[pid] for pid in remaining_ids]
            skipped = len(papers) - len(papers_to_process)
            if skipped > 0:
                summary = checkpoint.get_summary()
                print(
                    f"Skipping {skipped} papers: "
                    f"{summary.get('completed', 0)} completed, "
                    f"{summary.get('permanent_errors', 0)} permanent errors"
                )
        else:
            papers_to_process = papers

        # Initialize checkpoint for this batch
        checkpoint.start_batch(len(papers), all_paper_ids)

        if args.checkpoint:
            print(f"Checkpoint file: {args.checkpoint}")
        print()

        all_results = []
        success_count = 0
        failed_count = 0

        def process_paper(paper):
            """Process a single paper (for parallel execution)."""
            paper_id = paper["id"]

            # Check for shutdown request
            if is_shutdown_requested():
                return {
                    "success": False,
                    "summary": None,
                    "error": "Shutdown requested",
                    "_paper_id": paper_id,
                    "_title": paper.get("title", ""),
                    "_skipped": True,
                }

            # Mark as in progress
            checkpoint.mark_in_progress(paper_id)

            try:
                result = generate_summary_for_paper(
                    paper_id=paper_id,
                    model_name=args.model,
                    api_key=args.api_key,
                    prompt_file=args.prompt_file,
                    save_db=args.save_db,
                    overwrite=args.overwrite,
                )
                # Add paper info for internal tracking
                # (excluded from JSON output)
                result["_paper_id"] = paper_id
                result["_title"] = paper.get("title", "")

                # Update checkpoint
                if result["success"]:
                    if result.get("abstract_only"):
                        checkpoint.mark_abstract_only(
                            paper_id,
                            result.get("pdf_error"),
                        )
                    else:
                        checkpoint.mark_completed(paper_id)
                else:
                    checkpoint.mark_failed(paper_id, result.get("error"))

                return result

            except Exception as e:
                checkpoint.mark_failed(paper_id, str(e))
                return {
                    "success": False,
                    "summary": None,
                    "error": str(e),
                    "_paper_id": paper_id,
                    "_title": paper.get("title", ""),
                }

        if args.workers > 1:
            # Parallel processing with checkpointing
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {
                    executor.submit(process_paper, p): p for p in papers_to_process
                }
                for future in as_completed(futures):
                    if is_shutdown_requested():
                        print("\n[!] Cancelling remaining tasks...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    result = future.result()
                    if not result.get("_skipped"):
                        all_results.append(result)
                        if result["success"]:
                            success_count += 1
                        else:
                            failed_count += 1
                    print("")
        else:
            # Sequential processing with checkpointing
            for i, paper in enumerate(papers_to_process, 1):
                if is_shutdown_requested():
                    print(f"\n[!] Stopped after {i - 1} papers")
                    break

                result = process_paper(paper)
                if not result.get("_skipped"):
                    all_results.append(result)
                    if result["success"]:
                        success_count += 1
                    else:
                        failed_count += 1
                print("")

        db.close()

        # Output results
        print("\n" + "=" * 60)
        print(
            f"BATCH PROCESSING {'INTERRUPTED' if is_shutdown_requested() else 'COMPLETE'}"
        )
        print("=" * 60)

        # Print checkpoint summary if enabled
        if checkpoint.enabled:
            summary = checkpoint.get_summary()
            print(
                f"Progress: {summary['completed']}/{summary['total']} completed, "
                f"{summary['failed']} failed, {summary['remaining']} remaining"
            )
            if is_shutdown_requested():
                print(
                    f"\nTo resume: python {sys.argv[0]} --latest {args.latest} "
                    f"--checkpoint {args.checkpoint} --resume"
                )
            # Print detailed error statistics
            checkpoint.print_stats()
        else:
            print(
                f"Processed: {success_count} success, {failed_count} failed (this session)"
            )

        if args.save_db:
            print("Database updated")

        if args.output and all_results:
            # Remove internal tracking fields before writing to JSON
            output_results = []
            for r in all_results:
                output_r = {k: v for k, v in r.items() if not k.startswith("_")}
                output_results.append(output_r)
            with open(args.output, "w") as f:
                json.dump(output_results, f, indent=2)
            print(f"Results saved to: {args.output}")
        elif not args.output and all_results:
            for r in all_results:
                status = "[OK]" if r["success"] else "[FAIL]"
                print(f"  {status} [{r['_paper_id']}] {r['_title'][:50]}...")
                if r.get("error"):
                    print(f"      Error: {r['error']}")
        return

    # Process a single paper by ID
    if args.paper_id:
        result = generate_summary_for_paper(
            paper_id=args.paper_id,
            model_name=args.model,
            api_key=args.api_key,
            prompt_file=args.prompt_file,
            output_file=args.output,
            save_db=args.save_db,
            overwrite=args.overwrite,
        )
        if result["success"]:
            print("\nProcessing completed successfully!")
            if args.save_db:
                print("Database updated")
            if result.get("summary"):
                if args.output:
                    print(f"Summary: saved to {args.output}")
                else:
                    print("\n" + "=" * 60)
                    print("GENERATED SUMMARY")
                    print("=" * 60)
                    print(json.dumps(result["summary"], indent=2))
        else:
            print(f"\nError: {result['error']}")
        return

    # Generate summary if PDF URL provided
    if args.pdf_url:
        # Generate summary
        summary = generate_paper_summary(
            pdf_url=args.pdf_url,
            prompt_template=None,
            model_name=args.model,
            api_key=args.api_key,
        )

        # Output result
        output_json = json.dumps(summary, indent=2)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output_json)
            print(f"\nSummary saved to: {args.output}")
        else:
            print("\n" + "=" * 60)
            print("GENERATED SUMMARY")
            print("=" * 60)
            print(output_json)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
