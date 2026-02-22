"""
Unit tests for LLM client module.

Tests the LLM client at paper_collection/paper_summary/util/llm_client.py
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


class TestGetApiKey:
    """Tests for get_api_key function."""

    def test_get_api_key_from_env(self) -> None:
        """Test reading API key from GEMINI_API_KEY environment variable."""
        # Setup: Set the environment variable
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-from-env"}):
            # Mock config to return empty
            with patch(
                "paper_collection.paper_summary.util.llm_client.get_config_value"
            ) as mock_config:
                mock_config.return_value = "test-key-from-env"

                # Execute
                from paper_collection.paper_summary.util.llm_client import get_api_key

                result = get_api_key()

                # Assert: Key should be from env
                assert result == "test-key-from-env"

    def test_get_api_key_from_parameter(self) -> None:
        """Test that passing API key directly takes precedence."""
        # Setup & Execute
        from paper_collection.paper_summary.util.llm_client import get_api_key

        result = get_api_key(api_key="direct-api-key")

        # Assert: Direct parameter should be returned
        assert result == "direct-api-key"

    def test_get_api_key_missing(self) -> None:
        """Test that ValueError is raised if API key is not found."""
        # Setup: Mock config_value to return empty string
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = ""

            # Execute & Assert: Should raise ValueError
            from paper_collection.paper_summary.util.llm_client import get_api_key

            with pytest.raises(ValueError, match="API key not found"):
                get_api_key(api_key=None)


class TestGetApiUrl:
    """Tests for get_api_url function."""

    def test_get_api_url(self) -> None:
        """Test getting API endpoint URL from config."""
        # Setup
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = "https://api.test.com/endpoint"

            # Execute
            from paper_collection.paper_summary.util.llm_client import get_api_url

            result = get_api_url()

            # Assert
            assert result == "https://api.test.com/endpoint"
            mock_config.assert_called_once_with("api_url")

    def test_get_api_url_missing(self) -> None:
        """Test that ValueError is raised if API URL is not configured."""
        # Setup
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = None

            # Execute & Assert
            from paper_collection.paper_summary.util.llm_client import get_api_url

            with pytest.raises(ValueError, match="API URL not found"):
                get_api_url()


class TestGetDefaultModel:
    """Tests for get_default_model function."""

    def test_get_default_model(self) -> None:
        """Test that default model returns expected model name."""
        # Setup
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = "gemini-2.0-flash"

            # Execute
            from paper_collection.paper_summary.util.llm_client import get_default_model

            result = get_default_model()

            # Assert: Should return gemini-2.0-flash or similar
            assert "gemini" in result.lower()
            mock_config.assert_called_once_with("model")

    def test_get_default_model_missing(self) -> None:
        """Test that ValueError is raised if model is not configured."""
        # Setup
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = None

            # Execute & Assert
            from paper_collection.paper_summary.util.llm_client import get_default_model

            with pytest.raises(ValueError, match="Model not found"):
                get_default_model()


class TestGetLightweightModel:
    """Tests for get_lightweight_model function."""

    def test_get_lightweight_model(self) -> None:
        """Test that lightweight model returns expected model name."""
        # Setup
        with patch(
            "paper_collection.paper_summary.util.llm_client.get_config_value"
        ) as mock_config:
            mock_config.return_value = "gemini-2.0-flash-lite"

            # Execute
            from paper_collection.paper_summary.util.llm_client import (
                get_lightweight_model,
            )

            result = get_lightweight_model()

            # Assert: Should return lightweight model name
            assert "lite" in result.lower() or "flash" in result.lower()
            mock_config.assert_called_once_with("lightweight_model")


class TestCallGeminiApi:
    """Tests for call_gemini_api function."""

    @patch("paper_collection.paper_summary.util.llm_client.get_rate_limiter")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_url")
    @patch("paper_collection.paper_summary.util.llm_client.get_default_model")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_key")
    @patch("paper_collection.paper_summary.util.llm_client.requests.post")
    def test_call_gemini_api_success(
        self,
        mock_post: MagicMock,
        mock_get_key: MagicMock,
        mock_get_model: MagicMock,
        mock_get_url: MagicMock,
        mock_rate_limiter: MagicMock,
    ) -> None:
        """Test successful API call returns response text."""
        # Setup
        mock_rate_limiter.return_value = MagicMock()
        mock_get_key.return_value = "test-api-key"
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_get_url.return_value = "https://api.test.com/endpoint"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "Test response from Gemini"}
        mock_post.return_value = mock_response

        # Execute
        from paper_collection.paper_summary.util.llm_client import call_gemini_api

        result = call_gemini_api("Test prompt")

        # Assert: Should return the result
        assert result == "Test response from Gemini"
        mock_post.assert_called_once()

    @patch("paper_collection.paper_summary.util.llm_client.time.sleep")
    @patch("paper_collection.paper_summary.util.llm_client.get_rate_limiter")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_url")
    @patch("paper_collection.paper_summary.util.llm_client.get_default_model")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_key")
    @patch("paper_collection.paper_summary.util.llm_client.requests.post")
    def test_call_gemini_api_retry_on_429(
        self,
        mock_post: MagicMock,
        mock_get_key: MagicMock,
        mock_get_model: MagicMock,
        mock_get_url: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Test that 429 rate limit errors trigger retry."""
        # Setup
        mock_rate_limiter.return_value = MagicMock()
        mock_get_key.return_value = "test-api-key"
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_get_url.return_value = "https://api.test.com/endpoint"

        # First call returns 429, second returns 200
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = "Rate limit exceeded"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"result": "Success after retry"}

        mock_post.side_effect = [rate_limit_response, success_response]

        # Execute
        from paper_collection.paper_summary.util.llm_client import call_gemini_api

        result = call_gemini_api("Test prompt", max_retries=3)

        # Assert: Should succeed after retry
        assert result == "Success after retry"
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once()

    @patch("paper_collection.paper_summary.util.llm_client.get_rate_limiter")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_url")
    @patch("paper_collection.paper_summary.util.llm_client.get_default_model")
    @patch("paper_collection.paper_summary.util.llm_client.get_api_key")
    @patch("paper_collection.paper_summary.util.llm_client.requests.post")
    def test_call_gemini_api_no_retry_on_400(
        self,
        mock_post: MagicMock,
        mock_get_key: MagicMock,
        mock_get_model: MagicMock,
        mock_get_url: MagicMock,
        mock_rate_limiter: MagicMock,
    ) -> None:
        """Test that 400 client errors do not trigger retry."""
        # Setup
        mock_rate_limiter.return_value = MagicMock()
        mock_get_key.return_value = "test-api-key"
        mock_get_model.return_value = "gemini-2.0-flash"
        mock_get_url.return_value = "https://api.test.com/endpoint"

        bad_request_response = MagicMock()
        bad_request_response.status_code = 400
        bad_request_response.text = "Bad request"

        mock_post.return_value = bad_request_response

        # Execute & Assert: Should raise without retrying
        from paper_collection.paper_summary.util.llm_client import call_gemini_api

        with pytest.raises(Exception, match="API Error: 400"):
            call_gemini_api("Test prompt", max_retries=3)

        # Should only call once (no retry)
        assert mock_post.call_count == 1


