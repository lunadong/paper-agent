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
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

# Project root directory (parent of paper_collection)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Config file locations (in order of preference)
CONFIG_LOCATIONS = [
    os.path.join(PROJECT_ROOT, "config.yaml"),
    os.path.join(PROJECT_ROOT, "config.yml"),
    os.path.join(os.path.expanduser("~"), ".paper_agent", "config.yaml"),
]


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
    db_file: str = "papers.db"
    index_file: str = "papers.index"
    ids_file: str = "paper_ids.json"


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

    def get_db_path(self) -> str:
        """Get absolute path to database file."""
        return os.path.join(self.get_data_dir(), self.data.db_file)

    def get_index_path(self) -> str:
        """Get absolute path to FAISS index file."""
        return os.path.join(self.get_data_dir(), self.data.index_file)

    def get_ids_path(self) -> str:
        """Get absolute path to paper IDs file."""
        return os.path.join(self.get_data_dir(), self.data.ids_file)


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


def create_config_from_dict(data: dict) -> Config:
    """Create a Config object from a dictionary."""
    config = Config()

    # Top-level settings
    if "notification_email" in data:
        config.notification_email = data["notification_email"]
    if "website_url" in data:
        config.website_url = data["website_url"]

    # Gmail settings
    if "gmail" in data:
        gmail_data = data["gmail"]
        config.gmail = GmailConfig(
            credentials_file=gmail_data.get(
                "credentials_file", config.gmail.credentials_file
            ),
            token_file=gmail_data.get("token_file", config.gmail.token_file),
            search_query=gmail_data.get("search_query", config.gmail.search_query),
        )

    # Data settings
    if "data" in data:
        data_config = data["data"]
        config.data = DataConfig(
            data_dir=data_config.get("data_dir", config.data.data_dir),
            db_file=data_config.get("db_file", config.data.db_file),
            index_file=data_config.get("index_file", config.data.index_file),
            ids_file=data_config.get("ids_file", config.data.ids_file),
        )

    # Web settings
    if "web" in data:
        web_data = data["web"]
        config.web = WebConfig(
            host=web_data.get("host", config.web.host),
            port=web_data.get("port", config.web.port),
            debug=web_data.get("debug", config.web.debug),
            papers_per_page=web_data.get("papers_per_page", config.web.papers_per_page),
        )

    # Search settings
    if "search" in data:
        search_data = data["search"]
        config.search = SearchConfig(
            model_name=search_data.get("model_name", config.search.model_name),
            score_threshold=search_data.get(
                "score_threshold", config.search.score_threshold
            ),
        )

    # Topics settings
    if "topics" in data:
        topics_data = data["topics"]
        config.topics = TopicsConfig(
            score_threshold=topics_data.get(
                "score_threshold", config.topics.score_threshold
            ),
            definitions=topics_data.get("definitions", {}),
        )

    # Daily update settings
    if "daily_update" in data:
        daily_data = data["daily_update"]
        config.daily_update = DailyUpdateConfig(
            default_days=daily_data.get(
                "default_days", config.daily_update.default_days
            ),
            max_emails=daily_data.get("max_emails", config.daily_update.max_emails),
            send_notification=daily_data.get(
                "send_notification", config.daily_update.send_notification
            ),
        )

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
            help="Path to SQLite database file",
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
            # Extract data_dir and db_file from full path
            config.data.data_dir = os.path.dirname(args.db_path)
            config.data.db_file = os.path.basename(args.db_path)
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
    print(f"Database path: {cfg.get_db_path()}")
    print(f"Index path: {cfg.get_index_path()}")
