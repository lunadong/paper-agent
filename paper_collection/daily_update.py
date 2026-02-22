#!/usr/bin/python3
"""
Daily Paper Update Script

Fetches papers from Google Scholar alerts and processes them in 3 steps:
    1. Email parsing - Fetch emails from Gmail
    2. Paper parsing - Extract paper metadata from emails, save to PostgreSQL
    3. Summary generation - Generate topics and summaries for new papers

Usage:
    python3 daily_update.py              # Run full daily update (1 day back)
    python3 daily_update.py --days 7     # Fetch past 7 days
    python3 daily_update.py --dry-run    # Preview without saving
    python3 daily_update.py --no-email   # Skip notification email

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.
"""

import argparse
import os
import sys
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timedelta

# Script directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_METADATA_DIR = os.path.join(SCRIPT_DIR, "paper_metadata")
PAPER_SUMMARY_DIR = os.path.join(SCRIPT_DIR, "paper_summary")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PAPER_METADATA_DIR)
sys.path.insert(0, PAPER_SUMMARY_DIR)

from config import add_config_args, init_config
from gmail_client import (
    get_gmail_service,
    get_message,
    get_message_headers,
    get_raw_html,
    list_messages,
)
from paper_db import PaperDB
from paper_parser import parse_scholar_papers
from summary_generation import generate_summary_for_paper


def log(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def parse_email_date(date_str):
    """Parse email date to YYYY-MM-DD format."""
    import re

    if not date_str or date_str == "N/A":
        return date_str

    # Already in YYYY-MM-DD format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Try email format: "Thu, 14 Dec 2023 15:27:28 -0800"
    month_map = {
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
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str)
    if match:
        day = int(match.group(1))
        month = month_map.get(match.group(2).lower(), 1)
        year = match.group(3)
        return f"{year}-{month:02d}-{day:02d}"

    return date_str


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Daily paper update: fetch, parse, and tag papers"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to look back (default: 1)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=100,
        help="Maximum emails to fetch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving to database",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending notification email",
    )
    parser.add_argument(
        "--skip-topics",
        action="store_true",
        help="Skip topic tagging step",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for summary generation (default: 1)",
    )

    add_config_args(parser)
    return parser.parse_args()


