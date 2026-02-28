---
description: Generate a comprehensive HTML area summary report from parsed paper data with topic grouping and cross-topic analysis
oncalls:
  - paper_agent
---

# Generate Area Summary

Generate a comprehensive, self-contained HTML summary report for a research area by:
1. Parsing paper data from `{area}_papers.txt`
2. Grouping papers by topic taxonomy from background files
3. Summarizing each topic group using parallel sub-agents
4. Performing cross-topic analysis
5. Assembling a polished HTML report

## Example Commands

```
"Generate area summary for RAG"

"Create summary report for agents papers"

"Generate factuality area summary from tmp_summary/factuality_papers.txt"

"Build area summary for p13n"
```

## Prerequisites

- Paper data file: `tmp_summary/{area}_papers.txt` (from `get_paper_summaries.md` skill)
- Background file: `paper_summary/prompts/background_{area}.txt`
- Parse script: `parse_papers.py` in `paper_collection/area_summary/`
- Available areas: `rag`, `factuality`, `agents`, `memory`, `p13n`, `benchmark`

## Input Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `area` | Research area name (e.g., "rag", "agents") | Required |
| `papers_file` | Path to papers.txt or pre-parsed JSON | `tmp_summary/{area}_papers.txt` |
| `output_path` | Output HTML file path | `tmp_summary/{area}_area_summary.html` |

## Instructions

### Step 1: Parse Papers

First, check if a pre-parsed JSON exists. If not, run the parser.

```bash
cd paper_collection/area_summary

# Check for existing parsed JSON
PARSED_FILE="tmp_summary/{area}_papers_parsed.json"

if [ ! -f "$PARSED_FILE" ]; then
    python parse_papers.py \
        --input tmp_summary/{area}_papers.txt \
        --output "$PARSED_FILE"
fi
```

**Or programmatically:**

```python
from parse_papers import parse_papers_file, extract_metadata

papers = parse_papers_file("tmp_summary/{area}_papers.txt")
metadata = extract_metadata(papers)

print(f"Total papers: {metadata['total_papers']}")
print(f"Years: {metadata['years']}")
print(f"Avg breakthrough score: {metadata['avg_breakthrough_score']}")
print(f"Topics: {list(metadata['topics'].keys())[:10]}")
```

**Expected output:**
- List of paper objects with fields: `paper_num`, `title`, `abstract`, `basics`, `core`, `methods`
- Metadata summary: paper count, years range, topic distribution, average breakthrough score

### Step 2: Load Background & Extract Topic Taxonomy

Load the background file and identify the topic categories for grouping.

**Read the background file:**

```python
AREAS_DIR = "paper_collection/paper_summary/prompts"
bg_path = f"{AREAS_DIR}/background_{area}.txt"

with open(bg_path, "r") as f:
    background_text = f.read()
```

**Extract taxonomy (use the `extract_topic_taxonomy.md` skill or inline):**

```python
# Expected taxonomy structure:
taxonomy = {
    "area": "rag",
    "area_description": "...",
    "categories": [
        {
            "id": "modularized_rag",
            "name": "Modularized RAG Pipeline",
            "description": "...",
            "sub_topics": [...],
            "matching_keywords": ["RAG triggering", "Query rewriting", ...]
        },
        # ... more categories
    ]
}
```

**Reference taxonomies by area:**

| Area | Categories |
|------|------------|
| RAG | Modularized RAG Pipeline (triggering, query rewriting, retrieval, post-processing, answer generation), Graph-based RAG, Agentic RAG, Complex Question |
| Agents | Multi-call Tool Use (fixed plan), Multi-call Tool Use (flexible plan), Multi-turn User Interactions, Multi-agent, Multi-task Planning, Agent Evolution |
| Factuality | Knowledge Internalization, Hallucination Suppression |
| Memory | Memory Recall, Memory Organization |
| P13N | Conversational Personalization, Recommendation Personalization, User Modeling |

### Step 3: Group Papers by Topic

Map each paper to topic categories using `core.topic_relevance.sub_topic` and `core.topic_relevance.primary_focus` fields.

```python
def group_papers_by_topic(papers: list, taxonomy: dict) -> dict:
    """
    Group papers by taxonomy categories.

    Returns:
        {category_id: [list of paper objects]}
    """
    groups = {cat["id"]: [] for cat in taxonomy["categories"]}
    groups["other"] = []  # Papers that don't fit any category

    for paper in papers:
        core = paper.get("core") or {}
        topic_rel = core.get("topic_relevance", {})

        sub_topics = topic_rel.get("sub_topic", [])
        primary_focus = topic_rel.get("primary_focus", [])
        all_tags = sub_topics + primary_focus

        matched = False
        for cat in taxonomy["categories"]:
            keywords = cat.get("matching_keywords", [])
            # Check for keyword overlap (case-insensitive)
            if any(kw.lower() in [t.lower() for t in all_tags] for kw in keywords):
                groups[cat["id"]].append(paper)
                matched = True
                break  # Each paper goes to ONE category (first match)

        if not matched:
            groups["other"].append(paper)

    return groups

# Log paper counts
for cat_id, cat_papers in groups.items():
    print(f"  {cat_id}: {len(cat_papers)} papers")
```

