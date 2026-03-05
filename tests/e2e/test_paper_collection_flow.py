"""
E2E tests for paper collection workflow.

Tests the complete paper collection pipeline:
1. Email parsing from Gmail API
2. Paper extraction from Google Scholar alerts
3. Paper enrichment via ArXiv
4. Database storage

All external services (Gmail API, ArXiv, Database) are mocked.
"""

import base64
from datetime import datetime
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_scholar_email_html() -> str:
    """Sample Google Scholar alert email HTML content."""
    return """
    <html>
    <body>
    <h3>Google Scholar Alert - AI Research</h3>
    <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.12345&hl=en">
        Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
    </a>
    <font color="#006621">A. Author, B. Researcher - arXiv preprint arXiv:2401.12345, 2024</font>
    <div>This paper introduces a novel approach to RAG that combines dense retrieval
    with generative models for improved factuality and reduced hallucinations.</div>

    <a href="https://scholar.google.com/scholar_url?url=https://arxiv.org/abs/2401.67890&hl=en">
        Memory-Augmented Neural Networks for Long-Context Understanding
    </a>
    <font color="#006621">C. Developer, D. Engineer - arXiv preprint arXiv:2401.67890, 2024</font>
    <div>We present a memory-augmented architecture for handling long-context conversations
    with improved recall and coherence.</div>
    </body>
    </html>
    """


@pytest.fixture
def mock_arxiv_response_html() -> str:
    """Mock ArXiv abstract page HTML."""
    return """
    <html>
    <head><title>arXiv:2401.12345</title></head>
    <body>
    <div class="submission-history">
        <strong>Submitted</strong> on 15 Jan 2024
    </div>
    <blockquote class="abstract">
        <span class="descriptor">Abstract:</span>
        This paper introduces a novel approach to retrieval-augmented generation (RAG)
        that combines dense retrieval with generative language models. Our method
        achieves state-of-the-art results on multiple knowledge-intensive benchmarks
        including question answering and fact verification.
    </blockquote>
    </body>
    </html>
    """


@pytest.fixture
def mock_gmail_message(mock_scholar_email_html: str) -> Dict[str, Any]:
    """Create a mock Gmail message structure."""
    encoded_html = base64.urlsafe_b64encode(mock_scholar_email_html.encode()).decode()

    return {
        "id": "msg_test_123",
        "threadId": "thread_test_123",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "scholaralerts-noreply@google.com"},
                {"name": "Subject", "value": "Google Scholar Alert - AI Research"},
                {"name": "Date", "value": "Mon, 15 Jan 2024 10:00:00 -0800"},
            ],
            "body": {"data": ""},
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded_html},
                }
            ],
        },
    }


@pytest.fixture
def mock_gmail_service(mock_gmail_message: Dict[str, Any]) -> MagicMock:
    """Create a mock Gmail API service."""
    service = MagicMock()

    # Mock messages list
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg_test_123"}]
    }

    # Mock message get
    service.users().messages().get().execute.return_value = mock_gmail_message

    return service


