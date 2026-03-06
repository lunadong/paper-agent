#!/usr/bin/env python3
"""Generate a self-contained HTML area summary from JSON data files.

Reads topic summary JSONs, cross-topic analysis, taxonomy, and paper groups,
then renders a single HTML file with brief topic cards (basics, running example,
key insights) and collapsible full analysis (timeline, methods, benchmarks,
limitations, papers).

Usage:
    python generate_html.py \
        --area rag \
        --input-dir prompt_optimization/area_summaries/rag \
        --taxonomy prompts/taxonomy/rag_taxonomy.json \
        --output prompt_optimization/area_summaries/rag/area_summary.html
"""

import argparse
import glob
import json
import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path


# ============================================================
# Helpers
# ============================================================

PAPER_BASE_URL = "https://papers.lunadong.com/paper"

AREA_FULL_NAMES = {
    "rag": "Retrieval-Augmented Generation (RAG)",
    "factuality": "Factuality & Hallucination Detection",
    "agents": "LLM Agents",
    "memory": "Memory-Augmented LLMs",
    "p13n": "Personalization",
    "benchmark": "Benchmarks & Evaluation",
}


def e(text):
    """HTML-escape a string, handling None gracefully."""
    if text is None:
        return ""
    return escape(str(text))


def paper_link(paper_id, title, year=None):
    """Render a clickable paper link."""
    label = e(title)
    if year:
        label += f" ({year})"
    return (
        f'<a href="{PAPER_BASE_URL}/{paper_id}" '
        f'target="_blank" rel="noopener noreferrer">{label}</a>'
    )


def short_paper_name(title):
    """Extract a short display name from a paper title.

    If the title matches 'ShortName: Long Description', return 'ShortName'.
    Otherwise return None (caller should fall back to author-based label).
    """
    if not title:
        return None
    m = re.match(r"^([A-Z][A-Za-z0-9._-]+(?:\s?[A-Za-z0-9._-]+){0,2})\s*[:]", title)
    if m:
        return m.group(1).strip()
    m2 = re.match(r"^([A-Z][A-Za-z0-9-]+)\s", title)
    if m2 and len(m2.group(1)) >= 3 and any(c.isupper() for c in m2.group(1)[1:]):
        return m2.group(1)
    return None


def paper_link_short(paper):
    """Render a paper link from a dict with paper_id/title/year fields."""
    pid = paper.get("paper_id", "")
    title = paper.get("title", f"Paper {pid}")
    year = paper.get("year") or paper.get("pub_date", "")
    if isinstance(year, str) and len(year) > 4:
        year = year[:4]
    return paper_link(pid, title, year)


def paper_label_short(paper):
    """Return a short display label for a paper in tables.

    Uses the short name (e.g., 'QuCo-RAG') if the title has one,
    otherwise uses first author last name + 'et al.'.
    """
    title = paper.get("title", "") or paper.get("paper_title", "")
    sn = short_paper_name(title)
    if sn:
        return sn
    authors = paper.get("authors", "")
    if authors:
        first = authors.split(",")[0].strip() if isinstance(authors, str) else ""
        if first:
            parts = first.split()
            last = parts[-1] if parts else first
            return f"{last} et al."
    pid = paper.get("paper_id", "")
    if title:
        words = title.split()[:5]
        return " ".join(words) + ("..." if len(title.split()) > 5 else "")
    return f"Paper {pid}"


# Emoji mapping per topic type + index
CATEGORY_EMOJIS = ["\U0001f527", "\U0001f578\ufe0f", "\U0001f916", "\U0001f4e6"]
SUBTOPIC_EMOJIS = [
    "\U0001f3af",
    "\U0001f504",
    "\U0001f50d",
    "\U0001f4cb",
    "\u270d\ufe0f",
    "\U0001f517",
    "\u2699\ufe0f",
    "\U0001f4d0",
]
THEME_EMOJIS = ["\U0001f9e9", "\U0001f52c", "\U0001f3c6", "\U0001f4f1", "\U0001f4da"]


def assign_emoji(topic_type, index):
    if topic_type == "category_general":
        return CATEGORY_EMOJIS[index % len(CATEGORY_EMOJIS)]
    elif topic_type == "sub_topic":
        return SUBTOPIC_EMOJIS[index % len(SUBTOPIC_EMOJIS)]
    else:
        return THEME_EMOJIS[index % len(THEME_EMOJIS)]


def get_topic_order(taxonomy, paper_groups):
    """Return ordered list of (type, id, emoji) following taxonomy structure."""
    ordered = []
    cat_idx = 0
    st_idx = 0

    files_by_key = {}
    for fi in paper_groups.get("files", []):
        key = (fi["type"], fi["id"])
        files_by_key[key] = fi

    for cat in taxonomy.get("categories", []):
        cat_id = cat["id"]
        sub_topics = cat.get("sub_topics", [])
        if sub_topics:
            for st in sub_topics:
                st_id = st["id"]
                if ("sub_topic", st_id) in files_by_key:
                    ordered.append(
                        ("sub_topic", st_id, assign_emoji("sub_topic", st_idx))
                    )
                    st_idx += 1
        if ("category_general", cat_id) in files_by_key:
            ordered.append(
                ("category_general", cat_id, assign_emoji("category_general", cat_idx))
            )
            cat_idx += 1

    # Add "other" category before themes
    if ("category_general", "other") in files_by_key:
        ordered.append(("category_general", "other", "\U0001f4e6"))

    # Add themes, with survey last
    non_survey_themes = []
    survey_themes = []
    for theme in taxonomy.get("theme", []):
        theme_id = theme["id"]
        if ("theme", theme_id) in files_by_key:
            if "survey" in theme_id.lower():
                survey_themes.append(theme_id)
            else:
                non_survey_themes.append(theme_id)
    for theme_id in non_survey_themes + survey_themes:
        th_idx = len([o for o in ordered if o[0] == "theme"])
        ordered.append(("theme", theme_id, assign_emoji("theme", th_idx)))

    return ordered


def summary_file_key(topic_type, topic_id):
    """Map (type, id) to the expected summary JSON filename stem."""
    if topic_type == "sub_topic":
        return f"subtopic_{topic_id}"
    elif topic_type == "category_general":
        return f"category_{topic_id}"
    else:
        return f"theme_{topic_id}"


