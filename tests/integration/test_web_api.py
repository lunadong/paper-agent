"""
Integration tests for web_interface/web_server.py

Tests the web API using Flask test client with mocked database.
"""

from typing import Any, Dict, List
from unittest.mock import patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_paper_list() -> List[Dict[str, Any]]:
    """Sample list of papers for API responses."""
    return [
        {
            "id": 1,
            "title": "Retrieval-Augmented Generation for NLP Tasks",
            "authors": "A. Author, B. Researcher",
            "venue": "arXiv",
            "year": "2024",
            "abstract": "This paper introduces RAG...",
            "link": "https://arxiv.org/abs/2401.12345",
            "recomm_date": "2024-01-15",
            "topics": "RAG, Reasoning",
            "primary_topic": "RAG",
            "has_summary": True,
        },
        {
            "id": 2,
            "title": "Memory-Augmented Neural Networks",
            "authors": "C. Developer, D. Engineer",
            "venue": "ACM",
            "year": "2024",
            "abstract": "A memory-augmented architecture...",
            "link": "https://dl.acm.org/doi/10.1145/1234567",
            "recomm_date": "2024-01-16",
            "topics": "Memory, Agent",
            "primary_topic": "Memory",
            "has_summary": False,
        },
        {
            "id": 3,
            "title": "Knowledge Graph Embeddings",
            "authors": "E. Expert",
            "venue": "ICLR",
            "year": "2024",
            "abstract": "Knowledge graph methods...",
            "link": "https://openreview.net/forum?id=abc123",
            "recomm_date": "2024-01-14",
            "topics": "KG, Reasoning",
            "primary_topic": "KG",
            "has_summary": True,
        },
    ]


@pytest.fixture
def sample_stats() -> Dict[str, Any]:
    """Sample statistics for /api/stats endpoint."""
    return {
        "total_papers": 100,
        "papers_with_embedding": 85,
        "papers_without_embedding": 15,
        "coverage_percent": 85.0,
    }


@pytest.fixture
def mock_db_functions(sample_paper_list, sample_stats):
    """Mock all db.py functions used by web_server."""
    with patch("web_interface.web_server.get_all_papers") as mock_get_all:
        with patch("web_interface.web_server.search_papers_semantic") as mock_semantic:
            with patch(
                "web_interface.web_server.search_papers_keyword"
            ) as mock_keyword:
                with patch(
                    "web_interface.web_server.filter_papers_by_topics"
                ) as mock_filter_topics:
                    with patch(
                        "web_interface.web_server.filter_papers_by_date"
                    ) as mock_filter_date:
                        with patch(
                            "web_interface.web_server.get_similar_papers"
                        ) as mock_similar:
                            with patch(
                                "web_interface.web_server.get_stats"
                            ) as mock_stats:
                                with patch(
                                    "web_interface.web_server.calculate_monthly_stats"
                                ) as mock_monthly:
                                    with patch(
                                        "web_interface.web_server.calculate_topic_stats"
                                    ) as mock_topic:
                                        with patch(
                                            "web_interface.web_server.load_config"
                                        ) as mock_config:
                                            # Configure mocks
                                            mock_get_all.return_value = (
                                                sample_paper_list
                                            )
                                            mock_semantic.return_value = (
                                                sample_paper_list[:1]
                                            )
                                            mock_keyword.return_value = (
                                                sample_paper_list[:2]
                                            )
                                            mock_filter_topics.side_effect = (
                                                lambda papers, f: papers
                                            )
                                            mock_filter_date.side_effect = (
                                                lambda papers, f, t: papers
                                            )
                                            mock_similar.return_value = (
                                                sample_paper_list[1:]
                                            )
                                            mock_stats.return_value = sample_stats
                                            mock_monthly.return_value = [
                                                {"month": "2024-01", "count": 10}
                                            ]
                                            mock_topic.return_value = [
                                                {"topic": "RAG", "count": 5}
                                            ]
                                            mock_config.return_value = {
                                                "web": {"papers_per_page": 10}
                                            }

                                            yield {
                                                "get_all_papers": mock_get_all,
                                                "search_papers_semantic": mock_semantic,
                                                "search_papers_keyword": mock_keyword,
                                                "filter_papers_by_topics": mock_filter_topics,
                                                "filter_papers_by_date": mock_filter_date,
                                                "get_similar_papers": mock_similar,
                                                "get_stats": mock_stats,
                                                "calculate_monthly_stats": mock_monthly,
                                                "calculate_topic_stats": mock_topic,
                                                "load_config": mock_config,
                                            }


