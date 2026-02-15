"""
Vercel Serverless Function for Paper Browser API

This module provides a Flask app compatible with Vercel's serverless functions.
Uses shared db.py module for database operations.
"""

from pathlib import Path

# Import shared database utilities
from db import (
    calculate_monthly_stats,
    calculate_topic_stats,
    filter_papers_by_date,
    filter_papers_by_topics,
    get_all_papers,
    get_similar_papers,
    get_stats,
    search_papers_keyword,
    search_papers_semantic,
)
from flask import Flask, jsonify, render_template, request

# Import paper detail blueprint
from paper_detail import paper_detail_bp

# Get the directory where this file is located
WEB_INTERFACE_DIR = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(WEB_INTERFACE_DIR / "templates"),
    static_folder=str(WEB_INTERFACE_DIR / "static"),
    static_url_path="/static",
)

# Register blueprints
app.register_blueprint(paper_detail_bp)


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

    # Apply filters
    all_papers = filter_papers_by_topics(all_papers, topics_filter)
    all_papers = filter_papers_by_date(all_papers, date_from, date_to)

    # Calculate stats
    monthly_data = calculate_monthly_stats(all_papers)
    topic_data = calculate_topic_stats(all_papers)

    # Paginate
    total_papers = len(all_papers)
    papers_per_page = 10
    total_pages = (total_papers + papers_per_page - 1) // papers_per_page

    start = (page - 1) * papers_per_page
    end = start + papers_per_page
    papers = all_papers[start:end]

    # Remove embedding from response (if present)
    for paper in papers:
        paper.pop("embedding", None)

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


# Vercel requires this
if __name__ == "__main__":
    app.run(debug=True)
