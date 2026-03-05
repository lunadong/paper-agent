---
description: Load a background file for a research area and extract a structured topic taxonomy for paper grouping
oncalls:
  - paper_agent
---

# Extract Topic Taxonomy

**Input:**
- **area**: The research area name (e.g., rag, factuality, agents, memory, p13n, benchmark), or "all" to process every area in parallel

**Output:**
- **taxonomy_json**: prompts/taxonomy/{area}_taxonomy.json — hierarchical topic taxonomy with categories, sub_topics, theme (each with matching_keywords), and category-level matching_keywords (one file per area)

Load `background_{area}.txt` and extract a hierarchical topic taxonomy with matching keywords for downstream paper grouping. This includes:
- **Categories** (disjoint) — each paper belongs to exactly one category
- **Themes** (overlapping) — papers can match multiple themes across all categories
- **Sub-topics** (overlapping within category) — papers can match multiple sub-topics within their assigned category

## Example Commands

```
"Extract topic taxonomy for RAG"

"Get taxonomy for agents area"

"Load background and extract topics for factuality"

"Extract taxonomy for memory"

"Extract topic taxonomies for all areas"

"Generate taxonomies for all background files"
```

## Prerequisites

- Background file must exist at `paper_summary/prompts/background_{area}.txt`
- Available areas: `rag`, `factuality`, `agents`, `memory`, `p13n`, `benchmark`

## Instructions

### Mode Selection

If the user specifies `area = "all"` (or says "all areas", "every area", "all background files"), follow **Batch Mode** below. Otherwise, follow the **Single Area Mode** starting at Step 1.

---

### Batch Mode: All Areas (Parallel Sub-agents)

When the user requests taxonomies for all areas:

#### Batch Step 1: Discover Available Areas

```python
import os

AREAS_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/paper_summary/prompts"
OUTPUT_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/area_summary/prompts/taxonomy"

areas = sorted([f.replace("background_", "").replace(".txt", "")
                for f in os.listdir(AREAS_DIR) if f.startswith("background_")])
print(f"Found {len(areas)} areas: {areas}")
```

#### Batch Step 2: Launch Parallel Sub-agents

Launch **one sub-agent per area** using the `task` tool, all in a **single message** so they run in parallel.

For each area, use:

```
task(
    config={"subagent_name": "general-purpose"},
    title="Extract Taxonomy: {area}",
    prompt="""
    Load and execute the skill at:
    /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/area_summary/.llms/skills/extract_topic_taxonomy.md

    Extract the topic taxonomy for area: {area}

    1. Read the background file at:
       /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/paper_summary/prompts/background_{area}.txt

    2. Follow the skill instructions (Steps 1-5) for single-area mode.

    3. If a papers file exists at:
       /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/area_summary/tmp_summary/{area}/papers.txt
       then grep the actual sub_topic and primary_focus values from it to calibrate matching_keywords.
       Otherwise, generate matching_keywords from the background text + inferred synonyms.

    4. IMPORTANT: Generate matching_keywords at BOTH levels:
       - Each sub_topic must have its own matching_keywords (3-8 terms specific to that sub-topic)
       - Each category must have its own matching_keywords (5-15 terms covering the category broadly, including sub-topic terms rolled up)

    5. IMPORTANT: Generate themes as follows:
       - Extract any area-specific themes from the background text (cross-cutting concerns)
       - Always include the 4 standard themes: analysis, benchmark, application, survey
       - Each theme must have its own matching_keywords (5-10 terms)

    6. Save the taxonomy JSON to:
       /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/area_summary/prompts/taxonomy/{area}_taxonomy.json

    7. Return a summary: area name, number of categories, number of sub-topics, number of themes, number of category keywords, number of sub-topic keywords, number of theme keywords.
    """
)
```

**CRITICAL**: All `task` calls MUST be in the same message to enable parallel execution.

#### Batch Step 3: Aggregate Results

After all sub-agents complete, print a combined summary table:

