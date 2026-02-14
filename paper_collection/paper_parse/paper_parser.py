#!/usr/bin/python3
"""
Paper Parser Module

Provides functions for parsing Google Scholar alert emails to extract paper information.
Integrates with arXiv to fetch full abstracts and accurate dates for arXiv papers.
"""

import os
import re
import sys
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

# Add parent directory to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

from acm_fetcher import convert_acm_pdf_to_abs
from arxiv_fetcher import (
    extract_paper_info as extract_arxiv_paper_info,
    fetch_arxiv_html,
)
from gmail_client import strip_html


def extract_year_from_venue(venue):
    """
    Extract the year from a venue string.

    Examples:
        "arXiv, 1/2026" -> "2026"
        "ACM Transactions, 2025" -> "2025"
        "ICML 2024" -> "2024"
        "arXiv preprint arXiv:2601.19225, 2026" -> "2026"
        "Nature, 2023" -> "2023"
        "Unknown venue" -> None

    Args:
        venue: Venue string that may contain a year

    Returns:
        Year as string (e.g., "2026") or None if no year found
    """
    if not venue:
        return None

    # Look for 4-digit year pattern (2000-2099)
    year_match = re.search(r"\b(20\d{2})\b", venue)
    if year_match:
        return year_match.group(1)

    return None


def extract_url_from_scholar_link(link):
    """
    Extract the actual URL from a Google Scholar redirect link.

    Example:
        Input: https://scholar.google.com/scholar_url?url=https://dl.acm.org/doi/pdf/10.1145/3787466&hl=en&sa=X&...
        Output: https://dl.acm.org/doi/pdf/10.1145/3787466

    Args:
        link: Google Scholar redirect link

    Returns:
        Extracted URL or original link if not a Scholar redirect
    """
    # Check if this is a Google Scholar redirect URL
    if "scholar.google.com/scholar_url" not in link:
        return link

    try:
        parsed = urlparse(link)
        query_params = parse_qs(parsed.query)

        # Get the 'url' parameter
        if "url" in query_params:
            extracted_url = query_params["url"][0]
            return unquote(extracted_url)
    except Exception:
        pass

    return link


def extract_arxiv_url_from_link(link):
    """
    Extract arXiv URL from a Google Scholar redirect link.

    Args:
        link: Google Scholar link that may contain an arXiv URL

    Returns:
        arXiv abstract URL (https://arxiv.org/abs/...) or None if not arXiv
    """
    # Check if link contains arxiv.org
    if "arxiv.org" not in link and "arxiv" not in link.lower():
        return None

    # Try to find arxiv ID in the URL (format: YYMM.NNNNN)
    arxiv_id_match = re.search(r"(\d{4}\.\d{4,5})", link)
    if arxiv_id_match:
        arxiv_id = arxiv_id_match.group(1)
        return f"https://arxiv.org/abs/{arxiv_id}"

    # Check for direct arxiv.org/pdf/ or arxiv.org/abs/ links
    if "arxiv.org/pdf/" in link:
        # Extract ID from pdf URL
        match = re.search(r"arxiv\.org/pdf/(\d{4}\.\d{4,5})", link)
        if match:
            return f"https://arxiv.org/abs/{match.group(1)}"

    if "arxiv.org/abs/" in link:
        match = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", link)
        if match:
            return f"https://arxiv.org/abs/{match.group(1)}"

    return None


def update_arxiv_venue(venue, arxiv_date):
    """
    Update arXiv venue with the extracted date.

    Converts "arXiv preprint arXiv:2601.19225, 2026" to "arXiv, 1/2026"

    Args:
        venue: Original venue string
        arxiv_date: Date string in M/YYYY format from arXiv

    Returns:
        Updated venue string
    """
    # Check if this is an arXiv venue
    if "arxiv" not in venue.lower():
        return venue

    # Extract year from the venue (e.g., "2026")
    year_match = re.search(r"\b(20\d{2})\b", venue)
    if not year_match:
        return venue

    year = year_match.group(1)

    # If we have an arxiv_date, use the month from it
    if arxiv_date:
        # arxiv_date is in format "M/YYYY"
        return f"arXiv, {arxiv_date}"
    else:
        # Fallback: use ?? for unknown month
        return f"arXiv, ??/{year}"


