---
description: Revise area summary prompts based on analysis feedback to improve output quality
oncalls:
  - paper_agent
---

# Area Prompt Revision Skill

Revise the 3 area summary prompt files (`topic_summary_prompt.txt`, `cross_topic_analysis_prompt.txt`, `html_generation_prompt.txt`) based on analysis feedback to improve output quality.

## Prerequisites

### 1. Prompt Files Must Exist in revised_prompts/

**IMPORTANT:** Before running any revision, ensure `prompt_optimization/revised_prompts/` contains all three files:

| Required File | Purpose |
|---------------|---------|
| `topic_summary_prompt.txt` | Instructions for generating individual topic summaries |
| `cross_topic_analysis_prompt.txt` | Instructions for cross-topic synthesis |
| `html_generation_prompt.txt` | Instructions for HTML report generation |

**If any file is missing, copy from source:**
```bash
# Check and copy missing files
cd area_summary

# Copy topic_summary_prompt.txt if missing
[ ! -f prompt_optimization/revised_prompts/topic_summary_prompt.txt ] && \
  cp prompts/topic_summary_prompt.txt prompt_optimization/revised_prompts/

# Copy cross_topic_analysis_prompt.txt if missing
[ ! -f prompt_optimization/revised_prompts/cross_topic_analysis_prompt.txt ] && \
  cp prompts/cross_topic_analysis_prompt.txt prompt_optimization/revised_prompts/

# Copy html_generation_prompt.txt if missing
[ ! -f prompt_optimization/revised_prompts/html_generation_prompt.txt ] && \
  cp prompts/html_generation_prompt.txt prompt_optimization/revised_prompts/
```

### 2. Analysis Results Must Exist

**IMPORTANT:** `prompt_optimization/analysis_critics/` must contain analysis results. Revisions require analysis feedback to guide changes.

**If analysis_critics is empty, run analysis first:**
```
Load skill at .llms/skills/analyze_area_summary.md
Analyze area: <area_name>
Perspective: all
Save results to analysis_critics/
```

This will generate:
- `analysis_{area}_beginner.json` - Beginner perspective
- `analysis_{area}_expert.json` - Expert perspective
- `analysis_{area}_presenter.json` - Presenter perspective
- `analysis_{area}.json` - Combined result

---

## Example Commands

```
"Revise area prompts based on the analysis feedback"

"Fix accessibility issues in topic_summary_prompt"

"Improve HTML generation for better visual structure"

"Update prompts to require specific paper citations"
```

---

## When to Use

- After analyzing area summaries and finding issues (score < threshold)
- User asks to "improve area prompts based on feedback"
- User asks to "fix issues in the prompts"
- As part of the prompt optimization workflow

---

## File Locations

**Working Directory:** `prompt_optimization/revised_prompts/`

| File | Purpose | Path |
|------|---------|------|
| Topic Summary Prompt | Instructions for topic summaries | `prompt_optimization/revised_prompts/topic_summary_prompt.txt` |
| Cross-Topic Prompt | Instructions for cross-topic analysis | `prompt_optimization/revised_prompts/cross_topic_analysis_prompt.txt` |
| HTML Generation Prompt | Instructions for HTML output | `prompt_optimization/revised_prompts/html_generation_prompt.txt` |
| User Instructions | Revision constraints | `.llms/skills/user_instructions.md` |

**Source Files (DO NOT EDIT):** `prompts/` - Original versions for reference/reset

---

## Issue-to-Prompt Mapping

When addressing analysis issues, map each issue to the appropriate prompt file(s):

| Issue Category | Primary Prompt | May Also Affect |
|----------------|----------------|-----------------|
| **Beginner: accessibility** | `topic_summary_prompt.txt` | `html_generation_prompt.txt` |
| **Beginner: jargon_handling** | `topic_summary_prompt.txt` | - |
| **Beginner: motivation_clarity** | `topic_summary_prompt.txt` | - |
| **Beginner: logical_flow** | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| **Beginner: completeness** | `topic_summary_prompt.txt` | - |
| **Expert: technical_precision** | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| **Expert: coverage** | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| **Expert: novelty_assessment** | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| **Expert: evidence_grounding** | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| **Expert: actionability** | `cross_topic_analysis_prompt.txt` | - |
| **Presenter: narrative_arc** | `cross_topic_analysis_prompt.txt` | `html_generation_prompt.txt` |
| **Presenter: visual_structure** | `html_generation_prompt.txt` | - |
| **Presenter: key_takeaways** | `topic_summary_prompt.txt` | `html_generation_prompt.txt` |
| **Presenter: paper_links** | `html_generation_prompt.txt` | - |
| **Presenter: balance** | `cross_topic_analysis_prompt.txt` | `html_generation_prompt.txt` |