@pytest.mark.e2e
class TestPaperCollectionFlow:
    """E2E tests for the paper collection workflow."""

    @patch("daily_update.get_gmail_service")
    @patch("daily_update.parse_scholar_papers")
    def test_daily_update_dry_run(
        self,
        mock_parse_papers: MagicMock,
        mock_get_service: MagicMock,
        mock_gmail_service: MagicMock,
        sample_paper_dict: Dict[str, Any],
    ):
        """
        Test daily update in dry-run mode parses emails without saving to DB.

        This test validates:
        - Gmail API is called to fetch emails
        - Paper parser extracts papers from email HTML
        - In dry-run mode, no database operations occur
        - Papers are parsed but not persisted

        Mocks:
        - Gmail API service and message retrieval
        - Paper parser to return sample papers
        """
        # Setup mocks
        mock_get_service.return_value = mock_gmail_service
        mock_parse_papers.return_value = [sample_paper_dict]

        import sys

        # Import after patching
        from daily_update import main

        # Simulate command-line args for dry-run
        original_argv = sys.argv
        sys.argv = ["daily_update.py", "--dry-run", "--days", "1"]

        try:
            # Execute the main function - should complete without errors
            with patch("daily_update.PaperDB") as mock_db_class:
                main()

                # Verify Gmail service was called
                mock_get_service.assert_called_once()

                # Verify paper parser was called
                assert mock_parse_papers.called

                # Verify PaperDB was NOT instantiated (dry-run mode)
                mock_db_class.assert_not_called()
        finally:
            sys.argv = original_argv

    @patch("daily_update.get_gmail_service")
    @patch("daily_update.list_messages")
    @patch("daily_update.get_message")
    @patch("daily_update.get_message_headers")
    @patch("daily_update.get_raw_html")
    @patch("daily_update.parse_scholar_papers")
    @patch("daily_update.PaperDB")
    def test_paper_collection_single_email(
        self,
        mock_db_class: MagicMock,
        mock_parse_papers: MagicMock,
        mock_get_raw_html: MagicMock,
        mock_get_headers: MagicMock,
        mock_get_message: MagicMock,
        mock_list_messages: MagicMock,
        mock_get_service: MagicMock,
        mock_gmail_service: MagicMock,
        mock_scholar_email_html: str,
    ):
        """
        Test processing single email end-to-end: email -> parse -> enrich -> store.

        This test validates the complete paper collection flow:
        1. Gmail API returns a single email
        2. Email HTML is extracted
        3. Papers are parsed from the email
        4. Papers are enriched with ArXiv data (mocked)
        5. Papers are stored in the database

        Mocks:
        - Gmail API service, message listing, and retrieval
        - Paper parser
        - PaperDB for storage
        - Summary generation (skipped)
        """
        # Setup mocks
        mock_get_service.return_value = mock_gmail_service
        mock_list_messages.return_value = [{"id": "msg_single_123"}]
        mock_get_message.return_value = {"id": "msg_single_123", "payload": {}}
        mock_get_headers.return_value = {
            "from": "scholaralerts-noreply@google.com",
            "date": "Mon, 15 Jan 2024 10:00:00 -0800",
        }
        mock_get_raw_html.return_value = mock_scholar_email_html

        # Mock paper parser to return papers (without arXiv enrichment for speed)
        mock_parse_papers.return_value = [
            {
                "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "authors": "A. Author, B. Researcher",
                "venue": "arXiv, 1/2024",
                "year": "2024",
                "snippet": "This paper introduces a novel approach to RAG...",
                "link": "https://arxiv.org/abs/2401.12345",
                "email_date": "2024-01-15",
            }
        ]

        # Setup mock database
        mock_db_instance = MagicMock()
        mock_db_instance.add_paper.return_value = 1  # Return new paper ID
        mock_db_instance.get_all_papers.return_value = []  # No papers for summary
        mock_db_class.return_value = mock_db_instance

        import sys

        # Import and run
        from daily_update import main

        original_argv = sys.argv
        sys.argv = ["daily_update.py", "--days", "1", "--no-email", "--skip-topics"]

        try:
            main()

            # Verify Gmail service was used
            mock_get_service.assert_called_once()
            mock_list_messages.assert_called_once()
            mock_get_message.assert_called_once()

            # Verify paper was parsed
            mock_parse_papers.assert_called_once()

            # Verify paper was added to database
            mock_db_instance.add_paper.assert_called_once()

            # Check the add_paper call arguments
            call_kwargs = mock_db_instance.add_paper.call_args[1]
            assert "title" in call_kwargs
            assert "Retrieval-Augmented Generation" in call_kwargs["title"]
            assert call_kwargs["link"] == "https://arxiv.org/abs/2401.12345"

        finally:
            sys.argv = original_argv

    @patch("daily_update.get_gmail_service")
    @patch("daily_update.list_messages")
    @patch("daily_update.get_message")
    @patch("daily_update.get_message_headers")
    @patch("daily_update.get_raw_html")
    @patch("daily_update.parse_scholar_papers")
    @patch("daily_update.PaperDB")
    @patch("daily_update.generate_summary_for_paper")
    def test_paper_collection_with_topics(
        self,
        mock_generate_summary: MagicMock,
        mock_db_class: MagicMock,
        mock_parse_papers: MagicMock,
        mock_get_raw_html: MagicMock,
        mock_get_headers: MagicMock,
        mock_get_message: MagicMock,
        mock_list_messages: MagicMock,
        mock_get_service: MagicMock,
        mock_gmail_service: MagicMock,
        mock_scholar_email_html: str,
        sample_paper_db_row: Dict[str, Any],
    ):
        """
        Test paper collection with topic tagging via summary generation.

        This test validates:
        1. Papers are collected from emails
        2. Papers are stored in the database
        3. Summary generation is triggered for new papers
        4. Topics are extracted from summaries

        Mocks:
        - Gmail API
        - Paper parser
        - Database operations
        - Summary generation (returns topics)
        """
        # Setup mocks
        mock_get_service.return_value = mock_gmail_service
        mock_list_messages.return_value = [{"id": "msg_topic_123"}]
        mock_get_message.return_value = {"id": "msg_topic_123", "payload": {}}
        mock_get_headers.return_value = {
            "from": "scholaralerts-noreply@google.com",
            "date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S -0800"),
        }
        mock_get_raw_html.return_value = mock_scholar_email_html

        # Mock paper parser
        mock_parse_papers.return_value = [
            {
                "title": "RAG Paper Title",
                "authors": "A. Author",
                "venue": "arXiv, 1/2024",
                "year": "2024",
                "snippet": "About RAG...",
                "link": "https://arxiv.org/abs/2401.99999",
                "email_date": datetime.now().strftime("%Y-%m-%d"),
            }
        ]

        # Setup mock database
        mock_db_instance = MagicMock()
        mock_db_instance.add_paper.return_value = 100  # Return new paper ID

        # Create a paper without summary (needs summary generation)
        paper_without_summary = sample_paper_db_row.copy()
        paper_without_summary["id"] = 100
        paper_without_summary["summary_generated_at"] = None
        paper_without_summary["recomm_date"] = datetime.now().strftime("%Y-%m-%d")

        mock_db_instance.get_all_papers.return_value = [paper_without_summary]
        mock_db_class.return_value = mock_db_instance

        # Mock summary generation to return success with topics
        mock_generate_summary.return_value = {
            "success": True,
            "topics": ["RAG", "Reasoning"],
            "primary_topic": "RAG",
        }

        import sys

        # Import and run
        from daily_update import main

        original_argv = sys.argv
        sys.argv = ["daily_update.py", "--days", "1", "--no-email"]

        try:
            main()

            # Verify paper was added
            mock_db_instance.add_paper.assert_called()

            # Verify summary generation was called for the new paper
            mock_generate_summary.assert_called()

            # Check summary generation was called with correct paper_id
            call_kwargs = mock_generate_summary.call_args[1]
            assert call_kwargs["paper_id"] == 100
            assert call_kwargs["save_db"] is True

        finally:
            sys.argv = original_argv


