"""Tests for ASR namespace client."""

from unittest.mock import AsyncMock, Mock

import ormsgpack
import pytest

from fishaudio.core import AsyncClientWrapper, ClientWrapper, RequestOptions
from fishaudio.resources.asr import ASRClient, AsyncASRClient
from fishaudio.types import ASRResponse


@pytest.fixture
def mock_client_wrapper(mock_api_key):
    """Mock client wrapper."""
    wrapper = Mock(spec=ClientWrapper)
    wrapper.api_key = mock_api_key
    return wrapper


@pytest.fixture
def async_mock_client_wrapper(mock_api_key):
    """Mock async client wrapper."""
    wrapper = Mock(spec=AsyncClientWrapper)
    wrapper.api_key = mock_api_key
    return wrapper


@pytest.fixture
def asr_client(mock_client_wrapper):
    """ASRClient instance with mocked wrapper."""
    return ASRClient(mock_client_wrapper)


@pytest.fixture
def async_asr_client(async_mock_client_wrapper):
    """AsyncASRClient instance with mocked wrapper."""
    return AsyncASRClient(async_mock_client_wrapper)


class TestASRClient:
    """Test synchronous ASRClient."""

    def test_transcribe_basic(
        self, asr_client, mock_client_wrapper, sample_asr_response
    ):
        """Test basic transcription."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        mock_client_wrapper.request.return_value = mock_response

        result = asr_client.transcribe(audio=b"fake_audio")

        assert isinstance(result, ASRResponse)
        assert result.text == "Hello world"
        assert result.duration == 1500.0
        assert len(result.segments) == 2

        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/v1/asr"
        assert call_args[1]["headers"]["Content-Type"] == "application/msgpack"

        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["audio"] == b"fake_audio"
        assert payload["ignore_timestamps"] is False
        assert "language" not in payload

    def test_transcribe_with_language(
        self, asr_client, mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with language specified."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        mock_client_wrapper.request.return_value = mock_response

        asr_client.transcribe(audio=b"fake_audio", language="en")

        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["language"] == "en"

    def test_transcribe_without_timestamps(
        self, asr_client, mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with timestamps disabled."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        mock_client_wrapper.request.return_value = mock_response

        asr_client.transcribe(audio=b"fake_audio", include_timestamps=False)

        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["ignore_timestamps"] is True

    def test_transcribe_with_request_options(
        self, asr_client, mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with custom request options."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        mock_client_wrapper.request.return_value = mock_response

        request_options = RequestOptions(timeout=60.0)
        asr_client.transcribe(audio=b"fake_audio", request_options=request_options)

        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options

    def test_transcribe_language_none(
        self, asr_client, mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with language explicitly set to None."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        mock_client_wrapper.request.return_value = mock_response

        asr_client.transcribe(audio=b"fake_audio", language=None)

        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["language"] is None


class TestAsyncASRClient:
    """Test asynchronous AsyncASRClient."""

    @pytest.mark.asyncio
    async def test_transcribe_basic(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_response
    ):
        """Test basic transcription (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        result = await async_asr_client.transcribe(audio=b"fake_audio")

        assert isinstance(result, ASRResponse)
        assert result.text == "Hello world"
        assert result.duration == 1500.0
        assert len(result.segments) == 2

        async_mock_client_wrapper.request.assert_called_once()
        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/v1/asr"

        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["audio"] == b"fake_audio"
        assert payload["ignore_timestamps"] is False
        assert "language" not in payload

    @pytest.mark.asyncio
    async def test_transcribe_with_language(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with language specified (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        await async_asr_client.transcribe(audio=b"fake_audio", language="zh")

        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["language"] == "zh"

    @pytest.mark.asyncio
    async def test_transcribe_without_timestamps(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with timestamps disabled (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        await async_asr_client.transcribe(audio=b"fake_audio", include_timestamps=False)

        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["ignore_timestamps"] is True

    @pytest.mark.asyncio
    async def test_transcribe_with_request_options(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_response
    ):
        """Test transcription with custom request options (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        request_options = RequestOptions(timeout=60.0)
        await async_asr_client.transcribe(
            audio=b"fake_audio", request_options=request_options
        )

        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options
