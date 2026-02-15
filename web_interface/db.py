"""
Shared database utilities for Paper Browser

This module provides common database and embedding functions used by both
the local development server (web_server.py) and Vercel deployment (index.py).
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Connection pool
_conn = None
_config = None


def load_config():
    """Load configuration from config.yaml if available."""
    global _config
    if _config is not None:
        return _config

    try:
        import yaml

        config_paths = [
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent / "config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, "r") as f:
                    _config = yaml.safe_load(f)
                    return _config
    except Exception:
        pass

    _config = {}
    return _config


def get_database_url():
    """Get database URL from environment or config."""
    return os.environ.get("DATABASE_URL") or load_config().get("database", {}).get(
        "url"
    )


def get_openai_api_key():
    """Get OpenAI API key from environment or config."""
    return os.environ.get("OPENAI_API_KEY") or load_config().get("openai", {}).get(
        "api_key"
    )


def get_db_connection():
    """Get database connection with connection pooling."""
    global _conn
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL not configured. Set it in config.yaml or environment."
        )
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(database_url)
    return _conn


def get_cursor():
    """Get a database cursor."""
    conn = get_db_connection()
    return conn.cursor(cursor_factory=RealDictCursor)


def generate_openai_embedding(text: str) -> list:
    """Generate embedding using OpenAI API (text-embedding-3-small, 512 dims)."""
    api_key = get_openai_api_key()
    if not api_key:
        return None

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(
        {"input": text, "model": "text-embedding-3-small", "dimensions": 512}
    ).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["data"][0]["embedding"]
    except Exception as e:
        print(f"OpenAI embedding error: {e}")
        return None


def get_score_bucket(score):
    """Get the score bucket for sorting.

    Bucket scheme:
    - score >= 0.5: all in one bucket (1.0)
    - score < 0.5: 0.1 buckets
    """
    if score >= 0.5:
        return 1.0
    else:
        return round(score * 10) / 10


def get_all_papers(order_by="recomm_date", order_dir="DESC"):
    """Get all papers from the database."""
    valid_fields = {"created_at", "recomm_date", "title", "year", "id"}
    if order_by not in valid_fields:
        order_by = "recomm_date"
    if order_dir.upper() not in ("ASC", "DESC"):
        order_dir = "DESC"

    cursor = get_cursor()
    cursor.execute(
        f"""
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic,
               CASE WHEN summary_generated_at IS NOT NULL THEN true ELSE false END as has_summary
        FROM papers ORDER BY {order_by} {order_dir}
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def search_papers_keyword(query):
    """Search papers by keyword (SQL ILIKE)."""
    cursor = get_cursor()
    search_pattern = f"%{query}%"
    cursor.execute(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic
        FROM papers
        WHERE title ILIKE %s OR abstract ILIKE %s OR authors ILIKE %s
        ORDER BY recomm_date DESC
        """,
        (search_pattern, search_pattern, search_pattern),
    )
    return [dict(row) for row in cursor.fetchall()]


def search_papers_semantic(query, top_k=None, score_threshold=0.2):
    """Search papers using vector similarity (pgvector with OpenAI embeddings).

    Args:
        query: Search query string
        top_k: Maximum number of results (None = 1000)
        score_threshold: Minimum similarity score (0-1) to include a result
    """
    cursor = get_cursor()

    # Check if embeddings are available
    cursor.execute("SELECT COUNT(*) as total FROM papers WHERE embedding IS NOT NULL")
    result = cursor.fetchone()
    embedding_count = result["total"] if result else 0

    if embedding_count == 0:
        print("No embeddings available, falling back to keyword search")
        return search_papers_keyword(query)

    # Generate query embedding using OpenAI
    query_embedding = generate_openai_embedding(query)

    if query_embedding is None:
        print("OpenAI embedding failed, falling back to keyword search")
        return search_papers_keyword(query)

    # Use pgvector search
    if top_k is None:
        top_k = 1000

    cursor.execute(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic,
               1 - (embedding <=> %s::vector) as similarity
        FROM papers
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_embedding, query_embedding, top_k),
    )

    results = [dict(row) for row in cursor.fetchall()]

    # Filter by threshold
    if score_threshold:
        results = [r for r in results if r.get("similarity", 0) >= score_threshold]

    # Sort by score bucket, then by date
    for paper in results:
        paper["_score"] = paper.get("similarity", 0)

    results.sort(key=lambda p: p.get("recomm_date") or "0000-00-00", reverse=True)
    results.sort(key=lambda p: get_score_bucket(p["_score"]), reverse=True)

    # Remove internal fields before returning
    for paper in results:
        if "_score" in paper:
            del paper["_score"]
        if "similarity" in paper:
            del paper["similarity"]

    return results


def get_similar_papers(paper_id, limit=5):
    """Find papers similar to the given paper."""
    cursor = get_cursor()

    # Get source paper embedding
    cursor.execute("SELECT embedding FROM papers WHERE id = %s", (paper_id,))
    source = cursor.fetchone()

    if not source or not source.get("embedding"):
        return []

    # Find similar papers
    cursor.execute(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic,
               1 - (embedding <=> %s::vector) as similarity
        FROM papers
        WHERE id != %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (source["embedding"], paper_id, source["embedding"], limit),
    )

    similar = [dict(row) for row in cursor.fetchall()]

    for paper in similar:
        if "embedding" in paper:
            del paper["embedding"]

    return similar


def get_stats():
    """Get database and embedding statistics."""
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT
            COUNT(*) as total_papers,
            COUNT(embedding) as papers_with_embedding,
            COUNT(*) - COUNT(embedding) as papers_without_embedding
        FROM papers
        """
    )
    stats = dict(cursor.fetchone())
    stats["coverage_percent"] = (
        round(stats["papers_with_embedding"] / stats["total_papers"] * 100, 1)
        if stats["total_papers"] > 0
        else 0
    )
    return stats


