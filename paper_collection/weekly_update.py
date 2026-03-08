#!/usr/bin/env python3
"""
Weekly Update Script - Fetch latest papers from arXiv and Semantic Scholar.

This script fetches papers from the past week using:
1. arXiv API (primary source) - AI/ML/NLP preprints
2. Semantic Scholar API (for coverage) - Published papers

Papers are deduplicated by arXiv ID and title, then added to the database.

Usage:
    python weekly_update.py                    # Default: last 7 days
    python weekly_update.py --days 14          # Last 14 days
    python weekly_update.py --dry-run          # Preview without saving
    python weekly_update.py --skip-embeddings  # Skip embedding generation
    python weekly_update.py --arxiv-only       # Only fetch from arXiv
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.paper_db import PaperDB
from paper_discovery import deduplicate_papers, search_arxiv, search_semantic_scholar

# Default configuration
DEFAULT_DAYS = 7
DEFAULT_MAX_RESULTS_ARXIV = 500
DEFAULT_MAX_RESULTS_S2 = 300

# Categories to monitor
ARXIV_CATEGORIES = ["cs.CL", "cs.LG", "cs.AI", "cs.IR"]
S2_FIELDS_OF_STUDY = ["Computer Science"]


def fetch_arxiv_papers(
    days: int = DEFAULT_DAYS,
    max_results: int = DEFAULT_MAX_RESULTS_ARXIV,
) -> list[dict]:
    """
    Fetch recent papers from arXiv.

    Args:
        days: Number of days to look back
        max_results: Maximum number of results

    Returns:
        List of paper dicts
    """
    print("=" * 70)
    print("FETCHING FROM ARXIV")
    print("=" * 70)
    print(f"Categories: {', '.join(ARXIV_CATEGORIES)}")
    print(f"Days: {days}")
    print(f"Max results: {max_results}")
    print()

    papers = search_arxiv(
        query=None,
        categories=ARXIV_CATEGORIES,
        days=days,
        max_results=max_results,
        sort_by="submittedDate",
        sort_order="descending",
    )

    print(f"\nFetched {len(papers)} papers from arXiv")
    return papers


def fetch_s2_papers(
    days: int = DEFAULT_DAYS,
    max_results: int = DEFAULT_MAX_RESULTS_S2,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Fetch recent papers from Semantic Scholar.

    Args:
        days: Number of days to look back
        max_results: Maximum number of results
        api_key: Optional API key

    Returns:
        List of paper dicts
    """
    print()
    print("=" * 70)
    print("FETCHING FROM SEMANTIC SCHOLAR")
    print("=" * 70)
    print(f"Fields of study: {', '.join(S2_FIELDS_OF_STUDY)}")
    print(f"Days: {days}")
    print(f"Max results: {max_results}")
    print()

    # Search for recent AI/ML papers using common terms
    # S2 doesn't have a "get recent" endpoint, so we use broad search
    search_terms = [
        "large language model",
        "neural network",
        "deep learning",
        "transformer",
        "machine learning",
    ]

    all_papers = []
    seen_ids = set()

    for term in search_terms:
        if len(all_papers) >= max_results:
            break

        remaining = max_results - len(all_papers)
        papers = search_semantic_scholar(
            query=term,
            fields_of_study=S2_FIELDS_OF_STUDY,
            days=days,
            max_results=min(remaining, 100),
            api_key=api_key,
        )

        # Deduplicate within S2 results
        for paper in papers:
            paper_id = paper.get("s2_paper_id")
            if paper_id and paper_id not in seen_ids:
                seen_ids.add(paper_id)
                all_papers.append(paper)

    print(f"\nFetched {len(all_papers)} papers from Semantic Scholar")
    return all_papers


