#!/usr/bin/env python3
"""
Unit tests for the checkpoint and rate limiting module.

Tests paper_collection/paper_summary/util/checkpoint.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project paths to avoid import issues with __init__.py
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection" / "paper_summary" / "util"))

from checkpoint import (
    CheckpointManager,
    get_checkpoint_manager,
    get_rate_limiter,
    RateLimiter,
    set_checkpoint_manager,
    set_rate_limiter,
)


class TestCheckpointManagerInit:
    """Tests for CheckpointManager initialization."""

    def test_checkpoint_manager_init(self, tmp_path):
        """Create with file path."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"

        # Execute
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Assert
        assert manager.enabled is True
        assert manager.checkpoint_file == str(checkpoint_file)
        assert manager.data["completed_ids"] == []
        assert manager.data["failed_ids"] == []

    def test_checkpoint_manager_disabled(self):
        """Works when file is None."""
        # Execute
        manager = CheckpointManager(checkpoint_file=None)

        # Assert
        assert manager.enabled is False
        assert manager.checkpoint_file is None


class TestCheckpointSaveLoad:
    """Tests for CheckpointManager save/load operations."""

    def test_checkpoint_save_load(self, tmp_path):
        """Roundtrip save/load."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["completed_ids"] = [1, 2, 3]
        manager.data["total_papers"] = 10

        # Execute
        manager.save()

        # Create new manager and load
        manager2 = CheckpointManager(checkpoint_file=str(checkpoint_file))
        loaded = manager2.load()

        # Assert
        assert loaded is True
        assert manager2.data["completed_ids"] == [1, 2, 3]
        assert manager2.data["total_papers"] == 10

    def test_checkpoint_load_nonexistent(self, tmp_path):
        """Load returns False for non-existent file."""
        # Setup
        checkpoint_file = tmp_path / "nonexistent.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        loaded = manager.load()

        # Assert
        assert loaded is False

    def test_checkpoint_save_disabled(self):
        """Save is no-op when disabled."""
        # Setup
        manager = CheckpointManager(checkpoint_file=None)
        manager.data["completed_ids"] = [1, 2, 3]

        # Execute - should not raise
        manager.save()

        # Assert - manager still works
        assert manager.data["completed_ids"] == [1, 2, 3]


class TestMarkCompleted:
    """Tests for CheckpointManager.mark_completed."""

    def test_mark_completed(self, tmp_path):
        """Add to completed_ids."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_completed(123)

        # Assert
        assert 123 in manager.data["completed_ids"]

    def test_mark_completed_removes_from_failed(self, tmp_path):
        """Completing a paper removes it from failed_ids."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["failed_ids"] = [123]
        manager.data["errors"] = {"123": "Some error"}

        # Execute
        manager.mark_completed(123)

        # Assert
        assert 123 in manager.data["completed_ids"]
        assert 123 not in manager.data["failed_ids"]
        assert "123" not in manager.data.get("errors", {})

    def test_mark_completed_no_duplicates(self, tmp_path):
        """Don't add duplicate entries to completed_ids."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_completed(123)
        manager.mark_completed(123)

        # Assert
        assert manager.data["completed_ids"].count(123) == 1


class TestMarkFailed:
    """Tests for CheckpointManager.mark_failed."""

    def test_mark_failed(self, tmp_path):
        """Add to failed_ids with error."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_failed(456, error="PDF download failed")

        # Assert
        assert 456 in manager.data["failed_ids"]
        assert manager.data["errors"]["456"] == "PDF download failed"

    def test_mark_failed_no_error_message(self, tmp_path):
        """Add to failed_ids without error message."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_failed(456)

        # Assert
        assert 456 in manager.data["failed_ids"]

    def test_mark_failed_clears_in_progress(self, tmp_path):
        """Marking failed clears in_progress_id."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.mark_in_progress(456)

        # Execute
        manager.mark_failed(456, error="Error")

        # Assert
        assert manager.data["in_progress_id"] is None


class TestMarkAbstractOnly:
    """Tests for CheckpointManager.mark_abstract_only."""

    def test_mark_abstract_only(self, tmp_path):
        """Track abstract fallbacks."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_abstract_only(789, reason="HTTP 404")

        # Assert
        assert "abstract_only" in manager.data
        assert manager.data["abstract_only"]["789"] == "HTTP 404"

    def test_mark_abstract_only_default_reason(self, tmp_path):
        """Use default reason when not provided."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        manager.mark_abstract_only(789)

        # Assert
        assert manager.data["abstract_only"]["789"] == "PDF fetch failed"

    def test_mark_abstract_only_removes_from_failed(self, tmp_path):
        """Abstract-only removes paper from failed_ids."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["failed_ids"] = [789]
        manager.data["errors"] = {"789": "Some error"}

        # Execute
        manager.mark_abstract_only(789, reason="HTTP 404")

        # Assert
        assert 789 not in manager.data["failed_ids"]
        assert "789" not in manager.data.get("errors", {})


