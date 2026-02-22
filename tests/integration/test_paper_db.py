"""
Integration tests for paper_collection/paper_db.py

Tests the database layer with mocked PostgreSQL connection.
"""

import threading
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_cursor():
    """Create a mock cursor with RealDictCursor-like behavior."""
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.rowcount = 0
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    """Create a mock database connection."""
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    conn.autocommit = False
    conn.closed = False
    return conn


@pytest.fixture
def sample_paper_row() -> Dict[str, Any]:
    """Sample paper row as returned from database."""
    return {
        "id": 1,
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": "A. Author, B. Researcher",
        "venue": "arXiv",
        "year": "2024",
        "abstract": "This paper introduces a novel approach to RAG...",
        "link": "https://arxiv.org/abs/2401.12345",
        "recomm_date": "2024-01-15",
        "topics": "RAG, Reasoning",
        "primary_topic": "RAG",
        "embedding": [0.1] * 512,
        "summary_generated_at": None,
        "summary_basics": None,
        "summary_core": None,
        "summary_methods_evidence": None,
        "summary_figures": None,
        "created_at": "2024-01-15T10:00:00",
    }


# =============================================================================
# Test: PaperDB Initialization
# =============================================================================


@pytest.mark.integration
class TestPaperDBInit:
    """Tests for PaperDB initialization."""

    def test_paper_db_init(self, mock_connection, mock_cursor):
        """Test: Initialize PaperDB with mocked connection."""
        # Setup: Patch psycopg2.connect to return mock connection
        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                # Execute: Import and create PaperDB
                from paper_db import PaperDB

                db = PaperDB()

                # Assert: Connection was established
                assert db.conn is mock_connection
                assert db.db_url == "postgresql://test:test@localhost/test"

    def test_paper_db_init_with_custom_url(self, mock_connection, mock_cursor):
        """Test: Initialize PaperDB with custom database URL."""
        # Setup: Patch psycopg2.connect
        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            from paper_db import PaperDB

            # Execute: Create PaperDB with custom URL
            custom_url = "postgresql://custom:custom@localhost/custom"
            db = PaperDB(db_url=custom_url)

            # Assert: Custom URL is used
            assert db.db_url == custom_url

    def test_paper_db_init_no_config_raises_error(self):
        """Test: Raise error when no database URL configured."""
        # Setup: Patch config to return empty config
        with patch("paper_db.load_db_config") as mock_config:
            mock_config.return_value = {}

            from paper_db import PaperDB

            # Execute & Assert: Should raise ValueError
            with pytest.raises(ValueError, match="PostgreSQL URL not configured"):
                PaperDB()


# =============================================================================
# Test: Add Paper
# =============================================================================


@pytest.mark.integration
class TestAddPaper:
    """Tests for adding papers to the database."""

    def test_add_paper_new(self, mock_connection, mock_cursor, sample_paper_row):
        """Test: Insert new paper into database."""
        # Setup: Configure mock to return new paper ID
        mock_cursor.fetchone.return_value = {"id": 1}

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Add a new paper
                paper_id = db.add_paper(
                    title="Test Paper Title",
                    authors="John Doe, Jane Smith",
                    venue="arXiv",
                    year="2024",
                    abstract="This is a test abstract.",
                    link="https://arxiv.org/abs/2401.99999",
                    recomm_date="2024-01-20",
                )

                # Assert: Paper was inserted and ID returned
                assert paper_id == 1
                mock_cursor.execute.assert_called()
                mock_connection.commit.assert_called()

    def test_add_paper_duplicate(self, mock_connection, mock_cursor):
        """Test: Handle duplicate paper gracefully (returns None)."""
        # Setup: Configure mock to return None (duplicate case with ON CONFLICT DO NOTHING)
        mock_cursor.fetchone.return_value = None

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Try to add duplicate paper
                paper_id = db.add_paper(
                    title="Duplicate Paper",
                    authors="Author",
                    venue="arXiv",
                    year="2024",
                    abstract="Abstract",
                    link="https://arxiv.org/abs/2401.00001",
                    recomm_date="2024-01-15",
                )

                # Assert: None returned for duplicate
                assert paper_id is None


# =============================================================================
# Test: Get Paper
# =============================================================================


@pytest.mark.integration
class TestGetPaper:
    """Tests for retrieving papers from the database."""

    def test_get_paper_by_id(self, mock_connection, mock_cursor, sample_paper_row):
        """Test: Retrieve paper by ID from database."""
        # Setup: Configure mock to return sample paper
        mock_cursor.fetchone.return_value = sample_paper_row

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Get paper by ID
                paper = db.get_paper_by_id(1)

                # Assert: Paper data returned correctly
                assert paper is not None
                assert paper["id"] == 1
                assert paper["title"] == sample_paper_row["title"]
                assert paper["authors"] == sample_paper_row["authors"]
                mock_cursor.execute.assert_called()

    def test_get_paper_by_id_not_found(self, mock_connection, mock_cursor):
        """Test: Return None when paper not found."""
        # Setup: Configure mock to return None
        mock_cursor.fetchone.return_value = None

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Get non-existent paper
                paper = db.get_paper_by_id(99999)

                # Assert: None returned
                assert paper is None

    def test_get_all_papers(self, mock_connection, mock_cursor, sample_paper_row):
        """Test: Fetch all papers from database."""
        # Setup: Configure mock to return list of papers
        mock_cursor.fetchall.return_value = [sample_paper_row, sample_paper_row]

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Get all papers
                papers = db.get_all_papers()

                # Assert: All papers returned
                assert len(papers) == 2
                assert papers[0]["title"] == sample_paper_row["title"]


