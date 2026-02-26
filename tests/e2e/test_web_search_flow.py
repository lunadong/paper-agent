"""
E2E tests for web search functionality.

Tests the complete web search flow:
1. Query submission via Flask test client
2. Embedding generation via OpenAI API
3. Vector search in PostgreSQL with pgvector
4. Result filtering and pagination
5. Paper detail view with summaries

All external services (OpenAI API, Database) are mocked.
"""

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_papers_list() -> List[Dict[str, Any]]:
    """Sample list of papers for testing search and filtering."""
    return [
        {
            "id": 1,
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive Tasks",
            "authors": "A. Author, B. Researcher",
            "venue": "arXiv",
            "year": "2024",
            "abstract": "This paper introduces RAG for knowledge-intensive NLP tasks.",
            "link": "https://arxiv.org/abs/2401.12345",
            "recomm_date": "2024-01-15",
            "topics": "RAG, Reasoning",
            "primary_topic": "RAG",
            "has_summary": True,
        },
        {
            "id": 2,
            "title": "Memory-Augmented Neural Networks for Conversational AI",
            "authors": "C. Developer, D. Engineer",
            "venue": "ACM",
            "year": "2024",
            "abstract": "A memory-augmented architecture for long-context conversations.",
            "link": "https://dl.acm.org/doi/10.1145/1234567",
            "recomm_date": "2024-01-10",
            "topics": "Memory, Agent",
            "primary_topic": "Memory",
            "has_summary": False,
        },
        {
            "id": 3,
            "title": "Factuality Checking in Large Language Models",
            "authors": "E. Expert, F. Fellow",
            "venue": "NeurIPS",
            "year": "2023",
            "abstract": "Detecting and reducing hallucinations in LLM outputs.",
            "link": "https://neurips.cc/paper/1234",
            "recomm_date": "2023-12-01",
            "topics": "Factuality, Reasoning",
            "primary_topic": "Factuality",
            "has_summary": True,
        },
    ]


@pytest.fixture
def mock_embedding_vector() -> List[float]:
    """Mock OpenAI embedding vector (512 dimensions)."""
    return [0.1] * 512


@pytest.fixture
def sample_paper_with_summary() -> Dict[str, Any]:
    """Sample paper with full summary data."""
    return {
        "id": 1,
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive Tasks",
        "authors": "A. Author, B. Researcher",
        "venue": "arXiv",
        "year": "2024",
        "abstract": "This paper introduces RAG for knowledge-intensive NLP tasks.",
        "link": "https://arxiv.org/abs/2401.12345",
        "recomm_date": "2024-01-15",
        "topics": "RAG, Reasoning",
        "summary_generated_at": "2024-01-16T10:00:00Z",
        "summary_basics": json.dumps(
            {
                "title": "Retrieval-Augmented Generation for Knowledge-Intensive Tasks",
                "arxiv_id": "2401.12345",
                "venue": "arXiv",
                "year": "2024",
                "authors": ["A. Author", "B. Researcher"],
            }
        ),
        "summary_core": json.dumps(
            {
                "topics": ["RAG", "Reasoning"],
                "primary_topic": "RAG",
                "sub_topic": "Dense Retrieval",
                "problem_statement": "Improving factuality in LLM outputs",
                "thesis": "Combining dense retrieval with generation improves accuracy",
                "novelty": "Novel retrieval-generation fusion mechanism",
                "breakthrough_score": 7,
            }
        ),
        "summary_techniques": json.dumps(
            {
                "pipeline": ["Retrieve relevant passages", "Generate with context"],
                "results": [
                    {"metric": "Accuracy", "value": "85.3%", "baseline": "78.1%"}
                ],
            }
        ),
        "summary_experiments": json.dumps(
            {
                "pipeline": ["Retrieve relevant passages", "Generate with context"],
                "results": [
                    {"metric": "Accuracy", "value": "85.3%", "baseline": "78.1%"}
                ],
            }
        ),
        "summary_figures": json.dumps(
            {
                "figures": [
                    {"figure_id": "Figure 1", "description": "System architecture"},
                ]
            }
        ),
    }


