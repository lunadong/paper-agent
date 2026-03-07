"""
Utility modules for paper collection.

This package provides shared utilities:
- config: Configuration management (config.yaml loading)
- paper_db: PostgreSQL database layer with vector search
- profile_memory: Memory profiling utilities
"""

from .config import config, get_config
from .paper_db import close_connection_pool, PaperDB

__all__ = [
    "config",
    "get_config",
    "PaperDB",
    "close_connection_pool",
]