---

## Integrating User Instructions

> 🛑 **MANDATORY: User Instructions MUST Be Applied First**
>
> Before considering analysis feedback, you MUST read and apply EVERY item in `user_instructions.md`.
> This is the PRIMARY source of revision requirements. Analysis feedback is SECONDARY.

### Step 0: Read User Instructions (REQUIRED FIRST STEP)

```
Read: .llms/skills/user_instructions.md
```

### User Instructions Structure

| Section | What It Contains | Action Required |
|---------|------------------|-----------------|
| **Goals** | High-level improvement objectives | Ensure ALL revisions align with these goals |
| **For Beginners** | Accessibility requirements | **APPLY EVERY BULLET POINT** to prompts |
| **For Experts** | Technical precision requirements | **APPLY EVERY BULLET POINT** to prompts |
| **For Tutorial Presenters** | Presentation-readiness requirements | **APPLY EVERY BULLET POINT** to prompts |
| **Good and Keep** | What's working well | **DO NOT CHANGE these elements** |
| **Specific Issues with Current HTML Output** | Known problems to fix | **FIX EVERY LISTED ISSUE** |
| **Examples of Good vs Bad** | Reference examples | Follow good patterns, avoid bad ones |

### MANDATORY: Create User Instructions Checklist

**Before making any changes**, create a checklist from `user_instructions.md`:

```markdown
## User Instructions Checklist

### For Beginners
- [ ] Item 1 from user_instructions.md → Which prompt file? What change?
- [ ] Item 2 from user_instructions.md → Which prompt file? What change?
...

### For Experts
- [ ] Item 1 from user_instructions.md → Which prompt file? What change?
...

### For Tutorial Presenters
- [ ] Item 1 from user_instructions.md → Which prompt file? What change?
...

### Specific Issues with Current HTML Output
- [ ] Issue 1 → Which prompt file? What change?
...

### Good and Keep (DO NOT MODIFY)
- One-sentence definition of area/category/component/theme
- (list all items to preserve)
```

### User Instruction → Prompt Mapping

| User Instruction Category | Primary Prompt File | May Also Affect |
|---------------------------|---------------------|-----------------|
| For Beginners: text length | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| For Beginners: method count | `topic_summary_prompt.txt` | `html_generation_prompt.txt` |
| For Beginners: no premature numbers | `topic_summary_prompt.txt` | `cross_topic_analysis_prompt.txt` |
| For Experts: running examples | `topic_summary_prompt.txt` | `html_generation_prompt.txt` |
| For Experts: timelines | `topic_summary_prompt.txt` | `html_generation_prompt.txt` |
| For Presenters: paper links | `html_generation_prompt.txt` | - |
| Specific HTML Issues | `html_generation_prompt.txt` | - |

### Verification: All Items Applied?

**After revising, verify EVERY checkbox is checked:**

```markdown
## User Instructions Applied ✓

### For Beginners
- [x] ~30 words target → Added word count limits to overview fields
- [x] No premature numbers → Added "NO numbers or percentages" guidance
- [x] Max 5 methods → Added "STRICT MAXIMUM: 5 methods per topic"
...

### For Experts
- [x] Running examples for all topics → Required running_example field
...

### Specific Issues
- [x] Merge "How field evolved" and timeline → Updated HTML prompt section ordering
...
```

**⚠️ If ANY item is unchecked, you MUST continue revising until ALL items are addressed.**

---

## Revision Workflow

### Step 1: Check Prerequisites
Ensure all three prompt files exist in `revised_prompts/`. Copy from `prompts/` if missing.

### Step 2: Load User Instructions and Create Checklist (MANDATORY)

> 🛑 **THIS STEP IS MANDATORY AND MUST BE DONE FIRST**

