#!/bin/bash
# run_update.sh - Collect papers from Gmail and save to database
#
# Usage:
#   ./run_update.sh              # Run paper collection
#   ./run_update.sh --days 7     # Collect past 7 days
#   ./run_update.sh --dry-run    # Preview without saving
#
# Cron setup (runs daily at 5pm):
#   crontab -e
#   0 17 * * * /path/to/paper_agent/paper_collection/run_update.sh >> /tmp/paper-update.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find Python - try common locations
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif [ -f "/Library/Developer/CommandLineTools/usr/bin/python3" ]; then
    PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
elif [ -f "/usr/bin/python3" ]; then
    PYTHON="/usr/bin/python3"
else
    echo "Error: python3 not found"
    exit 1
fi

echo "========================================"
echo "Paper Update - $(date)"
echo "========================================"

cd "$SCRIPT_DIR"
$PYTHON daily_update.py --no-email "$@"

echo ""
echo "========================================"
echo "Update complete!"
echo "========================================"