```
=== Taxonomy Extraction Complete ===
| Area        | Categories | Sub-topics | Themes | Keywords | Output File                      |
|-------------|-----------|------------|--------|----------|----------------------------------|
| agents      | 6         | 10         | 5      | 82       | prompts/taxonomy/agents_taxonomy.json |
| benchmark   | 3         | 11         | 5      | 55       | prompts/taxonomy/benchmark_taxonomy.json |
| factuality  | 2         | 7          | 5      | 60       | prompts/taxonomy/factuality_taxonomy.json |
| memory      | 2         | 6          | 5      | 48       | prompts/taxonomy/memory_taxonomy.json |
| p13n        | 3         | 7          | 5      | 52       | prompts/taxonomy/p13n_taxonomy.json   |
| rag         | 4         | 14         | 6      | 95       | prompts/taxonomy/rag_taxonomy.json    |
```

---

### Single Area Mode

### Step 1: Validate Area Name

Check that the user-provided area name maps to an existing background file.

```python
import os

AREAS_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/paper_summary/prompts"
OUTPUT_DIR = "/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/area_summary/prompts/taxonomy"

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
5. **"Specialized topics"** / **"Orthogonal to above"** sections → extract as **themes** (not categories)
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
          "description": "Brief description from the background text.",
          "matching_keywords": [
            "sub_keyword1", "sub_keyword2", "sub_keyword3"
          ]
        }
      ],
      "matching_keywords": [
        "keyword1", "keyword2", "keyword3"
      ]
    }
  ],
  "theme": [
    {
      "id": "snake_case_theme_id",
      "name": "Theme Name",
      "description": "Brief description of the theme.",
      "matching_keywords": [
        "theme_keyword1", "theme_keyword2", "theme_keyword3"
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
| `categories[].sub_topics[]` | Child topics with `id`, `name`, `description`, `matching_keywords` |
| `categories[].sub_topics[].matching_keywords` | 3-8 terms specific to this sub-topic for fine-grained paper matching |
| `categories[].matching_keywords` | 5-15 terms for auto-matching papers to this category (broad, includes rolled-up sub-topic terms) |
| `theme[].id` | Snake_case identifier (e.g., `analysis`, `benchmark`) |
| `theme[].name` | Human-readable name (e.g., "Analysis", "Benchmark") |
| `theme[].description` | 1-2 sentence description of the theme |
| `theme[].matching_keywords` | 5-10 terms for matching papers to this theme (overlapping across categories) |

#### Matching Keywords Guidelines

Keywords are generated at **two levels**:

#### Sub-topic Level (3-8 keywords each)

For each sub-topic, generate **3-8 matching keywords** that are:
1. **Specific** to this sub-topic (not the parent category broadly)
2. **Exact terms** from the background text description of this sub-topic
3. **Synonyms and method names** commonly associated with this sub-topic

#### Category Level (5-15 keywords each)

For each category, generate **5-15 matching keywords** that include:
1. **Exact terms** from the background text (e.g., "Query rewriting", "knowledge graph")
2. **Synonyms and variations** likely to appear in paper metadata (e.g., "query reformulation", "KG")
3. **Method names** commonly associated with this topic (e.g., "GraphRAG", "ReAct")
4. **Sub-topic terms** rolled up from child nodes

These keywords will be matched against papers' `sub_topic`, `primary_focus`, and `problem_statement` fields by downstream skills. Aim for **recall over precision** — it's better to include a borderline keyword than miss papers.

#### Theme Extraction Guidelines

Themes are **orthogonal to categories** — papers can match multiple themes regardless of their category assignment. Extract themes in two ways:

##### 1. Area-Specific Themes (from background file)

Look for cross-cutting concerns mentioned in the background text that apply across multiple categories:
- Phrases like "orthogonal to above", "specialized topics", "cross-cutting concerns"
- Topics that appear in multiple category descriptions
- Methodological approaches that span categories (e.g., "complex question handling")

##### 2. Standard Themes (always include)

**Always include these 4 standard themes** in every taxonomy, regardless of the area:

```json
{
  "theme": [
    {
      "id": "analysis",
      "name": "Analysis",
      "description": "Papers where experiments are conducted to evaluate the performance of baseline solutions, showing gaps and future directions.",
      "matching_keywords": ["analysis", "evaluation", "experiments", "baseline", "comparison", "gaps", "limitations", "future directions", "empirical study", "performance evaluation"]
    },
    {
      "id": "benchmark",
      "name": "Benchmark",
      "description": "Papers that introduce new benchmark datasets and evaluation metrics.",
      "matching_keywords": ["benchmark", "dataset", "evaluation metrics", "test suite", "evaluation framework", "leaderboard", "standardized evaluation", "test set", "evaluation dataset"]
    },
    {
      "id": "application",
      "name": "Application",
      "description": "Papers that show how to apply the techniques to a specific domain or task, highlighting its strengths and gaps.",
      "matching_keywords": ["application", "case study", "domain-specific", "real-world", "deployment", "production", "industry", "practical", "use case", "applied"]
    },
    {
      "id": "survey",
      "name": "Survey",
      "description": "Papers that provide a comprehensive overview of the current state of the art, including its taxonomy, advantages and limitations.",
      "matching_keywords": ["survey", "review", "overview", "taxonomy", "state of the art", "comprehensive", "literature review", "systematic review", "meta-analysis"]
    }
  ]
}
```

##### Theme Keyword Generation

For each theme (both area-specific and standard), generate **5-10 matching keywords** that are:
1. **Cross-cutting** — applicable across multiple categories
2. **Methodology-focused** — describing approaches rather than topics
3. **Distinct from category keywords** — themes should capture paper types, not content areas

### Step 4: Save Taxonomy JSON

Save the extracted taxonomy to `prompts/taxonomy/{area}_taxonomy.json`:

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
Themes: {T}
  1. {theme_name} ({K} keywords)
  2. {theme_name} ({K} keywords)
  ...
Total sub-topics: {total}
Total themes: {total_themes}
Output: prompts/taxonomy/{area}_taxonomy.json
```