@pytest.fixture
def test_client(mock_db_functions):
    """Create Flask test client with mocked dependencies."""
    # Import app after mocks are set up
    from web_interface.web_server import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# Test: Index Page
# =============================================================================


@pytest.mark.integration
class TestIndexPage:
    """Tests for the index page."""

    def test_index_page(self, test_client):
        """Test: GET / returns 200 status code."""
        # Execute: Request index page
        response = test_client.get("/")

        # Assert: Page returned successfully
        assert response.status_code == 200


# =============================================================================
# Test: API Papers Endpoint
# =============================================================================


@pytest.mark.integration
class TestApiPapers:
    """Tests for /api/papers endpoint."""

    def test_api_papers_default(self, test_client, sample_paper_list):
        """Test: GET /api/papers with default parameters."""
        # Execute: Request papers with defaults
        response = test_client.get("/api/papers")

        # Assert: Response contains papers
        assert response.status_code == 200
        data = response.get_json()

        assert "papers" in data
        assert "page" in data
        assert "total_papers" in data
        assert data["page"] == 1
        assert data["total_papers"] == 3

    def test_api_papers_pagination(self, test_client, mock_db_functions):
        """Test: Page parameter works correctly."""
        # Setup: Create more papers than fit on one page
        many_papers = [
            {
                "id": i,
                "title": f"Paper {i}",
                "authors": "Author",
                "venue": "arXiv",
                "year": "2024",
                "abstract": "Abstract",
                "link": f"https://arxiv.org/abs/{i}",
                "recomm_date": "2024-01-15",
                "topics": "RAG",
                "primary_topic": "RAG",
                "has_summary": False,
            }
            for i in range(1, 26)
        ]
        mock_db_functions["get_all_papers"].return_value = many_papers

        # Execute: Request page 2
        response = test_client.get("/api/papers?page=2")

        # Assert: Correct page returned
        assert response.status_code == 200
        data = response.get_json()

        assert data["page"] == 2
        assert data["total_papers"] == 25
        assert data["start"] == 10  # Second page starts at index 10

    def test_api_papers_search(self, test_client, mock_db_functions):
        """Test: Search query parameter works."""
        # Execute: Search for papers
        response = test_client.get("/api/papers?q=RAG")

        # Assert: Search performed
        assert response.status_code == 200
        data = response.get_json()

        assert data["search"] == "RAG"
        mock_db_functions["search_papers_semantic"].assert_called_with("RAG")

    def test_api_papers_keyword_search(self, test_client, mock_db_functions):
        """Test: Keyword search mode works."""
        # Execute: Search with keyword mode
        response = test_client.get("/api/papers?q=RAG&mode=keyword")

        # Assert: Keyword search used
        assert response.status_code == 200
        data = response.get_json()

        assert data["search_mode"] == "keyword"
        mock_db_functions["search_papers_keyword"].assert_called_with("RAG")

    def test_api_papers_filter_topics(
        self, test_client, mock_db_functions, sample_paper_list
    ):
        """Test: Topic filtering parameter works."""

        # Setup: Configure filter mock to actually filter
        def filter_by_topic(papers, topics_filter):
            if not topics_filter:
                return papers
            return [p for p in papers if topics_filter in p.get("topics", "")]

        mock_db_functions["filter_papers_by_topics"].side_effect = filter_by_topic

        # Execute: Filter by topic
        response = test_client.get("/api/papers?topics=RAG")

        # Assert: Topics filter applied
        assert response.status_code == 200
        data = response.get_json()

        assert data["topics"] == "RAG"
        mock_db_functions["filter_papers_by_topics"].assert_called()

    def test_api_papers_sort_order(self, test_client, mock_db_functions):
        """Test: Sort and order parameters work."""
        # Execute: Request with custom sort
        response = test_client.get("/api/papers?sort=title&order=ASC")

        # Assert: Sort parameters returned in response
        assert response.status_code == 200
        data = response.get_json()

        assert data["sort"] == "title"
        assert data["order"] == "ASC"

    def test_api_papers_date_filter(self, test_client, mock_db_functions):
        """Test: Date range filtering works."""
        # Execute: Filter by date range
        response = test_client.get(
            "/api/papers?date_from=2024-01-01&date_to=2024-01-31"
        )

        # Assert: Date filters applied
        assert response.status_code == 200
        data = response.get_json()

        assert data["date_from"] == "2024-01-01"
        assert data["date_to"] == "2024-01-31"
        mock_db_functions["filter_papers_by_date"].assert_called()


