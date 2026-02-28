---
description: Fetch paper summaries from database with flexible filter criteria
oncalls:
  - paper_agent
input:
  - filter: Filter criteria — simple format (e.g., primary_topic=RAG) or SQL WHERE clause (e.g., primary_topic = 'RAG' AND year >= 2024)
  - format: Output format — json, txt, or both (default json)
  - output_dir: Output directory (default current directory)
output:
  - papers_file: JSON or TXT file with filtered papers and their summaries (Basics, Core, Technical_details, Experiments, Figures)
---

# Get Paper Summaries

Fetch paper summaries from the database using flexible filter criteria. Supports filtering by primary_topic, topic, year, recommendation date, and more. Outputs to JSON or text format.

## Example Commands

```
"Get all RAG papers with summaries"

"Fetch papers from 2025 with primary_topic='Agents'"

"Export papers recommended this year"

"Get papers where topic contains 'Factuality'"
```

## Prerequisites

Before running this skill, ensure:
1. Access to the paper database (PostgreSQL with papers table)
2. Python environment with required modules
3. Working directory: `paper_collection/area_summary`

## Usage

```
/skill get_paper_summaries
```

Then provide the filter criteria when prompted.

## Instructions

### Step 1: Determine Filter Criteria

Ask the user for the filter criteria. Supported filter formats:

| Simple Format | Description | SQL Equivalent |
|---------------|-------------|----------------|
| `primary_topic=RAG` | Filter by primary topic | `primary_topic = 'RAG'` |
| `topic=Agents` | Filter by topic (contains) | `topics ILIKE '%Agents%'` |
| `year=2025` | Filter by year | `year = 2025` |
| `year>=2024` | Filter by year range | `year >= 2024` |
| `recomm_date=this_year` | Papers from this year | `recomm_date >= '2025-01-01'` |

Complex filters using SQL syntax:
- `primary_topic = 'RAG' AND year = 2025`
- `topics ILIKE '%Factuality%'`
- `recomm_date >= '2025-01-01'`
- `summary_core IS NOT NULL`

Available Topics:
- RAG
- Agents
- Factuality/Hallucination
- Personalization/Memory
- Benchmark & Evaluation
- Multi-Modal/Cross-Modal
- LLM Pre-training
- LLM Reasoning
- Efficient LLM Inference/Serving
- Other NLP
- Other ML
- Other

### Step 2: Execute the Export Script

Run the Python script with the filter criteria:

```bash
cd paper_collection/area_summary

# Export ALL papers
python export_papers.py --all

# Simple filter examples
python export_papers.py --filter "primary_topic=RAG"
python export_papers.py --filter "topic=Agents"
python export_papers.py --filter "year=2025"
python export_papers.py --filter "recomm_date=this_year"

# SQL filter examples
python export_papers.py --filter "primary_topic = 'RAG'"
python export_papers.py --filter "primary_topic = 'RAG' AND year >= 2024"

# Specify output directory
python export_papers.py --filter "primary_topic=RAG" --output-dir ./output

# Specify output format
python export_papers.py --filter "primary_topic=RAG" --format json
python export_papers.py --filter "primary_topic=RAG" --format txt
python export_papers.py --filter "primary_topic=RAG" --format both

# List available topics
python export_papers.py --list-topics
```

### Step 3: Output Fields

The JSON output contains:

#### Metadata Fields

| Field | Description |
|-------|-------------|
| `id` | Unique paper database ID |
| `title` | Paper title |
| `authors` | Comma-separated list of authors |
| `abstract` | Paper abstract |
| `link` | URL to the paper (arXiv, ACL, etc.) |
| `venue` | Publication venue |
| `year` | Publication year |
| `topics` | Comma-separated list of assigned topics |
| `primary_topic` | Primary topic classification |
| `recomm_date` | Recommendation date |

#### Summary Fields (JSON stored in database)

| Field | Description |
|-------|-------------|
| `summary_basics` | Paper metadata (title, arxiv_id, authors, institutions) |
| `summary_core` | Core content (thesis, problem, novelty, evaluation highlights) |
| `summary_techniques` | Technical details (problem definition, system pipeline, methods) |
| `summary_experiments` | Experiments and results (setup, key results, takeaways) |
| `summary_figures` | Figure descriptions (architecture, experiment figures) |

### Step 4: Output Format

#### JSON Output Structure

```json
{
  "filter": "primary_topic=RAG",
  "where_clause": "primary_topic = 'RAG'",
  "count": 150,
  "exported_at": "2025-02-27T12:00:00",
  "papers": [
    {
      "id": 3569,
      "title": "Paper Title",
      "authors": "Author1, Author2",
      "abstract": "Abstract text...",
      "link": "https://arxiv.org/abs/...",
      "venue": "arXiv",
      "year": 2025,
      "topics": "Topic1, Topic2",
      "primary_topic": "RAG",
      "recomm_date": "2025-02-01",
      "summary_basics": {...},
      "summary_core": {...},
      "summary_techniques": {...},
      "summary_experiments": {...},
      "summary_figures": {...}
    }
  ]
}
```

#### Text Output Format

```
# Papers matching: primary_topic=RAG
# Total: 150 papers
# Exported: 2025-02-27T12:00:00
============================================================

[Paper 1/150]
# Paper Title
**arXiv | 2025 | Month: 02**

## Abstract
Abstract text...

## Basics
...

## Core Contributions
...

------------------------------------------------------------
```

### Step 5: Using the Script Programmatically

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "web_interface"))

from db import execute_with_retry

def get_papers_with_filter(where_clause: str) -> list:
    """Get papers matching the WHERE clause."""
    query = f"""
        SELECT id, title, authors, abstract, link, venue, year,
               topics, primary_topic, recomm_date,
               summary_basics, summary_core, summary_techniques,
               summary_experiments, summary_figures
        FROM papers
        WHERE {where_clause}
        ORDER BY created_at DESC
    """
    cursor = execute_with_retry(query, ())
    return cursor.fetchall()

# Example usage
papers = get_papers_with_filter("primary_topic = 'RAG'")
print(f"Found {len(papers)} RAG papers")

# Filter for papers with summaries
papers_with_summary = [p for p in papers if p.get('summary_core')]
print(f"{len(papers_with_summary)} have summaries")
```

## Command Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--all` | Export ALL papers | - |
| `--filter` | Filter criteria (required if not --all) | - |
| `--output-dir` | Output directory | Current directory |
| `--output` | Output filename (without extension) | Auto-generated |
| `--format` | Output format: `json`, `txt`, `both` | `json` |
| `--list-topics` | List available topics | - |

## Related Skills

- **fetch_summary.md**: Fetch a single paper summary by paper_id
- **generate_summary.md**: Generate summaries for papers
- **analyze_summary.md**: Analyze summary quality
