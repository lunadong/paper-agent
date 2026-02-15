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
import os
import sys

from flask import Flask, jsonify, render_template, request

# Add parent directory for config import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PARENT_DIR, "paper_collection"))

# Import shared database utilities
from db import (
    calculate_monthly_stats,
    calculate_topic_stats,
    filter_papers_by_date,
    filter_papers_by_topics,
    get_all_papers,
    get_similar_papers,
    get_stats,
    load_config,
    search_papers_keyword,
    search_papers_semantic,
)

# Import the paper detail blueprint
try:
    from web_interface.paper_detail import paper_detail_bp
except ImportError:
    from paper_detail import paper_detail_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(paper_detail_bp)


def get_papers_per_page():
    """Get papers per page from config or default."""
    cfg = load_config()
    return cfg.get("web", {}).get("papers_per_page", 10)


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
    search_mode = request.args.get("mode", "semantic", type=str)
    topics_filter = request.args.get("topics", "", type=str)

    if search:
        if search_mode == "semantic":
            all_papers = search_papers_semantic(search)
        else:
            all_papers = search_papers_keyword(search)
    else:
        all_papers = get_all_papers(order_by=sort, order_dir=order)

    # Apply filters
    all_papers = filter_papers_by_topics(all_papers, topics_filter)
    all_papers = filter_papers_by_date(all_papers, date_from, date_to)

    # Calculate stats
    monthly_data = calculate_monthly_stats(all_papers)
    topic_data = calculate_topic_stats(all_papers)

    # Paginate
    total_papers = len(all_papers)
    papers_per_page = get_papers_per_page()
    total_pages = (total_papers + papers_per_page - 1) // papers_per_page

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
    similar = get_similar_papers(paper_id, limit)
    return jsonify({"papers": similar, "source_id": paper_id})


@app.route("/api/stats")
def api_stats():
    """API endpoint for database and embedding statistics."""
    return jsonify(get_stats())


def parse_args():
    """Parse command-line arguments."""
    cfg = load_config()
    web_cfg = cfg.get("web", {})
    default_host = web_cfg.get("host", "0.0.0.0")
    default_port = web_cfg.get("port", 5001)

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
