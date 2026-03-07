#!/usr/bin/env python3
"""
Paper Grouping Utility for Area Summaries.

Groups papers from papers_parsed.json by taxonomy categories, themes, and sub-topics.
Produces formatted paper files for each group, ready for sub-agent summarization.

This script consumes the output of parse_papers.py and does NOT overlap with it:
- parse_papers.py: Parses raw text -> papers_parsed.json (paper parsing)
- group_papers.py: Groups papers_parsed.json by taxonomy -> formatted files (paper grouping)

Usage:
    python group_papers.py --area rag
    python group_papers.py --area rag --papers prompt_optimization/area_summaries/rag/papers_parsed.json
    python group_papers.py --area agents --taxonomy prompts/taxonomy/agents_taxonomy.json
"""

import argparse
import json
import sys
from pathlib import Path

# When a group exceeds this size, filter out low-score papers to keep prompts manageable
BIG_GROUP_THRESHOLD = 50
MIN_BREAKTHROUGH_SCORE = 7


def matches_keywords(all_text: str, keywords: list) -> bool:
    """Check if any keyword appears as substring in text (case-insensitive)."""
    all_text_lower = all_text.lower()
    return any(kw.lower() in all_text_lower for kw in keywords)


def get_paper_text(paper: dict) -> str:
    """Extract searchable text from paper's topic_relevance and title."""
    core = paper.get("core") or {}
    topic_rel = core.get("topic_relevance", {}) if isinstance(core, dict) else {}
    if topic_rel is None:
        topic_rel = {}

    sub_topics = topic_rel.get("sub_topic", [])
    primary_focus = topic_rel.get("primary_focus", [])

    if isinstance(sub_topics, str):
        sub_topics = [sub_topics]
    if isinstance(primary_focus, str):
        primary_focus = [primary_focus]

    all_tags = (sub_topics or []) + (primary_focus or [])
    title = paper.get("title", "")

    return " ".join([t.lower() for t in all_tags]) + " " + title.lower()


def get_paper_abstract(paper: dict) -> str:
    """Extract paper abstract for fallback matching."""
    abstract = paper.get("abstract", "")
    if not abstract:
        basics = paper.get("basics") or {}
        abstract = basics.get("abstract", "")
    return abstract.lower() if abstract else ""


def get_paper_id(paper: dict) -> str:
    """Get unique paper identifier."""
    basics = paper.get("basics") or {}
    return basics.get("arxiv_id") or str(paper.get("paper_num", ""))


