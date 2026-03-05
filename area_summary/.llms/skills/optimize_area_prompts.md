---
description: Run a single optimization pass on area summaries - select area, analyze from 3 perspectives, and revise prompts
oncalls:
  - paper_agent
---

# Single-Pass Area Prompt Optimization Skill

Run a single optimization pass: select area → get outputs → analyze from 3 perspectives → revise prompts if below threshold.

## 🛑 CRITICAL: User Confirmation Required

**Before launching any analysis sub-agents, you MUST:**
1. Use `ask_user_question` tool to confirm the output source
2. Wait for user response
3. Only then proceed to analysis

**DO NOT SKIP THIS STEP. DO NOT ASSUME "use existing" is acceptable.**

---

## Example Commands

```
"Optimize area prompts for RAG"
→ Analyze RAG area summary, revise based on feedback

"Optimize prompts for agents area with threshold 8.5"
→ Analyze agents, revise to target 8.5

"Optimize RAG from expert perspective only"
→ Run only expert analysis, revise based on expert feedback
```

---

## When to Use

- User asks to "optimize area prompts"
- User asks to "improve area summary quality"
- User specifies an area for testing
- As part of area prompt development workflow

---

## File Locations

| Folder | Purpose |
|--------|---------|
| `tmp_summary/{area}/` | Area summary outputs (topic JSONs, cross-topic, HTML) |
| `prompt_optimization/analysis_critics/` | Analysis results |
| `prompt_optimization/revised_prompts/` | Working prompt files |
| `prompt_optimization/area_summaries/` | Archived area summaries for reference |

---

## Single-Pass Workflow

> **🛑 STOP: Before running ANY analysis, you MUST ask the user to confirm the output source using `ask_user_question`. Do NOT proceed to Step 3 without explicit user confirmation.**

### Step 1: Determine What to Analyze

Check inputs:
- `area` (REQUIRED): Which area to analyze (e.g., "rag", "agents", "memory")
- Look for outputs in `tmp_summary/{area}/`

### Step 2: Get Outputs Based on Source Option (MANDATORY USER CONFIRMATION)

**⚠️ CRITICAL: You MUST ask the user to confirm the output source before proceeding. Do NOT skip this step.**

Use the `ask_user_question` tool to confirm:

```
ask_user_question(
    preamble="Before running analysis on the {area} area summary, I need to confirm the output source.",
    questions=[{
        "header": "Source",
        "question": "Output source for analysis:",
        "options": [
            {"label": "A) Use existing outputs", "description": "Use existing files in tmp_summary/{area}/"},
            {"label": "B) Re-generate", "description": "Re-generate using current prompts (run summarize_area.md skill)"}
        ]
    }]
)
```

**Wait for user response before proceeding.**

**Option A: Use Existing (default)**
```
Check tmp_summary/{area}/ for:
- Topic summaries: *_summary.json
- Cross-topic analysis: cross_topic_analysis.json
- HTML report: area_summary*.html

If outputs exist:
    Use them directly
Else:
    Error: "No outputs found. Please run summarize_area.md first or choose option B."
```

**Option B: Re-generate Outputs (Subagent Mode)**
```
task(
    subagent_name="general-purpose",
    title="Generate Area Summary: {area}",
    prompt="""
    Load skill: area_summary/.llms/skills/summarize_area.md
    Generate summary for area: {area}
    Save outputs to: tmp_summary/{area}/
    """
)
```

### Step 3: Run Analysis (3 Parallel Sub-agents)

Launch 3 parallel sub-agents for the 3 perspectives:

```
# In the SAME message, make 3 parallel task tool calls:

task(
    subagent_name="general-purpose",
    title="Beginner Analysis: {area}",
    prompt="""
    Load skill: area_summary/.llms/skills/analyze_area_summary.md
    Analyze area: {area}
    Perspective: beginner

    Read inputs from: tmp_summary/{area}/
    Save output to: prompt_optimization/analysis_critics/analysis_{area}_beginner.json

    Return JSON with beginner_score and criteria details.
    """
)

task(
    subagent_name="general-purpose",
    title="Expert Analysis: {area}",
    prompt="""
    Load skill: area_summary/.llms/skills/analyze_area_summary.md
    Analyze area: {area}
    Perspective: expert

    Read inputs from: tmp_summary/{area}/
    Save output to: prompt_optimization/analysis_critics/analysis_{area}_expert.json

    Return JSON with expert_score and criteria details.
    """
)

task(
    subagent_name="general-purpose",
    title="Presenter Analysis: {area}",
    prompt="""
    Load skill: area_summary/.llms/skills/analyze_area_summary.md
    Analyze area: {area}
    Perspective: presenter

    Read inputs from: tmp_summary/{area}/
    Save output to: prompt_optimization/analysis_critics/analysis_{area}_presenter.json

    Return JSON with presenter_score and criteria details.
    """
)
```

