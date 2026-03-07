"""
Integration tests for paper_collection/paper_discovery/gmail_client.py

Tests the Gmail client with mocked Gmail API.
"""

import base64
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "paper_collection"))


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_credentials():
    """Create mock OAuth credentials."""
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "refresh_token"
    creds.to_json.return_value = '{"token": "test_token"}'
    return creds


@pytest.fixture
def mock_gmail_service():
    """Create mock Gmail API service."""
    service = MagicMock()

    # Mock messages list
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg123"}, {"id": "msg456"}],
        "nextPageToken": None,
    }

    # Mock message get
    service.users().messages().get().execute.return_value = {
        "id": "msg123",
        "payload": {
            "headers": [
                {"name": "From", "value": "scholaralerts-noreply@google.com"},
                {"name": "Subject", "value": "Google Scholar Alert"},
                {"name": "Date", "value": "Mon, 15 Jan 2024 10:00:00 -0800"},
                {"name": "To", "value": "user@example.com"},
            ],
            "body": {"data": ""},
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"<html><body>Test content</body></html>"
                        ).decode()
                    },
                }
            ],
        },
    }

    return service


@pytest.fixture
def sample_multipart_message() -> Dict[str, Any]:
    """Sample multipart email message."""
    plain_content = "Plain text content"
    html_content = "<html><body><h1>Title</h1><p>HTML content</p></body></html>"

    return {
        "id": "msg789",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test Subject"},
                {"name": "Date", "value": "Tue, 16 Jan 2024 15:30:00 +0000"},
                {"name": "To", "value": "recipient@example.com"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            plain_content.encode()
                        ).decode()
                    },
                },
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": base64.urlsafe_b64encode(html_content.encode()).decode()
                    },
                },
            ],
        },
    }


# =============================================================================
# Test: Gmail Service Authentication
# =============================================================================


@pytest.mark.integration
class TestGmailServiceAuth:
    """Tests for Gmail API authentication."""

    def test_get_gmail_service_with_token(self, mock_credentials, tmp_path):
        """Test: Load Gmail service from existing token file."""
        # Setup: Create mock token file
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "test"}')

        with patch(
            "paper_discovery.gmail_client.Credentials.from_authorized_user_file"
        ) as mock_creds_load:
            mock_creds_load.return_value = mock_credentials
            with patch("paper_discovery.gmail_client.build") as mock_build:
                mock_build.return_value = MagicMock()

                from paper_discovery.gmail_client import get_gmail_service

                # Execute: Get Gmail service with existing token
                service = get_gmail_service(
                    credentials_file=str(tmp_path / "credentials.json"),
                    token_file=str(token_file),
                )

                # Assert: Service was created from existing token
                assert service is not None
                mock_creds_load.assert_called_once()
                mock_build.assert_called_once_with(
                    "gmail", "v1", credentials=mock_credentials
                )

    def test_get_gmail_service_with_expired_token(self, mock_credentials, tmp_path):
        """Test: Refresh expired token automatically."""
        # Setup: Create mock expired credentials
        mock_credentials.valid = False
        mock_credentials.expired = True

        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "expired"}')

        with patch(
            "paper_discovery.gmail_client.Credentials.from_authorized_user_file"
        ) as mock_creds_load:
            mock_creds_load.return_value = mock_credentials
            with patch("paper_discovery.gmail_client.Request"):
                with patch("paper_discovery.gmail_client.build") as mock_build:
                    mock_build.return_value = MagicMock()

                    from paper_discovery.gmail_client import get_gmail_service

                    # Execute: Get service with expired token
                    service = get_gmail_service(
                        credentials_file=str(tmp_path / "credentials.json"),
                        token_file=str(token_file),
                    )

                    # Assert: Credentials were refreshed
                    assert service is not None
                    mock_credentials.refresh.assert_called_once()


# =============================================================================
# Test: List Messages
# =============================================================================


