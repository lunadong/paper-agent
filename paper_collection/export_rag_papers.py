#!/usr/bin/env python3
"""
Export RAG papers from the database.

Finds all papers with primary_topic="RAG" and concatenates their descriptions
(title + summary or abstract) into a single output file.

Usage:
    python export_rag_papers.py --output rag_papers.txt
    python export_rag_papers.py --output rag_papers.txt --topic "Agents"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "web_interface"))

from db import execute_with_retry


def get_papers_by_primary_topic(topic: str) -> list:
    """Get all papers with the specified primary_topic."""
    cursor = execute_with_retry(
        "SELECT id, title, abstract, venue, year, recomm_date, "
        "summary_basics, summary_core, summary_techniques, summary_experiments "
        "FROM papers WHERE primary_topic = %s "
        "ORDER BY created_at DESC",
        (topic,),
    )
    return cursor.fetchall()


def format_paper_description(paper: dict) -> str:
    """Format a paper's description for output."""
    title = paper.get("title", "Untitled")
    venue = paper.get("venue") or ""
    year = paper.get("year") or ""
    recomm_date = paper.get("recomm_date") or ""

    # Build venue/year line
    meta_parts = []
    if venue:
        meta_parts.append(venue)
    if year:
        meta_parts.append(year)
    # Extract month from recomm_date if available (format: YYYY-MM-DD or similar)
    if recomm_date and len(recomm_date) >= 7:
        month = recomm_date[5:7] if recomm_date[4] == "-" else ""
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
    summary_techniques = paper.get("summary_techniques") or ""

    if summary_basics:
    summary_methods = paper.get("summary_methods_evidence") or ""

    if summary_basics:
        lines.append("## Basics")
        lines.append(summary_basics)
        lines.append("")
    if summary_core:
        lines.append("## Core Contributions")
        lines.append(summary_core)
        lines.append("")
    if summary_methods:
        lines.append("## Methods & Evidence")
        lines.append(summary_methods)
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Export papers by primary_topic to a single file"
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="RAG",
        help="Primary topic to filter by (default: RAG)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="rag_papers.txt",
        help="Output file path (default: rag_papers.txt)",
    )
    args = parser.parse_args()

    print(f"Fetching papers with primary_topic='{args.topic}'...")
    papers = get_papers_by_primary_topic(args.topic)
    print(f"Found {len(papers)} papers")

    if not papers:
        print("No papers found.")
        return

    output_parts = []
    output_parts.append(f"# Papers on {args.topic}")
    output_parts.append(f"# Total: {len(papers)} papers")
    output_parts.append("=" * 60)
    output_parts.append("")

    for i, paper in enumerate(papers, 1):
        output_parts.append(f"[Paper {i}/{len(papers)}]")
        output_parts.append(format_paper_description(paper))
        output_parts.append("-" * 60)
        output_parts.append("")

    output_content = "\n".join(output_parts)

    with open(args.output, "w") as f:
        f.write(output_content)

    print(f"Saved to: {args.output}")
    print(f"Total characters: {len(output_content)}")


if __name__ == "__main__":
    main()
