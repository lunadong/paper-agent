#!/usr/bin/env python3
"""
Extract figures from PDF papers using caption-centric heuristic detection.

This module extracts figures from academic papers by:
1. Finding all figure captions ("Figure X:" or "Figure X.")
2. Determining if each figure is single-column or full-width
3. Finding graphics above or below each caption
4. Validating that regions contain actual visual content (not just text)

Usage:
    python extract_figures.py --url "https://arxiv.org/pdf/2501.15228"
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Handle both direct execution and package import
try:
    from .util.pdf_processing import download_pdf_bytes
except ImportError:
    from util.pdf_processing import download_pdf_bytes

# Try to import PyMuPDF
try:
    import fitz

    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    Image = None
    PILLOW_AVAILABLE = False

# Directory for storing extracted figures
FIGURES_DIR = Path(__file__).parent.parent.parent / "tmp" / "figures"


@dataclass
class Caption:
    """Represents a figure caption found in the PDF."""

    fig_num: int
    page_num: int  # 0-indexed
    rect: "fitz.Rect"
    is_full_width: bool
    text: str

    @property
    def y_center(self) -> float:
        return (self.rect.y0 + self.rect.y1) / 2

    @property
    def x_center(self) -> float:
        return (self.rect.x0 + self.rect.x1) / 2


def download_pdf(pdf_url: str, timeout: int = 60) -> Optional[bytes]:
    """
    Download PDF from URL and return bytes.

    This is a wrapper around download_pdf_bytes for backward compatibility.
    """
    try:
        return download_pdf_bytes(pdf_url, max_retries=3)
    except Exception as e:
        print(f"  Error downloading PDF: {e}")
        return None


def extract_paper_id_from_url(pdf_url: str) -> str:
    """Extract a unique paper identifier from a PDF URL."""
    # Try to extract arxiv ID
    arxiv_match = re.search(r"arxiv\.org/(?:pdf|abs)/(\d+\.\d+)", pdf_url)
    if arxiv_match:
        return arxiv_match.group(1)

    # For other URLs, use the filename
    url_path = pdf_url.split("?")[0]
    filename = url_path.split("/")[-1]
    if filename:
        if filename.lower().endswith(".pdf"):
            filename = filename[:-4]
        return filename

    # Fallback: use hash of URL
    import hashlib

    return hashlib.md5(pdf_url.encode()).hexdigest()[:12]


def measure_caption_width(page, caption_rect) -> float:
    """
    Measure the actual width of caption text on the page.

    Looks at text blocks starting from the caption position to determine
    how wide the caption spans.
    """
    page_width = page.rect.width

    # Search for text in the caption region (first few lines)
    search_rect = fitz.Rect(0, caption_rect.y0 - 2, page_width, caption_rect.y0 + 50)

    blocks = page.get_text("dict", clip=search_rect)["blocks"]

    # Collect all text spans
    all_spans = []
    for block in blocks:
        if block.get("type") != 0:  # Text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span.get("bbox")
                if bbox:
                    all_spans.append((bbox[0], bbox[2]))  # (x0, x1)

    if not all_spans:
        return caption_rect.x1 - caption_rect.x0

    # Check if any span crosses the center of the page
    # This indicates a true full-width caption
    half_page = page_width / 2
    center_zone_left = half_page - 15
    center_zone_right = half_page + 15

    spans_crossing_center = [
        (x0, x1)
        for x0, x1 in all_spans
        if x0 < center_zone_left and x1 > center_zone_right
    ]

    if spans_crossing_center:
        # Full-width caption
        min_x = min(x0 for x0, x1 in all_spans)
        max_x = max(x1 for x0, x1 in all_spans)
        return max_x - min_x
    else:
        # Single-column caption - measure only column spans
        caption_x_center = (caption_rect.x0 + caption_rect.x1) / 2
        if caption_x_center < half_page:
            col_spans = [(x0, x1) for x0, x1 in all_spans if x1 < half_page + 20]
        else:
            col_spans = [(x0, x1) for x0, x1 in all_spans if x0 > half_page - 20]

        if not col_spans:
            return caption_rect.x1 - caption_rect.x0

        min_x = min(x0 for x0, x1 in col_spans)
        max_x = max(x1 for x0, x1 in col_spans)
        return max_x - min_x


def is_caption_at_line_start(page, rect, pattern: str) -> bool:
    """
    Check if a pattern appears at the start of a text line (true caption)
    vs. in the middle of a sentence (text reference).

    Returns True if this is likely a real caption.
    """
    # First, check text spans to see if any span starts with "Figure" or "Fig."
    # This is more reliable than using a clip rect which can pull in nearby text
    text_dict = page.get_text("dict")
    for block in text_dict["blocks"]:
        if block.get("type") != 0:  # Not a text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_text = span.get("text", "").strip()
                span_bbox = span.get("bbox")
                if not span_bbox:
                    continue

                # Check if this span overlaps with our rect
                span_rect = fitz.Rect(span_bbox)
                if not span_rect.intersects(rect):
                    continue

                # Check if the span text starts with "Figure" or "Fig."
                if span_text.startswith(("Figure ", "Fig. ")):
                    return True

    # Fallback: use clip rect approach but be more lenient
    check_rect = fitz.Rect(
        rect.x0 - 100,  # Look 100px to the left
        rect.y0 - 2,
        rect.x1 + 10,
        rect.y1 + 2,
    )
    text = page.get_text("text", clip=check_rect).strip()

    # Find where the pattern appears
    pattern_lower = pattern.lower()
    text_lower = text.lower()
    idx = text_lower.find(pattern_lower)

    if idx == -1:
        return False

    if idx == 0:
        # Pattern is at the very start - this is a caption
        return True

    # Check what's before the pattern
    before = text[:idx].rstrip()
    if not before:
        # Nothing meaningful before - this is a caption
        return True

    # If text before is just whitespace or newlines, it's a caption
    if not before.strip():
        return True

    # If the text before ends with common sentence-ending punctuation
    # followed by the caption, it's still a caption (new sentence)
    if before.endswith((".", "!", "?", ":")):
        return True

    # Check if "in Figure" pattern exists - this indicates a text reference
    in_figure_check = text_lower[max(0, idx - 20) : idx]
    if " in " in in_figure_check or " see " in in_figure_check:
        return False

    # Otherwise, assume it's a caption (be lenient)
    return True


def find_all_captions(doc, max_pages: int = 10) -> list[Caption]:
    """
    Find all figure captions in the document.

    Only includes captions with punctuation (colon or period) to distinguish
    from text references like "see Figure 3".
    """
    captions = []
    seen_fig_nums = set()  # Track which figures we've found

    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        page_width = page.rect.width

        # Search for caption patterns WITH punctuation
        # This filters out text references
        for fig_num in range(1, 15):  # Figures 1-14
            if fig_num in seen_fig_nums:
                continue

            # Try patterns in order of preference (colon first, then period)
            caption_rect = None

            for pattern in [
                f"Figure {fig_num}:",
                f"Fig. {fig_num}:",
                f"Figure {fig_num}.",
                f"Fig. {fig_num}.",
            ]:
                rects = page.search_for(pattern)
                for rect in rects:
                    # Validate this is a real caption (at start of line)
                    if is_caption_at_line_start(page, rect, pattern):
                        caption_rect = rect
                        break
                if caption_rect:
                    break

            if not caption_rect:
                continue

            # Measure caption width to determine if full-width or single-column
            caption_width = measure_caption_width(page, caption_rect)
            is_full_width = caption_width > page_width * 0.60

            # Extract caption text
            text_rect = fitz.Rect(
                caption_rect.x0,
                caption_rect.y0,
                page_width - 15,
                caption_rect.y0 + 80,
            )
            caption_text = page.get_text("text", clip=text_rect).strip()
            # Truncate to first sentence or two
            if len(caption_text) > 300:
                caption_text = caption_text[:300] + "..."

            captions.append(
                Caption(
                    fig_num=fig_num,
                    page_num=page_num,
                    rect=caption_rect,
                    is_full_width=is_full_width,
                    text=caption_text,
                )
            )
            seen_fig_nums.add(fig_num)

    # Sort by page, then by y position
    captions.sort(key=lambda c: (c.page_num, c.rect.y0))
    return captions


def get_column_bounds(
    caption: Caption, page_width: float, margin: float = 15
) -> tuple[float, float]:
    """
    Get the horizontal bounds for a figure based on caption position.

    Returns (x0, x1) for the search region.
    """
    if caption.is_full_width:
        return margin, page_width - margin

    half_page = page_width / 2
    if caption.x_center < half_page:
        # Left column
        return margin, half_page - 5
    else:
        # Right column
        return half_page + 5, page_width - margin


def find_vertical_bounds(
    caption: Caption,
    all_captions: list[Caption],
    page_height: float,
    margin: float = 15,
) -> tuple[float, float]:
    """
    Find vertical bounds for searching graphics.

    Uses neighboring captions on the same page (and same column for single-col)
    as boundaries.

    Returns (upper_bound, lower_bound).
    """
    upper_bound = margin
    lower_bound = page_height - margin

    page_width = 612  # Standard page width, will be updated
    half_page = page_width / 2

    for other in all_captions:
        if other.fig_num == caption.fig_num:
            continue
        if other.page_num != caption.page_num:
            continue

        # For single-column figures, only consider captions in same column
        if not caption.is_full_width:
            same_column = (
                caption.x_center < half_page and other.x_center < half_page
            ) or (caption.x_center >= half_page and other.x_center >= half_page)
            if not same_column:
                continue

        # Caption above current one
        if other.rect.y1 < caption.rect.y0:
            if other.rect.y1 > upper_bound:
                upper_bound = other.rect.y1 + 5

        # Caption below current one
        if other.rect.y0 > caption.rect.y1:
            if other.rect.y0 < lower_bound:
                lower_bound = other.rect.y0 - 5

    return upper_bound, lower_bound


def find_graphics_bounds(page, region_rect) -> Optional[tuple]:
    """
    Find the bounding box of graphics within a region.

    Looks for:
    - Embedded images
    - Vector drawings >= 20x20 pixels

    Returns (x0, y0, x1, y1) or None if no graphics found.
    """
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    found_graphics = False

    # Check vector drawings
    for d in page.get_drawings():
        d_rect = d.get("rect")
        if not d_rect or not region_rect.intersects(d_rect):
            continue
        # Skip very small drawings (likely decorations or axis lines)
        if d_rect.width < 20 or d_rect.height < 20:
            continue

        # Constrain to region
        min_x = min(min_x, max(d_rect.x0, region_rect.x0))
        min_y = min(min_y, max(d_rect.y0, region_rect.y0))
        max_x = max(max_x, min(d_rect.x1, region_rect.x1))
        max_y = max(max_y, min(d_rect.y1, region_rect.y1))
        found_graphics = True

    # Check embedded images
    for img in page.get_images(full=True):
        img_rect = page.get_image_bbox(img)
        if not img_rect or not region_rect.intersects(img_rect):
            continue

        # Constrain to region
        min_x = min(min_x, max(img_rect.x0, region_rect.x0))
        min_y = min(min_y, max(img_rect.y0, region_rect.y0))
        max_x = max(max_x, min(img_rect.x1, region_rect.x1))
        max_y = max(max_y, min(img_rect.y1, region_rect.y1))
        found_graphics = True

    if not found_graphics:
        return None

    return (min_x, min_y, max_x, max_y)


def count_visual_richness(page, rect) -> tuple[int, int]:
    """
    Count visual elements in a region.

    Returns (num_colors, num_images).
    """
    colors = set()
    num_images = 0

    # Count colors from drawings
    for d in page.get_drawings():
        d_rect = d.get("rect")
        if not d_rect or not rect.intersects(d_rect):
            continue

        fill = d.get("fill")
        if fill:
            colors.add(tuple(round(c, 2) for c in fill))

        stroke = d.get("color")
        if stroke:
            colors.add(tuple(round(c, 2) for c in stroke))

    # Count images
    for img in page.get_images(full=True):
        img_rect = page.get_image_bbox(img)
        if img_rect and rect.intersects(img_rect):
            num_images += 1

    return len(colors), num_images


def is_text_heavy(page, rect) -> bool:
    """
    Check if a region is text-heavy (e.g., algorithm pseudocode).

    Text-heavy regions have many text lines but few colors.
    """
    # Get text
    text = page.get_text("text", clip=rect)
    text_lines = [line for line in text.split("\n") if line.strip()]
    num_text_lines = len(text_lines)

    # Count visual elements
    num_colors, num_images = count_visual_richness(page, rect)

    # Real figures have many colors OR embedded images
    has_rich_colors = num_colors >= 4
    has_images = num_images >= 1

    # Text-heavy: many text lines, few colors, no images
    if num_text_lines > 25 and not has_rich_colors and not has_images:
        return True

    return False


def is_table_region(page, rect) -> bool:
    """
    Check if a region is a table (grid of lines).

    Tables have many horizontal/vertical lines but no colorful fills.
    """
    horizontal_lines = 0
    vertical_lines = 0
    has_colorful_fills = False

    for d in page.get_drawings():
        d_rect = d.get("rect")
        if not d_rect or not rect.intersects(d_rect):
            continue

        width = d_rect.width
        height = d_rect.height

        if height < 3 and width > 50:
            horizontal_lines += 1
        elif width < 3 and height > 20:
            vertical_lines += 1

        fill = d.get("fill")
        if fill and fill not in [(0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5)]:
            has_colorful_fills = True

    # Tables have grid lines but no colorful fills
    is_grid = horizontal_lines >= 5 and vertical_lines >= 4
    return is_grid and not has_colorful_fills


def extract_figures_from_pdf(
    pdf_url: str,
    paper_id: str,
    output_dir: Optional[Path] = None,
    max_figures: int = 20,
    dpi: int = 200,
) -> list[dict]:
    """
    Extract figures from a PDF and save them as images.

    Args:
        pdf_url: URL to the PDF file
        paper_id: Paper ID for organizing output folder
        output_dir: Directory to save figures
        max_figures: Maximum number of figures to extract
        dpi: Resolution for rendered images

    Returns:
        List of dicts with figure info
    """
    if not PYMUPDF_AVAILABLE:
        print("  PyMuPDF not installed. Install with: pip install PyMuPDF")
        return []

    # Setup output directory
    if output_dir is None:
        output_dir = FIGURES_DIR
    paper_dir = output_dir / str(paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)

    # Download PDF
    pdf_bytes = download_pdf(pdf_url)
    if not pdf_bytes:
        return []

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_figures = []

    # Step 1: Find all captions
    captions = find_all_captions(doc)

    if not captions:
        print("  No figure captions found.")
        doc.close()
        return []

    # Step 2: Process each caption
    for caption in captions:
        if len(extracted_figures) >= max_figures:
            break

        page = doc[caption.page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        margin = 15

        # Get search bounds
        x0, x1 = get_column_bounds(caption, page_width, margin)
        upper_bound, lower_bound = find_vertical_bounds(
            caption, captions, page_height, margin
        )

        # Search for graphics above and below caption
        search_above = fitz.Rect(x0, upper_bound, x1, caption.rect.y0 - 5)
        search_below = fitz.Rect(x0, caption.rect.y1 + 5, x1, lower_bound)

        graphics_above = find_graphics_bounds(page, search_above)
        graphics_below = find_graphics_bounds(page, search_below)

        # Check if there's another caption above us on the same page
        # If so, graphics above us likely belong to that caption
        has_caption_above = False
        for other in captions:
            if other.fig_num == caption.fig_num:
                continue
            if other.page_num == caption.page_num and other.rect.y1 < caption.rect.y0:
                # Check if same column for single-column figures
                if caption.is_full_width or (
                    (
                        caption.x_center < page_width / 2
                        and other.x_center < page_width / 2
                    )
                    or (
                        caption.x_center >= page_width / 2
                        and other.x_center >= page_width / 2
                    )
                ):
                    has_caption_above = True
                    break

        # Choose which graphics to use
        fig_bounds = None
        include_caption_below = True  # Caption position relative to graphics

        if graphics_above and graphics_below:
            # Both regions have graphics
            # If there's a caption above us, prefer graphics below
            # (graphics above likely belong to the upper caption)
            if has_caption_above:
                fig_bounds = graphics_below
                include_caption_below = False
            else:
                # No caption above, pick the one with more visual content
                colors_above, images_above = count_visual_richness(
                    page, fitz.Rect(*graphics_above)
                )
                colors_below, images_below = count_visual_richness(
                    page, fitz.Rect(*graphics_below)
                )

                richness_above = colors_above + images_above * 5
                richness_below = colors_below + images_below * 5

                if richness_above >= richness_below:
                    fig_bounds = graphics_above
                    include_caption_below = True
                else:
                    fig_bounds = graphics_below
                    include_caption_below = False

        elif graphics_above:
            # Only graphics above
            if has_caption_above:
                # Check if the graphics are closer to our caption or the upper caption
                # If graphics bottom (gy1) is close to our caption top, they're likely ours
                gx0, gy0, gx1, gy1 = graphics_above
                distance_to_our_caption = caption.rect.y0 - gy1

                # Find the upper caption
                upper_caption_y1 = margin
                for other in captions:
                    if other.fig_num == caption.fig_num:
                        continue
                    if (
                        other.page_num == caption.page_num
                        and other.rect.y1 < caption.rect.y0
                    ):
                        if caption.is_full_width or (
                            (
                                caption.x_center < page_width / 2
                                and other.x_center < page_width / 2
                            )
                            or (
                                caption.x_center >= page_width / 2
                                and other.x_center >= page_width / 2
                            )
                        ):
                            upper_caption_y1 = max(upper_caption_y1, other.rect.y1)

                distance_to_upper_caption = gy0 - upper_caption_y1

                # If graphics are much closer to our caption, they're ours
                # Or if graphics start well below the upper caption
                close_to_us = distance_to_our_caption < 50
                far_from_upper = distance_to_upper_caption > 100
                if close_to_us or far_from_upper:
                    fig_bounds = graphics_above
                    include_caption_below = True
                else:
                    print(
                        f"    Skipping Figure {caption.fig_num} (graphics belong to caption above)"
                    )
                    continue
            else:
                fig_bounds = graphics_above
                include_caption_below = True

        elif graphics_below:
            fig_bounds = graphics_below
            include_caption_below = False

        else:
            print(f"    Skipping Figure {caption.fig_num} (no graphics found)")
            continue

        # Validate the graphics region
        gx0, gy0, gx1, gy1 = fig_bounds
        test_rect = fitz.Rect(gx0, gy0, gx1, gy1)

        # Check for tables
        if is_table_region(page, test_rect):
            print(f"    Skipping Figure {caption.fig_num} (appears to be a table)")
            continue

        # Check for text-heavy regions
        if is_text_heavy(page, test_rect):
            print(f"    Skipping Figure {caption.fig_num} (text-heavy)")
            continue

        # Compute final bounding box with caption
        padding = 10

        # For full-width figures, use full page width to capture complete caption
        if caption.is_full_width:
            fig_x0 = margin
            fig_x1 = page_width - margin
        else:
            fig_x0 = max(margin, gx0 - padding)
            fig_x1 = min(page_width - margin, gx1 + padding)

        if include_caption_below:
            # Graphics above, caption below
            fig_y0 = max(margin, gy0 - padding)
            # Include caption (estimate height based on text length)
            caption_height = min(60, len(caption.text) // 3)
            fig_y1 = min(page_height - margin, caption.rect.y0 + caption_height)
        else:
            # Caption above, graphics below
            fig_y0 = max(margin, caption.rect.y0 - 5)
            fig_y1 = min(page_height - margin, gy1 + padding)

        # Constrain to column if single-column figure
        if not caption.is_full_width:
            col_x0, col_x1 = get_column_bounds(caption, page_width, margin)
            fig_x0 = max(fig_x0, col_x0)
            fig_x1 = min(fig_x1, col_x1)

        # Validate size
        if fig_y1 - fig_y0 < 50 or fig_x1 - fig_x0 < 50:
            print(f"    Skipping Figure {caption.fig_num} (too small)")
            continue

        if fig_y1 - fig_y0 > page_height * 0.75:
            print(f"    Skipping Figure {caption.fig_num} (too large)")
            continue

        # Render figure
        clip_rect = fitz.Rect(fig_x0, fig_y0, fig_x1, fig_y1)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        try:
            pix = page.get_pixmap(matrix=mat, clip=clip_rect)
            filename = f"{caption.fig_num}.png"

            # Get image bytes
            if PILLOW_AVAILABLE:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img = img.convert("P", palette=Image.ADAPTIVE, colors=256)
                import io

                buffer = io.BytesIO()
                img.save(buffer, "PNG", optimize=True)
                image_bytes = buffer.getvalue()
            else:
                image_bytes = pix.tobytes("png")

            filepath = None
            # Only save to disk if output_dir was provided
            if paper_dir is not None:
                filepath = paper_dir / filename
                with open(filepath, "wb") as f:
                    f.write(image_bytes)

            col_str = "full-width" if caption.is_full_width else "single-col"
            print(
                f"    Extracted Figure {caption.fig_num} from page "
                f"{caption.page_num + 1} ({pix.width}x{pix.height}, {col_str})"
            )

            figure_info = {
                "filename": filename,
                "figure_num": caption.fig_num,
                "page": caption.page_num + 1,
                "width": pix.width,
                "height": pix.height,
                "caption": caption.text,
                "is_full_width": caption.is_full_width,
                "image_data": image_bytes,
            }
            if filepath is not None:
                figure_info["path"] = str(filepath)

            extracted_figures.append(figure_info)

        except Exception as e:
            print(f"    Error extracting Figure {caption.fig_num}: {e}")
            continue

    doc.close()

    if extracted_figures:
        if paper_dir is not None:
            print(f"  Extracted {len(extracted_figures)} figures to {paper_dir}")
        else:
            print(f"  Extracted {len(extracted_figures)} figures (in-memory only)")
    else:
        print("  No figures extracted.")

    return extracted_figures


def extract_figures_from_pdf_bytes(
    pdf_bytes: bytes,
    paper_id: str,
    output_dir: Optional[Path] = None,
    max_figures: int = 20,
    dpi: int = 200,
) -> list[dict]:
    """
    Extract figures from PDF bytes and optionally save them as images.

    This function accepts raw PDF bytes instead of downloading from
    URL, allowing the same PDF download to be used for both text and
    figure extraction.

    Args:
        pdf_bytes: Raw PDF bytes.
        paper_id: Paper ID for organizing output folder.
        output_dir: Directory to save figures. If None, figures are only
            returned in memory (with image_data bytes) and not saved to disk.
        max_figures: Maximum number of figures to extract.
        dpi: Resolution for rendered images.

    Returns:
        List of dicts with figure info. Each dict contains:
        - filename: The figure filename
        - figure_num: The figure number
        - page: Page number where figure was found
        - width/height: Image dimensions
        - caption: Figure caption text
        - is_full_width: Whether figure spans full page width
        - image_data: Raw PNG bytes (always included)
        - path: File path (only if output_dir was provided)
    """
    if not PYMUPDF_AVAILABLE:
        print("  PyMuPDF not installed. Install with: pip install PyMuPDF")
        return []

    paper_dir = None
    if output_dir is not None:
        paper_dir = output_dir / str(paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_figures = []

    captions = find_all_captions(doc)

    if not captions:
        print("  No figure captions found.")
        doc.close()
        return []

    for caption in captions:
        if len(extracted_figures) >= max_figures:
            break

        page = doc[caption.page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        margin = 15

        x0, x1 = get_column_bounds(caption, page_width, margin)
        upper_bound, lower_bound = find_vertical_bounds(
            caption, captions, page_height, margin
        )

        search_above = fitz.Rect(x0, upper_bound, x1, caption.rect.y0 - 5)
        search_below = fitz.Rect(x0, caption.rect.y1 + 5, x1, lower_bound)

        graphics_above = find_graphics_bounds(page, search_above)
        graphics_below = find_graphics_bounds(page, search_below)

        has_caption_above = False
        for other in captions:
            if other.fig_num == caption.fig_num:
                continue
            same_page = other.page_num == caption.page_num
            above_us = other.rect.y1 < caption.rect.y0
            if same_page and above_us:
                left_col = caption.x_center < page_width / 2
                other_left = other.x_center < page_width / 2
                if caption.is_full_width or (
                    (left_col and other_left)
                    or (
                        caption.x_center >= page_width / 2
                        and other.x_center >= page_width / 2
                    )
                ):
                    has_caption_above = True
                    break

        fig_bounds = None
        include_caption_below = True

        if graphics_above and graphics_below:
            if has_caption_above:
                fig_bounds = graphics_below
                include_caption_below = False
            else:
                colors_above, images_above = count_visual_richness(
                    page, fitz.Rect(*graphics_above)
                )
                colors_below, images_below = count_visual_richness(
                    page, fitz.Rect(*graphics_below)
                )

                richness_above = colors_above + images_above * 5
                richness_below = colors_below + images_below * 5

                if richness_above >= richness_below:
                    fig_bounds = graphics_above
                    include_caption_below = True
                else:
                    fig_bounds = graphics_below
                    include_caption_below = False

        elif graphics_above:
            if has_caption_above:
                gx0, gy0, gx1, gy1 = graphics_above
                distance_to_our_caption = caption.rect.y0 - gy1

                upper_caption_y1 = margin
                for other in captions:
                    if other.fig_num == caption.fig_num:
                        continue
                    if (
                        other.page_num == caption.page_num
                        and other.rect.y1 < caption.rect.y0
                    ):
                        if caption.is_full_width or (
                            (
                                caption.x_center < page_width / 2
                                and other.x_center < page_width / 2
                            )
                            or (
                                caption.x_center >= page_width / 2
                                and other.x_center >= page_width / 2
                            )
                        ):
                            upper_caption_y1 = max(upper_caption_y1, other.rect.y1)

                distance_to_upper_caption = gy0 - upper_caption_y1

                close_to_us = distance_to_our_caption < 50
                far_from_upper = distance_to_upper_caption > 100
                if close_to_us or far_from_upper:
                    fig_bounds = graphics_above
                    include_caption_below = True
                else:
                    continue
            else:
                fig_bounds = graphics_above
                include_caption_below = True

        elif graphics_below:
            fig_bounds = graphics_below
            include_caption_below = False

        else:
            continue

        gx0, gy0, gx1, gy1 = fig_bounds
        test_rect = fitz.Rect(gx0, gy0, gx1, gy1)

        if is_table_region(page, test_rect):
            continue

        if is_text_heavy(page, test_rect):
            continue

        padding = 10

        if caption.is_full_width:
            fig_x0 = margin
            fig_x1 = page_width - margin
        else:
            fig_x0 = max(margin, gx0 - padding)
            fig_x1 = min(page_width - margin, gx1 + padding)

        if include_caption_below:
            fig_y0 = max(margin, gy0 - padding)
            caption_height = min(60, len(caption.text) // 3)
            fig_y1 = min(page_height - margin, caption.rect.y0 + caption_height)
        else:
            fig_y0 = max(margin, caption.rect.y0 - 5)
            fig_y1 = min(page_height - margin, gy1 + padding)

        if not caption.is_full_width:
            col_x0, col_x1 = get_column_bounds(caption, page_width, margin)
            fig_x0 = max(fig_x0, col_x0)
            fig_x1 = min(fig_x1, col_x1)

        if fig_y1 - fig_y0 < 50 or fig_x1 - fig_x0 < 50:
            continue

        if fig_y1 - fig_y0 > page_height * 0.75:
            continue

        clip_rect = fitz.Rect(fig_x0, fig_y0, fig_x1, fig_y1)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        try:
            pix = page.get_pixmap(matrix=mat, clip=clip_rect)
            filename = f"{caption.fig_num}.png"

            # Get image bytes
            if PILLOW_AVAILABLE:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img = img.convert("P", palette=Image.ADAPTIVE, colors=256)
                import io

                buffer = io.BytesIO()
                img.save(buffer, "PNG", optimize=True)
                image_bytes = buffer.getvalue()
            else:
                image_bytes = pix.tobytes("png")

            filepath = None
            # Only save to disk if output_dir was provided
            if paper_dir is not None:
                filepath = paper_dir / filename
                with open(filepath, "wb") as f:
                    f.write(image_bytes)

            col_str = "full-width" if caption.is_full_width else "single-col"
            print(
                f"    Extracted Figure {caption.fig_num} from page "
                f"{caption.page_num + 1} ({pix.width}x{pix.height}, {col_str})"
            )

            figure_info = {
                "filename": filename,
                "figure_num": caption.fig_num,
                "page": caption.page_num + 1,
                "width": pix.width,
                "height": pix.height,
                "caption": caption.text,
                "is_full_width": caption.is_full_width,
                "image_data": image_bytes,
            }
            if filepath is not None:
                figure_info["path"] = str(filepath)

            extracted_figures.append(figure_info)

        except Exception as e:
            print(f"    Error extracting Figure {caption.fig_num}: {e}")
            continue

    doc.close()

    if extracted_figures:
        if paper_dir is not None:
            print(f"  Extracted {len(extracted_figures)} figures to {paper_dir}")
        else:
            print(f"  Extracted {len(extracted_figures)} figures (in-memory only)")
    else:
        print("  No figures extracted.")

    return extracted_figures


def extract_from_url(
    pdf_url: str,
    paper_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """Extract figures from a PDF URL."""
    if paper_id is None:
        paper_id = extract_paper_id_from_url(pdf_url)

    print(f"Extracting figures from: {pdf_url}")
    print(f"Output folder: {paper_id}")
    figures = extract_figures_from_pdf(pdf_url, paper_id, output_dir)

    if figures:
        print(f"\nExtracted {len(figures)} figures:")
        for fig in figures:
            print(
                f"  - {fig['filename']} "
                f"(page {fig['page']}, {fig['width']}x{fig['height']})"
            )
            if fig.get("caption"):
                print(f"    Caption: {fig['caption'][:60]}...")
    else:
        print("No figures extracted.")

    return figures


def extract_from_paper_id(
    paper_id: int, output_dir: Optional[Path] = None
) -> list[dict]:
    """Extract figures from a paper in the database."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from paper_db import get_connection
    except ImportError:
        print("Error: Cannot import paper_db. Run from project root.")
        return []

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, link FROM papers WHERE id = %s", (paper_id,))
    row = cursor.fetchone()

    if not row:
        print(f"Error: Paper with ID {paper_id} not found.")
        return []

    db_id, title, link = row
    print(f"Paper: {title}")
    print(f"Link: {link}")

    pdf_url = link
    if "arxiv.org/abs/" in link:
        pdf_url = link.replace("arxiv.org/abs/", "arxiv.org/pdf/") + ".pdf"

    return extract_from_url(pdf_url, str(db_id), output_dir)