def extract_acm_url_from_link(link):
    """
    Extract ACM URL from a link.

    Args:
        link: Link that may contain an ACM URL

    Returns:
        ACM abstract URL (https://dl.acm.org/doi/abs/...) or None if not ACM
    """
    # Check if link contains dl.acm.org
    if "dl.acm.org" not in link:
        return None

    # Extract the actual URL if it's a Scholar redirect
    actual_url = extract_url_from_scholar_link(link)

    # Convert PDF URL to abstract URL
    if "dl.acm.org" in actual_url:
        return convert_acm_pdf_to_abs(actual_url)

    return None


def enrich_paper_with_arxiv(paper):
    """
    Enrich a paper dict with arXiv data if it's an arXiv paper.
    For ACM papers, cleans up the link (pdf -> abs).
    For other papers, cleans up the Google Scholar redirect link.

    Updates:
    - link: Replaces with clean abstract URL
    - snippet: Replaces with full abstract (arXiv only)
    - venue: Updates to "arXiv, M/YYYY" format (arXiv only)

    Args:
        paper: Paper dictionary with title, authors, venue, snippet, link

    Returns:
        Updated paper dictionary
    """
    # Check for arXiv first
    arxiv_url = extract_arxiv_url_from_link(paper["link"])

    if arxiv_url:
        # Fetch arXiv page
        html_content = fetch_arxiv_html(arxiv_url)

        if not html_content:
            # Still update the link even if fetch failed
            paper["link"] = arxiv_url
            paper["venue"] = update_arxiv_venue(paper["venue"], None)
            return paper

        # Extract paper info from arXiv
        arxiv_info = extract_arxiv_paper_info(html_content)

        # Update paper fields
        paper["link"] = arxiv_url

        if arxiv_info["abstract"]:
            paper["snippet"] = arxiv_info["abstract"]

        paper["venue"] = update_arxiv_venue(paper["venue"], arxiv_info["date"])

        return paper

    # Check for ACM - just clean up the link (don't fetch, ACM blocks requests)
    acm_url = extract_acm_url_from_link(paper["link"])

    if acm_url:
        paper["link"] = acm_url
        return paper

    # Not arXiv or ACM - just clean up the Scholar redirect link
    paper["link"] = extract_url_from_scholar_link(paper["link"])
    return paper


