---
description: Generate structured JSON summaries of research papers using current prompt templates
input:
  - pdf_url or paper_id to identify the paper
output:
  - JSON summary following template structure
  - Saved to prompt_optimization/paper_summaries/paper_{paper_id}.json (replaces existing)
---

# Generate Paper Summary

Generate a structured JSON summary of a research paper using the current prompt templates.

## Example Commands

```
"Generate a summary for https://arxiv.org/pdf/2501.15228"

"Generate summary for paper 3569 using the current prompts"

"Create a new summary for the RAG paper at <URL>"
```

## Prerequisites

Before running this skill, ensure:
1. Access to the paper PDF (via URL or local file)
2. Prompt templates available:
   - First check `prompt_optimization/revised_prompts/`
   - If not found, copy from `prompts/` folder

## Usage

### Direct Mode
```
/skill generate_summary
```
Then provide the paper URL or paper_id when prompted.

### Subagent Mode (Isolated Context)
Use the task tool to run in isolated context:
```
task(
    subagent_name="general-purpose",
    title="Generate Summary: Paper {id}",
    prompt="""
    Load and execute the skill at:
    .llms/skills/generate_summary.md

    Generate a summary for paper_id: {paper_id}
    PDF URL: {pdf_url}

    Use prompt templates from:
    prompt_optimization/revised_prompts/

    Save the result to:
    prompt_optimization/paper_summaries/paper_{paper_id}.json
    """
)

## Instructions

### Step 1: Identify the Paper

Get the paper PDF URL either:
1. **Direct URL**: User provides arxiv/PDF URL (e.g., `https://arxiv.org/pdf/2501.15228`)
2. **From paper_id**: Fetch paper metadata from database to get the PDF link

```python
# If paper_id is provided, fetch from database first:
import sys
sys.path.insert(0, '/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection')
from paper_db import PaperDB

db = PaperDB()
paper = db.get_paper_by_id(paper_id)
pdf_url = paper['link']  # Should be the arxiv/PDF URL
db.close()
```

### Step 2: Load Prompt Templates

Check for templates in order:
1. First check `prompt_optimization/revised_prompts/`
2. If not found, copy from `prompts/` folder to `revised_prompts/`

Required files:
- `prompt.txt` - Main prompt with placeholders
- `summary_template.json` - JSON structure template
- `summary_example.json` - Example output

Placeholders in prompt.txt:
- `<PDF_URL>` - Replaced with the actual PDF URL
- `<json_template>` - Replaced with `summary_template.json`
- `<json_example>` - Replaced with `summary_example.json`
- `<topic_background>` - Replaced with topic-specific context

### Step 3: Generate Summary

1. Read the prompt template from `prompt_optimization/revised_prompts/prompt.txt`
2. Read the JSON template from `prompt_optimization/revised_prompts/summary_template.json`
3. Read the example from `prompt_optimization/revised_prompts/summary_example.json`
4. Construct the full prompt by replacing placeholders
5. Download and read the PDF content
6. Generate the JSON summary following the template structure

### Step 4: Validate the Output

Ensure the generated summary:
1. Follows the exact JSON structure from `summary_template.json`
2. Contains all required sections
3. Has no TODO placeholders remaining
4. Explains all jargon and acronyms on first use

### Step 5: Save the Result

Save to:
```
prompt_optimization/paper_summaries/paper_{paper_id}.json
```

**Note:** This replaces any existing file with the same name. No versioning or renaming.

---

### Step 6: Populate Database (Optional)

> 🛑 **STOP: MANDATORY USER CONFIRMATION REQUIRED**
>
> After saving the JSON file, you MUST ask the user if they want to populate the database.
> **DO NOT skip this confirmation. DO NOT assume the answer.**

#### 6.1 Ask User for Confirmation

**YOU MUST** use the `ask_user_question` tool to confirm:

```
ask_user_question(
    preamble="The summary has been saved to prompt_optimization/paper_summaries/paper_{paper_id}.json. I can also update the database with this summary.",
    questions=[
        {
            "question": "Do you want to populate the database with this summary?",
            "header": "Database",
            "options": [
                {"label": "Yes", "description": "Update the database with the generated summary"},
                {"label": "No", "description": "Keep the JSON file only, do not update database"}
            ]
        }
    ]
)
```

#### 6.2 If User Confirms "Yes"

Use the `paper_db` module to update the summary in the database:

```python
import sys
import json
sys.path.insert(0, '/Users/lunadong/fbsource/fbcode/assistant/research/paper-agent/paper_collection')
from paper_db import PaperDB

# Load the generated summary
with open(f'prompt_optimization/paper_summaries/paper_{paper_id}.json', 'r') as f:
    summary_json = json.load(f)

# Update database
db = PaperDB()
db.update_paper_summary(paper_id, summary_json)
db.close()

print(f"✅ Database updated for paper_id: {paper_id}")
```

#### 6.3 If User Declines "No"

Simply acknowledge and complete:
```
"Summary saved to file only. Database not updated."
```

---

## Storage Location

Results should be stored in:
```
prompt_optimization/paper_summaries/
```

This folder is used for:
- Storing generated summaries for comparison
- Input to the analyze_summary skill
- Tracking paper summaries

## Related Skills

- **fetch_summary.md**: Fetch existing summary from database
- **analyze_summary.md**: Analyze a summary for quality
- **revise_prompts.md**: Revise prompts based on analysis feedback
- **optimize_prompts.md**: Full optimization workflow
