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


def get_arxiv_pdf_url(arxiv_id: str) -> str:
    """Convert arXiv ID to PDF download URL."""
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def search_arxiv_by_title(title: str):
    """
    Search arXiv for a paper by title.

    Args:
        title: Paper title to search for

    Returns:
        arXiv ID (e.g., "2601.12345") if found, None otherwise
    """
    global _last_request_time
    import urllib.parse
    import xml.etree.ElementTree as ET

    # Clean the title for search
    clean_title = re.sub(r"[^\w\s]", " ", title)  # Remove punctuation
    clean_title = re.sub(r"\s+", " ", clean_title).strip()  # Normalize whitespace

    # Extract key words from title (skip common short words)
    stop_words = {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "for",
        "to",
        "and",
        "or",
        "is",
        "are",
        "with",
        "by",
        "from",
        "as",
        "at",
    }
    words = [
        w for w in clean_title.lower().split() if w not in stop_words and len(w) > 2
    ]

    # Use top 5-6 distinctive words to avoid URL length issues
    # Prioritize longer words as they're more distinctive
    words.sort(key=len, reverse=True)
    search_words = words[:6]

    if not search_words:
        return None

    # Build search query using AND logic: (ti:word1 AND ti:word2 AND ...)
    # This finds papers where all words appear in the title
    term_queries = [f"ti:{word}" for word in search_words]
    search_query = "(" + " AND ".join(term_queries) + ")"

    # URL encode the query
    encoded_query = urllib.parse.quote(search_query)
    api_url = (
        f"http://export.arxiv.org/api/query?search_query={encoded_query}&max_results=5"
    )

    # Rate limiting
    elapsed = time.time() - _last_request_time
    if elapsed < ARXIV_REQUEST_DELAY:
        time.sleep(ARXIV_REQUEST_DELAY - elapsed)

    try:
        response = requests.get(api_url, timeout=30)
        _last_request_time = time.time()
        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.text)

        # Define namespace
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Search for matching entries
        for entry in root.findall("atom:entry", ns):
            entry_title_elem = entry.find("atom:title", ns)
            entry_id_elem = entry.find("atom:id", ns)

            if entry_title_elem is not None and entry_id_elem is not None:
                entry_title = entry_title_elem.text
                entry_id = entry_id_elem.text

                if entry_title and entry_id:
                    # Clean entry title for comparison
                    entry_title_clean = re.sub(r"\s+", " ", entry_title).strip().lower()
                    title_clean = clean_title.lower()

                    # Check for fuzzy match (80% of words match)
                    title_words = set(title_clean.split())
                    entry_words = set(entry_title_clean.split())

                    if len(title_words) > 0:
                        overlap = len(title_words & entry_words) / len(title_words)
                        if overlap >= 0.8:
                            # Extract arXiv ID from URL like "http://arxiv.org/abs/2601.12345v1"
                            match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", entry_id)
                            if match:
                                return match.group(1)

        return None

    except Exception as e:
        print(f"  arXiv search failed: {e}")
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


def extract_full_date(html_content):
    """
    Extract the full submission date from arXiv HTML.

    Looks for text like: [Submitted on 4 Mar 2024 (v1), last revised 4 Jun 2024 (this version, v4)]
    Returns the date in YYYY-MM-DD format (e.g., "2024-03-04").

    Args:
        html_content: HTML content from arXiv page

    Returns:
        Date string in YYYY-MM-DD format, or None if not found
    """
    # Pattern to match "Submitted on DD Mon YYYY"
    pattern = r"\[Submitted on\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
    match = re.search(pattern, html_content)

    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = match.group(3)

        month_num = MONTH_MAP.get(month_name)
        if month_num:
            return f"{year}-{month_num:02d}-{day:02d}"

    return None


def extract_authors(html_content):
    """
    Extract the authors from arXiv HTML.

    Args:
        html_content: HTML content from arXiv page

    Returns:
        Comma-separated author string, or None if not found
    """
    # arXiv authors are in <div class="authors"> or <meta name="citation_author">
    # Try meta tags first (more reliable)
    meta_pattern = r'<meta\s+name="citation_author"\s+content="([^"]+)"'
    authors = re.findall(meta_pattern, html_content)

    if authors:
        return ", ".join(authors)

    # Fallback: try <div class="authors">
    div_pattern = re.compile(
        r'<div[^>]*class="authors"[^>]*>(.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    match = div_pattern.search(html_content)

    if match:
        authors_html = match.group(1)
        # Extract names from <a> tags
        name_pattern = r"<a[^>]*>([^<]+)</a>"
        names = re.findall(name_pattern, authors_html)
        if names:
            return ", ".join(names)

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
        Dictionary with 'date', 'full_date', 'abstract', and 'authors' fields
    """
    return {
        "date": extract_date(html_content),
        "full_date": extract_full_date(html_content),
        "abstract": extract_abstract(html_content),
        "authors": extract_authors(html_content),
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
