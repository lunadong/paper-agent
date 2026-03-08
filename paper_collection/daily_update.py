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
import gc
import os
import sys
from concurrent.futures import (
    as_completed,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
)
from datetime import datetime, timedelta
from pathlib import Path

# Script directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_METADATA_DIR = os.path.join(SCRIPT_DIR, "paper_metadata")
PAPER_SUMMARY_DIR = os.path.join(SCRIPT_DIR, "paper_summary")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PAPER_METADATA_DIR)
sys.path.insert(0, PAPER_SUMMARY_DIR)

from core.config import add_config_args, init_config, parse_email_date
from core.paper_db import close_connection_pool, PaperDB
from paper_discovery.gmail_client import (
    get_gmail_service,
    get_message,
    get_message_headers,
    get_raw_html,
    list_messages,
)
from paper_discovery.paper_parser_from_emails import parse_scholar_papers
from summary_generation import generate_summary_for_paper

# Timeout for individual paper processing (5 minutes)
PAPER_PROCESSING_TIMEOUT = 300


def log(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


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


def _parse_emails_step(service, messages, args):
    """Step 2: Parse papers from emails and save to database."""
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
        email_papers = _deduplicate_papers(papers, seen_titles, headers)
        all_papers.extend(email_papers)

        # Save to database
        if db and email_papers:
            saved, skipped = _save_papers_to_db(db, email_papers)
            total_saved += saved
            total_skipped += skipped

        log(f"  [{idx}/{len(messages)}] {len(email_papers)} papers")

    if db:
        db.close()

    log(f"Total papers found: {len(all_papers)}")
    if not args.dry_run:
        log(f"Saved: {total_saved}, Skipped (duplicates): {total_skipped}")
    print()

    return total_saved, total_skipped


def _deduplicate_papers(papers, seen_titles, headers):
    """Deduplicate papers by title and add email date."""
    email_papers = []
    for paper in papers:
        title_lower = paper["title"].lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)
        paper["email_date"] = headers.get("date", "N/A")
        email_papers.append(paper)
    return email_papers


def _get_paper_recomm_date(paper):
    """Determine the recommendation date for a paper."""
    email_date = parse_email_date(paper.get("email_date", ""))
    if email_date:
        return email_date
    if paper.get("arxiv_date"):
        return paper["arxiv_date"]
    return ""


def _save_papers_to_db(db, papers):
    """Save papers to database. Returns (saved_count, skipped_count)."""
    saved = 0
    skipped = 0
    for paper in papers:
        paper_id = db.add_paper(
            title=paper["title"],
            authors=paper.get("authors", ""),
            venue=paper.get("venue", ""),
            year=paper.get("year", ""),
            abstract=paper.get("snippet", ""),
            link=paper.get("link", ""),
            recomm_date=_get_paper_recomm_date(paper),
        )
        if paper_id:
            saved += 1
        else:
            skipped += 1
    return saved, skipped


def _process_single_paper(paper):
    """Process a single paper for parallel execution."""
    result = generate_summary_for_paper(
        paper_id=paper["id"],
        save_db=True,
    )
    result["_paper_id"] = paper["id"]
    result["_title"] = paper.get("title", "")
    return result


def _process_paper_result(result, summary_errors):
    """Process result from paper summary generation."""
    if result["success"]:
        pid = result["_paper_id"]
        title = result["_title"][:50]
        log(f"  [OK] [{pid}] {title}...")
        return 1, 0
    else:
        pid = result["_paper_id"]
        title = result["_title"][:50]
        err = result.get("error", "Unknown")
        log(f"  [FAIL] [{pid}] {title}... Error: {err}")
        summary_errors.append(f"[{pid}] {err}")
        return 0, 1


def _generate_summaries_parallel(papers_to_process, args, summary_errors):
    """Generate summaries using parallel workers."""
    success_count = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_process_single_paper, p): p for p in papers_to_process
        }
        for future in as_completed(futures):
            try:
                result = future.result(timeout=PAPER_PROCESSING_TIMEOUT)
            except FuturesTimeoutError:
                paper = futures[future]
                failed_count += 1
                pid = paper["id"]
                title = paper.get("title", "")[:50]
                log(f"  [TIMEOUT] [{pid}] {title}...")
                summary_errors.append(
                    f"[{pid}] Timeout after {PAPER_PROCESSING_TIMEOUT}s"
                )
                continue
            except Exception as e:
                paper = futures[future]
                failed_count += 1
                pid = paper["id"]
                title = paper.get("title", "")[:50]
                log(f"  [ERROR] [{pid}] {title}... Error: {e}")
                summary_errors.append(f"[{pid}] {str(e)}")
                continue

            s, f = _process_paper_result(result, summary_errors)
            success_count += s
            failed_count += f
            gc.collect()

    return success_count, failed_count


def _generate_summaries_sequential(papers_to_process, summary_errors):
    """Generate summaries sequentially."""
    success_count = 0
    failed_count = 0

    for paper in papers_to_process:
        result = _process_single_paper(paper)
        s, f = _process_paper_result(result, summary_errors)
        success_count += s
        failed_count += f
        gc.collect()

    return success_count, failed_count


