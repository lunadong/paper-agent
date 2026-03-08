#!/usr/bin/env python3
"""
Semantic Scholar API Backend for paper search and retrieval.

This module provides functions to search and fetch papers from the Semantic Scholar API.
It supports searching by query, filtering by fields of study and date ranges.

API Documentation: https://api.semanticscholar.org/api-docs/

Rate limits (free tier): 100 requests per 5 minutes
API key optional but recommended for higher limits.
"""

import re
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

# Semantic Scholar API configuration
S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
S2_SEARCH_ENDPOINT = f"{S2_API_BASE}/paper/search"
S2_PAPER_ENDPOINT = f"{S2_API_BASE}/paper"
S2_BATCH_ENDPOINT = f"{S2_API_BASE}/paper/batch"

# Rate limiting: 100 requests per 5 minutes = 1 request per 3 seconds (conservative)
S2_REQUEST_DELAY = 3.0  # seconds between requests
S2_MAX_RESULTS_PER_PAGE = 100  # API limit per request

# Fields to request from the API
S2_PAPER_FIELDS = [
    "paperId",
    "externalIds",
    "title",
    "abstract",
    "venue",
    "year",
    "authors",
    "publicationDate",
    "openAccessPdf",
    "fieldsOfStudy",
    "citationCount",
]

# Default fields of study for CS papers
DEFAULT_FIELDS_OF_STUDY = ["Computer Science"]

# Module-level rate limiting
_last_request_time = 0.0
_request_count = 0
_window_start = 0.0


def _rate_limit() -> None:
    """
    Enforce rate limiting between requests.

    Implements conservative rate limiting to stay well under 100 req/5 min.
    """
    global _last_request_time, _request_count, _window_start

    current_time = time.time()

    # Reset counter every 5 minutes
    if current_time - _window_start > 300:
        _request_count = 0
        _window_start = current_time

    # If approaching limit, wait longer
    if _request_count >= 90:  # Leave buffer
        wait_time = 300 - (current_time - _window_start)
        if wait_time > 0:
            print(f"  Approaching rate limit, waiting {wait_time:.0f}s...")
            time.sleep(wait_time)
            _request_count = 0
            _window_start = time.time()

    # Enforce minimum delay between requests
    elapsed = current_time - _last_request_time
    if elapsed < S2_REQUEST_DELAY:
        time.sleep(S2_REQUEST_DELAY - elapsed)

    _last_request_time = time.time()
    _request_count += 1


def _make_request(
    url: str,
    params: Optional[dict] = None,
    api_key: Optional[str] = None,
    max_retries: int = 3,
) -> Optional[dict]:
    """
    Make HTTP request to Semantic Scholar API with retry logic.

    Args:
        url: API endpoint URL
        params: Query parameters
        api_key: Optional API key for higher rate limits
        max_retries: Maximum number of retry attempts

    Returns:
        JSON response as dict, or None if failed
    """
    _rate_limit()

    headers = {"User-Agent": "PaperAgent/1.0 (research paper collection tool)"}
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)

            if response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
            elif e.response.status_code == 404:
                return None  # Paper not found
            else:
                print(f"  HTTP error {e.response.status_code}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return None
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return None

    return None


def _parse_s2_paper(paper: dict) -> Optional[dict]:
    """
    Parse a single paper from Semantic Scholar API response.

    Args:
        paper: Paper dict from API response

    Returns:
        Standardized paper dict or None if parsing fails
    """
    try:
        paper_id = paper.get("paperId")
        if not paper_id:
            return None

        title = paper.get("title", "").strip()
        if not title:
            return None

        # Authors
        authors = paper.get("authors", [])
        authors_str = ", ".join(a.get("name", "") for a in authors if a.get("name"))

        # Abstract
        abstract = paper.get("abstract", "") or ""

        # Year
        year = paper.get("year")
        year_str = str(year) if year else None

        # Venue
        venue = paper.get("venue", "") or ""

        # Publication date (for recomm_date)
        pub_date = paper.get("publicationDate")  # Format: "2023-01-15"
        if pub_date:
            recomm_date = pub_date
        elif year:
            recomm_date = f"{year}-06-25"  # Default to mid-year
        else:
            recomm_date = None

        # External IDs
        external_ids = paper.get("externalIds", {}) or {}
        arxiv_id = external_ids.get("ArXiv")
        doi = external_ids.get("DOI")
        acl_id = external_ids.get("ACL")

        # Link (prefer arXiv, then open access PDF, then S2 page)
        link = None
        pdf_link = None

        if arxiv_id:
            link = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        elif paper.get("openAccessPdf", {}).get("url"):
            link = paper["openAccessPdf"]["url"]
            pdf_link = link
        elif acl_id:
            link = f"https://aclanthology.org/{acl_id}"
            pdf_link = f"https://aclanthology.org/{acl_id}.pdf"
        elif doi:
            link = f"https://doi.org/{doi}"
        else:
            link = f"https://www.semanticscholar.org/paper/{paper_id}"

        # Fields of study
        fields = paper.get("fieldsOfStudy", []) or []

        # Citation count
        citation_count = paper.get("citationCount", 0)

        return {
            "s2_paper_id": paper_id,
            "arxiv_id": arxiv_id,
            "doi": doi,
            "title": title,
            "authors": authors_str,
            "abstract": abstract,
            "year": year_str,
            "venue": venue,
            "link": link,
            "pdf_link": pdf_link,
            "recomm_date": recomm_date,
            "fields_of_study": fields,
            "citation_count": citation_count,
            "source": "semantic_scholar",
        }

    except Exception as e:
        print(f"  Error parsing paper: {e}")
        return None


def _build_year_filter(days, year_start, year_end):
    """Build year filter string for Semantic Scholar API."""
    if days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return f"{start_date.year}-{end_date.year}"
    if year_start or year_end:
        start = year_start or 1900
        end = year_end or datetime.now().year
        return f"{start}-{end}"
    return None


def _should_include_paper_by_date(paper, days):
    """Check if paper should be included based on date filter."""
    if not days or not paper.get("recomm_date"):
        return True

    try:
        pub_date = datetime.strptime(paper["recomm_date"], "%Y-%m-%d")
        cutoff_date = datetime.now() - timedelta(days=days)
        return pub_date >= cutoff_date
    except ValueError:
        return True  # Invalid date format, include anyway


def _fetch_s2_page(query, offset, limit, fields_of_study, year_filter, api_key):
    """Fetch a single page of results from Semantic Scholar."""
    params = {
        "query": query,
        "offset": offset,
        "limit": limit,
        "fields": ",".join(S2_PAPER_FIELDS),
    }

    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)

    if year_filter:
        params["year"] = year_filter

    return _make_request(S2_SEARCH_ENDPOINT, params=params, api_key=api_key)


