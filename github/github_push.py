#!/usr/bin/env python3
"""
GitHub Push Script

Pushes updated paper data files to GitHub for deployment.
This script is designed to be run after daily_update.py has collected new papers.

Usage:
    python3 github_push.py              # Push if there are changes
    python3 github_push.py --force      # Force push even if no changes detected
    python3 github_push.py --dry-run    # Show what would be done without pushing
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime

# Project root directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)


def log(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def push_to_github(dry_run=False, force=False):
    """
    Push updated data files to GitHub.

    Args:
        dry_run: If True, show what would be done without actually pushing
        force: If True, push even if no changes detected

    Returns:
        True if successful, False otherwise
    """
    log("Checking for changes to push to GitHub...")

    try:
        # Change to repo root directory
        os.chdir(REPO_ROOT)
        log(f"Working directory: {REPO_ROOT}")

        # Check current git status
        result = subprocess.run(
            ["git", "status", "--porcelain", "web_interface/data/"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log(f"Git status failed: {result.stderr}")
            return False

        has_changes = bool(result.stdout.strip())

        if has_changes:
            log(f"Found changes:\n{result.stdout}")
        else:
            log("No changes in web_interface/data/")

            if not force:
                log("Nothing to push. Use --force to push anyway.")
                return True

        if dry_run:
            log("[DRY RUN] Would add web_interface/data/")
            log("[DRY RUN] Would commit with timestamp")
            log("[DRY RUN] Would push to origin")
            return True

        # Add data files
        log("Adding data files...")
        result = subprocess.run(
            ["git", "add", "web_interface/data/"], capture_output=True, text=True
        )
        if result.returncode != 0:
            log(f"Git add failed: {result.stderr}")
            return False

        # Check if there are staged changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], capture_output=True
        )

        if result.returncode == 0 and not force:
            log("No staged changes to commit")
            return True

        # Commit with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = f"Daily update: {timestamp}"

        log(f"Committing: {commit_msg}")
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg], capture_output=True, text=True
        )
        if result.returncode != 0:
            # Check if it's just "nothing to commit"
            if (
                "nothing to commit" in result.stdout
                or "nothing to commit" in result.stderr
            ):
                log("Nothing to commit")
                return True
            log(f"Git commit failed: {result.stderr}")
            return False

        # Push to origin
        log("Pushing to origin...")
        result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if result.returncode != 0:
            log(f"Git push failed: {result.stderr}")
            return False

        log("Successfully pushed to GitHub!")
        return True

    except Exception as e:
        log(f"Error pushing to GitHub: {e}")
        return False


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Push paper data updates to GitHub")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually pushing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force push even if no changes detected",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    log("=" * 50)
    log("GitHub Push Script")
    log("=" * 50)

    success = push_to_github(dry_run=args.dry_run, force=args.force)

    log("=" * 50)
    if success:
        log("Done!")
    else:
        log("Failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