class TestExtractResponseFormats:
    """Tests for _extract_api_response function."""

    def test_extract_response_with_result_key(self) -> None:
        """Test extracting response when 'result' key exists."""
        # Setup
        from paper_collection.paper_summary.util.llm_client import _extract_api_response

        api_response = {"result": "Response content"}

        # Execute
        result = _extract_api_response(api_response)

        # Assert
        assert result == "Response content"

    def test_extract_response_with_choices_format(self) -> None:
        """Test extracting response from OpenAI-style choices format."""
        # Setup
        from paper_collection.paper_summary.util.llm_client import _extract_api_response

        api_response = {"choices": [{"message": {"content": "OpenAI style response"}}]}

        # Execute
        result = _extract_api_response(api_response)

        # Assert
        assert result == "OpenAI style response"

    def test_extract_response_with_content_key(self) -> None:
        """Test extracting response when 'content' key exists."""
        # Setup
        from paper_collection.paper_summary.util.llm_client import _extract_api_response

        api_response = {"content": "Direct content"}

        # Execute
        result = _extract_api_response(api_response)

        # Assert
        assert result == "Direct content"

    def test_extract_response_with_response_key(self) -> None:
        """Test extracting response when 'response' key exists."""
        # Setup
        from paper_collection.paper_summary.util.llm_client import _extract_api_response

        api_response = {"response": "Response value"}

        # Execute
        result = _extract_api_response(api_response)

        # Assert
        assert result == "Response value"

    def test_extract_response_fallback_to_json(self) -> None:
        """Test that unknown formats fall back to JSON serialization."""
        # Setup
        from paper_collection.paper_summary.util.llm_client import _extract_api_response

        api_response = {"unknown_key": "some_value", "other": 123}

        # Execute
        result = _extract_api_response(api_response)

        # Assert: Should be JSON string
        parsed = json.loads(result)
        assert parsed["unknown_key"] == "some_value"
        assert parsed["other"] == 123


class TestConfigValue:
    """Tests for get_config_value function."""

    def test_get_config_value_from_env(self) -> None:
        """Test that environment variable takes precedence."""
        # Setup
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-value"}):
            with patch(
                "paper_collection.paper_summary.util.llm_client._get_gemini_config"
            ) as mock_config:
                mock_gemini = MagicMock()
                mock_gemini.api_key = "config-value"
                mock_config.return_value = mock_gemini

                # Execute
                from paper_collection.paper_summary.util.llm_client import (
                    get_config_value,
                )

                result = get_config_value("api_key")

                # Assert: Env should take precedence
                assert result == "env-value"

    def test_get_config_value_from_config(self) -> None:
        """Test falling back to config when env not set."""
        # Setup: Clear env var
        with patch.dict(os.environ, {}, clear=True):
            # Remove GEMINI_API_KEY if it exists
            os.environ.pop("GEMINI_API_KEY", None)

            with patch(
                "paper_collection.paper_summary.util.llm_client._get_gemini_config"
            ) as mock_config:
                mock_gemini = MagicMock()
                mock_gemini.api_key = "config-value"
                mock_config.return_value = mock_gemini

                # Execute
                from paper_collection.paper_summary.util.llm_client import (
                    get_config_value,
                )

                result = get_config_value("api_key")

                # Assert: Should get from config
                assert result == "config-value"

    def test_get_config_value_default(self) -> None:
        """Test returning default when neither env nor config has value."""
        # Setup
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_CUSTOM_KEY", None)

            with patch(
                "paper_collection.paper_summary.util.llm_client._get_gemini_config"
            ) as mock_config:
                mock_gemini = MagicMock()
                mock_gemini.custom_key = None
                mock_config.return_value = mock_gemini

                # Execute
                from paper_collection.paper_summary.util.llm_client import (
                    get_config_value,
                )

                result = get_config_value("custom_key", default="my-default")

                # Assert
                assert result == "my-default"
