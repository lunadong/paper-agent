#!/usr/bin/env python3
"""
Prompt Manager Module

Provides prompt template loading and management for paper summarization.
Extracted from summary_generation.py for modularity.
"""

from pathlib import Path
from typing import Optional

# Map topic tags to background file names
TOPIC_BACKGROUND_FILES = {
    "RAG": "background_rag.txt",
    "Factuality": "background_factuality.txt",
    "Agent": "background_agent.txt",
    "Memory": "background_memory.txt",
    "P13N": "background_p13n.txt",
    "Benchmark": "background_benchmark.txt",
}

# Allowed topics for Stage 1 classification
ALLOWED_TOPICS = {
    "RAG",
    "Agent",
    "Memory",
    "P13N",
    "Factuality",
    "Benchmark",
    "Reasoning",
    "RL",
    "Pretraining",
    "KG",
    "QA",
    "Recommendation",
    "MM",
    "Speech",
    "ResponsiveAI",
}


def load_topic_prompt(prompt_file: Optional[str] = None) -> str:
    """
    Load the topic classification prompt from file.

    Args:
        prompt_file: Path to prompt file. Defaults to prompts/prompt_topic.txt.

    Returns:
        Topic classification prompt string.
    """
    actual_path: Path
    if prompt_file is None:
        script_dir = Path(__file__).parent
        actual_path = script_dir / "prompts" / "prompt_topic.txt"
    else:
        actual_path = Path(prompt_file)

    with open(actual_path, "r") as f:
        return f.read()


def load_prompt_template(
    prompt_file: Optional[str] = None,
    topics: Optional[list] = None,
    primary_topic: Optional[str] = None,
) -> str:
    """
    Load the prompt template from file and populate placeholders.

    Replaces:
        - <json_template> with contents of summary_template.json
        - <json_example> with contents of summary_example.json
        - <topic_background> with contents of background files for matching topics
          (or removes the "Area Background" section if no topics match)

    Supported topics with background files:
        RAG, Factuality, Agent, Memory, P13N, Benchmark

    Args:
        prompt_file: Path to prompt file. Defaults to prompts/prompt.txt.
        topics: List of topic tags for the paper (e.g., ["RAG", "Agent"]).
                If None or empty, Area Background section is removed.
        primary_topic: The primary topic for this paper. If provided,
            its background is loaded first with emphasis.

    Returns:
        Prompt template string with placeholders replaced.
    """
    actual_path: Path
    if prompt_file is None:
        script_dir = Path(__file__).parent
        prompts_dir = script_dir / "prompts"
        actual_path = prompts_dir / "prompt.txt"
    else:
        actual_path = Path(prompt_file)
        prompts_dir = actual_path.parent

    with open(actual_path, "r") as f:
        prompt = f.read()

    # Load and replace <json_template>
    template_file = prompts_dir / "summary_template.json"
    if template_file.exists():
        with open(template_file, "r") as f:
            json_template = f.read()
        prompt = prompt.replace("<json_template>", json_template)

    # Load and replace <json_example>
    example_file = prompts_dir / "summary_example.json"
    if example_file.exists():
        with open(example_file, "r") as f:
            json_example = f.read()
        prompt = prompt.replace("<json_example>", json_example)

    # Load backgrounds for matching topics
    backgrounds = []

    # First, load primary topic background with emphasis
    if primary_topic and primary_topic.strip() in TOPIC_BACKGROUND_FILES:
        primary_clean = primary_topic.strip()
        bg_file = prompts_dir / TOPIC_BACKGROUND_FILES[primary_clean]
        if bg_file.exists():
            with open(bg_file, "r") as f:
                bg_content = f.read().strip()
            if bg_content:
                backgrounds.append(
                    f"=== PRIMARY TOPIC: {primary_clean} ===\n"
                    f"(This is the main focus area for this paper. "
                    f"Focus sub_topic and primary_focus on this area.)"
                    f"\n\n{bg_content}"
                )

    # Then load other topic backgrounds as supplementary
    if topics:
        for topic in topics:
            topic_clean = topic.strip()
            # Skip if already added as primary
            if primary_topic and topic_clean == primary_topic.strip():
                continue
            if topic_clean in TOPIC_BACKGROUND_FILES:
                bg_file = prompts_dir / TOPIC_BACKGROUND_FILES[topic_clean]
                if bg_file.exists():
                    with open(bg_file, "r") as f:
                        bg_content = f.read().strip()
                    if bg_content:
                        backgrounds.append(
                            f"=== Supplementary: {topic_clean} ===\n{bg_content}"
                        )

    if backgrounds:
        # Combine all backgrounds with separators
        combined_background = "\n\n".join(backgrounds)
        prompt = prompt.replace("<topic_background>", combined_background)
    else:
        # Remove the entire "Area Background" section if no backgrounds
        prompt = prompt.replace(
            "\n========================\nArea Background"
            "\n========================\n\n<topic_background>",
            "",
        )

    return prompt


def get_prompts_dir() -> Path:
    """Get the prompts directory path."""
    return Path(__file__).parent / "prompts"
