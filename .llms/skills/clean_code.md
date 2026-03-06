---
name: clean_code
description: Clean up code by removing unused/duplicated methods, updating README files, running tests, and linting. Use after making significant code changes to ensure code quality.
user-invocable: true
argument-hint: "[folder_path] - Optional path to a specific folder to clean (e.g., paper_collection/paper_summary). If not provided, cleans the entire project."
oncalls:
  - lunadong
tools:
  - search_files
  - read_file
  - str_replace_edit
  - execute_command
  - task
  - get_local_changes
  - validate_changes
  - review_code
---

# Clean Code Skill

This skill performs a comprehensive code cleanup workflow after significant changes have been made to the codebase.

## Input Parameter

**folder_path** (optional): Path to a specific folder to clean up.
- If provided, only files within this folder will be analyzed and cleaned
- If not provided, the entire project will be cleaned
- Examples:
  - `/clean_code paper_collection/paper_summary` - Clean only the paper_summary folder
  - `/clean_code web_interface` - Clean only the web_interface folder
  - `/clean_code` - Clean the entire project

## Workflow Steps

Execute the following steps in order:

### Step 1: Code Review (Catch Bugs First)

Before cleaning up code structure, first catch any bugs or logic errors:

1. **Run code review** using the `review_code` tool:
   ```
   review_code(mode="quick", review_scope=["uncommitted changes"])
   ```

2. **Review findings and FIX issues**:
   - For any **errors** reported: FIX them immediately using `str_replace_edit`
   - For any **warnings**: Evaluate and fix if appropriate
   - For **informational** items: Note but don't necessarily fix

3. **Re-run validation** after fixing any review issues:
   ```
   validate_changes
   ```

4. **Track issues fixed**: Note the count and types of issues found and fixed for the final summary.

**CRITICAL**: Do NOT proceed to Step 2 until ALL bugs and errors from the code review are FIXED and validated. The purpose of this step is to catch and fix bugs BEFORE cleaning up code structure.

### Step 2: Identify and FIX Unused/Duplicated Code

**CRITICAL**: You MUST fix all issues found, not just report them. Analyze the ENTIRE target folder, not just recent changes.

1. **Parse the folder_path argument** (if provided):
   - If user provided a path like `/clean_code paper_collection/paper_summary`, use that folder
   - If no path provided, use the entire project root

2. **Use code_search subagent to analyze the entire folder**:
   ```
   Use the task tool with subagent_name=code_search to comprehensively analyze the target folder:

   Prompt: "Analyze ALL Python files in {folder_path or project root} for:
   1. Unused imports - imports that are never referenced in the file
   2. Unused functions/methods - functions defined but never called anywhere in the codebase
   3. Duplicated code patterns - similar function implementations that could be consolidated
   4. Dead code - code that cannot be reached or executed
   5. Export bugs - symbols in __all__ that are not actually defined/imported

   Search the ENTIRE folder recursively, not just recent changes.
   For each potential issue, verify by searching for usages across the codebase."
   ```

3. **For each issue found, IMMEDIATELY FIX IT**:
   - **Unused imports**: Remove them using `str_replace_edit`
   - **Unused functions/methods**: Delete them using `str_replace_edit`
   - **Duplicated code**: Consolidate into a single shared function, update all callers
   - **Export bugs**: Fix `__all__` to only include symbols that actually exist
   - **Dead code**: Remove unreachable code blocks

4. **Fixing approach** (DO NOT just report - FIX each issue):
   ```
   For each issue found:
   1. Read the file containing the issue
   2. Use str_replace_edit to remove/fix the problematic code
   3. If removing a function, search for any callers and update them
   4. If consolidating duplicates, create a shared utility and update imports
   5. Verify the fix doesn't break anything by checking for syntax errors
   ```

5. **After fixing, verify**:
   - Run `validate_changes` to ensure no new errors were introduced
   - If validation fails, fix the errors immediately before proceeding

### Step 3 & 4: Parallel Execution (README Update + Tests)

Launch these two tasks **in parallel** using the `task` tool:

#### Task A: Update README Files (use general-purpose subagent)