def compute_keyword_score(text: str, keywords: list) -> int:
    """Count how many keywords match in text (for finding closest match)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def find_closest_category(paper: dict, taxonomy: dict) -> str | None:
    """Find the closest matching category using abstract when no direct match."""
    abstract = get_paper_abstract(paper)
    if not abstract:
        return None

    best_cat_id = None
    best_score = 0

    for cat in taxonomy["categories"]:
        score = compute_keyword_score(abstract, cat.get("matching_keywords", []))
        if score > best_score:
            best_score = score
            best_cat_id = cat["id"]

    return best_cat_id if best_score > 0 else None


def find_closest_theme(paper: dict, taxonomy: dict) -> str | None:
    """Find the closest matching theme using abstract when no direct match."""
    abstract = get_paper_abstract(paper)
    if not abstract:
        return None

    best_theme_id = None
    best_score = 0

    for theme in taxonomy.get("theme", []):
        score = compute_keyword_score(abstract, theme.get("matching_keywords", []))
        if score > best_score:
            best_score = score
            best_theme_id = theme["id"]

    return best_theme_id if best_score > 0 else None


def _assign_paper_to_category(paper, category_ids, cat_info, groups, taxonomy):
    """
    Assign a paper to one disjoint category.

    Returns the assigned category ID or None if assigned to 'other'.
    """
    paper_text = get_paper_text(paper)

    for cat_id in category_ids:
        cat = cat_info[cat_id]
        if matches_keywords(paper_text, cat.get("matching_keywords", [])):
            groups[cat_id].append(paper)
            return cat_id

    closest_cat = find_closest_category(paper, taxonomy)
    if closest_cat:
        groups[closest_cat].append(paper)
        return closest_cat

    groups["other"].append(paper)
    return None


def _assign_paper_to_themes(paper, assigned_category, themes, taxonomy):
    """
    Assign a paper to overlapping themes.

    Returns True if any theme was matched directly.
    """
    paper_text = get_paper_text(paper)
    matched_theme = False

    for theme in taxonomy.get("theme", []):
        if matches_keywords(paper_text, theme.get("matching_keywords", [])):
            themes[theme["id"]].append(paper)
            matched_theme = True

    if assigned_category is None and not matched_theme:
        closest_theme = find_closest_theme(paper, taxonomy)
        if closest_theme:
            themes[closest_theme].append(paper)

    return matched_theme


def _tag_paper_subtopics(paper, assigned_category, cat_info, sub_topic_tags):
    """Tag paper with matching sub-topics within its assigned category."""
    if not assigned_category or assigned_category == "other":
        return

    paper_id = get_paper_id(paper)
    paper_text = get_paper_text(paper)
    cat_subtopics = cat_info[assigned_category].get("sub_topics", [])

    paper_subtopics = []
    for st in cat_subtopics:
        if matches_keywords(paper_text, st.get("matching_keywords", [])):
            paper_subtopics.append(st["id"])

    if paper_subtopics:
        sub_topic_tags[paper_id] = paper_subtopics


def _build_subtopic_paper_lists(groups, cat_info, sub_topic_tags, taxonomy):
    """Build sub-topic paper lists and category general papers."""
    sub_topic_papers = {}
    category_general_papers = {}

    for cat in taxonomy["categories"]:
        for st in cat.get("sub_topics", []):
            sub_topic_papers[st["id"]] = []

    for cat_id, cat_papers in groups.items():
        if cat_id == "other":
            category_general_papers["other"] = cat_papers
            continue

        cat = cat_info.get(cat_id)
        if not cat:
            category_general_papers[cat_id] = cat_papers
            continue

        cat_subtopic_ids = {st["id"] for st in cat.get("sub_topics", [])}

        papers_with_subtopics = set()
        for paper in cat_papers:
            paper_id = get_paper_id(paper)
            if paper_id in sub_topic_tags:
                paper_st_ids = set(sub_topic_tags[paper_id])
                matching_st_ids = paper_st_ids & cat_subtopic_ids
                if matching_st_ids:
                    papers_with_subtopics.add(paper_id)
                    for st_id in matching_st_ids:
                        if st_id in sub_topic_papers:
                            sub_topic_papers[st_id].append(paper)

        category_general_papers[cat_id] = [
            p for p in cat_papers if get_paper_id(p) not in papers_with_subtopics
        ]

    return sub_topic_papers, category_general_papers


def group_papers_by_topic(papers: list, taxonomy: dict) -> dict:
    """
    Group papers by taxonomy categories, themes, and sub-topics.

    Category assignment:
    1. Match using topic_relevance fields and title (substring matching)
    2. If no match, use abstract to find closest category

    Theme assignment:
    1. Match using topic_relevance fields and title
    2. If no match to any category OR theme, use abstract to find closest theme

    Sub-topic assignment:
    - Papers can match multiple sub-topics within their assigned category

    Returns:
        {
            "groups": {category_id: [paper_objects]},
            "themes": {theme_id: [paper_objects]},
            "sub_topic_tags": {paper_id: [sub_topic_ids]},
            "sub_topic_papers": {sub_topic_id: [paper_objects]},
            "category_general_papers": {category_id: [papers without sub-topics]}
        }
    """
    cat_info = {c["id"]: c for c in taxonomy["categories"]}

    def get_category_sort_key(cat):
        if "priority" in cat:
            return (cat["priority"], 0)
        has_subtopics = len(cat.get("sub_topics", [])) > 0
        return (1 if has_subtopics else 0, taxonomy["categories"].index(cat))

    sorted_categories = sorted(taxonomy["categories"], key=get_category_sort_key)
    category_ids = [c["id"] for c in sorted_categories]

    groups = {cat_id: [] for cat_id in category_ids}
    groups["other"] = []

    themes = {}
    for theme in taxonomy.get("theme", []):
        themes[theme["id"]] = []

    sub_topic_tags = {}

    for paper in papers:
        assigned_category = _assign_paper_to_category(
            paper, category_ids, cat_info, groups, taxonomy
        )
        _assign_paper_to_themes(paper, assigned_category, themes, taxonomy)
        _tag_paper_subtopics(paper, assigned_category, cat_info, sub_topic_tags)

    sub_topic_papers, category_general_papers = _build_subtopic_paper_lists(
        groups, cat_info, sub_topic_tags, taxonomy
    )

    return {
        "groups": groups,
        "themes": themes,
        "sub_topic_tags": sub_topic_tags,
        "sub_topic_papers": sub_topic_papers,
        "category_general_papers": category_general_papers,
    }


def get_breakthrough_score(paper: dict) -> int:
    """Extract breakthrough score from paper, defaulting to 5 if missing."""
    core = paper.get("core") or {}
    if not isinstance(core, dict):
        return 5
    ba = core.get("breakthrough_assessment", {})
    if not isinstance(ba, dict):
        return 5
    score = ba.get("score_1_to_10")
    if score is None:
        return 5
    return int(score)


def format_papers_for_prompt(papers: list) -> str:
    """Format papers for the topic summary prompt.

    For groups larger than BIG_GROUP_THRESHOLD, papers with breakthrough
    score below MIN_BREAKTHROUGH_SCORE are filtered out to keep prompt
    sizes manageable. The LLM sub-agent is expected to focus on the most
    impactful papers among those provided.
    """
    total_count = len(papers)
    if total_count > BIG_GROUP_THRESHOLD:
        filtered = [
            p for p in papers if get_breakthrough_score(p) >= MIN_BREAKTHROUGH_SCORE
        ]
        removed = total_count - len(filtered)
        papers = filtered
    else:
        removed = 0

    formatted = []
    if removed > 0:
        formatted.append(
            f"Note: Showing {len(papers)} of {total_count} papers "
            f"(filtered {removed} papers with breakthrough score "
            f"< {MIN_BREAKTHROUGH_SCORE}).\n"
        )
    for paper in papers:
        basics = paper.get("basics") or {}
        core = paper.get("core") or {}
        venue = paper.get("venue_info") or {}

        paper_id = paper.get("paper_num", "")
        title = basics.get("title", "") or paper.get("title", "")

        if isinstance(venue, dict):
            pub_date = (
                f"{venue.get('year', '')}-{venue.get('month', ''):02d}"
                if venue.get("month")
                else str(venue.get("year", ""))
            )
            venue_name = venue.get("venue", "arXiv")
        else:
            pub_date = ""
            venue_name = str(venue) if venue else "arXiv"

        abstract = (basics.get("abstract", "") or paper.get("abstract", ""))[:500]
        core_problem = (
            core.get("core_problem", {}).get("problem_statement", "")
            if isinstance(core, dict)
            else ""
        )
        key_novelty = core.get("key_novelty", {}) if isinstance(core, dict) else {}
        novelty_main = key_novelty.get("main_idea", "")
        novelty_points = key_novelty.get("explanation", [])
        eval_highlights = (
            core.get("evaluation_highlights", []) if isinstance(core, dict) else []
        )
        breakthrough = (
            core.get("breakthrough_assessment", {}).get("score_1_to_10", "")
            if isinstance(core, dict)
            else ""
        )

        formatted.append(f"""
