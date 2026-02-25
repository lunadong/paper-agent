---
description: Analyze paper summaries from beginner and expert perspectives to identify quality issues
input:
  - summary_file or paper_id to analyze
  - perspective (beginner, expert, or both - default both)
  - threshold (quality threshold - default 7.0)
  - use_pdf (fetch original PDF for verification - default false)
output:
  - beginner_score and expert_score
  - combined_score (when perspective is both)
  - issues and suggestions per criterion
  - Saved to prompt_optimization/analysis_critics/
---

# Paper Summary Analysis Skill

Analyze paper summaries from beginner and expert perspectives to identify quality issues and improvement opportunities.

## Example Commands

### Direct Mode
```
"Analyze the summary example"

"Analyze paper 50 from beginner perspective"

"Analyze paper 3569 from expert perspective only"

"Check if the example meets a threshold of 8.0"
```

### Subagent Mode (Isolated Context) - RECOMMENDED
```
# Run beginner analysis only
Use the task tool:
  - subagent_name: "general-purpose"
  - prompt: "Load skill at .llms/skills/analyze_summary.md
             Analyze: prompt_optimization/paper_summaries/paper_50.json
             Perspective: beginner
             Return JSON with beginner_score and criteria details."

# Run expert analysis only
Use the task tool:
  - subagent_name: "general-purpose"
  - prompt: "Load skill at .llms/skills/analyze_summary.md
             Analyze: prompt_optimization/paper_summaries/paper_50.json
             Perspective: expert
             Return JSON with expert_score and criteria details."

# Run both in parallel (2 separate sub-agent calls in same message)
```

## Perspective Parameter

| Value | Behavior |
|-------|----------|
| `beginner` | Run only beginner analysis, return beginner_score |
| `expert` | Run only expert analysis, return expert_score |
| `both` (DEFAULT) | **Spin up 2 parallel sub-agents** (beginner + expert), aggregate results |

**Default:** `perspective="both"` - always run both perspectives unless user specifies otherwise.

## PDF Verification (Optional)

| use_pdf | Behavior |
|---------|----------|
| `false` (DEFAULT) | Analyze summary JSON only, do not fetch PDF |
| `true` | Fetch original PDF to verify claims and accuracy |

### When perspective="both" (Default)

**IMPORTANT:** Do NOT run sequentially. Instead, launch 2 parallel sub-agents:

```
# In the SAME message, make 2 parallel task tool calls:

task(
  subagent_name="general-purpose",
  title="Beginner Analysis",
  prompt="Load .llms/skills/analyze_summary.md
          Analyze: <summary_file>
          Perspective: beginner
          Return JSON with beginner_score and criteria details."
)

task(
  subagent_name="general-purpose",
  title="Expert Analysis",
  prompt="Load .llms/skills/analyze_summary.md
          Analyze: <summary_file>
          Perspective: expert
          Return JSON with expert_score and criteria details."
)
```

Then aggregate results in main context:
```python
combined_score = (beginner_result["beginner_score"] + expert_result["expert_score"]) / 2
passed = combined_score >= threshold
```

**IMPORTANT: Save results** to `prompt_optimization/analysis_critics/`:
```
# For summary_example.json (perspective="both"):
prompt_optimization/analysis_critics/analysis_example_beginner.json  (from beginner sub-agent)
prompt_optimization/analysis_critics/analysis_example_expert.json    (from expert sub-agent)
prompt_optimization/analysis_critics/analysis_example.json           (aggregated combined result)

# For paper_{id}.json (perspective="both"):
prompt_optimization/analysis_critics/analysis_{id}_beginner.json
prompt_optimization/analysis_critics/analysis_{id}_expert.json
prompt_optimization/analysis_critics/analysis_{id}.json

# For single perspective:
prompt_optimization/analysis_critics/analysis_{id}_{perspective}.json
```

## Prerequisites

**For summary_example.json:**
- Must exist in `prompt_optimization/revised_prompts/`
- If not present, copy from `prompts/v2/`:
  ```bash
  cp prompts/v2/summary_example.json prompt_optimization/revised_prompts/
  ```

**For paper_{id}.json:**
- Must exist in `prompt_optimization/paper_summaries/`
- **If not present, run fetch_summary skill first:**
  ```
  Load skill at .llms/skills/fetch_summary.md
  Fetch summary for paper_id: <ID>
  Save to: prompt_optimization/paper_summaries/paper_<ID>.json
  ```