```
Prompt for subagent:
"Review the recent code changes and update any related README files to reflect the changes.

Target folder: {folder_path or 'entire project'}

Steps:
1. Use get_local_changes to see what files were modified
2. For each modified directory within the target folder, check if there's a README.md
3. Read the README and determine if it needs updates based on:
   - New features added
   - Removed functionality
   - Changed APIs or interfaces
   - Updated usage instructions
4. Make necessary updates to keep documentation in sync with code

Focus on README files within the target folder:
- {folder_path}/README.md (if exists)
- Subdirectory README.md files
- Root README.md (if changes affect project-level documentation)

Do NOT create new README files - only update existing ones."
```

#### Task B: Run Tests and FIX Failures (use general-purpose subagent)

```
Prompt for subagent:
"Run the project tests. If any tests FAIL, you MUST FIX them before completing.

Target folder: {folder_path or 'entire project'}

Steps:
1. Check for test configuration files (pytest.ini, setup.cfg, pyproject.toml)
2. Run tests relevant to the target folder:
   - If folder specified: python3 -m pytest tests/ -v -k '{folder_name}' or test files matching the folder
   - If entire project: python3 -m pytest tests/ -v
3. If tests FAIL:
   a. Analyze the failure message and traceback
   b. FIX the issue in the source code or test file using str_replace_edit
   c. Re-run the tests to verify the fix works
   d. Repeat until ALL tests pass
4. Only report success when ALL tests pass

CRITICAL: Do NOT just report failures - you MUST fix them and verify with another test run.

Working directory: (project root)"
```

### Step 5: Run Lint and FIX All Issues (Especially BLACK Formatting)

After parallel tasks complete, run linting and FIX all issues:

**[!] CRITICAL - BLACK FORMATTING ERRORS [!]**

BLACK formatting errors are a common source of persistent lint issues. Here's why they often remain unfixed:

1. **`format_document` tool (VSCode formatter) does NOT reliably fix BLACK errors** - VSCode's formatter may use different settings or rules than what `arc lint` expects. Common issues include:
   - Slice notation spacing: BLACK requires `block[match.end() :]` not `block[match.end():]`
   - Function call wrapping rules differ between VSCode and BLACK
   - Line length handling may differ

2. **Running `arc lint` from the wrong directory** - BLACK errors won't be detected or fixed properly if you run from the project directory instead of fbsource root.

3. **`arc lint -a` may need multiple runs** - Sometimes the auto-fix only partially applies. You MUST re-run until no BLACK errors remain.

**SOLUTION: Always use `arc lint -a` from fbsource root, NOT `format_document`:**

1. **Determine the fbsource-relative path**:
   ```
   # If project is at /Users/lunadong/fbsource/fbcode/assistant/research/paper-agent
   # The fbsource root is /Users/lunadong/fbsource
   # The relative path for arc lint is: fbcode/assistant/research/paper-agent/{folder_path or '.'}
   ```

2. **Run the linter with auto-fix FROM FBSOURCE ROOT**:
   ```bash
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/{folder_path or '.'}
   ```

   Example commands:
   ```bash
   # Clean entire project
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/

   # Clean specific folder
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/paper_collection/

   # Clean specific files
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/paper_collection/paper_db.py
   ```

3. **[!] RE-RUN `arc lint -a` UNTIL NO BLACK ERRORS REMAIN**:
   ```bash
   # First run - may only partially fix BLACK errors
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/path/to/file.py

   # Second run - check if BLACK errors are gone
   cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/path/to/file.py

   # Repeat until output shows NO BLACK errors (only AUTODEPS advice is acceptable)
   ```

4. **For any issues NOT auto-fixed after multiple runs, FIX them manually**:
   - Read the lint error message carefully - it shows the exact diff needed
   - Use `str_replace_edit` to apply the suggested change
   - Common BLACK fixes:
     - Add space before `:` in slices: `text[start :]` not `text[start:]`
     - Function arguments on single line vs multi-line
     - Line length adjustments

5. **Final validation**:
   - Use `validate_changes` to check for any remaining errors
   - If validation still shows BLACK errors, run `arc lint -a` again from fbsource root
   - Re-run `validate_changes` until no errors from your changes remain

