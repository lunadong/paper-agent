#!/usr/bin/python3
"""
OpenReview Paper Fetcher

Fetches paper metadata from OpenReview (used by ICLR and other ML conferences).
Extracts authors and abstracts from conference proceedings.

Usage:
    python openreview_fetcher.py https://openreview.net/forum?id=xxx
    python openreview_fetcher.py https://proceedings.iclr.cc/paper_files/paper/2025/file/xxx.pdf
"""

import argparse
import re
import time
from typing import Optional

import requests

REQUEST_DELAY = 0.5
MAX_RETRIES = 3
RETRY_DELAY = 5

_last_request_time = 0


def extract_openreview_id(url: str) -> Optional[str]:
    """
    Extract OpenReview paper ID from various URL formats.

    Handles:
    - https://openreview.net/forum?id=xxx
    - https://openreview.net/pdf?id=xxx
    - https://proceedings.iclr.cc/paper_files/paper/2025/file/xxx-Paper-Conference.pdf

    Returns:
        OpenReview ID or None if not found
    """
    if "openreview.net" in url:
        match = re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)

    if "proceedings.iclr.cc" in url:
        match = re.search(r"/file/([a-f0-9]+)-", url)
        if match:
            return match.group(1)

    return None


def is_openreview_paper(url: str) -> bool:
    """Check if a URL is from OpenReview or ICLR proceedings."""
    return (
        "openreview.net" in url
        or "proceedings.iclr.cc" in url
        or "iclr.cc" in url.lower()
    )


def fetch_openreview_html(forum_id: str) -> Optional[str]:
    """
    Fetch HTML content from an OpenReview forum page.

    Args:
        forum_id: OpenReview paper ID

    Returns:
        HTML content as a string, or None on error
    """
    global _last_request_time

    url = f"https://openreview.net/forum?id={forum_id}"

    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

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


def fetch_openreview_api(forum_id: str) -> Optional[dict]:
    """
    Fetch paper metadata from OpenReview API.

    Args:
        forum_id: OpenReview paper ID

    Returns:
        API response as dict, or None on error
    """
    global _last_request_time

    api_url = f"https://api.openreview.net/notes?id={forum_id}"

    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(api_url, timeout=30)
            _last_request_time = time.time()
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} after error: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Failed after {MAX_RETRIES} attempts: {e}")
                return None

    return None


def extract_authors_from_html(html_content: str) -> list[str]:
    """
    Extract author names from OpenReview HTML page.

    Args:
        html_content: HTML content from OpenReview page

    Returns:
        List of author names
    """
    authors = []

    author_pattern = re.compile(
        r'<meta\s+name="citation_author"\s+content="([^"]+)"',
        re.IGNORECASE,
    )
    matches = author_pattern.findall(html_content)
    if matches:
        authors = [m.strip() for m in matches]
        return authors

    author_link_pattern = re.compile(
        r'<a[^>]*href="[^"]*profile\?id=[^"]*"[^>]*>([^<]+)</a>',
        re.IGNORECASE,
    )
    matches = author_link_pattern.findall(html_content)
    if matches:
        authors = [m.strip() for m in matches if len(m.strip()) > 2]
        return authors[:20]

    return authors


def extract_abstract_from_html(html_content: str) -> Optional[str]:
    """
    Extract abstract from OpenReview HTML page.

    Args:
        html_content: HTML content from OpenReview page

    Returns:
        Abstract text or None if not found
    """
    abstract_pattern = re.compile(
        r'<meta\s+name="citation_abstract"\s+content="([^"]+)"',
        re.IGNORECASE | re.DOTALL,
    )
    match = abstract_pattern.search(html_content)
    if match:
        abstract = match.group(1).strip()
        abstract = re.sub(r"\s+", " ", abstract)
        return abstract

    return None


def extract_title_from_html(html_content: str) -> Optional[str]:
    """
    Extract title from OpenReview HTML page.

    Args:
        html_content: HTML content from OpenReview page

    Returns:
        Title text or None if not found
    """
    title_pattern = re.compile(
        r'<meta\s+name="citation_title"\s+content="([^"]+)"',
        re.IGNORECASE,
    )
    match = title_pattern.search(html_content)
    if match:
        return match.group(1).strip()

    return None


