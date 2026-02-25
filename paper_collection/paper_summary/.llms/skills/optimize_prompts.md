---
description: Run a single optimization pass on paper summaries - fetch or generate, analyze, and revise
input:
  - paper_ids (list of integers to analyze, optional)
  - use_example (analyze the example json, default true)
  - threshold (quality target, default 8.0)
output:
  - Fetched/generated summaries in paper_summaries/
  - Analysis results in analysis_critics/
  - Revised prompts in revised_prompts/
---

# Single-Pass Prompt Optimization Skill

Run a single optimization pass: fetch summaries if needed, analyze from both perspectives, and revise prompts based on feedback.

## 🛑 CRITICAL: User Confirmation Required

**Before launching any analysis sub-agents, you MUST:**
1. Use `ask_user_question` tool to ask about summary source (A/B/C)
2. Wait for user response
3. Only then proceed to analysis

**DO NOT SKIP THIS STEP. DO NOT ASSUME "use existing" is acceptable.**

## Example Commands

```
"Optimize prompts"
→ Analyze example, revise based on feedback

"Optimize prompts for paper 50"
→ Fetch paper 50 if needed, analyze, revise

"Optimize prompts for papers 50, 3569, 3584"
→ Fetch all papers, analyze all, revise based on aggregated feedback

"Optimize the example with threshold 8.5"
→ Analyze example, revise to target 8.5
```

## When to Use

- User asks to "optimize prompts"
- User asks to "improve summary quality"
- User provides paper IDs for testing
- As part of prompt development workflow

## File Locations

| Folder | Purpose |
|--------|---------|
| `prompt_optimization/paper_summaries/` | Fetched paper summaries |
| `prompt_optimization/analysis_critics/` | Analysis results |
| `prompt_optimization/revised_prompts/` | Working prompt files |

---

## Single-Pass Workflow

> **🛑 STOP: Before running ANY analysis, you MUST ask the user to confirm the summary source option using `ask_user_question`. Do NOT proceed to Step 3 without explicit user confirmation.**

### Step 1: Determine What to Analyze

Check inputs:
- If `use_example=true` (default): Include `revised_prompts/summary_example.json`
- If `paper_ids` provided: Include `paper_summaries/paper_{id}.json` for each

### Step 2: Get Summaries Based on Source Option (MANDATORY USER CONFIRMATION)

**⚠️ CRITICAL: You MUST ask the user to confirm the summary source before proceeding. Do NOT skip this step.**

Use the `ask_user_question` tool to confirm:

```
ask_user_question(
    preamble="Before running analysis, I need to confirm how to get the summaries.",
    questions=[{
        "header": "Source",
        "question": "Summary source for paper summaries:",
        "options": [
            {"label": "A) Use existing", "description": "Use existing files in paper_summaries/ (if exists)"},
            {"label": "B) Fetch from DB", "description": "Fetch fresh from database"},
            {"label": "C) Regenerate", "description": "Re-generate using current prompts (generate_summary skill)"}
        ]
    }]
)
```

**Wait for user response before proceeding.**

**Option A: Use Existing (default)**
```
If paper_summaries/paper_{id}.json exists:
    Use it directly
Else:
    Fall back to Option B (fetch from DB)
```

**Option B: Fetch from Database**
```
Load skill: .llms/skills/fetch_summary.md
Fetch paper_id and save to paper_summaries/paper_{id}.json
```

**Option C: Re-generate Summary (Subagent Mode)**
```
task(
    subagent_name="general-purpose",
    title="Generate Summary: Paper {id}",
    prompt="""
    Load skill: .llms/skills/generate_summary.md
    Generate summary for paper_id: {id}
    PDF URL: {pdf_url}
    Save to: paper_summaries/paper_{id}.json
    """
)
```

### Step 3: Run Analysis (Parallel Sub-agents)

For EACH summary to analyze, spin up parallel sub-agents:

