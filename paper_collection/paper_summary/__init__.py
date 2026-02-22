#!/usr/bin/env python3
"""
Paper Summary Module

A modular system for generating structured JSON summaries of research papers
using LLM APIs (Google Gemini via wearables-ape.io).

Structure:
    - util/: Reusable utilities (checkpoint, pdf_processing, llm_client)
    - prompt_manager: Prompt template loading (domain-specific)
    - summary_generation: Main orchestration and processing
"""

from .prompt_manager import (
    ALLOWED_TOPICS,
    get_prompts_dir,
    load_prompt_template,
    load_topic_prompt,
    TOPIC_BACKGROUND_FILES,
)
from .util import (
    call_gemini_api,
    CheckpointManager,
    download_pdf_bytes,
    download_pdf_text,
    download_pdf_with_figures,
    extract_and_store_figures,
    extract_text_from_pdf_bytes,
    get_api_key,
    get_api_url,
    get_checkpoint_manager,
    get_config_value,
    get_default_model,
    get_lightweight_model,
    get_pdf_cache,
    get_rate_limiter,
    is_shutdown_requested,
    MAX_PDF_CHARS,
    PDF_SUPPORT,
    PDFCache,
    RateLimiter,
    request_shutdown,
    set_checkpoint_manager,
    set_pdf_cache,
    set_rate_limiter,
    setup_signal_handlers,
    store_figures_in_db,
)

__all__ = [
    # util.checkpoint
    "RateLimiter",
    "CheckpointManager",
    "get_rate_limiter",
    "set_rate_limiter",
    "get_checkpoint_manager",
    "set_checkpoint_manager",
    "setup_signal_handlers",
    "is_shutdown_requested",
    "request_shutdown",
    # util.pdf_processing
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
    # util.llm_client
    "load_config",
    "get_config_value",
    "get_api_key",
    "get_api_url",
    "get_default_model",
    "get_lightweight_model",
    "call_gemini_api",
    # prompt_manager
    "TOPIC_BACKGROUND_FILES",
    "ALLOWED_TOPICS",
    "load_topic_prompt",
    "load_prompt_template",
    "get_prompts_dir",
]
