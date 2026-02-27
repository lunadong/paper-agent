#!/usr/bin/env python3
"""
Checkpoint and Rate Limiting Module

Provides checkpoint management for batch processing and rate limiting
for API requests. Extracted from summary_generation.py for modularity.
"""

import json
import os
import signal
import threading
import time
from datetime import datetime
from typing import Optional


# ==============================================================================
# Rate Limiter - Controls API requests per minute
# ==============================================================================
class RateLimiter:
    """
    Token bucket rate limiter for controlling API request rate.

    Thread-safe implementation that limits requests per minute.
    """

    def __init__(self, requests_per_minute: int):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute.
                                 If 0 or negative, rate limiting is disabled.
        """
        self.requests_per_minute = requests_per_minute
        self.enabled = requests_per_minute > 0
        self.min_interval = 60.0 / requests_per_minute if self.enabled else 0
        self.last_request_time = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        """
        Wait until a request is allowed, then consume one token.

        This method blocks if necessary to maintain the rate limit.
        """
        if not self.enabled:
            return

        with self._lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            wait_time = self.min_interval - time_since_last

            if wait_time > 0:
                print(f"  [Rate limit] Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)

            self.last_request_time = time.time()


# Global rate limiter (initialized in main)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter):
    """Set the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


# ==============================================================================
# Checkpoint Manager - Saves/loads batch progress for resume capability
# ==============================================================================
class CheckpointManager:
    """
    Manages checkpointing for batch processing.

    Saves progress to a JSON file so processing can resume after interruption.
    """

    def __init__(self, checkpoint_file: Optional[str] = None):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_file: Path to checkpoint file.
                If None, checkpointing is disabled.
        """
        self.checkpoint_file = checkpoint_file
        self.enabled = checkpoint_file is not None
        self.data = {
            "started_at": None,
            "updated_at": None,
            "total_papers": 0,
            "completed_ids": [],
            "failed_ids": [],
            "in_progress_id": None,
        }
        self._lock = threading.Lock()

    def load(self) -> bool:
        """
        Load checkpoint from file.

        Returns:
            True if checkpoint was loaded, False otherwise.
        """
        if not self.enabled or self.checkpoint_file is None:
            return False
        if not os.path.exists(self.checkpoint_file):
            return False

        try:
            with open(self.checkpoint_file, "r") as f:
                self.data = json.load(f)
            completed = len(self.data.get("completed_ids", []))
            retryable = len(self.data.get("errors", {}))
            abstract_only = len(self.data.get("abstract_only", {}))
            # Legacy: also count permanent_errors (will be reprocessed)
            permanent = len(self.data.get("permanent_errors", {}))
            print(
                f"Loaded checkpoint: {completed} completed, "
                f"{retryable} retryable errors, {abstract_only} abstract_only"
            )
            if permanent > 0:
                print(
                    f"  Note: {permanent} legacy permanent_errors will be "
                    f"reprocessed with abstract fallback"
                )
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load checkpoint: {e}")
            return False

    def save(self):
        """Save checkpoint to file."""
        if not self.enabled:
            return

        with self._lock:
            self.data["updated_at"] = datetime.now().isoformat()
            if self.checkpoint_file is None:
                return
            try:
                with open(self.checkpoint_file, "w") as f:
                    json.dump(self.data, f, indent=2)
            except IOError as e:
                print(f"Warning: Could not save checkpoint: {e}")

    def start_batch(self, total_papers: int, paper_ids: list):
        """
        Initialize checkpoint for a new batch.

        Args:
            total_papers: Total number of papers to process.
            paper_ids: List of paper IDs in the batch.
        """
        if not self.enabled:
            return

        with self._lock:
            self.data["started_at"] = datetime.now().isoformat()
            self.data["total_papers"] = total_papers
            self.data["all_ids"] = paper_ids
            # Preserve completed/failed from previous run if resuming
            if "completed_ids" not in self.data:
                self.data["completed_ids"] = []
            if "failed_ids" not in self.data:
                self.data["failed_ids"] = []
        self.save()

    def mark_in_progress(self, paper_id: int):
        """Mark a paper as currently being processed."""
        if not self.enabled:
            return

        with self._lock:
            self.data["in_progress_id"] = paper_id
        self.save()

    def mark_completed(self, paper_id: int):
        """Mark a paper as successfully completed."""
        if not self.enabled:
            return

        with self._lock:
            if "completed_ids" not in self.data:
                self.data["completed_ids"] = []
            if paper_id not in self.data["completed_ids"]:
                self.data["completed_ids"].append(paper_id)
            self.data["in_progress_id"] = None
            # Remove from failed_ids if it was there
            if paper_id in self.data.get("failed_ids", []):
                self.data["failed_ids"].remove(paper_id)
            # Remove from errors dict if it was there (successful retry)
            str_id = str(paper_id)
            if str_id in self.data.get("errors", {}):
                del self.data["errors"][str_id]
        self.save()

    def mark_failed(self, paper_id: int, error: Optional[str] = None):
        """Mark a paper as failed."""
        if not self.enabled:
            return

        with self._lock:
            if paper_id not in self.data.get("failed_ids", []):
                self.data["failed_ids"].append(paper_id)
            self.data["in_progress_id"] = None
            # Store error message
            if "errors" not in self.data:
                self.data["errors"] = {}
            if error:
                self.data["errors"][str(paper_id)] = error
        self.save()

    def is_completed(self, paper_id: int) -> bool:
        """Check if a paper was already completed."""
        return paper_id in self.data.get("completed_ids", [])

    def get_remaining_ids(self, all_ids: list) -> list:
        """
        Get IDs that still need processing.

        Excludes completed IDs and abstract_only IDs (already processed with
        abstract fallback).

        Args:
            all_ids: List of all paper IDs to process.

        Returns:
            List of paper IDs not yet completed or processed with abstract.
        """
        completed = set(self.data.get("completed_ids", []))
        # Also exclude abstract_only (already processed with fallback)
        abstract_only = set(
            int(pid) for pid in self.data.get("abstract_only", {}).keys()
        )
        exclude = completed | abstract_only
        return [pid for pid in all_ids if pid not in exclude]

    def mark_abstract_only(self, paper_id: int, reason: Optional[str] = None):
        """
        Mark a paper as processed with abstract-only (PDF fetch failed).

        These papers had stage 1 run with abstract text and stage 2 skipped.

        Args:
            paper_id: Paper database ID.
            reason: Why PDF fetch failed (e.g., "HTTP 404", "EOF error").
        """
        if not self.enabled:
            return
        with self._lock:
            if "abstract_only" not in self.data:
                self.data["abstract_only"] = {}
            reason_msg = reason or "PDF fetch failed"
            self.data["abstract_only"][str(paper_id)] = reason_msg
            self.data["in_progress_id"] = None
            # Remove from failed_ids if present
            if paper_id in self.data.get("failed_ids", []):
                self.data["failed_ids"].remove(paper_id)
            # Remove from errors if present
            str_id = str(paper_id)
            if str_id in self.data.get("errors", {}):
                del self.data["errors"][str_id]
        self.save()

    def get_summary(self) -> dict:
        """Get summary of checkpoint status."""
        completed = len(self.data.get("completed_ids", []))
        failed = len(self.data.get("failed_ids", []))
        abstract_only = len(self.data.get("abstract_only", {}))
        total = self.data.get("total_papers", 0)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "abstract_only": abstract_only,
            "remaining": total - completed - abstract_only,
        }

    def _categorize_errors(
        self, errors: dict, patterns: list[tuple[str, list[str]]]
    ) -> dict[str, list]:
        """
        Categorize errors based on pattern matching.

        Args:
            errors: Dict of {paper_id: error_message}
            patterns: List of (category_name, [patterns_to_match])

        Returns:
            Dict of {category_name: [paper_ids]}
        """
        categories: dict[str, list] = {name: [] for name, _ in patterns}
        for pid, msg in errors.items():
            for name, match_patterns in patterns:
                if any(p in msg for p in match_patterns):
                    categories[name].append(pid)
                    break
        return categories

    def get_error_stats(self) -> dict:
        """
        Get detailed error statistics with bucketing.

        Returns:
            Dict with error categories and counts.
        """
        errors = self.data.get("errors", {})
        abstract_only = self.data.get("abstract_only", {})

        # Pattern definitions: (category_name, [patterns_to_match])
        retryable_patterns = [
            ("Rate Limit (429)", ["429", "RESOURCE_EXHAUSTED"]),
            ("Gateway Timeout (504)", ["504", "Gateway Time-out"]),
            ("API Error (500)", ["API call failed"]),
            ("JSON Parse Error", ["Could not parse", "JSON"]),
        ]
        abstract_only_patterns = [
            ("EOF (corrupted PDFs)", ["EOF"]),
            ("HTTP 403 (access denied)", ["HTTP 403"]),
            ("HTTP 404 (not found)", ["HTTP 404"]),
            ("HTTP 405", ["HTTP 405"]),
            ("SSL error", ["SSL", "Certificate"]),
            ("Connection errors", ["HTTPSConnectionPool", "Max retries"]),
        ]

        retryable_cats = self._categorize_errors(errors, retryable_patterns)
        abstract_cats = self._categorize_errors(
            abstract_only,
            abstract_only_patterns,
        )

        return {
            "retryable": {k: len(v) for k, v in retryable_cats.items() if v},
            "abstract_only": {k: len(v) for k, v in abstract_cats.items() if v},
            "retryable_total": len(errors),
            "abstract_only_total": len(abstract_only),
        }

    def categorize_errors(self) -> dict:
        """
        Categorize errors into high-level categories for the summary table.

        Returns:
            Dict with counts for each category:
            - db_connection: Database connection errors (DNS, network issues)
            - rate_limit: LLM API rate limiting (429)
            - corrupt_pdf: Malformed PDF files (EOF errors)
            - api_error: Server-side API errors (500, 504)
            - timeout: Network timeouts
            - other: Miscellaneous errors
        """
        errors = self.data.get("errors", {})

        # Define category patterns
        categories = {
            "db_connection": [
                "sqlite3.OperationalError",
                "unable to resolve",
                "DNS",
                "database",
            ],
            "rate_limit": ["429", "RESOURCE_EXHAUSTED", "rate limit", "quota"],
            "corrupt_pdf": ["EOF", "EOF marker", "corrupt", "malformed"],
            "api_error": ["500", "504", "API call failed", "Gateway"],
            "timeout": ["timeout", "timed out", "TimeoutError"],
        }

        counts = {k: 0 for k in categories}
        counts["other"] = 0

        for _, msg in errors.items():
            if msg is None:
                msg = ""
            msg_lower = msg.lower()
            categorized = False
            for cat, patterns in categories.items():
                if any(p.lower() in msg_lower for p in patterns):
                    counts[cat] += 1
                    categorized = True
                    break
            if not categorized:
                counts["other"] += 1

        return counts

    def print_stats(self):
        """Print formatted error statistics table."""
        summary = self.get_summary()
        error_stats = self.get_error_stats()

        print()
        print("=" * 70)
        print("PROGRESS STATISTICS")
        print("=" * 70)
        print()
        print(f"{'Field':<30} {'Count':>8}   Description")
        print("-" * 70)
        print(
            f"{'completed_ids':<30} {summary['completed']:>8}   "
            f"Successfully processed (full PDF)"
        )
        print(
            f"{'abstract_only':<30} {error_stats['abstract_only_total']:>8}   "
            f"Processed with abstract (PDF failed)"
        )
        print(
            f"{'errors (retryable)':<30} {error_stats['retryable_total']:>8}   "
            f"Can retry: rate limits, API errors, timeouts"
        )
        print()

        if error_stats["retryable"]:
            print("Retryable errors breakdown:")
            for cat, count in sorted(
                error_stats["retryable"].items(), key=lambda x: -x[1]
            ):
                print(f"  - {cat}: {count}")
            print()

        if error_stats["abstract_only"]:
            print("Abstract-only breakdown (PDF fetch failures):")
            for cat, count in sorted(
                error_stats["abstract_only"].items(), key=lambda x: -x[1]
            ):
                print(f"  - {cat}: {count}")
            print()

        print("=" * 70)


# Global checkpoint manager (initialized in main)
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> Optional[CheckpointManager]:
    """Get the global checkpoint manager instance."""
    return _checkpoint_manager


def set_checkpoint_manager(manager: CheckpointManager):
    """Set the global checkpoint manager instance."""
    global _checkpoint_manager
    _checkpoint_manager = manager


# ==============================================================================
# Graceful Shutdown Handler
# ==============================================================================
_shutdown_requested = False


def request_shutdown():
    """Request graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """Check if shutdown was requested."""
    return _shutdown_requested


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        print("\n\n[!] Shutdown requested. Finishing current paper...")
        print("   (Press Ctrl+C again to force quit)\n")
        request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