1. **Read** `.llms/skills/user_instructions.md`
2. **Create a checklist** of ALL items from user_instructions.md (see "MANDATORY: Create User Instructions Checklist" above)
3. **Map each item** to the prompt file(s) that need to be modified
4. **Do NOT proceed** to Step 3 until you have a complete checklist

### Step 3: Read Analysis Feedback (Secondary)
Get the latest analysis from `analysis_critics/`:
- `analysis_{area}.json` (combined)
- `analysis_{area}_beginner.json` (beginner details)
- `analysis_{area}_expert.json` (expert details)
- `analysis_{area}_presenter.json` (presenter details)

### Step 4: Map Issues to Prompts
For each issue identified in analysis:
1. Determine which prompt file(s) it maps to (see Issue-to-Prompt Mapping)
2. Identify the specific section/instruction to modify
3. Plan coordinated changes across files if needed

### Step 5: Revise All Three Files Together
Apply revisions to ALL files as a coordinated set:

| File | Focus Areas |
|------|-------------|
| `topic_summary_prompt.txt` | Clarity, jargon handling, technical precision, coverage |
| `cross_topic_analysis_prompt.txt` | Narrative arc, balance, actionability, evidence grounding |
| `html_generation_prompt.txt` | Visual structure, paper links, presentation readiness |

**Cross-Prompt Consistency:**
- If `topic_summary_prompt.txt` adds a new field (e.g., `key_insights`), then `html_generation_prompt.txt` must render it
- If `cross_topic_analysis_prompt.txt` changes structure, `html_generation_prompt.txt` must adapt

### Step 6: Save to revised_prompts/
Save ALL changes to `prompt_optimization/revised_prompts/`:
```
prompt_optimization/revised_prompts/topic_summary_prompt.txt
prompt_optimization/revised_prompts/cross_topic_analysis_prompt.txt
prompt_optimization/revised_prompts/html_generation_prompt.txt
```

**DO NOT save to prompts/ or any other location.**

### Step 7: Update revision_metadata.json

**REQUIRED:** After every revision, update `prompt_optimization/revised_prompts/revision_metadata.json`:

```json
{
  "revision_date": "<ISO timestamp>",
  "revision_pass": "<pass name>",
  "previous_passes": ["<prior pass summaries>"],
  "area_analyzed": "<area_name>",
  "scores": {
    "beginner": <score>,
    "expert": <score>,
    "presenter": <score>,
    "combined": <score>
  },
  "threshold": 8.0,
  "passed": <true|false>,
  "files_revised": ["topic_summary_prompt.txt", "cross_topic_analysis_prompt.txt", "html_generation_prompt.txt"],
  "key_changes": {
    "topic_summary_prompt.txt": ["<change 1>", "<change 2>"],
    "cross_topic_analysis_prompt.txt": ["<change 1>", "<change 2>"],
    "html_generation_prompt.txt": ["<change 1>", "<change 2>"]
  },
  "user_instructions_applied": {
    "for_beginners": {
      "items": ["<item 1 from user_instructions.md>", "<item 2>"],
      "applied": ["<how item 1 was applied>", "<how item 2 was applied>"]
    },
    "for_experts": {
      "items": ["<item 1>"],
      "applied": ["<how item 1 was applied>"]
    },
    "for_presenters": {
      "items": ["<item 1>"],
      "applied": ["<how item 1 was applied>"]
    },
    "specific_html_issues": {
      "items": ["<issue 1>", "<issue 2>"],
      "applied": ["<how issue 1 was fixed>", "<how issue 2 was fixed>"]
    },
    "good_and_keep_preserved": ["<item 1 preserved>", "<item 2 preserved>"]
  },
  "analysis_issues_addressed": {
    "beginner": ["<issue> → <fix>"],
    "expert": ["<issue> → <fix>"],
    "presenter": ["<issue> → <fix>"]
  }
}
```

**⚠️ CRITICAL:** The `user_instructions_applied` section MUST list EVERY item from `user_instructions.md` and show how each was applied. If any item is missing, the revision is incomplete.

### Step 8: Handle Completed User Instructions (Final Step)

After completing all revisions, check if ALL points in `user_instructions.md` have been addressed.

#### 8.1 Verify All Instructions Fixed

