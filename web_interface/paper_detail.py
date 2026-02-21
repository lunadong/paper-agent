#!/usr/bin/env python3
"""
Paper Detail Page

Provides routes for viewing detailed paper summaries.
"""

import json
import re

# Import shared database utilities
from db import get_paper_by_id, get_paper_image_data, get_paper_images, load_config
from flask import abort, Blueprint, jsonify, render_template, Response

# Create Blueprint
paper_detail_bp = Blueprint(
    "paper_detail",
    __name__,
    template_folder="templates",
    static_folder="static",
)


def extract_figure_number(figure_id: str) -> str:
    """
    Extract the numeric part from a figure ID.

    Examples:
        "Figure 1" -> "1"
        "Table 3" -> "3"
        "1" -> "1"
        "Fig. 2a" -> "2"
    """
    if not figure_id:
        return ""
    match = re.search(r"(\d+)", str(figure_id))
    return match.group(1) if match else str(figure_id)


# Register custom Jinja2 filter
@paper_detail_bp.app_template_filter("extract_fig_num")
def extract_fig_num_filter(value):
    """Jinja2 filter to extract figure number from figure_id."""
    return extract_figure_number(value)


@paper_detail_bp.app_template_filter("is_figure")
def is_figure_filter(value):
    """
    Jinja2 filter to check if figure_id refers to an actual figure (not a table).

    Returns True for: "Figure 1", "Fig. 2", "Figure 3a", "1", "2"
    Returns False for: "Table 1", "Tab. 2", etc.
    """
    if not value:
        return False
    value_lower = str(value).lower()
    # Exclude tables
    if "table" in value_lower or "tab." in value_lower:
        return False
    return True


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

    # Get paper images from database
    paper_images = get_paper_images(paper_id)

    # Build a mapping from figure_name (e.g., "1", "2") to image_id
    image_map = {}
    for img in paper_images:
        # Extract figure number from figure_name (e.g., "Figure 1" -> "1", or just "1" -> "1")
        fig_name = img.get("figure_name", "")
        if fig_name:
            # Try to extract number from the name
            match = re.search(r"(\d+)", fig_name)
            if match:
                image_map[match.group(1)] = img["id"]
            else:
                image_map[fig_name] = img["id"]

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
        "images": paper_images,
        "image_map": image_map,
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


@paper_detail_bp.route("/api/paper/image/<int:image_id>")
def api_paper_image(image_id: int):
    """Serve a paper image from the database."""
    image_data = get_paper_image_data(image_id)

    if not image_data or not image_data.get("image_data"):
        abort(404)

    # Return image as PNG (assuming all stored images are PNG)
    return Response(
        bytes(image_data["image_data"]),
        mimetype="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f"inline; filename={image_data.get('figure_name', 'figure')}.png",
        },
    )
