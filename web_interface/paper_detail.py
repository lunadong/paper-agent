#!/usr/bin/env python3
"""
Paper Detail Page

Provides routes for viewing detailed paper summaries.
"""

import json

# Import shared database utilities
from db import get_paper_by_id, load_config
from flask import abort, Blueprint, jsonify, render_template

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
        cfg = load_config()
        if cfg and "gemini" in cfg and "model" in cfg["gemini"]:
            model = cfg["gemini"]["model"]
            # Remove "-preview" suffix if present
            if model.endswith("-preview"):
                model = model[:-8]
            return model
    except Exception:
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
    paper = get_paper_by_id(paper_id)
    if not paper:
        return None

    # Check if summary exists using summary_generated_at
    has_summary = paper.get("summary_generated_at") is not None

    # Parse summary JSON fields
    summary = {}
    if has_summary:
        if paper.get("summary_basics"):
            try:
                summary["basics"] = (
                    json.loads(paper["summary_basics"])
                    if isinstance(paper["summary_basics"], str)
                    else paper["summary_basics"]
                )
            except (json.JSONDecodeError, TypeError):
                summary["basics"] = {}

        if paper.get("summary_core"):
            try:
                summary["core"] = (
                    json.loads(paper["summary_core"])
                    if isinstance(paper["summary_core"], str)
                    else paper["summary_core"]
                )
            except (json.JSONDecodeError, TypeError):
                summary["core"] = {}

        if paper.get("summary_methods_evidence"):
            try:
                summary["methods"] = (
                    json.loads(paper["summary_methods_evidence"])
                    if isinstance(paper["summary_methods_evidence"], str)
                    else paper["summary_methods_evidence"]
                )
            except (json.JSONDecodeError, TypeError):
                summary["methods"] = {}

        if paper.get("summary_figures"):
            try:
                summary["figures"] = (
                    json.loads(paper["summary_figures"])
                    if isinstance(paper["summary_figures"], str)
                    else paper["summary_figures"]
                )
            except (json.JSONDecodeError, TypeError):
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
        "topic": paper.get("topic"),
        "has_summary": has_summary,
        "summary_generated_at": paper.get("summary_generated_at"),
        "summary": summary,
    }


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
    paper = get_paper_with_summary(paper_id)

    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    return jsonify(paper)