def find_transition(connections, from_name, to_name):
    """Find a transition sentence between two adjacent topics."""
    from_lower = from_name.lower()
    to_lower = to_name.lower()
    for conn in connections:
        ft = conn.get("from_topic", "").lower()
        tt = conn.get("to_topic", "").lower()
        if (from_lower in ft or ft in from_lower) and (
            to_lower in tt or tt in to_lower
        ):
            return conn.get("transition_sentence", conn.get("connection", ""))
    return None


def merge_glossaries(topic_summaries, cross_topic):
    """Merge and deduplicate glossary terms from all sources, sorted alphabetically."""
    seen = {}
    for ts in topic_summaries.values():
        for item in ts.get("glossary", []):
            term = item.get("term", "")
            if term and term.lower() not in seen:
                seen[term.lower()] = item
    for item in cross_topic.get("glossary", []):
        term = item.get("term", "")
        if term and term.lower() not in seen:
            seen[term.lower()] = item
    return sorted(seen.values(), key=lambda x: x.get("term", "").lower())


def linkify_text(text):
    """Convert markdown-style links [text](url) in text to HTML <a> tags."""
    if not text:
        return ""

    def _replace_md_link(m):
        link_text = m.group(1)
        url = m.group(2)
        return (
            f'<a href="{e(url)}" target="_blank" '
            f'rel="noopener noreferrer">{e(link_text)}</a>'
        )

    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", _replace_md_link, e(text))


def _shorten_md_paper_links(text):
    """Shorten markdown link text from full paper titles to short names.

    Converts [Full Paper Title](url) to [ShortName](url) using short_paper_name.
    Also handles patterns like 'Full Name ([ShortName](url), year)' by
    collapsing to 'ShortName ([ShortName](url), year)'.
    """
    if not text:
        return text

    def _shorten_link(m):
        link_text = m.group(1)
        url = m.group(2)
        sn = short_paper_name(link_text)
        if sn:
            return f"[{sn}]({url})"
        # Try first 5 words fallback for very long titles
        words = link_text.split()
        if len(words) > 6:
            return f"[{' '.join(words[:5])}...]({url})"
        return m.group(0)

    result = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", _shorten_link, text)

    # Collapse "Full Name ([ShortName](url), year)" -> "ShortName ([ShortName](url), year)"
    # Pattern: "Some Long Title ([\w-]+](url), 20XX)"
    result = re.sub(
        r"[A-Z][A-Za-z\s,:\-]+ (\(\[([A-Z][A-Za-z0-9._-]+(?:\s?[A-Za-z0-9._-]+){0,2})\])",
        lambda m: "(" + "[" + m.group(2) + "]",
        result,
    )
    return result


def css_path(_output_path):
    """Return CSS path for web serving.

    Returns /htmls/style.css for proper web serving from Flask.
    All generated HTML should be placed in web_interface/htmls/.
    """
    return "/htmls/style.css"


# ============================================================
# Phase 1 Helpers: Paper Year/ID Extraction
# ============================================================


def _extract_year_from_item(item):
    """Extract and normalize year from a paper item dict.

    Handles both 'year' and 'pub_date' fields, truncating to 4 chars if needed.
    Returns empty string if no valid year found.
    """
    yr = item.get("year") or item.get("pub_date", "")
    if isinstance(yr, str) and len(yr) >= 4:
        return yr[:4]
    return str(yr) if yr else ""


def _extract_paper_id(item):
    """Safely extract paper_id as int from item dict.

    Returns None if paper_id is missing or invalid.
    """
    pid = item.get("paper_id")
    if pid is None:
        return None
    try:
        return int(pid)
    except (ValueError, TypeError):
        return None


def _add_paper_to_map(pmap, item, overwrite=True):
    """Add a paper's id->year mapping to pmap.

    Args:
        pmap: dict to update (paper_id -> year)
        item: paper item dict with paper_id and year/pub_date
        overwrite: if False, skip if paper_id already in pmap
    """
    pid = _extract_paper_id(item)
    if pid is None:
        return
    if not overwrite and pid in pmap:
        return
    yr = _extract_year_from_item(item)
    pmap[pid] = yr


def _extract_short_name_link(item):
    """Extract (short_name, paper_id, year) from a paper item.

    Returns None if paper_id is missing or no short name can be derived.
    """
    pid = _extract_paper_id(item)
    if pid is None:
        return None
    title = item.get("title", "")
    sn = short_paper_name(title)
    if not sn:
        return None
    yr = _extract_year_from_item(item)
    return (sn, pid, yr)


def _add_paper_links_from_list(links, papers, overwrite=False):
    """Add short-name links from a list of paper items.

    Args:
        links: dict to update (short_name -> (paper_id, year))
        papers: list of paper item dicts
        overwrite: if False, skip if short_name already in links
    """
    for paper in papers:
        result = _extract_short_name_link(paper)
        if result is None:
            continue
        sn, pid, yr = result
        if overwrite or sn not in links:
            links[sn] = (pid, yr)


def _shorten_expanded_acronyms(text):
    """Shorten 'Full Name (ACRONYM, Paper N)' to 'ACRONYM (Paper N)' in text."""

    def _repl(m):
        acronym = m.group(1)
        rest = m.group(2)
        return f"{acronym} ({rest})"

    text = re.sub(
        r"[A-Z][A-Za-z\s,\-]+ \(([A-Z][A-Z0-9\-]+),\s*(Paper \d+|20\d{2})\)",
        _repl,
        text,
    )
    return text


def _build_paper_year_map(topic_summaries, cross_topic):
    """Build a comprehensive paper_id -> year mapping from all data sources.

    Collects papers from field_timeline, significant_papers, methods, and benchmarks.
    """
    pmap = {}

    # 1. Field timeline landmark papers (these take priority, so overwrite=True)
    ft = cross_topic.get("field_timeline", {})
    for period in ft.get("periods", []):
        for lp in period.get("landmark_papers", []):
            _add_paper_to_map(pmap, lp, overwrite=True)

    # 2. Topic summaries: significant_papers, methods, benchmarks (no overwrite)
    for ts in topic_summaries.values():
        # Significant papers
        for sp in ts.get("significant_papers", []):
            _add_paper_to_map(pmap, sp, overwrite=False)

        # Representative papers from methods
        for method in ts.get("methods", []):
            for rp in method.get("representative_papers", []):
                _add_paper_to_map(pmap, rp, overwrite=False)

        # Best results from benchmarks
        bm_data = ts.get("benchmark_results", {})
        for bm in bm_data.get("primary_benchmarks", []):
            best = bm.get("best_result", {})
            if isinstance(best, dict):
                _add_paper_to_map(pmap, best, overwrite=False)

    return pmap


