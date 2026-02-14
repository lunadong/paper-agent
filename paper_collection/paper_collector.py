#!/usr/bin/python3
"""
Google Scholar Alert Reader

Main script for fetching and parsing Google Scholar alert emails.
Also rebuilds FAISS index and tags topics to keep everything in sync.

Usage:
    python paper_collector.py -n 5 --after 2026/01/01      # Fetch, save, build index, tag topics
    python paper_collector.py -n 5 --after 2026/01/01 --skip-index --skip-tags  # Fetch only
    python paper_collector.py --help

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.
    You can also override settings via command line:
        python paper_collector.py --db-path /path/to/papers.db
"""

import argparse
import os
import re
import sys

# Script directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_PARSE_DIR = os.path.join(SCRIPT_DIR, "paper_parse")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PAPER_PARSE_DIR)

from config import add_config_args, config, init_config
from gmail_client import (
    get_gmail_service,
    get_message,
    get_message_headers,
    get_raw_html,
    list_messages,
    strip_html,
)
from paper_db import PaperDB
from paper_parser import parse_scholar_papers

# Default query for fetching emails
DEFAULT_QUERY = "from:scholaralerts-noreply@google.com"

# Month name to number mapping
MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_email_date(date_str):
    """
    Parse various date formats to YYYY-MM-DD (sortable format).

    Handles:
    - "Thu, 14 Dec 2023 15:27:28 -0800" → "2023-12-14"
    - "2/3/2026" or "12/14/2023" (M/D/YYYY) → "2026-02-03"
    - Already "2023-12-14" → unchanged
    """
    if not date_str or date_str == "N/A":
        return date_str

    # Already in YYYY-MM-DD format?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Try M/D/YYYY format (e.g., "2/3/2026" or "12/14/2023")
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = match.group(3)
        return f"{year}-{month:02d}-{day:02d}"

    # Try email format: "Thu, 14 Dec 2023 15:27:28 -0800"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = match.group(3)

        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month:02d}-{day:02d}"

    # Return original if can't parse
    return date_str


def parse_args():
    """Parse command-line arguments."""
    # Get default paths from config
    cfg = config()
    default_db_path = cfg.get_db_path()

    parser = argparse.ArgumentParser(
        description="Fetch emails from Gmail (Google Scholar Alerts by default)."
    )
    parser.add_argument(
        "-n",
        "--num-emails",
        type=int,
        default=20,
        help="Number of emails to fetch (default: 20)",
    )
    parser.add_argument(
        "--after", type=str, help="Fetch emails after this date (format: YYYY/MM/DD)"
    )
    parser.add_argument(
        "--before", type=str, help="Fetch emails before this date (format: YYYY/MM/DD)"
    )
    parser.add_argument(
        "-q",
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help=f"Gmail search query (default: {DEFAULT_QUERY})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw text content for debugging",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Print raw HTML content for debugging",
    )
    parser.add_argument(
        "--debug-titles",
        action="store_true",
        help="Print all detected paper titles for debugging",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_papers",
        help="Print all parsed papers to console",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save parsed papers to the SQLite database",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=default_db_path,
        help=f"Path to SQLite database file (default: {default_db_path})",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip rebuilding FAISS index after saving papers",
    )
    parser.add_argument(
        "--skip-tags",
        action="store_true",
        help="Skip topic tagging after saving papers",
    )

    # Add common config arguments
    add_config_args(parser)

    return parser.parse_args()


def build_query(base_query, after=None, before=None):
    """Build Gmail query string with optional date filters."""
    query_parts = [base_query] if base_query else []

    if after:
        query_parts.append(f"after:{after}")
    if before:
        query_parts.append(f"before:{before}")

    return " ".join(query_parts)