def search_semantic_scholar(
    query: str,
    fields_of_study: Optional[list[str]] = None,
    days: Optional[int] = None,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    max_results: int = 100,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Search Semantic Scholar API for papers.

    Args:
        query: Search query (searches title, abstract)
        fields_of_study: List of fields to filter by (e.g., ["Computer Science"])
        days: Only return papers from the last N days
        year_start: Only return papers from this year onwards
        year_end: Only return papers up to this year
        max_results: Maximum number of results to return
        api_key: Optional API key for higher rate limits

    Returns:
        List of paper dicts with keys:
        - s2_paper_id, arxiv_id, doi, title, authors, abstract, year
        - venue, link, pdf_link, recomm_date
        - fields_of_study, citation_count, source
    """
    if fields_of_study is None:
        fields_of_study = DEFAULT_FIELDS_OF_STUDY

    print(f"Semantic Scholar search: {query[:50]}...")

    year_filter = _build_year_filter(days, year_start, year_end)

    # Fetch results with pagination
    all_papers = []
    offset = 0

    while len(all_papers) < max_results:
        remaining = max_results - len(all_papers)
        limit = min(remaining, S2_MAX_RESULTS_PER_PAGE)

        print(f"  Fetching results {offset + 1}-{offset + limit}...")

        response = _fetch_s2_page(
            query, offset, limit, fields_of_study, year_filter, api_key
        )

        if not response:
            print("  Failed to fetch results, stopping")
            break

        papers_data = response.get("data", [])
        if not papers_data:
            print("  No more results")
            break

        # Parse and filter papers
        for paper_data in papers_data:
            paper = _parse_s2_paper(paper_data)
            if paper and _should_include_paper_by_date(paper, days):
                all_papers.append(paper)

        print(f"  Found {len(papers_data)} papers (total: {len(all_papers)})")

        # Check if we got fewer than requested (no more results)
        if len(papers_data) < limit:
            break

        offset += limit

        # Check total available
        total_available = response.get("total", 0)
        if offset >= total_available:
            break

    return all_papers[:max_results]


def fetch_recent_papers(
    fields_of_study: Optional[list[str]] = None,
    days: int = 7,
    max_results: int = 500,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Fetch papers published in the last N days.

    Note: Semantic Scholar's search API doesn't support exact date filtering,
    so we use year filtering and then post-filter by publication date.

    Args:
        fields_of_study: List of fields to filter by (default: Computer Science)
        days: Number of days to look back (default: 7)
        max_results: Maximum number of results (default: 500)
        api_key: Optional API key

    Returns:
        List of paper dicts sorted by publication date (newest first)
    """
    if fields_of_study is None:
        fields_of_study = DEFAULT_FIELDS_OF_STUDY

    print(f"Fetching papers from last {days} days")
    print(f"Fields of study: {', '.join(fields_of_study)}")

    # Search for recent papers using a wildcard-like approach
    # S2 doesn't have a "get recent" endpoint, so we search with common terms
    papers = search_semantic_scholar(
        query="machine learning OR deep learning OR neural network OR language model",
        fields_of_study=fields_of_study,
        days=days,
        max_results=max_results * 2,  # Fetch more, then filter
        api_key=api_key,
    )

    # Filter by exact date range
    cutoff_date = datetime.now() - timedelta(days=days)
    filtered_papers = []

    for paper in papers:
        pub_date_str = paper.get("recomm_date")
        if pub_date_str:
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
                if pub_date >= cutoff_date:
                    filtered_papers.append(paper)
            except ValueError:
                pass  # Skip papers with invalid dates

    # Sort by date (newest first)
    filtered_papers.sort(
        key=lambda p: p.get("recomm_date") or "1900-01-01",
        reverse=True,
    )

    print(f"Found {len(filtered_papers)} papers from the last {days} days")
    return filtered_papers[:max_results]


def fetch_paper_by_id(
    paper_id: str,
    id_type: str = "auto",
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Fetch a single paper by ID.

    Args:
        paper_id: Paper identifier
        id_type: Type of ID - "s2" (Semantic Scholar), "arxiv", "doi", or "auto"
        api_key: Optional API key

    Returns:
        Paper dict or None if not found
    """
    # Determine ID format
    if id_type == "auto":
        if paper_id.startswith("10."):
            id_type = "doi"
        elif re.match(r"\d{4}\.\d+", paper_id):
            id_type = "arxiv"
        else:
            id_type = "s2"

    # Build URL with appropriate prefix
    if id_type == "arxiv":
        url = f"{S2_PAPER_ENDPOINT}/arXiv:{paper_id}"
    elif id_type == "doi":
        url = f"{S2_PAPER_ENDPOINT}/DOI:{paper_id}"
    else:
        url = f"{S2_PAPER_ENDPOINT}/{paper_id}"

    params = {"fields": ",".join(S2_PAPER_FIELDS)}

    response = _make_request(url, params=params, api_key=api_key)

    if not response:
        return None

    return _parse_s2_paper(response)


def fetch_papers_by_arxiv_ids(
    arxiv_ids: list[str],
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Fetch multiple papers by their arXiv IDs using batch endpoint.

    Args:
        arxiv_ids: List of arXiv IDs (e.g., ["2301.12345", "2302.67890"])
        api_key: Optional API key

    Returns:
        List of paper dicts
    """
    if not arxiv_ids:
        return []

    # Format IDs for batch endpoint
    formatted_ids = [f"arXiv:{aid}" for aid in arxiv_ids]

    papers = []

    # Process in batches of 500 (API limit)
    batch_size = 500
    for i in range(0, len(formatted_ids), batch_size):
        batch = formatted_ids[i : i + batch_size]

        print(f"  Fetching batch {i // batch_size + 1} ({len(batch)} papers)...")

        _rate_limit()

        headers = {"User-Agent": "PaperAgent/1.0"}
        if api_key:
            headers["x-api-key"] = api_key

        try:
            response = requests.post(
                S2_BATCH_ENDPOINT,
                params={"fields": ",".join(S2_PAPER_FIELDS)},
                json={"ids": batch},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()

            for paper_data in response.json():
                if paper_data:  # Can be None for not found papers
                    paper = _parse_s2_paper(paper_data)
                    if paper:
                        papers.append(paper)

        except Exception as e:
            print(f"  Batch request error: {e}")

    return papers


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Semantic Scholar backend")
    parser.add_argument("--query", type=str, help="Search query")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--max", type=int, default=10, help="Max results")
    parser.add_argument("--year-start", type=int, help="Start year filter")
    parser.add_argument("--api-key", type=str, help="API key")
    args = parser.parse_args()

    if args.query:
        print(f"\nSearching for: {args.query}")
        papers = search_semantic_scholar(
            query=args.query,
            year_start=args.year_start,
            max_results=args.max,
            api_key=args.api_key,
        )
    else:
        print(f"\nFetching recent papers (last {args.days} days)")
        papers = fetch_recent_papers(
            days=args.days,
            max_results=args.max,
            api_key=args.api_key,
        )

    print(f"\nFound {len(papers)} papers:\n")
    for i, paper in enumerate(papers, 1):
        print(
            f"{i}. [{paper.get('arxiv_id') or paper['s2_paper_id'][:8]}] {paper['title'][:70]}..."
        )
        print(f"   Authors: {paper['authors'][:60]}...")
        print(
            f"   Date: {paper['recomm_date']} | Venue: {paper['venue'][:30] if paper['venue'] else 'N/A'}"
        )
        print(
            f"   Citations: {paper['citation_count']} | Link: {paper['link'][:50]}..."
        )
        print()