@pytest.mark.integration
class TestListMessages:
    """Tests for listing Gmail messages."""

    def test_list_messages(self, mock_gmail_service):
        """Test: List messages with mock service."""
        from paper_discovery.gmail_client import list_messages

        # Execute: List messages
        messages = list_messages(
            mock_gmail_service,
            max_results=10,
            query="from:scholaralerts-noreply@google.com",
        )

        # Assert: Messages returned correctly
        assert len(messages) == 2
        assert messages[0]["id"] == "msg123"
        assert messages[1]["id"] == "msg456"

    def test_list_messages_empty(self, mock_gmail_service):
        """Test: Handle empty message list."""
        # Setup: Configure mock to return no messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": []
        }

        from paper_discovery.gmail_client import list_messages

        # Execute: List messages
        messages = list_messages(mock_gmail_service, max_results=10)

        # Assert: Empty list returned
        assert len(messages) == 0

    def test_list_messages_with_pagination(self, mock_gmail_service):
        """Test: Handle paginated results."""
        # Setup: Configure mock to return multiple pages
        page1_response = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "token123",
        }
        page2_response = {
            "messages": [{"id": "msg3"}],
            "nextPageToken": None,
        }
        mock_gmail_service.users().messages().list().execute.side_effect = [
            page1_response,
            page2_response,
        ]

        from paper_discovery.gmail_client import list_messages

        # Execute: List messages with max_results larger than first page
        messages = list_messages(mock_gmail_service, max_results=5)

        # Assert: All messages from both pages returned
        assert len(messages) == 3
        assert messages[0]["id"] == "msg1"
        assert messages[2]["id"] == "msg3"


# =============================================================================
# Test: Get Message
# =============================================================================


@pytest.mark.integration
class TestGetMessage:
    """Tests for retrieving individual messages."""

    def test_get_message_success(self, mock_gmail_service):
        """Test: Retrieve email content successfully."""
        from paper_discovery.gmail_client import get_message

        # Execute: Get message by ID
        message = get_message(mock_gmail_service, "msg123")

        # Assert: Message retrieved successfully
        assert message is not None
        assert message["id"] == "msg123"
        assert "payload" in message

    def test_get_message_not_found(self, mock_gmail_service):
        """Test: Handle message not found."""
        from googleapiclient.errors import HttpError

        # Setup: Configure mock to raise 404 error
        resp = MagicMock()
        resp.status = 404
        mock_gmail_service.users().messages().get().execute.side_effect = HttpError(
            resp=resp, content=b"Not Found"
        )

        from paper_discovery.gmail_client import get_message

        # Execute: Try to get non-existent message
        message = get_message(mock_gmail_service, "nonexistent")

        # Assert: None returned for not found
        assert message is None

    def test_get_message_retry_on_transient_error(self, mock_gmail_service):
        """Test: Retry on transient HTTP errors (5xx, 429)."""
        from googleapiclient.errors import HttpError

        # Setup: Configure mock to fail twice then succeed
        resp = MagicMock()
        resp.status = 503

        mock_gmail_service.users().messages().get().execute.side_effect = [
            HttpError(resp=resp, content=b"Service Unavailable"),
            {"id": "msg123", "payload": {}},
        ]

        with patch("paper_discovery.gmail_client.time.sleep"):  # Skip actual sleep
            from paper_discovery.gmail_client import get_message

            # Execute: Get message with retry
            message = get_message(mock_gmail_service, "msg123")

            # Assert: Message retrieved after retry
            assert message is not None
            assert message["id"] == "msg123"


# =============================================================================
# Test: Get Raw HTML
# =============================================================================


