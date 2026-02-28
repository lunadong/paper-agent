#!/bin/bash
# monitor_memory.sh - Run daily_update.py while monitoring memory usage
#
# This script:
# 1. Runs daily_update.py in the background
# 2. Monitors its memory usage every 5 seconds
# 3. Logs memory stats to a file
# 4. Reports peak memory usage at the end
#
# Usage:
#   ./monitor_memory.sh              # Run with defaults
#   ./monitor_memory.sh --days 7     # Pass args to daily_update.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../tmp"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MEMORY_LOG="${LOG_DIR}/memory_${TIMESTAMP}.log"
PROCESS_LOG="${LOG_DIR}/process_${TIMESTAMP}.log"

# Create log directory if needed
mkdir -p "$LOG_DIR"

echo "========================================"
echo "Memory Monitoring - $(date)"
echo "========================================"
echo "Memory log: $MEMORY_LOG"
echo "Process log: $PROCESS_LOG"
echo ""

# Initialize memory log with header
echo "timestamp,pid,rss_mb,vsz_mb,cpu_percent,elapsed_time" > "$MEMORY_LOG"

# Use system Python
PYTHON="/usr/bin/python3"

# Start daily_update.py in background and capture its PID
cd "$SCRIPT_DIR"
$PYTHON daily_update.py --days 2 "$@" > "$PROCESS_LOG" 2>&1 &
MAIN_PID=$!

echo "Started daily_update.py with PID: $MAIN_PID"
echo "Monitoring memory usage..."
echo ""

# Track peak memory
PEAK_RSS=0
PEAK_VSZ=0
SAMPLE_COUNT=0

# Monitor memory while process is running
while kill -0 $MAIN_PID 2>/dev/null; do
    # Get current timestamp
    NOW=$(date +"%Y-%m-%d %H:%M:%S")

    # Get memory info for the main process and all child processes
    # Using ps to get RSS (resident set size) and VSZ (virtual memory)
    # Also sum up memory from child processes (ThreadPoolExecutor workers)

    TOTAL_RSS=0
    TOTAL_VSZ=0

    # Get stats for main process and children
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            # Parse: PID RSS VSZ %CPU
            read -r pid rss vsz cpu <<< "$line"
            if [ -n "$rss" ] && [ "$rss" != "RSS" ]; then
                TOTAL_RSS=$((TOTAL_RSS + rss))
                TOTAL_VSZ=$((TOTAL_VSZ + vsz))
            fi
        fi
    done < <(ps -o pid=,rss=,vsz=,%cpu= -p $MAIN_PID 2>/dev/null; pgrep -P $MAIN_PID 2>/dev/null | xargs -I {} ps -o pid=,rss=,vsz=,%cpu= -p {} 2>/dev/null)

    # Convert KB to MB
    RSS_MB=$((TOTAL_RSS / 1024))
    VSZ_MB=$((TOTAL_VSZ / 1024))

    # Update peaks
    if [ $TOTAL_RSS -gt $PEAK_RSS ]; then
        PEAK_RSS=$TOTAL_RSS
    fi
    if [ $TOTAL_VSZ -gt $PEAK_VSZ ]; then
        PEAK_VSZ=$TOTAL_VSZ
    fi

    # Get CPU usage
    CPU=$(ps -o %cpu= -p $MAIN_PID 2>/dev/null | tr -d ' ')
    if [ -z "$CPU" ]; then
        CPU="0.0"
    fi

    # Get elapsed time
    ELAPSED=$(ps -o etime= -p $MAIN_PID 2>/dev/null | tr -d ' ')
    if [ -z "$ELAPSED" ]; then
        ELAPSED="0:00"
    fi

    # Log to file
    echo "${NOW},${MAIN_PID},${RSS_MB},${VSZ_MB},${CPU},${ELAPSED}" >> "$MEMORY_LOG"

    # Print to console (every 6 samples = 30 seconds)
    SAMPLE_COUNT=$((SAMPLE_COUNT + 1))
    if [ $((SAMPLE_COUNT % 6)) -eq 0 ]; then
        echo "  [${ELAPSED}] RSS: ${RSS_MB} MB, VSZ: ${VSZ_MB} MB, CPU: ${CPU}%"
    fi

    # Sleep 5 seconds before next sample
    sleep 5
done

# Wait for process to fully complete
wait $MAIN_PID
EXIT_CODE=$?

# Final stats
echo ""
echo "========================================"
echo "Process completed with exit code: $EXIT_CODE"
echo "========================================"
echo ""
echo "Memory Statistics:"
echo "  Peak RSS: $((PEAK_RSS / 1024)) MB"
echo "  Peak VSZ: $((PEAK_VSZ / 1024)) MB"
echo "  Samples collected: $SAMPLE_COUNT"
echo ""
echo "Log files:"
echo "  Memory: $MEMORY_LOG"
echo "  Process: $PROCESS_LOG"
echo ""

# Check for memory leak indicators
# If peak RSS > 500MB, flag as potential issue
if [ $PEAK_RSS -gt 512000 ]; then
    echo "⚠️  WARNING: Peak RSS exceeded 500 MB - possible memory issue!"
fi

# Show last 10 lines of process log
echo "========================================"
echo "Last 10 lines of process output:"
echo "========================================"
tail -10 "$PROCESS_LOG"

echo ""
echo "========================================"
echo "Monitoring complete!"
echo "========================================"

exit $EXIT_CODE
