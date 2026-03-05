---
description: Analyze area summary outputs from beginner, expert, and tutorial presenter perspectives to identify quality issues
oncalls:
  - paper_agent
---

# Area Summary Analysis Skill

Analyze area summary outputs from **3 perspectives** (beginner, expert, tutorial presenter) to identify quality issues and improvement opportunities.

## 🔍 User Instructions Checklist

**CRITICAL:** In addition to weighted criteria, ALWAYS check specific issues from `user_instructions.md`:

### Beginner-Side Checks
| Check | Where to Look | What Fails |
|-------|--------------|------------|
| Jargon explained | Topic summaries, HTML overview, `glossary` | Technical terms used without definition; missing from `glossary` array |
| Motivation clear | Topic summaries `overview` field | Why this area matters is unclear |
| Logical flow | HTML structure, cross-topic analysis | Jumping between concepts without transitions |
| No assumed knowledge | All outputs | Assumes reader knows prior work/methods |
| Structured overview (motivation + baseline + challenges) | Topic summaries `overview.motivation`, `overview.baseline`, `overview.key_challenges` | `overview` is a flat string instead of structured object; OR any of the three sub-fields is missing/empty |
| Top-box area overview | Cross-topic `area_overview`; HTML "Area Overview Box" | Missing `area_overview.definition`, `area_overview.motivation`, or `area_overview.key_paradigms` in cross-topic JSON; or no area overview box in HTML |
| Category-level progress shown | Topic summaries `timeline.overall_progress` | For category/component topics, timeline lacks `overall_progress` section summarizing holistic advancement and paradigm shifts |
| Running example present | Topic summaries `running_example` | No concrete example illustrating challenges and how methods address them; `running_example` field missing or empty |
| Max 5 methods per topic | Topic summaries `methods` array | More than 5 methods listed; similar approaches not grouped into higher-level method categories |
| **Text brevity (~30 words)** | Topic summaries `definition`, `motivation`, `summary` fields | Text exceeds ~30 words; verbose explanations instead of concise statements |
| **No premature numbers in motivation** | Topic summaries `overview.motivation`; HTML overview | Contains specific numbers/percentages (e.g., "reducing errors by 18-57%") before establishing context |
| **Methods ranked by importance** | Topic summaries `methods` array order | Methods listed alphabetically or chronologically instead of by importance/popularity |
| **Surveys ranked by year** | Topic summaries `surveys` or survey references | Surveys not ordered from oldest to newest |
| **Meaningful method names (not author names)** | Topic summaries `methods[].method_name` | Method names use author citations ('Gao et al.') instead of descriptive names ('Comprehensive RAG Taxonomy Survey'). Author names may appear in representative_papers but NOT as the method_name |

### Expert-Side Checks
| Check | Where to Look | What Fails |
|-------|--------------|------------|
| Paper attribution | Topic summaries `key_papers` | Claims without specific paper references |
| Technical accuracy | Method descriptions | Incorrect or oversimplified method descriptions |
| Coverage completeness | Cross-topic analysis | Major sub-areas or significant papers missing |
| Novelty vs incremental | Topic summaries | All papers treated as equally novel |
| Timeline per topic with inline paper links | Topic summaries `timeline`; HTML timeline section | Missing `timeline.periods`; or timeline development bullets lack inline paper links; or timeline has separate "Key Papers" list instead of embedding links inline |
| Method evolution via comparison_to_sota | Topic summaries `methods[].improves_on`; cross-topic `method_evolution` | Methods listed without `improves_on` field; no method evolution chains in cross-topic analysis |
| Benchmark results with absolute numbers | Topic summaries `benchmark_results`; cross-topic `benchmark_leaderboard` | No `benchmark_results` in topic summary when metrics exist; or `benchmark_leaderboard` missing from cross-topic; or showing only relative increments without absolute scores |
| **Running example for ALL topics** | Topic summaries `running_example` for every category/component/theme | Any topic missing a concrete running example |
| **Timeline for ALL topics** | Topic summaries `timeline` for every category/component/theme | Any topic missing timeline showing field evolution |
| **Overlapping timeline stages OK** | Topic summaries `timeline.periods` | Flagging overlapping date ranges as errors (overlapping is acceptable and expected) |
| **Absolute benchmark numbers required** | Topic summaries `benchmark_results`, cross-topic `benchmark_leaderboard` | Showing only relative improvements ('+17.67% over baseline') without absolute scores ('57.2% EM'). MUST include BOTH relative AND absolute |
| **No paper_id: 0 in cross-topic** | Cross-topic `field_timeline.landmark_papers` | Any landmark paper with paper_id: 0 or placeholder ID — all paper_id values must be real database IDs |

