#!/usr/bin/env python3
"""
Paper Parsing Utility for Area Summaries.

Parses {area}_papers.txt files (exported from database) into structured JSON.
The raw text files can be very large (~927K tokens), so this parser enables
selective loading by converting to a clean JSON array of paper objects.

Usage:
    # CLI
    python parse_papers.py --input tmp_summary/rag_papers.txt --output tmp_summary/rag_papers_parsed.json

    # Programmatic
    from parse_papers import parse_papers_file
    papers = parse_papers_file("tmp_summary/rag_papers.txt")
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_json_block(text: str) -> dict | None:
    """Parse a JSON block from text, handling potential formatting issues."""
    if not text or not text.strip():
        return None

    text = text.strip()
    if not text.startswith("{"):
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_count = 0
        end_idx = -1
        for i, char in enumerate(text):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break

        if end_idx > 0:
            try:
                return json.loads(text[: end_idx + 1])
            except json.JSONDecodeError:
                pass

        return None


def parse_paper_block(block: str) -> dict | None:
    """
    Parse a single paper block into a structured dictionary.

    Returns a dict with fields:
    - paper_num: int
    - total_papers: int
    - title: str
    - venue_info: str (venue, year, month line)
    - abstract: str
    - basics: dict (parsed JSON)
    - core: dict (parsed JSON)
    - methods: dict (parsed JSON)
    """
    lines = block.strip().split("\n")
    if not lines:
        return None

    result = {
        "paper_num": None,
        "total_papers": None,
        "title": "",
        "venue_info": "",
        "abstract": "",
        "basics": None,
        "core": None,
        "methods": None,
    }

    current_section = None
    section_content = []

    for line in lines:
        line_stripped = line.strip()

        paper_match = re.match(r"\[Paper\s+(\d+)/(\d+)\]", line_stripped)
        if paper_match:
            result["paper_num"] = int(paper_match.group(1))
            result["total_papers"] = int(paper_match.group(2))
            continue

        if line_stripped.startswith("# ") and not line_stripped.startswith("## "):
            result["title"] = line_stripped[2:].strip()
            continue

        if line_stripped.startswith("**") and line_stripped.endswith("**"):
            result["venue_info"] = line_stripped.strip("*").strip()
            continue

        if line_stripped == "## Abstract":
            if current_section and section_content:
                _store_section(result, current_section, section_content)
            current_section = "abstract"
            section_content = []
            continue

        if line_stripped == "## Basics":
            if current_section and section_content:
                _store_section(result, current_section, section_content)
            current_section = "basics"
            section_content = []
            continue

        if line_stripped == "## Core Contributions":
            if current_section and section_content:
                _store_section(result, current_section, section_content)
            current_section = "core"
            section_content = []
            continue

        if line_stripped == "## Methods & Evidence":
            if current_section and section_content:
                _store_section(result, current_section, section_content)
            current_section = "methods"
            section_content = []
            continue

        if current_section:
            section_content.append(line)

    if current_section and section_content:
        _store_section(result, current_section, section_content)

    if result["paper_num"] is None and not result["title"]:
        return None

    return result


def _store_section(result: dict, section: str, content: list) -> None:
    """Store parsed section content into result dict."""
    text = "\n".join(content).strip()

    if section == "abstract":
        result["abstract"] = text
    elif section in ("basics", "core", "methods"):
        parsed = parse_json_block(text)
        result[section] = parsed


def parse_papers_file(input_path: str | Path) -> list[dict]:
    """
    Parse a papers.txt file and return a list of paper dictionaries.

    Args:
        input_path: Path to the {area}_papers.txt file

    Returns:
        List of paper dicts with fields: paper_num, total_papers, title,
        venue_info, abstract, basics, core, methods
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_path, encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n-{50,}\n", content)

    header_match = re.search(r"# Total:\s*(\d+)\s*papers", content)
    expected_count = int(header_match.group(1)) if header_match else None

    papers = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if block.startswith(":Q#") or block.startswith("# Papers on"):
            continue

        if re.match(r"^# Total:\s*\d+\s*papers", block):
            continue

        if block.startswith("====="):
            continue

        paper = parse_paper_block(block)
        if paper and paper.get("title"):
            papers.append(paper)

    if expected_count and len(papers) != expected_count:
        print(
            f"Warning: Expected {expected_count} papers but parsed {len(papers)}",
            file=sys.stderr,
        )

    return papers


def extract_metadata(papers: list[dict]) -> dict:
    """
    Extract aggregate metadata from parsed papers.

    Returns:
        Dict with:
        - total_papers: int
        - years: list of unique years
        - topics: dict mapping sub_topic -> count
        - primary_focus: dict mapping focus -> count
        - avg_breakthrough_score: float
    """
    metadata = {
        "total_papers": len(papers),
        "years": set(),
        "topics": {},
        "primary_focus": {},
        "breakthrough_scores": [],
    }

    for paper in papers:
        basics = paper.get("basics") or {}
        if isinstance(basics, dict):
            for key in basics:
                entry = basics[key]
                if isinstance(entry, dict) and "year" in entry:
                    metadata["years"].add(entry["year"])

        core = paper.get("core") or {}
        if isinstance(core, dict):
            topic_rel = core.get("topic_relevance", {})

            for sub_topic in topic_rel.get("sub_topic", []):
                metadata["topics"][sub_topic] = metadata["topics"].get(sub_topic, 0) + 1

            for focus in topic_rel.get("primary_focus", []):
                metadata["primary_focus"][focus] = (
                    metadata["primary_focus"].get(focus, 0) + 1
                )

            assessment = core.get("breakthrough_assessment", {})
            if isinstance(assessment, dict) and "score_1_to_10" in assessment:
                try:
                    score = float(assessment["score_1_to_10"])
                    metadata["breakthrough_scores"].append(score)
                except (ValueError, TypeError):
                    pass

    metadata["years"] = sorted(metadata["years"])
    if metadata["breakthrough_scores"]:
        metadata["avg_breakthrough_score"] = round(
            sum(metadata["breakthrough_scores"]) / len(metadata["breakthrough_scores"]),
            2,
        )
    else:
        metadata["avg_breakthrough_score"] = None
    del metadata["breakthrough_scores"]

    return metadata


def main():
    parser = argparse.ArgumentParser(
        description="Parse {area}_papers.txt files into structured JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python parse_papers.py --input tmp_summary/rag_papers.txt --output tmp_summary/rag_papers_parsed.json
  python parse_papers.py --input tmp_summary/rag_papers.txt  # prints to stdout
  python parse_papers.py --input tmp_summary/rag_papers.txt --metadata  # show metadata only
        """,
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to the {area}_papers.txt file",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output JSON file path (if not specified, prints to stdout)",
    )
    parser.add_argument(
        "--metadata",
        "-m",
        action="store_true",
        help="Only output metadata summary, not full papers",
    )
    parser.add_argument(
        "--pretty",
        "-p",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: True)",
    )
    parser.add_argument(
        "--compact",
        "-c",
        action="store_true",
        help="Output compact JSON (overrides --pretty)",
    )

    args = parser.parse_args()

    try:
        papers = parse_papers_file(args.input)
        metadata = extract_metadata(papers)

        if args.metadata:
            output_data = metadata
        else:
            output_data = {
                "metadata": metadata,
                "papers": papers,
            }

        indent = None if args.compact else 2
        json_str = json.dumps(output_data, indent=indent, ensure_ascii=False)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"Wrote {len(papers)} papers to {output_path}", file=sys.stderr)
            print(f"Metadata: {json.dumps(metadata, indent=2)}", file=sys.stderr)
        else:
            print(json_str)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing papers: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
