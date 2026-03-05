#!/usr/bin/env python3
"""
Paper Detail Page

Provides routes for viewing detailed paper summaries.
"""

import json
import re
from typing import Optional

# Import shared database utilities
from db import (
    get_paper_by_id,
    get_paper_image_data,
    get_paper_images,
    increment_page_view,
    load_config,
)
from flask import abort, Blueprint, jsonify, render_template, Response

# Create Blueprint
paper_detail_bp = Blueprint(
    "paper_detail",
    __name__,
    template_folder="templates",
    static_folder="static",
)


def bold_before_colon(text: str) -> str:
    """
    Make text before the first colon bold.

    Examples:
        "Real-world impact: Over-personalized..." -> "<strong>Real-world impact:</strong> Over-personalized..."
        "vs. Constitutional AI / RLHF (not cited in paper): While..." -> "<strong>vs. Constitutional AI / RLHF (not cited in paper):</strong> While..."
        "No colon here" -> "No colon here"
    """
    if not text or ":" not in text:
        return text

    # Only bold if the colon appears in the first 100 characters (likely a label)
    # and there's content after the colon
    first_colon = text.find(":")
    if first_colon > 0 and first_colon < 100 and first_colon < len(text) - 1:
        return f"<strong>{text[: first_colon + 1]}</strong>{text[first_colon + 1 :]}"
    return text


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


def _parse_json_field(value, default=None):
    """Parse JSON field, handling both string and dict inputs."""
    if default is None:
        default = {}
    if not value:
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return default


# Register custom Jinja2 filter
@paper_detail_bp.app_template_filter("extract_fig_num")
def extract_fig_num_filter(value):
    """Jinja2 filter to extract figure number from figure_id."""
    return extract_figure_number(value)


@paper_detail_bp.app_template_filter("replace_colon_bold")
def replace_colon_bold_filter(value):
    """Jinja2 filter to make text before the first colon bold."""
    return bold_before_colon(value)


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


def get_paper_with_summary(paper_id: int) -> Optional[dict]:
    """
    Get paper with parsed summary data.

    Args:
        paper_id: The paper's database ID

    Returns:
        Dictionary with paper data and parsed summary sections, or None if not found
    """
    paper = get_paper_by_id(paper_id)
    if not paper:
        return None

    # Check if summary exists using summary_generated_at
    has_summary = paper.get("summary_generated_at") is not None

    # Parse summary JSON fields
    summary = {}
    if has_summary:
        for field in ["basics", "core", "techniques", "experiments", "figures"]:
            summary[field] = _parse_json_field(paper.get(f"summary_{field}"), {})

    # Get paper images from database
    paper_images = get_paper_images(paper_id)

    # Build a mapping from figure_name (e.g., "1", "2") to image_id
    image_map = {}
    for img in paper_images:
        fig_name = img.get("figure_name", "")
        if fig_name:
            fig_num = extract_figure_number(fig_name)
            if fig_num:
                image_map[fig_num] = img["id"]
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
        "topics": paper.get("topics"),
        "primary_topic": paper.get("primary_topic"),
        "has_summary": has_summary,
        "summary_generated_at": paper.get("summary_generated_at"),
        "summary": summary,
        "images": paper_images,
        "image_map": image_map,
    }


@paper_detail_bp.route("/paper/<int:paper_id>")
def paper_detail(paper_id: int):
    """Render paper detail page."""
    increment_page_view("paper_detail")
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

    # Type narrowing: after abort(404), image_data is guaranteed to be non-None
    # but Pyright doesn't understand abort() never returns, so we assert
    assert image_data is not None

    # Return image as PNG (assuming all stored images are PNG)
    return Response(
        bytes(image_data["image_data"]),
        mimetype="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": (
                f"inline; filename={image_data.get('figure_name', 'figure')}.png"
            ),
        },
    )