## Reference: Expected Taxonomies

Below are the expected top-level categories for each area, based on the current background files. Use these as a guide — the actual extraction should be driven by the file content.

**Note**: Every taxonomy will also include the 4 standard themes (analysis, benchmark, application, survey), plus any area-specific themes extracted from the background file.

### RAG (`background_rag.txt`)
**Categories:**
1. Modularized RAG Pipeline (sub: triggering, query rewriting, retrieval, post-processing, answer generation, embedding concatenation)
2. Graph-based RAG Pipeline
3. Agentic RAG Pipeline

**Area-specific Themes:**
- Complex Question (specialized topic, orthogonal to pipeline categories)

### Personalization (`background_p13n.txt`)
**Categories:**
1. Conversational Personalization (sub: RAG-based, user-profile based)
2. Recommendation Personalization (sub: LLM-based recommendation, leveraging LLM signals, diversity/serendipity)
3. User Modeling (sub: text profiles, embedding profiles, graph/concept-net profiles)

### Factuality (`background_factuality.txt`)
**Categories:**
1. Knowledge Internalization (sub: pre-training/mid-training, post-training, new memory architecture)
2. Hallucination Suppression (sub: internal parameters, fine-tuning, confidence-based, verification)

### Agents (`background_agent.txt`)
**Categories:**
1. Multi-call Tool Use with Fixed Plan (sub: tool profiling, tool-use post-training)
2. Multi-call Tool Use with Flexible Plan (sub: internalized APIs, web agents, prompt-based optimization, RL-based, reflection-based)
3. Multi-turn with User Interactions
4. Multi-agent (sub: role-based, lead-worker, decentralized)
5. Multi-task Planning
6. Agent Evolution

### Memory (`background_memory.txt`)
**Categories:**
1. Memory Recall (sub: sparse memory QA, dense memory QA)
2. Memory Organization (sub: linear memory, layered memory, tree/graph-based memory, memory internalization)

### Benchmark (`background_benchmark.txt`)
**Categories:**
1. Benchmark Datasets (sub: task input/output, size, dimensions/distribution, generation method)
2. Metrics and Evaluation (sub: what's evaluated, metric/range, answer labeling method)
3. Analysis (sub: models compared, overall capability, fundamental deficiencies)

## Related Skills

- **get_paper_summaries.md**: Fetch papers from database for grouping against this taxonomy
- **summarize_area.md**: Uses grouped papers to produce an HTML area summary