Review `revision_metadata.json` → `user_instructions_addressed.specific_issues_fixed` to confirm every item from `user_instructions.md` has been addressed.

**If any items remain unaddressed:** Stop here and continue revising until all are fixed.

#### 8.2 If All Instructions Fixed → Ask User Two Questions

> 🛑 **MANDATORY USER CONFIRMATION**
>
> When ALL user_instructions are fixed, you MUST ask the user these two questions before proceeding.

**YOU MUST** use the `ask_user_question` tool:

```
ask_user_question(
    preamble="All specific issues from user_instructions.md have been addressed in this revision pass. Before completing, I need your input on two follow-up actions.",
    questions=[
        {
            "question": "Update analyze_area_summary.md critics with these instructions?",
            "header": "Critics",
            "options": [
                {"label": "Yes", "description": "Add the fixed issues to analyze_area_summary.md criteria so future analyses check for them"},
                {"label": "No", "description": "Keep analyze_area_summary.md as is"}
            ]
        },
        {
            "question": "Clear the specific issues from user_instructions.md?",
            "header": "Clear",
            "options": [
                {"label": "Yes", "description": "Clear the issues (keep skeleton placeholders)"},
                {"label": "No", "description": "Keep user_instructions.md as is"}
            ]
        }
    ]
)
```

#### 8.3 If User Confirms "Update Critics" → Update analyze_area_summary.md

Add the fixed issues as new criteria checks in `analyze_area_summary.md`:

1. Read current `.llms/skills/analyze_area_summary.md`
2. Add the fixed issues to the "User Instructions Checklist" tables
3. Save the updated file

#### 8.4 If User Confirms "Clear Instructions" → Clear user_instructions.md

**IMPORTANT:** Do NOT delete the file or empty it completely. Keep the skeleton structure.

Replace the content of `.llms/skills/user_instructions.md` with the skeleton (see user_instructions.md for template).

---

## Revision Guidelines

### Prioritize Issues

From analysis results, prioritize:
1. **High severity** - Fundamental problems (accuracy, clarity, coverage)
2. **Medium severity** - Notable issues (jargon, structure, balance)
3. **Low severity** - Polish items (wording, formatting)

### Apply Conservative Changes

**Principle: Minimal effective change**

| Issue Type | Revision Strategy |
|------------|-------------------|
| Jargon in topic summaries | Add instruction to define terms on first use |
| Missing paper citations | Add requirement for specific paper references |
| Poor narrative flow | Add explicit story arc structure |
| Visual structure issues | Add section/formatting requirements to HTML prompt |
| Balance problems | Add proportionality guidance |

### Preserve Working Elements

Before changing anything, identify what's working:
- High-scoring criteria should NOT be touched
- Only address issues explicitly identified in analysis
- Respect "Good and Keep" items from user instructions

### Cross-Prompt Coordination

When making changes, ensure consistency:

| If You Change... | Also Update... |
|------------------|----------------|
| Topic summary output format | HTML generation to render new fields |
| Cross-topic analysis structure | HTML generation to reflect new structure |
| New required fields | All downstream prompts that consume them |

---

## Output

After revision, report:
1. What files were changed
2. Summary of changes per file
3. Which analysis issues were addressed
4. Which user_instructions issues were addressed
5. Updated revision_metadata.json

```
Revised files saved to prompt_optimization/revised_prompts/:
- topic_summary_prompt.txt: Added jargon handling, paper citation requirements
- cross_topic_analysis_prompt.txt: Added narrative arc structure
- html_generation_prompt.txt: Added visual structure requirements
- revision_metadata.json: Updated with pass details

User Instructions Addressed:
✓ For Beginners: Ensure technical terms are explained
✓ For Experts: Include specific paper citations
✓ For Presenters: Add crisp takeaways

Analysis Issues Addressed:
- Beginner jargon_handling (6.5 → target 8.0)
- Expert evidence_grounding (7.0 → target 8.0)
- Presenter narrative_arc (6.8 → target 8.0)
```

---

## Quality Thresholds

Target scores for optimization:
- Beginner Score: >= 8.0/10
- Expert Score: >= 8.0/10
- Presenter Score: >= 8.0/10
- Combined Score: >= 8.0/10
