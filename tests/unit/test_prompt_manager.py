"""
Unit tests for prompt manager module.

Tests the prompt manager at paper_collection/paper_summary/prompt_manager.py
"""

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest


class TestLoadTopicPrompt:
    """Tests for load_topic_prompt function."""

    def test_load_topic_prompt(self, tmp_path: Path) -> None:
        """Test loading prompt_topic.txt successfully."""
        # Setup: Create a mock prompt file
        prompt_content = "Classify this paper into topics: {topics}"
        prompt_file = tmp_path / "prompt_topic.txt"
        prompt_file.write_text(prompt_content)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_topic_prompt

        result = load_topic_prompt(str(prompt_file))

        # Assert
        assert result == prompt_content

    def test_load_topic_prompt_default_path(self) -> None:
        """Test that default path points to prompts/prompt_topic.txt."""
        # Setup: Mock the open call and file read
        mock_content = "Default topic prompt content"

        with patch("builtins.open", mock_open(read_data=mock_content)):
            with patch("pathlib.Path.exists", return_value=True):
                # Execute
                from paper_collection.paper_summary.prompt_manager import (
                    load_topic_prompt,
                )

                result = load_topic_prompt(prompt_file=None)

                # Assert: Should return the mocked content
                assert result == mock_content

    def test_load_topic_prompt_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for missing file."""
        # Execute & Assert
        from paper_collection.paper_summary.prompt_manager import load_topic_prompt

        with pytest.raises(FileNotFoundError):
            load_topic_prompt("/nonexistent/path/prompt.txt")


class TestLoadPromptTemplate:
    """Tests for load_prompt_template function."""

    def test_load_prompt_template_no_topics(self, tmp_path: Path) -> None:
        """Test removing topic section if topics list is empty."""
        # Setup: Create prompt file with topic background section
        prompt_content = """This is the prompt.

========================
Area Background
========================

<topic_background>

Now analyze the paper."""
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text(prompt_content)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_prompt_template

        result = load_prompt_template(str(prompt_file), topics=None, primary_topic=None)

        # Assert: Area Background section should be removed
        assert "Area Background" not in result
        assert "<topic_background>" not in result
        assert "This is the prompt." in result
        assert "Now analyze the paper." in result

    def test_load_prompt_template_single_topic(self, tmp_path: Path) -> None:
        """Test primary topic with emphasis."""
        # Setup: Create prompt and background files
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        prompt_content = """Analyze paper.
<topic_background>
End."""
        (prompts_dir / "prompt.txt").write_text(prompt_content)

        rag_background = "RAG is a technique for retrieval-augmented generation."
        (prompts_dir / "background_rag.txt").write_text(rag_background)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_prompt_template

        result = load_prompt_template(
            str(prompts_dir / "prompt.txt"),
            topics=["RAG"],
            primary_topic="RAG",
        )

        # Assert: Should have PRIMARY TOPIC emphasis
        assert "PRIMARY TOPIC: RAG" in result
        assert "RAG is a technique" in result
        assert "main focus area" in result

    def test_load_prompt_template_multiple_topics(self, tmp_path: Path) -> None:
        """Test primary topic plus supplementary topics."""
        # Setup: Create prompt and background files
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        prompt_content = """Analyze paper.
<topic_background>
End."""
        (prompts_dir / "prompt.txt").write_text(prompt_content)

        rag_background = "RAG information"
        agent_background = "Agent information"
        (prompts_dir / "background_rag.txt").write_text(rag_background)
        (prompts_dir / "background_agent.txt").write_text(agent_background)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_prompt_template

        result = load_prompt_template(
            str(prompts_dir / "prompt.txt"),
            topics=["RAG", "Agent"],
            primary_topic="RAG",
        )

        # Assert: Should have primary and supplementary topics
        assert "PRIMARY TOPIC: RAG" in result
        assert "Supplementary: Agent" in result
        assert "RAG information" in result
        assert "Agent information" in result

    def test_load_prompt_template_replaces_json_template(self, tmp_path: Path) -> None:
        """Test that <json_template> placeholder is replaced."""
        # Setup
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        prompt_content = "Template: <json_template>"
        (prompts_dir / "prompt.txt").write_text(prompt_content)

        json_template = '{"field": "value"}'
        (prompts_dir / "summary_template.json").write_text(json_template)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_prompt_template

        result = load_prompt_template(str(prompts_dir / "prompt.txt"))

        # Assert
        assert '{"field": "value"}' in result
        assert "<json_template>" not in result

    def test_load_prompt_template_replaces_json_example(self, tmp_path: Path) -> None:
        """Test that <json_example> placeholder is replaced."""
        # Setup
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        prompt_content = "Example: <json_example>"
        (prompts_dir / "prompt.txt").write_text(prompt_content)

        json_example = '{"example": "data"}'
        (prompts_dir / "summary_example.json").write_text(json_example)

        # Execute
        from paper_collection.paper_summary.prompt_manager import load_prompt_template

        result = load_prompt_template(str(prompts_dir / "prompt.txt"))

        # Assert
        assert '{"example": "data"}' in result
        assert "<json_example>" not in result


class TestAllowedTopics:
    """Tests for ALLOWED_TOPICS constant."""

    def test_allowed_topics_defined(self) -> None:
        """Test that ALLOWED_TOPICS has expected topics."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import ALLOWED_TOPICS

        # Assert: Should have expected topic types
        expected_topics = {
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
        }

        assert ALLOWED_TOPICS == expected_topics

    def test_allowed_topics_is_set(self) -> None:
        """Test that ALLOWED_TOPICS is a set for efficient lookup."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import ALLOWED_TOPICS

        # Assert
        assert isinstance(ALLOWED_TOPICS, set)

    def test_allowed_topics_contains_core_categories(self) -> None:
        """Test that core research categories are in ALLOWED_TOPICS."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import ALLOWED_TOPICS

        # Assert: Core categories should be present
        core_categories = ["RAG", "Agent", "Memory", "Benchmark"]
        for category in core_categories:
            assert category in ALLOWED_TOPICS


