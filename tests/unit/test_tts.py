"""Tests for TTS namespace client."""

import pytest
from unittest.mock import Mock, AsyncMock
import ormsgpack

from fishaudio.core import ClientWrapper, AsyncClientWrapper, RequestOptions
from fishaudio.resources.tts import TTSClient, AsyncTTSClient
from fishaudio.types import ReferenceAudio, Prosody, TTSConfig


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
def tts_client(mock_client_wrapper):
    """TTSClient instance with mocked wrapper."""
    return TTSClient(mock_client_wrapper)


@pytest.fixture
def async_tts_client(async_mock_client_wrapper):
    """AsyncTTSClient instance with mocked wrapper."""
    return AsyncTTSClient(async_mock_client_wrapper)


class TestTTSClient:
    """Test synchronous TTSClient."""

    def test_convert_basic(self, tts_client, mock_client_wrapper):
        """Test basic TTS conversion."""
        # Setup mock response with audio chunks
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"chunk1", b"chunk2", b"chunk3"])
        mock_client_wrapper.request.return_value = mock_response

        # Call convert
        audio_chunks = list(tts_client.convert(text="Hello world"))

        # Verify we got chunks back
        assert audio_chunks == [b"chunk1", b"chunk2", b"chunk3"]

        # Verify request was made correctly
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args

        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/v1/tts"

        # Check headers
        assert call_args[1]["headers"]["Content-Type"] == "application/msgpack"
        assert call_args[1]["headers"]["model"] == "s1"  # default model

        # Check payload was msgpack encoded
        assert "content" in call_args[1]

    def test_convert_with_reference_id(self, tts_client, mock_client_wrapper):
        """Test TTS with reference voice ID."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        config = TTSConfig(reference_id="voice_123")
        list(tts_client.convert(text="Hello", config=config))

        # Verify reference_id in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_123"

    def test_convert_with_reference_id_parameter(self, tts_client, mock_client_wrapper):
        """Test TTS with reference_id as direct parameter."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        list(tts_client.convert(text="Hello", reference_id="voice_456"))

        # Verify reference_id in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_456"

    def test_convert_config_reference_id_overrides_parameter(
        self, tts_client, mock_client_wrapper
    ):
        """Test that config.reference_id overrides parameter reference_id."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        config = TTSConfig(reference_id="voice_from_config")
        list(
            tts_client.convert(
                text="Hello", reference_id="voice_from_param", config=config
            )
        )

        # Verify config reference_id takes precedence
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_from_config"

    def test_convert_with_references(self, tts_client, mock_client_wrapper):
        """Test TTS with reference audio samples."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        references = [
            ReferenceAudio(audio=b"ref_audio_1", text="Sample 1"),
            ReferenceAudio(audio=b"ref_audio_2", text="Sample 2"),
        ]

        config = TTSConfig(references=references)
        list(tts_client.convert(text="Hello", config=config))

        # Verify references in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert len(payload["references"]) == 2
        assert payload["references"][0]["text"] == "Sample 1"
        assert payload["references"][1]["text"] == "Sample 2"

    def test_convert_with_references_parameter(self, tts_client, mock_client_wrapper):
        """Test TTS with references as direct parameter."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        references = [
            ReferenceAudio(audio=b"ref_audio_1", text="Sample 1"),
            ReferenceAudio(audio=b"ref_audio_2", text="Sample 2"),
        ]

        list(tts_client.convert(text="Hello", references=references))

        # Verify references in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert len(payload["references"]) == 2
        assert payload["references"][0]["text"] == "Sample 1"
        assert payload["references"][1]["text"] == "Sample 2"

    def test_convert_config_references_overrides_parameter(
        self, tts_client, mock_client_wrapper
    ):
        """Test that config.references overrides parameter references."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        config_refs = [ReferenceAudio(audio=b"config_audio", text="Config")]
        param_refs = [ReferenceAudio(audio=b"param_audio", text="Param")]

        config = TTSConfig(references=config_refs)
        list(tts_client.convert(text="Hello", references=param_refs, config=config))

        # Verify config references take precedence
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert len(payload["references"]) == 1
        assert payload["references"][0]["text"] == "Config"

    def test_convert_with_different_backend(self, tts_client, mock_client_wrapper):
        """Test TTS with different backend/model."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        list(tts_client.convert(text="Hello", model="s1"))

        # Verify model in headers
        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["headers"]["model"] == "s1"

    def test_convert_with_prosody(self, tts_client, mock_client_wrapper):
        """Test TTS with prosody settings."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        prosody = Prosody(speed=1.5, volume=0.5)
        config = TTSConfig(prosody=prosody)

        list(tts_client.convert(text="Hello", config=config))

        # Verify prosody in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["prosody"]["speed"] == 1.5
        assert payload["prosody"]["volume"] == 0.5

    def test_convert_with_custom_parameters(self, tts_client, mock_client_wrapper):
        """Test TTS with custom audio parameters."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        config = TTSConfig(
            format="wav",
            sample_rate=48000,
            mp3_bitrate=192,
            chunk_length=150,
            normalize=False,
            latency="normal",
            top_p=0.9,
            temperature=0.8,
        )

        list(tts_client.convert(text="Hello", config=config))

        # Verify parameters in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["format"] == "wav"
        assert payload["sample_rate"] == 48000
        assert payload["mp3_bitrate"] == 192
        assert payload["chunk_length"] == 150
        assert payload["normalize"] is False
        assert payload["latency"] == "normal"
        assert payload["top_p"] == 0.9
        assert payload["temperature"] == 0.8

    def test_convert_omit_parameters_not_sent(self, tts_client, mock_client_wrapper):
        """Test that None/optional parameters are not included in request."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        # Call with defaults (None values should be excluded)
        list(tts_client.convert(text="Hello"))

        # Verify None params not in payload
        call_args = mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])

        # These should NOT be in payload (are None by default)
        assert "reference_id" not in payload
        assert "sample_rate" not in payload
        assert "prosody" not in payload

        # references is an empty list by default, so it IS included
        assert payload["references"] == []

    def test_convert_with_request_options(self, tts_client, mock_client_wrapper):
        """Test TTS with custom request options."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([b"audio"])
        mock_client_wrapper.request.return_value = mock_response

        request_options = RequestOptions(
            timeout=120.0, additional_headers={"X-Custom": "value"}
        )

        list(tts_client.convert(text="Hello", request_options=request_options))

        # Verify request_options passed through
        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options

    def test_convert_streaming_behavior(self, tts_client, mock_client_wrapper):
        """Test that convert returns an iterator that can be consumed."""
        # Setup mock with multiple chunks
        mock_response = Mock()
        chunks = [b"chunk1", b"chunk2", b"chunk3", b""]  # Empty chunk should be skipped
        mock_response.iter_bytes.return_value = iter(chunks)
        mock_client_wrapper.request.return_value = mock_response

        # Get iterator
        audio_iterator = tts_client.convert(text="Hello")

        # Consume one chunk at a time
        result = []
        for chunk in audio_iterator:
            result.append(chunk)

        # Empty chunk should be filtered out
        assert result == [b"chunk1", b"chunk2", b"chunk3"]

    def test_convert_empty_response(self, tts_client, mock_client_wrapper):
        """Test handling of empty audio response."""
        mock_response = Mock()
        mock_response.iter_bytes.return_value = iter([])
        mock_client_wrapper.request.return_value = mock_response

        audio_chunks = list(tts_client.convert(text="Hello"))

        assert audio_chunks == []


class TestAsyncTTSClient:
    """Test asynchronous AsyncTTSClient."""

    @pytest.mark.asyncio
    async def test_convert_basic(self, async_tts_client, async_mock_client_wrapper):
        """Test basic async TTS conversion."""
        # Setup mock response
        mock_response = Mock()

        async def async_iter_bytes():
            for chunk in [b"chunk1", b"chunk2", b"chunk3"]:
                yield chunk

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        # Call convert and collect chunks
        audio_chunks = []
        async for chunk in async_tts_client.convert(text="Hello world"):
            audio_chunks.append(chunk)

        assert audio_chunks == [b"chunk1", b"chunk2", b"chunk3"]

        # Verify request was made
        async_mock_client_wrapper.request.assert_called_once()
        call_args = async_mock_client_wrapper.request.call_args

        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/v1/tts"

    @pytest.mark.asyncio
    async def test_convert_with_reference_id(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test async TTS with reference voice ID."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        config = TTSConfig(reference_id="voice_123")
        audio_chunks = []
        async for chunk in async_tts_client.convert(text="Hello", config=config):
            audio_chunks.append(chunk)

        # Verify reference_id in payload
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_123"

    @pytest.mark.asyncio
    async def test_convert_with_reference_id_parameter(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test async TTS with reference_id as direct parameter."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        audio_chunks = []
        async for chunk in async_tts_client.convert(
            text="Hello", reference_id="voice_456"
        ):
            audio_chunks.append(chunk)

        # Verify reference_id in payload
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_456"

    @pytest.mark.asyncio
    async def test_convert_config_reference_id_overrides_parameter(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test that config.reference_id overrides parameter reference_id (async)."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        config = TTSConfig(reference_id="voice_from_config")
        audio_chunks = []
        async for chunk in async_tts_client.convert(
            text="Hello", reference_id="voice_from_param", config=config
        ):
            audio_chunks.append(chunk)

        # Verify config reference_id takes precedence
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["reference_id"] == "voice_from_config"

    @pytest.mark.asyncio
    async def test_convert_with_references_parameter(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test async TTS with references as direct parameter."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        references = [
            ReferenceAudio(audio=b"ref_audio_1", text="Sample 1"),
            ReferenceAudio(audio=b"ref_audio_2", text="Sample 2"),
        ]

        audio_chunks = []
        async for chunk in async_tts_client.convert(
            text="Hello", references=references
        ):
            audio_chunks.append(chunk)

        # Verify references in payload
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert len(payload["references"]) == 2
        assert payload["references"][0]["text"] == "Sample 1"
        assert payload["references"][1]["text"] == "Sample 2"

    @pytest.mark.asyncio
    async def test_convert_config_references_overrides_parameter(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test that config.references overrides parameter references (async)."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        config_refs = [ReferenceAudio(audio=b"config_audio", text="Config")]
        param_refs = [ReferenceAudio(audio=b"param_audio", text="Param")]

        config = TTSConfig(references=config_refs)
        audio_chunks = []
        async for chunk in async_tts_client.convert(
            text="Hello", references=param_refs, config=config
        ):
            audio_chunks.append(chunk)

        # Verify config references take precedence
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert len(payload["references"]) == 1
        assert payload["references"][0]["text"] == "Config"

    @pytest.mark.asyncio
    async def test_convert_with_prosody(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test async TTS with prosody settings."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        prosody = Prosody(speed=2.0, volume=1.0)
        config = TTSConfig(prosody=prosody)

        audio_chunks = []
        async for chunk in async_tts_client.convert(text="Hello", config=config):
            audio_chunks.append(chunk)

        # Verify prosody in payload
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])
        assert payload["prosody"]["speed"] == 2.0
        assert payload["prosody"]["volume"] == 1.0

    @pytest.mark.asyncio
    async def test_convert_omit_parameters(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test that OMIT parameters work in async client."""
        mock_response = Mock()

        async def async_iter_bytes():
            yield b"audio"

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        audio_chunks = []
        async for chunk in async_tts_client.convert(text="Hello"):
            audio_chunks.append(chunk)

        # Verify OMIT params not in payload
        call_args = async_mock_client_wrapper.request.call_args
        payload = ormsgpack.unpackb(call_args[1]["content"])

        assert "reference_id" not in payload
        assert "sample_rate" not in payload
        assert "prosody" not in payload

    @pytest.mark.asyncio
    async def test_convert_empty_response(
        self, async_tts_client, async_mock_client_wrapper
    ):
        """Test handling of empty async response."""
        mock_response = Mock()

        async def async_iter_bytes():
            return
            yield  # Make it a generator

        mock_response.aiter_bytes = async_iter_bytes
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        audio_chunks = []
        async for chunk in async_tts_client.convert(text="Hello"):
            audio_chunks.append(chunk)

        assert audio_chunks == []
