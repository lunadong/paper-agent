#!/usr/bin/python3
"""
ACM Digital Library Fetcher

Fetches HTML content from ACM Digital Library abstract pages and extracts paper metadata.

Usage:
    python acm_fetcher.py https://dl.acm.org/doi/abs/10.1145/3787466
"""

import argparse
import re
import sys

import requests


def fetch_acm_html(url):
    """
    Fetch HTML content from an ACM Digital Library abstract page.

    Args:
        url: ACM URL starting with "https://dl.acm.org/doi/"

    Returns:
        HTML content as a string, or None on error
    """
    # Validate URL format
    if not url.startswith("https://dl.acm.org/doi/"):
        raise ValueError(
            f"Invalid ACM URL. Must start with 'https://dl.acm.org/doi/'. Got: {url}"
        )

    try:
        # Use a session to handle cookies properly
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        session.headers.update(headers)

        # First request to get cookies
        response = session.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        # ACM may block automated requests - return None silently for paper enrichment
        return None


def extract_acm_doi(url):
    """
    Extract the DOI from an ACM URL.

    Args:
        url: ACM URL

    Returns:
        DOI string (e.g., "10.1145/3787466") or None if not found
    """
    # DOI pattern: 10.XXXX/XXXXXXX
    match = re.search(r"(10\.\d{4,}/[^\s&?#]+)", url)
    if match:
        return match.group(1)
    return None


def convert_acm_pdf_to_abs(url):
    """
    Convert ACM PDF URL to abstract URL.

    Example:
        Input:  https://dl.acm.org/doi/pdf/10.1145/3787466
        Output: https://dl.acm.org/doi/abs/10.1145/3787466

    Args:
        url: ACM URL (may be pdf or abs)

    Returns:
        ACM abstract URL
    """
    # Replace /pdf/ with /abs/
    if "/doi/pdf/" in url:
        return url.replace("/doi/pdf/", "/doi/abs/")
    elif "/doi/" in url and "/doi/abs/" not in url:
        # Handle URLs like https://dl.acm.org/doi/10.1145/3787466
        # Insert /abs/ after /doi/
        return url.replace("/doi/", "/doi/abs/", 1)
    return url


def extract_abstract(html_content):
    """
    Extract the abstract from ACM HTML.

    Args:
        html_content: HTML content from ACM page

    Returns:
        Abstract text as a string, or None if not found
    """
    # ACM abstracts are typically in a div with class "abstractSection abstractInFull"
    # or in a section with role="doc-abstract"
    patterns = [
        # Pattern 1: abstractSection class
        re.compile(
            r'<div[^>]*class="[^"]*abstractSection[^"]*"[^>]*>(.*?)</div>',
            re.IGNORECASE | re.DOTALL,
        ),
        # Pattern 2: role="doc-abstract"
        re.compile(
            r'<section[^>]*role="doc-abstract"[^>]*>(.*?)</section>',
            re.IGNORECASE | re.DOTALL,
        ),
        # Pattern 3: Abstract paragraph
        re.compile(
            r'<div[^>]*class="[^"]*abstract[^"]*"[^>]*>.*?<p>(.*?)</p>',
            re.IGNORECASE | re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(html_content)
        if match:
            abstract_html = match.group(1)

            # Remove HTML tags
            abstract_text = re.sub(r"<[^>]+>", "", abstract_html)

            # Clean up whitespace
            abstract_text = re.sub(r"\s+", " ", abstract_text).strip()

            if abstract_text and len(abstract_text) > 50:
                return abstract_text

    return None


def extract_date(html_content):
    """
    Extract the publication date from ACM HTML.

    Args:
        html_content: HTML content from ACM page

    Returns:
        Date string in M/YYYY format, or None if not found
    """
    # Look for publication date patterns
    # Pattern: "Published: DD Month YYYY" or "Publication Date: Month YYYY"
    month_map = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    # Try to find date in various formats
    patterns = [
        r"Published[:\s]+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        r"Publication Date[:\s]+([A-Za-z]+)\s+(\d{4})",
        r'"datePublished"[:\s]+"(\d{4})-(\d{2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                # Format: DD Month YYYY
                month_name = groups[1].lower()
                year = groups[2]
                month_num = month_map.get(month_name)
                if month_num:
                    return f"{month_num}/{year}"
            elif len(groups) == 2:
                if groups[0].isdigit():
                    # Format: YYYY-MM (from datePublished)
                    year = groups[0]
                    month = int(groups[1])
                    return f"{month}/{year}"
                else:
                    # Format: Month YYYY
                    month_name = groups[0].lower()
                    year = groups[1]
                    month_num = month_map.get(month_name)
                    if month_num:
                        return f"{month_num}/{year}"

    return None


def extract_paper_info(html_content):
    """
    Extract all paper information from ACM HTML.

    Args:
        html_content: HTML content from ACM page

    Returns:
        Dictionary with 'date' and 'abstract' fields
    """
    return {
        "date": extract_date(html_content),
        "abstract": extract_abstract(html_content),
    }


def main():
    """Main function to test ACM fetching and extraction."""
    parser = argparse.ArgumentParser(
        description="Fetch HTML from ACM Digital Library abstract pages."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://dl.acm.org/doi/abs/10.1145/3787466",
        help="ACM URL (default: https://dl.acm.org/doi/abs/10.1145/3787466)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Save HTML to file instead of printing",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw HTML preview instead of extracted fields",
    )
    args = parser.parse_args()

    # Convert PDF URL to abstract URL if needed
    url = convert_acm_pdf_to_abs(args.url)
    print(f"Fetching: {url}")

    doi = extract_acm_doi(url)
    if doi:
        print(f"DOI: {doi}")

    html_content = fetch_acm_html(url)

    if html_content:
        print(f"Successfully fetched {len(html_content)} bytes\n")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Saved to: {args.output}")
        elif args.raw:
            # Print first 3000 characters as preview
            print("=" * 60)
            print("HTML Preview (first 3000 chars):")
            print("=" * 60)
            print(html_content[:3000])
            print("\n... (truncated)")
        else:
            # Extract and display paper info
            paper_info = extract_paper_info(html_content)

            print("=" * 60)
            print("Extracted Paper Information:")
            print("=" * 60)

            print(f"\nDate: {paper_info['date']}")

            print(f"\nAbstract:\n{paper_info['abstract']}")
    else:
        print("Failed to fetch HTML content.")
        sys.exit(1)


if __name__ == "__main__":
    main()
