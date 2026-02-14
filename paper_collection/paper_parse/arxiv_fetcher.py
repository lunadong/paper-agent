#!/usr/bin/python3
"""
ArXiv Paper Fetcher

Fetches HTML content from arXiv abstract pages and extracts paper metadata.

Usage:
    python arxiv_fetcher.py https://arxiv.org/abs/2601.07696
"""

import argparse
import re
import sys
import time

import requests

# Rate limiting: delay between arXiv requests (seconds)
ARXIV_REQUEST_DELAY = 0.5  # Increased from 0.5 to reduce rate limiting

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds to wait before retrying

# Track last request time for rate limiting
_last_request_time = 0

# Month name to number mapping
MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def fetch_arxiv_html(url):
    """
    Fetch HTML content from an arXiv abstract page.
    Includes rate limiting and retry logic to handle connection errors.

    Args:
        url: arXiv URL starting with "https://arxiv.org/abs/"

    Returns:
        HTML content as a string, or None on error
    """
    global _last_request_time

    # Validate URL format
    if not url.startswith("https://arxiv.org/abs/"):
        raise ValueError(
            f"Invalid arXiv URL. Must start with 'https://arxiv.org/abs/'. Got: {url}"
        )

    # Rate limiting: wait if needed
    elapsed = time.time() - _last_request_time
    if elapsed < ARXIV_REQUEST_DELAY:
        time.sleep(ARXIV_REQUEST_DELAY - elapsed)

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=30)
            _last_request_time = time.time()
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} after error: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Failed after {MAX_RETRIES} attempts: {e}")
                return None

    return None


def extract_arxiv_id(url):
    """Extract the arXiv ID from a URL."""
    match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", url)
    if match:
        return match.group(1)
    return None


def extract_date(html_content):
    """
    Extract the submission date from arXiv HTML.

    Looks for text like: [Submitted on 4 Mar 2024 (v1), last revised 4 Jun 2024 (this version, v4)]
    Returns the date in M/YYYY format (e.g., "3/2024").

    Args:
        html_content: HTML content from arXiv page

    Returns:
        Date string in M/YYYY format, or None if not found
    """
    # Pattern to match "Submitted on DD Mon YYYY"
    pattern = r"\[Submitted on\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
    match = re.search(pattern, html_content)

    if match:
        month_name = match.group(2).lower()
        year = match.group(3)

        month_num = MONTH_MAP.get(month_name)
        if month_num:
            return f"{month_num}/{year}"

    return None


def extract_abstract(html_content):
    """
    Extract the abstract from arXiv HTML.

    Args:
        html_content: HTML content from arXiv page

    Returns:
        Abstract text as a string, or None if not found
    """
    # arXiv abstracts are in a <blockquote class="abstract mathjax">
    # with the format: <span class="descriptor">Abstract:</span> actual abstract text
    pattern = re.compile(
        r'<blockquote[^>]*class="abstract[^"]*"[^>]*>(.*?)</blockquote>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html_content)

    if match:
        abstract_html = match.group(1)

        # Remove the "Abstract:" descriptor span
        abstract_html = re.sub(
            r'<span[^>]*class="descriptor"[^>]*>.*?</span>',
            "",
            abstract_html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Remove HTML tags
        abstract_text = re.sub(r"<[^>]+>", "", abstract_html)

        # Clean up whitespace
        abstract_text = re.sub(r"\s+", " ", abstract_text).strip()

        return abstract_text

    return None


def extract_paper_info(html_content):
    """
    Extract all paper information from arXiv HTML.

    Args:
        html_content: HTML content from arXiv page

    Returns:
        Dictionary with 'date' and 'abstract' fields
    """
    return {
        "date": extract_date(html_content),
        "abstract": extract_abstract(html_content),
    }


def main():
    """Main function to test arXiv fetching and extraction."""
    parser = argparse.ArgumentParser(
        description="Fetch HTML from arXiv abstract pages."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://arxiv.org/abs/2601.07696",
        help="arXiv URL (default: https://arxiv.org/abs/2601.07696)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Save HTML to file instead of printing",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw HTML preview instead of extracted fields",
    )
    args = parser.parse_args()

    print(f"Fetching: {args.url}")

    arxiv_id = extract_arxiv_id(args.url)
    if arxiv_id:
        print(f"arXiv ID: {arxiv_id}")

    html_content = fetch_arxiv_html(args.url)

    if html_content:
        print(f"Successfully fetched {len(html_content)} bytes\n")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Saved to: {args.output}")
        elif args.raw:
            # Print first 2000 characters as preview
            print("=" * 60)
            print("HTML Preview (first 2000 chars):")
            print("=" * 60)
            print(html_content[:2000])
            print("\n... (truncated)")
        else:
            # Extract and display paper info
            paper_info = extract_paper_info(html_content)

            print("=" * 60)
            print("Extracted Paper Information:")
            print("=" * 60)

            print(f"\nDate: {paper_info['date']}")

            print(f"\nAbstract:\n{paper_info['abstract']}")
    else:
        print("Failed to fetch HTML content.")
        sys.exit(1)


if __name__ == "__main__":
    main()
