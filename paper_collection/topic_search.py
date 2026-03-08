#!/usr/bin/env python3
"""
Topic Search Script - Search and batch ingest papers by topic.

This script searches for papers on a specific topic using:
1. arXiv API (primary source) - AI/ML/NLP preprints
2. Semantic Scholar API (for coverage) - Published papers

Papers are deduplicated by arXiv ID and title, then added to the database.

Usage:
    python topic_search.py "RAG retrieval augmented generation"
    python topic_search.py "LLM agents" --year 2023 --max 500
    python topic_search.py "multimodal LLM" --dry-run
    python topic_search.py "transformer architecture" --arxiv-only
    python topic_search.py --resume  # Resume interrupted search
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.paper_db import PaperDB
from paper_discovery import deduplicate_papers, search_arxiv, search_semantic_scholar

# Default configuration
DEFAULT_MAX_RESULTS = 500
PROGRESS_FILE = Path(__file__).parent.parent / "tmp" / "topic_search_progress.json"

# Categories to search
ARXIV_CATEGORIES = ["cs.CL", "cs.LG", "cs.AI", "cs.IR"]
S2_FIELDS_OF_STUDY = ["Computer Science"]


def save_progress(progress: dict) -> None:
    """Save search progress to file."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def load_progress() -> Optional[dict]:
    """Load search progress from file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return None


def clear_progress() -> None:
    """Clear saved progress."""
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


def search_arxiv_papers(
    query: str,
    year_start: Optional[int] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict]:
    """
    Search for papers on arXiv by topic.

    Args:
        query: Search query
        year_start: Only return papers from this year onwards
        max_results: Maximum number of results

    Returns:
        List of paper dicts
    """
    print("=" * 70)
    print("SEARCHING ARXIV")
    print("=" * 70)
    print(f"Query: {query}")
    print(f"Categories: {', '.join(ARXIV_CATEGORIES)}")
    print(f"Year filter: {year_start or 'None'}")
    print(f"Max results: {max_results}")
    print()

    papers = search_arxiv(
        query=query,
        categories=ARXIV_CATEGORIES,
        year_start=year_start,
        max_results=max_results,
        sort_by="relevance",
        sort_order="descending",
    )

    print(f"\nFound {len(papers)} papers from arXiv")
    return papers


def search_s2_papers(
    query: str,
    year_start: Optional[int] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Search for papers on Semantic Scholar by topic.

    Args:
        query: Search query
        year_start: Only return papers from this year onwards
        max_results: Maximum number of results
        api_key: Optional API key

    Returns:
        List of paper dicts
    """
    print()
    print("=" * 70)
    print("SEARCHING SEMANTIC SCHOLAR")
    print("=" * 70)
    print(f"Query: {query}")
    print(f"Fields of study: {', '.join(S2_FIELDS_OF_STUDY)}")
    print(f"Year filter: {year_start or 'None'}")
    print(f"Max results: {max_results}")
    print()

    papers = search_semantic_scholar(
        query=query,
        fields_of_study=S2_FIELDS_OF_STUDY,
        year_start=year_start,
        max_results=max_results,
        api_key=api_key,
    )

    print(f"\nFound {len(papers)} papers from Semantic Scholar")
    return papers


