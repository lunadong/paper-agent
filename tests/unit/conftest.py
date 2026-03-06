"""
Pytest fixtures for unit tests.

Provides shared test fixtures used across multiple test modules.
"""

from typing import Any, Dict

import pytest


@pytest.fixture
def sample_summary_json() -> Dict[str, Any]:
    """
    Provide a sample paper summary JSON structure for testing.

    Returns a complete summary structure with all required sections
    and fields that match the expected output format.
    """
    return {
        "basics": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "arxiv_id": "2401.12345",
            "authors": ["Author One", "Author Two", "Author Three"],
            "venue": "arXiv",
            "year": "2024",
            "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
        },
        "core": {
            "topics": ["RAG", "Agent", "Memory"],
            "primary_topic": "RAG",
            "problem_statement": (
                "Current language models struggle with knowledge-intensive tasks "
                "that require access to external information."
            ),
            "thesis": (
                "Combining retrieval mechanisms with generative models improves "
                "performance on knowledge-intensive NLP tasks."
            ),
            "key_contributions": [
                "Novel retrieval-augmented architecture",
                "State-of-the-art results on open-domain QA",
                "Efficient training methodology",
            ],
        },
        "technical_details": {
            "pipeline": [
                "Query encoding using dense retriever",
                "Document retrieval from knowledge base",
                "Context integration with generator",
                "Answer generation using seq2seq model",
            ],
            "methods": {
                "retriever": "Dense Passage Retrieval (DPR)",
                "generator": "BART-large",
                "training": "End-to-end with marginalized likelihood",
            },
            "results": [
                {
                    "metric": "Exact Match",
                    "value": "44.5%",
                    "dataset": "Natural Questions",
                },
                {
                    "metric": "Exact Match",
                    "value": "56.1%",
                    "dataset": "TriviaQA",
                },
            ],
            "limitations": [
                "Requires large knowledge base",
                "Retrieval latency at inference time",
            ],
        },
    }


@pytest.fixture
def sample_paper_text() -> str:
    """
    Provide sample paper text content for testing.

    Returns a simplified version of paper text that might be
    extracted from a PDF.
    """
    return """
    --- Page 1 ---
    Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

    Abstract
    We explore a general-purpose fine-tuning recipe for retrieval-augmented
    generation (RAG) -- models which combine pre-trained parametric and
    non-parametric memory for language generation.

    1 Introduction
    Large pre-trained language models have been shown to store factual
    knowledge in their parameters. However, their ability to access and
    precisely manipulate knowledge is still limited.

    --- Page 2 ---
    2 Methods
    Our approach combines a pre-trained seq2seq model (the generator) with
    a dense retrieval component (the retriever).
    """
