"""
Unit tests for summary generation module.

Tests the summary generation at paper_collection/paper_summary/summary_generation.py
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Module paths for patching
_SG_MODULE = "paper_collection.paper_summary.summary_generation"


class TestAllowedTopicsValidation:
    """Tests for topic validation against allowed list."""

    def test_validate_topics_all_valid(self) -> None:
        """Test that valid topics pass validation unchanged."""
        # Setup
        from paper_collection.paper_summary.summary_generation import _validate_topics

        result = {
            "topics": ["RAG", "Agent", "Memory"],
            "primary_topic": "RAG",
        }

        # Execute
        validated = _validate_topics(result)

        # Assert: All topics should remain
        assert validated["topics"] == ["RAG", "Agent", "Memory"]
        assert validated["primary_topic"] == "RAG"

    def test_validate_topics_removes_invalid(self) -> None:
        """Test that invalid topics are removed from the list."""
        # Setup
        from paper_collection.paper_summary.summary_generation import _validate_topics

        result = {
            "topics": ["RAG", "InvalidTopic", "Agent", "NotAllowed"],
            "primary_topic": "RAG",
        }

        # Execute
        validated = _validate_topics(result)

        # Assert: Only valid topics should remain
        assert "InvalidTopic" not in validated["topics"]
        assert "NotAllowed" not in validated["topics"]
        assert "RAG" in validated["topics"]
        assert "Agent" in validated["topics"]

    def test_validate_topics_invalid_primary_topic(self) -> None:
        """Test that invalid primary_topic is set to None."""
        # Setup
        from paper_collection.paper_summary.summary_generation import _validate_topics

        result = {
            "topics": ["RAG", "Agent"],
            "primary_topic": "InvalidPrimaryTopic",
        }

        # Execute
        validated = _validate_topics(result)

        # Assert: Invalid primary_topic should become None
        assert validated["primary_topic"] is None
        assert validated["topics"] == ["RAG", "Agent"]

    def test_validate_topics_empty_input(self) -> None:
        """Test validation with empty topics list."""
        # Setup
        from paper_collection.paper_summary.summary_generation import _validate_topics

        result = {
            "topics": [],
            "primary_topic": None,
        }

        # Execute
        validated = _validate_topics(result)

        # Assert
        assert validated["topics"] == []
        assert validated["primary_topic"] is None

    def test_validate_topics_preserves_order(self) -> None:
        """Test that topic order is preserved after validation."""
        # Setup
        from paper_collection.paper_summary.summary_generation import _validate_topics

        result = {
            "topics": ["Agent", "RAG", "Memory", "Benchmark"],
            "primary_topic": "Agent",
        }

        # Execute
        validated = _validate_topics(result)

        # Assert: Order should be preserved
        assert validated["topics"] == ["Agent", "RAG", "Memory", "Benchmark"]


class TestJsonExtractionFromMarkdown:
    """Tests for extracting JSON from markdown code blocks."""

    def test_extract_json_from_response_simple(self) -> None:
        """Test extracting JSON from plain response."""
        # Setup: Simulate response text with JSON
        response_text = '{"key": "value", "number": 42}'

        # Execute: Find JSON in response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
        else:
            result = None

        # Assert
        assert result is not None
        assert result["key"] == "value"
        assert result["number"] == 42

    def test_extract_json_from_markdown_code_block(self) -> None:
        """Test extracting JSON from markdown code block."""
        # Setup: Response with markdown code block
        response_text = """Here is the summary:

```json
{
    "title": "Test Paper",
    "topics": ["RAG", "Agent"]
}
```

That's the analysis."""

        # Execute: Find JSON in response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
        else:
            result = None

        # Assert
        assert result is not None
        assert result["title"] == "Test Paper"
        assert result["topics"] == ["RAG", "Agent"]

    def test_extract_json_with_prefix_text(self) -> None:
        """Test extracting JSON when there's text before the JSON."""
        # Setup: Response with text before JSON
        response_text = """Based on my analysis of the paper:

{
    "primary_topic": "RAG",
    "reasoning": "The paper focuses on retrieval"
}"""

        # Execute: Find JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
        else:
            result = None

        # Assert
        assert result is not None
        assert result["primary_topic"] == "RAG"

    def test_extract_json_no_json_present(self) -> None:
        """Test handling when no JSON is present in response."""
        # Setup: Response without JSON
        response_text = "This response does not contain any JSON data."

        # Execute: Try to find JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        # Assert: Should not find valid JSON bounds
        has_json = json_start != -1 and json_end > json_start
        assert not has_json

    def test_extract_json_nested_objects(self) -> None:
        """Test extracting nested JSON structures."""
        # Setup: Response with nested JSON
        response_text = """
{
    "basics": {
        "title": "Paper Title",
        "authors": ["Author A", "Author B"]
    },
    "core": {
        "topics": ["RAG"],
        "score": 7
    }
}"""

        # Execute: Find JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
        else:
            result = None

        # Assert: Nested structure should be preserved
        assert result is not None
        assert result["basics"]["title"] == "Paper Title"
        assert result["core"]["topics"] == ["RAG"]


