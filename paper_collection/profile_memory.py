#!/usr/bin/env python3
"""
Memory Profile Wrapper for daily_update.py

Runs daily_update.py with detailed memory profiling using tracemalloc.
Provides snapshots of memory allocation and identifies potential leaks.

Usage:
    python3 profile_memory.py              # Run with defaults
    python3 profile_memory.py --days 7     # Pass args to daily_update.py
"""

import gc
import sys
import tracemalloc
from datetime import datetime
from pathlib import Path

# Add script directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

LOG_DIR = SCRIPT_DIR.parent / "tmp"
LOG_DIR.mkdir(exist_ok=True)


def format_size(size_bytes: float) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def get_memory_stats() -> dict:
    """Get current memory statistics."""
    import resource

    rusage = resource.getrusage(resource.RUSAGE_SELF)

    # Get tracemalloc stats if running
    traced_current = 0
    traced_peak = 0
    if tracemalloc.is_tracing():
        traced_current, traced_peak = tracemalloc.get_traced_memory()

    # On macOS, ru_maxrss is in bytes; on Linux it's in KB
    rss_bytes = rusage.ru_maxrss
    if sys.platform == "darwin":
        rss_mb = rss_bytes / (1024 * 1024)
    else:
        rss_mb = rss_bytes / 1024

    return {
        "rss_mb": rss_mb,
        "traced_current_mb": traced_current / (1024 * 1024),
        "traced_peak_mb": traced_peak / (1024 * 1024),
        "gc_counts": gc.get_count(),
    }


def log_memory_snapshot(log_file, label: str, snapshot=None):
    """Log a memory snapshot with top allocations."""
    stats = get_memory_stats()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_file.write(f"\n{'=' * 60}\n")
    log_file.write(f"[{timestamp}] {label}\n")
    log_file.write(f"{'=' * 60}\n")
    log_file.write(f"RSS: {stats['rss_mb']:.2f} MB\n")
    log_file.write(f"Traced: {stats['traced_current_mb']:.2f} MB (peak: {stats['traced_peak_mb']:.2f} MB)\n")
    log_file.write(f"GC counts: {stats['gc_counts']}\n")

    if snapshot:
        log_file.write("\nTop 10 memory allocations:\n")
        top_stats = snapshot.statistics("lineno")[:10]
        for stat in top_stats:
            log_file.write(f"  {stat}\n")

    log_file.flush()
    print(f"[{timestamp}] {label} - RSS: {stats['rss_mb']:.2f} MB")


def run_with_profiling():
    """Run daily_update.py with memory profiling."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    memory_log_path = LOG_DIR / f"memory_profile_{timestamp}.log"

    print("=" * 60)
    print("Memory Profiling - daily_update.py")
    print("=" * 60)
    print(f"Log file: {memory_log_path}")
    print()

    # Start memory tracing
    tracemalloc.start(25)  # Store 25 frames for detailed tracebacks

    with open(memory_log_path, "w") as log_file:
        log_file.write(f"Memory Profile Log - {datetime.now()}\n")
        log_file.write(f"Python: {sys.version}\n")
        log_file.write(f"Script dir: {SCRIPT_DIR}\n\n")

        # Initial snapshot
        snapshot1 = tracemalloc.take_snapshot()
        log_memory_snapshot(log_file, "INITIAL STATE", snapshot1)

        # Import and run the main function
        try:
            # Import dependencies
            log_memory_snapshot(log_file, "After imports")

            from daily_update import main

            snapshot2 = tracemalloc.take_snapshot()
            log_memory_snapshot(log_file, "After importing daily_update", snapshot2)

            # Run the main function
            # Note: We need to patch sys.argv for argument handling
            original_argv = sys.argv
            sys.argv = ["daily_update.py", "--days", "2"] + sys.argv[1:]

            try:
                main()
            finally:
                sys.argv = original_argv

            snapshot3 = tracemalloc.take_snapshot()
            log_memory_snapshot(log_file, "After main() completed", snapshot3)

            # Force garbage collection
            gc.collect()
            snapshot4 = tracemalloc.take_snapshot()
            log_memory_snapshot(log_file, "After gc.collect()", snapshot4)

            # Compare snapshots to find memory growth
            log_file.write("\n" + "=" * 60 + "\n")
            log_file.write("MEMORY GROWTH ANALYSIS\n")
            log_file.write("=" * 60 + "\n")

            log_file.write("\nGrowth from start to end:\n")
            top_diffs = snapshot4.compare_to(snapshot1, "lineno")[:15]
            for diff in top_diffs:
                if diff.size_diff > 0:
                    log_file.write(f"  {diff}\n")

            log_file.write("\nGrowth during main() execution:\n")
            main_diffs = snapshot3.compare_to(snapshot2, "lineno")[:15]
            for diff in main_diffs:
                if diff.size_diff > 0:
                    log_file.write(f"  {diff}\n")

            # Summary
            current, peak = tracemalloc.get_traced_memory()
            log_file.write("\n" + "=" * 60 + "\n")
            log_file.write("SUMMARY\n")
            log_file.write("=" * 60 + "\n")
            log_file.write(f"Final traced memory: {format_size(current)}\n")
            log_file.write(f"Peak traced memory: {format_size(peak)}\n")

            print()
            print("=" * 60)
            print("PROFILING COMPLETE")
            print("=" * 60)
            print(f"Peak memory: {format_size(peak)}")
            print(f"Log file: {memory_log_path}")

            # Flag potential issues
            if peak > 500 * 1024 * 1024:  # 500 MB
                print("\n⚠️  WARNING: Peak memory exceeded 500 MB!")
                log_file.write("\n⚠️  WARNING: Peak memory exceeded 500 MB!\n")

        except Exception as e:
            log_file.write(f"\nERROR: {e}\n")
            import traceback
            log_file.write(traceback.format_exc())
            raise

        finally:
            tracemalloc.stop()

    return memory_log_path


if __name__ == "__main__":
    run_with_profiling()
