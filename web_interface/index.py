"""
Vercel Serverless Function for Paper Browser API

This module provides a Flask app compatible with Vercel's serverless functions.
Uses OpenAI embeddings for search queries (lightweight).
"""

import os
from datetime import datetime
from pathlib import Path

import psycopg2
from flask import Flask, jsonify, render_template, request
from psycopg2.extras import RealDictCursor

# Get the directory where this file is located
WEB_INTERFACE_DIR = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(WEB_INTERFACE_DIR / "templates"),
    static_folder=str(WEB_INTERFACE_DIR / "static"),
    static_url_path="/static",
)


def load_config():
    """Load configuration from config.yaml if available."""
    try:
        import yaml

        config_paths = [
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent / "config.yaml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, "r") as f:
                    return yaml.safe_load(f)
    except Exception:
        pass
    return {}


# Load config
_config = load_config()

# Database connection (uses Vercel environment variable or config.yaml)
DATABASE_URL = os.environ.get("DATABASE_URL") or _config.get("database", {}).get("url")

# OpenAI API key for embeddings (from environment variable or config.yaml)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or _config.get("openai", {}).get(
    "api_key"
)

# Connection pool
_conn = None


def get_db_connection():
    """Get database connection with connection pooling."""
    global _conn
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL)
    return _conn


def get_cursor():
    """Get a database cursor."""
    conn = get_db_connection()
    return conn.cursor(cursor_factory=RealDictCursor)


def generate_openai_embedding(text: str) -> list:
    """Generate embedding using OpenAI API (text-embedding-3-small)."""
    import json
    import urllib.request

    if not OPENAI_API_KEY:
        return None

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
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
    """Get the score bucket for sorting."""
    if score >= 0.5:
        return 1.0
    elif score >= 0.3:
        return round(score * 10) / 10
    else:
        return round(score * 20) / 20


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


def search_papers_semantic(query, top_k=None, score_threshold=0.15):
    """Search papers using vector similarity (pgvector with OpenAI embeddings)."""
    cursor = get_cursor()

    # Check if embeddings are available
    cursor.execute("SELECT COUNT(*) as total FROM papers WHERE embedding IS NOT NULL")
    embedding_count = cursor.fetchone()["total"]

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

    for paper in results:
        if "_score" in paper:
            del paper["_score"]

    return results


def get_all_papers(order_by="recomm_date", order_dir="DESC"):
    """Get all papers from the database."""
    cursor = get_cursor()
    valid_columns = ["recomm_date", "title", "year", "authors"]
    if order_by not in valid_columns:
        order_by = "recomm_date"
    order_dir = "DESC" if order_dir.upper() == "DESC" else "ASC"

    cursor.execute(
        f"""
        SELECT id, title, authors, venue, year, abstract, link, recomm_date, topic
        FROM papers ORDER BY {order_by} {order_dir}
    """
    )
    return [dict(row) for row in cursor.fetchall()]


@app.route("/")
def index():
    """Serve the main page."""
    return render_template("papers.html")


@app.route("/api/papers")
def api_papers():
    """API endpoint for fetching papers with pagination and search."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "", type=str)
    sort = request.args.get("sort", "recomm_date", type=str)
    order = request.args.get("order", "DESC", type=str)
    date_from = request.args.get("date_from", "", type=str)
    date_to = request.args.get("date_to", "", type=str)
    search_mode = request.args.get("mode", "semantic", type=str)
    topics_filter = request.args.get("topics", "", type=str)

    if search:
        if search_mode == "semantic":
            all_papers = search_papers_semantic(search)
        else:
            all_papers = search_papers_keyword(search)
    else:
        all_papers = get_all_papers(order_by=sort, order_dir=order)

    # Filter by topics
    if topics_filter:
        selected_topics = [t.strip() for t in topics_filter.split(",")]
        filtered_papers = []
        for paper in all_papers:
            paper_topics = paper.get("topic", "") or ""
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

    # Calculate monthly stats
    monthly_stats = {}
    for paper in all_papers:
        recomm_date = paper.get("recomm_date", "")
        if recomm_date and len(recomm_date) >= 7:
            month_key = recomm_date[:7]
            monthly_stats[month_key] = monthly_stats.get(month_key, 0) + 1

    current_month = datetime.now().strftime("%Y-%m")
    monthly_stats.pop(current_month, None)

    sorted_months = sorted(monthly_stats.keys())
    monthly_data = [{"month": m, "count": monthly_stats[m]} for m in sorted_months]

    # Calculate topic stats
    topic_stats = {}
    for paper in all_papers:
        paper_topics = paper.get("topic", "") or ""
        if paper_topics:
            for topic in paper_topics.split(","):
                topic = topic.strip()
                if topic:
                    topic_stats[topic] = topic_stats.get(topic, 0) + 1

    sorted_topics = sorted(topic_stats.items(), key=lambda x: x[1], reverse=True)
    topic_data = [{"topic": t, "count": c} for t, c in sorted_topics]

    total_papers = len(all_papers)
    papers_per_page = 10
    total_pages = (total_papers + papers_per_page - 1) // papers_per_page

    start = (page - 1) * papers_per_page
    end = start + papers_per_page
    papers = all_papers[start:end]

    # Remove embedding from response
    for paper in papers:
        if "embedding" in paper:
            del paper["embedding"]

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


# Vercel requires this
if __name__ == "__main__":
    app.run(debug=True)
