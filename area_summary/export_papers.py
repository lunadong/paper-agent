#!/usr/bin/env python3
"""
Export papers from the database with flexible filtering.

Fetches papers matching filter criteria and exports their metadata and summaries
to a JSON file.

Usage:
    # Export ALL papers
    python export_papers.py --all

    # Filter by primary_topic
    python export_papers.py --filter "primary_topic = 'RAG'"
    python export_papers.py --filter "primary_topic=RAG"

    # Filter by topic (contains)
    python export_papers.py --filter "topics ILIKE '%Agents%'"
    python export_papers.py --filter "topic=Agents"

    # Filter by year
    python export_papers.py --filter "year = 2025"
    python export_papers.py --filter "year>=2024"

    # Filter by recommendation date (this year)
    python export_papers.py --filter "recomm_date >= '2025-01-01'"
    python export_papers.py --filter "recomm_date=this_year"

    # Complex filters
    python export_papers.py --filter "primary_topic = 'RAG' AND year >= 2024"

    # Specify output directory
    python export_papers.py --filter "primary_topic = 'RAG'" --output-dir ./output

    # List all topics
    python export_papers.py --list-topics

Filter Examples:
    primary_topic = 'RAG'
    primary_topic = 'Agents'
    topics ILIKE '%Factuality%'
    year = 2025
    year >= 2024
    recomm_date >= '2025-01-01'
    recomm_date BETWEEN '2025-01-01' AND '2025-12-31'
    summary_core IS NOT NULL
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "paper_collection"))

from core.paper_db import PaperDB


def get_all_topics() -> list:
    """Get all unique primary_topic values from the database with counts."""
    db = PaperDB()
    try:
        cursor = db._get_cursor()
        cursor.execute("""
            SELECT primary_topic, COUNT(*) as count
            FROM papers
            WHERE primary_topic IS NOT NULL
            GROUP BY primary_topic
            ORDER BY count DESC
            """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        db.close()


def get_papers_with_filter(where_clause: str) -> list:
    """
    Get papers matching the WHERE clause.

    Args:
        where_clause: SQL WHERE clause (without the WHERE keyword)

    Returns:
        List of paper dictionaries
    """
    db = PaperDB()
    try:
        cursor = db._get_cursor()
        query = f"""
            SELECT id, title, authors, abstract, link, venue, year,
                   topics, primary_topic, recomm_date,
                   summary_basics, summary_core, summary_techniques,
                   summary_experiments, summary_figures
            FROM papers
            WHERE {where_clause}
            ORDER BY created_at DESC
        """
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        db.close()


def format_paper_for_json(paper: dict) -> dict:
    """Format a paper for JSON output."""
    # Convert any non-JSON-serializable types
    result = {}
    for key, value in paper.items():
        if value is None:
            result[key] = None
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "isoformat"):  # date objects
            result[key] = str(value)
        else:
            result[key] = value
    return result


def format_paper_description(paper: dict) -> str:
    """Format a paper's description for text output."""
    title = paper.get("title", "Untitled")
    venue = paper.get("venue") or ""
    year = paper.get("year") or ""
    recomm_date = paper.get("recomm_date") or ""

    # Build venue/year line
    meta_parts = []
    if venue:
        meta_parts.append(str(venue))
    if year:
        meta_parts.append(str(year))
    # Extract month from recomm_date if available
    if recomm_date:
        recomm_str = str(recomm_date)
        if len(recomm_str) >= 7 and recomm_str[4:5] == "-":
            month = recomm_str[5:7]
            if month:
                meta_parts.append(f"Month: {month}")

    meta_line = " | ".join(meta_parts) if meta_parts else ""

    lines = [f"# {title}"]
    if meta_line:
        lines.append(f"**{meta_line}**")
    lines.append("")

    # Always add abstract first
    abstract = paper.get("abstract") or ""
    if abstract:
        lines.append("## Abstract")
        lines.append(abstract)
        lines.append("")

    # Then add summaries if available
    summary_basics = paper.get("summary_basics") or ""
    summary_core = paper.get("summary_core") or ""
    summary_techniques = paper.get("summary_techniques") or ""
    summary_experiments = paper.get("summary_experiments") or ""

    if summary_basics:
        lines.append("## Basics")
        lines.append(str(summary_basics))
        lines.append("")
    if summary_core:
        lines.append("## Core Contributions")
        lines.append(str(summary_core))
        lines.append("")
    if summary_techniques:
        lines.append("## Techniques")
        lines.append(str(summary_techniques))
        lines.append("")
    if summary_experiments:
        lines.append("## Experiments")
        lines.append(str(summary_experiments))
        lines.append("")

    return "\n".join(lines)


