"""
Shared database utilities for Paper Browser

This module provides common database and embedding functions used by both
the local development server (web_server.py) and Vercel deployment (index.py).
"""

import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Import pgvector for proper vector type handling
try:
    from pgvector.psycopg2 import register_vector
except ImportError:
    register_vector = None

# Connection pool
_conn = None
_config = None

# Cache for papers (to avoid fetching all papers on every request)
_papers_cache = None
_papers_cache_time = 0
CACHE_TTL_SECONDS = 60  # Cache papers for 60 seconds

# Common SQL columns for paper queries (reduce duplication)
PAPER_LIST_COLUMNS = """
    id, title, authors, venue, year, abstract, link, recomm_date, topics,
    CASE WHEN summary_generated_at IS NOT NULL THEN true ELSE false END as has_summary,
    primary_topic
""".strip()


def load_config():
    """Load configuration from config.yaml if available."""
    global _config
    if _config is not None:
        return _config

    try:
        import yaml

        # Use absolute path based on this file's location
        this_file = Path(__file__).resolve()
        config_paths = [
            this_file.parent.parent / "config.yaml",  # paper-agent/config.yaml
            this_file.parent / "config.yaml",  # web_interface/config.yaml
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
        _conn.autocommit = True  # Avoid transaction issues
        # Register pgvector type for proper vector handling
        if register_vector is not None:
            register_vector(_conn)
    return _conn


def get_cursor():
    """Get a database cursor with automatic reconnection on SSL drops."""
    global _conn
    max_retries = 2
    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            # Reset connection if in error state
            if conn.status != psycopg2.extensions.STATUS_READY:
                conn.rollback()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            # Only test connection on retry attempt (after a failure)
            if attempt > 0:
                cursor.execute("SELECT 1")
            return cursor
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            if attempt < max_retries - 1:
                # Force reconnection on next attempt
                try:
                    if _conn:
                        _conn.close()
                except Exception:
                    pass
                _conn = None
            else:
                raise


def execute_with_retry(query, params=None, max_retries=2):
    """Execute a query with automatic retry on connection errors."""
    global _conn
    last_error = None
    for attempt in range(max_retries):
        try:
            cursor = get_cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(
                f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}"
            )
            # Force reconnection on next attempt
            try:
                if _conn:
                    _conn.close()
            except Exception:
                pass
            _conn = None
            if attempt >= max_retries - 1:
                raise
    raise last_error


def generate_openai_embedding(text: str) -> list:
    """
    Generate embedding using OpenAI API (text-embedding-3-small, 512 dims).

    Note: This function is intentionally duplicated from paper_db.py for
    Vercel deployment independence. Keep in sync with paper_db.py version.
    """
    api_key = get_openai_api_key()
    if not api_key:
        return None

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
    """Get all papers from the database with caching."""
    global _papers_cache, _papers_cache_time

    # Check cache first
    current_time = time.time()
    if (
        _papers_cache is not None
        and (current_time - _papers_cache_time) < CACHE_TTL_SECONDS
    ):
        papers = _papers_cache
    else:
        # Fetch from database with retry on connection errors
        cursor = execute_with_retry(f"SELECT {PAPER_LIST_COLUMNS} FROM papers")
        papers = [dict(row) for row in cursor.fetchall()]
        _papers_cache = papers
        _papers_cache_time = current_time

    # Apply sorting in memory (fast since data is cached)
    valid_fields = {"created_at", "recomm_date", "title", "year", "id"}
    if order_by not in valid_fields:
        order_by = "recomm_date"
    if order_dir.upper() not in ("ASC", "DESC"):
        order_dir = "DESC"

    reverse = order_dir.upper() == "DESC"
    papers = sorted(
        papers,
        key=lambda p: (p.get(order_by) is None, p.get(order_by)),
        reverse=reverse,
    )

    return papers


def invalidate_papers_cache():
    """Invalidate the papers cache (call after database updates)."""
    global _papers_cache, _papers_cache_time
    _papers_cache = None
    _papers_cache_time = 0


