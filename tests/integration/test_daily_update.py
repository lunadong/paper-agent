"""
Integration tests for paper_collection/daily_update.py

Tests the daily update workflow with mocked external dependencies.
"""

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_email_message() -> Dict[str, Any]:
    """Sample email message from Gmail."""
    return {
        "id": "msg123",
        "payload": {
            "headers": [
                {"name": "From", "value": "scholaralerts-noreply@google.com"},
                {"name": "Subject", "value": "Google Scholar Alert - RAG"},
                {"name": "Date", "value": "Mon, 15 Jan 2024 10:00:00 -0800"},
            ],
        },
    }


@pytest.fixture
def sample_parsed_papers():
    """Sample papers parsed from email HTML."""
    return [
        {
            "title": "RAG for NLP Tasks",
            "authors": "A. Author",
            "venue": "arXiv",
            "year": "2024",
            "snippet": "Paper about RAG...",
            "link": "https://arxiv.org/abs/2401.12345",
        },
        {
            "title": "Memory Networks",
            "authors": "B. Researcher",
            "venue": "NeurIPS",
            "year": "2024",
            "snippet": "Paper about memory...",
            "link": "https://arxiv.org/abs/2401.54321",
        },
    ]


# =============================================================================
# Test: Parse Email Date
# =============================================================================


@pytest.mark.integration
class TestParseEmailDate:
    """Tests for email date parsing."""

    def test_parse_email_date_standard_format(self):
        """Test: Convert standard email date format to YYYY-MM-DD."""
        from daily_update import parse_email_date

        # Execute: Parse standard email date
        result = parse_email_date("Mon, 15 Jan 2024 10:00:00 -0800")

        # Assert: Converted to YYYY-MM-DD format
        assert result == "2024-01-15"

    def test_parse_email_date_already_formatted(self):
        """Test: Return date as-is if already in YYYY-MM-DD format."""
        from daily_update import parse_email_date

        # Execute: Parse already formatted date
        result = parse_email_date("2024-01-15")

        # Assert: Same date returned
        assert result == "2024-01-15"

    def test_parse_email_date_na(self):
        """Test: Handle N/A date value."""
        from daily_update import parse_email_date

        # Execute: Parse N/A
        result = parse_email_date("N/A")

        # Assert: N/A returned unchanged
        assert result == "N/A"

    def test_parse_email_date_empty(self):
        """Test: Handle empty date string."""
        from daily_update import parse_email_date

        # Execute: Parse empty string
        result = parse_email_date("")

        # Assert: Empty string returned
        assert result == ""

    def test_parse_email_date_none(self):
        """Test: Handle None date value."""
        from daily_update import parse_email_date

        # Execute: Parse None
        result = parse_email_date(None)

        # Assert: None returned
        assert result is None

    def test_parse_email_date_various_months(self):
        """Test: Parse dates with various month abbreviations."""
        from daily_update import parse_email_date

        # Setup: Test cases for each month
        test_cases = [
            ("1 Jan 2024", "2024-01-01"),
            ("15 Feb 2024", "2024-02-15"),
            ("20 Mar 2024", "2024-03-20"),
            ("5 Apr 2024", "2024-04-05"),
            ("10 May 2024", "2024-05-10"),
            ("25 Jun 2024", "2024-06-25"),
            ("4 Jul 2024", "2024-07-04"),
            ("31 Aug 2024", "2024-08-31"),
            ("1 Sep 2024", "2024-09-01"),
            ("15 Oct 2024", "2024-10-15"),
            ("30 Nov 2024", "2024-11-30"),
            ("25 Dec 2024", "2024-12-25"),
        ]

        for input_date, expected in test_cases:
            # Execute & Assert
            result = parse_email_date(input_date)
            assert result == expected, f"Failed for {input_date}"

    def test_parse_email_date_unrecognized_format(self):
        """Test: Return original string for unrecognized format."""
        from daily_update import parse_email_date

        # Execute: Parse unrecognized format
        unrecognized = "Some Random String"
        result = parse_email_date(unrecognized)

        # Assert: Original string returned
        assert result == unrecognized


# =============================================================================
# Test: Parse Arguments - Defaults
# =============================================================================


@pytest.mark.integration
class TestParseArgsDefaults:
    """Tests for argument parsing with default values."""

    def test_parse_args_defaults(self):
        """Test: Default argument values are set correctly."""
        # Setup: Patch sys.argv to simulate no arguments
        with patch("sys.argv", ["daily_update.py"]):
            with patch("daily_update.init_config"):
                from daily_update import parse_args

                # Execute: Parse with no arguments
                args = parse_args()

                # Assert: Default values
                assert args.days == 1
                assert args.max_emails == 100
                assert args.dry_run is False
                assert args.no_email is False
                assert args.skip_topics is False
                assert args.workers == 1


# =============================================================================
# Test: Parse Arguments - Custom Values
# =============================================================================


