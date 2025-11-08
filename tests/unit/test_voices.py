"""Tests for voices namespace client."""

import pytest
from unittest.mock import Mock

from fishaudio.core import ClientWrapper
from fishaudio.resources.voices import VoicesClient
from fishaudio.types import Voice, PaginatedResponse


@pytest.fixture
def mock_client_wrapper(mock_api_key):
    """Mock client wrapper."""
    wrapper = Mock(spec=ClientWrapper)
    wrapper.api_key = mock_api_key
    return wrapper


@pytest.fixture
def voices_client(mock_client_wrapper):
    """VoicesClient instance with mocked wrapper."""
    return VoicesClient(mock_client_wrapper)


class TestVoicesClient:
    """Test VoicesClient."""

    def test_list_voices(
        self, voices_client, mock_client_wrapper, sample_paginated_voices_response
    ):
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_paginated_voices_response
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        result = voices_client.list(page_size=10, page_number=1)

        # Verify
        assert isinstance(result, PaginatedResponse)
        assert result.total == 1
        assert len(result.items) == 1
        assert isinstance(result.items[0], Voice)

        # Verify request was made correctly
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/model"

    def test_get_voice(self, voices_client, mock_client_wrapper, sample_voice_response):
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_voice_response
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        result = voices_client.get("voice123")

        # Verify
        assert isinstance(result, Voice)
        assert result.id == "voice123"
        assert result.title == "Test Voice"

        # Verify request
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/model/voice123"

    def test_delete_voice(self, voices_client, mock_client_wrapper):
        # Setup mock response
        mock_response = Mock()
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        voices_client.delete("voice123")

        # Verify request
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "DELETE"
        assert call_args[0][1] == "/model/voice123"

    def test_create_voice(
        self, voices_client, mock_client_wrapper, sample_voice_response
    ):
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_voice_response
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        result = voices_client.create(
            title="New Voice",
            voices=[b"audio1", b"audio2"],
            description="Test description",
            tags=["test"],
        )

        # Verify
        assert isinstance(result, Voice)
        assert result.title == "Test Voice"

        # Verify request
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/model"
        # Check that data and files were passed
        assert "data" in call_args[1]
        assert "files" in call_args[1]