### Tutorial Presenter Checks
| Check | Where to Look | What Fails |
|-------|--------------|------------|
| Clear narrative arc | Cross-topic analysis, HTML | No story from problem → approaches → frontiers |
| Presentation-ready takeaways | Topic summaries `key_insights` | Takeaways too verbose or vague for slides |
| Visual structure | HTML output | Poorly organized sections, missing visual aids |
| Balanced coverage | All topic summaries | One topic dominates, others under-covered |
| Paper links open new tab | HTML `<a>` tags | Any paper `<a>` link missing `target="_blank"` attribute |
| Year shown with method names | HTML method table | Method names in table without year, e.g., "CRAG" instead of "CRAG (2024)" |
| One-sentence definitions preserved | Topic summaries `overview.definition`; HTML topic overview boxes | Definition is missing, multi-sentence, or buried in longer text |
| Glossary at end of HTML | HTML glossary section | Glossary section missing or not placed near the end of the document (before footer) |
| No "Paper 123" naming | HTML method table, paper lists | Papers without system names shown as "Paper 123" instead of descriptive names. Method names in tables should be descriptive (e.g., 'Corrective Retrieval' not 'Gao et al.') |
| **Merged evolution timeline** | HTML timeline section | Separate "How the field evolved" AND "Field Evolution Timeline" sections (should be merged into one) |
| **"More" links for large boxes** | HTML expandable content | Large content boxes without "more" link to expand; JSON data excluded instead of collapsed |
| **Transitions between blocks preserved** | HTML category/component/theme blocks | Missing transitional text connecting different topic blocks |
| **ALL JSON content rendered in HTML** | HTML topic sections vs JSON summaries | Running examples, timelines, benchmark_results, key_insights, or limitations from JSON summaries not rendered in corresponding HTML topic sections. Every piece of JSON data should appear in the HTML (use collapsible sections for long content) |
| **Method names descriptive in HTML** | HTML methods tables | Method names in tables use author citations ('Gao et al.') instead of descriptive names ('Comprehensive RAG Taxonomy Survey'). NEVER use author-only method names |

---

## Example Commands

### Direct Mode
```
"Analyze the RAG area summary"

"Analyze the agents summary from beginner perspective"

"Check if the RAG summary meets a threshold of 8.0"
```

### Subagent Mode (Isolated Context) - RECOMMENDED
```
# Run beginner analysis only
Use the task tool:
  - subagent_name: "general-purpose"
  - prompt: "Load skill at area_summary/.llms/skills/analyze_area_summary.md
             Analyze area: rag
             Perspective: beginner
             Return JSON with beginner_score and criteria details."

# Run all 3 perspectives in parallel (3 separate sub-agent calls in same message)
```

---

## Perspective Parameter

| Value | Behavior |
|-------|----------|
| `beginner` | Run only beginner analysis, return beginner_score |
| `expert` | Run only expert analysis, return expert_score |
| `presenter` | Run only presenter analysis, return presenter_score |
| `all` (DEFAULT) | **Spin up 3 parallel sub-agents**, aggregate results |

**Default:** `perspective="all"` - always run all perspectives unless user specifies otherwise.

---

## When perspective="all" (Default)

**IMPORTANT:** Do NOT run sequentially. Instead, launch 3 parallel sub-agents:

```
# In the SAME message, make 3 parallel task tool calls:

task(
  subagent_name="general-purpose",
  title="Beginner Analysis: {area}",
  prompt="Load area_summary/.llms/skills/analyze_area_summary.md
          Analyze area: {area}
          Perspective: beginner
          Return JSON with beginner_score and criteria details."
)

task(
  subagent_name="general-purpose",
  title="Expert Analysis: {area}",
  prompt="Load area_summary/.llms/skills/analyze_area_summary.md
          Analyze area: {area}
          Perspective: expert
          Return JSON with expert_score and criteria details."
)

task(
  subagent_name="general-purpose",
  title="Presenter Analysis: {area}",
  prompt="Load area_summary/.llms/skills/analyze_area_summary.md
          Analyze area: {area}
          Perspective: presenter
          Return JSON with presenter_score and criteria details."
)
```

Then aggregate results in main context:
```python
combined_score = (beginner_score + expert_score + presenter_score) / 3
passed = combined_score >= threshold
```

---

## Input Sources

Analyze outputs in `area_summary/prompt_optimization/area_summaries/{area}/`:

