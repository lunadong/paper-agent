---
description: Generate a comprehensive HTML area summary report from parsed paper data with topic grouping and cross-topic analysis
oncalls:
  - paper_agent
---

# Summarize Area

**Input:**
- **area**: The research area name (e.g., rag, factuality, agents, memory, p13n, benchmark)
- **papers_file**: Path to papers.txt or pre-parsed JSON with paper summaries (default: `prompt_optimization/area_summaries/{area}/papers.txt`)
- **taxonomy_json**: Path to prompts/taxonomy/{area}_taxonomy.json from extract_topic_taxonomy skill (optional — will run extraction if missing)

**Output:**
- **area_summary_html**: prompt_optimization/area_summaries/{area}/area_summary.html — self-contained HTML report with topic-grouped progress summaries

Generate a comprehensive, self-contained HTML summary report for a research area by:
1. Grouping papers by topic taxonomy from background files
2. Summarizing each topic group using parallel sub-agents
3. Performing cross-topic analysis
4. Assembling a polished HTML report

## Example Commands

```
"Summarize area for RAG"

"Create summary report for agents papers"

"Summarize factuality area"

"Build area summary for p13n"
```

## Prerequisites

Before starting the area summary generation, ensure the following files exist. **Skip any step where the file already exists.**

> 🛑 **NEVER use files from `old*/` subdirectories.** Always use files at the top level of `prompt_optimization/area_summaries/{area}/`. If a required file only exists inside an `old*/` folder, treat it as missing and regenerate it from scratch.

### 1. Export Papers (if `prompt_optimization/area_summaries/{area}/papers.txt` does not exist)

```bash
cd area_summary

# Create area subfolder and check if papers file exists; if not, export from database
mkdir -p prompt_optimization/area_summaries/{area}
if [ ! -f "prompt_optimization/area_summaries/{area}/papers.txt" ]; then
    python export_papers.py --filter "primary_topic={AREA}" --format txt --output-dir prompt_optimization/area_summaries/{area}
fi
```

### 2. Parse Papers (if `prompt_optimization/area_summaries/{area}/papers_parsed.json` does not exist)

```bash
cd area_summary

# Check if parsed JSON exists; if not, run parser
if [ ! -f "prompt_optimization/area_summaries/{area}/papers_parsed.json" ]; then
    python parse_papers.py \
        --input prompt_optimization/area_summaries/{area}/papers.txt \
        --output prompt_optimization/area_summaries/{area}/papers_parsed.json
fi
```

### 3. Extract Topic Taxonomy (ALWAYS rerun)

**ALWAYS run the `extract_topic_taxonomy.md` skill** — do NOT reuse a taxonomy JSON from a previous run, `old*/` folder, or any other cached source. The taxonomy must be freshly generated from the background file.

```bash
cd area_summary

# ALWAYS regenerate taxonomy from the background file using the extract_topic_taxonomy skill.
# Do NOT skip this step even if prompts/taxonomy/{area}_taxonomy.json already exists.
# Invoke: extract_topic_taxonomy.md skill for area: {area}
```

### 4. Group Papers by Taxonomy (if `prompt_optimization/area_summaries/{area}/paper_groups.json` does not exist)

```bash
cd area_summary

# Check if paper groups exist; if not, run grouping
if [ ! -f "prompt_optimization/area_summaries/{area}/paper_groups.json" ]; then
    python group_papers.py --area {area}
fi
```

This step reads `papers_parsed.json` (from step 2) and groups papers by the taxonomy (from step 3). It produces:
- **Formatted paper files** for each sub-agent:
  - `subtopic_{st_id}_papers.txt` — papers for each sub-topic
  - `category_{cat_id}_general_papers.txt` — papers in category but NOT matching any sub-topic within that category
  - `theme_{theme_id}_papers.txt` — papers matching each theme
- **Grouping summary** (`paper_groups.json`) with counts and file paths

**Grouping Logic**:
- **Categories (disjoint)**: Each paper belongs to exactly ONE category
- **Themes (overlapping)**: Papers can match multiple themes regardless of category
- **Sub-topics (overlapping within category)**: Papers can match multiple sub-topics within their assigned category
- **Category order**: Categories without sub-topics are checked first (more specific)
- **Fallback matching**: If no category match, uses abstract to find closest category