def search_papers_keyword(query):
    """Search papers by keyword (SQL ILIKE)."""
    search_pattern = f"%{query}%"
    cursor = execute_with_retry(
        f"""
        SELECT {PAPER_LIST_COLUMNS}
        FROM papers
        WHERE title ILIKE %s OR abstract ILIKE %s OR authors ILIKE %s
        ORDER BY recomm_date DESC
        """,
        (search_pattern, search_pattern, search_pattern),
    )
    return [dict(row) for row in cursor.fetchall()]


def search_papers_semantic(query, top_k=None, score_threshold=0.1):
    """Search papers using vector similarity (pgvector with OpenAI embeddings).

    Args:
        query: Search query string
        top_k: Maximum number of results (None = 1000)
        score_threshold: Minimum similarity score (0-1) to include a result
    """
    try:
        # Check if embeddings are available
        cursor = execute_with_retry(
            "SELECT COUNT(*) as total FROM papers WHERE embedding IS NOT NULL"
        )
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

        # Convert embedding list to string format for PostgreSQL vector type
        # Format: '[0.1, 0.2, 0.3, ...]'
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        cursor = execute_with_retry(
            """
            SELECT id, title, authors, venue, year, abstract, link, recomm_date, topics,
                   1 - (embedding <=> %s::vector) as similarity,
                   CASE WHEN summary_generated_at IS NOT NULL THEN true ELSE false END as has_summary,
                   summary_core->>'topic_relevance' as topic_relevance_json,
                   primary_topic
            FROM papers
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (embedding_str, embedding_str, top_k),
        )

        results = []
        for row in cursor.fetchall():
            paper = dict(row)
            # Extract primary_topic from summary_core if not already set
            if not paper.get("primary_topic") and paper.get("topic_relevance_json"):
                try:
                    topic_rel = json.loads(paper["topic_relevance_json"])
                    paper["primary_topic"] = topic_rel.get("primary_topic", "")
                except (json.JSONDecodeError, TypeError):
                    paper["primary_topic"] = ""
            paper.pop("topic_relevance_json", None)
            results.append(paper)

        # Filter by threshold - use a lower threshold for semantic search
        # to ensure we return results even for less common queries
        if score_threshold:
            filtered_results = [
                r for r in results if r.get("similarity", 0) >= score_threshold
            ]
            # If threshold filters out everything, return top results anyway
            if not filtered_results and results:
                # Return top 50 results without threshold filtering
                results = results[:50]
            else:
                results = filtered_results

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

    except Exception as e:
        # If anything fails in semantic search, fall back to keyword search
        import traceback

        print(f"Semantic search error: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        print("Falling back to keyword search")
        return search_papers_keyword(query)


def get_similar_papers(paper_id, limit=5):
    """Find papers similar to the given paper."""
    # Get source paper embedding
    cursor = execute_with_retry(
        "SELECT embedding FROM papers WHERE id = %s", (paper_id,)
    )
    source = cursor.fetchone()

    if not source or not source.get("embedding"):
        return []

    # Find similar papers
    cursor = execute_with_retry(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topics,
               1 - (embedding <=> %s::vector) as similarity,
               CASE WHEN summary_generated_at IS NOT NULL THEN true ELSE false END as has_summary
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
    cursor = execute_with_retry(
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
        paper_topics = paper.get("topics", "") or ""
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
    """Calculate topic count statistics using primary_topic."""
    topic_stats = {}
    for paper in papers:
        primary_topic = paper.get("primary_topic", "") or ""
        if primary_topic:
            primary_topic = primary_topic.strip()
            if primary_topic:
                topic_stats[primary_topic] = topic_stats.get(primary_topic, 0) + 1

    # Sort by count (descending)
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)
    return [{"topic": t, "count": c} for t, c in sorted_topics]


def get_paper_by_id(paper_id):
    """Get a single paper by ID with all fields."""
    cursor = execute_with_retry(
        """
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topics,
               primary_topic, summary_generated_at, summary_basics, summary_core,
               summary_techniques, summary_experiments, summary_figures
        FROM papers WHERE id = %s
        """,
        (paper_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_paper_images(paper_id):
    """Get all images for a paper (without binary data)."""
    cursor = execute_with_retry(
        """
        SELECT id, paper_id, file_path, figure_name, caption, created_at
        FROM paper_images
        WHERE paper_id = %s
        ORDER BY id
        """,
        (paper_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_paper_image_data(image_id):
    """Get a single image's binary data by image ID."""
    cursor = execute_with_retry(
        """
        SELECT id, paper_id, image_data, figure_name
        FROM paper_images
        WHERE id = %s
        """,
        (image_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


# ============================================================================
# Page View Counter Functions
# ============================================================================

_page_views_table_initialized = False


def _ensure_page_views_table():
    """Ensure the page_views table exists and has initial values."""
    global _page_views_table_initialized
    if _page_views_table_initialized:
        return

    execute_with_retry(
        """
        CREATE TABLE IF NOT EXISTS page_views (
            page_name VARCHAR(50) PRIMARY KEY,
            view_count BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    execute_with_retry(
        """
        INSERT INTO page_views (page_name, view_count) VALUES ('main', 100)
        ON CONFLICT (page_name) DO NOTHING
        """
    )

    execute_with_retry(
        """
        INSERT INTO page_views (page_name, view_count) VALUES ('paper_detail', 50)
        ON CONFLICT (page_name) DO NOTHING
        """
    )

    _page_views_table_initialized = True


def increment_page_view(page_name: str) -> int:
    """
    Atomically increment page view count and return the new count.

    Args:
        page_name: The name of the page ('main' or 'paper_detail')

    Returns:
        The new view count after incrementing
    """
    _ensure_page_views_table()

    cursor = execute_with_retry(
        """
        UPDATE page_views
        SET view_count = view_count + 1,
            last_viewed_at = CURRENT_TIMESTAMP
        WHERE page_name = %s
        RETURNING view_count
        """,
        (page_name,),
    )
    result = cursor.fetchone()
    if result:
        return result["view_count"]

    execute_with_retry(
        """
        INSERT INTO page_views (page_name, view_count)
        VALUES (%s, 1)
        ON CONFLICT (page_name) DO UPDATE
        SET view_count = page_views.view_count + 1,
            last_viewed_at = CURRENT_TIMESTAMP
        """,
        (page_name,),
    )
    cursor = execute_with_retry(
        "SELECT view_count FROM page_views WHERE page_name = %s",
        (page_name,),
    )
    result = cursor.fetchone()
    return result["view_count"] if result else 1


def get_page_views() -> dict:
    """
    Get all page view counts with their creation dates.

    Returns:
        Dictionary with page view data:
        {
            'main_page_views': int,
            'main_page_since': str (YYYY-MM-DD),
            'paper_detail_views': int,
            'paper_detail_since': str (YYYY-MM-DD)
        }
    """
    _ensure_page_views_table()

    cursor = execute_with_retry(
        "SELECT page_name, view_count, created_at FROM page_views"
    )
    rows = cursor.fetchall()

    result = {}
    for row in rows:
        page_name = row["page_name"]
        view_count = row["view_count"]
        created_at = row["created_at"]

        if created_at:
            date_str = created_at.strftime("%Y-%m-%d")
        else:
            date_str = "unknown"

        if page_name == "main":
            result["main_page_views"] = view_count
            result["main_page_since"] = date_str
        elif page_name == "paper_detail":
            result["paper_detail_views"] = view_count
            result["paper_detail_since"] = date_str

    result.setdefault("main_page_views", 0)
    result.setdefault("main_page_since", "unknown")
    result.setdefault("paper_detail_views", 0)
    result.setdefault("paper_detail_since", "unknown")

    return result