def main():
    """Main function for daily update."""
    args = parse_args()
    config = init_config(args)

    # Calculate date range
    date_cutoff = datetime.now() - timedelta(days=args.days)
    after_date = date_cutoff.strftime("%Y/%m/%d")
    query = f"from:scholaralerts-noreply@google.com after:{after_date}"

    log("=" * 60)
    log("DAILY PAPER UPDATE")
    log("=" * 60)
    log(f"Looking back {args.days} day(s) (after {after_date})")
    if args.dry_run:
        log("DRY RUN - no changes will be saved")
    print()

    # =========================================================================
    # STEP 1: Email Parsing - Fetch emails from Gmail
    # =========================================================================
    log("STEP 1: Fetching emails from Gmail...")

    try:
        service = get_gmail_service()
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        log("Please set up Gmail API credentials (see README)")
        return

    messages = list_messages(service, max_results=args.max_emails, query=query)

    if not messages:
        log("No emails found. Nothing to do.")
        return

    log(f"Found {len(messages)} email(s)")
    print()

    # =========================================================================
    # STEP 2: Paper Parsing - Extract paper metadata, save to database
    # =========================================================================
    log("STEP 2: Parsing papers from emails...")

    db = None
    if not args.dry_run:
        db = PaperDB()
        log("Connected to PostgreSQL database")

    all_papers = []
    seen_titles = set()
    total_saved = 0
    total_skipped = 0

    for idx, msg in enumerate(messages, 1):
        full_msg = get_message(service, msg["id"])
        if not full_msg:
            continue

        headers = get_message_headers(full_msg)
        html_content = get_raw_html(full_msg)
        papers = parse_scholar_papers(html_content)

        # Deduplicate and collect papers
        email_papers = []
        for paper in papers:
            title_lower = paper["title"].lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)
            paper["email_date"] = headers.get("date", "N/A")
            email_papers.append(paper)
            all_papers.append(paper)

        # Save to database
        if db and email_papers:
            for paper in email_papers:
                paper_id = db.add_paper(
                    title=paper["title"],
                    authors=paper.get("authors", ""),
                    venue=paper.get("venue", ""),
                    year=paper.get("year", ""),
                    abstract=paper.get("snippet", ""),
                    link=paper.get("link", ""),
                    recomm_date=parse_email_date(paper.get("email_date", "")),
                )
                if paper_id:
                    total_saved += 1
                else:
                    total_skipped += 1

        log(f"  [{idx}/{len(messages)}] {len(email_papers)} papers")

    if db:
        db.close()

    log(f"Total papers found: {len(all_papers)}")
    if not args.dry_run:
        log(f"Saved: {total_saved}, Skipped (duplicates): {total_skipped}")
    print()

    # =========================================================================
    # STEP 3: Summary Generation - Generate tags and summaries for new papers
    # =========================================================================
    # Track summary generation results for email notification
    summary_success_count = 0
    summary_failed_count = 0
    summary_errors = []  # Track error messages for email
    summary_skipped_reason = None

    if args.dry_run:
        log("STEP 3: Skipped (dry run)")
        summary_skipped_reason = "dry run"
    elif args.skip_topics:
        log("STEP 3: Skipped (--skip-topics)")
        summary_skipped_reason = "--skip-topics flag"
    elif total_saved == 0:
        log("STEP 3: Skipped (no new papers)")
        summary_skipped_reason = "no new papers"
    else:
        log(f"STEP 3: Generating summaries (workers={args.workers})...")
        db = PaperDB()
        # Get papers without summaries that are within the date range
        date_cutoff_str = date_cutoff.strftime("%Y-%m-%d")
        papers = db.get_all_papers(order_by="created_at", order_dir="DESC")
        papers_to_process = [
            p
            for p in papers
            if not p.get("summary_generated_at")
            and p.get("recomm_date", "") >= date_cutoff_str
        ]

        if papers_to_process:
            log(f"Found {len(papers_to_process)} papers without summaries")

            def process_paper(paper):
                """Process a single paper for parallel execution."""
                result = generate_summary_for_paper(
                    paper_id=paper["id"],
                    save_db=True,
                )
                result["_paper_id"] = paper["id"]
                result["_title"] = paper.get("title", "")
                return result

            if args.workers > 1:
                # Parallel processing
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    futures = {
                        executor.submit(process_paper, p): p for p in papers_to_process
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        if result["success"]:
                            summary_success_count += 1
                            pid = result["_paper_id"]
                            title = result["_title"][:50]
                            log(f"  [OK] [{pid}] {title}...")
                        else:
                            summary_failed_count += 1
                            pid = result["_paper_id"]
                            title = result["_title"][:50]
                            err = result.get("error", "Unknown")
                            log(f"  [FAIL] [{pid}] {title}... Error: {err}")
                            summary_errors.append(f"[{pid}] {err}")
            else:
                # Sequential processing
                for paper in papers_to_process:
                    result = process_paper(paper)
                    if result["success"]:
                        summary_success_count += 1
                        pid = result["_paper_id"]
                        title = result["_title"][:50]
                        log(f"  [OK] [{pid}] {title}...")
                    else:
                        summary_failed_count += 1
                        pid = result["_paper_id"]
                        title = result["_title"][:50]
                        err = result.get("error", "Unknown")
                        log(f"  [FAIL] [{pid}] {title}... Error: {err}")
                        summary_errors.append(f"[{pid}] {err}")

            log(
                f"Generated summaries: {summary_success_count} success, {summary_failed_count} failed"
            )
        else:
            log("No papers need summaries")
            summary_skipped_reason = "no papers need summaries"
        db.close()

    print()

    # =========================================================================
    # Send notification email (always send, include failures if any)
    # =========================================================================
    if not args.dry_run and not args.no_email and config.notification_email:
        log("Sending notification email...")
        from gmail_client import send_email

        # Determine email subject based on success/failure status
        if summary_failed_count > 0 and summary_success_count == 0:
            subject = f"[Paper Update] ⚠️ {total_saved} papers added, {summary_failed_count} summary failures"
        elif summary_failed_count > 0:
            subject = f"[Paper Update] {total_saved} papers added ({summary_failed_count} summary failures)"
        else:
            subject = f"[Paper Update] {total_saved} new papers added"

        # Build email body
        body = f"""Daily Paper Update Summary
========================

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Days: {args.days}

Paper Collection:
- New papers added: {total_saved}
- Duplicates skipped: {total_skipped}
"""

        # Add summary generation status
        if summary_skipped_reason:
            body += f"""
Summary Generation: Skipped ({summary_skipped_reason})
"""
        else:
            body += f"""
Summary Generation:
- Successful: {summary_success_count}
- Failed: {summary_failed_count}
"""

        # Add error details if there were failures
        if summary_errors:
            # Deduplicate errors (often same error repeated)
            unique_errors = list(dict.fromkeys(summary_errors))
            body += """
Errors (showing up to 5):
"""
            for err in unique_errors[:5]:
                body += f"  - {err}\n"
            if len(unique_errors) > 5:
                body += f"  ... and {len(unique_errors) - 5} more\n"

        body += f"""
View papers at: {config.website_url}

---
This is an automated message from daily_update.py
"""
        if send_email(service, config.notification_email, subject, body):
            log(f"Notification sent to {config.notification_email}")
        else:
            log("Failed to send notification email")

    log("=" * 60)
    log("DAILY UPDATE COMPLETE")
    log("=" * 60)


if __name__ == "__main__":
    main()
