"""
Unit tests for the configuration module.

Tests paper_collection/config.py functionality including:
- Config file finding
- YAML loading
- Config object creation with defaults and overrides
- Singleton pattern
"""

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection"))

import config as config_module
from config import (
    config,
    create_config_from_dict,
    DatabaseConfig,
    find_config_file,
    GeminiConfig,
    GmailConfig,
    load_config_from_file,
)


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_find_config_file_in_current_dir(self, tmp_path: Path) -> None:
        """Config file is found when it exists in the expected location."""
        # Setup: Create a config file in a temp directory
        config_file = tmp_path / "config.yaml"
        config_file.write_text("notification_email: test@example.com")

        # Execute: Patch CONFIG_LOCATIONS to use our temp file
        with patch("config.CONFIG_LOCATIONS", [str(config_file)]):
            result = find_config_file()

        # Assert: The config file path is returned
        assert result == str(config_file), "Should return the path to the config file"

    def test_find_config_file_not_found(self, tmp_path: Path) -> None:
        """Returns None when no config file exists."""
        # Setup: Define paths that don't exist
        nonexistent_paths = [
            str(tmp_path / "nonexistent1.yaml"),
            str(tmp_path / "nonexistent2.yaml"),
        ]

        # Execute: Patch CONFIG_LOCATIONS with nonexistent paths
        with patch("config.CONFIG_LOCATIONS", nonexistent_paths):
            result = find_config_file()

        # Assert: None is returned when no config exists
        assert result is None, "Should return None when no config file exists"


class TestLoadConfigFromFile:
    """Tests for load_config_from_file function."""

    def test_load_config_from_file(self, tmp_path: Path) -> None:
        """Parse YAML config file correctly."""
        # Setup: Create a valid YAML config file
        config_content = {
            "notification_email": "user@example.com",
            "website_url": "http://test.local:8080",
            "database": {"url": "postgresql://user:pass@localhost:5432/db"},
        }
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_content, f)

        # Execute: Load the config file
        result = load_config_from_file(str(config_file))

        # Assert: Parsed content matches expected values
        assert result["notification_email"] == "user@example.com", (
            "Should parse notification_email correctly"
        )
        assert result["website_url"] == "http://test.local:8080", (
            "Should parse website_url correctly"
        )
        assert (
            result["database"]["url"] == "postgresql://user:pass@localhost:5432/db"
        ), "Should parse nested database config correctly"


class TestCreateConfigFromDict:
    """Tests for create_config_from_dict function."""

    def test_create_config_from_dict_defaults(self) -> None:
        """Default values are applied when config dict is empty."""
        # Setup: Empty config dictionary
        empty_config: Dict[str, Any] = {}

        # Execute: Create config from empty dict
        result = create_config_from_dict(empty_config)

        # Assert: Default values are applied
        assert result.notification_email == "", (
            "notification_email should default to empty string"
        )
        assert result.website_url == "http://localhost:5001", (
            "website_url should default to localhost:5001"
        )
        assert result.web.port == 5001, "web.port should default to 5001"
        assert result.web.debug is True, "web.debug should default to True"
        assert result.search.model_name == "all-MiniLM-L6-v2", (
            "search.model_name should have default value"
        )
        assert result.daily_update.default_days == 1, (
            "daily_update.default_days should default to 1"
        )

    def test_create_config_from_dict_overrides(
        self, sample_config_dict: Dict[str, Any]
    ) -> None:
        """Custom values override default values."""
        # Setup: Use sample_config_dict from conftest.py
        config_data = sample_config_dict.copy()
        config_data["notification_email"] = "custom@example.com"
        config_data["website_url"] = "https://custom.example.com"
        config_data["web"]["port"] = 8080
        config_data["web"]["papers_per_page"] = 20

        # Execute: Create config from dict with overrides
        result = create_config_from_dict(config_data)

        # Assert: Custom values override defaults
        assert result.notification_email == "custom@example.com", (
            "notification_email should be overridden"
        )
        assert result.website_url == "https://custom.example.com", (
            "website_url should be overridden"
        )
        assert result.web.port == 8080, "web.port should be overridden"
        assert result.web.papers_per_page == 20, (
            "web.papers_per_page should be overridden"
        )


