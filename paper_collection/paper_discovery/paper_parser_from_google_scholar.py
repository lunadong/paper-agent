#!/usr/bin/env python3
"""
Parse papers from Google Scholar search results.

Fetches papers from Google Scholar and adds them to the database.
Handles rate limiting, resumable progress, and duplicate detection.

Usage:
    python paper_parser_from_google_scholar.py --query "RAG" --year-start 2023
    python paper_parser_from_google_scholar.py --resume
    python paper_parser_from_google_scholar.py --query "RAG" --max-pages 10 --dry-run
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: Required packages not installed.")
    print("Run: pip install requests beautifulsoup4")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.paper_db import PaperDB

# Constants
# Common stopwords and characters to normalize for title matching
TITLE_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "for",
    "in",
    "on",
    "to",
    "and",
    "with",
    "via",
    "using",
    "is",
    "are",
    "by",
}

# Conference name to typical month mapping for date estimation
# Month numbers: 1=Jan, 2=Feb, ..., 12=Dec
CONFERENCE_MONTHS = {
    # NLP/Computational Linguistics
    "acl": 7,  # July
    "emnlp": 11,  # November
    "naacl": 6,  # June
    "coling": 8,  # August
    "eacl": 4,  # April
    "aacl": 11,  # November
    "conll": 11,  # November (co-located with EMNLP)
    "tacl": 6,  # Transactions - use mid-year
    # Machine Learning
    "neurips": 12,  # December
    "nips": 12,  # December (old name)
    "icml": 7,  # July
    "iclr": 5,  # May
    "aaai": 2,  # February
    "ijcai": 8,  # August
    "uai": 8,  # August
    "aistats": 4,  # April
    "colt": 7,  # July
    # Data Mining / IR
    "kdd": 8,  # August
    "www": 5,  # May (TheWebConf)
    "sigir": 7,  # July
    "wsdm": 2,  # February
    "cikm": 10,  # October
    "recsys": 9,  # September
    "icdm": 11,  # November
    "sdm": 4,  # April
    "ecir": 4,  # April
    "pakdd": 5,  # May
    # Computer Vision
    "cvpr": 6,  # June
    "iccv": 10,  # October
    "eccv": 10,  # October
    "wacv": 1,  # January
    # Speech/Audio
    "interspeech": 9,  # September
    "icassp": 4,  # April
    "asru": 12,  # December
    "slt": 12,  # December
    # Knowledge/Semantics
    "iswc": 10,  # October
    "eswc": 5,  # May
    "akbc": 6,  # June
    # Systems
    "osdi": 10,  # October
    "sosp": 10,  # October
    "nsdi": 4,  # April
    "eurosys": 4,  # April
    "atc": 7,  # July (USENIX ATC)
    "mlsys": 3,  # March
    # HCI
    "chi": 4,  # April
    "uist": 10,  # October
    "cscw": 10,  # October
    # General
    "findings": 7,  # Findings of ACL/EMNLP - varies, use July
}


def normalize_title(title: str) -> str:
    """Normalize title for duplicate comparison.

    - Lowercase
    - Remove punctuation
    - Remove common stopwords
    - Sort words (order-independent matching)
    """
    if not title:
        return ""
    # Lowercase and remove punctuation
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    # Split into words, remove stopwords, sort
    words = [w for w in title.split() if w and w not in TITLE_STOPWORDS]
    return " ".join(sorted(words))


def normalize_arxiv_link(link: str) -> Optional[str]:
    """Extract normalized arXiv ID from link, ignoring abs/pdf/html and version variants.

    Handles:
    - https://arxiv.org/abs/2301.12345
    - https://arxiv.org/pdf/2301.12345
    - https://arxiv.org/pdf/2301.12345.pdf
    - https://arxiv.org/html/2301.12345
    - https://arxiv.org/abs/2301.12345v1
    - https://arxiv.org/abs/2301.12345v2
    - http://arxiv.org/abs/2301.12345

    Returns:
        Normalized arXiv ID (e.g., "2301.12345") or None if not an arXiv link
    """
    if not link:
        return None
    # Match arXiv patterns, capturing just the base ID without version
    match = re.search(
        r"arxiv\.org/(?:abs|pdf|html)/(\d+\.\d+)(?:v\d+)?(?:\.pdf)?",
        link,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def is_non_english_title(title: str) -> bool:
    """Check if title is in a non-English language.

    Detects:
    - CJK (Chinese, Japanese, Korean)
    - Cyrillic (Russian, Ukrainian, etc.)
    - Arabic, Hebrew, Thai
    - Uzbek (Latin script with specific patterns)
    """
    if not title:
        return False

    # CJK characters
    if re.search(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", title):
        return True

    # Cyrillic
    if re.search(r"[\u0400-\u04ff]", title):
        return True

    # Arabic
    if re.search(r"[\u0600-\u06ff]", title):
        return True

    # Hebrew, Thai
    if re.search(r"[\u0590-\u05ff\u0e00-\u0e7f]", title):
        return True

    # Uzbek patterns (Latin script but specific words)
    uzbek_patterns = [
        r"Rag'batlantirish",
        r"O'zbekiston",
        r"O 'zbekiston",
        r"Yashil ",
        r"Barqaror",
        r"Iqtisodiy",
        r"Faoliyat",
        r"Tashkil Etish",
        r"Takomillashtirish",
        r"XODIM",
        r"Samaradorlig",
        r"RAQAMLI",
        r"Innovatsion",
        r"Strategiya",
    ]
    if sum(1 for p in uzbek_patterns if re.search(p, title, re.IGNORECASE)) >= 2:
        return True

    return False


def get_recomm_date(year_str: Optional[str]) -> str:
    """Get recommendation date based on year.

    - For 2026 papers: 2/28/2026
    - For other years: 12/31 of that year
    """
    if not year_str:
        return "2025-12-31"

    try:
        year = int(year_str)
        if year == 2026:
            return "2026-02-28"
        elif 2000 <= year <= 2030:
            return f"{year}-12-31"
        else:
            return "2025-12-31"
    except ValueError:
        return "2025-12-31"


def parse_arxiv_id_date(arxiv_id: str) -> Optional[str]:
    """
    Extract month and year from arXiv ID and return date as YYYY-MM-25.

    arXiv IDs since April 2007 use format: YYMM.NNNNN
    - YY: last 2 digits of year (07-99 for 2007-2099)
    - MM: month (01-12)

    Examples:
    - 2405.15556 -> 2024-05-25
    - 2501.12789 -> 2025-01-25
    - 1909.02339 -> 2019-09-25

    Returns:
        Date string "YYYY-MM-25" or None if not parseable
    """
    if not arxiv_id:
        return None

    # Match YYMM.XXXXX format
    match = re.match(r"(\d{2})(\d{2})\.\d+", arxiv_id)
    if match:
        yy = int(match.group(1))
        mm = int(match.group(2))

        # Convert 2-digit year to 4-digit
        # 07-99 -> 2007-2099
        # 00-06 -> 2100-2106 (future)
        if yy >= 7:
            year = 2000 + yy
        else:
            year = 2100 + yy

        if 1 <= mm <= 12:
            return f"{year}-{mm:02d}-25"

    return None


def get_conference_month(venue: str) -> Optional[int]:
    """
    Get the typical month for a conference based on venue name.

    Returns month number (1-12) or None if not found.
    """
    if not venue:
        return None

    venue_lower = venue.lower()

    # Check each conference pattern
    for conf_name, month in CONFERENCE_MONTHS.items():
        if conf_name in venue_lower:
            return month

    return None


def get_smart_recomm_date(
    arxiv_id: Optional[str],
    arxiv_submission_date: Optional[str],
    venue: Optional[str],
    year: Optional[str],
) -> str:
    """
    Get the best recommendation date using multiple sources in priority order:

    1. arXiv submission date from API (most accurate)
    2. Date derived from arXiv ID (YYMM.XXXXX -> YYYY-MM-25)
    3. Year + conference month (e.g., EMNLP 2024 -> 2024-11-25)
    4. Fallback to year-based date (YYYY-12-31 or 2026-02-28)

    Args:
        arxiv_id: arXiv paper ID (e.g., "2405.15556")
        arxiv_submission_date: Submission date from arXiv API (YYYY-MM-DD)
        venue: Conference/journal venue name
        year: Publication year

    Returns:
        Recommendation date in YYYY-MM-DD format
    """
    # Priority 1: arXiv submission date from API
    if arxiv_submission_date:
        return arxiv_submission_date

    # Priority 2: Parse from arXiv ID
    if arxiv_id:
        arxiv_date = parse_arxiv_id_date(arxiv_id)
        if arxiv_date:
            return arxiv_date

    # Priority 3: Year + conference month
    if year and venue:
        conf_month = get_conference_month(venue)
        if conf_month:
            try:
                year_int = int(year)
                return f"{year_int}-{conf_month:02d}-25"
            except ValueError:
                pass

    # Priority 4: Fallback to year-based date
    return get_recomm_date(year)


def fetch_arxiv_metadata(arxiv_id: str) -> Optional[dict]:
    """Fetch metadata (abstract, authors, year, submission_date) from arXiv API.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2301.12345")

    Returns:
        Dict with title, abstract, authors, year, submission_date or None if failed
    """
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")

        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entry = root.find("atom:entry", ns)
        if entry is None:
            return None

        title_elem = entry.find("atom:title", ns)
        abstract_elem = entry.find("atom:summary", ns)

        title = None
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip().replace("\n", " ")
        abstract = None
        if abstract_elem is not None and abstract_elem.text:
            abstract = abstract_elem.text.strip()

        # Get authors
        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.find("atom:name", ns)
            if name is not None and name.text:
                authors.append(name.text.strip())

        # Get submission date from <published> element
        # Format: 2025-01-21T18:23:42Z -> 2025-01-21
        published = entry.find("atom:published", ns)
        year = None
        submission_date = None
        if published is not None and published.text:
            date_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", published.text)
            if date_match:
                submission_date = (
                    f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                )
                year = date_match.group(1)

        return {
            "title": title,
            "abstract": abstract,
            "authors": ", ".join(authors) if authors else None,
            "year": year,
            "submission_date": submission_date,
        }
    except Exception:
        return None


def title_similarity(title1: str, title2: str) -> float:
    """Calculate Jaccard similarity between two titles.

    Returns value between 0 and 1.
    """
    norm1 = set(normalize_title(title1).split())
    norm2 = set(normalize_title(title2).split())
    if not norm1 or not norm2:
        return 0.0
    intersection = len(norm1 & norm2)
    union = len(norm1 | norm2)
    return intersection / union if union > 0 else 0.0


GOOGLE_SCHOLAR_BASE = "https://scholar.google.com/scholar"
RESULTS_PER_PAGE = 10
DEFAULT_MAX_PAGES = 100  # 1000 results max (Google Scholar limit)
DEFAULT_DELAY = 10  # seconds between requests
PROGRESS_FILE = Path(__file__).parent.parent / "tmp" / "google_scholar_progress.json"

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}


def build_search_url(
    query: str,
    start: int,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> str:
    """Build Google Scholar search URL.

    Args:
        query: Search query string
        start: Result offset (0, 10, 20, ...)
        year_start: Filter papers from this year
        year_end: Filter papers until this year

    Returns:
        Full Google Scholar search URL
    """
    params = {
        "q": query,
        "hl": "en",
        "as_sdt": "0,5",
        "start": start,
    }
    if year_start:
        params["as_ylo"] = year_start
    if year_end:
        params["as_yhi"] = year_end
    return f"{GOOGLE_SCHOLAR_BASE}?{urlencode(params)}"


def fetch_page(
    url: str, session: requests.Session, max_retries: int = 3
) -> Optional[str]:
    """Fetch a Google Scholar page with retry logic.

    Args:
        url: URL to fetch
        session: Requests session for cookies
        max_retries: Maximum retry attempts

    Returns:
        HTML content or None if failed
    """
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=HEADERS, timeout=30)

            if response.status_code == 200:
                # Check if we got a CAPTCHA page
                if "unusual traffic" in response.text.lower():
                    print("  CAPTCHA detected! Please solve manually and resume.")
                    return None
                return response.text

            elif response.status_code == 429:
                wait_time = 60 * (attempt + 1)  # 60, 120, 180 seconds
                print(f"  Rate limited (429), waiting {wait_time} seconds...")
                time.sleep(wait_time)

            elif response.status_code == 503:
                print("  Service unavailable (503), waiting 30 seconds...")
                time.sleep(30)

            else:
                print(f"  HTTP {response.status_code}, retrying...")
                time.sleep(10)

        except requests.exceptions.Timeout:
            print("  Timeout, retrying...")
            time.sleep(10)
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}, retrying...")
            time.sleep(10)

    return None


def parse_papers(html: str) -> list:
    """Parse papers from Google Scholar HTML.

    Args:
        html: Raw HTML content

    Returns:
        List of paper dictionaries
    """
    soup = BeautifulSoup(html, "html.parser")
    papers = []

    # Find all paper result divs
    results = soup.select("div.gs_r.gs_or.gs_scl")

    for result in results:
        try:
            paper = parse_single_paper(result)
            if paper and paper.get("title"):
                papers.append(paper)
        except Exception as e:
            print(f"  Error parsing paper: {e}")

    return papers


def parse_single_paper(result) -> Optional[dict]:
    """Parse a single paper result from Google Scholar.

    Args:
        result: BeautifulSoup element for a single result

    Returns:
        Paper dictionary or None if parsing failed
    """
    # Title and main link
    title_elem = result.select_one("h3.gs_rt")
    if not title_elem:
        return None

    # Get title text and link
    title_link = title_elem.select_one("a")
    if title_link:
        title = title_link.get_text(strip=True)
        link = title_link.get("href")
    else:
        title = title_elem.get_text(strip=True)
        link = None

    # Clean title - remove [PDF], [HTML], [BOOK], [CITATION] prefixes
    title = re.sub(
        r"^\[(PDF|HTML|BOOK|CITATION|B)\]\s*", "", title, flags=re.IGNORECASE
    )
    title = title.strip()

    if not title:
        return None

    # Authors, venue, and year from meta line
    # Format: "Authors - Venue, Year - Publisher" or variations
    meta_elem = result.select_one("div.gs_a")
    authors = ""
    venue = ""
    year = ""

    if meta_elem:
        meta_text = meta_elem.get_text()
        # Remove HTML entities and normalize
        meta_text = meta_text.replace("\xa0", " ").strip()

        # Split by " - "
        parts = [p.strip() for p in meta_text.split(" - ")]

        if len(parts) >= 1:
            # First part is usually authors
            authors = parts[0]
            # Clean up author names (remove "..." at end)
            authors = re.sub(r"\.{3,}$", "", authors).strip()

        if len(parts) >= 2:
            # Second part is usually venue and year
            venue_year = parts[1]
            # Extract year (4-digit number between 1900-2030)
            year_match = re.search(r"\b(19\d{2}|20[0-3]\d)\b", venue_year)
            if year_match:
                year = year_match.group(1)
                # Remove year from venue string
                venue = re.sub(r",?\s*" + year + r"\s*,?", "", venue_year).strip()
                venue = venue.rstrip(",").strip()
            else:
                venue = venue_year

    # Abstract snippet
    abstract_elem = result.select_one("div.gs_rs")
    abstract = ""
    if abstract_elem:
        abstract = abstract_elem.get_text(strip=True)
        # Clean up abstract
        abstract = re.sub(r"\.{3,}$", "...", abstract)

    # PDF link (from the side panel)
    pdf_link = None
    pdf_elem = result.select_one("div.gs_or_ggsm a")
    if pdf_elem:
        pdf_link = pdf_elem.get("href")

    # Citation count from "Cited by X" link
    citations = 0
    cite_elem = result.select_one("div.gs_fl a")
    if cite_elem:
        # Look for "Cited by X" pattern
        for link_elem in result.select("div.gs_fl a"):
            link_text = link_elem.get_text(strip=True)
            cite_match = re.search(r"Cited by (\d+)", link_text)
            if cite_match:
                citations = int(cite_match.group(1))
                break

    # Prefer arXiv link if available
    final_link = link
    if link:
        # Check if there's an arXiv link in the result
        arxiv_match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", link)
        if arxiv_match:
            final_link = f"https://arxiv.org/abs/{arxiv_match.group(1)}"
        elif pdf_link and "arxiv.org" in pdf_link:
            arxiv_match = re.search(r"arxiv\.org/pdf/(\d+\.\d+)", pdf_link)
            if arxiv_match:
                final_link = f"https://arxiv.org/abs/{arxiv_match.group(1)}"

    return {
        "title": title,
        "authors": authors,
        "venue": venue,
        "year": year,
        "abstract": abstract,
        "link": final_link,
        "pdf_link": pdf_link,
        "citations": citations,
    }


def load_progress(progress_file: Path) -> dict:
    """Load progress from checkpoint file.

    Args:
        progress_file: Path to progress JSON file

    Returns:
        Progress dictionary
    """
    default_progress = {
        "query": None,
        "year_start": None,
        "year_end": None,
        "processed_pages": [],
        "added": 0,
        "skipped": 0,
        "failed_pages": 0,
        "last_updated": None,
    }

    if progress_file.exists():
        try:
            with open(progress_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print("Warning: Could not load progress file, starting fresh")

    return default_progress


def save_progress(progress: dict, progress_file: Path):
    """Save progress to checkpoint file.

    Args:
        progress: Progress dictionary
        progress_file: Path to progress JSON file
    """
    progress["last_updated"] = datetime.now().isoformat()
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Parse papers from Google Scholar search results"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="RAG",
        help="Search query (default: RAG)",
    )
    parser.add_argument(
        "--year-start",
        type=int,
        default=2023,
        help="Start year filter (default: 2023)",
    )
    parser.add_argument(
        "--year-end",
        type=int,
        help="End year filter (default: none)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum pages to fetch (default: {DEFAULT_MAX_PAGES})",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY,
        help=f"Delay between pages in seconds (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save to database, just show what would be added",
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default=str(PROGRESS_FILE),
        help=f"Progress file path (default: {PROGRESS_FILE})",
    )
    args = parser.parse_args()

    progress_file = Path(args.progress_file)

    # Load or initialize progress
    if args.resume:
        progress = load_progress(progress_file)
        if progress["query"]:
            print(f"Resuming search for: {progress['query']}")
            print(f"  Year: {progress['year_start']}-{progress.get('year_end', 'now')}")
            print(f"  Pages processed: {len(progress['processed_pages'])}")
            print(f"  Papers added so far: {progress['added']}")
        else:
            print("No previous progress found, starting fresh")
            progress["query"] = args.query
            progress["year_start"] = args.year_start
            progress["year_end"] = args.year_end
    else:
        progress = load_progress(progress_file)
        # Reset if query changed
        if progress["query"] != args.query or progress["year_start"] != args.year_start:
            progress = {
                "query": args.query,
                "year_start": args.year_start,
                "year_end": args.year_end,
                "processed_pages": [],
                "added": 0,
                "skipped": 0,
                "failed_pages": 0,
                "last_updated": None,
            }

    print()
    print("=" * 70)
    print("Google Scholar Paper Parser")
    print("=" * 70)
    print(f"Query: {progress['query']}")
    print(f"Year filter: {progress['year_start']}-{progress.get('year_end') or 'now'}")
    print(f"Max pages: {args.max_pages}")
    print(f"Delay: {args.delay} seconds")
    print(f"Dry run: {args.dry_run}")
    print()

    # Connect to database
    if not args.dry_run:
        db = PaperDB()
        # Pre-load existing titles and arXiv IDs for duplicate checking
        print("Loading existing papers for duplicate detection...")
        cursor = db._get_cursor()
        cursor.execute("SELECT id, title, link FROM papers")
        existing_papers = cursor.fetchall()

        # Build two indexes: by normalized title and by arXiv ID
        existing_titles = {}
        existing_arxiv_ids = {}
        for p in existing_papers:
            # Index by normalized title
            norm_title = normalize_title(p["title"])
            if norm_title:
                existing_titles[norm_title] = p["id"]
            # Index by arXiv ID (ignores abs/pdf/html and version)
            arxiv_id = normalize_arxiv_link(p["link"])
            if arxiv_id:
                existing_arxiv_ids[arxiv_id] = p["id"]

        print(
            f"Loaded {len(existing_titles)} titles, {len(existing_arxiv_ids)} arXiv IDs"
        )
    else:
        db = None
        existing_titles = {}
        existing_arxiv_ids = {}

    # Create session for cookies
    session = requests.Session()

    try:
        for page_num in range(args.max_pages):
            start = page_num * RESULTS_PER_PAGE

            # Skip already processed pages
            if start in progress["processed_pages"]:
                continue

            # Build and fetch URL
            url = build_search_url(
                progress["query"],
                start,
                progress["year_start"],
                progress.get("year_end"),
            )
            print(f"[Page {page_num + 1}/{args.max_pages}] Fetching start={start}...")

            html = fetch_page(url, session)
            if not html:
                print("  Failed to fetch page, stopping")
                progress["failed_pages"] += 1
                # Save progress and stop on persistent failure
                save_progress(progress, progress_file)
                if progress["failed_pages"] >= 3:
                    print(
                        "\n3 consecutive failures, stopping. Use --resume to continue."
                    )
                    break
                continue

            # Reset failure counter on success
            progress["failed_pages"] = 0

            # Parse papers
            papers = parse_papers(html)
            print(f"  Found {len(papers)} papers")

            if len(papers) == 0:
                print("  No more results, stopping")
                break

            # Add papers to database
            for paper in papers:
                if not paper.get("title"):
                    continue

                # Check for non-English title
                paper_title = paper["title"]
                if is_non_english_title(paper_title):
                    print(f"    Skipped (non-English): {paper_title[:40]}...")
                    progress["skipped"] += 1
                    continue

                # Check for duplicate by normalized title
                norm_title = normalize_title(paper_title)
                paper_link = paper.get("link", "")
                paper_arxiv_id = normalize_arxiv_link(paper_link)

                # Check title-based duplicate
                if norm_title in existing_titles:
                    existing_id = existing_titles[norm_title]
                    print(
                        f"    Skipped (title dup of [{existing_id}]): {paper_title[:40]}..."
                    )
                    progress["skipped"] += 1
                    continue

                # Check arXiv-based duplicate
                if paper_arxiv_id and paper_arxiv_id in existing_arxiv_ids:
                    existing_id = existing_arxiv_ids[paper_arxiv_id]
                    print(
                        f"    Skipped (arXiv dup of [{existing_id}]): {paper_title[:40]}..."
                    )
                    progress["skipped"] += 1
                    continue

                # Skip papers before 2026 with fewer than 10 citations
                paper_year = paper.get("year", "")
                paper_citations = paper.get("citations", 0)
                try:
                    year_int = int(paper_year) if paper_year else 0
                except ValueError:
                    year_int = 0

                if year_int > 0 and year_int < 2026 and paper_citations < 10:
                    print(
                        f"    Skipped (year={year_int}, citations={paper_citations}): "
                        f"{paper_title[:40]}..."
                    )
                    progress["skipped"] += 1
                    continue

                if args.dry_run:
                    print(f"    [DRY RUN] Would add: {paper['title'][:50]}...")
                    print(f"              Link: {paper.get('link', 'No link')}")
                    progress["added"] += 1
                elif db:
                    # Enrich paper data from arXiv if available
                    final_title = paper["title"]
                    final_abstract = paper.get("abstract")
                    final_authors = paper.get("authors")
                    final_year = paper.get("year")
                    recomm_date = (
                        None  # Will be set from arXiv or fallback to year-based
                    )

                    if paper_arxiv_id:
                        arxiv_data = fetch_arxiv_metadata(paper_arxiv_id)
                        if arxiv_data:
                            # Use arXiv title (more accurate than Google Scholar)
                            if arxiv_data.get("title"):
                                final_title = arxiv_data["title"]
                            # Use arXiv abstract if longer than Google Scholar snippet
                            if arxiv_data.get("abstract"):
                                if not final_abstract or len(
                                    arxiv_data["abstract"]
                                ) > len(final_abstract):
                                    final_abstract = arxiv_data["abstract"]
                            # Always use arXiv authors (more accurate)
                            if arxiv_data.get("authors"):
                                final_authors = arxiv_data["authors"]
                            # Use arXiv year if missing
                            if not final_year and arxiv_data.get("year"):
                                final_year = arxiv_data["year"]
                            # Store submission date for smart recomm_date
                            arxiv_submission_date = arxiv_data.get("submission_date")
                        else:
                            arxiv_submission_date = None
                        time.sleep(0.3)  # Rate limiting for arXiv API
                    else:
                        arxiv_submission_date = None

                    # Use smart recomm_date with multiple fallback sources
                    recomm_date = get_smart_recomm_date(
                        arxiv_id=paper_arxiv_id,
                        arxiv_submission_date=arxiv_submission_date,
                        venue=paper.get("venue"),
                        year=final_year,
                    )

                    paper_id = db.add_paper(
                        title=final_title,
                        authors=final_authors,
                        venue=paper.get("venue"),
                        year=final_year,
                        abstract=final_abstract,
                        link=paper.get("link"),
                        recomm_date=recomm_date,
                    )

                    if paper_id:
                        print(f"    [{paper_id}] Added: {paper['title'][:50]}...")
                        progress["added"] += 1
                        # Add to existing indexes to catch duplicates within same run
                        existing_titles[norm_title] = paper_id
                        if paper_arxiv_id:
                            existing_arxiv_ids[paper_arxiv_id] = paper_id
                    else:
                        print(f"    Skipped (DB conflict): {paper['title'][:40]}...")
                        progress["skipped"] += 1

            # Mark page as processed
            progress["processed_pages"].append(start)

            # Save progress after each page
            save_progress(progress, progress_file)

            # Delay between pages (except for last page)
            if page_num < args.max_pages - 1 and len(papers) > 0:
                print(f"  Waiting {args.delay} seconds...")
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
        save_progress(progress, progress_file)

    finally:
        # Generate embeddings for newly added papers
        if db and progress["added"] > 0:
            print()
            print("=" * 70)
            print("GENERATING EMBEDDINGS")
            print("=" * 70)
            try:
                result = db.update_all_embeddings()
                print(f"Generated {result.get('updated', 0)} embeddings")
            except Exception as e:
                print(f"Warning: Embedding generation failed: {e}")

        if db:
            db.close()

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Query: {progress['query']}")
    print(f"Pages processed: {len(progress['processed_pages'])}")
    print(f"Papers added: {progress['added']}")
    print(f"Papers skipped (duplicates): {progress['skipped']}")
    print(f"Progress saved to: {progress_file}")
    print()
    print("To resume: python paper_parser_from_google_scholar.py --resume")


if __name__ == "__main__":
    main()
