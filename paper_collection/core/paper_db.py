#!/usr/bin/python3
"""
Paper Database Module (PostgreSQL with PGVector)

Provides functions for storing and retrieving papers from Neon PostgreSQL,
including vector similarity search using pgvector.

Usage:
    from paper_db import PaperDB

    db = PaperDB()  # Uses config.yaml settings
    db.add_paper(title="...", authors="...", venue="...", year="...",
                 abstract="...", link="...", recomm_date="...")

    # Vector similarity search
    results = db.vector_search("retrieval augmented generation", limit=10)

    db.close()
"""

from pathlib import Path
from typing import Optional, Union

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI model
EMBEDDING_DIM = 512  # Using OpenAI text-embedding-3-small dimensions


# ==============================================================================
# Connection Pool - Shared database connections for efficient batch processing
# ==============================================================================
import threading

# Class-level lock for thread-safe singleton initialization
_connection_pool_lock = threading.Lock()


class ConnectionPool:
    """
    Simple connection pool for PostgreSQL connections.

    Thread-safe singleton that manages a pool of database connections.
    """

    _instance: Optional["ConnectionPool"] = None
    _pool: Optional[pool.ThreadedConnectionPool] = None
    _lock: Optional[threading.Lock] = None

    def __new__(
        cls,
        db_url: Optional[str] = None,
        min_conn: int = 1,
        max_conn: int = 10,
    ):
        """Create or return singleton instance (thread-safe)."""
        if cls._instance is None:
            with _connection_pool_lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._lock = threading.Lock()
                    cls._pool = None
        return cls._instance

    def initialize(self, db_url: str, min_conn: int = 1, max_conn: int = 10):
        """
        Initialize the connection pool.

        Args:
            db_url: PostgreSQL connection URL
            min_conn: Minimum connections to keep open
            max_conn: Maximum connections allowed
        """
        if self._lock is None:
            raise RuntimeError("Connection pool lock not initialized")
        with self._lock:
            if self._pool is None:
                self._pool = pool.ThreadedConnectionPool(
                    minconn=min_conn,
                    maxconn=max_conn,
                    dsn=db_url,
                )

    def get_connection(self):
        """Get a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized")
        return self._pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if self._pool:
            self._pool.putconn(conn)

    def close_all(self):
        """Close all connections in the pool."""
        if self._lock is None:
            return
        with self._lock:
            if self._pool:
                self._pool.closeall()
                self._pool = None

    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self._pool is not None


# Global connection pool instance
_connection_pool: Optional[ConnectionPool] = None


def get_connection_pool() -> ConnectionPool:
    """Get the global connection pool instance."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool()
    return _connection_pool


def init_connection_pool(db_url: str, min_conn: int = 1, max_conn: int = 10):
    """
    Initialize the global connection pool.

    Args:
        db_url: PostgreSQL connection URL
        min_conn: Minimum connections to keep open
        max_conn: Maximum connections allowed
    """
    pool = get_connection_pool()
    pool.initialize(db_url, min_conn, max_conn)