- Then proceed with analysis

## Analysis Options

### Option 1: Analyze Summary Example (default)
Use `prompt_optimization/revised_prompts/summary_example.json`
- This is the working copy for prompt iteration
- Check it exists; if not, copy from `prompts/v2/`

### Option 2: Analyze Paper Summary by ID
Use `prompt_optimization/paper_summaries/paper_{paper_id}.json`

## When to Use

- User asks to "analyze a paper summary"
- User asks to "evaluate summary quality"
- User wants to check if a summary meets quality standards
- As part of the prompt optimization workflow

## Invocation Modes

### Mode 1: Direct (Shared Context)
Simply ask in conversation:
```
"Analyze the summary example"
```

### Mode 2: Subagent (Isolated Context) - RECOMMENDED
Run as independent subagent with its own context:
```
Use the task tool with subagent_name="general-purpose" and prompt:
"Load the skill at paper_collection/paper_summary/.llms/skills/analyze_summary.md
Then analyze the summary at: prompts/v2/summary_example.json
Return the analysis results as JSON."
```

Benefits of subagent mode:
- Each analysis runs in isolated context
- Doesn't pollute main conversation with file contents
- Can run multiple analyses in parallel
- Returns only the results

## File Locations

| File | Path |
|------|------|
| Summary Example | `prompt_optimization/revised_prompts/summary_example.json` |
| Summary Template | `prompt_optimization/revised_prompts/summary_template.json` |
| Main Prompt | `prompt_optimization/revised_prompts/prompt.txt` |
| Paper Summaries (input) | `prompt_optimization/paper_summaries/` |
| Analysis Results (output) | `prompt_optimization/analysis_critics/` |

## Storage Folders

The `prompt_optimization/` folder has 3 subfolders for diff/comparison purposes:

| Folder | Purpose |
|--------|---------|
| `paper_summaries/` | Store fetched/generated paper summaries |
| `analysis_critics/` | Store analysis results from this skill |
| `revised_prompts/` | Store revised prompt versions |

---

## Beginner Perspective

**Persona:** ML researcher who is NEW to the specific field

### Criteria and Weights

| Criterion | Weight | Description | Questions to Ask |
|-----------|--------|-------------|------------------|
| **accessibility** | 22% | Can someone new to the field understand the core idea? | Is the main contribution explained in plain terms? Could a general ML researcher follow the key points? Are there unexplained assumptions about domain knowledge? |
| **jargon_handling** | 18% | Are technical terms and acronyms explained or defined? | Are acronyms defined on first use (e.g., DPO, MAPPO, RAG)? Are domain-specific terms explained? Is there excessive jargon that could be simplified? |
| **motivation_clarity** | 18% | Is it clear WHY this problem matters (real-world impact)? | Does 'why_it_matters' explain real-world implications? Would a reader understand the practical significance? Is the problem statement relatable beyond the research community? |
| **logical_flow** | 12% | Does the summary tell a coherent story? | Does the summary flow logically from problem to solution to results? Are the connections between sections clear? Is there a clear narrative arc? |
| **architecture_figure** | 12% | Is the architecture figure appropriate and helpful for understanding? | Does the architecture_figure description help visualize the system? Is the figure description accessible to newcomers? Does it complement the text explanation or just repeat it? Would a beginner understand the system better with this figure? |
| **consistency** | 13% | Are claims grounded in the paper (no hallucination)? | Do the evaluation highlights match typical paper claims? Are there any claims that seem fabricated or exaggerated? Is the breakthrough_assessment justified by the evidence? |
| **completeness** | 5% | Are the essential elements present (less strict for beginners)? | Are the core sections filled in? Is there enough context to understand the contribution? |

### Beginner Analysis Prompt Template

~~~
You are an ML researcher who is NEW to the specific field of this paper.
You are evaluating a generated summary to see if it would be helpful for someone like you.

## Paper Title
{paper_title}

## Generated Summary (JSON)
```json
{summary_json}
```

## Your Task
Analyze this summary from a BEGINNER'S perspective. For each criterion below, provide:
1. A score from 1-10 (10 = excellent)
2. Specific issues found
3. Concrete suggestions for improvement

## Evaluation Criteria

{criteria_descriptions}