def sanitize_filename(filter_clause: str) -> str:
    """Convert filter clause to a safe filename."""
    # Extract key parts for filename
    safe_name = filter_clause.lower()
    # Replace common SQL operators and quotes
    safe_name = re.sub(r"[=<>!]+", "_", safe_name)
    safe_name = re.sub(r"['\"]+", "", safe_name)
    safe_name = re.sub(r"\s+", "_", safe_name)
    safe_name = re.sub(r"[^a-z0-9_]", "", safe_name)
    # Truncate if too long
    if len(safe_name) > 50:
        safe_name = safe_name[:50]
    return safe_name or "papers"


def translate_simple_filter(filter_str: str) -> str:
    """
    Translate simple filter expressions to SQL WHERE clauses.

    Supports:
        primary_topic=RAG  ->  primary_topic = 'RAG'
        topic=RAG          ->  topics ILIKE '%RAG%'
        year=2025          ->  year = 2025
        recomm_date=this_year  ->  recomm_date >= '2025-01-01'

    If the filter already looks like SQL, return as-is.
    """
    # If it looks like SQL already (has quotes or SQL keywords), return as-is
    if "'" in filter_str or '"' in filter_str:
        return filter_str
    if any(
        kw in filter_str.upper()
        for kw in ["ILIKE", "LIKE", "BETWEEN", "IS NULL", "IS NOT NULL", "IN ("]
    ):
        return filter_str

    # Split on common connectors
    parts = re.split(r"\s+(AND|OR)\s+", filter_str, flags=re.IGNORECASE)

    translated_parts = []
    for part in parts:
        part = part.strip()

        # Handle AND/OR connectors
        if part.upper() in ("AND", "OR"):
            translated_parts.append(part.upper())
            continue

        # Parse simple key=value or key>=value expressions
        match = re.match(r"(\w+)\s*([=<>!]+)\s*(.+)", part)
        if match:
            key, op, value = match.groups()
            key = key.strip().lower()
            value = value.strip()

            # Handle special cases
            if key == "topic":
                # topic=X means topics contains X
                translated_parts.append(f"topics ILIKE '%{value}%'")
            elif key == "recomm_date" and value.lower() == "this_year":
                # recomm_date=this_year means this calendar year
                current_year = datetime.now().year
                translated_parts.append(f"recomm_date >= '{current_year}-01-01'")
            elif key in ("year",) and value.isdigit():
                # Numeric values don't need quotes
                translated_parts.append(f"{key} {op} {value}")
            else:
                # String values need quotes
                if not value.startswith("'") and not value.isdigit():
                    value = f"'{value}'"
                translated_parts.append(f"{key} {op} {value}")
        else:
            # Keep as-is if we can't parse it
            translated_parts.append(part)

    return " ".join(translated_parts)