@pytest.mark.integration
class TestParseArgsCustom:
    """Tests for argument parsing with custom values."""

    def test_parse_args_custom(self):
        """Test: Custom argument values are parsed correctly."""
        # Setup: Patch sys.argv with custom arguments
        with patch(
            "sys.argv",
            [
                "daily_update.py",
                "--days",
                "7",
                "--max-emails",
                "50",
                "--dry-run",
                "--no-email",
                "--skip-topics",
                "--workers",
                "4",
            ],
        ):
            with patch("daily_update.init_config"):
                from daily_update import parse_args

                # Execute: Parse with custom arguments
                args = parse_args()

                # Assert: Custom values
                assert args.days == 7
                assert args.max_emails == 50
                assert args.dry_run is True
                assert args.no_email is True
                assert args.skip_topics is True
                assert args.workers == 4

    def test_parse_args_days_only(self):
        """Test: Parse only days argument."""
        with patch("sys.argv", ["daily_update.py", "--days", "14"]):
            with patch("daily_update.init_config"):
                from daily_update import parse_args

                args = parse_args()

                assert args.days == 14
                assert args.dry_run is False

    def test_parse_args_workers(self):
        """Test: Parse workers argument for parallel processing."""
        with patch("sys.argv", ["daily_update.py", "--workers", "8"]):
            with patch("daily_update.init_config"):
                from daily_update import parse_args

                args = parse_args()

                assert args.workers == 8


# =============================================================================
# Test: Log Function
# =============================================================================


@pytest.mark.integration
class TestLogFunction:
    """Tests for the log function."""

    def test_log_outputs_with_timestamp(self, capsys):
        """Test: Log function outputs message with timestamp."""
        from daily_update import log

        # Execute: Log a message
        log("Test message")

        # Assert: Output contains timestamp and message
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "[" in captured.out  # Timestamp brackets
        assert "]" in captured.out


# =============================================================================
# Test: Main Workflow (Integration)
# =============================================================================


@pytest.mark.integration
class TestMainWorkflow:
    """Tests for the main daily update workflow."""

    def test_main_dry_run_no_changes(
        self, sample_email_message, sample_parsed_papers, capsys
    ):
        """Test: Dry run mode doesn't save to database."""
        # Setup: Mock all external dependencies
        with patch("sys.argv", ["daily_update.py", "--dry-run", "--days", "1"]):
            with patch("daily_update.init_config") as mock_init_config:
                mock_config = MagicMock()
                mock_config.notification_email = None
                mock_init_config.return_value = mock_config

                with patch("daily_update.get_gmail_service") as mock_gmail:
                    mock_service = MagicMock()
                    mock_gmail.return_value = mock_service

                    with patch("daily_update.list_messages") as mock_list:
                        mock_list.return_value = [{"id": "msg1"}]

                        with patch("daily_update.get_message") as mock_get_msg:
                            mock_get_msg.return_value = sample_email_message

                            with patch(
                                "daily_update.get_message_headers"
                            ) as mock_headers:
                                mock_headers.return_value = {
                                    "date": "Mon, 15 Jan 2024 10:00:00"
                                }

                                with patch("daily_update.get_raw_html") as mock_html:
                                    mock_html.return_value = "<html>test</html>"

                                    with patch(
                                        "daily_update.parse_scholar_papers"
                                    ) as mock_parse:
                                        mock_parse.return_value = sample_parsed_papers

                                        with patch(
                                            "daily_update.PaperDB"
                                        ) as mock_db_class:
                                            from daily_update import main

                                            # Execute: Run main in dry-run mode
                                            main()

                                            # Assert: PaperDB was never instantiated (dry run)
                                            mock_db_class.assert_not_called()

                                            # Assert: Output indicates dry run
                                            captured = capsys.readouterr()
                                            assert "DRY RUN" in captured.out

    def test_main_no_emails_found(self, capsys):
        """Test: Handle case when no emails found."""
        with patch("sys.argv", ["daily_update.py", "--days", "1"]):
            with patch("daily_update.init_config") as mock_init_config:
                mock_config = MagicMock()
                mock_init_config.return_value = mock_config

                with patch("daily_update.get_gmail_service") as mock_gmail:
                    mock_service = MagicMock()
                    mock_gmail.return_value = mock_service

                    with patch("daily_update.list_messages") as mock_list:
                        mock_list.return_value = []

                        from daily_update import main

                        # Execute: Run main with no emails
                        main()

                        # Assert: Output indicates no emails
                        captured = capsys.readouterr()
                        assert "No emails found" in captured.out

    def test_main_gmail_credentials_missing(self, capsys):
        """Test: Handle missing Gmail credentials gracefully."""
        with patch("sys.argv", ["daily_update.py", "--days", "1"]):
            with patch("daily_update.init_config") as mock_init_config:
                mock_config = MagicMock()
                mock_init_config.return_value = mock_config

                with patch("daily_update.get_gmail_service") as mock_gmail:
                    mock_gmail.side_effect = FileNotFoundError(
                        "Credentials file not found"
                    )

                    from daily_update import main

                    # Execute: Run main with missing credentials
                    main()

                    # Assert: Error message displayed
                    captured = capsys.readouterr()
                    assert "ERROR" in captured.out or "Credentials" in captured.out
