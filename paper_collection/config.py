#!/usr/bin/python3
"""
Configuration Management Module

Loads configuration from config.yaml file and provides defaults.
Supports command-line overrides for all settings.

Usage:
    from config import get_config

    config = get_config()
    email = config.notification_email
    db_path = config.get_db_path()
"""

import argparse
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

import yaml

# Project root directory (parent of paper_collection)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Config file locations (in order of preference)
# SCRIPT_DIR is checked first to support standalone deployment (e.g., cron jobs)
# where config.py is in the same directory as config.yaml
CONFIG_LOCATIONS = [
    os.path.join(SCRIPT_DIR, "config.yaml"),
    os.path.join(PROJECT_ROOT, "config.yaml"),
    os.path.join(PROJECT_ROOT, "config.yml"),
    os.path.join(os.path.expanduser("~"), ".paper_agent", "config.yaml"),
]

# Month name to number mapping for date parsing
MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_email_date(date_str: str) -> str:
    """
    Parse various date formats to YYYY-MM-DD (sortable format).

    Handles:
    - "Thu, 14 Dec 2023 15:27:28 -0800" -> "2023-12-14"
    - "2/3/2026" or "12/14/2023" (M/D/YYYY) -> "2026-02-03"
    - Already "2023-12-14" -> unchanged

    Args:
        date_str: Date string in various formats

    Returns:
        Date string in YYYY-MM-DD format, or original string if parsing fails
    """
    if not date_str or date_str == "N/A":
        return date_str

    # Already in YYYY-MM-DD format?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Try M/D/YYYY format (e.g., "2/3/2026" or "12/14/2023")
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = match.group(3)
        return f"{year}-{month:02d}-{day:02d}"

    # Try email format: "Thu, 14 Dec 2023 15:27:28 -0800"
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = match.group(3)

        month = MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month:02d}-{day:02d}"

    # Return original if can't parse
    return date_str


@dataclass
class GmailConfig:
    """Gmail API configuration."""

    credentials_file: str = "credentials.json"
    token_file: str = "token.json"
    search_query: str = "from:scholaralerts-noreply@google.com"


@dataclass
class DataConfig:
    """Data storage configuration."""

    data_dir: str = "web_interface/data"


@dataclass
class WebConfig:
    """Web server configuration."""

    host: str = "0.0.0.0"
    port: int = 5001
    debug: bool = True
    papers_per_page: int = 10


@dataclass
class SearchConfig:
    """Semantic search configuration."""

    model_name: str = "all-MiniLM-L6-v2"
    score_threshold: float = 0.2


@dataclass
class TopicsConfig:
    """Topic tagging configuration."""

    score_threshold: float = 0.2
    definitions: Dict = field(default_factory=dict)


@dataclass
class DailyUpdateConfig:
    """Daily update configuration."""

    default_days: int = 1
    max_emails: int = 100
    send_notification: bool = True


@dataclass
class DatabaseConfig:
    """Database configuration."""

    url: str = ""


@dataclass
class OpenAIConfig:
    """OpenAI API configuration."""

    api_key: str = ""
    embedding_model: str = "text-embedding-3-small"


@dataclass
class GeminiConfig:
    """Gemini API configuration for LLM calls."""

    api_key: str = ""
    api_url: str = ""
    model: str = "gemini-2.0-flash"
    lightweight_model: str = "gemini-2.0-flash-lite"


@dataclass
class AnthropicConfig:
    """Anthropic Claude API configuration for prompt optimization."""

    api_key: str = ""
    model: str = "claude-opus-4.5"


