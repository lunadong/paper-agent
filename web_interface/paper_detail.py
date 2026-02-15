#!/usr/bin/env python3
"""
Paper Detail Page

Provides routes for viewing detailed paper summaries.
"""

import json
import sys
from pathlib import Path

from flask import abort, Blueprint, render_template

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from paper_collection.paper_db import PaperDB

# Create Blueprint
paper_detail_bp = Blueprint(
    "paper_detail",
    __name__,
    template_folder="templates",
    static_folder="static",
)


def get_gemini_model():
    """Get Gemini model name from config, removing '-preview' suffix if present."""
    try:
        from paper_collection.config import config

        cfg = config()
        if cfg and hasattr(cfg, "gemini") and hasattr(cfg.gemini, "model"):
            model = cfg.gemini.model
            # Remove "-preview" suffix if present
            if model.endswith("-preview"):
                model = model[:-8]
            return model
    except ImportError:
        pass
    return "Gemini"


def get_paper_with_summary(paper_id: int) -> dict:
    """
    Get paper with parsed summary data.

    Args:
        paper_id: The paper's database ID

    Returns:
        Dictionary with paper data and parsed summary sections
    """
    db = PaperDB()
    try:
        paper = db.get_paper_by_id(paper_id)
        if not paper:
            return None

        # Check if summary exists using summary_generated_at
        has_summary = paper.get("summary_generated_at") is not None

        # Parse summary JSON fields
        summary = {}
        if has_summary:
            if paper.get("summary_basics"):
                try:
                    summary["basics"] = json.loads(paper["summary_basics"])
                except json.JSONDecodeError:
                    summary["basics"] = {}

            if paper.get("summary_core"):
                try:
                    summary["core"] = json.loads(paper["summary_core"])
                except json.JSONDecodeError:
                    summary["core"] = {}

            if paper.get("summary_methods_evidence"):
                try:
                    summary["methods"] = json.loads(paper["summary_methods_evidence"])
                except json.JSONDecodeError:
                    summary["methods"] = {}

            if paper.get("summary_figures"):
                try:
                    summary["figures"] = json.loads(paper["summary_figures"])
                except json.JSONDecodeError:
                    summary["figures"] = {}

        return {
            "id": paper["id"],
            "title": paper["title"],
            "authors": paper.get("authors"),
            "venue": paper.get("venue"),
            "year": paper.get("year"),
            "abstract": paper.get("abstract"),
            "link": paper.get("link"),
            "recomm_date": paper.get("recomm_date"),
            "tags": paper.get("tags"),
            "topic": paper.get("topic"),
            "has_summary": has_summary,
            "summary_generated_at": paper.get("summary_generated_at"),
            "summary": summary,
        }
    finally:
        db.close()


@paper_detail_bp.route("/paper/<int:paper_id>")
def paper_detail(paper_id: int):
    """Render paper detail page."""
    paper = get_paper_with_summary(paper_id)

    if not paper:
        abort(404)

    model_name = get_gemini_model()
    return render_template("paper_detail.html", paper=paper, model_name=model_name)


@paper_detail_bp.route("/api/paper/<int:paper_id>")
def api_paper_detail(paper_id: int):
    """API endpoint for paper detail data."""
    from flask import jsonify

    paper = get_paper_with_summary(paper_id)

    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    return jsonify(paper)
