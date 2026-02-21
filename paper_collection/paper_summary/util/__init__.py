#!/usr/bin/env python3
"""
Utility Module for Paper Summary Generation

Contains reusable utilities for:
- Checkpoint management and rate limiting
- PDF processing (download, cache, extraction)
- LLM API client (Gemini)
"""

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
    # llm_client
    "get_config_value",
    "get_api_key",
    "get_api_url",
    "get_default_model",
    "get_lightweight_model",
    "call_gemini_api",
]
