"""
Paper discovery modules for fetching papers from various sources.

This package provides unified interfaces for:
- arXiv API
- Semantic Scholar API
- Gmail client for email-based paper discovery
- Parsers for Google Scholar alerts
"""

import re
from typing import Optional

from .arxiv_backend import (
    fetch_paper_by_id as fetch_paper_by_arxiv_id,
    fetch_recent_papers as fetch_recent_papers_arxiv,
    search_arxiv,
)
from .semantic_scholar_backend import (
    fetch_paper_by_id as fetch_paper_by_s2_id,
    fetch_papers_by_arxiv_ids,
    fetch_recent_papers as fetch_recent_papers_s2,
    search_semantic_scholar,
)

# Gmail and parser modules available via submodule import:
# from paper_discovery.gmail_client import get_gmail_service, ...
# from paper_discovery.paper_parser_from_emails import parse_scholar_papers


def normalize_title(title: str) -> str:
    """Normalize title for comparison (lowercase, remove non-alphanumeric)."""
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def deduplicate_papers(
    arxiv_papers: list[dict],
    s2_papers: list[dict],
) -> list[dict]:
    """
    Deduplicate papers from multiple sources.

    Strategy:
    1. Match by arXiv ID (exact match)
    2. Match by normalized title (fuzzy)
    3. Prefer arXiv version (has direct PDF link)

    Args:
        arxiv_papers: Papers from arXiv API
        s2_papers: Papers from Semantic Scholar API

    Returns:
        Deduplicated list of papers (arXiv papers preferred)
    """
    seen_arxiv_ids = set()
    seen_titles = set()
    result = []

    # Add all arXiv papers first (preferred source)
    for paper in arxiv_papers:
        arxiv_id = paper.get("arxiv_id")
        title_norm = normalize_title(paper.get("title", ""))

        if arxiv_id:
            seen_arxiv_ids.add(arxiv_id)
        if title_norm:
            seen_titles.add(title_norm)
        result.append(paper)

    # Add S2 papers not already present
    for paper in s2_papers:
        arxiv_id = paper.get("arxiv_id")
        title_norm = normalize_title(paper.get("title", ""))

        # Skip if already have by arXiv ID
        if arxiv_id and arxiv_id in seen_arxiv_ids:
            continue

        # Skip if already have by title
        if title_norm and title_norm in seen_titles:
            continue

        if title_norm:
            seen_titles.add(title_norm)
        result.append(paper)

    return result


__all__ = [
    # arXiv backend
    "search_arxiv",
    "fetch_recent_papers_arxiv",
    "fetch_paper_by_arxiv_id",
    # Semantic Scholar backend
    "search_semantic_scholar",
    "fetch_recent_papers_s2",
    "fetch_paper_by_s2_id",
    "fetch_papers_by_arxiv_ids",
    # Utility functions
    "normalize_title",
    "deduplicate_papers",
]