class TestTopicBackgroundFiles:
    """Tests for TOPIC_BACKGROUND_FILES mapping."""

    def test_topic_background_files(self) -> None:
        """Test that TOPIC_BACKGROUND_FILES maps topics to files."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import TOPIC_BACKGROUND_FILES

        # Assert: Expected mappings
        expected_mappings = {
            "RAG": "background_rag.txt",
            "Factuality": "background_factuality.txt",
            "Agent": "background_agent.txt",
            "Memory": "background_memory.txt",
            "P13N": "background_p13n.txt",
            "Benchmark": "background_benchmark.txt",
        }

        assert TOPIC_BACKGROUND_FILES == expected_mappings

    def test_topic_background_files_is_dict(self) -> None:
        """Test that TOPIC_BACKGROUND_FILES is a dictionary."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import TOPIC_BACKGROUND_FILES

        # Assert
        assert isinstance(TOPIC_BACKGROUND_FILES, dict)

    def test_topic_background_files_values_are_txt(self) -> None:
        """Test that all background file names end with .txt."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import TOPIC_BACKGROUND_FILES

        # Assert: All values should be .txt files
        for topic, filename in TOPIC_BACKGROUND_FILES.items():
            assert filename.endswith(".txt"), f"File for {topic} should be .txt"
            assert filename.startswith("background_"), (
                f"File for {topic} should start with background_"
            )


class TestGetPromptsDir:
    """Tests for get_prompts_dir function."""

    def test_get_prompts_dir_returns_path(self) -> None:
        """Test that get_prompts_dir returns a Path object."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import get_prompts_dir

        result = get_prompts_dir()

        # Assert
        assert isinstance(result, Path)
        assert result.name == "prompts"

    def test_get_prompts_dir_relative_to_module(self) -> None:
        """Test that prompts dir is relative to the module location."""
        # Execute
        from paper_collection.paper_summary.prompt_manager import get_prompts_dir

        result = get_prompts_dir()

        # Assert: Should be under paper_summary directory
        assert "paper_summary" in str(result)
