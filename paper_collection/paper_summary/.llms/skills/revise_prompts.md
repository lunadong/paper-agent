---
description: Revise paper summary prompts and examples based on analysis feedback to improve quality
input:
  - analysis_feedback from analyze_summary skill
  - user_instructions from .llms/skills/user_instructions.md (loaded at runtime)
  - pdf_url of the paper used in summary_example.json (fetch and read to verify/correct claims)
output:
  - Updated prompt.txt, summary_template.json, summary_example.json in revised_prompts/
---

# Prompt Revision Skill

Revise paper summary prompts and examples based on analysis feedback to improve output quality.

## Prerequisites

### 1. Prompt Files Must Exist

**IMPORTANT:** Before running any revision, ensure `prompt_optimization/revised_prompts/` contains all three files:

| Required File | Purpose |
|---------------|---------|
| `prompt.txt` | Main LLM instructions |
| `summary_template.json` | Output structure definition |
| `summary_example.json` | Few-shot example |

**If any file is missing, copy from source:**
```bash
# Check and copy missing files
cd /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection/paper_summary

# Copy prompt.txt if missing
[ ! -f prompt_optimization/revised_prompts/prompt.txt ] && cp prompts/prompt.txt prompt_optimization/revised_prompts/

# Copy summary_template.json if missing
[ ! -f prompt_optimization/revised_prompts/summary_template.json ] && cp prompts/summary_template.json prompt_optimization/revised_prompts/

# Copy summary_example.json if missing
[ ! -f prompt_optimization/revised_prompts/summary_example.json ] && cp prompts/summary_example.json prompt_optimization/revised_prompts/
```

### 2. Analysis Results Must Exist

**IMPORTANT:** `prompt_optimization/analysis_critics/` must contain analysis results. Revisions require analysis feedback to guide changes.

**If analysis_critics is empty, run analysis first:**
```
Load skill at .llms/skills/analyze_summary.md
Analyze: prompt_optimization/revised_prompts/summary_example.json
Perspective: both
Save results to analysis_critics/
```

This will generate:
- `analysis_example_beginner.json` - Beginner perspective
- `analysis_example_expert.json` - Expert perspective
- `analysis_example.json` - Combined result

**Check in Python:**
```python
import os

analysis_dir = "prompt_optimization/analysis_critics"
if not os.listdir(analysis_dir):
    print("ERROR: analysis_critics/ is empty!")
    print("Run analyze_summary skill on summary_example.json first.")
else:
    print(f"Found {len(os.listdir(analysis_dir))} analysis files")
```

## Example Commands

```
"Revise prompts based on the analysis feedback above"

"Fix jargon handling issues - add explanations for DPO and MAPPO"

"Improve the prompts to require SOTA comparisons"

"Fix the architecture figure description"
```

## When to Use

- After analyzing summaries and finding issues (score < threshold)
- User asks to "improve prompts based on feedback"
- User asks to "fix issues in the prompts"
- As part of the progressive optimization workflow

## File Locations

**Working Directory:** `prompt_optimization/revised_prompts/`

| File | Purpose | Path |
|------|---------|------|
| Main Prompt | LLM instructions | `prompt_optimization/revised_prompts/prompt.txt` |
| Template | Output structure | `prompt_optimization/revised_prompts/summary_template.json` |
| Example | Few-shot example | `prompt_optimization/revised_prompts/summary_example.json` |
| User Instructions | Revision constraints | `.llms/skills/user_instructions.md` |

**Source Files (DO NOT EDIT):** `prompts/` - Original versions for reference/reset

## Storage Folders

| Folder | Purpose |
|--------|---------|
| `paper_summaries/` | Store fetched/generated paper summaries |
| `analysis_critics/` | Store analysis results |
| `revised_prompts/` | Working directory for prompt iteration |

---

## Integrating User Instructions

**IMPORTANT:** Before revising, always load and integrate user instructions:

```
Read: .llms/skills/user_instructions.md
```

The user instructions define:
- **Goals** - What to improve overall
- **For Beginners** - Accessibility requirements
- **For Experts** - Technical precision requirements
- **Good and Keep** - What's working (don't change)
- **Specific Issues** - Known problems to fix
- **Examples** - Good vs bad examples

These instructions MUST guide all revisions.

---

## Revision Workflow

### Step 1: Check Prerequisites
Ensure all three files exist in `revised_prompts/`. Copy from `prompts/` if missing.

### Step 2: Load User Instructions
Read `.llms/skills/user_instructions.md` for revision constraints.

### Step 3: Fetch and Read the Source Paper PDF
**IMPORTANT:** When revising `summary_example.json`, you MUST read the original paper to verify and correct claims.

1. Get the `pdf_url` or `arxiv_id` from the current `summary_example.json`
2. Fetch the paper content using WebFetch on the arxiv abstract page:
   ```
   WebFetch: https://arxiv.org/abs/{arxiv_id}
   Prompt: "Extract the full paper content including: title, authors, institutions, venue, abstract, methodology, experimental results (all tables with exact numbers), model details, hyperparameters, datasets, metrics, figures described, limitations, and any other technical details."
   ```
3. Use the extracted paper content to cross-check every claim in `summary_example.json`

**Why this matters:** Without PDF verification, revisions may introduce or preserve fabricated claims (wrong venue, hallucinated confidence intervals, incorrect model details). Every factual claim in the example must be grounded in the actual paper.

### Step 4: Read Analysis Feedback
Get the latest analysis from `analysis_critics/`:
- `analysis_example.json` (combined)
- `analysis_example_beginner.json` (beginner details)
- `analysis_example_expert.json` (expert details)

