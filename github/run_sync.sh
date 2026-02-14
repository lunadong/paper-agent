#!/bin/bash
# run_sync.sh - Collect papers from Gmail and push to GitHub
#
# Usage:
#   ./run_sync.sh              # Run full sync
#   ./run_sync.sh --dry-run    # Preview without making changes
#
# Cron setup (runs daily at 5pm):
#   crontab -e
#   0 17 * * * /Users/lunadong/Code/paper_agent/github/run_sync.sh >> /tmp/paper-sync.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Use the system Python with user packages
export PYTHONPATH="/Users/lunadong/Library/Python/3.9/lib/python/site-packages:$PYTHONPATH"
PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"

echo "========================================"
echo "Paper Sync - $(date)"
echo "========================================"

# Step 1: Collect papers from Gmail (calls run_update.sh)
echo ""
echo "Step 1: Collecting papers..."

if [[ "$1" == "--dry-run" ]]; then
    "$REPO_ROOT/paper_collection/run_update.sh" --dry-run
else
    "$REPO_ROOT/paper_collection/run_update.sh"
fi

# Step 2: Push to GitHub
echo ""
echo "Step 2: Pushing to GitHub..."
cd "$SCRIPT_DIR"

if [[ "$1" == "--dry-run" ]]; then
    $PYTHON github_push.py --dry-run
else
    $PYTHON github_push.py
fi

echo ""
echo "========================================"
echo "Sync complete!"
echo "========================================"