## Output Format
Respond with a JSON object:
```json
{
  "criteria_scores": {
    "accessibility": {
      "score": <1-10>,
      "issues": ["issue1", "issue2"],
      "suggestions": ["suggestion1", "suggestion2"]
    },
    "jargon_handling": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "motivation_clarity": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "logical_flow": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "architecture_figure": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "consistency": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "completeness": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    }
  },
  "top_issues": [
    "The most critical issue overall",
    "Second most critical issue",
    "Third most critical issue"
  ],
  "suggested_improvements": [
    "Most impactful improvement suggestion",
    "Second suggestion",
    "Third suggestion"
  ]
}
```

Be specific and actionable in your feedback. Focus on what would help a newcomer understand this paper.
~~~

---

## Expert Perspective

**Persona:** DOMAIN EXPERT in the research area

### Criteria and Weights

| Criterion | Weight | Description | Questions to Ask |
|-----------|--------|-------------|------------------|
| **technical_precision** | 22% | Are methods and formulations described accurately and precisely? | Are the technical details correct and complete? Is the methodology described with sufficient precision? Are mathematical formulations and algorithms accurately captured? Are implementation details (models, hyperparameters) precise? |
| **novelty_assessment** | 18% | Is it clear what's new vs. prior work? | Does 'why_this_is_new' clearly differentiate from prior work? Are the key innovations explicitly stated? Is the relationship to existing methods clear? Would an expert understand the delta over SOTA? |
| **evaluation_rigor** | 18% | Are results properly contextualized (vs SOTA, baselines)? | Are evaluation metrics appropriate for the task? Are baselines properly described and compared? Is there context for understanding the magnitude of improvements? Are benchmark choices reasonable and representative? |
| **experiment_figures** | 12% | Are experimental result figures appropriate and helpful? | Do the major_experiment_figures highlight key results effectively? Are the most important experimental comparisons captured? Do figure descriptions convey the significance of results? Would an expert find these figures useful for quick assessment? |
| **consistency** | 12% | Are claims grounded in the paper (no hallucination)? | Do evaluation numbers seem plausible for this domain? Is the breakthrough_assessment consistent with the evidence? Are there any claims that appear fabricated or exaggerated? Do the technical details match typical paper conventions? |
| **completeness** | 10% | Are key technical details included? | Are all major components of the method described? Are important ablations or analysis mentioned? Are limitations acknowledged? Is the system_pipeline complete? |
| **reproducibility** | 8% | Is there enough info to understand or replicate the approach? | Are model architectures and sizes specified? Are training details (data, compute) mentioned? Are key hyperparameters documented? Would an expert know what's needed to reproduce? |

### Expert Analysis Prompt Template

~~~
You are a DOMAIN EXPERT in the research area of this paper.
You are evaluating a generated summary to see if it accurately captures the technical contributions.

## Paper Title
{paper_title}

## Primary Topic
{primary_topic}

## Generated Summary (JSON)
```json
{summary_json}
```

## Your Task
Analyze this summary from an EXPERT'S perspective. For each criterion below, provide:
1. A score from 1-10 (10 = excellent)
2. Specific issues found (be technically precise)
3. Concrete suggestions for improvement

## Evaluation Criteria

{criteria_descriptions}

## Output Format
Respond with a JSON object:
```json
{
  "criteria_scores": {
    "technical_precision": {
      "score": <1-10>,
      "issues": ["issue1", "issue2"],
      "suggestions": ["suggestion1", "suggestion2"]
    },
    "novelty_assessment": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "evaluation_rigor": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "experiment_figures": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "consistency": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "completeness": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    },
    "reproducibility": {
      "score": <1-10>,
      "issues": [...],
      "suggestions": [...]
    }
  },
  "top_issues": [
    "The most critical technical issue",
    "Second most critical issue",
    "Third most critical issue"
  ],
  "suggested_improvements": [
    "Most impactful improvement for experts",
    "Second suggestion",
    "Third suggestion"
  ],
  "missing_technical_details": [
    "Important detail that should be included",
    "Another missing element"
  ]
}
```

Be technically rigorous in your feedback. Focus on what would help an expert quickly assess this paper's contributions and validity.
~~~

---

## Scoring

### Calculate Overall Scores

**Beginner Overall Score:**
```
beginner_score = (
    accessibility * 0.22 +
    jargon_handling * 0.18 +
    motivation_clarity * 0.18 +
    logical_flow * 0.12 +
    architecture_figure * 0.12 +
    consistency * 0.13 +
    completeness * 0.05
)
```

