#!/usr/bin/env python3
"""
arXiv API Backend for paper search and retrieval.

This module provides functions to search and fetch papers from the arXiv API.
It supports searching by query, filtering by categories and date ranges.

API Documentation: https://info.arxiv.org/help/api/basics.html

Rate limits: ~3 requests/second (generous)
No API key required.
"""

import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import requests

# arXiv API configuration
ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_REQUEST_DELAY = 0.5  # seconds between requests (conservative)
ARXIV_MAX_RESULTS_PER_PAGE = 100  # API limit per request

# Default categories for AI/ML/NLP papers
DEFAULT_CATEGORIES = ["cs.CL", "cs.LG", "cs.AI", "cs.IR"]

# XML namespace for arXiv API responses
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# Module-level rate limiting
_last_request_time = 0.0


def _rate_limit() -> None:
    """Enforce rate limiting between requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < ARXIV_REQUEST_DELAY:
        time.sleep(ARXIV_REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _make_request(url: str, max_retries: int = 3) -> Optional[str]:
    """
    Make HTTP request with retry logic.

    Args:
        url: URL to fetch
        max_retries: Maximum number of retry attempts

    Returns:
        Response content as string, or None if failed
    """
    _rate_limit()

    headers = {"User-Agent": "PaperAgent/1.0 (research paper collection tool)"}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503:  # Service unavailable, retry
                wait_time = (attempt + 1) * 10
                print(f"  arXiv API returned 503, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"  HTTP error {e.response.status_code}: {e}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return None

    return None


def _parse_arxiv_entry(entry: ET.Element) -> Optional[dict]:
    """
    Parse a single arXiv entry from the API response.

    Args:
        entry: XML Element for a single paper entry

    Returns:
        Dict with paper metadata or None if parsing fails
    """
    try:
        # Extract arXiv ID from the id URL
        id_elem = entry.find(f"{ATOM_NS}id")
        if id_elem is None or id_elem.text is None:
            return None

        arxiv_url = id_elem.text
        # Extract ID: http://arxiv.org/abs/2301.12345v1 -> 2301.12345
        match = re.search(r"arxiv\.org/abs/([^v]+)", arxiv_url)
        if not match:
            return None
        arxiv_id = match.group(1)

        # Title (clean up whitespace)
        title_elem = entry.find(f"{ATOM_NS}title")
        title = (
            title_elem.text.strip()
            if title_elem is not None and title_elem.text
            else ""
        )
        title = re.sub(r"\s+", " ", title)  # Normalize whitespace

        # Abstract (clean up whitespace)
        summary_elem = entry.find(f"{ATOM_NS}summary")
        abstract = (
            summary_elem.text.strip()
            if summary_elem is not None and summary_elem.text
            else ""
        )
        abstract = re.sub(r"\s+", " ", abstract)

        # Authors
        authors = []
        for author_elem in entry.findall(f"{ATOM_NS}author"):
            name_elem = author_elem.find(f"{ATOM_NS}name")
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())
        authors_str = ", ".join(authors)

        # Publication date (submitted date)
        published_elem = entry.find(f"{ATOM_NS}published")
        if published_elem is not None and published_elem.text:
            # Format: 2023-01-15T12:34:56Z -> 2023-01-15
            pub_date = published_elem.text[:10]
            year = pub_date[:4]
        else:
            pub_date = None
            year = None

        # Categories
        categories = []
        for cat_elem in entry.findall(f"{ARXIV_NS}primary_category"):
            term = cat_elem.get("term")
            if term:
                categories.append(term)
        for cat_elem in entry.findall(f"{ATOM_NS}category"):
            term = cat_elem.get("term")
            if term and term not in categories:
                categories.append(term)

        # PDF link
        pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        abs_link = f"https://arxiv.org/abs/{arxiv_id}"

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors_str,
            "abstract": abstract,
            "year": year,
            "venue": "arXiv",
            "link": abs_link,
            "pdf_link": pdf_link,
            "recomm_date": pub_date,
            "categories": categories,
            "source": "arxiv",
        }

    except Exception as e:
        print(f"  Error parsing entry: {e}")
        return None


def _parse_arxiv_response(content: str) -> list[dict]:
    """
    Parse arXiv API XML response.

    Args:
        content: XML response content

    Returns:
        List of paper dicts
    """
    papers = []
    try:
        root = ET.fromstring(content)
        for entry in root.findall(f"{ATOM_NS}entry"):
            paper = _parse_arxiv_entry(entry)
            if paper:
                papers.append(paper)
    except ET.ParseError as e:
        print(f"  XML parse error: {e}")

    return papers


def _build_date_query(days: int) -> str:
    """
    Build arXiv date filter query.

    Args:
        days: Number of days to look back

    Returns:
        Date filter string for arXiv API
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # arXiv date format: YYYYMMDDHHMI
    start_str = start_date.strftime("%Y%m%d0000")
    end_str = end_date.strftime("%Y%m%d2359")

    return f"submittedDate:[{start_str} TO {end_str}]"


def _build_category_query(categories: list[str]) -> str:
    """
    Build arXiv category filter query.

    Args:
        categories: List of arXiv category codes

    Returns:
        Category filter string for arXiv API
    """
    if not categories:
        return ""

    # OR together multiple categories: (cat:cs.CL OR cat:cs.LG)
    cat_queries = [f"cat:{cat}" for cat in categories]
    return "(" + " OR ".join(cat_queries) + ")"