# =============================================================================
# Test: Update Paper
# =============================================================================


@pytest.mark.integration
class TestUpdatePaper:
    """Tests for updating papers in the database."""

    def test_update_paper(self, mock_connection, mock_cursor):
        """Test: Update paper fields in database."""
        # Setup: Configure mock to indicate update success
        mock_cursor.rowcount = 1

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Update paper fields
                result = db.update_paper(
                    paper_id=1,
                    title="Updated Title",
                    topics="RAG, Memory",
                    primary_topic="RAG",
                )

                # Assert: Update was successful
                assert result is True
                mock_connection.commit.assert_called()

    def test_update_paper_not_found(self, mock_connection, mock_cursor):
        """Test: Return False when updating non-existent paper."""
        # Setup: Configure mock to indicate no rows updated
        mock_cursor.rowcount = 0

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Try to update non-existent paper
                result = db.update_paper(paper_id=99999, title="New Title")

                # Assert: Update returned False (no rows affected)
                assert result is False

    def test_update_paper_no_valid_fields(self, mock_connection, mock_cursor):
        """Test: Return False when no valid fields provided."""
        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }

                from paper_db import PaperDB

                db = PaperDB()

                # Execute: Update with invalid field names
                result = db.update_paper(paper_id=1, invalid_field="value")

                # Assert: Returns False for no valid fields
                assert result is False


# =============================================================================
# Test: Vector Search
# =============================================================================


@pytest.mark.integration
class TestVectorSearch:
    """Tests for vector similarity search."""

    def test_vector_search_mock(self, mock_connection, mock_cursor, sample_paper_row):
        """Test: Vector search with mocked results."""
        # Setup: Add similarity score to sample paper
        search_result = sample_paper_row.copy()
        search_result["similarity"] = 0.85
        mock_cursor.fetchall.return_value = [search_result]

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }
                with patch("paper_db.generate_openai_embedding") as mock_embed:
                    mock_embed.return_value = [0.1] * 512

                    from paper_db import PaperDB

                    db = PaperDB()

                    # Execute: Perform vector search
                    results = db.vector_search(
                        query="retrieval augmented generation",
                        limit=5,
                    )

                    # Assert: Search results returned
                    assert len(results) == 1
                    assert results[0]["similarity"] == 0.85
                    assert results[0]["title"] == sample_paper_row["title"]
                    mock_embed.assert_called_once()

    def test_vector_search_with_threshold(
        self, mock_connection, mock_cursor, sample_paper_row
    ):
        """Test: Vector search with similarity threshold."""
        # Setup: Return papers with different similarity scores
        high_sim = sample_paper_row.copy()
        high_sim["similarity"] = 0.9

        low_sim = sample_paper_row.copy()
        low_sim["id"] = 2
        low_sim["similarity"] = 0.3

        mock_cursor.fetchall.return_value = [high_sim, low_sim]

        with patch("paper_db.psycopg2.connect", return_value=mock_connection):
            with patch("paper_db.load_db_config") as mock_config:
                mock_config.return_value = {
                    "database": {"url": "postgresql://test:test@localhost/test"}
                }
                with patch("paper_db.generate_openai_embedding") as mock_embed:
                    mock_embed.return_value = [0.1] * 512

                    from paper_db import PaperDB

                    db = PaperDB()

                    # Execute: Search with threshold
                    results = db.vector_search(
                        query="RAG",
                        limit=10,
                        threshold=0.5,
                    )

                    # Assert: Only high similarity result returned
                    assert len(results) == 1
                    assert results[0]["similarity"] == 0.9


# =============================================================================
# Test: Connection Pool Singleton
# =============================================================================


@pytest.mark.integration
class TestConnectionPoolSingleton:
    """Tests for connection pool singleton pattern."""

    def test_connection_pool_singleton(self):
        """Test: Verify ConnectionPool follows singleton pattern."""
        # Setup: Import ConnectionPool
        from paper_db import ConnectionPool

        # Execute: Create multiple instances
        pool1 = ConnectionPool()
        pool2 = ConnectionPool()

        # Assert: Both references point to same instance
        assert pool1 is pool2

    def test_connection_pool_thread_safety(self):
        """Test: Verify ConnectionPool is thread-safe."""
        from paper_db import ConnectionPool

        # Setup: List to store instances from different threads
        instances: List[ConnectionPool] = []
        errors: List[Exception] = []

        def get_pool():
            try:
                pool = ConnectionPool()
                instances.append(pool)
            except Exception as e:
                errors.append(e)

        # Execute: Create instances from multiple threads
        threads = [threading.Thread(target=get_pool) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: All instances are the same (singleton)
        assert len(errors) == 0
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)

    def test_get_connection_pool_returns_singleton(self):
        """Test: get_connection_pool returns singleton instance."""
        from paper_db import get_connection_pool

        # Execute: Get pool multiple times
        pool1 = get_connection_pool()
        pool2 = get_connection_pool()

        # Assert: Same instance returned
        assert pool1 is pool2