def _replace_paper_refs_with_year(text, paper_year_map):
    """Replace (Paper N) and 'Paper N' references with (year) using paper data."""

    def _repl_parens(m):
        pid = int(m.group(1))
        year = paper_year_map.get(pid)
        if year:
            return f"({year})"
        return m.group(0)

    def _repl_bare(m):
        pid = int(m.group(1))
        year = paper_year_map.get(pid)
        if year:
            return f"({year})"
        return m.group(0)

    result = re.sub(r"\(Paper\s+(\d+)\)", _repl_parens, text)
    result = re.sub(r"(?<!\()Paper\s+(\d+)(?!\))", _repl_bare, result)
    return result


def _build_timeline_paper_links(field_timeline):
    """Build mapping of paper short name -> (paper_id, year) from landmark_papers."""
    links = {}
    for period in field_timeline.get("periods", []):
        _add_paper_links_from_list(
            links, period.get("landmark_papers", []), overwrite=True
        )
    return links


def _extract_acronyms_from_developments(field_timeline, paper_year_map):
    """Extract acronym->link mappings from development text patterns.

    Parses "Full Name (ACRONYM, Paper N)" patterns from timeline developments.
    Returns dict of acronym -> (paper_id, year).
    """
    acronym_links = {}
    for period in field_timeline.get("periods", []):
        for dev in period.get("key_developments", period.get("developments", [])):
            txt = (
                dev
                if isinstance(dev, str)
                else dev.get("description", dev.get("development", ""))
            )
            for match in re.finditer(
                r"[A-Z][A-Za-z\s,\-]+ \(([A-Z][A-Z0-9\-]+),\s*Paper (\d+)\)", txt
            ):
                acronym, pid = match.group(1), int(match.group(2))
                yr = paper_year_map.get(pid, "")
                if acronym not in acronym_links:
                    acronym_links[acronym] = (pid, str(yr))
    return acronym_links


def _build_global_paper_links(topic_summaries, field_timeline):
    """Build name->link mapping from ALL papers across all topic summaries.

    Collects links from: timeline landmark_papers, development acronyms,
    topic landmark_papers, and method representative_papers.
    """
    # 1. Timeline landmark papers (highest priority)
    links = _build_timeline_paper_links(field_timeline)

    # 2. Acronyms from timeline development text
    paper_year_map = _build_paper_year_map(
        topic_summaries, {"field_timeline": field_timeline}
    )
    acronym_links = _extract_acronyms_from_developments(field_timeline, paper_year_map)
    for acronym, link_data in acronym_links.items():
        if acronym not in links:
            links[acronym] = link_data

    # 3. Topic summaries: landmark_papers and method representative_papers
    for ts in topic_summaries.values():
        _add_paper_links_from_list(
            links, ts.get("landmark_papers", []), overwrite=False
        )
        for method in ts.get("methods", []):
            _add_paper_links_from_list(
                links, method.get("representative_papers", []), overwrite=False
            )

    return links


def _linkify_timeline_papers(text, timeline_links):
    """Replace known paper names with clickable links in timeline text."""
    for name, (pid, year) in sorted(timeline_links.items(), key=lambda x: -len(x[0])):
        pattern = re.escape(name) + r"\s*\(" + re.escape(year) + r"\)"
        link = (
            f'<a href="{PAPER_BASE_URL}/{pid}" '
            f'target="_blank" rel="noopener noreferrer">'
            f"{name} ({year})</a>"
        )
        text = re.sub(pattern, link, text)
    return text


# ============================================================
# Component Functions \u2014 Global Sections
# ============================================================


def render_header(area, stats):
    total = stats.get("total_papers", 0)
    yr = stats.get("year_range", "")
    avg = stats.get("avg_breakthrough_score", "")
    topics_count = len(stats.get("papers_by_topic", {}))
    full_name = AREA_FULL_NAMES.get(area.lower(), area.upper())

    return f"""
<header class="header">
  <div class="container">
    <h1>\U0001f50d {e(full_name)}</h1>
    <p class="subtitle">Comprehensive Research Area Summary</p>
    <div class="stats-banner">
      <div class="stat-item"><div class="stat-value">{total}</div><div class="stat-label">Papers</div></div>
      <div class="stat-item"><div class="stat-value">{topics_count}</div><div class="stat-label">Topic Groups</div></div>
      <div class="stat-item"><div class="stat-value">{avg}</div><div class="stat-label">Avg Breakthrough Score</div></div>
      <div class="stat-item"><div class="stat-value">{e(str(yr))}</div><div class="stat-label">Year Range</div></div>
    </div>
  </div>
</header>"""


def render_area_overview(overview, area):
    definition = e(overview.get("definition", ""))
    motivation = e(overview.get("motivation", ""))
    paradigms = overview.get("key_paradigms", [])
    full_name = AREA_FULL_NAMES.get(area.lower(), area.upper())
    short = full_name.split("(")[0].strip() if "(" in full_name else full_name

    paradigm_html = ""
    for p in paradigms:
        name = e(p.get("paradigm_name", p.get("name", p.get("paradigm", ""))))
        desc = e(p.get("description", ""))
        link = p.get("link", "")
        if link:
            name_html = f'<a href="{link}" style="color:inherit;text-decoration:underline;">{name}</a>'
        else:
            name_html = name
        paradigm_html += f"""
      <div class="paradigm-card"><strong>{name_html}</strong><p>{desc}</p></div>"""

    return f"""
<div class="container">
<div class="area-overview-box">
  <h2>\U0001f4d6 What is {e(short)}?</h2>
  <p class="definition">{definition}</p>
  <h3>\U0001f4a1 Why it Matters</h3>
  <p class="motivation" style="margin-bottom:24px;">{motivation}</p>
  <h3>\U0001f3af Key Paradigms</h3>
  <div class="paradigm-grid">{paradigm_html}
  </div>
</div>
</div>"""