def add_papers_to_db(
    papers: list[dict],
    db: PaperDB,
    dry_run: bool = False,
) -> dict:
    """
    Add papers to the database.

    Args:
        papers: List of paper dicts
        db: PaperDB instance
        dry_run: If True, don't actually save to database

    Returns:
        Dict with stats: added, skipped, errors
    """
    stats = {
        "added": 0,
        "skipped": 0,
        "errors": 0,
    }

    for paper in papers:
        try:
            title = paper.get("title", "")
            if not title:
                stats["errors"] += 1
                continue

            if dry_run:
                # In dry run, just count (can't easily check for duplicates)
                stats["added"] += 1
                if stats["added"] <= 5:  # Show first 5
                    print(f"  [DRY RUN] Would add: {title[:60]}...")
                elif stats["added"] == 6:
                    print("  ... and more papers")
            else:
                # Use add_paper method with individual arguments
                result = db.add_paper(
                    title=title,
                    authors=paper.get("authors"),
                    venue=paper.get("venue"),
                    year=paper.get("year"),
                    abstract=paper.get("abstract"),
                    link=paper.get("link"),
                    recomm_date=paper.get("recomm_date"),
                    generate_embedding=False,  # We'll batch generate later
                )
                if result:
                    stats["added"] += 1
                else:
                    stats["skipped"] += 1

        except Exception as e:
            print(f"  Error adding paper '{paper.get('title', '')[:50]}': {e}")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fetch latest papers from arXiv and Semantic Scholar"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Number of days to look back (default: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving to database",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation after adding papers",
    )
    parser.add_argument(
        "--arxiv-only",
        action="store_true",
        help="Only fetch from arXiv (faster, no S2 rate limiting)",
    )
    parser.add_argument(
        "--s2-api-key",
        type=str,
        help="Semantic Scholar API key (optional, for higher rate limits)",
    )
    parser.add_argument(
        "--max-arxiv",
        type=int,
        default=DEFAULT_MAX_RESULTS_ARXIV,
        help=f"Max papers to fetch from arXiv (default: {DEFAULT_MAX_RESULTS_ARXIV})",
    )
    parser.add_argument(
        "--max-s2",
        type=int,
        default=DEFAULT_MAX_RESULTS_S2,
        help=f"Max papers to fetch from S2 (default: {DEFAULT_MAX_RESULTS_S2})",
    )
    args = parser.parse_args()

    # Print header
    print()
    print("=" * 70)
    print("WEEKLY PAPER UPDATE")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Days to look back: {args.days}")
    print(f"Dry run: {args.dry_run}")
    print(f"arXiv only: {args.arxiv_only}")
    print()

    # Fetch papers from arXiv (primary source)
    arxiv_papers = fetch_arxiv_papers(
        days=args.days,
        max_results=args.max_arxiv,
    )

    # Fetch papers from Semantic Scholar (for coverage)
    s2_papers = []
    if not args.arxiv_only:
        s2_papers = fetch_s2_papers(
            days=args.days,
            max_results=args.max_s2,
            api_key=args.s2_api_key,
        )

    # Deduplicate papers (prefer arXiv version)
    print()
    print("=" * 70)
    print("DEDUPLICATING PAPERS")
    print("=" * 70)
    print(f"arXiv papers: {len(arxiv_papers)}")
    print(f"S2 papers: {len(s2_papers)}")

    all_papers = deduplicate_papers(arxiv_papers, s2_papers)
    print(f"After deduplication: {len(all_papers)} unique papers")

    if not all_papers:
        print("\nNo papers found. Exiting.")
        return

    # Add papers to database
    print()
    print("=" * 70)
    print("ADDING PAPERS TO DATABASE")
    print("=" * 70)

    db = PaperDB()

    try:
        stats = add_papers_to_db(all_papers, db, dry_run=args.dry_run)

        print()
        print(f"Papers added: {stats['added']}")
        print(f"Papers skipped (duplicates): {stats['skipped']}")
        print(f"Errors: {stats['errors']}")

        # Generate embeddings for new papers
        if not args.dry_run and not args.skip_embeddings and stats["added"] > 0:
            print()
            print("=" * 70)
            print("GENERATING EMBEDDINGS")
            print("=" * 70)
            try:
                result = db.update_all_embeddings()
                print(f"Generated {result.get('updated', 0)} embeddings")
            except Exception as e:
                print(f"Warning: Embedding generation failed: {e}")
                print(
                    "You can run embeddings later with: python tmp/generate_embeddings.py"
                )

    finally:
        db.close()

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Date range: last {args.days} days")
    print(f"arXiv papers fetched: {len(arxiv_papers)}")
    print(f"S2 papers fetched: {len(s2_papers)}")
    print(f"Unique papers: {len(all_papers)}")
    print(f"New papers added: {stats['added']}")
    print(f"Duplicates skipped: {stats['skipped']}")

    if args.dry_run:
        print("\n[DRY RUN - No changes saved]")


if __name__ == "__main__":
    main()