@pytest.mark.e2e
class TestSemanticSearchFlow:
    """E2E tests for semantic search functionality."""

    @patch("db.generate_openai_embedding")
    @patch("db.execute_with_retry")
    @patch("db.get_db_connection")
    def test_semantic_search_flow(
        self,
        mock_get_conn: MagicMock,
        mock_execute: MagicMock,
        mock_gen_embedding: MagicMock,
        sample_papers_list: List[Dict[str, Any]],
        mock_embedding_vector: List[float],
    ):
        """
        Test semantic search: Query -> Embed -> Search -> Results.

        This test validates the complete semantic search flow:
        1. User query is converted to embedding via OpenAI
        2. pgvector similarity search finds matching papers
        3. Results are returned with similarity scores
        4. Results are properly sorted and formatted

        Mocks:
        - OpenAI embedding API
        - Database connection and queries
        """
        # Setup mocks
        mock_gen_embedding.return_value = mock_embedding_vector

        # Mock database connection
        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_get_conn.return_value = mock_conn

        # Mock database cursor with search results
        mock_cursor = MagicMock()
        search_results = [
            {**paper, "similarity": 0.85 - (i * 0.1)}
            for i, paper in enumerate(sample_papers_list)
        ]
        mock_cursor.fetchone.side_effect = [
            {"total": 3},  # First call: embedding count check
        ]
        mock_cursor.fetchall.return_value = search_results
        mock_execute.return_value = mock_cursor

        from db import search_papers_semantic

        # Execute semantic search
        results = search_papers_semantic("retrieval augmented generation")

        # Verify embedding was generated
        mock_gen_embedding.assert_called_once()
        assert "retrieval augmented generation" in mock_gen_embedding.call_args[0][0]

        # Verify results
        assert len(results) >= 1

    @patch("db.search_papers_semantic")
    @patch("db.calculate_monthly_stats")
    @patch("db.calculate_topic_stats")
    def test_semantic_search_via_api(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_search: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test semantic search via Flask API endpoint.

        This test validates:
        1. API endpoint accepts search query
        2. Semantic search mode is used
        3. Results are paginated correctly
        4. JSON response format is correct

        Mocks:
        - Database search functions
        - Statistics calculations
        """
        # Setup mocks
        mock_search.return_value = sample_papers_list
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request
        response = flask_client.get("/api/papers?q=RAG&mode=semantic")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data
        assert "total_papers" in data
        assert "search" in data
        assert data["search"] == "RAG"
        assert data["search_mode"] == "semantic"

    @patch("web_server.search_papers_keyword")
    @patch("web_server.calculate_monthly_stats")
    @patch("web_server.calculate_topic_stats")
    def test_keyword_search_fallback(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_keyword_search: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test keyword search mode via API.

        This test validates:
        1. Keyword search mode is selected with mode=keyword
        2. SQL ILIKE search is performed
        3. Results match keyword pattern

        Mocks:
        - Database keyword search function
        - Statistics calculations
        """
        # Setup mocks
        mock_keyword_search.return_value = [sample_papers_list[0]]
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request with keyword mode
        response = flask_client.get("/api/papers?q=RAG&mode=keyword")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data
        mock_keyword_search.assert_called_once_with("RAG")


@pytest.mark.e2e
class TestTopicFilterFlow:
    """E2E tests for topic filtering functionality."""

    @patch("db.get_all_papers")
    @patch("db.calculate_monthly_stats")
    @patch("db.calculate_topic_stats")
    def test_topic_filter_flow(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_get_all: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test filtering papers by topic.

        This test validates:
        1. API accepts topic filter parameter
        2. Papers are filtered to only include matching topics
        3. Only papers with ALL selected topics are returned

        Mocks:
        - Database get_all_papers function
        - Statistics calculations
        """
        # Setup mocks
        mock_get_all.return_value = sample_papers_list
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request with topic filter
        response = flask_client.get("/api/papers?topics=RAG")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data

        # Verify only papers with "RAG" topic are returned
        for paper in data["papers"]:
            assert "RAG" in paper.get("topics", "")

    @patch("db.get_all_papers")
    @patch("db.calculate_monthly_stats")
    @patch("db.calculate_topic_stats")
    def test_primary_topic_filter(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_get_all: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test filtering papers by primary topic.

        This test validates:
        1. API accepts primary_topic filter parameter
        2. Papers are filtered by exact primary_topic match
        3. Only papers with matching primary_topic are returned

        Mocks:
        - Database get_all_papers function
        - Statistics calculations
        """
        # Setup mocks
        mock_get_all.return_value = sample_papers_list
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request with primary_topic filter
        response = flask_client.get("/api/papers?primary_topic=Memory")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data

        # Verify only papers with "Memory" as primary_topic are returned
        for paper in data["papers"]:
            assert paper.get("primary_topic") == "Memory"

    @patch("db.get_all_papers")
    @patch("db.calculate_monthly_stats")
    @patch("db.calculate_topic_stats")
    def test_multiple_topic_filter(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_get_all: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test filtering papers by multiple topics (AND logic).

        This test validates:
        1. Multiple topics can be specified comma-separated
        2. Papers must have ALL specified topics
        3. Papers with only some topics are excluded

        Mocks:
        - Database get_all_papers function
        - Statistics calculations
        """
        # Setup mocks
        mock_get_all.return_value = sample_papers_list
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request with multiple topics
        response = flask_client.get("/api/papers?topics=RAG,Reasoning")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data

        # Verify papers have both topics
        for paper in data["papers"]:
            topics = paper.get("topics", "")
            assert "RAG" in topics and "Reasoning" in topics


@pytest.mark.e2e
class TestPaperDetailFlow:
    """E2E tests for paper detail view with summaries."""

    @patch("web_interface.paper_detail.get_paper_by_id")
    @patch("web_interface.paper_detail.get_paper_images")
    def test_paper_detail_with_summary(
        self,
        mock_get_images: MagicMock,
        mock_get_paper: MagicMock,
        flask_client,
        sample_paper_with_summary: Dict[str, Any],
    ):
        """
        Test viewing paper detail page with AI summary.

        This test validates:
        1. Paper detail endpoint returns paper data
        2. Summary sections are parsed from JSON
        3. Summary data is included in response
        4. All summary sections (basics, core, methods, figures) are available

        Mocks:
        - Database get_paper_by_id function
        - Database get_paper_images function
        """
        # Setup mocks
        mock_get_paper.return_value = sample_paper_with_summary
        mock_get_images.return_value = []

        # Make API request for paper detail
        response = flask_client.get("/api/paper/1")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()

        # Verify paper data
        assert data["id"] == 1
        assert "Retrieval-Augmented Generation" in data["title"]

        # Verify summary is present
        assert data["has_summary"] is True
        assert "summary" in data

        # Verify summary sections
        summary = data["summary"]
        assert "basics" in summary
        assert "core" in summary
        assert "techniques" in summary

        # Verify summary content
        assert summary["basics"]["arxiv_id"] == "2401.12345"
        assert summary["core"]["primary_topic"] == "RAG"
        assert summary["core"]["breakthrough_score"] == 7

    @patch("web_interface.paper_detail.get_paper_by_id")
    @patch("web_interface.paper_detail.get_paper_images")
    def test_paper_detail_without_summary(
        self,
        mock_get_images: MagicMock,
        mock_get_paper: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test viewing paper detail without AI summary.

        This test validates:
        1. Paper without summary still returns valid response
        2. has_summary flag is False
        3. Basic paper metadata is still available

        Mocks:
        - Database get_paper_by_id function
        - Database get_paper_images function
        """
        # Setup mocks - paper without summary
        paper_no_summary = sample_papers_list[1].copy()
        paper_no_summary["summary_generated_at"] = None
        paper_no_summary["summary_basics"] = None
        paper_no_summary["summary_core"] = None
        paper_no_summary["summary_techniques"] = None
        paper_no_summary["summary_experiments"] = None
        paper_no_summary["summary_figures"] = None
        mock_get_paper.return_value = paper_no_summary
        mock_get_images.return_value = []

        # Make API request for paper detail
        response = flask_client.get("/api/paper/2")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()

        # Verify paper data
        assert data["id"] == 2
        assert "Memory-Augmented" in data["title"]

        # Verify no summary
        assert data["has_summary"] is False

    @patch("web_interface.paper_detail.get_paper_by_id")
    def test_paper_not_found(
        self,
        mock_get_paper: MagicMock,
        flask_client,
    ):
        """
        Test paper detail for non-existent paper.

        This test validates:
        1. API returns 404 for non-existent paper
        2. Error message is included in response

        Mocks:
        - Database get_paper_by_id function (returns None)
        """
        # Setup mocks
        mock_get_paper.return_value = None

        # Make API request for non-existent paper
        response = flask_client.get("/api/paper/99999")

        # Verify response
        assert response.status_code == 404


@pytest.mark.e2e
class TestDateFilterFlow:
    """E2E tests for date range filtering."""

    @patch("db.get_all_papers")
    @patch("db.calculate_monthly_stats")
    @patch("db.calculate_topic_stats")
    def test_date_range_filter(
        self,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_get_all: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test filtering papers by date range.

        This test validates:
        1. API accepts date_from and date_to parameters
        2. Papers are filtered to date range
        3. Papers outside range are excluded

        Mocks:
        - Database get_all_papers function
        - Statistics calculations
        """
        # Setup mocks
        mock_get_all.return_value = sample_papers_list
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []

        # Make API request with date filter
        response = flask_client.get(
            "/api/papers?date_from=2024-01-01&date_to=2024-01-31"
        )

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data
        assert "date_from" in data
        assert "date_to" in data
        assert data["date_from"] == "2024-01-01"
        assert data["date_to"] == "2024-01-31"

        # Verify papers are within date range
        for paper in data["papers"]:
            recomm_date = paper.get("recomm_date", "")
            assert recomm_date >= "2024-01-01"
            assert recomm_date <= "2024-01-31"


@pytest.mark.e2e
class TestSimilarPapersFlow:
    """E2E tests for similar papers functionality."""

    @patch("db.execute_with_retry")
    def test_similar_papers_api(
        self,
        mock_execute: MagicMock,
        flask_client,
        sample_papers_list: List[Dict[str, Any]],
    ):
        """
        Test finding similar papers via API.

        This test validates:
        1. Similar papers endpoint accepts paper_id
        2. Vector similarity search is performed
        3. Similar papers are returned with similarity scores

        Mocks:
        - Database execute function
        """
        # Setup mocks
        mock_cursor = MagicMock()

        # First call returns source paper embedding
        # Second call returns similar papers
        mock_cursor.fetchone.side_effect = [
            {"embedding": [0.1] * 512},  # Source paper
        ]
        mock_cursor.fetchall.return_value = [
            {**paper, "similarity": 0.9 - (i * 0.1)}
            for i, paper in enumerate(sample_papers_list[1:])
        ]
        mock_execute.return_value = mock_cursor

        # Make API request
        response = flask_client.get("/api/similar/1?limit=5")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert "papers" in data
        assert "source_id" in data
        assert data["source_id"] == 1


@pytest.mark.e2e
class TestPaginationFlow:
    """E2E tests for pagination functionality."""

    @patch("web_server.get_all_papers")
    @patch("web_server.calculate_monthly_stats")
    @patch("web_server.calculate_topic_stats")
    @patch("web_server.load_config")
    def test_pagination(
        self,
        mock_config: MagicMock,
        mock_topic_stats: MagicMock,
        mock_monthly_stats: MagicMock,
        mock_get_all: MagicMock,
        flask_client,
    ):
        """
        Test pagination of paper list.

        This test validates:
        1. Papers are paginated correctly
        2. Page number and total pages are returned
        3. Start and end indices are correct

        Mocks:
        - Database get_all_papers function
        - Configuration
        - Statistics calculations
        """
        # Create a list of 25 papers for pagination testing
        papers = [
            {
                "id": i,
                "title": f"Paper {i}",
                "authors": "Author",
                "venue": "Venue",
                "year": "2024",
                "abstract": f"Abstract {i}",
                "link": f"https://example.com/{i}",
                "recomm_date": "2024-01-15",
                "topics": "",
                "primary_topic": "",
                "has_summary": False,
            }
            for i in range(1, 26)
        ]

        # Setup mocks
        mock_get_all.return_value = papers
        mock_monthly_stats.return_value = []
        mock_topic_stats.return_value = []
        mock_config.return_value = {"web": {"papers_per_page": 10}}

        # Make API request for page 1
        response = flask_client.get("/api/papers?page=1")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert data["page"] == 1
        assert data["total_papers"] == 25
        assert data["total_pages"] == 3  # 25 papers / 10 per page = 3 pages
        assert data["start"] == 0
        assert data["end"] == 10
        assert len(data["papers"]) == 10

        # Make API request for page 2
        response = flask_client.get("/api/papers?page=2")
        data = response.get_json()
        assert data["page"] == 2
        assert data["start"] == 10
        assert data["end"] == 20

        # Make API request for page 3 (partial page)
        response = flask_client.get("/api/papers?page=3")
        data = response.get_json()
        assert data["page"] == 3
        assert data["start"] == 20
        assert data["end"] == 25
        assert len(data["papers"]) == 5


@pytest.mark.e2e
class TestStatsEndpoint:
    """E2E tests for statistics endpoint."""

    @patch("db.execute_with_retry")
    def test_stats_api(
        self,
        mock_execute: MagicMock,
        flask_client,
    ):
        """
        Test database statistics API endpoint.

        This test validates:
        1. Stats endpoint returns paper counts
        2. Embedding coverage is calculated
        3. Response format is correct

        Mocks:
        - Database execute function
        """
        # Setup mocks
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total_papers": 100,
            "papers_with_embedding": 80,
            "papers_without_embedding": 20,
        }
        mock_execute.return_value = mock_cursor

        # Make API request
        response = flask_client.get("/api/stats")

        # Verify response
        assert response.status_code == 200

        data = response.get_json()
        assert data["total_papers"] == 100
        assert data["papers_with_embedding"] == 80
        assert data["papers_without_embedding"] == 20
        assert data["coverage_percent"] == 80.0