@pytest.mark.integration
class TestGetRawHtml:
    """Tests for extracting HTML content from messages."""

    def test_get_raw_html(self, sample_multipart_message):
        """Test: Extract HTML from multipart message."""
        from paper_discovery.gmail_client import get_raw_html

        # Execute: Extract HTML
        html = get_raw_html(sample_multipart_message)

        # Assert: HTML content extracted
        assert html is not None
        assert "<html>" in html
        assert "<h1>Title</h1>" in html

    def test_get_raw_html_simple_body(self):
        """Test: Extract HTML from simple message body."""
        # Setup: Message with direct body data
        html_content = "<html><body>Simple content</body></html>"
        message = {
            "payload": {
                "body": {
                    "data": base64.urlsafe_b64encode(html_content.encode()).decode()
                }
            }
        }

        from paper_discovery.gmail_client import get_raw_html

        # Execute: Extract HTML
        html = get_raw_html(message)

        # Assert: HTML content extracted from simple body
        assert html == html_content

    def test_get_raw_html_no_html_part(self):
        """Test: Return empty string when no HTML part."""
        # Setup: Message with only plain text
        message = {
            "payload": {
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "data": base64.urlsafe_b64encode(b"Plain text").decode()
                        },
                    }
                ]
            }
        }

        from paper_discovery.gmail_client import get_raw_html

        # Execute: Try to extract HTML
        html = get_raw_html(message)

        # Assert: Empty string returned
        assert html == ""


# =============================================================================
# Test: Get Message Headers
# =============================================================================


@pytest.mark.integration
class TestGetMessageHeaders:
    """Tests for extracting message headers."""

    def test_get_message_headers(self, sample_multipart_message):
        """Test: Extract common headers from message."""
        from paper_discovery.gmail_client import get_message_headers

        # Execute: Extract headers
        headers = get_message_headers(sample_multipart_message)

        # Assert: Common headers extracted
        assert "from" in headers
        assert headers["from"] == "sender@example.com"
        assert "subject" in headers
        assert headers["subject"] == "Test Subject"
        assert "date" in headers
        assert "to" in headers

    def test_get_message_headers_missing_headers(self):
        """Test: Handle missing headers gracefully."""
        # Setup: Message with minimal headers
        message = {
            "payload": {
                "headers": [{"name": "From", "value": "test@example.com"}],
            }
        }

        from paper_discovery.gmail_client import get_message_headers

        # Execute: Extract headers
        headers = get_message_headers(message)

        # Assert: Only present header returned
        assert "from" in headers
        assert "subject" not in headers
        assert "date" not in headers


# =============================================================================
# Test: Strip HTML
# =============================================================================


@pytest.mark.integration
class TestStripHtml:
    """Tests for HTML to plain text conversion."""

    def test_strip_html(self):
        """Test: Convert HTML to plain text."""
        from paper_discovery.gmail_client import strip_html

        # Setup: HTML content with various elements
        html = """
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
        <h1>Title</h1>
        <p>First paragraph.</p>
        <p>Second paragraph with <strong>bold</strong> text.</p>
        <br>
        <div>A div element</div>
        </body>
        </html>
        """

        # Execute: Strip HTML
        text = strip_html(html)

        # Assert: Plain text extracted correctly
        assert "Title" in text
        assert "First paragraph" in text
        assert "bold" in text
        assert "<html>" not in text
        assert "<p>" not in text
        assert "color: red" not in text  # Style content removed

    def test_strip_html_entities(self):
        """Test: Decode HTML entities."""
        from paper_discovery.gmail_client import strip_html

        # Setup: HTML with entities
        html = "<p>Tom &amp; Jerry &lt;3 &gt; 2</p>"

        # Execute: Strip HTML
        text = strip_html(html)

        # Assert: Entities decoded
        assert "Tom & Jerry" in text
        assert "<3" in text
        assert "> 2" in text

    def test_strip_html_script_tags(self):
        """Test: Remove script tag content."""
        from paper_discovery.gmail_client import strip_html

        # Setup: HTML with script tag
        html = """
        <p>Visible text</p>
        <script>alert('hidden');</script>
        <p>More visible text</p>
        """

        # Execute: Strip HTML
        text = strip_html(html)

        # Assert: Script content removed
        assert "Visible text" in text
        assert "More visible text" in text
        assert "alert" not in text
        assert "hidden" not in text

    def test_strip_html_preserves_newlines(self):
        """Test: BR and closing tags create newlines."""
        from paper_discovery.gmail_client import strip_html

        # Setup: HTML with line breaks
        html = "<p>Line 1</p><br><p>Line 2</p>"

        # Execute: Strip HTML
        text = strip_html(html)

        # Assert: Newlines preserved
        assert "Line 1" in text
        assert "Line 2" in text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        assert len(lines) >= 2