### Step 4: Summarize Each Topic Group (Parallel Sub-agents)

Launch **one sub-agent per topic group** using the `task` tool. Each sub-agent produces a structured topic summary.

**Sub-agent prompt template:**

```
You are summarizing research papers in the topic: "{topic_name}"

## Topic Description
{topic_description}

## Papers in this Group ({paper_count} papers)

{for each paper, include:}
### Paper {n}: {title}
**Abstract:** {abstract}
**Core Problem:** {core.core_problem.problem_statement}
**Key Novelty:** {core.key_novelty.main_idea} - {core.key_novelty.explanation}
**Evaluation Highlights:** {core.evaluation_highlights}
**Breakthrough Score:** {core.breakthrough_assessment.score_1_to_10}
---

## Your Task

Produce a JSON summary with these exact fields:

{
  "topic_id": "{category_id}",
  "topic_name": "{topic_name}",
  "paper_count": {N},
  "overview": "2-3 sentences describing the main theme and research focus of this topic.",
  "methods_table": [
    {
      "method_name": "Name of notable method",
      "key_innovation": "One-line description of what makes it novel",
      "improvement": "+X% on Y metric" or "X% accuracy on Z benchmark",
      "venue": "Conference/Journal Year",
      "paper_title": "Full paper title for reference"
    }
    // Include top 4-6 methods with highest breakthrough scores or clearest improvements
  ],
  "progress_points": [
    "Bullet point describing research progress, citing 1-3 specific papers",
    // Include 3-5 points
  ],
  "key_insights": [
    "High-level takeaway or pattern observed across papers",
    // Include 2-3 insights
  ]
}

Focus on:
- Concrete improvements with metrics when available
- Patterns across multiple papers
- Practical implications for practitioners
```

**Launching sub-agents:**

```python
# Use the task tool to launch sub-agents in parallel
for cat_id, cat_papers in groups.items():
    if not cat_papers:
        continue

    # Build the prompt with paper details
    papers_text = format_papers_for_prompt(cat_papers)

    # Launch sub-agent (these run in parallel)
    task(
        title=f"Summarize {cat_id} topic",
        prompt=TOPIC_SUMMARY_PROMPT.format(
            topic_name=category_name,
            topic_description=category_description,
            paper_count=len(cat_papers),
            papers_text=papers_text
        ),
        config={"subagent_name": "general-purpose"}
    )
```

**Expected output per topic:**
- JSON with: `topic_id`, `topic_name`, `paper_count`, `overview`, `methods_table`, `progress_points`, `key_insights`

### Step 5: Generate Cross-Topic Analysis

After collecting all topic summaries, launch a sub-agent for cross-cutting analysis.

**Cross-topic analysis prompt:**

```
You have summaries from {N} topic groups covering {total_papers} papers in the "{area}" research area.

## Topic Summaries
{Insert all topic summaries from Step 4}

## Your Task

Produce a JSON cross-topic analysis with these fields:

{
  "statistics": {
    "total_papers": N,
    "year_range": "YYYY-YYYY",
    "avg_breakthrough_score": X.X,
    "papers_by_topic": {"topic_name": count, ...}
  },
  "practical_recommendations": [
    {
      "recommendation": "Actionable recommendation for practitioners",
      "priority": "High" | "Medium" | "Low",
      "supporting_evidence": "Brief citation of papers/methods supporting this"
    }
    // Include 6-8 recommendations
  ],
  "key_takeaways": [
    {
      "emoji": "🎯",
      "title": "Short title (4-6 words)",
      "description": "2-3 sentence explanation"
    }
    // Include 4-6 takeaways
  ],
  "emerging_trends": [
    "Trend description with supporting evidence",
    // Include 3-5 trends
  ]
}

Focus on:
- Cross-cutting patterns that span multiple topics
- Practical implications for real-world systems
- Gaps and opportunities for future research
```

### Step 6: Assemble HTML Report

A sub-agent takes all topic summaries + cross-topic analysis and generates a single self-contained HTML file.

**HTML generation prompt:**