def render_field_timeline(field_timeline, paper_year_map=None, timeline_links=None):
    periods = field_timeline.get("periods", [])
    if paper_year_map is None:
        paper_year_map = {}
    if timeline_links is None:
        timeline_links = {}

    periods_html = ""
    for p in periods:
        period_str = e(p.get("period", ""))
        name = e(p.get("period_name", p.get("name", p.get("theme", ""))))
        theme = e(p.get("theme", ""))
        devs = p.get("key_developments", p.get("developments", []))
        dev_items = ""
        for d in devs:
            if isinstance(d, str):
                cleaned = _replace_paper_refs_with_year(
                    _shorten_expanded_acronyms(d), paper_year_map
                )
                linked = _linkify_timeline_papers(linkify_text(cleaned), timeline_links)
                dev_items += f"\n          <li>{linked}</li>"
            elif isinstance(d, dict):
                desc = d.get("description", d.get("development", ""))
                cleaned = _replace_paper_refs_with_year(
                    _shorten_expanded_acronyms(desc), paper_year_map
                )
                linked = _linkify_timeline_papers(linkify_text(cleaned), timeline_links)
                dev_items += f"\n          <li>{linked}</li>"
        shifts = p.get("paradigm_shifts", [])
        shift_html = ""
        if shifts:
            tags = " ".join(
                f'<span class="paradigm-shift-tag">{e(s)}</span>' for s in shifts[:4]
            )
            shift_html = f'<div class="paradigm-shifts">{tags}</div>'
        periods_html += f"""
    <div class="timeline-period">
      <div class="period-header">
        <span class="period-dates">{period_str}</span>
        <span class="period-name">{name}</span>
      </div>
      <div class="period-content">
        <p class="period-theme">{theme}</p>
        <ul class="period-developments">{dev_items}
        </ul>
        {shift_html}
      </div>
    </div>"""

    narrative_html = ""

    return f"""
<div class="container">
<div class="section field-timeline">
  <h2>\U0001f4c5 Field Evolution Timeline</h2>
  {narrative_html}
  {periods_html}
</div>
</div>"""


def render_toc(ordered_topics, topic_summaries, taxonomy):
    cats, subs, themes = _categorize_ordered_topics(ordered_topics, topic_summaries)
    pipeline_section = _build_pipeline_section(cats, subs, taxonomy)
    theme_section = _build_theme_section(themes)
    cross_section = _build_cross_topic_section()

    return f"""
<div class="container">
<div class="section">
  <h2>\U0001f4d1 Table of Contents</h2>
  <div class="toc">{pipeline_section}{theme_section}{cross_section}
  </div>
</div>
</div>"""


def _categorize_ordered_topics(ordered_topics, topic_summaries):
    """Categorize ordered topics into cats, subs, and themes lists.

    Returns tuple of (cats, subs, themes) where each is a list of (emoji, name, anchor).
    """
    cats = []
    subs = []
    themes = []
    for topic_type, topic_id, emoji_icon in ordered_topics:
        key = summary_file_key(topic_type, topic_id)
        ts = topic_summaries.get(key)
        if not ts:
            continue
        name = ts.get("topic_name", topic_id)
        anchor = ts.get("topic_id", topic_id)
        entry = (emoji_icon, name, anchor)
        if topic_type == "category_general":
            cats.append(entry)
        elif topic_type == "sub_topic":
            subs.append(entry)
        else:
            themes.append(entry)
    return cats, subs, themes


def _build_pipeline_section(cats, subs, taxonomy):
    """Build the pipeline categories TOC section HTML."""
    pipeline_html = ""
    for cat in taxonomy.get("categories", []):
        cat_id = cat["id"]
        cat_entry = _find_matching_cat_entry(cats, cat_id)
        sub_ids = [s["id"] for s in cat.get("sub_topics", [])]
        matched_subs = [(em, nm, anc) for em, nm, anc in subs if anc in sub_ids]

        if cat_entry:
            pipeline_html += f'\n          <li><a href="#{e(cat_entry[2])}">{cat_entry[0]} {e(cat_entry[1])}</a></li>'
        for _s_em, s_nm, s_anc in matched_subs:
            pipeline_html += f'\n          <li class="toc-sub"><a href="#{e(s_anc)}">\u2192 {e(s_nm)}</a></li>'

        # Fallback matching if no direct match found
        if not cat_entry and not matched_subs:
            for em, nm, anc in cats:
                if cat_id.replace("_", "") in anc.replace("_", ""):
                    pipeline_html += (
                        f'\n          <li><a href="#{e(anc)}">{em} {e(nm)}</a></li>'
                    )

    if not pipeline_html:
        return ""
    return f"""
      <div class="toc-section">
        <h3>Pipeline Categories</h3>
        <ul>{pipeline_html}
        </ul>
      </div>"""


def _find_matching_cat_entry(cats, cat_id):
    """Find a category entry that matches the given cat_id."""
    for em, nm, anc in cats:
        if anc == cat_id or cat_id in anc:
            return (em, nm, anc)
    return None


def _build_theme_section(themes):
    """Build the research themes TOC section HTML."""
    if not themes:
        return ""
    theme_items = ""
    for em, nm, anc in themes:
        theme_items += f'\n          <li><a href="#{e(anc)}">{em} {e(nm)}</a></li>'
    return f"""
      <div class="toc-section">
        <h3>Research Themes</h3>
        <ul>{theme_items}
        </ul>
      </div>"""


def _build_cross_topic_section():
    """Build the cross-topic analysis TOC section HTML."""
    return """
      <div class="toc-section">
        <h3>Cross-Topic Analysis</h3>
        <ul>
          <li><a href="#recommendations">\U0001f4a1 Practical Recommendations</a></li>
          <li><a href="#takeaways">\U0001f3af Key Takeaways</a></li>
          <li><a href="#trends">\U0001f680 Emerging Trends</a></li>
          <li><a href="#opportunities">\U0001f52d Research Opportunities</a></li>
          <li><a href="#distribution">\U0001f4ca Topic Distribution</a></li>
          <li><a href="#glossary">\U0001f4da Glossary</a></li>
        </ul>
      </div>"""


