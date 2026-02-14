#!/usr/bin/python3
"""
Paper Database Module (PostgreSQL with PGVector)

Provides functions for storing and retrieving papers from Neon PostgreSQL,
including vector similarity search using pgvector.

Usage:
    from paper_db import PaperDB

    db = PaperDB()  # Uses config.yaml settings
    db.add_paper(title="...", authors="...", venue="...", year="...",
                 abstract="...", link="...", recomm_date="...", tags="...")

    # Vector similarity search
    results = db.vector_search("retrieval augmented generation", limit=10)

    db.close()
"""

from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI model
EMBEDDING_DIM = 512  # Using OpenAI text-embedding-3-small dimensions


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


def generate_openai_embedding(text: str, api_key: str = None) -> list:
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

    def __init__(self, db_url: str = None):
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
                tags TEXT,
                topic TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                summary_basics TEXT,
                summary_core TEXT,
                summary_methods_evidence TEXT,
                summary_figures TEXT,
                summary_generated_at TEXT,
                embedding vector({EMBEDDING_DIM}),
                UNIQUE(title, link)
            )
        """)
        self.conn.commit()

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
        tags: Optional[str] = None,
        generate_embedding: bool = False,
    ) -> Optional[int]:
        """
        Add a paper to the database.

        Args:
            title: Paper title
            authors: Comma-separated list of authors
            venue: Publication venue (journal, conference, arXiv, etc.)
            year: Publication year
            abstract: Paper abstract
            link: URL to the paper
            recomm_date: Date the paper was recommended (from email)
            tags: Comma-separated tags
            generate_embedding: If True, generate and store embedding

        Returns:
            The row ID of the inserted paper, or None if it already exists
        """
        cursor = self._get_cursor()

        embedding = None
        if generate_embedding:
            text = f"{title} {abstract or ''} {authors or ''}"
            embedding = self._generate_embedding(text)

        try:
            if embedding:
                cursor.execute(
                    """
                    INSERT INTO papers (title, authors, venue, year, abstract, link, recomm_date, tags, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        tags,
                        embedding,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO papers (title, authors, venue, year, abstract, link, recomm_date, tags)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (title, link) DO NOTHING
                    RETURNING id
                """,
                    (title, authors, venue, year, abstract, link, recomm_date, tags),
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
        threshold: float = None,
        topic: str = None,
    ) -> list[dict]:
        """
        Search papers using vector similarity.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            threshold: Minimum similarity score (0-1, cosine similarity)
            topic: Optional topic filter

        Returns:
            List of paper dictionaries with similarity scores
        """
        query_embedding = self._generate_embedding(query)

        cursor = self._get_cursor()

        # Build query with optional filters
        if topic:
            cursor.execute(
                """
                SELECT *, 1 - (embedding <=> %s::vector) as similarity
                FROM papers
                WHERE embedding IS NOT NULL AND topic ILIKE %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """,
                (query_embedding, f"%{topic}%", query_embedding, limit),
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

    def find_similar_papers(self, paper_id: int, limit: int = 5) -> list[dict]:
        """
        Find papers similar to a given paper.

        Args:
            paper_id: The paper's database ID
            limit: Maximum number of results

        Returns:
            List of similar paper dictionaries with similarity scores
        """
        cursor = self._get_cursor()

        cursor.execute(
            """
            SELECT p.*, 1 - (p.embedding <=> source.embedding) as similarity
            FROM papers p, papers source
            WHERE source.id = %s
              AND p.id != %s
              AND p.embedding IS NOT NULL
              AND source.embedding IS NOT NULL
            ORDER BY p.embedding <=> source.embedding
            LIMIT %s
        """,
            (paper_id, paper_id, limit),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_embedding_stats(self) -> dict:
        """
        Get statistics about embeddings in the database.

        Returns:
            Dictionary with embedding statistics
        """
        cursor = self._get_cursor()
        cursor.execute("SELECT COUNT(*) as total FROM papers")
        total = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) as with_embedding FROM papers WHERE embedding IS NOT NULL"
        )
        with_embedding = cursor.fetchone()["with_embedding"]

        return {
            "total_papers": total,
            "papers_with_embedding": with_embedding,
            "papers_without_embedding": total - with_embedding,
            "coverage_percent": round(100 * with_embedding / total, 1)
            if total > 0
            else 0,
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

        valid_order_queries = {
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

    def get_papers_by_topic(self, topic: str) -> list[dict]:
        """
        Get papers that have a specific topic.

        Args:
            topic: Topic to search for (e.g., "RAG", "Agent")

        Returns:
            List of paper dictionaries
        """
        cursor = self._get_cursor()
        cursor.execute(
            "SELECT * FROM papers WHERE topic ILIKE %s ORDER BY created_at DESC",
            (f"%{topic}%",),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_papers_by_tag(self, tag: str) -> list[dict]:
        """
        Get papers that have a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of paper dictionaries
        """
        cursor = self._get_cursor()
        cursor.execute(
            "SELECT * FROM papers WHERE tags ILIKE %s ORDER BY created_at DESC",
            (f"%{tag}%",),
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
            **kwargs: Fields to update (title, authors, venue, abstract, link, recomm_date, tags, topic)

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
            "tags": "UPDATE papers SET tags = %s WHERE id = %s",
            "topic": "UPDATE papers SET topic = %s WHERE id = %s",
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

        The summary is stored in 4 columns corresponding to top-level sections:
        - summary_basics: JSON for "Basics" section
        - summary_core: JSON for "Core" section
        - summary_methods_evidence: JSON for "Methods_and_Evidence" section
        - summary_figures: JSON for "Figures" section

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
            "summary_methods_evidence": json.dumps(
                summary.get("Methods_and_Evidence", {})
            ),
            "summary_figures": json.dumps(summary.get("Figures", {})),
            "summary_generated_at": datetime.now().isoformat(),
        }

        set_clauses = [f"{field} = %s" for field in update_values.keys()]
        values = list(update_values.values())
        values.append(paper_id)

        query = f"UPDATE papers SET {', '.join(set_clauses)} WHERE id = %s"

        cursor = self._get_cursor()
        cursor.execute(query, values)
        self.conn.commit()
        return cursor.rowcount > 0

    def remove_tag(self, paper_id: int, tag_to_remove: str) -> bool:
        """
        Remove a specific tag from a paper's tags.

        Args:
            paper_id: The paper's database ID
            tag_to_remove: The tag to remove (case-insensitive)

        Returns:
            True if the tag was removed, False if paper not found or tag not present
        """
        paper = self.get_paper_by_id(paper_id)
        if not paper or not paper.get("tags"):
            return False

        current_tags = [t.strip() for t in paper["tags"].split(",")]
        tag_lower = tag_to_remove.lower()
        new_tags = [t for t in current_tags if t.lower() != tag_lower]

        if len(new_tags) == len(current_tags):
            return False

        new_tags_str = ", ".join(new_tags) if new_tags else None
        return self.update_paper(paper_id, tags=new_tags_str)

    def get_papers_without_summary(self, tag: str = None) -> list[dict]:
        """
        Get papers that don't have a generated summary yet.

        Args:
            tag: Optional tag to filter by

        Returns:
            List of paper dictionaries without summaries
        """
        cursor = self._get_cursor()

        if tag:
            cursor.execute(
                """SELECT * FROM papers
                   WHERE summary_generated_at IS NULL AND tags ILIKE %s
                   ORDER BY created_at DESC""",
                (f"%{tag}%",),
            )
        else:
            cursor.execute(
                """SELECT * FROM papers
                   WHERE summary_generated_at IS NULL
                   ORDER BY created_at DESC"""
            )
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
        return cursor.fetchone()["count"]

    def close(self):
        """Close the database connection."""
        self.conn.close()

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