| File Type | Pattern | Description |
|-----------|---------|-------------|
| Topic summaries | `subtopic_*_summary.json`, `category_*_summary.json`, `theme_*_summary.json` | Individual topic summaries |
| Cross-topic analysis | `cross_topic_analysis.json` | Synthesis across all topics |
| HTML report | `area_summary.html` (or `area_summary_v*.html`) | Final rendered output |

---

## Output

Save results to `prompt_optimization/analysis_critics/`:

```
# For perspective="all":
analysis_critics/analysis_{area}_beginner.json  (from beginner sub-agent)
analysis_critics/analysis_{area}_expert.json    (from expert sub-agent)
analysis_critics/analysis_{area}_presenter.json (from presenter sub-agent)
analysis_critics/analysis_{area}.json           (aggregated combined result)

# For single perspective:
analysis_critics/analysis_{area}_{perspective}.json
```

---

## Beginner Perspective (weight ~33%)

**Persona:** ML researcher who is NEW to this specific research area, reading the area summary to get oriented.

### Criteria and Weights

| Criterion | Weight | Description | Questions to Ask |
|-----------|--------|-------------|------------------|
| **accessibility** | 25% | Can someone new to the area understand the overview, methods, and insights? | Is the main area contribution explained in plain terms? Could a general ML researcher follow the key points? Are there unexplained assumptions about domain knowledge? |
| **jargon_handling** | 20% | Are technical terms explained or defined? | Are area-specific terms defined on first use? Are acronyms expanded? Is there excessive jargon that could be simplified? |
| **motivation_clarity** | 20% | Is it clear WHY each method/trend matters (real-world impact)? | Does each topic explain why this research direction is important? Would a reader understand the practical significance? |
| **logical_flow** | 15% | Does the summary tell a coherent story from overview → methods → insights? | Does the summary flow logically across topics? Are the connections between sections clear? Is there a clear narrative arc? |
| **completeness** | 20% | Are essential sections present and informative? | Are the major topics covered? Is there enough context to understand each approach? Are key papers referenced? |

### Beginner Analysis Prompt Template

~~~
You are an ML researcher who is NEW to this specific research area.
You are evaluating an area summary to see if it would help someone like you get oriented.

## Area
{area_name}

## Topic Summaries
```json
{topic_summaries}
```

## Cross-Topic Analysis
```json
{cross_topic_analysis}
```

## HTML Report (excerpt)
```html
{html_excerpt}
```

## Your Task
Analyze this area summary from a BEGINNER'S perspective. For each criterion below, provide:
1. A score from 1-10 (10 = excellent)
2. Specific issues found (with quotes/examples from the output)
3. Concrete suggestions for improvement

## Evaluation Criteria

{criteria_descriptions}

## Output Format
Respond with a JSON object:
```json
{
  "area": "{area_name}",
  "perspective": "beginner",
  "beginner_score": <weighted_score>,
  "criteria_scores": {
    "accessibility": {
      "score": <1-10>,
      "issues": ["issue1 with quote", "issue2"],
      "suggestions": ["suggestion1", "suggestion2"]
    },
    "jargon_handling": { ... },
    "motivation_clarity": { ... },
    "logical_flow": { ... },
    "completeness": { ... }
  },
  "top_issues": [
    "Most critical issue overall",
    "Second most critical issue",
    "Third most critical issue"
  ],
  "suggested_improvements": [
    "Most impactful improvement suggestion",
    "Second suggestion",
    "Third suggestion"
  ],
  "user_instruction_violations": [
    "Specific violation from user_instructions.md"
  ]
}
```

Focus on what would help a newcomer quickly understand this research area.
~~~

---

## Expert Perspective (weight ~33%)

**Persona:** Domain EXPERT in this research area, assessing whether the summary accurately captures the research landscape.

### Criteria and Weights

| Criterion | Weight | Description | Questions to Ask |
|-----------|--------|-------------|------------------|
| **technical_precision** | 25% | Are methods described accurately? Are paper contributions correctly attributed? | Are the technical details correct? Is the methodology described with sufficient precision? Are papers cited for specific claims? |
| **coverage** | 20% | Does it capture the major sub-areas and significant papers? | Are all important research directions represented? Are seminal/influential papers included? Is the coverage proportional to impact? |
| **novelty_assessment** | 20% | Is it clear what's genuinely new vs. incremental? | Does the summary differentiate breakthrough vs incremental work? Are true innovations highlighted appropriately? |
| **evidence_grounding** | 15% | Are claims backed by specific papers and metrics? | Are evaluation results cited? Do claims have paper references? Are benchmark comparisons accurate? |
| **actionability** | 20% | Are recommendations and opportunities well-justified? | Are research opportunities grounded in evidence? Would an expert find the recommendations actionable? Are gaps clearly identified? |