def extract_paper_info_from_api(api_response: dict) -> dict:
    """
    Extract paper info from OpenReview API response.

    Args:
        api_response: JSON response from OpenReview API

    Returns:
        Dictionary with 'title', 'authors', 'abstract', 'venue' fields
    """
    result = {
        "title": None,
        "authors": [],
        "abstract": None,
        "venue": None,
    }

    if not api_response or "notes" not in api_response:
        return result

    notes = api_response.get("notes", [])
    if not notes:
        return result

    note = notes[0]
    content = note.get("content", {})

    if "title" in content:
        title_val = content["title"]
        result["title"] = (
            title_val.get("value") if isinstance(title_val, dict) else title_val
        )

    if "authors" in content:
        authors_val = content["authors"]
        if isinstance(authors_val, dict):
            result["authors"] = authors_val.get("value", [])
        elif isinstance(authors_val, list):
            result["authors"] = authors_val

    if "abstract" in content:
        abstract_val = content["abstract"]
        result["abstract"] = (
            abstract_val.get("value")
            if isinstance(abstract_val, dict)
            else abstract_val
        )

    venue = note.get("venue")
    if venue:
        result["venue"] = venue

    return result


def extract_paper_info(url: str) -> dict:
    """
    Extract paper information from an OpenReview/ICLR URL.

    Tries API first, falls back to HTML scraping.

    Args:
        url: OpenReview or ICLR proceedings URL

    Returns:
        Dictionary with 'title', 'authors', 'abstract', 'venue' fields
    """
    result = {
        "title": None,
        "authors": [],
        "abstract": None,
        "venue": None,
    }

    forum_id = extract_openreview_id(url)
    if not forum_id:
        return result

    api_response = fetch_openreview_api(forum_id)
    if api_response:
        api_info = extract_paper_info_from_api(api_response)
        if api_info.get("authors") or api_info.get("abstract"):
            return api_info

    html_content = fetch_openreview_html(forum_id)
    if html_content:
        result["title"] = extract_title_from_html(html_content)
        result["authors"] = extract_authors_from_html(html_content)
        result["abstract"] = extract_abstract_from_html(html_content)

    return result


def get_openreview_forum_url(paper_id: str) -> str:
    """Convert paper ID to OpenReview forum URL."""
    return f"https://openreview.net/forum?id={paper_id}"


def main():
    """Main function to test OpenReview fetching and extraction."""
    parser = argparse.ArgumentParser(
        description="Fetch paper info from OpenReview/ICLR."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://openreview.net/forum?id=ScRhEuj480",
        help="OpenReview or ICLR proceedings URL",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw API/HTML response instead of extracted fields",
    )
    args = parser.parse_args()

    print(f"Fetching: {args.url}")

    forum_id = extract_openreview_id(args.url)
    if forum_id:
        print(f"OpenReview ID: {forum_id}")

    if args.raw:
        if forum_id:
            api_response = fetch_openreview_api(forum_id)
            if api_response:
                import json

                print("\n" + "=" * 60)
                print("API Response:")
                print("=" * 60)
                print(json.dumps(api_response, indent=2)[:3000])
            else:
                html_content = fetch_openreview_html(forum_id)
                if html_content:
                    print("\n" + "=" * 60)
                    print("HTML Preview (first 2000 chars):")
                    print("=" * 60)
                    print(html_content[:2000])
    else:
        paper_info = extract_paper_info(args.url)

        print("\n" + "=" * 60)
        print("Extracted Paper Information:")
        print("=" * 60)

        print(f"\nTitle: {paper_info.get('title')}")
        print(f"\nAuthors: {', '.join(paper_info.get('authors', []))}")
        print(f"\nAbstract: {paper_info.get('abstract')}")
        print(f"\nVenue: {paper_info.get('venue')}")


if __name__ == "__main__":
    main()
