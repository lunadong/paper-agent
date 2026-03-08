"""
Unit tests for the topic tagger module.

Tests paper_collection/paper_metadata/topic_tagger.py functionality including:
- TOPICS constant existence and structure
- TOPIC_QUERIES definitions
- Exact match searching with word boundaries
- Case insensitivity
- False positive prevention for short acronyms
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection"))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection" / "paper_metadata"))

# Import TOPICS from paper_db
from core.paper_db import TOPICS
from topic_tagger import exact_match_search, SHORT_ACRONYMS, TOPIC_QUERIES


class TestTopicsDict:
    """Tests for the TOPICS constant."""

    def test_topics_dict_exists(self) -> None:
        """TOPICS constant exists with 14 entries."""
        # Setup: Expected topic count and some key topics
        expected_count = 14
        expected_topics = {
            "Pretraining",
            "RL",
            "Reasoning",
            "Factuality",
            "RAG",
            "Agent",
            "P13N",
            "Memory",
            "KG",
            "QA",
            "Recommendation",
            "MM",
            "Speech",
            "Benchmark",
        }

        # Execute: Check TOPICS structure (implicitly done above)

        # Assert: TOPICS has correct structure and count
        assert isinstance(TOPICS, dict), "TOPICS should be a dictionary"
        assert len(TOPICS) == expected_count, (
            f"TOPICS should have {expected_count} entries, got {len(TOPICS)}"
        )

        # Verify all expected topic keys exist
        for topic in expected_topics:
            assert topic in TOPICS, f"Topic '{topic}' should exist in TOPICS"

        # Verify each topic has a non-empty full name
        for tag, full_name in TOPICS.items():
            assert isinstance(full_name, str), (
                f"Full name for '{tag}' should be a string"
            )
            assert len(full_name) > 0, f"Full name for '{tag}' should not be empty"


class TestTopicQueries:
    """Tests for the TOPIC_QUERIES constant."""

    def test_topic_queries_defined(self) -> None:
        """TOPIC_QUERIES has queries for each topic in TOPICS."""
        # Setup: Get all topic keys from TOPICS
        topic_keys = set(TOPICS.keys())

        # Execute: Get all topic keys from TOPIC_QUERIES
        query_keys = set(TOPIC_QUERIES.keys())

        # Assert: Every topic has corresponding queries
        assert query_keys == topic_keys, (
            f"TOPIC_QUERIES keys should match TOPICS keys.\n"
            f"Missing in TOPIC_QUERIES: {topic_keys - query_keys}\n"
            f"Extra in TOPIC_QUERIES: {query_keys - topic_keys}"
        )

        # Verify structure of each query definition
        for tag, (exact_queries, semantic_queries) in TOPIC_QUERIES.items():
            assert isinstance(exact_queries, list), (
                f"Exact queries for '{tag}' should be a list"
            )
            assert isinstance(semantic_queries, list), (
                f"Semantic queries for '{tag}' should be a list"
            )
            # At least one type of query should be defined
            assert len(exact_queries) > 0 or len(semantic_queries) > 0, (
                f"Topic '{tag}' should have at least one exact or semantic query"
            )


class TestExactMatchSearch:
    """Tests for exact_match_search function."""

    def test_exact_match_rag(self) -> None:
        """Match 'RAG' with word boundary to find relevant papers."""
        # Setup: Papers with and without RAG mentions
        papers = [
            {"id": 1, "title": "RAG for Question Answering", "abstract": "We use RAG."},
            {
                "id": 2,
                "title": "Retrieval-Augmented Generation",
                "abstract": "RAG works.",
            },
            {
                "id": 3,
                "title": "Unrelated Paper",
                "abstract": "No relevant content here.",
            },
        ]
        queries = ["RAG"]

        # Execute: Search for papers matching "RAG"
        result = exact_match_search(papers, queries)

        # Assert: Papers with "RAG" are matched
        assert 1 in result, "Paper 1 should match 'RAG' in title"
        assert 2 in result, "Paper 2 should match 'RAG' in abstract"
        assert 3 not in result, "Paper 3 should not match"

    def test_exact_match_case_insensitive(self) -> None:
        """Match queries case-insensitively for both 'rag' and 'RAG'."""
        # Setup: Papers with different case variations
        papers = [
            {"id": 1, "title": "Using RAG for Tasks", "abstract": ""},
            {"id": 2, "title": "rag-based approach", "abstract": ""},
            {"id": 3, "title": "Rag methods work", "abstract": ""},
            {"id": 4, "title": "No match here", "abstract": "rAg technique"},
        ]
        queries = ["RAG"]

        # Execute: Search with uppercase query
        result = exact_match_search(papers, queries)

        # Assert: All case variations are matched
        assert 1 in result, "Should match 'RAG' (uppercase)"
        assert 2 in result, "Should match 'rag' (lowercase)"
        assert 3 in result, "Should match 'Rag' (title case)"
        assert 4 in result, "Should match 'rAg' (mixed case)"

    def test_exact_match_no_false_positive(self) -> None:
        """'DRAG' should not match 'RAG' due to word boundary matching."""
        # Setup: Papers with words containing RAG as substring
        papers = [
            {"id": 1, "title": "DRAG-based systems", "abstract": "Using DRAGGING"},
            {"id": 2, "title": "leverage RAG", "abstract": ""},  # This should match
            {"id": 3, "title": "STORAGE system", "abstract": ""},
            {"id": 4, "title": "fragmented", "abstract": "leverages something"},
        ]
        queries = ["RAG"]

        # Execute: Search should use word boundaries for short terms
        result = exact_match_search(papers, queries)

        # Assert: Only exact word matches, no false positives
        assert 1 not in result, "Should NOT match 'DRAG' (RAG is substring)"
        assert 2 in result, "Should match 'RAG' as separate word"
        assert 3 not in result, "Should NOT match 'STORAGE' (RAG is substring)"
        assert 4 not in result, "Should NOT match 'fragmented' (RAG is substring)"

    def test_exact_match_multiple_queries(self) -> None:
        """Match any of multiple keywords in the query list."""
        # Setup: Papers with different keyword matches
        papers = [
            {"id": 1, "title": "Reinforcement Learning", "abstract": ""},
            {"id": 2, "title": "RLHF Training", "abstract": ""},
            {"id": 3, "title": "DPO Optimization", "abstract": ""},
            {"id": 4, "title": "GRPO Methods", "abstract": ""},
            {"id": 5, "title": "Unrelated ML", "abstract": "Neural networks"},
        ]
        queries = ["reinforcement learning", "RLHF", "DPO", "GRPO"]

        # Execute: Search with multiple queries
        result = exact_match_search(papers, queries)

        # Assert: Papers matching any query are found
        assert 1 in result, "Should match 'reinforcement learning'"
        assert 2 in result, "Should match 'RLHF'"
        assert 3 in result, "Should match 'DPO'"
        assert 4 in result, "Should match 'GRPO'"
        assert 5 not in result, "Should not match unrelated paper"

    def test_exact_match_short_terms_word_boundary(self) -> None:
        """Short terms like 'RL' use word boundary matching to avoid false positives."""
        # Setup: Papers with RL as word vs substring
        papers = [
            {"id": 1, "title": "RL for Robotics", "abstract": ""},
            {
                "id": 2,
                "title": "Early stopping",
                "abstract": "",
            },  # Contains 'rl' in 'early'
            {
                "id": 3,
                "title": "CURL algorithm",
                "abstract": "",
            },  # Contains 'RL' in 'CURL'
            {"id": 4, "title": "Applied RL", "abstract": ""},
            {
                "id": 5,
                "title": "World models",
                "abstract": "",
            },  # Contains 'rl' in 'world'
        ]
        queries = ["RL"]

        # Execute: Search with short term
        result = exact_match_search(papers, queries)

        # Assert: Word boundary matching prevents false positives
        assert 1 in result, "Should match 'RL' as separate word"
        assert 2 not in result, "Should NOT match 'early' (RL is substring)"
        assert 3 not in result, "Should NOT match 'CURL' (RL is substring)"
        assert 4 in result, "Should match 'RL' at end of phrase"
        assert 5 not in result, "Should NOT match 'world' (RL is substring)"


class TestShortAcronyms:
    """Tests for SHORT_ACRONYMS constant."""

    def test_short_acronyms_defined(self) -> None:
        """SHORT_ACRONYMS contains expected short terms."""
        # Setup: Expected short acronyms
        expected_acronyms = {"RL", "RAG", "KG", "QA", "MM"}

        # Execute: Check SHORT_ACRONYMS (implicit)

        # Assert: All expected acronyms are present
        assert SHORT_ACRONYMS == expected_acronyms, (
            f"SHORT_ACRONYMS should contain {expected_acronyms}, got {SHORT_ACRONYMS}"
        )


class TestExactMatchEdgeCases:
    """Edge case tests for exact_match_search."""

    def test_exact_match_empty_papers_list(self) -> None:
        """Handle empty papers list gracefully."""
        # Setup: Empty papers list
        papers: List[Dict[str, Any]] = []
        queries = ["RAG", "RL"]

        # Execute: Search with no papers
        result = exact_match_search(papers, queries)

        # Assert: Empty set is returned
        assert result == set(), "Should return empty set for empty papers list"

    def test_exact_match_empty_queries_list(self) -> None:
        """Handle empty queries list gracefully."""
        # Setup: Papers but no queries
        papers = [
            {"id": 1, "title": "Some Paper", "abstract": "Content"},
        ]
        queries: List[str] = []

        # Execute: Search with no queries
        result = exact_match_search(papers, queries)

        # Assert: Empty set is returned
        assert result == set(), "Should return empty set for empty queries list"

    def test_exact_match_none_fields(self) -> None:
        """Handle papers with None title or abstract."""
        # Setup: Papers with None fields
        papers = [
            {"id": 1, "title": None, "abstract": "RAG methods"},
            {"id": 2, "title": "RAG paper", "abstract": None},
            {"id": 3, "title": None, "abstract": None},
        ]
        queries = ["RAG"]

        # Execute: Search should not crash on None fields
        result = exact_match_search(papers, queries)

        # Assert: Papers with matching content are found
        assert 1 in result, "Should match RAG in abstract even if title is None"
        assert 2 in result, "Should match RAG in title even if abstract is None"
        assert 3 not in result, "Should not match when both fields are None"

    def test_exact_match_long_term_substring(self) -> None:
        """Long terms (>3 chars) use substring matching."""
        # Setup: Papers with long term matches
        papers = [
            {"id": 1, "title": "Reinforcement Learning", "abstract": ""},
            {"id": 2, "title": "Deep Reinforcement", "abstract": ""},
            {"id": 3, "title": "Pretraining models", "abstract": ""},
        ]
        queries = ["reinforcement learning"]

        # Execute: Search with long term
        result = exact_match_search(papers, queries)

        # Assert: Substring matching for long terms
        assert 1 in result, "Should match 'Reinforcement Learning'"
        assert 2 not in result, "Should not match partial 'Reinforcement' only"
        assert 3 not in result, "Should not match unrelated"