def extract_batch(limit: int = 10, output_dir: Optional[Path] = None) -> None:
    """Extract figures from multiple papers in the database."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from paper_db import get_connection
    except ImportError:
        print("Error: Cannot import paper_db. Run from project root.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, link FROM papers
        WHERE link LIKE '%arxiv%'
        ORDER BY recomm_date DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cursor.fetchall()

    print(f"Processing {len(rows)} papers...")
    total_figures = 0

    for db_id, title, link in rows:
        print(f"\n--- Paper {db_id}: {title[:60]}...")

        pdf_url = link
        if "arxiv.org/abs/" in link:
            pdf_url = link.replace("arxiv.org/abs/", "arxiv.org/pdf/") + ".pdf"

        figures = extract_figures_from_pdf(pdf_url, str(db_id), output_dir)
        total_figures += len(figures)

    print(f"\n\nTotal figures extracted: {total_figures}")


def main():
    parser = argparse.ArgumentParser(description="Extract figures from PDF papers")
    parser.add_argument("--url", type=str, help="PDF URL to extract figures from")
    parser.add_argument("--paper-id", type=int, help="Paper ID from database")
    parser.add_argument("--all", action="store_true", help="Extract from all papers")
    parser.add_argument("--limit", type=int, default=10, help="Limit for batch mode")
    parser.add_argument("--output-dir", type=str, help="Output directory for figures")
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for rendering (default: 200)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else FIGURES_DIR

    if args.url:
        extract_from_url(args.url, output_dir=output_dir)
    elif args.paper_id:
        extract_from_paper_id(args.paper_id, output_dir=output_dir)
    elif args.all:
        extract_batch(args.limit, output_dir=output_dir)
    else:
        parser.print_help()
        print("\nExample:")
        print('  python extract_figures.py --url "https://arxiv.org/pdf/2501.15228"')


if __name__ == "__main__":
    main()