### Expert Analysis Prompt Template

~~~
You are a DOMAIN EXPERT in this research area.
You are evaluating an area summary to see if it accurately captures the research landscape.

## Area
{area_name}

## Topic Summaries
```json
{topic_summaries}
```

## Cross-Topic Analysis
```json
{cross_topic_analysis}
```

## Your Task
Analyze this area summary from an EXPERT'S perspective. For each criterion below, provide:
1. A score from 1-10 (10 = excellent)
2. Specific issues found (be technically precise)
3. Concrete suggestions for improvement

## Evaluation Criteria

{criteria_descriptions}

## Output Format
Respond with a JSON object:
```json
{
  "area": "{area_name}",
  "perspective": "expert",
  "expert_score": <weighted_score>,
  "criteria_scores": {
    "technical_precision": {
      "score": <1-10>,
      "issues": ["technical inaccuracy with quote", "missing attribution"],
      "suggestions": ["add citation for X", "correct description of Y"]
    },
    "coverage": { ... },
    "novelty_assessment": { ... },
    "evidence_grounding": { ... },
    "actionability": { ... }
  },
  "top_issues": [
    "Critical technical issue",
    "Second critical issue",
    "Third critical issue"
  ],
  "suggested_improvements": [
    "Most impactful improvement for experts",
    "Second suggestion",
    "Third suggestion"
  ],
  "missing_elements": [
    "Important paper/method not covered",
    "Missing research direction"
  ],
  "user_instruction_violations": [
    "Specific violation from user_instructions.md"
  ]
}
```

Focus on technical accuracy and completeness for domain experts.
~~~

---

## Tutorial Presenter Perspective (weight ~33%)

**Persona:** Someone preparing a tutorial or presentation from this area summary.

### Criteria and Weights

| Criterion | Weight | Description | Questions to Ask |
|-----------|--------|-------------|------------------|
| **narrative_arc** | 25% | Is there a clear story from problem landscape → approaches → frontiers? | Does the summary tell a compelling story? Is there a clear progression? Could you build a presentation outline from this? |
| **visual_structure** | 20% | Is the HTML well-organized with clear sections, tables, charts? | Are sections clearly delineated? Are there helpful visual elements? Is the hierarchy clear? |
| **key_takeaways** | 20% | Are takeaways crisp, memorable, and presentation-ready? | Are insights concise enough for slides? Are they memorable? Do they capture the essence? |
| **paper_links** | 15% | Are paper references correct and clickable? | Do paper links work? Are titles accurate? Are key papers easy to find? |
| **balance** | 20% | Are topics given proportional coverage (not dominated by one area)? | Is coverage balanced across topics? Are some areas over/under-represented? Does emphasis match importance? |

### Tutorial Presenter Analysis Prompt Template

~~~
You are preparing a TUTORIAL or PRESENTATION from this area summary.
You are evaluating whether this summary provides good material for creating a presentation.

## Area
{area_name}

## Topic Summaries
```json
{topic_summaries}
```

## Cross-Topic Analysis
```json
{cross_topic_analysis}
```

## HTML Report
```html
{html_content}
```

## Your Task
Analyze this area summary from a TUTORIAL PRESENTER'S perspective. For each criterion below, provide:
1. A score from 1-10 (10 = excellent)
2. Specific issues found
3. Concrete suggestions for improvement

## Evaluation Criteria

{criteria_descriptions}

## Output Format
Respond with a JSON object:
```json
{
  "area": "{area_name}",
  "perspective": "presenter",
  "presenter_score": <weighted_score>,
  "criteria_scores": {
    "narrative_arc": {
      "score": <1-10>,
      "issues": ["no clear story arc", "missing transition"],
      "suggestions": ["add overview section", "connect topics X and Y"]
    },
    "visual_structure": { ... },
    "key_takeaways": { ... },
    "paper_links": { ... },
    "balance": { ... }
  },
  "top_issues": [
    "Most critical presentation issue",
    "Second critical issue",
    "Third critical issue"
  ],
  "suggested_improvements": [
    "Most impactful improvement for presenters",
    "Second suggestion",
    "Third suggestion"
  ],
  "presentation_ready_elements": [
    "Element that would work well in a presentation",
    "Another presentation-ready element"
  ],
  "user_instruction_violations": [
    "Specific violation from user_instructions.md"
  ]
}
```