### Paper ID: {paper_id}
**Title**: {title}
**Venue Info**: {venue_name}, {pub_date}
**Pub Date**: {pub_date}
**Link**: https://papers.lunadong.com/paper/{paper_id}

**Abstract**: {abstract}

**Core Problem**: {core_problem}

**Key Novelty**: {novelty_main}
{novelty_points}

**Evaluation Highlights**: {"; ".join(eval_highlights[:3]) if eval_highlights else "N/A"}

**Breakthrough Score**: {breakthrough}

---
""")
    return "\n".join(formatted)


def save_grouped_papers(
    result: dict, taxonomy: dict, output_dir: Path, area: str
) -> dict:
    """
    Save formatted paper files for each group.

    Returns summary of files created.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    files_created = []

    sub_topic_papers = result["sub_topic_papers"]
    category_general_papers = result["category_general_papers"]
    themes = result["themes"]

    # Save sub-topic papers
    for cat in taxonomy["categories"]:
        for st in cat.get("sub_topics", []):
            st_id = st["id"]
            st_papers = sub_topic_papers.get(st_id, [])
            if st_papers:
                papers_text = format_papers_for_prompt(st_papers)
                filepath = output_dir / f"subtopic_{st_id}_papers.txt"
                filepath.write_text(papers_text, encoding="utf-8")
                files_created.append(
                    {
                        "type": "sub_topic",
                        "id": st_id,
                        "path": str(filepath),
                        "count": len(st_papers),
                    }
                )

    # Save category general papers
    for cat in taxonomy["categories"]:
        cat_id = cat["id"]
        general_papers = category_general_papers.get(cat_id, [])
        if general_papers:
            papers_text = format_papers_for_prompt(general_papers)
            filepath = output_dir / f"category_{cat_id}_general_papers.txt"
            filepath.write_text(papers_text, encoding="utf-8")
            files_created.append(
                {
                    "type": "category_general",
                    "id": cat_id,
                    "path": str(filepath),
                    "count": len(general_papers),
                }
            )

    # Save "other" category
    other_papers = category_general_papers.get("other", [])
    if other_papers:
        papers_text = format_papers_for_prompt(other_papers)
        filepath = output_dir / "category_other_general_papers.txt"
        filepath.write_text(papers_text, encoding="utf-8")
        files_created.append(
            {
                "type": "category_general",
                "id": "other",
                "path": str(filepath),
                "count": len(other_papers),
            }
        )

    # Save theme papers
    for theme in taxonomy.get("theme", []):
        theme_id = theme["id"]
        theme_papers = themes.get(theme_id, [])
        if theme_papers:
            papers_text = format_papers_for_prompt(theme_papers)
            filepath = output_dir / f"theme_{theme_id}_papers.txt"
            filepath.write_text(papers_text, encoding="utf-8")
            files_created.append(
                {
                    "type": "theme",
                    "id": theme_id,
                    "path": str(filepath),
                    "count": len(theme_papers),
                }
            )

    return files_created