```
# For example + N papers, launch 2*(N+1) parallel sub-agents:

# Example analysis (if use_example=true)
task(subagent="general-purpose", prompt="Analyze summary_example.json, perspective=beginner, save to analysis_critics/analysis_example_beginner.json")
task(subagent="general-purpose", prompt="Analyze summary_example.json, perspective=expert, save to analysis_critics/analysis_example_expert.json")

# Paper analyses (for each paper_id)
task(subagent="general-purpose", prompt="Analyze paper_{id}.json, perspective=beginner, save to analysis_critics/analysis_{id}_beginner.json")
task(subagent="general-purpose", prompt="Analyze paper_{id}.json, perspective=expert, save to analysis_critics/analysis_{id}_expert.json")
```

**Output Files (for example + paper 50):**
```
analysis_critics/
├── analysis_example_beginner.json   # Beginner analysis of example
├── analysis_example_expert.json     # Expert analysis of example
├── analysis_example.json            # Combined (aggregated in main context)
├── analysis_50_beginner.json        # Beginner analysis of paper 50
├── analysis_50_expert.json          # Expert analysis of paper 50
└── analysis_50.json                 # Combined (aggregated in main context)
```
```

Aggregate results:
- Collect all beginner scores and issues
- Collect all expert scores and issues
- Calculate average scores

### Step 4: Check Against Threshold

```python
avg_beginner = mean([s["beginner_score"] for s in results])
avg_expert = mean([s["expert_score"] for s in results])
avg_combined = (avg_beginner + avg_expert) / 2

if avg_combined >= threshold:
    print(f"✅ PASSED: Combined score {avg_combined:.2f} >= {threshold}")
    # Still save analysis, but skip revision
else:
    print(f"❌ BELOW THRESHOLD: Combined score {avg_combined:.2f} < {threshold}")
    # Proceed to revision
```

### Step 5: Revise Prompts (If Below Threshold)

Load and run revise_prompts skill:
```
Load skill: .llms/skills/revise_prompts.md
Load user instructions: .llms/skills/user_instructions.md

Aggregate all issues from analyses:
- Beginner issues (sorted by frequency across papers)
- Expert issues (sorted by frequency across papers)

Revise all three files:
- prompt.txt
- summary_template.json
- summary_example.json

Save to revised_prompts/
```

### Step 6: Report Results

Output summary:
```
=== Optimization Pass Complete ===

Analyzed:
- summary_example.json (beginner: 7.32, expert: 7.12)
- paper_50.json (beginner: 7.45, expert: 7.28)
- paper_3569.json (beginner: 7.21, expert: 6.95)

Average Scores:
- Beginner: 7.33
- Expert: 7.12
- Combined: 7.22

Threshold: 8.0
Status: ❌ BELOW THRESHOLD

Revisions Applied:
- prompt.txt: Added accessibility requirements, technical precision requirements
- summary_template.json: Added key_terms section, guidance comments
- summary_example.json: Simplified thesis, added concrete examples

Top Issues Addressed:
1. Jargon density (appeared in 3/3 analyses)
2. Missing model specifications (appeared in 3/3 analyses)
3. No confidence intervals (appeared in 2/3 analyses)

Next Steps:
- Re-run analysis to verify improvement
## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_example` | true | Include summary_example.json in analysis |
| `paper_ids` | [] | List of paper IDs to analyze |
| `threshold` | 8.0 | Quality target for combined score |

---

## Subagent Orchestration

For analyzing multiple papers efficiently, use parallel sub-agents:

```
# Analyze 3 papers + example with both perspectives = 8 parallel sub-agents

# Launch ALL in the SAME message:
task(title="Beginner: Example", subagent="general-purpose",
     prompt="Load analyze_summary.md, analyze summary_example.json, perspective=beginner")
task(title="Expert: Example", subagent="general-purpose",
     prompt="Load analyze_summary.md, analyze summary_example.json, perspective=expert")
task(title="Beginner: Paper 50", subagent="general-purpose",
     prompt="Load analyze_summary.md, analyze paper_50.json, perspective=beginner")
task(title="Expert: Paper 50", subagent="general-purpose",
     prompt="Load analyze_summary.md, analyze paper_50.json, perspective=expert")
# ... etc for all papers

# Then aggregate results and run revision
```

---

## Related Skills

| Skill | Purpose |
|-------|---------|
| `fetch_summary.md` | Fetch paper summaries from database |
| `analyze_summary.md` | Analyze from beginner/expert perspectives |
| `revise_prompts.md` | Apply revisions based on feedback |
| `user_instructions.md` | User-specified constraints for revisions |