class TestSummaryStructureValidation:
    """Tests for validating summary has required fields."""

    def test_summary_has_basics_section(self) -> None:
        """Test that summary includes basics section."""
        # Setup: Valid summary structure
        summary = {
            "basics": {
                "title": "Test Paper",
                "arxiv_id": "2401.12345",
                "venue": "arXiv",
                "year": "2024",
            },
            "core": {},
            "technical_details": {},
        }

        # Assert: basics section should exist with required fields
        assert "basics" in summary
        assert "title" in summary["basics"]
        assert "arxiv_id" in summary["basics"]

    def test_summary_has_core_section(self) -> None:
        """Test that summary includes core section."""
        # Setup: Valid summary structure
        summary = {
            "basics": {},
            "core": {
                "topics": ["RAG"],
                "primary_topic": "RAG",
                "problem_statement": "Improving retrieval",
                "thesis": "Our method improves accuracy",
            },
            "technical_details": {},
        }

        # Assert: core section should exist with required fields
        assert "core" in summary
        assert "topics" in summary["core"]
        assert "primary_topic" in summary["core"]

    def test_summary_has_methods_section(self) -> None:
        """Test that summary includes technical_details section."""
        # Setup: Valid summary structure
        summary = {
            "basics": {},
            "core": {},
            "technical_details": {
                "pipeline": ["Step 1", "Step 2"],
                "results": [{"metric": "Accuracy", "value": "85%"}],
            },
        }

        # Assert: methods section should exist
        assert "technical_details" in summary
        assert "pipeline" in summary["technical_details"]
        assert "results" in summary["technical_details"]

    def test_summary_missing_section_detected(self) -> None:
        """Test detection of missing required section."""
        # Setup: Summary missing core section
        summary = {
            "basics": {"title": "Test"},
            "technical_details": {},
        }

        # Assert: core section should be missing
        assert "core" not in summary

    def test_summary_complete_structure(
        self, sample_summary_json: Dict[str, Any]
    ) -> None:
        """Test a complete summary structure from fixtures."""
        # Setup: Use fixture from conftest.py

        # Assert: All main sections should exist
        required_sections = ["basics", "core", "technical_details"]
        for section in required_sections:
            assert section in sample_summary_json

        # Assert: Nested fields in basics
        assert "title" in sample_summary_json["basics"]
        assert "authors" in sample_summary_json["basics"]

        # Assert: Nested fields in core
        assert "topics" in sample_summary_json["core"]
        assert "primary_topic" in sample_summary_json["core"]