def main():
    """Main function for fetching and displaying Google Scholar papers."""
    args = parse_args()

    # Build query with date filters if provided
    query = build_query(args.query, args.after, args.before)

    print("Connecting to Gmail API...")

    try:
        service = get_gmail_service()
        print("Successfully connected!\n")

        # Build description for output
        date_range = ""
        if args.after or args.before:
            if args.after and args.before:
                date_range = f" from {args.after} to {args.before}"
            elif args.after:
                date_range = f" after {args.after}"
            else:
                date_range = f" before {args.before}"

        print("=" * 60)
        print(f"Google Scholar Alerts (up to {args.num_emails}{date_range}):")
        print("=" * 60)
        messages = list_messages(service, max_results=args.num_emails, query=query)

        if not messages:
            print("No emails found from Google Scholar Alerts.")
        else:
            print(f"Found {len(messages)} email(s)\n")

            # Initialize database connection for incremental saving
            db = None
            if args.save_db:
                db = PaperDB(args.db_path)
                print(f"Database: {args.db_path}")

            all_papers = []
            seen_titles = set()  # Track seen titles across all emails for deduplication
            total_saved = 0
            total_skipped = 0
            total_emails = len(messages)

            for email_idx, msg in enumerate(messages, 1):
                full_msg = get_message(service, msg["id"])
                if full_msg:
                    headers = get_message_headers(full_msg)
                    html_content = get_raw_html(full_msg)

                    if args.debug:
                        print("\n" + "=" * 60)
                        print("DEBUG: Raw text after HTML stripping:")
                        print("=" * 60)
                        text = strip_html(html_content)
                        print(text)
                        print("=" * 60 + "\n")

                    if args.debug_html:
                        print("\n" + "=" * 60)
                        print("DEBUG: Raw HTML content:")
                        print("=" * 60)
                        print(html_content[:5000])  # First 5000 chars
                        print("=" * 60 + "\n")

                    papers = parse_scholar_papers(
                        html_content, debug_titles=args.debug_titles
                    )

                    email_papers = []
                    for paper in papers:
                        # Deduplicate across all emails using lowercase title
                        title_lower = paper["title"].lower()
                        if title_lower in seen_titles:
                            continue
                        seen_titles.add(title_lower)

                        paper["email_date"] = headers.get("date", "N/A")
                        paper["email_subject"] = headers.get("subject", "N/A")
                        email_papers.append(paper)
                        all_papers.append(paper)

                    # Incremental save: save papers from this email immediately
                    if db and email_papers:
                        for paper in email_papers:
                            paper_id = db.add_paper(
                                title=paper["title"],
                                authors=paper.get("authors", ""),
                                venue=paper.get("venue", ""),
                                year=paper.get("year", ""),
                                abstract=paper.get("snippet", ""),
                                link=paper.get("link", ""),
                                recomm_date=parse_email_date(
                                    paper.get("email_date", "")
                                ),
                                tags="",
                            )
                            if paper_id:
                                total_saved += 1
                            else:
                                total_skipped += 1

                    # Progress tracking
                    progress = f"[{email_idx}/{total_emails}]"
                    papers_info = f"{len(email_papers)} new papers"
                    if db:
                        save_info = (
                            f"(total saved: {total_saved}, skipped: {total_skipped})"
                        )
                        print(f"{progress} Processed email: {papers_info} {save_info}")
                    else:
                        print(f"{progress} Processed email: {papers_info}")

            print(f"\nTotal papers found: {len(all_papers)}")

            # Close database connection
            if db:
                db.close()
                print(f"Total saved to database: {total_saved}")
                if total_skipped > 0:
                    print(f"Total duplicates skipped: {total_skipped}")

                # Build FAISS index (unless skipped)
                if total_saved > 0 and not args.skip_index:
                    print("\n" + "=" * 60)
                    print("Rebuilding FAISS index...")
                    print("=" * 60)
                    from index_builder import build_index

                    build_index()
                elif args.skip_index:
                    print("\nSkipping FAISS index rebuild (--skip-index)")
                else:
                    print("\nNo new papers - skipping index rebuild")

                # Tag topics (unless skipped)
                if total_saved > 0 and not args.skip_tags:
                    print("\n" + "=" * 60)
                    print("Tagging papers with topics...")
                    print("=" * 60)
                    from topic_tagger import tag_new_papers

                    tag_new_papers()
                elif args.skip_tags:
                    print("\nSkipping topic tagging (--skip-tags)")
                else:
                    print("\nNo new papers - skipping topic tagging")

            # Print papers if requested
            if args.print_papers:
                print("\n" + "=" * 60)
                for i, paper in enumerate(all_papers, 1):
                    print(f"\n[{i}] {paper['title']}")
                    if paper["authors"]:
                        print(f"    Authors: {paper['authors']}")
                    if paper["venue"]:
                        print(f"    Venue: {paper['venue']}")
                    if paper["year"]:
                        print(f"    Year: {paper['year']}")
                    if paper["snippet"]:
                        print(f"    Abstract: {paper['snippet']}")
                    if paper["link"]:
                        print(f"    Link: {paper['link']}")
                    print(
                        f"    From alert: {paper['email_subject']} ({paper['email_date']})"
                    )
                    print("-" * 60)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease follow the setup instructions in email_access.py docstring.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
