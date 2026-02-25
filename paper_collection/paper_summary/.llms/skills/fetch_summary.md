---
description: Fetch paper summaries from database or local files by paper_id
input:
  - paper_id: integer (e.g., 3569, 3584)
output:
  - JSON summary with summary_basics, summary_core, summary_techniques, summary_experiments, summary_figures
  - Saved to: prompt_optimization/paper_summaries/paper_{paper_id}.json
---

# Fetch Paper Summary

Fetch the summary of a research paper from the database by paper_id, or from a local JSON file.

## Example Commands

```
"Fetch the summary for paper 3569"

"Get paper 3584 from the database"

"Read the existing summary for paper_id 3686"
```

## Prerequisites

Before running this skill, ensure:
1. Access to the paper database (PostgreSQL with paper_summary table)
2. Python environment with `paper_db` module available
3. OR: Access to local JSON summary files in `prompt_optimization/paper_summaries/`

## Usage

```
/skill fetch_summary
```
Then provide the paper_id when prompted.

## Instructions

### Step 1: Determine the Paper ID

Ask the user for the paper_id if not provided. Valid paper IDs are integers (e.g., 3569, 3584, 3686).

### Step 2: Check for Existing Local Summary

First, check if a summary already exists locally:

```
prompt_optimization/paper_summaries/paper_{paper_id}.json
```

If found, read and return this file.

### Step 3: Fetch from Database (if no local file)

If no local file exists, fetch from the database using Python:

```python
import sys
sys.path.insert(0, '/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection')

from paper_db import PaperDB

db = PaperDB()

# Get paper metadata and summary fields
paper = db.get_paper_by_id(paper_id)
if not paper:
    print(f"Paper {paper_id} not found")
else:
    # Basic metadata
    print(f"Title: {paper['title']}")
    print(f"Authors: {paper['authors']}")
    print(f"Abstract: {paper['abstract']}")
    print(f"Link: {paper['link']}")
    print(f"Topics: {paper.get('topics', 'N/A')}")
    print(f"Primary Topic: {paper.get('primary_topic', 'N/A')}")

    # Summary fields (JSON stored in database)
    print(f"Summary Basics: {paper.get('summary_basics')}")
    print(f"Summary Core: {paper.get('summary_core')}")
    print(f"Summary Technique: {paper.get('summary_techniques')}")
    print(f"Summary Experiments: {paper.get('summary_experiments')}")
    print(f"Summary Figures: {paper.get('summary_figures')}")

db.close()
```

### Database Summary Fields

| Field | Description |
|-------|-------------|
| `summary_basics` | Paper metadata (title, arxiv_id, authors, institutions) |
| `summary_core` | Core content (thesis, problem, novelty, evaluation highlights) |
| `summary_techniques` | Technical details (problem definition, system pipeline, methods) |
| `summary_experiments` | Experiments and results (setup, key results, takeaways) |
| `summary_figures` | Figure descriptions (architecture, experiment figures) |

### Step 4: Save to Local File (Optional)

Save the fetched summary to the local folder for future use:

```
prompt_optimization/paper_summaries/paper_{paper_id}.json
```

## Output Format

The output should be a JSON object containing either:

### Full Summary (if available from local file)
```json
{
  "paper_id": 3569,
  "title": "Paper Title",
  "primary_topic": "TopicName",
  "Basics": {...},
  "Core": {...},
  "Technical_details": {...},
  "Experiments": {...},
  "Figures": {...}
}
```

### Full Summary (if fetched from database)
```json
{
  "paper_id": 3569,
  "title": "Paper Title",
  "authors": ["Author1", "Author2"],
  "abstract": "Abstract text...",
  "link": "https://arxiv.org/abs/...",
  "venue": "arXiv",
  "year": 2026,
  "topics": ["Topic1", "Topic2"],
  "primary_topic": "Topic1",
  "summary_basics": {
    "#1": {
      "title": "...",
      "arxiv_id": "...",
      "authors": [...],
      "institutions": [...]
    }
  },
  "summary_core": {
    "topic_relevance": {...},
    "core_problem": {...},
    "one_sentence_thesis": "...",
    "key_novelty": {...},
    "evaluation_highlights": [...],
    "breakthrough_assessment": {...}
  },
  "summary_techniques": {
    "problem_definition": {...},
    "prerequisite_knowledge": {...},
    "system_pipeline": {...}
  },
  "summary_experiments": {
    "setup": {...},
    "key_results": [...],
    "main_takeaways": [...]
  },
  "summary_figures": {
    "figures": {
      "architecture_figure": {...},
      "major_experiment_figures": [...]
    }
  }
}
```

## Storage Location

Results should be stored in:
```
prompt_optimization/paper_summaries/
```

This folder is used for:
- Storing fetched summaries for diff comparison
- Input to the analyze_summary skill
- Historical tracking of summary versions

## Available Paper IDs (Examples)

Based on existing files in `prompt_optimization/paper_summaries/`:
- 50: OP-Bench (Personalization/Memory)
- 3569: PretrainRL (Factuality/Hallucination)
- 3584: (Available)
- 3686: (Available)
- 3687: (Available)

## Related Skills

- **analyze_summary.md**: Analyze a fetched summary for quality
- **generate_summary.md**: Generate a new summary using current prompts
- **revise_prompts.md**: Revise prompts based on analysis feedback