@dataclass
class Config:
    """Main configuration class."""

    notification_email: str = ""
    website_url: str = "http://localhost:5001"
    gmail: GmailConfig = field(default_factory=GmailConfig)
    data: DataConfig = field(default_factory=DataConfig)
    web: WebConfig = field(default_factory=WebConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    topics: TopicsConfig = field(default_factory=TopicsConfig)
    daily_update: DailyUpdateConfig = field(default_factory=DailyUpdateConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)

    # Internal: track where config was loaded from
    _config_file: Optional[str] = None

    def get_credentials_path(self) -> str:
        """Get absolute path to credentials file."""
        path = self.gmail.credentials_file
        if not os.path.isabs(path):
            # Try relative to script directory first
            script_path = os.path.join(SCRIPT_DIR, path)
            if os.path.exists(script_path):
                return script_path
            # Then try relative to project root
            return os.path.join(PROJECT_ROOT, path)
        return path

    def get_token_path(self) -> str:
        """Get absolute path to token file."""
        path = self.gmail.token_file
        if not os.path.isabs(path):
            # Try relative to script directory first
            script_path = os.path.join(SCRIPT_DIR, path)
            if os.path.exists(script_path) or os.path.exists(
                os.path.dirname(script_path) or SCRIPT_DIR
            ):
                return script_path
            # Then try relative to project root
            return os.path.join(PROJECT_ROOT, path)
        return path

    def get_data_dir(self) -> str:
        """Get absolute path to data directory."""
        path = self.data.data_dir
        if not os.path.isabs(path):
            return os.path.join(PROJECT_ROOT, path)
        return path


def find_config_file() -> Optional[str]:
    """Find the first existing config file."""
    for path in CONFIG_LOCATIONS:
        if os.path.exists(path):
            return path
    return None


def load_config_from_file(path: str) -> dict:
    """Load configuration from a YAML file."""
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _apply_gmail_config(config: Config, data: dict) -> None:
    """Apply gmail settings from data dict to config."""
    if "gmail" not in data:
        return
    gmail_data = data["gmail"]
    config.gmail = GmailConfig(
        credentials_file=gmail_data.get(
            "credentials_file", config.gmail.credentials_file
        ),
        token_file=gmail_data.get("token_file", config.gmail.token_file),
        search_query=gmail_data.get("search_query", config.gmail.search_query),
    )


def _apply_web_config(config: Config, data: dict) -> None:
    """Apply web settings from data dict to config."""
    if "web" not in data:
        return
    web_data = data["web"]
    config.web = WebConfig(
        host=web_data.get("host", config.web.host),
        port=web_data.get("port", config.web.port),
        debug=web_data.get("debug", config.web.debug),
        papers_per_page=web_data.get("papers_per_page", config.web.papers_per_page),
    )


def _apply_search_config(config: Config, data: dict) -> None:
    """Apply search settings from data dict to config."""
    if "search" not in data:
        return
    search_data = data["search"]
    config.search = SearchConfig(
        model_name=search_data.get("model_name", config.search.model_name),
        score_threshold=search_data.get(
            "score_threshold", config.search.score_threshold
        ),
    )


def _apply_topics_config(config: Config, data: dict) -> None:
    """Apply topics settings from data dict to config."""
    if "topics" not in data:
        return
    topics_data = data["topics"]
    config.topics = TopicsConfig(
        score_threshold=topics_data.get(
            "score_threshold", config.topics.score_threshold
        ),
        definitions=topics_data.get("definitions", {}),
    )


def _apply_daily_update_config(config: Config, data: dict) -> None:
    """Apply daily_update settings from data dict to config."""
    if "daily_update" not in data:
        return
    daily_data = data["daily_update"]
    config.daily_update = DailyUpdateConfig(
        default_days=daily_data.get("default_days", config.daily_update.default_days),
        max_emails=daily_data.get("max_emails", config.daily_update.max_emails),
        send_notification=daily_data.get(
            "send_notification", config.daily_update.send_notification
        ),
    )


def _apply_llm_configs(config: Config, data: dict) -> None:
    """Apply LLM provider settings (openai, gemini, anthropic) from data dict to config."""
    if "openai" in data:
        openai_data = data["openai"]
        config.openai = OpenAIConfig(
            api_key=openai_data.get("api_key", config.openai.api_key),
            embedding_model=openai_data.get(
                "embedding_model", config.openai.embedding_model
            ),
        )

    if "gemini" in data:
        gemini_data = data["gemini"]
        config.gemini = GeminiConfig(
            api_key=gemini_data.get("api_key", config.gemini.api_key),
            api_url=gemini_data.get("api_url", config.gemini.api_url),
            model=gemini_data.get("model", config.gemini.model),
            lightweight_model=gemini_data.get(
                "lightweight_model", config.gemini.lightweight_model
            ),
        )

    if "anthropic" in data:
        anthropic_data = data["anthropic"]
        config.anthropic = AnthropicConfig(
            api_key=anthropic_data.get("api_key", config.anthropic.api_key),
            model=anthropic_data.get("model", config.anthropic.model),
        )


def create_config_from_dict(data: dict) -> Config:
    """Create a Config object from a dictionary."""
    config = Config()

    if "notification_email" in data:
        config.notification_email = data["notification_email"]
    if "website_url" in data:
        config.website_url = data["website_url"]

    _apply_gmail_config(config, data)

    if "data" in data:
        config.data = DataConfig(
            data_dir=data["data"].get("data_dir", config.data.data_dir),
        )

    _apply_web_config(config, data)
    _apply_search_config(config, data)
    _apply_topics_config(config, data)
    _apply_daily_update_config(config, data)

    if "database" in data:
        config.database = DatabaseConfig(
            url=data["database"].get("url", config.database.url),
        )

    _apply_llm_configs(config, data)

    return config


def add_config_args(parser: argparse.ArgumentParser) -> None:
    """Add common configuration arguments to an argument parser.

    Note: Only adds arguments that don't already exist in the parser.
    """
    # Get existing argument names to avoid conflicts
    existing_args = set()
    for action in parser._actions:
        existing_args.update(action.option_strings)

    if "--config" not in existing_args:
        parser.add_argument(
            "--config",
            type=str,
            help="Path to configuration file (default: config.yaml)",
        )
    if "--notification-email" not in existing_args:
        parser.add_argument(
            "--notification-email",
            type=str,
            help="Email address for notifications",
        )
    if "--credentials-file" not in existing_args:
        parser.add_argument(
            "--credentials-file",
            type=str,
            help="Path to Gmail OAuth credentials file",
        )
    if "--token-file" not in existing_args:
        parser.add_argument(
            "--token-file",
            type=str,
            help="Path to Gmail OAuth token file",
        )
    if "--db-path" not in existing_args:
        parser.add_argument(
            "--db-path",
            type=str,
            help="Path to database file",
        )
    if "--data-dir" not in existing_args:
        parser.add_argument(
            "--data-dir",
            type=str,
            help="Directory for data files",
        )


def get_config(args: Optional[argparse.Namespace] = None) -> Config:
    """
    Get configuration, loading from file and applying CLI overrides.

    Args:
        args: Parsed command-line arguments (optional)

    Returns:
        Config object with all settings
    """
    # Find and load config file
    config_path = None
    if args and hasattr(args, "config") and args.config:
        config_path = args.config
    else:
        config_path = find_config_file()

    if config_path and os.path.exists(config_path):
        data = load_config_from_file(config_path)
        config = create_config_from_dict(data)
        config._config_file = config_path
    else:
        config = Config()

    # Apply CLI overrides
    if args:
        if hasattr(args, "notification_email") and args.notification_email:
            config.notification_email = args.notification_email
        if hasattr(args, "credentials_file") and args.credentials_file:
            config.gmail.credentials_file = args.credentials_file
        if hasattr(args, "token_file") and args.token_file:
            config.gmail.token_file = args.token_file
        if hasattr(args, "db_path") and args.db_path:
            # Legacy: db_path is no longer used (PostgreSQL via config.yaml)
            # Just set the data_dir from the path for backwards compatibility
            config.data.data_dir = os.path.dirname(args.db_path)
        if hasattr(args, "data_dir") and args.data_dir:
            config.data.data_dir = args.data_dir

    return config


# Singleton instance for easy access
_config_instance: Optional[Config] = None


def init_config(args: Optional[argparse.Namespace] = None) -> Config:
    """Initialize the global config instance."""
    global _config_instance
    _config_instance = get_config(args)
    return _config_instance


def config() -> Config:
    """Get the global config instance (initializes with defaults if not set)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance


if __name__ == "__main__":
    # Test configuration loading
    cfg = get_config()
    print(f"Config file: {cfg._config_file or '(defaults)'}")
    print(f"Notification email: {cfg.notification_email or '(not set)'}")
    print(f"Website URL: {cfg.website_url}")
    print(f"Credentials path: {cfg.get_credentials_path()}")
    print(f"Token path: {cfg.get_token_path()}")
    print(f"Data dir: {cfg.get_data_dir()}")
    print(f"Database URL: {'(set)' if cfg.database.url else '(not set)'}")