def search_arxiv(
    query: Optional[str] = None,
    categories: Optional[list[str]] = None,
    days: Optional[int] = None,
    year_start: Optional[int] = None,
    max_results: int = 100,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
) -> list[dict]:
    """
    Search arXiv API for papers.

    Args:
        query: Search query (searches title, abstract, authors)
        categories: List of arXiv category codes (e.g., ["cs.CL", "cs.LG"])
        days: Only return papers from the last N days
        year_start: Only return papers from this year onwards
        max_results: Maximum number of results to return
        sort_by: Sort field ("submittedDate", "relevance", "lastUpdatedDate")
        sort_order: Sort direction ("ascending", "descending")

    Returns:
        List of paper dicts with keys:
        - arxiv_id, title, authors, abstract, year
        - venue, link, pdf_link, recomm_date
        - categories, source
    """
    if categories is None:
        categories = DEFAULT_CATEGORIES

    # Build search query
    query_parts = []

    # Add text search
    if query:
        # Search in all fields (title, abstract, authors)
        clean_query = query.replace('"', "").strip()
        words = clean_query.split()
        if len(words) > 1:
            # Multi-word: use AND logic so all terms must appear (any order)
            # This is much more effective than phrase matching for topic search
            term_queries = [f"all:{word}" for word in words]
            query_parts.append("(" + " AND ".join(term_queries) + ")")
        else:
            query_parts.append(f"all:{clean_query}")

    # Add category filter
    cat_query = _build_category_query(categories)
    if cat_query:
        query_parts.append(cat_query)

    # Add date filter
    if days:
        date_query = _build_date_query(days)
        query_parts.append(date_query)

    # Combine query parts with AND
    if query_parts:
        search_query = " AND ".join(query_parts)
    else:
        # Default: search all papers in specified categories
        search_query = _build_category_query(categories)

    print(f"arXiv search query: {search_query[:100]}...")

    # Fetch results with pagination
    all_papers = []
    start = 0

    while len(all_papers) < max_results:
        # Calculate how many to fetch this page
        remaining = max_results - len(all_papers)
        page_size = min(remaining, ARXIV_MAX_RESULTS_PER_PAGE)

        # Build URL
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": page_size,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"

        print(f"  Fetching results {start + 1}-{start + page_size}...")

        # Make request
        content = _make_request(url)
        if not content:
            print("  Failed to fetch results, stopping")
            break

        # Parse response
        papers = _parse_arxiv_response(content)
        if not papers:
            print("  No more results")
            break

        # Filter by year if specified
        if year_start:
            papers = [
                p for p in papers if p.get("year") and int(p["year"]) >= year_start
            ]

        all_papers.extend(papers)
        print(f"  Found {len(papers)} papers (total: {len(all_papers)})")

        # Check if we got fewer than requested (no more results)
        if len(papers) < page_size:
            break

        start += page_size

    return all_papers[:max_results]


def fetch_recent_papers(
    categories: Optional[list[str]] = None,
    days: int = 7,
    max_results: int = 500,
) -> list[dict]:
    """
    Fetch papers submitted in the last N days.

    Args:
        categories: List of arXiv category codes (default: cs.CL, cs.LG, cs.AI, cs.IR)
        days: Number of days to look back (default: 7)
        max_results: Maximum number of results (default: 500)

    Returns:
        List of paper dicts sorted by submission date (newest first)
    """
    if categories is None:
        categories = DEFAULT_CATEGORIES

    print(f"Fetching papers from last {days} days")
    print(f"Categories: {', '.join(categories)}")

    papers = search_arxiv(
        query=None,
        categories=categories,
        days=days,
        max_results=max_results,
        sort_by="submittedDate",
        sort_order="descending",
    )

    print(f"Found {len(papers)} papers from the last {days} days")
    return papers


def fetch_paper_by_id(arxiv_id: str) -> Optional[dict]:
    """
    Fetch a single paper by arXiv ID.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2301.12345")

    Returns:
        Paper dict or None if not found
    """
    # Clean the ID (remove version suffix if present)
    clean_id = re.sub(r"v\d+$", "", arxiv_id)

    url = f"{ARXIV_API_URL}?id_list={clean_id}"
    content = _make_request(url)

    if not content:
        return None

    papers = _parse_arxiv_response(content)
    return papers[0] if papers else None


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test arXiv backend")
    parser.add_argument("--query", type=str, help="Search query")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--max", type=int, default=10, help="Max results")
    parser.add_argument(
        "--categories",
        type=str,
        default="cs.CL,cs.LG,cs.AI,cs.IR",
        help="Comma-separated categories",
    )
    args = parser.parse_args()

    categories = args.categories.split(",")

    if args.query:
        print(f"\nSearching for: {args.query}")
        papers = search_arxiv(
            query=args.query,
            categories=categories,
            max_results=args.max,
        )
    else:
        print(f"\nFetching recent papers (last {args.days} days)")
        papers = fetch_recent_papers(
            categories=categories,
            days=args.days,
            max_results=args.max,
        )

    print(f"\nFound {len(papers)} papers:\n")
    for i, paper in enumerate(papers, 1):
        print(f"{i}. [{paper['arxiv_id']}] {paper['title'][:70]}...")
        print(f"   Authors: {paper['authors'][:60]}...")
        print(
            f"   Date: {paper['recomm_date']} | Categories: {', '.join(paper['categories'][:3])}"
        )
        print()