### Required Files Summary

| File | Source | Check |
|------|--------|-------|
| `prompt_optimization/area_summaries/{area}/papers.txt` | `export_papers.py` via `get_paper_summaries.md` skill | Skip export if exists |
| `prompt_optimization/area_summaries/{area}/papers_parsed.json` | `parse_papers.py` | Skip parsing if exists |
| `prompts/taxonomy/{area}_taxonomy.json` | `extract_topic_taxonomy.md` skill | **Always rerun** — never reuse |
| `prompt_optimization/area_summaries/{area}/paper_groups.json` | `group_papers.py` | Skip grouping if exists |
| `paper_collection/paper_summary/prompts/background_{area}.txt` | Manual/pre-existing | Required |
| `style.css` | Pre-existing (shared CSS) | Required for HTML generation |
| `generate_html.py` | Pre-existing (HTML generator) | Required for Step 4 |

### Available Areas

`rag`, `factuality`, `agents`, `memory`, `p13n`, `benchmark`

## Input Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `area` | Research area name (e.g., "rag", "agents") | Required |
| `papers_file` | Path to papers.txt or pre-parsed JSON | `prompt_optimization/area_summaries/{area}/papers.txt` |
| `output_path` | Output HTML file path | `prompt_optimization/area_summaries/{area}/area_summary.html` |

## Instructions

### Step 1: Load Paper Groups & Taxonomy

Load the pre-requisite files (paper groups and taxonomy).

```python
import json

area = "<user_provided_area>"  # e.g., "rag"

# Load paper groups from group_papers.py output (Prerequisite 4)
with open(f"prompt_optimization/area_summaries/{area}/paper_groups.json") as f:
    paper_groups = json.load(f)

print(f"Total papers: {paper_groups['total_papers']}")
print(f"Categories: {list(paper_groups['categories'].keys())}")
print(f"Themes: {list(paper_groups['themes'].keys())}")
print(f"Sub-topics: {list(paper_groups['sub_topics'].keys())}")
print(f"Files to process: {len(paper_groups['files'])}")

# Load taxonomy for category/theme metadata
with open(f"prompts/taxonomy/{area}_taxonomy.json") as f:
    taxonomy = json.load(f)

print(f"Taxonomy: {len(taxonomy['categories'])} categories, {len(taxonomy.get('theme', []))} themes")
```

### Step 2: Launch Parallel Sub-agents

Launch sub-agents in parallel for:
1. **Sub-topics**: One sub-agent per sub-topic with papers matching that sub-topic within their assigned category
2. **Category general**: One sub-agent per category for papers NOT matching any sub-topic within that category
3. **Themes**: One sub-agent per theme (papers can overlap with categories)