def render_recommendations(recs):
    if not recs:
        return ""
    rows = ""
    for r in recs:
        priority = r.get("priority", "Medium")
        css_cls = (
            f"priority-{priority.lower()}"
            if priority.lower() in ("high", "medium", "low")
            else "priority-medium"
        )
        text = e(r.get("recommendation", ""))
        evidence = e(r.get("supporting_evidence", ""))
        rows += f"""
        <tr>
          <td><span class="{css_cls}">{e(priority)}</span></td>
          <td>{text}</td>
          <td>{evidence}</td>
        </tr>"""

    return f"""
<div class="container">
<div class="section" id="recommendations">
  <h2>\U0001f3af Practical Recommendations</h2>
  <table class="rec-table">
    <thead><tr><th>Priority</th><th>Recommendation</th><th>Evidence</th></tr></thead>
    <tbody>{rows}
    </tbody>
  </table>
</div>
</div>"""


def render_takeaways(takeaways):
    if not takeaways:
        return ""
    cards = ""
    for t in takeaways:
        emoji_icon = e(t.get("emoji", "\U0001f4a1"))
        title = e(t.get("title", ""))
        desc = e(t.get("description", ""))
        one_liner = t.get("one_liner", "")
        liner_html = f'<p class="one-liner">{e(one_liner)}</p>' if one_liner else ""
        cards += f"""
      <div class="takeaway-card">
        <div class="emoji">{emoji_icon}</div>
        <h3>{title}</h3>
        <p>{desc}</p>
        {liner_html}
      </div>"""

    return f"""
<div class="container">
<div class="section" id="takeaways">
  <h2>\U0001f511 Key Takeaways</h2>
  <div class="takeaways-grid">{cards}
  </div>
</div>
</div>"""


def render_trends(trends):
    if not trends:
        return ""
    items = ""
    for t in trends:
        trend_text = e(t.get("trend", ""))
        evidence = e(t.get("evidence", ""))
        papers = t.get("supporting_papers", [])
        paper_links = ", ".join(paper_link_short(p) for p in papers) if papers else ""
        paper_html = (
            f'<p class="trend-papers">\U0001f4c4 {paper_links}</p>'
            if paper_links
            else ""
        )
        items += f"""
      <div class="trend-item">
        <h3>{trend_text}</h3>
        <p>{evidence}</p>
        {paper_html}
      </div>"""

    return f"""
<div class="container">
<div class="section" id="trends">
  <h2>\U0001f680 Emerging Trends</h2>
  {items}
</div>
</div>"""


def render_opportunities(opps):
    if not opps:
        return ""
    items = ""
    for o in opps:
        title = e(o.get("opportunity", ""))
        rationale = e(o.get("rationale", ""))
        difficulty = o.get("difficulty", "Medium")
        impact = o.get("potential_impact", o.get("impact", "Medium"))
        items += f"""
      <div class="opportunity-item">
        <h3>{title}</h3>
        <p>{rationale}</p>
        <span class="difficulty-badge difficulty-{difficulty.lower()}" >Difficulty: {e(difficulty)}</span>
        <span class="impact-badge impact-{impact.lower()}">Impact: {e(impact)}</span>
      </div>"""

    return f"""
<div class="container">
<div class="section" id="opportunities">
  <h2>\U0001f52d Research Opportunities</h2>
  {items}
</div>
</div>"""


def render_benchmark_leaderboard(benchmarks):
    if not benchmarks:
        return ""
    cards = ""
    for bm in benchmarks:
        name = e(bm.get("benchmark_name", ""))
        desc = e(bm.get("what_it_measures", ""))
        metric = e(bm.get("metric", ""))
        results = bm.get("top_results", [])
        rank_icons = ["\U0001f947", "\U0001f948", "\U0001f949"]
        rows = ""
        for i, r in enumerate(results):
            rank = rank_icons[i] if i < 3 else str(i + 1)
            method = e(r.get("method", ""))
            value = e(r.get("value", ""))
            rel = r.get("relative_improvement", "")
            score_cell = value
            if rel:
                rel_clean = e(rel)
                # Skip relative_improvement if it largely duplicates the value text
                # e.g. "+17.67% EM over greedy decoding" vs "+17.67% EM over standard greedy decoding"
                val_nums = set(re.findall(r"[\d.]+%?", value))
                rel_nums = set(re.findall(r"[\d.]+%?", rel_clean))
                if val_nums and val_nums == rel_nums:
                    pass  # duplicate -- skip
                elif rel_clean.strip() in value:
                    pass  # substring -- skip
                else:
                    score_cell += f" \u2014 {rel_clean}"
            pid = r.get("paper_id", "")
            ptitle = r.get("paper_title", "")
            year = r.get("year", "")
            plabel = paper_label_short(r) if ptitle else ptitle
            paper_cell = paper_link(pid, plabel, year) if pid else e(plabel)
            rows += f"""
            <tr><td>{rank}</td><td>{method}</td><td>{score_cell}</td><td>{paper_cell}</td><td>{year}</td></tr>"""

        cards += f"""
      <div class="benchmark-card">
        <h3>{name}</h3>
        <p class="benchmark-description">{desc} (Metric: {metric})</p>
        <table class="benchmark-table">
          <thead><tr><th>Rank</th><th>Method</th><th>Score</th><th>Paper</th><th>Year</th></tr></thead>
          <tbody>{rows}
          </tbody>
        </table>
      </div>
"""

    return f"""
<div class="container">
<div class="section benchmark-leaderboard" id="leaderboard">
  <h2>\U0001f3c6 Benchmark Leaderboard</h2>
  {cards}
</div>
</div>"""


def render_distribution(paper_groups, taxonomy):  # noqa: unused taxonomy kept for future use
    files = paper_groups.get("files", [])
    if not files:
        return ""
    total = max(paper_groups.get("total_papers", 1), 1)

    bars = ""
    for fi in files:
        name = fi.get("id", "").replace("_", " ").title()
        count = fi.get("count", 0)
        pct = round(count / total * 100, 1)
        bars += f"""
      <div class="topic-bar">
        <span class="topic-bar-label">{e(name)}</span>
        <div class="topic-bar-bg" style="width: {max(pct, 1)}%;">
          <span class="topic-bar-value">{count} ({pct}%)</span>
        </div>
      </div>
"""

    return f"""
<div class="container">
<details class="section" id="distribution">
  <summary><h2 style="display:inline;">\U0001f4ca Topic Distribution</h2></summary>
  <div class="topic-distribution">{bars}
  </div>
</details>
</div>"""


