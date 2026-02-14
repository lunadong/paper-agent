#!/usr/bin/python3
"""
Paper Browser Web Server (Local Development)

A Flask web server for browsing and searching papers.
Uses PostgreSQL with pgvector for semantic search.

Usage (local):
    python web_server.py
    python web_server.py --port 8080
    python web_server.py --host 127.0.0.1 --port 5000

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.

Then visit: http://localhost:5001 (or your configured port)
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

import psycopg2
from flask import Flask, jsonify, render_template, request
from psycopg2.extras import RealDictCursor

# Add parent directory for config import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PARENT_DIR, "paper_collection"))

app = Flask(__name__)

# Configuration (loaded lazily)
_config = None


def get_app_config():
    """Get application configuration."""
    global _config
    if _config is None:
        try:
            from config import config

            _config = config()
        except ImportError:
            # Config module not available, use defaults
            _config = None
    return _config


def get_database_url():
    """Get database URL from config or environment."""
    cfg = get_app_config()
    if cfg and hasattr(cfg, "database") and hasattr(cfg.database, "url"):
        return cfg.database.url
    return os.environ.get("DATABASE_URL")


def get_openai_api_key():
    """Get OpenAI API key from config or environment."""
    cfg = get_app_config()
    if cfg and hasattr(cfg, "openai") and hasattr(cfg.openai, "api_key"):
        return cfg.openai.api_key
    return os.environ.get("OPENAI_API_KEY")


def get_papers_per_page():
    """Get papers per page from config or default."""
    cfg = get_app_config()
    if cfg and hasattr(cfg, "web") and hasattr(cfg.web, "papers_per_page"):
        return cfg.web.papers_per_page
    return 10


# Database connection pool
_conn = None


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
    """Generate embedding using OpenAI API (text-embedding-3-small)."""
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
    - score < 0.3: 0.1 buckets
    """
    if score >= 0.5:
        return 1.0  # All high scores in same bucket
    else:
        return round(score * 10) / 10  # 0.05 buckets


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
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic
        FROM papers ORDER BY {order_by} {order_dir}
        """
    )
    papers = [dict(row) for row in cursor.fetchall()]
    return papers


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
    papers = [dict(row) for row in cursor.fetchall()]
    return papers


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


@app.route("/")
def index():
    """Serve the main page."""
    return render_template("papers.html")


@app.route("/api/papers")
def api_papers():
    """API endpoint for fetching papers with pagination and search."""
    # Get query parameters
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "", type=str)
    sort = request.args.get("sort", "recomm_date", type=str)
    order = request.args.get("order", "DESC", type=str)
    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    search_mode = request.args.get(
        "mode", "semantic", type=str
    )  # "keyword" or "semantic"
    topics_filter = request.args.get("topics", "", type=str)  # Comma-separated topics

    if search:
        if search_mode == "semantic":
            all_papers = search_papers_semantic(search)
        else:
            all_papers = search_papers_keyword(search)
    else:
        all_papers = get_all_papers(order_by=sort, order_dir=order)

    # Filter by topics (paper must have ALL selected topics)
    if topics_filter:
        selected_topics = [t.strip() for t in topics_filter.split(",")]
        filtered_papers = []
        for paper in all_papers:
            paper_topics = paper.get("topic", "") or ""
            # Check if paper has all selected topics
            has_all = all(topic in paper_topics for topic in selected_topics)
            if has_all:
                filtered_papers.append(paper)
        all_papers = filtered_papers

    # Filter by date range
    if date_from or date_to:
        filtered_papers = []
        for paper in all_papers:
            recomm_date = paper.get("recomm_date", "")
            if date_from and recomm_date < date_from:
                continue
            if date_to and recomm_date > date_to:
                continue
            filtered_papers.append(paper)
        all_papers = filtered_papers

    # Calculate monthly stats for the filtered papers
    monthly_stats = {}
    for paper in all_papers:
        recomm_date = paper.get("recomm_date", "")
        if recomm_date and len(recomm_date) >= 7:
            month_key = recomm_date[:7]  # "YYYY-MM"
            monthly_stats[month_key] = monthly_stats.get(month_key, 0) + 1

    # Remove current month (incomplete data)
    current_month = datetime.now().strftime("%Y-%m")
    monthly_stats.pop(current_month, None)

    # Sort monthly stats by date
    sorted_months = sorted(monthly_stats.keys())
    monthly_data = [{"month": m, "count": monthly_stats[m]} for m in sorted_months]

    # Calculate topic stats for the filtered papers (for bar chart when no search)
    topic_stats = {}
    for paper in all_papers:
        paper_topics = paper.get("topic", "") or ""
        if paper_topics:
            for topic in paper_topics.split(","):
                topic = topic.strip()
                if topic:
                    topic_stats[topic] = topic_stats.get(topic, 0) + 1

    # Sort topic stats by count (descending)
    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)
    topic_data = [{"topic": t, "count": c} for t, c in sorted_topics]

    total_papers = len(all_papers)
    papers_per_page = get_papers_per_page()
    total_pages = (total_papers + papers_per_page - 1) // papers_per_page

    # Paginate
    start = (page - 1) * papers_per_page
    end = start + papers_per_page
    papers = all_papers[start:end]

    return jsonify(
        {
            "papers": papers,
            "page": page,
            "total_pages": total_pages,
            "total_papers": total_papers,
            "start": start,
            "end": min(end, total_papers),
            "search": search,
            "search_mode": search_mode,
            "sort": sort,
            "order": order,
            "date_from": date_from,
            "date_to": date_to,
            "topics": topics_filter,
            "monthly_stats": monthly_data,
            "topic_stats": topic_data,
        }
    )


@app.route("/api/similar/<int:paper_id>")
def api_similar_papers(paper_id):
    """API endpoint for finding similar papers."""
    limit = request.args.get("limit", 5, type=int)
    cursor = get_cursor()

    # Get source paper embedding
    cursor.execute("SELECT embedding FROM papers WHERE id = %s", (paper_id,))
    source = cursor.fetchone()

    if not source or not source.get("embedding"):
        return jsonify({"papers": [], "source_id": paper_id, "error": "No embedding"})

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

    return jsonify({"papers": similar, "source_id": paper_id})


@app.route("/api/stats")
def api_stats():
    """API endpoint for database and embedding statistics."""
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
    return jsonify(stats)


def parse_args():
    """Parse command-line arguments."""
    cfg = get_app_config()
    default_host = cfg.web.host if cfg and hasattr(cfg, "web") else "0.0.0.0"
    default_port = cfg.web.port if cfg and hasattr(cfg, "web") else 5001
    default_debug = cfg.web.debug if cfg and hasattr(cfg, "web") else True

    parser = argparse.ArgumentParser(description="Paper Browser web server")
    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help=f"Host to bind to (default: {default_host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"Port to bind to (default: {default_port})",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Disable debug mode",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    debug = not args.no_debug

    print("Starting Paper Browser web server...")
    print(f"Visit: http://localhost:{args.port}")
    print("Press Ctrl+C to stop\n")
    app.run(debug=debug, host=args.host, port=args.port)