```
Generate a self-contained HTML file for the "{area}" research area summary.

## Data Inputs
- Area: {area}
- Total Papers: {total_papers}
- Year Range: {year_range}
- Avg Breakthrough Score: {avg_score}
- Topic Summaries: {topic_summaries_json}
- Cross-Topic Analysis: {cross_topic_json}

## Design Requirements

### Header Section
- Gradient background (use CSS variables for theming)
- Area name with emoji
- Stats banner: paper count, theme count, avg score, year range

### Table of Contents
- Clickable links to each section
- Two-column layout on desktop

### Topic Sections (one per topic)
Each section must include:

1. **Section header** with:
   - Emoji icon
   - Topic name
   - Paper count badge: `<span class="paper-count-badge">{N} papers</span>`

2. **Methods table** with columns:
   - Method name (bold)
   - Key Innovation
   - Improvement (styled badge)
   - Venue

3. **Progress points** as styled list with left border

4. **Key insights** in card format

5. **Collapsible paper list** using HTML5 details/summary:
   ```html
   <details class="paper-details">
     <summary>📚 View all {N} papers in this topic</summary>
     <ul class="paper-list">
       <li>{paper_title} ({venue})</li>
       ...
     </ul>
   </details>
   ```

### Topic Distribution Chart
Pure CSS horizontal bar chart (no JavaScript):

```html
<div class="topic-bar" style="--bar-width: {percentage}%;">
  <span class="topic-bar-label">{topic_name}</span>
  <span class="topic-bar-value">{count} ({percentage}%)</span>
</div>
```

### Practical Recommendations Table
- Priority column with color coding:
  - High: red/pink background
  - Medium: yellow background
  - Low: green background

### Key Takeaways Grid
- Responsive grid (3 columns on desktop, 1 on mobile)
- Each card has emoji, title, description
- Gradient background styling

### Footer
- Generation timestamp
- Paper count and source info

### CSS Requirements
- Use CSS variables for colors (primary, secondary, accent, success, warning)
- Mobile-responsive (breakpoint at 768px)
- Print-friendly styles
- Smooth hover transitions

### Creative Enhancements (beyond RAG example)
1. **Breakthrough score indicators**: Color-coded badges (7+: green, 5-7: yellow, <5: orange)
2. **Topic distribution chart**: Horizontal bars showing paper distribution
3. **Collapsible paper lists**: Using <details>/<summary> tags
4. **Paper count badges**: In section headers
5. **Method improvement badges**: Styled spans with appropriate colors

## Output

Return ONLY the complete HTML content (no markdown code fences).
Start with `<!DOCTYPE html>` and end with `</html>`.
```

**Save the output:**

```python
output_path = f"tmp_summary/{area}_area_summary.html"
with open(output_path, "w") as f:
    f.write(html_content)
print(f"Report saved to: {output_path}")
```

### Step 7: Validate & Report

Verify the HTML renders correctly and print a summary.

```python
import os

output_path = f"tmp_summary/{area}_area_summary.html"

# Check file exists and has content
if os.path.exists(output_path):
    size_kb = os.path.getsize(output_path) / 1024
    print(f"✅ HTML report generated: {output_path}")
    print(f"   File size: {size_kb:.1f} KB")
else:
    print(f"❌ Failed to generate report")

# Print summary
print(f"\n📊 Summary Report")
print(f"   Area: {area}")
print(f"   Total papers: {metadata['total_papers']}")
print(f"   Topics identified: {len(groups)}")
for topic_id, papers in groups.items():
    print(f"     - {topic_id}: {len(papers)} papers")
print(f"   Output: {output_path}")
```

## Complete Workflow Example

```bash
# 1. Export papers from database (if not done)
cd paper_collection/area_summary
python export_papers.py --filter "primary_topic=RAG" --format txt --output-dir tmp_summary

# 2. Parse papers to JSON
python parse_papers.py \
    --input tmp_summary/rag_papers.txt \
    --output tmp_summary/rag_papers_parsed.json

# 3. Generate the area summary (via this skill)
# The skill will:
#   - Load parsed papers
#   - Extract taxonomy from background_rag.txt
#   - Group papers by topic
#   - Launch parallel sub-agents for topic summaries
#   - Generate cross-topic analysis
#   - Assemble HTML report
#   - Save to tmp_summary/rag_area_summary.html
```

## Output Files

| File | Description |
|------|-------------|
| `tmp_summary/{area}_papers_parsed.json` | Parsed paper data with metadata |
| `tmp_summary/{area}_taxonomy.json` | Extracted topic taxonomy |
| `tmp_summary/{area}_area_summary.html` | Final HTML report |

## HTML Report Structure

```
📄 {area}_area_summary.html
├── Header (gradient, stats banner)
├── Table of Contents
├── Topic Distribution Chart (CSS bars)
├── Topic Sections (one per category)
│   ├── Methods Table
│   ├── Progress Points
│   ├── Key Insights
│   └── Collapsible Paper List
├── Practical Recommendations (priority-coded table)
├── Key Takeaways (grid with emojis)
├── Emerging Trends
└── Footer (timestamp, metadata)
```

## Related Skills

- **get_paper_summaries.md**: Export papers from database to txt/json
- **extract_topic_taxonomy.md**: Extract taxonomy from background files
- **analyze_summary.md**: Analyze individual paper summary quality
