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
        assert result.duration == 1.5
        assert len(result.segments) == 2
        assert result.language_code is None
        assert result.speaker_turns is None

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

    def test_transcribe_standard_model_response(
        self, asr_client, mock_client_wrapper, sample_asr_standard_response
    ):
        """Test that a transcribe-1 response keeps its language fields."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_standard_response
        mock_client_wrapper.request.return_value = mock_response

        result = asr_client.transcribe(audio=b"fake_audio")

        assert result.text == "Hello, world."
        assert result.duration == 1.62
        assert result.language == "English"
        assert result.language_code == "en"
        assert result.request_id is None
        assert result.speaker_turns is None

    def test_transcribe_pro_model_response(
        self, asr_client, mock_client_wrapper, sample_asr_pro_response
    ):
        """Test that a transcribe-1-pro response keeps request_id and speaker_turns."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_pro_response
        mock_client_wrapper.request.return_value = mock_response

        request_options = RequestOptions(
            additional_headers={"model": "transcribe-1-pro"}
        )
        result = asr_client.transcribe(
            audio=b"fake_audio", request_options=request_options
        )

        assert result.duration == 3.5
        assert result.language == "English"
        assert result.language_code == "en"
        assert result.request_id == "0b9e4f5c-7d2a-4f1e-9c3b-5a8d6e2f1c07"
        assert result.speaker_turns is not None
        assert [turn.speaker for turn in result.speaker_turns] == [
            "speaker:0",
            "speaker:1",
        ]
        assert result.speaker_turns[1].text == "Hi back."
        assert result.speaker_turns[1].start == 1.8
        assert result.speaker_turns[1].end == 3.1

        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] is request_options


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
        assert result.duration == 1.5
        assert len(result.segments) == 2
        assert result.language_code is None
        assert result.speaker_turns is None

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

    @pytest.mark.asyncio
    async def test_transcribe_standard_model_response(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_standard_response
    ):
        """Test that a transcribe-1 response keeps its language fields (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_standard_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        result = await async_asr_client.transcribe(audio=b"fake_audio")

        assert result.text == "Hello, world."
        assert result.duration == 1.62
        assert result.language == "English"
        assert result.language_code == "en"
        assert result.request_id is None
        assert result.speaker_turns is None

    @pytest.mark.asyncio
    async def test_transcribe_pro_model_response(
        self, async_asr_client, async_mock_client_wrapper, sample_asr_pro_response
    ):
        """Test that a transcribe-1-pro response keeps request_id and speaker_turns (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_asr_pro_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        request_options = RequestOptions(
            additional_headers={"model": "transcribe-1-pro"}
        )
        result = await async_asr_client.transcribe(
            audio=b"fake_audio", request_options=request_options
        )

        assert result.duration == 3.5
        assert result.language == "English"
        assert result.language_code == "en"
        assert result.request_id == "0b9e4f5c-7d2a-4f1e-9c3b-5a8d6e2f1c07"
        assert result.speaker_turns is not None
        assert [turn.speaker for turn in result.speaker_turns] == [
            "speaker:0",
            "speaker:1",
        ]
        assert result.speaker_turns[0].text == "Hello there."
        assert result.speaker_turns[0].start == 0.24
        assert result.speaker_turns[0].end == 1.2

        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] is request_options