# =============================================================================
# Test: API Stats Endpoint
# =============================================================================


@pytest.mark.integration
class TestApiStats:
    """Tests for /api/stats endpoint."""

    def test_api_stats(self, test_client, sample_stats, mock_db_functions):
        """Test: GET /api/stats returns database statistics."""
        # Execute: Request stats
        response = test_client.get("/api/stats")

        # Assert: Stats returned correctly
        assert response.status_code == 200
        data = response.get_json()

        assert data["total_papers"] == sample_stats["total_papers"]
        assert data["papers_with_embedding"] == sample_stats["papers_with_embedding"]
        assert data["coverage_percent"] == sample_stats["coverage_percent"]
        mock_db_functions["get_stats"].assert_called_once()


# =============================================================================
# Test: API Similar Papers Endpoint
# =============================================================================


@pytest.mark.integration
class TestApiSimilarPapers:
    """Tests for /api/similar/<id> endpoint."""

    def test_api_similar_papers(
        self, test_client, sample_paper_list, mock_db_functions
    ):
        """Test: GET /api/similar/<id> returns similar papers."""
        # Execute: Request similar papers for paper ID 1
        response = test_client.get("/api/similar/1")

        # Assert: Similar papers returned
        assert response.status_code == 200
        data = response.get_json()

        assert "papers" in data
        assert "source_id" in data
        assert data["source_id"] == 1
        assert len(data["papers"]) == 2  # sample_paper_list[1:]
        mock_db_functions["get_similar_papers"].assert_called_with(1, 5)

    def test_api_similar_papers_custom_limit(self, test_client, mock_db_functions):
        """Test: Custom limit parameter works."""
        # Execute: Request with custom limit
        response = test_client.get("/api/similar/1?limit=10")

        # Assert: Custom limit used
        assert response.status_code == 200
        mock_db_functions["get_similar_papers"].assert_called_with(1, 10)

    def test_api_similar_papers_no_results(self, test_client, mock_db_functions):
        """Test: Handle no similar papers gracefully."""
        # Setup: Return empty list
        mock_db_functions["get_similar_papers"].return_value = []

        # Execute: Request similar papers
        response = test_client.get("/api/similar/999")

        # Assert: Empty list returned
        assert response.status_code == 200
        data = response.get_json()

        assert data["papers"] == []
        assert data["source_id"] == 999


# =============================================================================
# Test: Response Structure
# =============================================================================


@pytest.mark.integration
class TestResponseStructure:
    """Tests for API response structure."""

    def test_api_papers_response_structure(self, test_client):
        """Test: /api/papers response has all required fields."""
        # Execute: Request papers
        response = test_client.get("/api/papers")
        data = response.get_json()

        # Assert: All required fields present
        required_fields = [
            "papers",
            "page",
            "total_pages",
            "total_papers",
            "start",
            "end",
            "search",
            "search_mode",
            "sort",
            "order",
            "date_from",
            "date_to",
            "topics",
            "primary_topic",
            "monthly_stats",
            "topic_stats",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_monthly_stats_in_response(self, test_client, mock_db_functions):
        """Test: Monthly stats included in papers response."""
        # Execute: Request papers
        response = test_client.get("/api/papers")
        data = response.get_json()

        # Assert: Monthly stats present and formatted correctly
        assert "monthly_stats" in data
        assert len(data["monthly_stats"]) > 0
        assert "month" in data["monthly_stats"][0]
        assert "count" in data["monthly_stats"][0]

    def test_topic_stats_in_response(self, test_client, mock_db_functions):
        """Test: Topic stats included in papers response."""
        # Execute: Request papers
        response = test_client.get("/api/papers")
        data = response.get_json()

        # Assert: Topic stats present and formatted correctly
        assert "topic_stats" in data
        assert len(data["topic_stats"]) > 0
        assert "topic" in data["topic_stats"][0]
        assert "count" in data["topic_stats"][0]