### Step 5: Revise All Three Files Together
Apply revisions to ALL files as a coordinated set:

| File | Focus Areas |
|------|-------------|
| `prompt.txt` | Add/clarify instructions for systematic issues |
| `summary_template.json` | Adjust structure, add guidance comments |
| `summary_example.json` | Fix specific content issues |

### Step 6: Save to revised_prompts/
Save ALL changes to `prompt_optimization/revised_prompts/`:
```
prompt_optimization/revised_prompts/prompt.txt
prompt_optimization/revised_prompts/summary_template.json
prompt_optimization/revised_prompts/summary_example.json
```

**DO NOT save to prompts/v2/ or any other location.**

---

## Revision Prompt Template

Use this when generating revisions:

~~~
You are an expert prompt engineer helping to improve prompts for academic paper summarization.

## Original Paper Content

**IMPORTANT:** Use this to verify and correct all factual claims in summary_example.json.
Any claim not supported by the paper must be removed or corrected.

```
{paper_content}
```

## Current Prompt Files

### prompt.txt (main prompt)
```
{current_prompt}
```

### summary_template.json (output structure)
```json
{current_template}
```

### summary_example.json (example output)
```json
{current_example}
```

## Analysis Results

### Beginner Perspective (score: {beginner_score}/10)

**Top Issues:**
{beginner_issues}

**Suggestions:**
{beginner_suggestions}

### Expert Perspective (score: {expert_score}/10)

**Top Issues:**
{expert_issues}

**Suggestions:**
{expert_suggestions}

## User Instructions
```
{user_instructions_content}
```

## Your Task

Based on the analysis results and user instructions, generate REVISED versions of ALL THREE prompt files.

For each file, explain your changes first, then provide the complete revised content.

Your response must be a JSON object with this structure:
```json
{
  "revision_summary": "Brief overview of the key changes made",

  "prompt_txt": {
    "changes": ["List of specific changes made to prompt.txt"],
    "content": "The complete revised prompt.txt content"
  },

  "summary_template": {
    "changes": ["List of specific changes made to the template"],
    "content": { ... complete revised JSON template ... }
  },

  "summary_example": {
    "changes": ["List of specific changes made to the example"],
    "content": { ... complete revised JSON example ... }
  }
}
```

Important guidelines:
1. Address issues from BOTH beginner and expert perspectives
2. Follow the user's specific instructions (especially "Good and Keep" items)
3. Maintain backward compatibility where possible
4. Make changes to ALL THREE files as a coordinated set
5. Ensure the example demonstrates all template fields properly
6. **Every factual claim in summary_example.json must be verified against the original paper** — remove or correct any unverified venue, numerical result, confidence interval, hyperparameter, or model detail
7. Add instructions to prompt.txt requiring the LLM to only include facts stated in the source paper (no fabrication of statistical tests, confidence intervals, or other details)
~~~

---

## Revision Guidelines

### Prioritize Issues

From analysis results, prioritize:
1. **High severity** - Fundamental problems (accuracy, clarity)
2. **Medium severity** - Notable issues (jargon, structure)
3. **Low severity** - Polish items (wording, formatting)

### Apply Conservative Changes

**Principle: Minimal effective change**

| Issue Type | Revision Strategy |
|------------|-------------------|
| Jargon in example | Replace specific terms with explanations |
| Missing context | Add background sentences, not paragraphs |
| Structural issues | Reorder existing content, don't add sections |
| Technical errors | Correct specific claims |
| Vague instructions | Add specific examples to prompt.txt |

### Preserve Working Elements

Before changing anything, identify what's working:
- High-scoring criteria should NOT be touched
- Only address issues explicitly identified in analysis
- Respect "Good and Keep" items from user instructions

---

## Revision Examples

### Example: Fixing Jargon in summary_example.json

**Analysis Issue:**
```json
{
  "criterion": "jargon_handling",
  "location": "Core.one_sentence_thesis",
  "description": "Uses 'cross-attention mechanisms' without explanation"
}
```

**Before:**
```json
"one_sentence_thesis": "We propose a novel transformer architecture with cross-attention mechanisms for multi-modal fusion."
```

**After:**
```json
"one_sentence_thesis": "We introduce a new AI model that can process multiple types of data (like text and images) together by allowing each type to inform how the other is understood."
```

### Example: Adding Clarity to prompt.txt

**Analysis Issue:**
```
Multiple papers have unclear methodology descriptions
```

**Add to prompt.txt:**
```
When describing the methodology:
- Start with the high-level approach in plain language
- Then provide technical details
- Always explain WHY each step is necessary, not just WHAT it does
- Use concrete examples where possible
```

### Example: Adjusting summary_template.json

**Analysis Issue:**
```
Technical_details section is too dense for beginners
```

**Before:**
```json
"Technical_details": {
  "_comment": "Technical approach and methods"
}
```

**After:**
```json
"Technical_details": {
  "_comment": "Technical approach and methods. Start with intuitive explanation, then add formal details.",
  "approach_intuition": "...",
  "formal_methodology": "..."
}
```

---

## Output

After revision, report:
1. What files were changed
2. Summary of changes per file
3. Which analysis issues were addressed

```
Revised files saved to prompt_optimization/revised_prompts/:
- prompt.txt: Added methodology clarity instructions
- summary_template.json: Restructured Technical_details
- summary_example.json: Fixed jargon in one_sentence_thesis

Issues addressed:
- Beginner jargon_handling (7 → target 8.0)
- Expert technical_precision (7 → target 8.0)
```

---

## Quality Thresholds

Target scores for optimization:
- Beginner Accessibility: >= 8.0/10
- Expert Technical Depth: >= 8.0/10
- Combined Score: >= 8.0/10
