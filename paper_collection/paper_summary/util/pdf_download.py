#!/usr/bin/env python3
"""
PDF Download Module

Provides PDF downloading with retry logic.
Extracted from pdf_processing.py to break circular dependencies.
"""

import time

try:
    import requests
except ImportError:
    print("Error: requests package not installed.")
    print("Install it with: pip install requests")
    raise


# Retry configuration
RETRY_BASE_DELAY = 2
RETRY_MAX_DELAY = 30


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