**Total sub-agents** = (# of sub-topics with papers) + (# of categories with general papers) + (# of themes with papers) + (1 for "other" if any unmatched papers)

**Sub-agent prompt template:** See `prompts/topic_summary_prompt.txt`

```python
import json
from pathlib import Path

area = "<user_provided_area>"

# Load paper groups from group_papers.py output
with open(f"prompt_optimization/area_summaries/{area}/paper_groups.json") as f:
    paper_groups = json.load(f)

# Load taxonomy for category/theme metadata
with open(f"prompts/taxonomy/{area}_taxonomy.json") as f:
    taxonomy = json.load(f)

# Build lookup dictionaries
cat_info = {c["id"]: c for c in taxonomy["categories"]}
theme_info = {t["id"]: t for t in taxonomy.get("theme", [])}

# Collect all sub-agent tasks from the files created by group_papers.py
subagent_tasks = []

for file_info in paper_groups["files"]:
    file_path = Path(file_info["path"])
    if not file_path.exists():
        continue

    papers_text = file_path.read_text(encoding="utf-8")

    if file_info["type"] == "sub_topic":
        # Find sub-topic info from taxonomy
        st_id = file_info["id"]
        st_info = None
        parent_cat = None
        for cat in taxonomy["categories"]:
            for st in cat.get("sub_topics", []):
                if st["id"] == st_id:
                    st_info = st
                    parent_cat = cat
                    break
            if st_info:
                break

        if st_info:
            subagent_tasks.append({
                "type": "sub_topic",
                "id": st_id,
                "name": st_info["name"],
                "description": st_info["description"],
                "parent_category": parent_cat["name"] if parent_cat else "",
                "paper_count": file_info["count"],
                "papers_text": papers_text
            })

    elif file_info["type"] == "category_general":
        cat_id = file_info["id"]
        if cat_id == "other":
            subagent_tasks.append({
                "type": "category_general",
                "id": "other",
                "name": "Other Topics",
                "description": "Papers that don't fit the main taxonomy categories.",
                "paper_count": file_info["count"],
                "papers_text": papers_text
            })
        elif cat_id in cat_info:
            cat = cat_info[cat_id]
            subagent_tasks.append({
                "type": "category_general",
                "id": cat_id,
                "name": cat["name"] + " (General)",
                "description": cat["description"] + " Papers in this category that don't fit specific sub-topics.",
                "paper_count": file_info["count"],
                "papers_text": papers_text
            })

    elif file_info["type"] == "theme":
        theme_id = file_info["id"]
        if theme_id in theme_info:
            theme = theme_info[theme_id]
            subagent_tasks.append({
                "type": "theme",
                "id": theme_id,
                "name": theme["name"],
                "description": theme["description"],
                "paper_count": file_info["count"],
                "papers_text": papers_text
            })

print(f"\nTotal sub-agent tasks: {len(subagent_tasks)}")
for t in subagent_tasks:
    print(f"  [{t['type']}] {t['name']}: {t['paper_count']} papers")
```

### Step 2b: Launch ALL Sub-agents in ONE Batch

**CRITICAL: You MUST launch ALL tasks in a SINGLE message.** Every entry in `paper_groups.json["files"]` must produce a corresponding `*_summary.json`.

**Single batch rule:** Launch ALL sub-agents in ONE parallel call. Do NOT split into multiple batches.

```
# Example: 15 tasks total — launch ALL in the SAME message

task(title="Summarize RAG Triggering (subtopic)", ...)
task(title="Summarize Query Rewriting (subtopic)", ...)
task(title="Summarize Retrieval (subtopic)", ...)
task(title="Summarize Post Processing (subtopic)", ...)
task(title="Summarize Answer Generation (subtopic)", ...)
task(title="Summarize Embedding Concatenation (subtopic)", ...)
task(title="Summarize Modularized RAG (category general)", ...)
task(title="Summarize Graph-based RAG (category general)", ...)
task(title="Summarize Agentic RAG (category general)", ...)
task(title="Summarize Other Topics (category general)", ...)
task(title="Summarize Complex Question (theme)", ...)
task(title="Summarize Analysis (theme)", ...)
task(title="Summarize Benchmark (theme)", ...)
task(title="Summarize Application (theme)", ...)
task(title="Summarize Survey (theme)", ...)

# All 15 tasks launched in parallel — wait for ALL to complete
```

Each sub-agent task call should use:
```
task(
    title=f"Summarize {t['name']}",
    prompt=TOPIC_SUMMARY_PROMPT.format(
        topic_name=t["name"],
        topic_description=t["description"],
        paper_count=t["paper_count"],
        papers_text=t["papers_text"]
    ),
    config={"subagent_name": "general-purpose"}
)
```

**Save each sub-agent result** to `prompt_optimization/area_summaries/{area}/` using this naming convention:

| Task Type | Output File |
|-----------|-------------|
| sub_topic | `subtopic_{id}_summary.json` |
| category_general | `category_{id}_summary.json` (or `category_{id}_general_summary.json`) |
| theme | `theme_{id}_summary.json` |

### Step 2c: Verify All Summaries Generated

**IMPORTANT:** After ALL batches complete, verify that every file in `paper_groups.json["files"]` has a corresponding `*_summary.json`.

```python
import os

# Build expected output files from paper_groups.json
expected_files = []
for file_info in paper_groups["files"]:
    ftype = file_info["type"]
    fid = file_info["id"]
    if ftype == "sub_topic":
      expected_files.append(f"prompt_optimization/area_summaries/{area}/subtopic_{fid}_summary.json")
    elif ftype == "category_general":
        expected_files.append(f"prompt_optimization/area_summaries/{area}/category_{fid}_summary.json")
    elif ftype == "theme":
        expected_files.append(f"prompt_optimization/area_summaries/{area}/theme_{fid}_summary.json")

# Check which are missing
missing = [f for f in expected_files if not os.path.exists(f)]
generated = [f for f in expected_files if os.path.exists(f)]

print(f"Expected: {len(expected_files)} summary files")
print(f"Generated: {len(generated)}")
print(f"Missing: {len(missing)}")

if missing:
    print("\nMISSING FILES (must re-run):")
    for f in missing:
        print(f"  - {f}")
    # Re-launch sub-agents for missing files only
else:
    print("\nAll summary files generated successfully.")
```

**If any files are missing**, re-launch sub-agents for the missing tasks only (do NOT re-run already completed ones).

**Expected output per sub-agent:**
- JSON with: `topic_id`, `topic_name`, `paper_count`, `overview`, `methods`, `timeline`, `key_insights`, `limitations`, `significant_papers`

**Paper Links:**
- All paper references should include links in format: `https://papers.lunadong.com/paper/{paper_id}`

### Step 3: Generate Cross-Topic Analysis

After collecting all topic summaries, launch a sub-agent for cross-cutting analysis.

**Cross-topic analysis prompt:** See `prompts/cross_topic_analysis_prompt.txt`

### Step 4: Assemble HTML Report

Run the deterministic `generate_html.py` script to assemble the HTML report from all topic summaries and cross-topic analysis JSON files. This replaces the previous LLM sub-agent approach for faster, consistent, and complete HTML generation.

```bash
cd area_summary
python generate_html.py --area {area}
```

**What the script does:**
- Reads all `subtopic_*_summary.json` and `cross_topic_analysis.json` from `prompt_optimization/area_summaries/{area}/`
- Reads taxonomy from `prompts/taxonomy/{area}_taxonomy.json`
- Reads paper groups from `prompt_optimization/area_summaries/{area}/paper_groups.json`
- Renders topic cards with brief/full layout using `<details>/<summary>` for expansion
- Links to shared `style.css` for styling
- Outputs `prompt_optimization/area_summaries/{area}/area_summary.html`

**CLI options:**
- `--area` (required): Area name (e.g., `rag`)
- `--input-dir`: Override input directory (default: `prompt_optimization/area_summaries/{area}`)
- `--taxonomy`: Override taxonomy file path
- `--output`: Override output file path

### Step 5: Copy to Web Serving Directory

After generating the HTML, copy it to the web interface's `htmls/` folder with the naming convention `{area}_summary.html`:

```bash
cd area_summary

# Copy to web serving directory
cp prompt_optimization/area_summaries/{area}/area_summary.html ../web_interface/htmls/{area}_summary.html
```

This places the report alongside other area summaries (e.g., `rag_summary.html`) in the directory served by the web interface.

### Step 6: Validate & Report

The `generate_html.py` script prints a summary upon completion. Verify the output:

```bash
# The script automatically prints:
#   - File size in KB
#   - Number of topic cards rendered
#   - Number of basics boxes, running examples, key insights
#   - Number of methods tables, limitations, paper lists
#   - Total paper links and glossary items
#   - Number of cross-topic transitions

# Open the HTML to verify rendering:
open ../web_interface/htmls/{area}_summary.html
```

**Expected output characteristics:**
- Each topic has a brief card (basics box, running example, key insights) always visible
- Each topic has a "Show full analysis" toggle that expands to show timeline, sub-topics, methods, benchmarks, limitations, and paper list
- All papers from JSON are linked with `https://papers.lunadong.com/paper/{id}`
- Glossary terms are merged from all topic summaries
- Topics appear in taxonomy order with cross-topic transitions between adjacent topics

## Complete Workflow Example

```bash
cd area_summary

# Prerequisites: Export, parse papers, and extract taxonomy (skip if files already exist)
mkdir -p prompt_optimization/area_summaries/rag

[ ! -f "prompt_optimization/area_summaries/rag/papers.txt" ] && \
    python export_papers.py --filter "primary_topic=RAG" --format txt --output-dir prompt_optimization/area_summaries/rag

[ ! -f "prompt_optimization/area_summaries/rag/papers_parsed.json" ] && \
    python parse_papers.py \
        --input prompt_optimization/area_summaries/rag/papers.txt \
        --output prompt_optimization/area_summaries/rag/papers_parsed.json

[ ! -f "prompts/taxonomy/rag_taxonomy.json" ] && \
    echo "Run extract_topic_taxonomy.md skill for area: rag"

# NOTE: Taxonomy is ALWAYS regenerated from the background file.
# Even if prompts/taxonomy/rag_taxonomy.json exists, the summarize_area skill
# will rerun extract_topic_taxonomy.md to ensure it reflects the latest background.

# Summarize the area (via this skill)
# The skill will:
#   1. Load parsed papers from prompt_optimization/area_summaries/rag/papers_parsed.json
#   2. Load taxonomy from prompts/taxonomy/rag_taxonomy.json
#   3. Group papers by topic (group_papers.py)
#   4. Launch parallel sub-agents for topic summaries → subtopic_*_summary.json
#   5. Generate cross-topic analysis → cross_topic_analysis.json
#   6. Run generate_html.py to assemble the HTML report deterministically
#   7. Save to prompt_optimization/area_summaries/rag/area_summary.html

# Step 4 can also be run standalone:
python generate_html.py --area rag

# Step 5: Copy to web serving directory
cp prompt_optimization/area_summaries/rag/area_summary.html ../web_interface/htmls/rag_summary.html
```

## Output Files

| File | Description |
|------|-------------|
| `prompt_optimization/area_summaries/{area}/papers.txt` | Exported papers in text format |
| `prompt_optimization/area_summaries/{area}/papers_parsed.json` | Parsed paper data with metadata |
| `prompts/taxonomy/{area}_taxonomy.json` | Extracted topic taxonomy |
| `prompt_optimization/area_summaries/{area}/paper_groups.json` | Paper-to-topic grouping with counts |
| `prompt_optimization/area_summaries/{area}/subtopic_*_summary.json` | Per-topic summary JSON files |
| `prompt_optimization/area_summaries/{area}/cross_topic_analysis.json` | Cross-topic analysis JSON |
| `prompt_optimization/area_summaries/{area}/area_summary.html` | Final HTML report (generated by `generate_html.py`) |
| `../web_interface/htmls/{area}_summary.html` | Serving copy of the HTML report (copied in Step 5) |
| `style.css` | Shared CSS stylesheet (referenced by all HTML reports) |
| `generate_html.py` | Deterministic HTML generation script |

## HTML Report Structure

```
📄 prompt_optimization/area_summaries/{area}/area_summary.html
├── <link> to style.css (shared stylesheet)
├── Header (gradient, stats banner)
├── Area Overview (definition, scope, field timeline)
├── Table of Contents (clickable links to each topic)
├── Topic Cards (one per topic, in taxonomy order)
│   ├── Brief (always visible)
│   │   ├── Basics Box (What / Why / Baseline / Challenges)
│   │   ├── Running Example (query → baseline → challenge → solutions)
│   │   └── Key Insights (bullet list)
│   ├── Cross-Topic Transition (between adjacent topics, if available)
│   └── Full Analysis (<details>/<summary> "Show full analysis ▶")
│       ├── Topic Timeline (periods with milestones)
│       ├── Sub-topics Grid (cards with paper counts)
│       ├── Methods Table (name, description, paper links)
│       ├── Benchmark Results (per-benchmark tables with scores)
│       ├── Limitations (categorized list)
│       └── Paper List (all papers with links, in a collapsible <details>)
├── Practical Recommendations (priority-coded table)
├── Key Takeaways (grid with emojis)
├── Emerging Trends (with paper citations)
├── Research Opportunities
├── Benchmark Leaderboard (top results across all topics)
├── Topic Distribution Chart (CSS bars)
├── Glossary (merged from all topics)
└── Footer (timestamp, metadata)
```

## Paper Link Format

All paper references in the HTML report use clickable links:
- Format: `https://papers.lunadong.com/paper/{paper_id}`
- Example: Paper ID 52 → `https://papers.lunadong.com/paper/52`

## Writing Style Guidelines

The generated report should:
1. **Avoid jargon**: Explain technical terms when necessary
2. **Balance high-level and technical depth**: Lead with "what" and "why", then provide technical details
3. **Be concrete**: Include specific metrics and explain what they mean
4. **Be actionable**: Help readers understand when to use each method

## Related Skills

- **get_paper_summaries.md**: Export papers from database to txt/json
- **extract_topic_taxonomy.md**: Extract taxonomy from background files
- **analyze_summary.md**: Analyze individual paper summary quality