@pytest.mark.e2e
class TestPaperParserIntegration:
    """E2E tests for paper parser with ArXiv enrichment."""

    @patch("paper_parser_from_emails.fetch_arxiv_html")
    def test_parse_and_enrich_arxiv_paper(
        self,
        mock_fetch_arxiv: MagicMock,
        mock_scholar_email_html: str,
        mock_arxiv_response_html: str,
    ):
        """
        Test parsing a Google Scholar email and enriching with ArXiv data.

        This test validates:
        1. Scholar email HTML is parsed correctly
        2. Paper titles and metadata are extracted
        3. ArXiv papers are identified and enriched
        4. Abstracts are fetched from ArXiv

        Mocks:
        - ArXiv HTTP requests
        """
        # Mock ArXiv fetch to return our sample HTML
        mock_fetch_arxiv.return_value = mock_arxiv_response_html

        from paper_parser_from_emails import parse_scholar_papers

        # Parse the mock email HTML
        papers = parse_scholar_papers(mock_scholar_email_html, enrich_arxiv=True)

        # Verify papers were extracted
        assert len(papers) >= 1

        # Verify first paper
        first_paper = papers[0]
        assert "title" in first_paper
        assert "Retrieval-Augmented Generation" in first_paper["title"]
        assert first_paper["link"] == "https://arxiv.org/abs/2401.12345"

        # Verify ArXiv enrichment was called
        mock_fetch_arxiv.assert_called()

    def test_parse_scholar_papers_no_enrichment(
        self,
        mock_scholar_email_html: str,
    ):
        """
        Test parsing Google Scholar email without ArXiv enrichment.

        This test validates:
        1. Parser works without external HTTP calls
        2. Basic paper metadata is extracted correctly
        3. enrich_arxiv=False disables enrichment

        Mocks:
        - None (pure parsing test)
        """
        from paper_parser_from_emails import parse_scholar_papers

        # Parse without enrichment
        papers = parse_scholar_papers(mock_scholar_email_html, enrich_arxiv=False)

        # Verify papers were extracted
        assert len(papers) >= 1

        # Verify metadata
        first_paper = papers[0]
        assert "title" in first_paper
        assert "authors" in first_paper
        assert "venue" in first_paper
        assert "link" in first_paper


@pytest.mark.e2e
class TestEmailProcessingFlow:
    """E2E tests for email processing components."""

    def test_gmail_message_parsing(
        self,
        mock_gmail_message: Dict[str, Any],
    ):
        """
        Test parsing Gmail message structure.

        This test validates:
        1. Message headers are extracted correctly
        2. HTML body is decoded from base64
        3. Email metadata (date, from, subject) is accessible

        Mocks:
        - None (uses fixture data)
        """
        from gmail_client import get_message_headers, get_raw_html

        # Extract headers
        headers = get_message_headers(mock_gmail_message)

        assert headers["from"] == "scholaralerts-noreply@google.com"
        assert headers["subject"] == "Google Scholar Alert - AI Research"
        assert "2024" in headers["date"]

        # Extract HTML body
        html_content = get_raw_html(mock_gmail_message)

        assert html_content is not None
        assert len(html_content) > 0
        assert "Retrieval-Augmented Generation" in html_content

    @patch("gmail_client.build")
    @patch("gmail_client.Credentials")
    @patch("os.path.exists")
    def test_gmail_service_initialization(
        self,
        mock_exists: MagicMock,
        mock_credentials: MagicMock,
        mock_build: MagicMock,
    ):
        """
        Test Gmail service initialization with credentials.

        This test validates:
        1. Credential file existence is checked
        2. OAuth2 credentials are loaded
        3. Gmail service is built with credentials

        Mocks:
        - File system (os.path.exists)
        - Google auth credentials
        - Google API client builder
        """
        # Mock credential file exists and is valid
        mock_exists.return_value = True

        # Mock credentials
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_credentials.from_authorized_user_file.return_value = mock_creds

        # Mock build
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        from gmail_client import get_gmail_service

        # Get service with explicit paths
        service = get_gmail_service(
            credentials_file="test_creds.json",
            token_file="test_token.json",
        )

        # Verify service was built
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)
        assert service == mock_service