**Expert Overall Score:**
```
expert_score = (
    technical_precision * 0.22 +
    novelty_assessment * 0.18 +
    evaluation_rigor * 0.18 +
    experiment_figures * 0.12 +
    consistency * 0.12 +
    completeness * 0.10 +
    reproducibility * 0.08
)
```

**Combined Score:**
```
combined_score = (beginner_score + expert_score) / 2
```

### Quality Thresholds

| Level | Score | Interpretation |
|-------|-------|----------------|
| Poor | < 5.0 | Major issues, needs significant revision |
| Fair | 5.0-6.5 | Notable issues, needs improvement |
| Good | 6.5-8.0 | Minor issues, acceptable with polish |
| Excellent | >= 8.0 | Publication quality |

---

## Workflow

### Step 1: Read the Summary
```
Read the summary JSON file (example or generated):
- prompt_optimization/revised_prompts/summary_example.json (for example)
- prompt_optimization/paper_summaries/paper_{paper_id}.json (for generated)
```

### Step 2: Determine Perspective and PDF Option
Check which perspective to run:
- `perspective="beginner"` → Go to Step 3 only
- `perspective="expert"` → Go to Step 4 only
- `perspective="both"` (DEFAULT) → Run both Step 3 and Step 4

Check PDF option:
- `use_pdf=false` (DEFAULT) → Analyze summary JSON only
- `use_pdf=true` → Also fetch PDF to verify claims (requires arxiv_id from summary)

### Step 3: Beginner Analysis
Apply the beginner prompt template and evaluate each criterion.

**IMPORTANT:** For each criterion, provide:
1. **Score** (1-10)
2. **Detailed issues** (3-5 specific problems with examples from the summary)
3. **Actionable suggestions** (3-5 concrete fixes with specific wording/examples)

Return:
```json
{
  "paper_id": <id>,
  "paper_title": "<title from summary>",
  "perspective": "beginner",
  "beginner_score": <weighted_score>,
  "criteria_scores": {
    "accessibility": {
      "score": <1-10>,
      "issues": [
        "Specific issue 1 with quote or example from summary",
        "Specific issue 2 explaining what concept is unclear",
        "Specific issue 3 with concrete reference"
      ],
      "suggestions": [
        "Add specific explanation: 'For example, [concrete example text]'",
        "Replace [jargon term] with '[plain language explanation]'",
        "Include analogy: '[specific analogy suggestion]'"
      ]
    },
    "jargon_handling": {
      "score": <1-10>,
      "issues": [
        "Term '[X]' is used without definition",
        "Acronym '[Y]' appears but is never expanded",
        "Technical concept '[Z]' assumes prior knowledge"
      ],
      "suggestions": [
        "Define [X] as: '[clear definition]'",
        "Expand [Y] on first use: '[full name] ([acronym])'",
        "Add glossary or inline definitions"
      ]
    },
    ... (similar detail for all criteria)
  },
  "top_issues": [
    "Most critical issue with specific reference to summary content",
    "Second critical issue with concrete example",
    "Third critical issue explaining impact on reader"
  ],
  "suggested_improvements": [
    "Detailed improvement 1 with specific wording to add/change",
    "Detailed improvement 2 with example text",
    "Detailed improvement 3 with concrete action"
  ]
}
```

### Step 4: Expert Analysis
Apply the expert prompt template and evaluate each criterion.

**IMPORTANT:** For each criterion, provide:
1. **Score** (1-10)
2. **Detailed issues** (3-5 specific problems with examples from the summary)
3. **Actionable suggestions** (3-5 concrete fixes with specific wording/examples)