def main():
    parser = argparse.ArgumentParser(
        description="Group papers by taxonomy categories, themes, and sub-topics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python group_papers.py --area rag
  python group_papers.py --area rag --papers prompt_optimization/area_summaries/rag/papers_parsed.json
  python group_papers.py --area agents --taxonomy prompts/taxonomy/agents_taxonomy.json
        """,
    )
    parser.add_argument(
        "--area",
        "-a",
        required=True,
        help="Research area name (e.g., rag, agents, memory)",
    )
    parser.add_argument(
        "--papers",
        "-p",
        help="Path to papers_parsed.json (default: prompt_optimization/area_summaries/{area}/papers_parsed.json)",
    )
    parser.add_argument(
        "--taxonomy",
        "-t",
        help="Path to taxonomy JSON (default: prompts/taxonomy/{area}_taxonomy.json)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory for formatted papers (default: prompt_optimization/area_summaries/{area})",
    )
    parser.add_argument(
        "--summary-only",
        "-s",
        action="store_true",
        help="Only print summary, don't write files",
    )

    args = parser.parse_args()

    area = args.area
    papers_path = Path(
        args.papers or f"prompt_optimization/area_summaries/{area}/papers_parsed.json"
    )
    taxonomy_path = Path(args.taxonomy or f"prompts/taxonomy/{area}_taxonomy.json")
    output_dir = Path(args.output_dir or f"prompt_optimization/area_summaries/{area}")

    # Load papers
    if not papers_path.exists():
        print(f"Error: Papers file not found: {papers_path}", file=sys.stderr)
        print(
            "Run parse_papers.py first to generate papers_parsed.json", file=sys.stderr
        )
        sys.exit(1)

    with open(papers_path, encoding="utf-8") as f:
        papers_data = json.load(f)

    papers = papers_data.get("papers", [])
    if not papers:
        print(f"Error: No papers found in {papers_path}", file=sys.stderr)
        sys.exit(1)

    # Load taxonomy
    if not taxonomy_path.exists():
        print(f"Error: Taxonomy file not found: {taxonomy_path}", file=sys.stderr)
        print(
            "Run extract_topic_taxonomy skill to generate taxonomy JSON",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(taxonomy_path, encoding="utf-8") as f:
        taxonomy = json.load(f)

    # Group papers
    print(f"Grouping {len(papers)} papers by taxonomy...", file=sys.stderr)
    result = group_papers_by_topic(papers, taxonomy)

    # Print summary
    print("\n" + "=" * 70, file=sys.stderr)
    print(f"[SUMMARY] PAPER GROUPING SUMMARY ({area})", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    print("\nCategories (disjoint):", file=sys.stderr)
    for cat in taxonomy["categories"]:
        cat_id = cat["id"]
        total = len(result["groups"].get(cat_id, []))
        general = len(result["category_general_papers"].get(cat_id, []))
        print(f"  {cat['name']}: {total} total, {general} general", file=sys.stderr)
    other_count = len(result["groups"].get("other", []))
    print(f"  Other: {other_count}", file=sys.stderr)

    print("\nThemes (overlapping):", file=sys.stderr)
    for theme in taxonomy.get("theme", []):
        theme_id = theme["id"]
        count = len(result["themes"].get(theme_id, []))
        print(f"  {theme['name']}: {count}", file=sys.stderr)

    print("\nSub-topics:", file=sys.stderr)
    for cat in taxonomy["categories"]:
        for st in cat.get("sub_topics", []):
            st_id = st["id"]
            count = len(result["sub_topic_papers"].get(st_id, []))
            if count > 0:
                print(f"  {st['name']}: {count}", file=sys.stderr)

    # Save files
    if not args.summary_only:
        files_created = save_grouped_papers(result, taxonomy, output_dir, area)
        print(f"\nCreated {len(files_created)} files in {output_dir}:", file=sys.stderr)
        for f in files_created:
            print(
                f"  [{f['type']}] {f['id']}: {f['count']} papers -> {Path(f['path']).name}",
                file=sys.stderr,
            )

        # Save grouping result as JSON
        result_json = {
            "area": area,
            "total_papers": len(papers),
            "avg_breakthrough_score": papers_data.get("avg_breakthrough_score"),
            "year_range": (
                f"{papers_data['years'][0]}-{papers_data['years'][-1]}"
                if papers_data.get("years")
                else None
            ),
            "categories": {
                cat_id: len(papers) for cat_id, papers in result["groups"].items()
            },
            "category_general": {
                cat_id: len(papers)
                for cat_id, papers in result["category_general_papers"].items()
            },
            "themes": {
                theme_id: len(papers) for theme_id, papers in result["themes"].items()
            },
            "sub_topics": {
                st_id: len(papers)
                for st_id, papers in result["sub_topic_papers"].items()
                if papers
            },
            "files": files_created,
        }
        result_path = output_dir / "paper_groups.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=2)
        print(f"\nGrouping summary saved to: {result_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