def _generate_summaries_step(args, date_cutoff):
    """Step 3: Generate summaries for papers without summaries."""
    summary_success_count = 0
    summary_failed_count = 0
    summary_errors = []
    summary_skipped_reason = None

    log(f"STEP 3: Generating summaries (workers={args.workers})...")
    db = PaperDB()
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

        if args.workers > 1:
            success, failed = _generate_summaries_parallel(
                papers_to_process, args, summary_errors
            )
        else:
            success, failed = _generate_summaries_sequential(
                papers_to_process, summary_errors
            )

        summary_success_count = success
        summary_failed_count = failed
        log(f"Generated summaries: {success} success, {failed} failed")
    else:
        log("No papers need summaries")
        summary_skipped_reason = "no papers need summaries"

    db.close()
    return (
        summary_success_count,
        summary_failed_count,
        summary_errors,
        summary_skipped_reason,
    )


def _build_notification_email(
    args,
    total_saved,
    total_skipped,
    summary_success_count,
    summary_failed_count,
    summary_errors,
    summary_skipped_reason,
    config,
):
    """Build notification email subject and body."""
    # Determine subject
    if summary_failed_count > 0 and summary_success_count == 0:
        subject = (
            f"[Paper Update] WARNING: {total_saved} papers added, "
            f"{summary_failed_count} summary failures"
        )
    elif summary_failed_count > 0:
        subject = (
            f"[Paper Update] {total_saved} papers added "
            f"({summary_failed_count} summary failures)"
        )
    elif total_saved == 0:
        subject = (
            f"[Paper Update] No new papers today ({total_skipped} duplicates skipped)"
        )
    else:
        subject = f"[Paper Update] {total_saved} new papers added"

    # Build body
    body = f"""Daily Paper Update Summary
========================

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Days: {args.days}

Paper Collection:
- New papers added: {total_saved}
- Duplicates skipped: {total_skipped}
"""

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

    if summary_errors:
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
    return subject, body


def _fetch_emails_step(args, query):
    """Step 1: Fetch emails from Gmail. Returns (service, messages) or None."""
    log("STEP 1: Fetching emails from Gmail...")

    try:
        service = get_gmail_service()
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        log("Please set up Gmail API credentials (see README)")
        return None, None

    messages = list_messages(service, max_results=args.max_emails, query=query)

    if not messages:
        log("No emails found. Nothing to do.")
        return service, None

    log(f"Found {len(messages)} email(s)")
    print()
    return service, messages


def _generate_embeddings_step(args, total_saved):
    """Step 2.5: Generate embeddings for new papers."""
    embedding_count = 0
    if args.dry_run:
        log("STEP 2.5: Skipped embedding generation (dry run)")
    elif total_saved == 0:
        log("STEP 2.5: Skipped embedding generation (no new papers)")
    else:
        log("STEP 2.5: Generating embeddings for new papers...")
        db = PaperDB()
        try:
            result = db.update_all_embeddings()
            embedding_count = result.get("updated", 0)
            log(f"Generated {embedding_count} embeddings")
        except Exception as e:
            log(f"Warning: Embedding generation failed: {e}")
        finally:
            db.close()
    print()
    return embedding_count


def _summary_generation_step(args, total_saved, date_cutoff):
    """Step 3: Generate tags and summaries for new papers."""
    if args.dry_run:
        log("STEP 3: Skipped (dry run)")
        return 0, 0, [], "dry run"
    if args.skip_topics:
        log("STEP 3: Skipped (--skip-topics)")
        return 0, 0, [], "--skip-topics flag"
    if total_saved == 0:
        log("STEP 3: Skipped (no new papers)")
        return 0, 0, [], "no new papers"

    return _generate_summaries_step(args, date_cutoff)


def _send_notification_step(
    args,
    service,
    config,
    total_saved,
    total_skipped,
    summary_success_count,
    summary_failed_count,
    summary_errors,
    summary_skipped_reason,
):
    """Send notification email if configured."""
    if args.dry_run:
        log("Skipping notification email (dry run)")
        return
    if args.no_email:
        log("Skipping notification email (--no-email flag)")
        return
    if not config.notification_email:
        log("Skipping notification email (no email configured)")
        return

    log("Sending notification email...")
    from paper_discovery.gmail_client import send_email

    subject, body = _build_notification_email(
        args,
        total_saved,
        total_skipped,
        summary_success_count,
        summary_failed_count,
        summary_errors,
        summary_skipped_reason,
        config,
    )

    if send_email(service, config.notification_email, subject, body):
        log(f"Notification sent to {config.notification_email}")
    else:
        log("Failed to send notification email")


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

    # STEP 1: Email Parsing - Fetch emails from Gmail
    service, messages = _fetch_emails_step(args, query)
    if messages is None:
        if service is None:
            return  # Error occurred
        return  # No emails found

    # STEP 2: Paper Parsing - Extract paper metadata, save to database
    total_saved, total_skipped = _parse_emails_step(service, messages, args)

    # STEP 2.5: Embedding Generation
    _generate_embeddings_step(args, total_saved)

    # STEP 3: Summary Generation
    (
        summary_success_count,
        summary_failed_count,
        summary_errors,
        summary_skipped_reason,
    ) = _summary_generation_step(args, total_saved, date_cutoff)
    print()

    # Send notification email
    _send_notification_step(
        args,
        service,
        config,
        total_saved,
        total_skipped,
        summary_success_count,
        summary_failed_count,
        summary_errors,
        summary_skipped_reason,
    )

    log("=" * 60)
    log("DAILY UPDATE COMPLETE")
    log("=" * 60)

    # Clean up connection pool to prevent memory leaks
    close_connection_pool()
    gc.collect()


if __name__ == "__main__":
    main()