def filter_papers_by_topics(papers, topics_filter):
    """Filter papers by topics (paper must have ALL selected topics)."""
    if not topics_filter:
        return papers

    selected_topics = [t.strip() for t in topics_filter.split(",")]
    filtered = []
    for paper in papers:
        paper_topics = paper.get("topic", "") or ""
        if all(topic in paper_topics for topic in selected_topics):
            filtered.append(paper)
    return filtered


def filter_papers_by_date(papers, date_from, date_to):
    """Filter papers by date range."""
    if not date_from and not date_to:
        return papers

    filtered = []
    for paper in papers:
        recomm_date = paper.get("recomm_date", "")
        if date_from and recomm_date < date_from:
            continue
        if date_to and recomm_date > date_to:
            continue
        filtered.append(paper)
    return filtered


def calculate_monthly_stats(papers):
    """Calculate monthly paper count statistics."""
    monthly_stats = {}
    for paper in papers:
        recomm_date = paper.get("recomm_date", "")
        if recomm_date and len(recomm_date) >= 7:
            month_key = recomm_date[:7]  # "YYYY-MM"
            monthly_stats[month_key] = monthly_stats.get(month_key, 0) + 1

    # Remove current month (incomplete data)
    current_month = datetime.now().strftime("%Y-%m")
    monthly_stats.pop(current_month, None)

    # Sort by date
    sorted_months = sorted(monthly_stats.keys())
    return [{"month": m, "count": monthly_stats[m]} for m in sorted_months]


def calculate_topic_stats(papers):
    """Calculate topic count statistics."""
    topic_stats = {}
    for paper in papers:
        paper_topics = paper.get("topic", "") or ""
        if paper_topics:
            for topic in paper_topics.split(","):
                topic = topic.strip()
                if topic:
                    topic_stats[topic] = topic_stats.get(topic, 0) + 1

    # Sort by count (descending)
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)
    return [{"topic": t, "count": c} for t, c in sorted_topics]


def get_paper_by_id(paper_id):
    """Get a single paper by ID with all fields."""
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic,
               summary_generated_at, summary_basics, summary_core,
               summary_methods_evidence, summary_figures
        FROM papers WHERE id = %s
        """,
        (paper_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None