def add_papers_to_db(
    papers: list[dict],
    db: PaperDB,
    dry_run: bool = False,
    topic_tag: Optional[str] = None,
) -> dict:
    """
    Add papers to the database.

    Args:
        papers: List of paper dicts
        db: PaperDB instance
        dry_run: If True, don't actually save to database
        topic_tag: Optional topic tag to add to papers

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
                stats["added"] += 1
                if stats["added"] <= 10:  # Show first 10
                    arxiv_id = paper.get("arxiv_id", "")
                    year = paper.get("year", "?")
                    print(f"  [{arxiv_id or 'S2'}] ({year}) {title[:55]}...")
                elif stats["added"] == 11:
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
                    generate_embedding=False,  # Batch generate later
                )
                if result:
                    stats["added"] += 1
                    if stats["added"] % 50 == 0:
                        print(f"  Added {stats['added']} papers...")
                else:
                    stats["skipped"] += 1

        except Exception as e:
            print(f"  Error adding paper '{paper.get('title', '')[:40]}': {e}")
            stats["errors"] += 1

    return stats


def _handle_resume_or_new_search(args, parser):
    """Handle resume logic or validate new search. Returns (query, year_start)."""
    if args.resume:
        progress = load_progress()
        if not progress:
            print("No saved progress found. Start a new search instead.")
            return None, None

        print("Resuming previous search...")
        return progress.get("query"), progress.get("year_start")

    if not args.query:
        parser.error("Query is required (unless using --resume)")
        return None, None

    return args.query, args.year


def _search_papers(args, query, year_start):
    """Search for papers from configured sources. Returns (arxiv_papers, s2_papers)."""
    arxiv_papers = []
    s2_papers = []

    if not args.s2_only:
        arxiv_papers = search_arxiv_papers(
            query=query,
            year_start=year_start,
            max_results=args.max,
        )

    if not args.arxiv_only:
        s2_papers = search_s2_papers(
            query=query,
            year_start=year_start,
            max_results=args.max,
            api_key=args.s2_api_key,
        )

    return arxiv_papers, s2_papers


def _generate_embeddings_if_needed(args, db, stats):
    """Generate embeddings for new papers if configured."""
    if args.dry_run or args.skip_embeddings or stats["added"] == 0:
        return

    print()
    print("=" * 70)
    print("GENERATING EMBEDDINGS")
    print("=" * 70)
    try:
        result = db.update_all_embeddings()
        print(f"Generated {result.get('updated', 0)} embeddings")
    except Exception as e:
        print(f"Warning: Embedding generation failed: {e}")
        print("You can run embeddings later with: python tmp/generate_embeddings.py")


def _get_sources_description(args):
    """Get human-readable description of search sources."""
    if args.arxiv_only:
        return "arXiv only"
    if args.s2_only:
        return "S2 only"
    return "arXiv + Semantic Scholar"


def main():
    parser = argparse.ArgumentParser(
        description="Search and batch ingest papers by topic"
    )
    parser.add_argument(
        "query",
        nargs="?",
        type=str,
        help="Search query (e.g., 'RAG retrieval augmented generation')",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Only include papers from this year onwards",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=f"Maximum papers to fetch per source (default: {DEFAULT_MAX_RESULTS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving to database",
    )
    parser.add_argument(
        "--arxiv-only",
        action="store_true",
        help="Only search arXiv (faster, no S2 rate limiting)",
    )
    parser.add_argument(
        "--s2-only",
        action="store_true",
        help="Only search Semantic Scholar",
    )
    parser.add_argument(
        "--s2-api-key",
        type=str,
        help="Semantic Scholar API key (optional)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation after adding papers",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously interrupted search",
    )
    parser.add_argument(
        "--topic-tag",
        type=str,
        help="Tag to add to papers (e.g., 'RAG')",
    )
    args = parser.parse_args()

    # Handle resume or validate new search
    query, year_start = _handle_resume_or_new_search(args, parser)
    if query is None:
        return

    # Print header
    print()
    print("=" * 70)
    print("TOPIC-BASED PAPER SEARCH")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Query: {query}")
    print(f"Year filter: {year_start or 'All years'}")
    print(f"Max results per source: {args.max}")
    print(f"Dry run: {args.dry_run}")
    print(f"Sources: {_get_sources_description(args)}")
    print()

    # Save progress
    progress = {
        "query": query,
        "year_start": year_start,
        "started_at": datetime.now().isoformat(),
        "status": "in_progress",
    }
    save_progress(progress)

    # Search papers
    arxiv_papers, s2_papers = _search_papers(args, query, year_start)

    # Deduplicate papers
    print()
    print("=" * 70)
    print("DEDUPLICATING PAPERS")
    print("=" * 70)
    print(f"arXiv papers: {len(arxiv_papers)}")
    print(f"S2 papers: {len(s2_papers)}")

    all_papers = deduplicate_papers(arxiv_papers, s2_papers)
    print(f"After deduplication: {len(all_papers)} unique papers")

    if not all_papers:
        print("\nNo papers found. Try a different query.")
        clear_progress()
        return

    # Show sample papers
    print()
    print("Sample papers found:")
    for paper in all_papers[:5]:
        arxiv_id = paper.get("arxiv_id", "")
        year = paper.get("year", "?")
        title = paper.get("title", "")[:60]
        print(f"  [{arxiv_id or 'S2'}] ({year}) {title}...")

    # Add papers to database
    print()
    print("=" * 70)
    print("ADDING PAPERS TO DATABASE")
    print("=" * 70)

    db = PaperDB()

    try:
        stats = add_papers_to_db(
            all_papers,
            db,
            dry_run=args.dry_run,
            topic_tag=args.topic_tag,
        )

        print()
        print(f"Papers added: {stats['added']}")
        print(f"Papers skipped (duplicates): {stats['skipped']}")
        print(f"Errors: {stats['errors']}")

        _generate_embeddings_if_needed(args, db, stats)

    finally:
        db.close()

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Query: {query}")
    print(f"Year filter: {year_start or 'All years'}")
    print(f"arXiv papers found: {len(arxiv_papers)}")
    print(f"S2 papers found: {len(s2_papers)}")
    print(f"Unique papers: {len(all_papers)}")
    print(f"New papers added: {stats['added']}")
    print(f"Duplicates skipped: {stats['skipped']}")

    if args.dry_run:
        print("\n[DRY RUN - No changes saved]")

    # Clear progress on success
    clear_progress()
    print("\nDone! Search complete.")


if __name__ == "__main__":
    main()
