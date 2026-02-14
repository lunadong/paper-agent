#!/usr/bin/python3
"""
Daily Paper Update Script

Invokes paper_collector.py to fetch papers from Google Scholar alerts,
save to database, rebuild FAISS index, and tag topics.
Optionally sends an email notification.

Usage:
    python3 daily_update.py              # Run full daily update
    python3 daily_update.py --days 7     # Fetch past 7 days instead of 1
    python3 daily_update.py --dry-run    # Show what would be done without saving
    python3 daily_update.py --no-email   # Skip sending notification email
    python3 daily_update.py --check      # Only run if not already run today

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.
    You can also override settings via command line:
        python3 daily_update.py --notification-email your@email.com

For automated daily runs, use the shell script with cron:
    crontab -e
    0 17 * * * /path/to/paper_agent/paper_collection/run_update.sh >> /tmp/paper-update.log 2>&1
"""

import argparse
import io
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta

# Add script directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_PARSE_DIR = os.path.join(SCRIPT_DIR, "paper_parse")
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, PAPER_PARSE_DIR)

# File to track last successful run
LAST_RUN_FILE = os.path.join(SCRIPT_DIR, ".last_update_run")

from config import add_config_args, init_config
from gmail_client import get_gmail_service, send_email


def log(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_main(days=1, dry_run=False):
    """
    Run main.py to fetch papers, build index, and tag topics.

    Returns:
        Tuple of (output_log, new_count, skipped_count)
    """
    # Import main module
    from paper_collector import main as main_func

    # Calculate date for --after argument
    after_date = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")

    # Build arguments for main.py
    sys.argv = [
        "main.py",
        "-n",
        "100",  # Fetch up to 100 emails
        "--after",
        after_date,
    ]

    if not dry_run:
        sys.argv.append("--save-db")

    # Capture output
    output = io.StringIO()

    try:
        with redirect_stdout(output):
            main_func()
    except SystemExit:
        pass  # Ignore sys.exit calls

    output_log = output.getvalue()

    # Parse results from output
    new_count = 0
    skipped_count = 0

    # Look for "Total saved to database: X"
    match = re.search(r"Total saved to database: (\d+)", output_log)
    if match:
        new_count = int(match.group(1))

    # Look for "Total duplicates skipped: X"
    match = re.search(r"Total duplicates skipped: (\d+)", output_log)
    if match:
        skipped_count = int(match.group(1))

    return output_log, new_count, skipped_count


def send_notification_email(service, new_count, skipped_count, log_output, config):
    """Send email notification with update summary."""
    subject = f"[Paper Update] {new_count} new papers added"

    notification_email = config.notification_email
    website_url = config.website_url

    body = f"""Daily Paper Update Summary
========================

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Results:
- New papers added: {new_count}
- Duplicates skipped: {skipped_count}

View papers at: {website_url}

--- Execution Log ---
{log_output}

---
This is an automated message from daily_update.py
"""

    result = send_email(service, notification_email, subject, body)
    if result:
        log(f"Notification email sent to {notification_email}")
    else:
        log("Failed to send notification email")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Daily paper update script")
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to look back (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without saving",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending notification email",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only run if not already run today (for wake-from-sleep catch-up)",
    )

    # Add common config arguments
    add_config_args(parser)

    return parser.parse_args()


def get_last_run_date():
    """Get the date of the last successful run."""
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, "r") as f:
                date_str = f.read().strip()
                return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, IOError):
            pass
    return None


def save_last_run_date():
    """Save today's date as the last run date."""
    with open(LAST_RUN_FILE, "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d"))


def should_run_today():
    """Check if we should run today (haven't run yet today)."""
    last_run = get_last_run_date()
    today = datetime.now().date()
    return last_run != today


def main():
    """Main function for daily update."""
    args = parse_args()

    # Initialize config (loads from config.yaml if available)
    config = init_config(args)

    # Change to script directory for proper path resolution
    os.chdir(SCRIPT_DIR)

    # Check if we should skip (already ran today)
    if args.check:
        if not should_run_today():
            log("Already ran today - skipping (use without --check to force)")
            return
        log("Haven't run today - proceeding with update")

    log("=" * 50)
    log("Starting daily paper update")
    log("=" * 50)

    # Run paper_collector.py to fetch papers, build index, and tag topics
    log(f"Fetching papers from the past {args.days} day(s)...")
    output_log, new_count, skipped_count = run_main(
        days=args.days, dry_run=args.dry_run
    )

    # Print the captured output
    print(output_log)

    if args.dry_run:
        log("Dry run complete - no changes made")
        return

    log(f"Results: {new_count} new papers, {skipped_count} duplicates skipped")

    # Send notification email
    if not args.no_email and config.notification_email:
        log("Sending notification email...")
        service = get_gmail_service()
        send_notification_email(service, new_count, skipped_count, output_log, config)
    elif not config.notification_email:
        log("Skipping notification email (no email configured in config.yaml)")
    else:
        log("Skipping notification email (--no-email)")

    # Save last run date (only if not dry-run)
    save_last_run_date()

    log("=" * 50)
    log("Daily update complete!")
    log("=" * 50)


if __name__ == "__main__":
    main()
