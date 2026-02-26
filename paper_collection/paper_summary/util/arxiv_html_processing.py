#!/usr/bin/env python3
"""
ArXiv HTML Processing Module

Extracts text and figures from arXiv HTML pages (e.g., https://arxiv.org/html/2601.06798).
This is preferred over PDF extraction for arXiv papers as it provides cleaner text
and better figure handling.
"""

import io
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("Error: requests package not installed.")
    print("Install it with: pip install requests")
    raise

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS4_AVAILABLE = False

try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:
    Image = None
    PILLOW_AVAILABLE = False


# Retry configuration
RETRY_BASE_DELAY = 2
RETRY_MAX_DELAY = 30

# Text extraction limits
MAX_HTML_CHARS = 63000


def is_arxiv_url(url: str) -> bool:
    """
    Check if a URL is an arXiv URL.

    Args:
        url: URL to check.

    Returns:
        True if the URL is an arXiv URL, False otherwise.
    """
    return "arxiv.org" in url.lower()


def get_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Extract arXiv ID from various arXiv URL formats.

    Args:
        url: arXiv URL (PDF, abstract, or HTML).

    Returns:
        arXiv ID (e.g., "2601.06798") or None if not found.

    Examples:
        >>> get_arxiv_id_from_url("https://arxiv.org/abs/2601.06798")
        '2601.06798'
        >>> get_arxiv_id_from_url("https://arxiv.org/pdf/2601.06798.pdf")
        '2601.06798'
        >>> get_arxiv_id_from_url("https://arxiv.org/html/2601.06798")
        '2601.06798'
    """
    patterns = [
        r"arxiv\.org/abs/([0-9]+\.[0-9]+)",
        r"arxiv\.org/pdf/([0-9]+\.[0-9]+)",
        r"arxiv\.org/html/([0-9]+\.[0-9]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def get_html_url_from_arxiv_url(url: str) -> Optional[str]:
    """
    Convert any arXiv URL to its HTML version.

    Args:
        url: arXiv URL (PDF, abstract, or HTML).

    Returns:
        HTML URL (e.g., "https://arxiv.org/html/2601.06798") or None.
    """
    arxiv_id = get_arxiv_id_from_url(url)
    if arxiv_id:
        return f"https://arxiv.org/html/{arxiv_id}"
    return None


def check_html_available(arxiv_id: str, timeout: int = 10) -> bool:
    """
    Check if HTML version is available for an arXiv paper.

    Not all arXiv papers have HTML versions available.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2601.06798").
        timeout: Request timeout in seconds.

    Returns:
        True if HTML is available, False otherwise.
    """
    html_url = f"https://arxiv.org/html/{arxiv_id}"
    try:
        response = requests.head(html_url, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False


def download_html(
    url: str,
    max_retries: int = 3,
) -> str:
    """
    Download HTML content from a URL.

    Args:
        url: URL to download.
        max_retries: Maximum retry attempts.

    Returns:
        HTML content as string.

    Raises:
        Exception: If download fails after all retries.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                raise Exception("HTML not available for this paper: HTTP 404")
            elif response.status_code in {429, 503}:
                wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
                print(f"  HTTP {response.status_code}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                last_error = Exception(f"HTTP {response.status_code}")
            else:
                raise Exception(f"Failed to download HTML: HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            print(
                f"  Timeout, retrying in {wait_time}s... ({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
            last_error = Exception("Download timeout")
        except requests.exceptions.ConnectionError as e:
            wait_time = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
            print(
                f"  Connection error, retrying in {wait_time}s... "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
            last_error = e

    if last_error:
        raise last_error
    raise Exception("Failed to download HTML after retries")


def extract_text_from_html(
    html_content: str,
    max_chars: int = MAX_HTML_CHARS,
) -> str:
    """
    Extract text content from arXiv HTML.

    Args:
        html_content: Raw HTML content.
        max_chars: Maximum characters to extract.

    Returns:
        Extracted text from the HTML.
    """
    if not BS4_AVAILABLE:
        raise ImportError(
            "BeautifulSoup is required for HTML extraction.\n"
            "Install it with: pip install beautifulsoup4"
        )

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    # Extract text from the article content
    # arXiv HTML uses ltx_page_content for main content
    article = soup.find("article", class_="ltx_document")
    if not article:
        article = soup.find("div", class_="ltx_page_content")
    if not article:
        article = soup

    text_parts = []
    total_chars = 0

    # Process sections
    for section in article.find_all(["section", "div"], class_=re.compile(r"ltx_")):
        # Get section title if available
        title = section.find(["h1", "h2", "h3", "h4"], class_="ltx_title")
        if title:
            title_text = title.get_text(strip=True)
            if title_text:
                text_parts.append(f"\n=== {title_text} ===\n")
                total_chars += len(title_text) + 10

        # Get paragraphs
        for para in section.find_all("p", class_="ltx_p"):
            para_text = para.get_text(strip=True)
            if para_text:
                text_parts.append(para_text)
                total_chars += len(para_text)

                if total_chars >= max_chars:
                    print(f"  Reached {max_chars} char limit")
                    break

        if total_chars >= max_chars:
            break

    full_text = "\n\n".join(text_parts)
    print(f"  Extracted {len(full_text)} characters from HTML")
    return full_text[:max_chars]


def _convert_to_png(image_data: bytes) -> bytes:
    """
    Convert image data to PNG format if not already PNG.

    Args:
        image_data: Raw image bytes.

    Returns:
        PNG-formatted image bytes.
    """
    if not PILLOW_AVAILABLE or Image is None:
        return image_data

    try:
        img = Image.open(io.BytesIO(image_data))
        if img.format == "PNG":
            return image_data

        output = io.BytesIO()
        if img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        ):
            img.save(output, format="PNG")
        else:
            img = img.convert("RGB")
            img.save(output, format="PNG")
        return output.getvalue()
    except Exception:
        return image_data


def _download_and_save_figure(
    fig_data: dict,
    output_dir: Optional[Path],
    paper_id: Optional[str],
) -> None:
    """Download figure image, convert to PNG if needed, and optionally save to disk."""
    try:
        image_url = fig_data["image_url"]
        response = requests.get(image_url, timeout=30)
        if response.status_code != 200:
            print(
                f"  Warning: Failed to download figure {fig_data['figure_num']}: "
                f"HTTP {response.status_code} from {image_url}"
            )
            return

        image_data = _convert_to_png(response.content)
        fig_data["image_data"] = image_data

        if output_dir:
            paper_dir = output_dir / paper_id if paper_id else output_dir
            paper_dir.mkdir(parents=True, exist_ok=True)
            file_path = paper_dir / fig_data["filename"]
            file_path.write_bytes(image_data)
            fig_data["path"] = str(file_path)
    except Exception as e:
        print(f"  Warning: Could not download figure {fig_data['figure_num']}: {e}")


def _extract_figure_data(
    figure,
    idx: int,
    base_url: str,
) -> Optional[dict]:
    """Extract data from a single figure element."""
    img = figure.find("img")
    if not img or not img.get("src"):
        return None

    src = img["src"]
    if src.startswith("data:"):
        return None

    # Ensure base_url ends with "/" for proper urljoin behavior
    if not base_url.endswith("/"):
        base_url = base_url + "/"

    fig_data = {
        "figure_num": idx,
        "caption": "",
        "image_url": urljoin(base_url, src),
        "filename": f"{idx}.png",
        "path": "",
        "image_data": None,
    }

    caption = figure.find("figcaption", class_="ltx_caption")
    if caption:
        fig_data["caption"] = caption.get_text(strip=True)

    return fig_data


def extract_figures_from_html(
    html_content: str,
    base_url: str,
    paper_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
    download_images: bool = True,
) -> list[dict]:
    """
    Extract figures and their captions from arXiv HTML.

    Args:
        html_content: Raw HTML content.
        base_url: Base URL for resolving relative image paths.
        paper_id: Paper ID for organizing output.
        output_dir: Directory to save downloaded images.
        download_images: Whether to download the images.

    Returns:
        List of figure dicts with keys:
        - figure_num: Figure number
        - caption: Figure caption
        - image_url: Full URL to the image
        - filename: Generated filename
        - path: Local path if downloaded
        - image_data: Binary image data if downloaded
    """
    if not BS4_AVAILABLE:
        raise ImportError(
            "BeautifulSoup is required for HTML extraction.\n"
            "Install it with: pip install beautifulsoup4"
        )

    soup = BeautifulSoup(html_content, "html.parser")
    figures = []
    downloaded_count = 0

    for idx, figure in enumerate(soup.find_all("figure", class_="ltx_figure"), start=1):
        fig_data = _extract_figure_data(figure, idx, base_url)
        if not fig_data:
            continue

        if download_images:
            _download_and_save_figure(fig_data, output_dir, paper_id)
            if fig_data.get("image_data"):
                downloaded_count += 1

        figures.append(fig_data)

    print(f"  Found {len(figures)} figures, downloaded {downloaded_count} successfully")
    return figures


def download_arxiv_html_with_figures(
    url: str,
    paper_id: Optional[str] = None,
    max_chars: int = MAX_HTML_CHARS,
    max_retries: int = 3,
    extract_figures: bool = True,
    figures_output_dir: Optional[Path] = None,
) -> dict:
    """
    Download arXiv HTML and extract both text and figures.

    This is the main entry point for arXiv HTML processing.

    Args:
        url: arXiv URL (PDF, abstract, or HTML).
        paper_id: Paper ID for organizing output.
        max_chars: Maximum characters to extract for text.
        max_retries: Maximum retry attempts for download.
        extract_figures: Whether to extract figures.
        figures_output_dir: Directory to save extracted figures.

    Returns:
        Dictionary with:
        - text: Extracted text from the HTML
        - figures: List of extracted figure dicts (if extract_figures=True)
        - html_url: The HTML URL used
        - source: "html" to indicate source type

    Raises:
        Exception: If HTML is not available or download fails.
    """
    result = {
        "text": "",
        "figures": [],
        "html_url": "",
        "source": "html",
    }

    # Convert to HTML URL
    html_url = get_html_url_from_arxiv_url(url)
    if not html_url:
        raise Exception(f"Could not extract arXiv ID from URL: {url}")

    result["html_url"] = html_url

    if paper_id is None:
        paper_id = get_arxiv_id_from_url(url)

    print(f"Downloading arXiv HTML from: {html_url}")

    # Download HTML
    html_content = download_html(html_url, max_retries)

    # Extract text
    result["text"] = extract_text_from_html(html_content, max_chars)

    # Extract figures
    if extract_figures:
        try:
            figures = extract_figures_from_html(
                html_content=html_content,
                base_url=html_url,
                paper_id=paper_id,
                output_dir=figures_output_dir,
                download_images=True,
            )
            result["figures"] = figures
        except Exception as e:
            print(f"  Error extracting figures from HTML: {e}")

    return result
