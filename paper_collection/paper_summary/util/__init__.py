#!/usr/bin/env python3
"""
Utility Module for Paper Summary Generation

Contains reusable utilities for:
- Checkpoint management and rate limiting
- PDF processing (download, cache, extraction)
- arXiv HTML processing (preferred for arXiv papers)
- LLM API client (Gemini)
"""

from .arxiv_html_processing import (
    BS4_AVAILABLE,
    check_html_available,
    download_arxiv_html_with_figures,
    extract_figures_from_html,
    extract_text_from_html,
    get_arxiv_id_from_url,
    get_html_url_from_arxiv_url,
    is_arxiv_url,
    MAX_HTML_CHARS,
)
from .checkpoint import (
    CheckpointManager,
    get_checkpoint_manager,
    get_rate_limiter,
    is_shutdown_requested,
    RateLimiter,
    request_shutdown,
    set_checkpoint_manager,
    set_rate_limiter,
    setup_signal_handlers,
)
from .figure_extraction_from_pdf import (
    Caption,
    extract_figures_from_pdf_bytes,
    extract_paper_id_from_url,
    FIGURES_DIR,
    find_all_captions,
    find_graphics_bounds,
    get_column_bounds,
    PILLOW_AVAILABLE,
    PYMUPDF_AVAILABLE,
)
from .llm_client import (
    call_gemini_api,
    get_api_key,
    get_api_url,
    get_config_value,
    get_default_model,
    get_lightweight_model,
)
from .pdf_processing import (
    download_pdf_bytes,
    download_pdf_text,
    download_pdf_with_figures,
    extract_and_store_figures,
    extract_text_from_pdf_bytes,
    get_pdf_cache,
    MAX_PDF_CHARS,
    PDF_SUPPORT,
    PDFCache,
    set_pdf_cache,
    store_figures_in_db,
)

__all__ = [
    # checkpoint
    "RateLimiter",
    "CheckpointManager",
    "get_rate_limiter",
    "set_rate_limiter",
    "get_checkpoint_manager",
    "set_checkpoint_manager",
    "setup_signal_handlers",
    "is_shutdown_requested",
    "request_shutdown",
    # pdf_processing
    "PDFCache",
    "PDF_SUPPORT",
    "MAX_PDF_CHARS",
    "get_pdf_cache",
    "set_pdf_cache",
    "download_pdf_bytes",
    "extract_text_from_pdf_bytes",
    "download_pdf_text",
    "download_pdf_with_figures",
    "store_figures_in_db",
    "extract_and_store_figures",
    # figure_extraction_from_pdf
    "Caption",
    "FIGURES_DIR",
    "PYMUPDF_AVAILABLE",
    "PILLOW_AVAILABLE",
    "extract_figures_from_pdf_bytes",
    "extract_paper_id_from_url",
    "find_all_captions",
    "find_graphics_bounds",
    "get_column_bounds",
    # arxiv_html_processing
    "BS4_AVAILABLE",
    "MAX_HTML_CHARS",
    "is_arxiv_url",
    "get_arxiv_id_from_url",
    "get_html_url_from_arxiv_url",
    "check_html_available",
    "extract_text_from_html",
    "extract_figures_from_html",
    "download_arxiv_html_with_figures",
    # llm_client
    "get_config_value",
    "get_api_key",
    "get_api_url",
    "get_default_model",
    "get_lightweight_model",
    "call_gemini_api",
]