def render_glossary(glossary_items):
    if not glossary_items:
        return ""
    items = ""
    for g in glossary_items:
        term = e(g.get("term", ""))
        defn = e(g.get("definition", ""))
        items += f"""
      <div class="glossary-item"><dt>{term}</dt><dd>{defn}</dd></div>"""

    return f"""
<details class="glossary-section container" id="glossary">
  <summary>\U0001f4da Glossary of Terms ({len(glossary_items)} terms)</summary>
  <div class="glossary-grid">{items}
  </div>
</details>"""


def render_footer(area, stats):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = stats.get("total_papers", 0)
    return f"""
<footer class="footer container">
  <p>Generated on {now} \u00b7 {total} papers \u00b7 Area: {e(area.upper())}</p>
  <p>Paper links: <a href="{PAPER_BASE_URL}" target="_blank" rel="noopener noreferrer">{PAPER_BASE_URL}</a></p>
</footer>"""


# ============================================================
# Component Functions \u2014 Topic Card (Brief)
# ============================================================


def render_basics_box(overview):
    definition = e(overview.get("definition", ""))
    motivation = e(overview.get("motivation", ""))
    baseline = e(overview.get("baseline", ""))
    challenges = overview.get("key_challenges", [])

    challenge_items = ""
    for c in challenges:
        challenge_items += f"\n        <li>{e(c)}</li>"

    return f"""
      <div class="topic-overview">
        <p><strong>What:</strong> {definition}</p>
        <p><strong>Why:</strong> {motivation}</p>
        <p><strong>Baseline:</strong> {baseline}</p>
        <ul class="challenge-list">{challenge_items}
        </ul>
      </div>"""


def render_running_example(example):
    if not example:
        return ""
    query = e(example.get("example_query", ""))
    baseline = e(example.get("baseline_behavior", ""))
    challenge = e(example.get("challenge_illustration", ""))
    solutions = example.get("method_solutions", [])

    solutions_html = ""
    for i, sol in enumerate(solutions):
        name = e(sol.get("method_name", f"Method {i + 1}"))
        how = e(sol.get("how_it_helps", ""))
        if i < 3:
            solutions_html += f"""
          <div class="solution-item">
            <span class="solution-name">\u2705 {name}:</span>
            <span class="solution-desc">{how}</span>
          </div>"""
        elif i == 3:
            solutions_html += (
                "\n          <details><summary>Show more solutions</summary>"
            )
            solutions_html += f"""
            <div class="solution-item">
              <span class="solution-name">\u2705 {name}:</span>
              <span class="solution-desc">{how}</span>
            </div>"""
        else:
            solutions_html += f"""
            <div class="solution-item">
              <span class="solution-name">\u2705 {name}:</span>
              <span class="solution-desc">{how}</span>
            </div>"""

    if len(solutions) > 3:
        solutions_html += "\n          </details>"

    return f"""
      <div class="running-example">
        <h3>\U0001f9ea Running Example</h3>
        <div class="example-query">\u2753 {query}</div>
        <p><strong>Baseline:</strong> {baseline}</p>
        <p><strong>Challenge:</strong> {challenge}</p>
        {solutions_html}
      </div>"""


def render_key_insights(insights):
    if not insights:
        return ""
    cards = ""
    for ins in insights:
        text = (
            ins
            if isinstance(ins, str)
            else ins.get("insight", ins.get("description", str(ins)))
        )
        cards += f"""
        <div class="insight-card"><p>\U0001f4a1 {e(text)}</p></div>"""

    return f"""
      <h3 style="font-size:1.1rem;color:#374151;margin-bottom:12px;">\U0001f4a1 Key Insights</h3>
      <div class="insight-cards">{cards}
      </div>"""


# ============================================================
# Component Functions \u2014 Topic Card (Full / Expanded)
# ============================================================


def render_topic_timeline(timeline):
    if not timeline:
        return ""
    periods = timeline.get("periods", [])
    trend = timeline.get("trend_summary", "")

    periods_html = ""
    for _i, p in enumerate(periods):
        period_str = e(p.get("period", ""))
        theme = e(p.get("theme", ""))
        shift = p.get("paradigm_shift", "")
        devs = p.get("key_developments", p.get("developments", []))
        dev_items = ""
        for d in devs:
            if isinstance(d, str):
                dev_items += f"\n              <li>{linkify_text(_shorten_md_paper_links(d))}</li>"
            elif isinstance(d, dict):
                desc = d.get("description", d.get("development", ""))
                dev_items += f"\n              <li>{linkify_text(_shorten_md_paper_links(desc))}</li>"
        shift_html = (
            f'<p style="font-size:0.85rem;color:var(--secondary);margin-top:6px;">\U0001f500 <em>{e(shift)}</em></p>'
            if shift
            else ""
        )

        period_block = f"""
          <div class="timeline-period">
            <div class="period-header">
              <span class="period-dates">{period_str}</span>
              <span class="period-name">{theme}</span>
            </div>
            <div class="period-content">
              <ul class="period-developments">{dev_items}
              </ul>
              {shift_html}
            </div>
          </div>"""

        periods_html += period_block

    trend_html = (
        f'<p style="font-size:0.88rem;color:var(--gray-500);margin-top:4px;margin-bottom:18px;"><em>{e(trend)}</em></p>'
        if trend
        else ""
    )

    return f"""
        <div class="topic-timeline">
          <h3>\U0001f4c5 Timeline</h3>
          {trend_html}
          {periods_html}
        </div>"""


def render_subtopics_grid(subtopics):
    if not subtopics:
        return ""
    cards = ""
    for st in subtopics:
        name = e(st.get("sub_topic_name", st.get("name", "")))
        desc = e(st.get("description", ""))
        count = st.get("paper_count", 0)
        methods = st.get("key_methods", [])
        method_tags = " ".join(
            f'<span class="method-tag">{e(m)}</span>'
            for m in (methods[:4] if isinstance(methods, list) else [])
        )
        cards += f"""
        <div class="subtopic-card">
          <h4>{name}</h4>
          <p class="paper-count">{count} papers</p>
          <p style="font-size:0.85rem;color:var(--gray-600);margin-bottom:6px;">{desc}</p>
          <div class="methods">{method_tags}</div>
        </div>"""

    return f"""
        <h3 style="font-size:1.1rem;color:var(--gray-700);margin-bottom:12px;">\U0001f4c2 Sub-topics</h3>
        <div class="subtopic-grid">{cards}
        </div>"""