Focus on what would make this summary most useful for creating a tutorial or presentation.
~~~

---

## Scoring

### Calculate Overall Scores

**Beginner Overall Score:**
```
beginner_score = (
    accessibility * 0.25 +
    jargon_handling * 0.20 +
    motivation_clarity * 0.20 +
    logical_flow * 0.15 +
    completeness * 0.20
)
```

**Expert Overall Score:**
```
expert_score = (
    technical_precision * 0.25 +
    coverage * 0.20 +
    novelty_assessment * 0.20 +
    evidence_grounding * 0.15 +
    actionability * 0.20
)
```

**Presenter Overall Score:**
```
presenter_score = (
    narrative_arc * 0.25 +
    visual_structure * 0.20 +
    key_takeaways * 0.20 +
    paper_links * 0.15 +
    balance * 0.20
)
```

**Combined Score:**
```
combined_score = (beginner_score + expert_score + presenter_score) / 3
```

### Quality Thresholds

| Level | Score | Interpretation |
|-------|-------|----------------|
| Poor | < 5.0 | Major issues, needs significant revision |
| Fair | 5.0-6.5 | Notable issues, needs improvement |
| Good | 6.5-8.0 | Minor issues, acceptable with polish |
| Excellent | >= 8.0 | Publication/presentation quality |

---

## Workflow

### Step 1: Identify Area and Outputs
```
Check area_summary/prompt_optimization/area_summaries/{area}/ for:
- Topic summaries: subtopic_*_summary.json, category_*_summary.json, theme_*_summary.json
- Cross-topic analysis: cross_topic_analysis.json
- HTML report: area_summary.html or area_summary_v*.html
```

### Step 2: Determine Perspective
- `perspective="beginner"` → Go to Step 3 only
- `perspective="expert"` → Go to Step 4 only
- `perspective="presenter"` → Go to Step 5 only
- `perspective="all"` (DEFAULT) → Run Steps 3, 4, 5 in parallel

### Step 3: Beginner Analysis
Apply the beginner prompt template and evaluate each criterion.

### Step 4: Expert Analysis
Apply the expert prompt template and evaluate each criterion.

### Step 5: Presenter Analysis
Apply the presenter prompt template and evaluate each criterion.

### Step 6: Compile Results (if perspective="all")
Calculate weighted scores and aggregate:
```json
{
  "area": "{area_name}",
  "perspective": "all",
  "beginner_score": <score>,
  "expert_score": <score>,
  "presenter_score": <score>,
  "combined_score": (<beginner> + <expert> + <presenter>) / 3,
  "threshold": <threshold>,
  "passed": <combined_score >= threshold>,
  "beginner_analysis": { ... },
  "expert_analysis": { ... },
  "presenter_analysis": { ... }
}
```

### Step 7: Save Results to File

**IMPORTANT:** Always save analysis results to the output folder.

```python
import json

output_dir = "area_summary/prompt_optimization/analysis_critics"
base_name = f"analysis_{area}"

# Save based on perspective
if perspective == "beginner":
    output_file = f"{output_dir}/{base_name}_beginner.json"
elif perspective == "expert":
    output_file = f"{output_dir}/{base_name}_expert.json"
elif perspective == "presenter":
    output_file = f"{output_dir}/{base_name}_presenter.json"
elif perspective == "all":
    # Save individual perspectives
    write_json(f"{output_dir}/{base_name}_beginner.json", beginner_result)
    write_json(f"{output_dir}/{base_name}_expert.json", expert_result)
    write_json(f"{output_dir}/{base_name}_presenter.json", presenter_result)
    # Save combined result
    write_json(f"{output_dir}/{base_name}.json", combined_result)
```

---

## File Locations

| File | Path |
|------|------|
| Topic Summaries | `area_summary/prompt_optimization/area_summaries/{area}/*_summary.json` |
| Cross-Topic Analysis | `area_summary/prompt_optimization/area_summaries/{area}/cross_topic_analysis.json` |
| HTML Report | `area_summary/prompt_optimization/area_summaries/{area}/area_summary*.html` |
| Analysis Results (output) | `area_summary/prompt_optimization/analysis_critics/` |
| User Instructions | `area_summary/.llms/skills/user_instructions.md` |

---

## Prerequisites

**For analyzing an area:**
1. Outputs must exist in `prompt_optimization/area_summaries/{area}/`
2. At minimum: at least one topic summary JSON and `cross_topic_analysis.json`
3. For presenter analysis: HTML report should also exist

**If outputs are missing:**
Run the `summarize_area.md` skill first to generate outputs.