def _create_argument_parser():
    """Create and return the argument parser for export_papers CLI."""
    parser = argparse.ArgumentParser(
        description="Export papers with flexible filtering to JSON/text files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all
  %(prog)s --filter "primary_topic = 'RAG'"
  %(prog)s --filter "primary_topic=RAG"
  %(prog)s --filter "topic=Agents"
  %(prog)s --filter "year >= 2024"
  %(prog)s --filter "recomm_date=this_year"
  %(prog)s --filter "primary_topic = 'RAG' AND year = 2025"
  %(prog)s --list-topics
        """,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export ALL papers from the database",
    )
    parser.add_argument(
        "--filter",
        type=str,
        help="Filter criteria (SQL WHERE clause or simple expression like 'primary_topic=RAG')",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Output directory for exported files (default: current directory)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output filename (default: auto-generated from filter)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "txt", "both"],
        default="json",
        help="Output format: json, txt, or both (default: json)",
    )
    parser.add_argument(
        "--list-topics",
        action="store_true",
        help="List all available topics with paper counts",
    )
    return parser


def _handle_list_topics():
    """Handle the --list-topics mode."""
    print("Available topics in database:\n")
    topics = get_all_topics()
    print(f"{'Topic':<35} {'Count':>8}")
    print("-" * 45)
    total = 0
    for row in topics:
        topic = row["primary_topic"]
        count = row["count"]
        total += count
        print(f"{topic:<35} {count:>8}")
    print("-" * 45)
    print(f"{'TOTAL':<35} {total:>8}")


def _get_output_base_name(args):
    """Determine the base filename for output files."""
    if args.output:
        base_name = args.output
        if base_name.endswith(".json") or base_name.endswith(".txt"):
            if base_name.endswith(".txt"):
                base_name = base_name[:-4]
            else:
                base_name = base_name[:-5]
        return base_name
    if args.all:
        return "all_papers"
    return sanitize_filename(args.filter) + "_papers"


def _export_to_json(papers, output_dir, base_name, filter_display, where_clause):
    """Export papers to JSON format."""
    json_file = output_dir / f"{base_name}.json"
    papers_json = [format_paper_for_json(p) for p in papers]

    output_data = {
        "filter": filter_display,
        "where_clause": where_clause,
        "count": len(papers),
        "exported_at": datetime.now().isoformat(),
        "papers": papers_json,
    }

    with open(json_file, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"JSON saved to: {json_file}")


def _export_to_text(papers, output_dir, base_name, filter_display):
    """Export papers to text format."""
    txt_file = output_dir / f"{base_name}.txt"

    output_parts = []
    output_parts.append(f"# Papers matching: {filter_display}")
    output_parts.append(f"# Total: {len(papers)} papers")
    output_parts.append(f"# Exported: {datetime.now().isoformat()}")
    output_parts.append("=" * 60)
    output_parts.append("")

    for i, paper in enumerate(papers, 1):
        output_parts.append(f"[Paper {i}/{len(papers)}]")
        output_parts.append(format_paper_description(paper))
        output_parts.append("-" * 60)
        output_parts.append("")

    output_content = "\n".join(output_parts)

    with open(txt_file, "w") as f:
        f.write(output_content)
    print(f"Text saved to: {txt_file}")
    print(f"Total characters: {len(output_content)}")


def main():
    parser = _create_argument_parser()
    args = parser.parse_args()

    if args.list_topics:
        _handle_list_topics()
        return

    if not args.filter and not args.all:
        print(
            "Error: --filter or --all is required (or use --list-topics to see available topics)"
        )
        print("\nExample usage:")
        print("  python export_papers.py --all")
        print("  python export_papers.py --filter \"primary_topic = 'RAG'\"")
        print('  python export_papers.py --filter "primary_topic=RAG"')
        print('  python export_papers.py --filter "topic=Agents"')
        print("  python export_papers.py --list-topics")
        sys.exit(1)

    if args.all:
        where_clause = "1=1"
        filter_display = "ALL"
        print("Exporting ALL papers...")
    else:
        where_clause = translate_simple_filter(args.filter)
        filter_display = args.filter
        print(f"Filter: {args.filter}")
        if where_clause != args.filter:
            print(f"SQL WHERE: {where_clause}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = _get_output_base_name(args)

    print("Fetching papers...")
    try:
        papers = get_papers_with_filter(where_clause)
    except Exception as e:
        print(f"Error executing query: {e}")
        print(f"WHERE clause: {where_clause}")
        sys.exit(1)

    print(f"Found {len(papers)} papers")

    if not papers:
        print("No papers found matching the filter.")
        return

    if args.format in ("json", "both"):
        _export_to_json(papers, output_dir, base_name, filter_display, where_clause)

    if args.format in ("txt", "both"):
        _export_to_text(papers, output_dir, base_name, filter_display)


if __name__ == "__main__":
    main()