def close_connection_pool():
    """Close the global connection pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.close_all()
        _connection_pool = None


# Topic definitions: tag -> full_name
# Search queries are defined in topic_tagger.py
TOPICS = {
    "Pretraining": "LLM pre-train",
    "RL": "Reinforcement learning",
    "Reasoning": "Reasoning",
    "Factuality": "Factuality, Hallucination",
    "RAG": "RAG (Retrieval-Augmented Generation)",
    "Agent": "Agentic AI",
    "P13N": "Personalization",
    "Memory": "Memory",
    "KG": "Knowledge Graph",
    "QA": "Question Answering",
    "Recommendation": "Recommendation",
    "MM": "Multi-Modal",
    "Speech": "Speech",
    "Benchmark": "Benchmark",
}


def load_db_config() -> dict:
    """Load database configuration from config.yaml."""
    try:
        import yaml

        config_paths = [
            Path(__file__).parent.parent / "config.yaml",
            Path.cwd() / "config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
                    return config

    except Exception:
        pass

    return {}


def get_openai_api_key() -> str:
    """Get OpenAI API key from config."""
    config = load_db_config()
    return config.get("openai", {}).get("api_key", "")


def generate_openai_embedding(text: str, api_key: Optional[str] = None) -> list:
    """Generate embedding using OpenAI API (text-embedding-3-small, 512 dims)."""
    import json
    import urllib.request

    if api_key is None:
        api_key = get_openai_api_key()

    if not api_key:
        raise ValueError("OpenAI API key not configured in config.yaml")

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(
        {
            "input": text[:8000],  # Truncate to avoid token limits
            "model": "text-embedding-3-small",
            "dimensions": 512,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["data"][0]["embedding"]
    except Exception as e:
        raise RuntimeError(f"OpenAI embedding error: {e}")


class PaperDB:
    """Database for storing paper information using PostgreSQL with pgvector."""

    _embedding_model = None  # Class-level cache for embedding model

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize the paper database.

        Args:
            db_url: PostgreSQL connection URL. If None, reads from config.yaml
        """
        config = load_db_config()
        self.db_url = db_url or config.get("database", {}).get("url")

        if not self.db_url:
            raise ValueError(
                "PostgreSQL URL not configured. "
                "Set it in config.yaml under database.url"
            )

        self.conn = psycopg2.connect(self.db_url)
        self.conn.autocommit = False
        self._ensure_pgvector()
        self._create_tables()

    def _ensure_pgvector(self):
        """Ensure pgvector extension is enabled."""
        cursor = self._get_cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.conn.commit()

    def _get_cursor(self):
        """Get a cursor with dict-like row access."""
        return self.conn.cursor(cursor_factory=RealDictCursor)

    def _create_tables(self):
        """Create the papers table if it doesn't exist."""
        cursor = self._get_cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS papers (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT,
                venue TEXT,
                year TEXT,
                abstract TEXT,
                link TEXT,
                recomm_date TEXT,
                topics TEXT,
                primary_topic TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                summary_basics TEXT,
                summary_core TEXT,
                summary_techniques TEXT,
                summary_experiments TEXT,
                summary_figures TEXT,
                summary_generated_at TEXT,
                embedding vector({EMBEDDING_DIM}),
                UNIQUE(title, link)
            )
        """)
        self.conn.commit()

        # Run migrations to add new columns to existing tables
        self._run_migrations()

    def _run_migrations(self):
        """Run database migrations to add new columns to existing tables."""
        cursor = self._get_cursor()

        # Check if primary_topic column exists, add if not
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'papers' AND column_name = 'primary_topic'
        """)
        if cursor.fetchone() is None:
            print("Adding primary_topic column to papers table...")
            cursor.execute("ALTER TABLE papers ADD COLUMN primary_topic TEXT")
            self.conn.commit()
            print("Migration complete: primary_topic column added")

        # Check if summary_techniques column exists, add if not
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'papers' AND column_name = 'summary_techniques'
        """)
        if cursor.fetchone() is None:
            print("Adding summary_techniques column to papers table...")
            cursor.execute("ALTER TABLE papers ADD COLUMN summary_techniques TEXT")
            self.conn.commit()
            print("Migration complete: summary_techniques column added")

        # Check if summary_experiments column exists, add if not
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'papers' AND column_name = 'summary_experiments'
        """)
        if cursor.fetchone() is None:
            print("Adding summary_experiments column to papers table...")
            cursor.execute("ALTER TABLE papers ADD COLUMN summary_experiments TEXT")
            self.conn.commit()
            print("Migration complete: summary_experiments column added")

        # Create paper_images table if it doesn't exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'paper_images'
        """)
        if cursor.fetchone() is None:
            print("Creating paper_images table...")
            cursor.execute("""
                CREATE TABLE paper_images (
                    id SERIAL PRIMARY KEY,
                    paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE,
                    file_path TEXT NOT NULL,
                    figure_name TEXT,
                    caption TEXT,
                    image_data BYTEA,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX idx_paper_images_paper_id ON paper_images(paper_id)"
            )
            self.conn.commit()
            print("Migration complete: paper_images table created")

    def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text using OpenAI API."""
        return generate_openai_embedding(text)

    def _get_paper_text(self, paper: dict) -> str:
        """Get text representation of a paper for embedding."""
        parts = []
        if paper.get("title"):
            parts.append(paper["title"])
        if paper.get("abstract"):
            parts.append(paper["abstract"])
        if paper.get("authors"):
            parts.append(paper["authors"])
        return " ".join(parts)

    def add_paper(
        self,
        title: str,
        authors: Optional[str] = None,
        venue: Optional[str] = None,
        year: Optional[str] = None,
        abstract: Optional[str] = None,
        link: Optional[str] = None,
        recomm_date: Optional[str] = None,
        generate_embedding: bool = False,
    ) -> Optional[int]:
        """
        Add a paper to the database.

        Args:
            title: Paper title (required)
            authors: Comma-separated list of authors
            venue: Publication venue (journal, conference, arXiv, etc.)
            year: Publication year
            abstract: Paper abstract
            link: URL to the paper (required)
            recomm_date: Date the paper was recommended (from email)
            generate_embedding: If True, generate and store embedding

        Returns:
            The row ID of the inserted paper, or None if:
            - Missing required fields (title or link)
            - Paper already exists (duplicate)
        """
        # Validate required fields - both title and link must be present
        if not title or not title.strip():
            print(f"  Skipping paper: missing title")
            return None
        if not link or not link.strip():
            print(f"  Skipping paper '{title[:50]}...': missing link")
            return None

        # Clean the values
        title = title.strip()
        link = link.strip()

        cursor = self._get_cursor()

        embedding = None
        if generate_embedding:
            text = f"{title} {abstract or ''} {authors or ''}"
            embedding = self._generate_embedding(text)

        try:
            if embedding:
                cursor.execute(
                    """
                    INSERT INTO papers (title, authors, venue, year, abstract, link, recomm_date, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (title, link) DO NOTHING
                    RETURNING id
                """,
                    (
                        title,
                        authors,
                        venue,
                        year,
                        abstract,
                        link,
                        recomm_date,
                        embedding,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO papers (title, authors, venue, year, abstract, link, recomm_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (title, link) DO NOTHING
                    RETURNING id
                """,
                    (title, authors, venue, year, abstract, link, recomm_date),
                )
            result = cursor.fetchone()
            self.conn.commit()
            return result["id"] if result else None

        except psycopg2.IntegrityError:
            self.conn.rollback()
            return None

    def update_embedding(self, paper_id: int) -> bool:
        """
        Generate and store embedding for a paper.

        Args:
            paper_id: The paper's database ID

        Returns:
            True if embedding was updated, False if paper not found
        """
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            return False

        text = self._get_paper_text(paper)
        embedding = self._generate_embedding(text)

        cursor = self._get_cursor()
        cursor.execute(
            "UPDATE papers SET embedding = %s WHERE id = %s",
            (embedding, paper_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update_all_embeddings(self, batch_size: int = 100) -> dict:
        """
        Generate embeddings for all papers that don't have one.

        Args:
            batch_size: Number of papers to process at a time

        Returns:
            Dictionary with counts of processed and updated papers
        """
        cursor = self._get_cursor()
        cursor.execute(
            "SELECT id, title, abstract, authors FROM papers WHERE embedding IS NULL"
        )
        papers = cursor.fetchall()

        results = {"total": len(papers), "updated": 0, "errors": 0}

        print(f"Generating embeddings for {len(papers)} papers...")

        for i, paper in enumerate(papers):
            try:
                text = self._get_paper_text(paper)
                embedding = self._generate_embedding(text)

                cursor.execute(
                    "UPDATE papers SET embedding = %s WHERE id = %s",
                    (embedding, paper["id"]),
                )
                results["updated"] += 1

                if (i + 1) % batch_size == 0:
                    self.conn.commit()
                    print(f"  Processed {i + 1}/{len(papers)}...")

            except Exception as e:
                results["errors"] += 1
                print(f"  Error for paper {paper['id']}: {e}")

        self.conn.commit()
        print(f"Done! Updated {results['updated']} embeddings.")
        return results

    def vector_search(
        self,
        query: str,
        limit: int = 10,
        threshold: Optional[float] = None,
        topics_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Search papers using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            threshold: Minimum similarity score (0-1, cosine similarity)
            topics_filter: Optional topics filter

        Returns:
            List of paper dictionaries with similarity scores
        """
        query_embedding = self._generate_embedding(query)

        cursor = self._get_cursor()

        # Build query with optional filters
        if topics_filter:
            cursor.execute(
                """
                SELECT *, 1 - (embedding <=> %s::vector) as similarity
                FROM papers
                WHERE embedding IS NOT NULL AND topics ILIKE %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """,
                (query_embedding, f"%{topics_filter}%", query_embedding, limit),
            )
        else:
            cursor.execute(
                """
                SELECT *, 1 - (embedding <=> %s::vector) as similarity
                FROM papers
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """,
                (query_embedding, query_embedding, limit),
            )

        results = [dict(row) for row in cursor.fetchall()]

        # Filter by threshold if specified
        if threshold is not None:
            results = [r for r in results if r["similarity"] >= threshold]

        return results

    def get_embedding_stats(self) -> dict:
        """
        Get statistics about embeddings in the database.

        Returns:
            Dictionary with embedding statistics
        """
        cursor = self._get_cursor()
        cursor.execute("SELECT COUNT(*) as total FROM papers")
        row = cursor.fetchone()
        total = row["total"] if row else 0

        cursor.execute(
            "SELECT COUNT(*) as with_embedding FROM papers WHERE embedding IS NOT NULL"
        )
        row = cursor.fetchone()
        with_embedding = row["with_embedding"] if row else 0

        return {
            "total_papers": total,
            "papers_with_embedding": with_embedding,
            "papers_without_embedding": total - with_embedding,
            "coverage_percent": (
                round(100 * with_embedding / total, 1) if total > 0 else 0
            ),
        }

    def get_all_papers(
        self, order_by: str = "created_at", order_dir: str = "DESC"
    ) -> list[dict]:
        """
        Get all papers from the database.

        Args:
            order_by: Field to order by (created_at, recomm_date, title, year)
            order_dir: Order direction (ASC or DESC)

        Returns:
            List of paper dictionaries
        """
        valid_fields = {"created_at", "recomm_date", "title", "year", "id"}
        if order_by not in valid_fields:
            order_by = "created_at"
        order_dir_upper = order_dir.upper()
        if order_dir_upper not in ("ASC", "DESC"):
            order_dir_upper = "DESC"

        valid_order_queries: dict[tuple[str, str], str] = {
            ("created_at", "ASC"): "SELECT * FROM papers ORDER BY created_at ASC",
            ("created_at", "DESC"): "SELECT * FROM papers ORDER BY created_at DESC",
            ("recomm_date", "ASC"): "SELECT * FROM papers ORDER BY recomm_date ASC",
            ("recomm_date", "DESC"): "SELECT * FROM papers ORDER BY recomm_date DESC",
            ("title", "ASC"): "SELECT * FROM papers ORDER BY title ASC",
            ("title", "DESC"): "SELECT * FROM papers ORDER BY title DESC",
            ("year", "ASC"): "SELECT * FROM papers ORDER BY year ASC",
            ("year", "DESC"): "SELECT * FROM papers ORDER BY year DESC",
            ("id", "ASC"): "SELECT * FROM papers ORDER BY id ASC",
            ("id", "DESC"): "SELECT * FROM papers ORDER BY id DESC",
        }

        query = valid_order_queries[(order_by, order_dir_upper)]
        cursor = self._get_cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_papers_paginated(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "DESC",
    ) -> list[dict]:
        """
        Get papers with pagination support (memory-efficient for large datasets).

        Args:
            limit: Maximum number of papers to return per page
            offset: Number of papers to skip
            order_by: Field to order by (created_at, recomm_date, title, year)
            order_dir: Order direction (ASC or DESC)

        Returns:
            List of paper dictionaries for this page
        """
        valid_fields = {"created_at", "recomm_date", "title", "year", "id"}
        if order_by not in valid_fields:
            order_by = "created_at"
        order_dir_upper = order_dir.upper()
        if order_dir_upper not in ("ASC", "DESC"):
            order_dir_upper = "DESC"

        # Use a whitelist approach for safety
        valid_order_queries: dict[tuple[str, str], str] = {
            (
                "created_at",
                "ASC",
            ): "SELECT * FROM papers ORDER BY created_at ASC LIMIT %s OFFSET %s",
            (
                "created_at",
                "DESC",
            ): "SELECT * FROM papers ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (
                "recomm_date",
                "ASC",
            ): "SELECT * FROM papers ORDER BY recomm_date ASC LIMIT %s OFFSET %s",
            (
                "recomm_date",
                "DESC",
            ): "SELECT * FROM papers ORDER BY recomm_date DESC LIMIT %s OFFSET %s",
            (
                "title",
                "ASC",
            ): "SELECT * FROM papers ORDER BY title ASC LIMIT %s OFFSET %s",
            (
                "title",
                "DESC",
            ): "SELECT * FROM papers ORDER BY title DESC LIMIT %s OFFSET %s",
            (
                "year",
                "ASC",
            ): "SELECT * FROM papers ORDER BY year ASC LIMIT %s OFFSET %s",
            (
                "year",
                "DESC",
            ): "SELECT * FROM papers ORDER BY year DESC LIMIT %s OFFSET %s",
            ("id", "ASC"): "SELECT * FROM papers ORDER BY id ASC LIMIT %s OFFSET %s",
            ("id", "DESC"): "SELECT * FROM papers ORDER BY id DESC LIMIT %s OFFSET %s",
        }

        query = valid_order_queries[(order_by, order_dir_upper)]
        cursor = self._get_cursor()
        cursor.execute(query, (limit, offset))
        return [dict(row) for row in cursor.fetchall()]

    def iter_papers(
        self,
        batch_size: int = 100,
        order_by: str = "created_at",
        order_dir: str = "DESC",
    ):
        """
        Iterate over papers in batches (generator for memory efficiency).

        Args:
            batch_size: Number of papers per batch
            order_by: Field to order by
            order_dir: Order direction

        Yields:
            Paper dictionaries one at a time
        """
        offset = 0
        while True:
            batch = self.get_papers_paginated(
                limit=batch_size,
                offset=offset,
                order_by=order_by,
                order_dir=order_dir,
            )
            if not batch:
                break
            for paper in batch:
                yield paper
            offset += batch_size

    def get_paper_count(self) -> int:
        """Get total number of papers in the database."""
        cursor = self._get_cursor()
        cursor.execute("SELECT COUNT(*) as count FROM papers")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def get_paper_by_id(self, paper_id: int) -> Optional[dict]:
        """
        Get a paper by its ID.

        Args:
            paper_id: The paper's database ID

        Returns:
            Paper dictionary or None if not found
        """
        cursor = self._get_cursor()
        cursor.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_papers_by_topics(self, topics_filter: str) -> list[dict]:
        """
        Get papers by topics.

        Args:
            topics_filter: Topics to filter by

        Returns:
            List of paper dictionaries
        """
        cursor = self._get_cursor()
        cursor.execute(
            "SELECT * FROM papers WHERE topics ILIKE %s ORDER BY created_at DESC",
            (f"%{topics_filter}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_papers(self, query: str) -> list[dict]:
        """
        Search papers by title, authors, or abstract (text search).

        Args:
            query: Search query

        Returns:
            List of matching paper dictionaries
        """
        cursor = self._get_cursor()
        cursor.execute(
            """
            SELECT * FROM papers
            WHERE title ILIKE %s OR authors ILIKE %s OR abstract ILIKE %s
            ORDER BY created_at DESC
        """,
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_paper(self, paper_id: int, **kwargs) -> bool:
        """
        Update a paper's fields.

        Args:
            paper_id: The paper's database ID
            **kwargs: Fields to update (title, authors, venue, abstract, link, recomm_date, topics, primary_topic)

        Returns:
            True if the paper was updated, False if not found
        """
        field_to_query = {
            "title": "UPDATE papers SET title = %s WHERE id = %s",
            "authors": "UPDATE papers SET authors = %s WHERE id = %s",
            "venue": "UPDATE papers SET venue = %s WHERE id = %s",
            "year": "UPDATE papers SET year = %s WHERE id = %s",
            "abstract": "UPDATE papers SET abstract = %s WHERE id = %s",
            "link": "UPDATE papers SET link = %s WHERE id = %s",
            "recomm_date": "UPDATE papers SET recomm_date = %s WHERE id = %s",
            "topics": "UPDATE papers SET topics = %s WHERE id = %s",
            "primary_topic": "UPDATE papers SET primary_topic = %s WHERE id = %s",
        }

        updates = {k: v for k, v in kwargs.items() if k in field_to_query}

        if not updates:
            return False

        cursor = self._get_cursor()
        rows_updated = 0
        for field, value in updates.items():
            cursor.execute(field_to_query[field], (value, paper_id))
            rows_updated += cursor.rowcount

        self.conn.commit()
        return rows_updated > 0

    def update_paper_summary(self, paper_id: int, summary: dict) -> bool:
        """
        Update a paper's summary fields from a generated summary JSON.

        The summary is stored in 5 columns corresponding to top-level sections:
        - summary_basics: JSON for "Basics" section
        - summary_core: JSON for "Core" section
        - summary_techniques: JSON for "Technical_details" section
        - summary_experiments: JSON for "Experiments" section
        - summary_figures: JSON for "Figures" section

        Also updates paper title from summary_basics if the current title is empty.

        Args:
            paper_id: The paper's database ID
            summary: Summary dictionary (from generate_paper_summary)

        Returns:
            True if the paper was updated, False if not found
        """
        import json
        from datetime import datetime

        update_values = {
            "summary_basics": json.dumps(summary.get("Basics", {})),
            "summary_core": json.dumps(summary.get("Core", {})),
            "summary_techniques": json.dumps(summary.get("Technical_details", {})),
            "summary_experiments": json.dumps(summary.get("Experiments", {})),
            "summary_figures": json.dumps(summary.get("Figures", {})),
            "summary_generated_at": datetime.now().isoformat(),
        }

        set_clauses = [f"{field} = %s" for field in update_values.keys()]
        values: list[Union[str, int]] = list(update_values.values())
        values.append(paper_id)

        query = f"UPDATE papers SET {', '.join(set_clauses)} WHERE id = %s"

        cursor = self._get_cursor()
        cursor.execute(query, values)
        self.conn.commit()
        updated = cursor.rowcount > 0

        if updated:
            self._backfill_from_summary_basics(paper_id, summary.get("Basics", {}))

        return updated

    def _backfill_from_summary_basics(self, paper_id: int, basics: dict) -> None:
        """
        Backfill paper metadata (title only) from summary_basics if empty.

        NOTE: Authors are NOT backfilled because arXiv-sourced authors
        (populated during paper collection) are the authoritative source.

        This handles cases where paper collection didn't get complete metadata
        (e.g., ICLR/OpenReview papers parsed from Google Scholar alerts).

        Args:
            paper_id: The paper's database ID
            basics: The Basics section from the summary
        """
        if not basics:
            return

        paper = self.get_paper_by_id(paper_id)
        if not paper:
            return

        updates = {}

        # Only backfill title if empty
        if not paper.get("title") or len(paper.get("title", "").strip()) == 0:
            title_from_summary = basics.get("title")
            if title_from_summary and isinstance(title_from_summary, str):
                updates["title"] = title_from_summary.strip()

        # NOTE: Do NOT backfill authors - arXiv authors are authoritative
        # The previous code that backfilled authors has been removed

        if updates:
            self.update_paper(paper_id, **updates)

    def remove_topic(self, paper_id: int, topic_to_remove: str) -> bool:
        """
        Remove a specific topic from a paper's topics.

        Args:
            paper_id: The paper's database ID
            topic_to_remove: The topic to remove (case-insensitive)

        Returns:
            True if the topic was removed, False if paper not found or topic not present
        """
        paper = self.get_paper_by_id(paper_id)
        if not paper or not paper.get("topics"):
            return False

        current_topics = [t.strip() for t in paper["topics"].split(",")]
        topic_lower = topic_to_remove.lower()
        new_topics = [t for t in current_topics if t.lower() != topic_lower]

        if len(new_topics) == len(current_topics):
            return False

        new_topics_str = ", ".join(new_topics) if new_topics else None
        return self.update_paper(paper_id, topics=new_topics_str)

    def get_papers_without_summary(self, topic: Optional[str] = None) -> list[dict]:
        """
        Get papers that don't have a generated summary yet.

        Args:
            topic: Optional topic to filter by

        Returns:
            List of paper dictionaries without summaries
        """
        cursor = self._get_cursor()

        if topic:
            cursor.execute(
                """SELECT * FROM papers
                   WHERE summary_generated_at IS NULL AND topics ILIKE %s
                   ORDER BY created_at DESC""",
                (f"%{topic}%",),
            )
        else:
            cursor.execute("""SELECT * FROM papers
                   WHERE summary_generated_at IS NULL
                   ORDER BY created_at DESC""")
        return [dict(row) for row in cursor.fetchall()]

    def delete_paper(self, paper_id: int) -> bool:
        """
        Delete a paper by its ID.

        Args:
            paper_id: The paper's database ID

        Returns:
            True if the paper was deleted, False if not found
        """
        cursor = self._get_cursor()
        cursor.execute("DELETE FROM papers WHERE id = %s", (paper_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def count_papers(self) -> int:
        """
        Get the total number of papers in the database.

        Returns:
            Number of papers
        """
        cursor = self._get_cursor()
        cursor.execute("SELECT COUNT(*) as count FROM papers")
        row = cursor.fetchone()
        return row["count"] if row else 0

    def close(self):
        """Close the database connection."""
        self.conn.close()

    # ==================== Paper Images Methods ====================

    def add_paper_image(
        self,
        paper_id: int,
        file_path: str,
        figure_name: Optional[str] = None,
        caption: Optional[str] = None,
        image_data: Optional[bytes] = None,
    ) -> Optional[int]:
        """
        Add an image for a paper.

        Args:
            paper_id: The paper's database ID
            file_path: Path to the image file (relative or absolute)
            figure_name: Name of the figure (e.g., "Figure 1", "Table 2")
            caption: Figure caption text
            image_data: Optional binary image data (PNG bytes)

        Returns:
            The row ID of the inserted image, or None on failure
        """
        cursor = self._get_cursor()
        try:
            cursor.execute(
                """
                INSERT INTO paper_images (paper_id, file_path, figure_name, caption, image_data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """,
                (paper_id, file_path, figure_name, caption, image_data),
            )
            result = cursor.fetchone()
            self.conn.commit()
            return result["id"] if result else None
        except Exception as e:
            print(f"Error adding paper image: {e}")
            self.conn.rollback()
            return None

    def get_paper_images(self, paper_id: int) -> list[dict]:
        """
        Get all images for a paper.

        Args:
            paper_id: The paper's database ID

        Returns:
            List of image dictionaries
        """
        cursor = self._get_cursor()
        cursor.execute(
            """
            SELECT id, paper_id, file_path, figure_name, caption, created_at
            FROM paper_images
            WHERE paper_id = %s
            ORDER BY id
        """,
            (paper_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_paper_image_with_data(self, image_id: int) -> Optional[dict]:
        """
        Get a paper image including binary data.

        Args:
            image_id: The image's database ID

        Returns:
            Image dictionary with image_data, or None if not found
        """
        cursor = self._get_cursor()
        cursor.execute(
            "SELECT * FROM paper_images WHERE id = %s",
            (image_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def delete_paper_image(self, image_id: int) -> bool:
        """
        Delete a paper image by its ID.

        Args:
            image_id: The image's database ID

        Returns:
            True if deleted, False otherwise
        """
        cursor = self._get_cursor()
        try:
            cursor.execute("DELETE FROM paper_images WHERE id = %s", (image_id,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting paper image: {e}")
            self.conn.rollback()
            return False

    def delete_paper_images(self, paper_id: int) -> int:
        """
        Delete all images for a paper.

        Args:
            paper_id: The paper's database ID

        Returns:
            Number of images deleted
        """
        cursor = self._get_cursor()
        try:
            cursor.execute("DELETE FROM paper_images WHERE paper_id = %s", (paper_id,))
            self.conn.commit()
            return cursor.rowcount
        except Exception as e:
            print(f"Error deleting paper images: {e}")
            self.conn.rollback()
            return 0

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def main():
    """Test the paper database with pgvector."""
    print("Testing Paper Database (PostgreSQL + PGVector)...\n")

    db = PaperDB()

    try:
        # Basic stats
        count = db.count_papers()
        print(f"Total papers: {count}")

        # Embedding stats
        stats = db.get_embedding_stats()
        print("\nEmbedding coverage:")
        print(f"  With embeddings: {stats['papers_with_embedding']}")
        print(f"  Without embeddings: {stats['papers_without_embedding']}")
        print(f"  Coverage: {stats['coverage_percent']}%")

        # Test vector search if embeddings exist
        if stats["papers_with_embedding"] > 0:
            print("\nVector search for 'retrieval augmented generation':")
            results = db.vector_search("retrieval augmented generation", limit=5)
            for r in results:
                sim = r.get("similarity", 0)
                print(f"  [{r['id']}] {r['title'][:50]}... (sim: {sim:.3f})")

    finally:
        db.close()

    print("\nDatabase test complete!")


if __name__ == "__main__":
    main()
