#!/bin/bash
# run_update.sh - Collect papers from Gmail and save to database
#
# Usage:
#   ./run_update.sh              # Run paper collection
#   ./run_update.sh --days 7     # Collect past 7 days
#   ./run_update.sh --dry-run    # Preview without saving
#
# Scheduling (macOS):
#   Use launchd instead of cron for proper permissions.
#   See com.paper-agent.daily-update.plist in this directory.
#
#   To install:
#     cp com.paper-agent.daily-update.plist ~/Library/LaunchAgents/
#     launchctl load ~/Library/LaunchAgents/com.paper-agent.daily-update.plist
#
#   To uninstall:
#     launchctl unload ~/Library/LaunchAgents/com.paper-agent.daily-update.plist

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Use system Python 3.9 which has required packages installed
PYTHON="/usr/bin/python3"

echo "========================================"
echo "Paper Update - $(date)"
echo "========================================"

cd "$SCRIPT_DIR"
$PYTHON daily_update.py --days 2 "$@"

echo ""
echo "========================================"
echo "Update complete!"
echo "========================================"