def _render_paper_short_links(papers, limit=5):
    """Render paper links using short names for table cells."""
    links = []
    for p in papers[:limit]:
        pid = p.get("paper_id", "")
        label = paper_label_short(p)
        year = p.get("year") or p.get("pub_date", "")
        if isinstance(year, str) and len(year) > 4:
            year = year[:4]
        # When label is a "Paper N" fallback, use short_paper_name from title
        # or just the year to avoid _replace_paper_refs_with_year making "(year) (year)"
        # label already uses paper_label_short with 5-word fallback
        if year and str(year) in label:
            yr_str = ""
        else:
            yr_str = f" ({year})" if year else ""
        links.append(
            f'<a href="{PAPER_BASE_URL}/{pid}" '
            f'target="_blank" rel="noopener noreferrer">{e(label)}{yr_str}</a>'
        )
    return ", ".join(links)


def render_methods_table(methods):
    if not methods:
        return ""
    rows = ""
    for m in methods[:5]:
        raw_name = m.get("method_name", "")
        raw_name = re.sub(r"\s*\([^)]*\)\s*$", "", raw_name).strip()
        name = e(raw_name)
        year = m.get("first_appeared", m.get("latest_advancement", ""))
        if isinstance(year, str) and len(year) > 4:
            year = year[:4]
        key_idea = e(m.get("key_idea", m.get("summary", "")))
        improves = e(m.get("improves_on", ""))
        papers = m.get("representative_papers", [])
        paper_links = _render_paper_short_links(papers, limit=8)

        rows += f"""
          <tr>
            <td><strong>{name}</strong></td>
            <td>{key_idea}</td>
            <td>{improves}</td>
            <td>{paper_links}</td>
          </tr>"""

    return f"""
        <h3 style="font-size:1.1rem;color:var(--gray-700);margin-top:24px;margin-bottom:12px;">\U0001f52c Key Methods</h3>
        <table class="methods-table">
          <thead><tr><th>Method</th><th>Key Innovation</th><th>Improves On</th><th>Papers</th></tr></thead>
          <tbody>{rows}
          </tbody>
        </table>"""


def render_benchmark_results(benchmark_data):
    if not benchmark_data:
        return ""
    benchmarks = benchmark_data.get("primary_benchmarks", [])
    if not benchmarks:
        return ""

    rows = ""
    for bm in benchmarks:
        name = e(bm.get("benchmark_name", ""))
        metric = e(bm.get("metric", ""))
        best = bm.get("best_result", {})
        if not best and bm.get("top_results"):
            best = bm["top_results"][0]
        if isinstance(best, dict):
            value = e(best.get("value", ""))
            paper_id = best.get("paper_id", "")
            paper_title = best.get("paper_title", "")
            label = (
                paper_label_short(best) if paper_title else e(best.get("method", ""))
            )
            yr = best.get("year") or best.get("pub_date", "")
            if isinstance(yr, str) and len(yr) > 4:
                yr = yr[:4]
            # label already uses paper_label_short with 5-word fallback
            # Avoid duplicate year if label already contains it
            if yr and str(yr) in label:
                yr_str = ""
            else:
                yr_str = f" ({yr})" if yr else ""
            if paper_id:
                paper_cell = (
                    f'<a href="{PAPER_BASE_URL}/{paper_id}" '
                    f'target="_blank" rel="noopener noreferrer">{e(label)}{yr_str}</a>'
                )
            else:
                paper_cell = e(label)
        else:
            value = e(str(best))
            paper_cell = ""
        rows += f"""
          <tr><td>{name}</td><td>{metric}</td><td>{value}</td><td>{paper_cell}</td></tr>"""

    return f"""
        <h3 style="font-size:1.1rem;color:var(--gray-700);margin-bottom:12px;">\U0001f4ca Benchmark Results</h3>
        <table class="benchmark-table">
          <thead><tr><th>Benchmark</th><th>Metric</th><th>Best Result</th><th>Paper</th></tr></thead>
          <tbody>{rows}
          </tbody>
        </table>"""


def render_limitations(limitations):
    if not limitations:
        return ""
    items = ""
    for lim in limitations:
        if isinstance(lim, str):
            items += f"\n          <li>{e(lim)}</li>"
        elif isinstance(lim, dict):
            text = e(lim.get("limitation", ""))
            affected = lim.get("affected_methods", [])
            solutions = e(lim.get("potential_solutions", ""))
            affected_str = ", ".join(e(m) for m in affected) if affected else ""
            detail = ""
            if affected_str:
                detail += f" <em style='font-size:0.82rem;color:var(--gray-500);'>(affects: {affected_str})</em>"
            if solutions:
                detail += f" <br><span style='font-size:0.82rem;color:var(--success);'>Potential fix: {solutions}</span>"
            items += f"\n          <li><strong>{text}</strong>{detail}</li>"

    return f"""
        <div class="limitations-section">
          <h3>\u26a0\ufe0f Known Limitations ({len(limitations)})</h3>
          <ul class="limitations-list">{items}
          </ul>
        </div>"""


def render_paper_list(papers, folded=True):
    if not papers:
        return ""
    items = ""
    for p in papers:
        pid = p.get("paper_id", "")
        title = p.get("title", f"Paper {pid}")
        pub_date = p.get("pub_date", "")
        score = p.get("breakthrough_score", "")
        link = paper_link(pid, title)
        score_html = ""
        if score:
            cls = "score-high" if score >= 7 else "score-mid"
            score_html = f' <span class="score-badge {cls}">{score}</span>'
        items += f"\n          <li>{link} ({e(str(pub_date))}){score_html}</li>"

    if not folded:
        return f"""
        <div class="paper-list-open">
          <ul class="paper-list">{items}
          </ul>
        </div>"""
    return f"""
        <details class="paper-details">
          <summary>\U0001f4da View major papers in this topic ({len(papers)})</summary>
          <ul class="paper-list">{items}
          </ul>
        </details>"""


# ============================================================
# Topic Card Assembly
# ============================================================


