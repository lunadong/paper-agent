#!/usr/bin/env python3
"""
LLM Client Module

Provides API client for Gemini LLM via wearables-ape.io, including
configuration loading and retry logic.
Extracted from summary_generation.py for modularity.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: requests package not installed.")
    print("Install it with: pip install requests")
    raise

# Handle both direct execution and package import
try:
    from .checkpoint import get_rate_limiter
except ImportError:
    from checkpoint import get_rate_limiter

# Import centralized config
# Add paper_collection to path for config import
_paper_collection_dir = str(Path(__file__).parent.parent.parent)
if _paper_collection_dir not in sys.path:
    sys.path.insert(0, _paper_collection_dir)

try:
    from core.config import config as get_app_config, GeminiConfig
except ImportError:
    # Fallback: define minimal config loading if config.py not available
    GeminiConfig = None
    get_app_config = None


# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2
RETRY_MAX_DELAY = 30
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ==============================================================================
# Configuration Loading (using centralized config.py)
# ==============================================================================
def _get_gemini_config() -> "GeminiConfig":
    """
    Get GeminiConfig from centralized config.py.

    Returns:
        GeminiConfig object with gemini settings.
    """
    if get_app_config is not None:
        return get_app_config().gemini
    # Fallback: return empty-ish config (will use env vars)
    if GeminiConfig is not None:
        return GeminiConfig()

    # Ultimate fallback: return a dict-like object
    class _FallbackConfig:
        api_key = ""
        api_url = ""
        model = "gemini-2.0-flash"
        lightweight_model = "gemini-2.0-flash-lite"

    return _FallbackConfig()


def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a value from config, environment, or default.

    Args:
        key: Config key (e.g., 'api_key', 'api_url', 'model')
        default: Default value if not found

    Returns:
        Config value string.
    """
    gemini_config = _get_gemini_config()
    env_key = f"GEMINI_{key.upper()}"

    # Check environment first
    env_value = os.environ.get(env_key)
    if env_value:
        return env_value

    # Then check config
    config_value = getattr(gemini_config, key, None)
    if config_value:
        return config_value

    return default


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


# ==============================================================================
# API Client
# ==============================================================================
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
