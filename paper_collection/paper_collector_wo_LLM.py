#!/usr/bin/python3
"""
Google Scholar Alert Reader (Without LLM)

Main script for fetching and parsing Google Scholar alert emails.
Tags topics using keyword matching (no LLM calls).

Usage:
    python paper_collector_wo_LLM.py -n 5 --after 2026/01/01      # Fetch, save, tag topics
    python paper_collector_wo_LLM.py -n 5 --after 2026/01/01 --skip-tags  # Fetch only
    python paper_collector_wo_LLM.py --help

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.
"""

import argparse
import os
import sys

# Script directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_PARSE_DIR = os.path.join(SCRIPT_DIR, "paper_metadata")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PAPER_PARSE_DIR)

from config import add_config_args, parse_email_date
from gmail_client import (
    get_gmail_service,
    get_message,
    get_message_headers,
    get_raw_html,
    list_messages,
    strip_html,
)
from paper_db import PaperDB
from paper_parser_from_emails import parse_scholar_papers

# Default query for fetching emails
DEFAULT_QUERY = "from:scholaralerts-noreply@google.com"


def parse_args():
    """Parse command-line arguments."""
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
        help="Save parsed papers to PostgreSQL database",
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


def _build_date_range_display(args) -> str:
    """Build a human-readable date range description."""
    if args.after and args.before:
        return f" from {args.after} to {args.before}"
    elif args.after:
        return f" after {args.after}"
    elif args.before:
        return f" before {args.before}"
    return ""


def _print_debug_content(args, html_content: str) -> None:
    """Print debug content if requested."""
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
        print(html_content[:5000])
        print("=" * 60 + "\n")


def _process_email_papers(papers, seen_titles, headers):
    """Filter duplicates and add email metadata to papers."""
    email_papers = []
    for paper in papers:
        title_lower = paper["title"].lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)
        paper["email_date"] = headers.get("date", "N/A")
        paper["email_subject"] = headers.get("subject", "N/A")
        email_papers.append(paper)
    return email_papers


def _save_papers_to_db(db, email_papers):
    """Save papers to database and return counts."""
    saved = 0
    skipped = 0
    for paper in email_papers:
        paper_id = db.add_paper(
            title=paper["title"],
            authors=paper.get("authors", ""),
            venue=paper.get("venue", ""),
            year=paper.get("year", ""),
            abstract=paper.get("snippet", ""),
            link=paper.get("link", ""),
            recomm_date=parse_email_date(paper.get("email_date", "")),
            tags="",
        )
        if paper_id:
            saved += 1
        else:
            skipped += 1
    return saved, skipped


def _print_paper_details(all_papers) -> None:
    """Print detailed information about all papers."""
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
        print(f"    From alert: {paper['email_subject']} ({paper['email_date']})")
        print("-" * 60)


def _tag_topics_if_needed(total_saved, args) -> None:
    """Tag topics for new papers if applicable."""
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


def _process_single_email(service, msg, args, seen_titles):
    """Process a single email and return papers."""
    full_msg = get_message(service, msg["id"])
    if not full_msg:
        return []

    headers = get_message_headers(full_msg)
    html_content = get_raw_html(full_msg)

    _print_debug_content(args, html_content)

    papers = parse_scholar_papers(html_content, debug_titles=args.debug_titles)
    return _process_email_papers(papers, seen_titles, headers)


def _log_email_progress(
    email_idx, total_emails, num_papers, db, total_saved, total_skipped
):
    """Log progress for processing an email."""
    progress = f"[{email_idx}/{total_emails}]"
    papers_info = f"{num_papers} new papers"
    if db:
        save_info = f"(total saved: {total_saved}, skipped: {total_skipped})"
        print(f"{progress} Processed email: {papers_info} {save_info}")
    else:
        print(f"{progress} Processed email: {papers_info}")


def _finalize_collection(db, total_saved, total_skipped, args):
    """Close database and tag topics if needed."""
    if not db:
        return

    db.close()
    print(f"Total saved to database: {total_saved}")
    if total_skipped > 0:
        print(f"Total duplicates skipped: {total_skipped}")
    _tag_topics_if_needed(total_saved, args)


def main():
    """Main function for fetching and displaying Google Scholar papers."""
    args = parse_args()
    query = build_query(args.query, args.after, args.before)

    print("Connecting to Gmail API...")

    try:
        service = get_gmail_service()
        print("Successfully connected!\n")

        date_range = _build_date_range_display(args)
        print("=" * 60)
        print(f"Google Scholar Alerts (up to {args.num_emails}{date_range}):")
        print("=" * 60)
        messages = list_messages(service, max_results=args.num_emails, query=query)

        if not messages:
            print("No emails found from Google Scholar Alerts.")
            return

        print(f"Found {len(messages)} email(s)\n")

        db = PaperDB() if args.save_db else None
        if db:
            print("Connected to PostgreSQL database")

        all_papers = []
        seen_titles = set()
        total_saved = 0
        total_skipped = 0

        for email_idx, msg in enumerate(messages, 1):
            email_papers = _process_single_email(service, msg, args, seen_titles)
            all_papers.extend(email_papers)

            if db and email_papers:
                saved, skipped = _save_papers_to_db(db, email_papers)
                total_saved += saved
                total_skipped += skipped

            _log_email_progress(
                email_idx,
                len(messages),
                len(email_papers),
                db,
                total_saved,
                total_skipped,
            )

        print(f"\nTotal papers found: {len(all_papers)}")
        _finalize_collection(db, total_saved, total_skipped, args)

        if args.print_papers:
            _print_paper_details(all_papers)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease follow the setup instructions in email_access.py docstring.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