**[X] DO NOT use `format_document` for BLACK errors - it will NOT fix them reliably!**

## Example Usage

When invoked, execute this workflow:

```python
# Step 1: Code review (catch bugs first)
review_code(mode="quick", review_scope=["uncommitted changes"])
# - Fix any errors found
# - Re-validate after fixes

# Step 2: Analyze and FIX unused code
# - Search entire folder for unused functions, imports, duplicates
# - FIX each issue immediately using str_replace_edit
# - Run validate_changes to verify fixes

# Step 3 & 4: Launch in parallel
task(
    config={"subagent_name": "general-purpose"},
    title="Update README files",
    prompt="Review changes and update README files..."
)
task(
    config={"subagent_name": "general-purpose"},
    title="Run tests and FIX failures",
    prompt="Run tests. If any fail, FIX them and re-run until all pass..."
)

# Step 5: After parallel tasks complete
# [!] CRITICAL: Run arc lint from fbsource root, not from project directory!
# This is required for Black formatting to be properly detected.
# [!] DO NOT use format_document - it will NOT fix BLACK errors reliably!

# First run - may only partially fix BLACK errors
execute_command(
    command="cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/",
    summary="Run arc lint from fbsource root for proper Black detection"
)

# [!] CRITICAL: Re-run until NO BLACK errors remain!
# arc lint -a may need multiple runs to fix all BLACK formatting issues
execute_command(
    command="cd /Users/lunadong/fbsource && arc lint -a fbcode/assistant/research/paper-agent/",
    summary="Re-run arc lint to ensure all BLACK errors are fixed"
)

# - If BLACK errors persist after 2 runs, manually fix using str_replace_edit
# - Common BLACK fixes: add space before : in slices (e.g., text[start :] not text[start:])
# - Run validate_changes to confirm no errors
```

## Output

After completion, provide a summary showing:
1. **Code review**: Issues found and fixed (errors/warnings/info counts)
2. **Code cleaned**: List of removed unused/duplicated code (with file paths)
3. **README updates**: Files updated (if any)
4. **Tests**: Confirm ALL tests pass (include pass count)
5. **Lint**: Confirm lint is clean (or list any unfixable warnings)
6. **Validation**: Confirm `validate_changes` shows no new errors

**IMPORTANT**: The output should confirm everything is FIXED and VALIDATED, not just reported.

## Environment Check (from environment_details)

Before starting, examine the environment_details and report:

1. **Files Changed Externally** - List any files in dirty state that have been modified externally:
   ```
   Check: "Files Changed Externally (In dirty state)" section
   These files need to be re-read to get the latest version before making changes
   ```

2. **Current Working Stack** - Show commits ahead of master:
   ```
   Check: "Current Working Stack" section
   Report how many commits ahead of master and the most recent commit message
   ```

3. **VSCode Open Tabs** - Files currently being worked on:
   ```
   Check: "VSCode Open Tabs" section
   These are likely the files that need attention during cleanup
   ```

4. **VSCode Visible Files** - Currently focused file:
   ```
   Check: "VSCode Visible Files" section
   Start cleanup analysis from this file if within target folder
   ```

5. **Search Context** - Project structure overview:
   ```
   Check: "Search Context" section
   Use this to understand available test directories, config files (pytest.ini, ruff.toml), and README locations
   ```

### Example Environment Report

```
[INFO] ENVIRONMENT CHECK
====================

[DIR] Target Folder: paper_collection/paper_summary

[!]  Files Changed Externally (need re-read):
   - paper_collection/paper_summary/compare_models.py

[STACK] Working Stack:
   - 1 commit ahead of master
   - Most recent: "prompt engineering for better paper summarization"

[TABS] Open Tabs (potential cleanup targets):
   - summary_generation.py
   - prompt.txt
   - summary_example.json
   - paper_detail.html

[CFG] Config Files Found:
   - pytest.ini (for running tests)
   - ruff.toml (for linting)
   - requirements.txt

[README] README Files to Check:
   - README.md (root)
   - paper_collection/paper_summary/ (check if exists)
```

This environment check helps identify:
- Which files may have stale content and need re-reading
- What changes are pending commit
- Which files the user is actively working on
- What testing/linting tools are configured