def parse_scholar_papers(html_content, debug_titles=False, enrich_arxiv=True):
    """
    Parse Google Scholar alert email HTML to extract individual papers.

    HTML structure:
    - Title: in blue (typically <a> tag with specific style/class)
      May have [PDF] as a separate preceding link
    - Authors + Venue: in green (typically <font color="#006621" or similar)
      Format: "Author1, Author2 - Journal/Conference, Year"
    - Abstract snippet: regular text following the above

    Args:
        html_content: Raw HTML content from the email
        debug_titles: If True, print all detected paper titles for debugging
        enrich_arxiv: If True, fetch full abstracts from arXiv for arXiv papers

    Returns:
        List of dictionaries with paper info (title, authors, venue, snippet, link)
    """
    papers = []
    seen_titles = set()  # Track seen titles to avoid duplicates

    # Title pattern: <a href="...">Paper Title</a>
    # Match any link that could be a paper (we'll filter by title content later)
    # Capture all content inside <a> tag (including nested HTML) - we'll strip HTML later
    title_pattern = re.compile(
        r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    # Green text pattern for authors (Google uses font color="#006621" for green)
    green_pattern = re.compile(
        r'<font[^>]*color=["\']#006621["\'][^>]*>(.*?)</font>',
        re.IGNORECASE | re.DOTALL,
    )

    # Alternative green patterns
    green_span_pattern = re.compile(
        r'<span[^>]*style=["\'][^"\']*color:\s*#006621[^"\']*["\'][^>]*>(.*?)</span>',
        re.IGNORECASE | re.DOTALL,
    )

    # Fallback: author pattern in plain text (Name1, Name2 - Source, Year)
    # Matches patterns like "T Poppi, B Uzkent, A Garg - Journal, 2026"
    # or "T Zhang, K Li - arXiv preprint, 2026"
    author_text_pattern = re.compile(
        r"^([A-Z][A-Za-z\u00C0-\u017F]*\s+[A-Za-z\u00C0-\u017F]+(?:,\s*[A-Z][A-Za-z\u00C0-\u017F]*\s+[A-Za-z\u00C0-\u017F]+)*(?:,?\s*…)?)\s*-\s*(.+?,\s*\d{4})",
    )

    # Skip keywords for non-paper links
    skip_keywords = [
        "google scholar",
        "unsubscribe",
        "alert",
        "manage",
        "delete",
        "create",
        "cancel",
        "forward",
        "edit",
        "settings",
        "why this ad",
        "see all recommendations",
        "see all",
    ]

    # Find ALL title links in the entire HTML content
    # Each link with a substantial title (length > 15) is potentially a paper
    all_title_matches = list(title_pattern.finditer(html_content))

    # Filter to get only paper title links (not [PDF]/[HTML] only links)
    paper_title_matches = []
    for match in all_title_matches:
        raw_content = match.group(2) or ""  # Full content inside <a> tag

        # Strip HTML to get plain text title
        title_text = strip_html(raw_content).strip()

        # Check for and remove [PDF], [HTML], etc. prefixes
        title_text = re.sub(
            r"^\s*\[(PDF|HTML|BOOK|CITATION)\]\s*", "", title_text, flags=re.IGNORECASE
        ).strip()

        # Skip if empty or just [PDF]/[HTML]
        if not title_text:
            continue

        # Skip short titles (likely navigation links)
        if len(title_text) < 15:
            continue

        # Clean title (unescape was already done by strip_html)
        clean_title = title_text

        # Skip non-paper links (check whole words only to avoid false positives like "editing")
        title_lower = clean_title.lower()
        is_skip = False
        for kw in skip_keywords:
            # Use word boundary check to avoid substring matches
            if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
                is_skip = True
                break
        if is_skip:
            continue

        paper_title_matches.append((match, clean_title))

    if debug_titles:
        print(f"\n[DEBUG] Found {len(paper_title_matches)} potential paper titles:")
        for idx, (m, t) in enumerate(paper_title_matches):
            print(f"  {idx + 1}. {t[:80]}{'...' if len(t) > 80 else ''}")
        print()

    # Process each paper title match
    for i, (title_match, title) in enumerate(paper_title_matches):
        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        link = unescape(title_match.group(1))

        # Determine the text block for this paper:
        # From current title match to the next title match (or end of content)
        start_pos = title_match.end()
        if i + 1 < len(paper_title_matches):
            end_pos = paper_title_matches[i + 1][0].start()
        else:
            end_pos = len(html_content)

        block = html_content[start_pos:end_pos]

        # Find green text (authors + venue)
        green_match = green_pattern.search(block)
        if not green_match:
            green_match = green_span_pattern.search(block)

        authors = ""
        venue = ""
        snippet = ""

        if green_match:
            green_text = strip_html(green_match.group(1)).strip()
            # Split by " - " to separate authors from venue
            if " - " in green_text:
                parts = green_text.split(" - ", 1)
                authors = parts[0].strip()
                venue = parts[1].strip() if len(parts) > 1 else ""
            else:
                authors = green_text

            # Get snippet from text after green section
            after_green = block[green_match.end() :]
            snippet_text = strip_html(after_green).strip()
        else:
            # No green match - try to find author pattern in plain text after title
            plain_text = strip_html(block).strip()

            # Try to match author pattern at the start of the text
            author_match = author_text_pattern.search(plain_text)
            if author_match:
                authors = author_match.group(1).strip()
                venue = author_match.group(2).strip()
                snippet_text = plain_text[author_match.end() :].strip()
            else:
                # Fallback: first line might be authors
                lines = plain_text.split("\n")
                if lines and " - " in lines[0]:
                    parts = lines[0].split(" - ", 1)
                    authors = parts[0].strip()
                    venue = parts[1].strip() if len(parts) > 1 else ""
                    snippet_text = "\n".join(lines[1:]).strip()
                else:
                    snippet_text = plain_text

        # Clean up snippet
        if snippet_text:
            # Remove common footer/navigation text
            snippet_text = re.split(
                r"(Cited by|Related articles|All \d+ versions|Save|See all recommendations|"
                r"This message was sent by Google Scholar|List alerts|Cancel alert|"
                r"following new recommended articles|following new articles)",
                snippet_text,
                flags=re.IGNORECASE,
            )[0]
            snippet = snippet_text.strip()

        paper = {
            "title": title,
            "authors": authors,
            "venue": venue,
            "year": extract_year_from_venue(venue),
            "snippet": snippet,
            "link": link,
        }

        # Enrich with arXiv data if enabled
        if enrich_arxiv:
            paper = enrich_paper_with_arxiv(paper)

        papers.append(paper)

    return papers
