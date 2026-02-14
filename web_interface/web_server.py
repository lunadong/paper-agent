#!/usr/bin/python3
"""
Paper Browser Web Server

A Flask web server for browsing and searching papers.
Supports both keyword search (SQL ILIKE) and semantic search (pgvector).

Usage (local):
    python web_server.py
    python web_server.py --port 8080
    python web_server.py --host 127.0.0.1 --port 5000

Configuration:
    Copy config.yaml.example to config.yaml and customize settings.

Then visit: http://localhost:5001 (or your configured port)
"""

import argparse
import os
import sys
from datetime import datetime

from flask import Flask, jsonify, render_template, request

# Add parent directory for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PARENT_DIR, "paper_collection"))

from paper_db import PaperDB

app = Flask(__name__)

# Configuration (loaded lazily)
_config = None
_db = None


def get_app_config():
    """Get application configuration."""
    global _config
    if _config is None:
        try:
            from config import config

            _config = config()
        except ImportError:
            _config = None
    return _config


def get_db():
    """Get database connection (lazy initialization)."""
    global _db
    if _db is None:
        print("Connecting to PostgreSQL database...")
        _db = PaperDB()
        print("Database connected!")
    return _db


def get_papers_per_page():
    """Get papers per page from config or default."""
    cfg = get_app_config()
    if cfg:
        return cfg.web.papers_per_page
    return 10


def get_all_papers(order_by="recomm_date", order_dir="DESC"):
    """Get all papers from the database."""
    db = get_db()
    return db.get_all_papers(order_by=order_by, order_dir=order_dir)


def get_score_bucket(score):
    """Get the score bucket for sorting.

    Bucket scheme:
    - score >= 0.5: all in one bucket (1.0)
    - 0.3 <= score < 0.5: 0.1 buckets (0.3, 0.4)
    - 0.15 <= score < 0.3: 0.05 buckets (0.15, 0.20, 0.25)
    - score < 0.15: 0.05 buckets
    """
    if score >= 0.5:
        return 1.0
    elif score >= 0.3:
        return round(score * 10) / 10
    else:
        return round(score * 20) / 20


def search_papers_keyword(query):
    """Search papers by keyword (SQL ILIKE)."""
    db = get_db()
    return db.search_papers(query)


def search_papers_semantic(query, top_k=None, score_threshold=0.15):
    """Search papers using vector similarity (pgvector).

    Args:
        query: Search query string
        top_k: Maximum number of results (default: all papers)
        score_threshold: Minimum similarity score (0-1) to include a result
    """
    db = get_db()

    # Check if embeddings are available
    stats = db.get_embedding_stats()
    if stats["papers_with_embedding"] == 0:
        print("No embeddings available, falling back to keyword search")
        return search_papers_keyword(query)

    # Use pgvector search
    if top_k is None:
        top_k = stats["total_papers"]

    results = db.vector_search(query, limit=top_k, threshold=score_threshold)

    # Sort by score bucket, then by date
    for paper in results:
        paper["_score"] = paper.get("similarity", 0)

    # Step 1: Sort by date descending (secondary key)
    results.sort(key=lambda p: p.get("recomm_date") or "0000-00-00", reverse=True)

    # Step 2: Sort by score bucket descending (primary key)
    results.sort(key=lambda p: get_score_bucket(p["_score"]), reverse=True)

    # Remove internal score field
    for paper in results:
        if "_score" in paper:
            del paper["_score"]

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
    topics_filter = request.args.get("topics", "", type=str)

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

    # Remove current month (incomplete data)
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
    papers_per_page = get_papers_per_page()
    total_pages = (total_papers + papers_per_page - 1) // papers_per_page

    # Paginate
    start = (page - 1) * papers_per_page
    end = start + papers_per_page
    papers = all_papers[start:end]

    # Remove embedding from response (too large)
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
    db = get_db()

    similar = db.find_similar_papers(paper_id, limit=limit)

    # Remove embedding from response
    for paper in similar:
        if "embedding" in paper:
            del paper["embedding"]

    return jsonify({"papers": similar, "source_id": paper_id})


@app.route("/api/stats")
def api_stats():
    """API endpoint for database and embedding statistics."""
    db = get_db()
    stats = db.get_embedding_stats()
    return jsonify(stats)


def parse_args():
    """Parse command-line arguments."""
    cfg = get_app_config()
    default_host = cfg.web.host if cfg else "0.0.0.0"
    default_port = cfg.web.port if cfg else 5001

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