**Output Files:**
```
prompt_optimization/analysis_critics/
├── analysis_{area}_beginner.json   # Beginner analysis
├── analysis_{area}_expert.json     # Expert analysis
├── analysis_{area}_presenter.json  # Presenter analysis
└── analysis_{area}.json            # Combined (aggregated in main context)
```

Aggregate results:
- Collect all perspective scores and issues
- Calculate combined score = mean of 3 perspective scores
- Save aggregated result to `analysis_{area}.json`

### Step 4: Check Against Threshold

```python
threshold = 8.0  # configurable

beginner_score = results["beginner"]["beginner_score"]
expert_score = results["expert"]["expert_score"]
presenter_score = results["presenter"]["presenter_score"]
combined_score = (beginner_score + expert_score + presenter_score) / 3

if combined_score >= threshold:
    print(f"✅ PASSED: Combined score {combined_score:.2f} >= {threshold}")
    # Still save analysis, but skip revision
else:
    print(f"❌ BELOW THRESHOLD: Combined score {combined_score:.2f} < {threshold}")
    # Proceed to revision
```

### Step 5: Revise Prompts (If Below Threshold)

Load and run revise_area_prompts skill:

> **Note:** The revision step includes the user-instructions-to-critics integration flow (Steps 8.2–8.4 in `revise_area_prompts.md`). After revising, it will ask the user whether to update `analyze_area_summary.md` with fixed issues and whether to clear `user_instructions.md`.

```
Load skill: .llms/skills/revise_area_prompts.md
Load user instructions: .llms/skills/user_instructions.md

Aggregate all issues from analyses:
- Beginner issues (sorted by severity)
- Expert issues (sorted by severity)
- Presenter issues (sorted by severity)

Map issues to prompts:
- Topic-level issues → topic_summary_prompt.txt
- Cross-topic issues → cross_topic_analysis_prompt.txt
- HTML/visual issues → html_generation_prompt.txt

Revise all three files:
- topic_summary_prompt.txt
- cross_topic_analysis_prompt.txt
- html_generation_prompt.txt

Save to revised_prompts/
```

### Step 6: Report Results

Output summary:
```
=== Area Optimization Pass Complete ===

Area: {area}

Scores:
- Beginner: 7.25
- Expert: 7.45
- Presenter: 6.80
- Combined: 7.17

Threshold: 8.0
Status: ❌ BELOW THRESHOLD

Revisions Applied:
- topic_summary_prompt.txt: Added jargon handling requirements, paper citation instructions
- cross_topic_analysis_prompt.txt: Added narrative arc structure, balance guidance
- html_generation_prompt.txt: Added visual structure requirements, takeaway formatting

Top Issues Addressed:
1. Jargon not explained (beginner, presenter)
2. Missing paper citations (expert)
3. No clear narrative arc (presenter)
4. Imbalanced topic coverage (presenter)

Next Steps:
- Re-run area summary generation with revised prompts
- Re-analyze to verify improvement
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `area` | Required | Which area to analyze (rag, agents, memory, etc.) |
| `threshold` | 8.0 | Quality target for combined score |
| `perspectives` | all | Which perspectives to run (beginner, expert, presenter, or all) |

---

## Subagent Orchestration

For efficient analysis, use parallel sub-agents:

```
# Analyze area from 3 perspectives = 3 parallel sub-agents

# Launch ALL in the SAME message:
task(title="Beginner: {area}", subagent="general-purpose",
     prompt="Load analyze_area_summary.md, analyze {area}, perspective=beginner")
task(title="Expert: {area}", subagent="general-purpose",
     prompt="Load analyze_area_summary.md, analyze {area}, perspective=expert")
task(title="Presenter: {area}", subagent="general-purpose",
     prompt="Load analyze_area_summary.md, analyze {area}, perspective=presenter")

# Then aggregate results and run revision
```

---

## Related Skills

| Skill | Purpose |
|-------|---------|
| `summarize_area.md` | Generate area summary outputs |
| `analyze_area_summary.md` | Analyze from 3 perspectives |
| `revise_area_prompts.md` | Apply revisions based on feedback |
| `user_instructions.md` | User-specified constraints for revisions |

---

## Prompt Files

The 3 prompt files being optimized:

| File | Controls | Location |
|------|----------|----------|
| `topic_summary_prompt.txt` | Individual topic summary generation | `prompts/` (source), `prompt_optimization/revised_prompts/` (working) |
| `cross_topic_analysis_prompt.txt` | Cross-topic synthesis | `prompts/` (source), `prompt_optimization/revised_prompts/` (working) |
| `html_generation_prompt.txt` | HTML report generation | `prompts/` (source), `prompt_optimization/revised_prompts/` (working) |

---

## Full Workflow Example

```
User: "Optimize area prompts for RAG"
