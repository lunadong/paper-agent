---
description: Load a background file for a research area and extract a structured topic taxonomy for paper grouping
oncalls:
  - paper_agent
---

# Extract Topic Taxonomy

Load `background_{area}.txt` and extract a hierarchical topic taxonomy with matching keywords for downstream paper grouping.

## Example Commands

```
"Extract topic taxonomy for RAG"

"Get taxonomy for agents area"

"Load background and extract topics for factuality"

"Extract taxonomy for memory"
```

## Prerequisites

- Background file must exist at `paper_summary/prompts/background_{area}.txt`
- Available areas: `rag`, `factuality`, `agents`, `memory`, `p13n`, `benchmark`

## Instructions

### Step 1: Validate Area Name

Check that the user-provided area name maps to an existing background file.

```python
import os

AREAS_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/paper_summary/prompts"
OUTPUT_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/area_summary/tmp_summary"

area = "<user_provided_area>"  # e.g., "rag"
bg_path = os.path.join(AREAS_DIR, f"background_{area}.txt")

if not os.path.exists(bg_path):
    available = [f.replace("background_", "").replace(".txt", "")
                 for f in os.listdir(AREAS_DIR) if f.startswith("background_")]
    print(f"Area '{area}' not found. Available areas: {available}")
    # STOP and ask the user to pick a valid area
```

If the area is invalid, list the available areas and ask the user to choose.

### Step 2: Read the Background File

Read the full text of `background_{area}.txt`:

```python
with open(bg_path, "r") as f:
    background_text = f.read()
```

### Step 3: Extract Taxonomy

Parse the background text into a structured taxonomy. The background files follow a semi-structured format with these patterns:

#### Parsing Rules

1. **Opening paragraph** (text before the first numbered item) → `area_description`
2. **Numbered lines** (`1.`, `2.`, `3.`, etc.) → top-level `categories`
3. **Dashed lines** (`- `) under a numbered item → `sub_topics` of that category
4. **Sub-numbered lines** (`2.1`, `2.2`, etc.) → also `sub_topics`
5. **"Specialized topics"** / **"Orthogonal to above"** sections → additional top-level categories
6. **"Special case"** lines → sub_topics under the current category

#### Output Schema

Generate a JSON object with this exact structure:

```json
{
  "area": "rag",
  "area_description": "First paragraph from the background file — 1-2 sentences describing the area.",
  "categories": [
    {
      "id": "snake_case_identifier",
      "name": "Human-Readable Category Name",
      "description": "1-2 sentence description derived from the background text.",
      "sub_topics": [
        {
          "id": "snake_case_sub_id",
          "name": "Sub-topic Name",
          "description": "Brief description from the background text."
        }
      ],
      "matching_keywords": [
        "keyword1", "keyword2", "keyword3"
      ]
    }
  ]
}
```

#### Field Definitions

| Field | Description |
|-------|-------------|
| `area` | The area name (e.g., `rag`, `agents`) |
| `area_description` | Opening paragraph from the background file |
| `categories[].id` | Snake_case identifier (e.g., `modularized_rag`, `knowledge_internalization`) |
| `categories[].name` | Human-readable name (e.g., "Modularized RAG Pipeline") |
| `categories[].description` | 1-2 sentence description from the background text |
| `categories[].sub_topics[]` | Child topics with `id`, `name`, `description` |
| `categories[].matching_keywords` | 5-15 terms for auto-matching papers to this category |

#### Matching Keywords Guidelines

For each category, generate **5-15 matching keywords** that include:

1. **Exact terms** from the background text (e.g., "Query rewriting", "knowledge graph")
2. **Synonyms and variations** likely to appear in paper metadata (e.g., "query reformulation", "KG")
3. **Method names** commonly associated with this topic (e.g., "GraphRAG", "ReAct")
4. **Sub-topic terms** rolled up from child nodes

These keywords will be matched against papers' `sub_topic`, `primary_focus`, and `problem_statement` fields by downstream skills. Aim for **recall over precision** — it's better to include a borderline keyword than miss papers.

### Step 4: Save Taxonomy JSON

Save the extracted taxonomy to `tmp_summary/{area}_taxonomy.json`:

```python
import json, os

os.makedirs(OUTPUT_DIR, exist_ok=True)
output_path = os.path.join(OUTPUT_DIR, f"{area}_taxonomy.json")

with open(output_path, "w") as f:
    json.dump(taxonomy, f, indent=2)

print(f"Taxonomy saved to: {output_path}")
```

### Step 5: Print Summary

Display a summary of what was extracted:

```
Area: {area}
Description: {first 100 chars of area_description}...
Categories: {N}
  1. {category_name} ({M} sub-topics, {K} keywords)
  2. {category_name} ({M} sub-topics, {K} keywords)
  ...
Total sub-topics: {total}
Output: tmp_summary/{area}_taxonomy.json
```

## Reference: Expected Taxonomies

Below are the expected top-level categories for each area, based on the current background files. Use these as a guide — the actual extraction should be driven by the file content.

### RAG (`background_rag.txt`)
1. Modularized RAG Pipeline (sub: triggering, query rewriting, retrieval, post-processing, answer generation, embedding concatenation)
2. Graph-based RAG Pipeline
3. Agentic RAG Pipeline
4. Complex Question (specialized topic)

### Personalization (`background_p13n.txt`)
1. Conversational Personalization (sub: RAG-based, user-profile based)
2. Recommendation Personalization (sub: LLM-based recommendation, leveraging LLM signals, diversity/serendipity)
3. User Modeling (sub: text profiles, embedding profiles, graph/concept-net profiles)

### Factuality (`background_factuality.txt`)
1. Knowledge Internalization (sub: pre-training/mid-training, post-training, new memory architecture)
2. Hallucination Suppression (sub: internal parameters, fine-tuning, confidence-based, verification)

### Agents (`background_agent.txt`)
1. Multi-call Tool Use with Fixed Plan (sub: tool profiling, tool-use post-training)
2. Multi-call Tool Use with Flexible Plan (sub: internalized APIs, web agents, prompt-based optimization, RL-based, reflection-based)
3. Multi-turn with User Interactions
4. Multi-agent (sub: role-based, lead-worker, decentralized)
5. Multi-task Planning
6. Agent Evolution

### Memory (`background_memory.txt`)
1. Memory Recall (sub: sparse memory QA, dense memory QA)
2. Memory Organization (sub: linear memory, layered memory, tree/graph-based memory, memory internalization)

### Benchmark (`background_benchmark.txt`)
1. Benchmark Datasets (sub: task input/output, size, dimensions/distribution, generation method)
2. Metrics and Evaluation (sub: what's evaluated, metric/range, answer labeling method)
3. Analysis (sub: models compared, overall capability, fundamental deficiencies)

## Related Skills

- **get_paper_summaries.md**: Fetch papers from database for grouping against this taxonomy
- Future: **group_papers_by_topic.md**: Uses the taxonomy output to assign papers to categories
- Future: **generate_area_summary.md**: Uses grouped papers to produce an HTML area summary