def render_topic_card(topic_summary, emoji_icon, topic_type=""):
    topic_id = topic_summary.get("topic_id", "")
    topic_name = topic_summary.get("topic_name", topic_id)

    if topic_type == "theme" and "survey" in topic_id.lower():
        survey_papers = sorted(
            topic_summary.get("significant_papers", []),
            key=lambda p: p.get("pub_date", p.get("year", "9999")),
        )
        papers_html = render_paper_list(survey_papers, folded=False)
        return f"""
<div class="topic-section container" id="{e(topic_id)}">
  <div class="topic-header">
    <span class="topic-emoji">{emoji_icon}</span>
    <h2>{e(topic_name)}</h2>
  </div>
  {papers_html}
</div>"""

    timeline_data = topic_summary.get("timeline", {})
    progress = timeline_data.get("overall_progress", "")
    progress_html = ""
    if progress:
        progress_html = f"""
      <div class="overall-progress">
        <h3>\U0001f4c8 Overall Progress</h3>
        <p>{e(progress)}</p>
      </div>"""

    subtopics_html = render_subtopics_grid(topic_summary.get("sub_topics", []))

    brief = (
        render_basics_box(topic_summary.get("overview", {}))
        + render_running_example(topic_summary.get("running_example", {}))
        + progress_html
        + subtopics_html
        + render_key_insights(topic_summary.get("key_insights", []))
    )

    full = (
        render_topic_timeline(topic_summary.get("timeline", {}))
        + render_methods_table(topic_summary.get("methods", []))
        + render_benchmark_results(topic_summary.get("benchmark_results", {}))
        + render_limitations(topic_summary.get("limitations", []))
        + render_paper_list(topic_summary.get("significant_papers", []))
    )

    return f"""
<div class="topic-section container" id="{e(topic_id)}">
  <div class="topic-header">
    <span class="topic-emoji">{emoji_icon}</span>
    <h2>{e(topic_name)}</h2>
  </div>
  <div class="topic-brief">
    {brief}
  </div>
  <details class="topic-full">
    <summary>\U0001f4d6 Show full analysis (timeline, methods, benchmarks)</summary>
    <div class="topic-full-content">
      {full}
    </div>
  </details>
</div>"""


def render_topic_transition(transition_text):
    if not transition_text:
        return ""
    return f"""
<div class="topic-transition">
  <p class="transition-text">\U0001f4a1 {e(transition_text)}</p>
</div>"""


# ============================================================
# Data Loading
# ============================================================


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_topic_summaries(input_dir):
    """Load all *_summary.json files, keyed by filename stem."""
    summaries = {}
    pattern = os.path.join(input_dir, "*_summary.json")
    for filepath in sorted(glob.glob(pattern)):
        stem = Path(filepath).stem
        if stem.endswith("_summary"):
            key = stem[: -len("_summary")]
        else:
            key = stem
        summaries[key] = load_json(filepath)
    return summaries


# ============================================================
# Main Assembly
# ============================================================


def generate_html(area, input_dir, taxonomy_path, output_path):
    cross_topic = load_json(os.path.join(input_dir, "cross_topic_analysis.json"))
    paper_groups = load_json(os.path.join(input_dir, "paper_groups.json"))
    taxonomy = load_json(taxonomy_path)
    topic_summaries = load_all_topic_summaries(input_dir)

    stats = cross_topic.get("statistics", {})
    overview = cross_topic.get("area_overview", {})
    field_tl = cross_topic.get("field_timeline", {})
    connections = cross_topic.get("cross_topic_connections", [])

    ordered = get_topic_order(taxonomy, paper_groups)

    # Use list accumulation instead of string concatenation to avoid O(n^2) memory
    topic_parts = []
    prev_name = None
    for topic_type, topic_id, emoji_icon in ordered:
        key = summary_file_key(topic_type, topic_id)
        ts = topic_summaries.get(key)
        if not ts:
            continue
        cur_name = ts.get("topic_name", topic_id)
        if prev_name:
            transition = find_transition(connections, prev_name, cur_name)
            if transition:
                topic_parts.append(render_topic_transition(transition))
        topic_parts.append(render_topic_card(ts, emoji_icon, topic_type))
        prev_name = cur_name
    topic_html = "".join(topic_parts)
    del topic_parts  # Free memory after join

    all_glossary = merge_glossaries(topic_summaries, cross_topic)

    paper_year_map = _build_paper_year_map(topic_summaries, cross_topic)
    global_paper_links = _build_global_paper_links(topic_summaries, field_tl)
    rel_css = css_path(output_path)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(area.upper())} Research Area Summary</title>
<link rel="stylesheet" href="{e(rel_css)}">
</head>
<body>
{render_header(area, stats)}
{render_area_overview(overview, area)}
{render_field_timeline(field_tl, paper_year_map, global_paper_links)}
{render_toc(ordered, topic_summaries, taxonomy)}
{topic_html}
{render_recommendations(cross_topic.get("practical_recommendations", []))}
{render_takeaways(cross_topic.get("key_takeaways", []))}
{render_trends(cross_topic.get("emerging_trends", []))}
{render_opportunities(cross_topic.get("research_opportunities", []))}
{render_benchmark_leaderboard(cross_topic.get("benchmark_leaderboard", []))}
{render_distribution(paper_groups, taxonomy)}
{render_glossary(all_glossary)}
{render_footer(area, stats)}
</body>
</html>"""

    # Free intermediate data structures before final processing
    del topic_summaries
    del cross_topic
    del paper_groups
    del taxonomy
    del all_glossary
    del global_paper_links
    del topic_html

    html = _replace_paper_refs_with_year(html, paper_year_map)
    del paper_year_map  # Free after use

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML area summary from JSON data."
    )
    parser.add_argument("--area", required=True, help="Research area name (e.g. rag)")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing *_summary.json and cross_topic_analysis.json",
    )
    parser.add_argument("--taxonomy", required=True, help="Path to taxonomy JSON file")
    parser.add_argument("--output", required=True, help="Output HTML file path")
    args = parser.parse_args()

    output = generate_html(args.area, args.input_dir, args.taxonomy, args.output)

    size_kb = os.path.getsize(output) / 1024
    with open(output, encoding="utf-8") as f:
        line_count = sum(1 for _ in f)
    print(f"Generated: {output}")
    print(f"   Size: {size_kb:.1f} KB, {line_count} lines")


if __name__ == "__main__":
    main()