class TestGmailConfig:
    """Tests for GmailConfig defaults."""

    def test_gmail_config_defaults(self) -> None:
        """Gmail config has correct default values."""
        # Setup: Create a default GmailConfig
        gmail_config = GmailConfig()

        # Execute: Check default values (no action needed, values set on creation)

        # Assert: Default values are correct
        assert gmail_config.credentials_file == "credentials.json", (
            "credentials_file should default to credentials.json"
        )
        assert gmail_config.token_file == "token.json", (
            "token_file should default to token.json"
        )
        assert gmail_config.search_query == "from:scholaralerts-noreply@google.com", (
            "search_query should filter for Google Scholar alerts"
        )


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""

    def test_database_config(self) -> None:
        """Database URL is configured correctly from dict."""
        # Setup: Config dict with database URL
        config_data = {
            "database": {"url": "postgresql://user:password@localhost:5432/papers"}
        }

        # Execute: Create config from dict
        result = create_config_from_dict(config_data)

        # Assert: Database URL is set correctly
        assert (
            result.database.url == "postgresql://user:password@localhost:5432/papers"
        ), "Database URL should be set from config dict"

    def test_database_config_default_empty(self) -> None:
        """Database URL defaults to empty string when not provided."""
        # Setup: Create default DatabaseConfig
        db_config = DatabaseConfig()

        # Execute: Check default value (no action needed)

        # Assert: Default URL is empty
        assert db_config.url == "", "Database URL should default to empty string"


class TestGeminiConfig:
    """Tests for GeminiConfig."""

    def test_gemini_config(self) -> None:
        """Gemini API settings are configured correctly."""
        # Setup: Config dict with Gemini settings
        config_data = {
            "gemini": {
                "api_key": "test-api-key-12345",
                "api_url": "https://api.example.com/v1/chat",
                "model": "gemini-2.0-pro",
                "lightweight_model": "gemini-2.0-nano",
            }
        }

        # Execute: Create config from dict
        result = create_config_from_dict(config_data)

        # Assert: Gemini settings are configured correctly
        assert result.gemini.api_key == "test-api-key-12345", (
            "api_key should be set from config"
        )
        assert result.gemini.api_url == "https://api.example.com/v1/chat", (
            "api_url should be set from config"
        )
        assert result.gemini.model == "gemini-2.0-pro", (
            "model should be set from config"
        )
        assert result.gemini.lightweight_model == "gemini-2.0-nano", (
            "lightweight_model should be set from config"
        )

    def test_gemini_config_defaults(self) -> None:
        """Gemini config has correct default values."""
        # Setup: Create default GeminiConfig
        gemini_config = GeminiConfig()

        # Execute: Check default values (no action needed)

        # Assert: Default values are correct
        assert gemini_config.api_key == "", "api_key should default to empty string"
        assert gemini_config.api_url == "", "api_url should default to empty string"
        assert gemini_config.model == "gemini-2.0-flash", (
            "model should default to gemini-2.0-flash"
        )
        assert gemini_config.lightweight_model == "gemini-2.0-flash-lite", (
            "lightweight_model should default to gemini-2.0-flash-lite"
        )


class TestConfigSingleton:
    """Tests for config singleton behavior."""

    def test_config_singleton(self, tmp_path: Path) -> None:
        """config() returns the same instance on multiple calls."""
        # Setup: Reset the singleton and create a temp config
        config_module._config_instance = None

        config_file = tmp_path / "config.yaml"
        config_file.write_text("notification_email: singleton@test.com")

        # Execute: Call config() multiple times
        with patch("config.CONFIG_LOCATIONS", [str(config_file)]):
            first_call = config()
            second_call = config()
            third_call = config()

        # Assert: All calls return the same instance
        assert first_call is second_call, "Second call should return same instance"
        assert second_call is third_call, "Third call should return same instance"
        assert first_call.notification_email == "singleton@test.com", (
            "Singleton should load config correctly"
        )

        # Cleanup: Reset singleton for other tests
        config_module._config_instance = None