class TestGetRemainingIds:
    """Tests for CheckpointManager.get_remaining_ids."""

    def test_get_remaining_ids(self, tmp_path):
        """Filter out processed papers."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["completed_ids"] = [1, 2]
        manager.data["abstract_only"] = {"3": "HTTP 404"}

        all_ids = [1, 2, 3, 4, 5]

        # Execute
        remaining = manager.get_remaining_ids(all_ids)

        # Assert
        assert remaining == [4, 5]

    def test_get_remaining_ids_all_completed(self, tmp_path):
        """Return empty list when all papers processed."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["completed_ids"] = [1, 2, 3]

        all_ids = [1, 2, 3]

        # Execute
        remaining = manager.get_remaining_ids(all_ids)

        # Assert
        assert remaining == []

    def test_get_remaining_ids_none_completed(self, tmp_path):
        """Return all IDs when none processed."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        all_ids = [1, 2, 3, 4, 5]

        # Execute
        remaining = manager.get_remaining_ids(all_ids)

        # Assert
        assert remaining == [1, 2, 3, 4, 5]


class TestGetSummaryStats:
    """Tests for CheckpointManager.get_summary."""

    def test_get_summary_stats(self, tmp_path):
        """Calculate progress statistics."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))
        manager.data["total_papers"] = 100
        manager.data["completed_ids"] = [1, 2, 3, 4, 5]
        manager.data["failed_ids"] = [6, 7]
        manager.data["abstract_only"] = {"8": "HTTP 404", "9": "EOF error"}

        # Execute
        summary = manager.get_summary()

        # Assert
        assert summary["total"] == 100
        assert summary["completed"] == 5
        assert summary["failed"] == 2
        assert summary["abstract_only"] == 2
        assert summary["remaining"] == 93

    def test_get_summary_stats_empty(self, tmp_path):
        """Calculate progress with empty data."""
        # Setup
        checkpoint_file = tmp_path / "checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        summary = manager.get_summary()

        # Assert
        assert summary["total"] == 0
        assert summary["completed"] == 0
        assert summary["failed"] == 0
        assert summary["abstract_only"] == 0
        assert summary["remaining"] == 0


class TestRateLimiterInit:
    """Tests for RateLimiter initialization."""

    def test_rate_limiter_init(self):
        """Initialize with requests per minute."""
        # Execute
        limiter = RateLimiter(requests_per_minute=60)

        # Assert
        assert limiter.enabled is True
        assert limiter.requests_per_minute == 60
        assert limiter.min_interval == 1.0

    def test_rate_limiter_disabled(self):
        """Works when rate is 0."""
        # Execute
        limiter = RateLimiter(requests_per_minute=0)

        # Assert
        assert limiter.enabled is False
        assert limiter.min_interval == 0

    def test_rate_limiter_negative(self):
        """Disabled when rate is negative."""
        # Execute
        limiter = RateLimiter(requests_per_minute=-1)

        # Assert
        assert limiter.enabled is False


class TestRateLimiterAcquire:
    """Tests for RateLimiter.acquire."""

    @patch("paper_collection.paper_summary.util.checkpoint.time.sleep")
    def test_rate_limiter_acquire_no_wait(self, _mock_sleep):
        """No wait when enough time has passed."""
        # Setup
        limiter = RateLimiter(requests_per_minute=60)
        limiter.last_request_time = 0  # Long ago

        # Execute
        limiter.acquire()

        # Assert - no sleep called or minimal sleep
        assert limiter.last_request_time > 0

    def test_rate_limiter_acquire_disabled(self):
        """No-op when disabled."""
        # Setup
        limiter = RateLimiter(requests_per_minute=0)

        # Execute - should return immediately
        limiter.acquire()

        # Assert
        assert limiter.last_request_time == 0.0


class TestGlobalCheckpointManager:
    """Tests for global checkpoint manager functions."""

    def test_get_set_checkpoint_manager(self, tmp_path):
        """Test global get/set checkpoint manager functions."""
        # Setup
        checkpoint_file = tmp_path / "global_checkpoint.json"
        manager = CheckpointManager(checkpoint_file=str(checkpoint_file))

        # Execute
        set_checkpoint_manager(manager)
        result = get_checkpoint_manager()

        # Assert
        assert result is manager

    def test_set_checkpoint_manager_to_none(self):
        """Allow setting global manager to None."""
        # Setup
        set_checkpoint_manager(None)

        # Execute
        result = get_checkpoint_manager()

        # Assert
        assert result is None


class TestGlobalRateLimiter:
    """Tests for global rate limiter functions."""

    def test_get_set_rate_limiter(self):
        """Test global get/set rate limiter functions."""
        # Setup
        limiter = RateLimiter(requests_per_minute=30)

        # Execute
        set_rate_limiter(limiter)
        result = get_rate_limiter()

        # Assert
        assert result is limiter
        assert result.requests_per_minute == 30

    def test_set_rate_limiter_to_none(self):
        """Allow setting global limiter to None."""
        # Setup
        set_rate_limiter(None)

        # Execute
        result = get_rate_limiter()

        # Assert
        assert result is None