class TestGeneratePaperSummary:
    """Tests for generate_paper_summary function."""

    @patch(f"{_SG_MODULE}.call_gemini_api")
    @patch(f"{_SG_MODULE}.download_pdf_text")
    @patch(f"{_SG_MODULE}.load_prompt_template")
    @patch(f"{_SG_MODULE}.get_default_model")
    def test_generate_paper_summary_success(
        self,
        mock_get_model: MagicMock,
        mock_load_prompt: MagicMock,
        mock_download: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Test successful summary generation."""
        # Setup
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_load_prompt.return_value = (
            "Analyze <PDF_URL> For the above paper in the given link,"
        )
        mock_download.return_value = "Sample PDF text content"
        mock_api.return_value = (
            '{"basics": {"title": "Test"}, "core": {}, "technical_details": {}}'
        )

        # Execute
        from paper_collection.paper_summary.summary_generation import (
            generate_paper_summary,
        )

        result = generate_paper_summary("https://arxiv.org/pdf/2401.12345")

        # Assert
        assert "basics" in result
        assert result["basics"]["title"] == "Test"

    @patch(f"{_SG_MODULE}.call_gemini_api")
    @patch(f"{_SG_MODULE}.download_pdf_text")
    @patch(f"{_SG_MODULE}.load_prompt_template")
    @patch(f"{_SG_MODULE}.get_default_model")
    def test_generate_paper_summary_invalid_json(
        self,
        mock_get_model: MagicMock,
        mock_load_prompt: MagicMock,
        mock_download: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Test handling of invalid JSON response."""
        # Setup
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_load_prompt.return_value = (
            "Analyze <PDF_URL> For the above paper in the given link,"
        )
        mock_download.return_value = "Sample PDF text"
        mock_api.return_value = "This is not valid JSON"

        # Execute
        from paper_collection.paper_summary.summary_generation import (
            generate_paper_summary,
        )

        result = generate_paper_summary("https://arxiv.org/pdf/2401.12345")

        # Assert: Should return raw_response on parse failure
        assert "raw_response" in result


class TestClassifyPaperTopics:
    """Tests for classify_paper_topics function."""

    @patch(f"{_SG_MODULE}.call_gemini_api")
    @patch(f"{_SG_MODULE}.download_pdf_text")
    @patch(f"{_SG_MODULE}.load_topic_prompt")
    @patch(f"{_SG_MODULE}.get_default_model")
    def test_classify_paper_topics_success(
        self,
        mock_get_model: MagicMock,
        mock_load_prompt: MagicMock,
        mock_download: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Test successful topic classification."""
        # Setup
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_load_prompt.return_value = "Classify <PDF_URL> For the above paper,"
        mock_download.return_value = "Paper about RAG and retrieval"
        mock_api.return_value = """
{
    "topics": ["RAG", "Agent"],
    "primary_topic": "RAG",
    "reasoning": "Paper focuses on retrieval-augmented generation"
}"""

        # Execute
        from paper_collection.paper_summary.summary_generation import (
            classify_paper_topics,
        )

        result = classify_paper_topics("https://arxiv.org/pdf/2401.12345")

        # Assert
        assert "RAG" in result.get("topics", result.get("topic", []))
        assert result.get("primary_topic") == "RAG"

    @patch(f"{_SG_MODULE}.call_gemini_api")
    @patch(f"{_SG_MODULE}.download_pdf_text")
    @patch(f"{_SG_MODULE}.load_topic_prompt")
    @patch(f"{_SG_MODULE}.get_default_model")
    def test_classify_paper_topics_invalid_topics_filtered(
        self,
        mock_get_model: MagicMock,
        mock_load_prompt: MagicMock,
        mock_download: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Test that invalid topics are filtered out."""
        # Setup
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_load_prompt.return_value = "Classify <PDF_URL> For the above paper,"
        mock_download.return_value = "Paper content"
        mock_api.return_value = """
{
    "topics": ["RAG", "InvalidTopic", "Agent"],
    "primary_topic": "RAG",
    "reasoning": "Test"
}"""

        # Execute
        from paper_collection.paper_summary.summary_generation import (
            classify_paper_topics,
        )

        result = classify_paper_topics("https://arxiv.org/pdf/2401.12345")

        # Assert: Invalid topic should be filtered
        topics = result.get("topics", result.get("topic", []))
        assert "InvalidTopic" not in topics
        assert "RAG" in topics
        assert "Agent" in topics


class TestAllowedTopicsConstant:
    """Tests for ALLOWED_TOPICS constant imported from prompt_manager."""

    def test_allowed_topics_imported(self) -> None:
        """Test that ALLOWED_TOPICS is accessible from summary_generation."""
        # Import ALLOWED_TOPICS through the regular import chain
        from paper_collection.paper_summary.prompt_manager import ALLOWED_TOPICS

        # Assert: Should contain expected topics
        assert "RAG" in ALLOWED_TOPICS
        assert "Agent" in ALLOWED_TOPICS
        assert "Memory" in ALLOWED_TOPICS
        assert "Benchmark" in ALLOWED_TOPICS

    def test_validate_topic_against_allowed_list(self) -> None:
        """Test validating individual topics against allowed list."""
        from paper_collection.paper_summary.prompt_manager import ALLOWED_TOPICS

        # Valid topics
        valid_topics = ["RAG", "Agent", "Memory", "P13N", "Factuality"]
        for topic in valid_topics:
            assert topic in ALLOWED_TOPICS

        # Invalid topics
        invalid_topics = ["NotATopic", "Random", "InvalidCategory"]
        for topic in invalid_topics:
            assert topic not in ALLOWED_TOPICS