Return:
```json
{
  "paper_id": <id>,
  "paper_title": "<title from summary>",
  "perspective": "expert",
  "expert_score": <weighted_score>,
  "criteria_scores": {
    "technical_precision": {
      "score": <1-10>,
      "issues": [
        "Specific technical inaccuracy or missing detail with quote",
        "Method description lacks precision in [specific area]",
        "Hyperparameter/config detail X is missing or incorrect"
      ],
      "suggestions": [
        "Add specific detail: '[exact technical specification]'",
        "Clarify method: '[precise description of what to add]'",
        "Include hyperparameters: '[list specific params needed]'"
      ]
    },
    "novelty_assessment": {
      "score": <1-10>,
      "issues": [
        "Comparison to [specific prior work] is missing",
        "Delta over SOTA is not quantified",
        "Relationship to [related method] unclear"
      ],
      "suggestions": [
        "Add comparison: 'Unlike [prior work], this method...'",
        "Quantify improvement: 'Achieves X% better than [baseline]'",
        "Clarify novelty: '[specific differentiation text]'"
      ]
    },
    ... (similar detail for all criteria)
  },
  "top_issues": [
    "Critical technical issue with specific reference",
    "Second issue with concrete example from summary",
    "Third issue explaining impact on expert assessment"
  ],
  "suggested_improvements": [
    "Detailed improvement with specific text to add",
    "Technical fix with exact specification",
    "Reproducibility improvement with concrete action"
  ],
  "missing_technical_details": [
    "Specific missing detail 1 (e.g., 'exact model size')",
    "Specific missing detail 2 (e.g., 'training compute budget')",
    "Specific missing detail 3 (e.g., 'hyperparameter X value')"
  ]
}
```

### Step 5: Compile Results (if perspective="both")
Calculate weighted scores and output structured analysis:
```json
{
  "summary_file": "<path to analyzed file>",
  "paper_id": <id>,
  "paper_title": "<title>",
  "perspective": "both",
  "beginner_score": <score>,
  "expert_score": <score>,
  "combined_score": (<beginner_score> + <expert_score>) / 2,
  "threshold": <threshold>,
  "passed": <combined_score >= threshold>,
  "beginner_analysis": {
    "criteria_scores": {
      "<criterion>": {
        "score": <1-10>,
        "issues": ["Detailed issue 1 with specific quote/example", "..."],
        "suggestions": ["Specific suggestion with example text", "..."]
      },
      ...
    },
    "top_issues": ["Critical issue 1 with context", "..."],
    "suggested_improvements": ["Detailed improvement with specific wording", "..."]
  },
  "expert_analysis": {
    "criteria_scores": {...},
    "top_issues": [...],
    "suggested_improvements": [...],
    "missing_technical_details": ["Specific detail 1", "..."]
  }
}
```

### Step 6: Save Results to File

**IMPORTANT:** Always save analysis results to the output folder.

```python
import json

# Determine base name
if analyzing summary_example.json:
    base_name = "analysis_example"
else:
    base_name = f"analysis_{paper_id}"

output_dir = "prompt_optimization/analysis_critics"

# Save based on perspective
if perspective == "beginner":
    output_file = f"{output_dir}/{base_name}_beginner.json"
    with open(output_file, "w") as f:
        json.dump(beginner_result, f, indent=2)
    print(f"Saved beginner analysis to: {output_file}")

elif perspective == "expert":
    output_file = f"{output_dir}/{base_name}_expert.json"
    with open(output_file, "w") as f:
        json.dump(expert_result, f, indent=2)
    print(f"Saved expert analysis to: {output_file}")

elif perspective == "both":
    # Save individual perspectives
    beginner_file = f"{output_dir}/{base_name}_beginner.json"
    expert_file = f"{output_dir}/{base_name}_expert.json"
    combined_file = f"{output_dir}/{base_name}.json"

    with open(beginner_file, "w") as f:
        json.dump(beginner_result, f, indent=2)
    print(f"Saved beginner analysis to: {beginner_file}")

    with open(expert_file, "w") as f:
        json.dump(expert_result, f, indent=2)
    print(f"Saved expert analysis to: {expert_file}")

    # Save combined result
    with open(combined_file, "w") as f:
        json.dump(combined_result, f, indent=2)
    print(f"Saved combined analysis to: {combined_file}")
```

Output file format:
```json
{
  "summary_file": "<path to analyzed summary>",
  "perspective": "both",
  "beginner_score": 8.41,
  "expert_score": 7.72,
  "combined_score": 8.07,
  "threshold": 7.0,
  "passed": true,
  "beginner_analysis": {
    "criteria_scores": {...},
    "top_issues": [...],
    "suggested_improvements": [...]
  },
  "expert_analysis": {
    "criteria_scores": {...},
    "top_issues": [...],
    "suggested_improvements": [...],
    "missing_technical_details": [...]
  }
}
```

---

## Example Commands

```
"Analyze the summary example"
→ Read prompts/v2/summary_example.json and analyze from both perspectives

"Analyze the summary for paper 3569"
→ Find and analyze optimization_runs/.../summary_3569.json

"Check if the example meets a threshold of 8.0"
→ Analyze and report whether all criterion scores >= 8.0
```
