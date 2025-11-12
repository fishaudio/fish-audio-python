"""Tests for TTS realtime streaming."""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from fishaudio.core import ClientWrapper, AsyncClientWrapper
from fishaudio.resources.tts import TTSClient, AsyncTTSClient
from fishaudio.types import Prosody, TTSConfig, TextEvent, FlushEvent, ReferenceAudio
import ormsgpack


@pytest.fixture
def mock_client_wrapper(mock_api_key):
    """Mock client wrapper."""
    wrapper = Mock(spec=ClientWrapper)
    wrapper.api_key = mock_api_key
    # Mock the underlying httpx.Client
    wrapper._client = Mock()
    return wrapper


@pytest.fixture
def async_mock_client_wrapper(mock_api_key):
    """Mock async client wrapper."""
    wrapper = Mock(spec=AsyncClientWrapper)
    wrapper.api_key = mock_api_key
    # Mock the underlying httpx.AsyncClient
    wrapper._client = Mock()
    return wrapper


@pytest.fixture
def tts_client(mock_client_wrapper):
    """TTSClient instance with mocked wrapper."""
    return TTSClient(mock_client_wrapper)


@pytest.fixture
def async_tts_client(async_mock_client_wrapper):
    """AsyncTTSClient instance with mocked wrapper."""
    return AsyncTTSClient(async_mock_client_wrapper)


class TestTTSRealtimeClient:
    """Test synchronous TTSClient realtime streaming."""

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_basic(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test basic WebSocket streaming."""
        # Setup mock WebSocket
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = mock_ws

        # Setup mock executor
        mock_future = Mock()
        mock_future.result.return_value = None
        mock_executor_instance = Mock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        # Mock the audio receiver (iter_websocket_audio)
        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio1", b"audio2", b"audio3"])

            # Create text stream
            text_stream = iter(["Hello ", "world", "!"])

            # Call stream_websocket
            audio_chunks = list(tts_client.stream_websocket(text_stream))

            # Verify audio chunks
            assert audio_chunks == [b"audio1", b"audio2", b"audio3"]

            # Verify WebSocket connection was created
            mock_connect_ws.assert_called_once()
            assert mock_connect_ws.call_args[0][0] == "/v1/tts/live"

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_with_config(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test WebSocket streaming with custom config."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = mock_ws

        mock_future = Mock()
        mock_future.result.return_value = None
        mock_executor_instance = Mock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            # Custom config
            config = TTSConfig(
                reference_id="voice_123",
                format="wav",
                prosody=Prosody(speed=1.2, volume=0.5),
            )

            text_stream = iter(["Test"])
            list(
                tts_client.stream_websocket(
                    text_stream, config=config, model="speech-1.5"
                )
            )

            # Verify model in headers
            call_args = mock_connect_ws.call_args
            assert call_args[1]["headers"]["model"] == "speech-1.5"

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_with_text_events(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test WebSocket streaming with TextEvent and FlushEvent."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = mock_ws

        mock_future = Mock()
        mock_future.result.return_value = None
        mock_executor_instance = Mock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio1", b"audio2"])

            # Mix of strings and events
            text_stream = iter(
                [
                    "Hello ",
                    TextEvent(text="world"),
                    FlushEvent(),
                ]
            )

            audio_chunks = list(tts_client.stream_websocket(text_stream))

            # Should receive audio
            assert len(audio_chunks) == 2
            assert audio_chunks == [b"audio1", b"audio2"]

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_max_workers(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test WebSocket streaming with custom max_workers."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = mock_ws

        mock_future = Mock()
        mock_future.result.return_value = None
        mock_executor_instance = Mock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            text_stream = iter(["Test"])
            list(tts_client.stream_websocket(text_stream, max_workers=5))

            # Verify ThreadPoolExecutor was created with max_workers=5
            mock_executor.assert_called_once_with(max_workers=5)

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_with_reference_id_parameter(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test WebSocket streaming with reference_id as direct parameter."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_ws.send_bytes = Mock()
        mock_connect_ws.return_value = mock_ws

        # Make executor.submit actually run the function
        def submit_side_effect(fn):
            fn()  # Execute the sender function
            mock_future = Mock()
            mock_future.result.return_value = None
            return mock_future

        mock_executor_instance = Mock()
        mock_executor_instance.submit.side_effect = submit_side_effect
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            text_stream = iter(["Test"])
            list(tts_client.stream_websocket(text_stream, reference_id="voice_456"))

            # Verify WebSocket was called with StartEvent containing reference_id
            assert mock_ws.send_bytes.called
            # Get the first call (StartEvent)
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert start_event_payload["request"]["reference_id"] == "voice_456"

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_parameter_reference_id_overrides_config(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test that parameter reference_id overrides config.reference_id."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_ws.send_bytes = Mock()
        mock_connect_ws.return_value = mock_ws

        # Make executor.submit actually run the function
        def submit_side_effect(fn):
            fn()  # Execute the sender function
            mock_future = Mock()
            mock_future.result.return_value = None
            return mock_future

        mock_executor_instance = Mock()
        mock_executor_instance.submit.side_effect = submit_side_effect
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            config = TTSConfig(reference_id="voice_from_config")
            text_stream = iter(["Test"])
            list(
                tts_client.stream_websocket(
                    text_stream, reference_id="voice_from_param", config=config
                )
            )

            # Verify parameter reference_id takes precedence
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert start_event_payload["request"]["reference_id"] == "voice_from_param"

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_with_references_parameter(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test WebSocket streaming with references as direct parameter."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_ws.send_bytes = Mock()
        mock_connect_ws.return_value = mock_ws

        # Make executor.submit actually run the function
        def submit_side_effect(fn):
            fn()  # Execute the sender function
            mock_future = Mock()
            mock_future.result.return_value = None
            return mock_future

        mock_executor_instance = Mock()
        mock_executor_instance.submit.side_effect = submit_side_effect
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            references = [
                ReferenceAudio(audio=b"ref_audio_1", text="Sample 1"),
                ReferenceAudio(audio=b"ref_audio_2", text="Sample 2"),
            ]

            text_stream = iter(["Test"])
            list(tts_client.stream_websocket(text_stream, references=references))

            # Verify references in StartEvent
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert len(start_event_payload["request"]["references"]) == 2
            assert start_event_payload["request"]["references"][0]["text"] == "Sample 1"
            assert start_event_payload["request"]["references"][1]["text"] == "Sample 2"

    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_stream_websocket_parameter_references_overrides_config(
        self, mock_executor, mock_connect_ws, tts_client, mock_client_wrapper
    ):
        """Test that parameter references overrides config.references."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__enter__ = Mock(return_value=mock_ws)
        mock_ws.__exit__ = Mock(return_value=None)
        mock_ws.send_bytes = Mock()
        mock_connect_ws.return_value = mock_ws

        # Make executor.submit actually run the function
        def submit_side_effect(fn):
            fn()  # Execute the sender function
            mock_future = Mock()
            mock_future.result.return_value = None
            return mock_future

        mock_executor_instance = Mock()
        mock_executor_instance.submit.side_effect = submit_side_effect
        mock_executor.return_value = mock_executor_instance

        with patch("fishaudio.resources.tts.iter_websocket_audio") as mock_receiver:
            mock_receiver.return_value = iter([b"audio"])

            config_refs = [ReferenceAudio(audio=b"config_audio", text="Config")]
            param_refs = [ReferenceAudio(audio=b"param_audio", text="Param")]

            config = TTSConfig(references=config_refs)
            text_stream = iter(["Test"])
            list(
                tts_client.stream_websocket(
                    text_stream, references=param_refs, config=config
                )
            )

            # Verify parameter references take precedence
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert len(start_event_payload["request"]["references"]) == 1
            assert start_event_payload["request"]["references"][0]["text"] == "Param"


class TestAsyncTTSRealtimeClient:
    """Test asynchronous AsyncTTSClient realtime streaming."""

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_basic(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test basic async WebSocket streaming."""
        # Setup mock WebSocket
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        # Mock the audio receiver
        async def mock_audio_receiver(ws):
            for chunk in [b"audio1", b"audio2", b"audio3"]:
                yield chunk

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            # Create async text stream
            async def text_stream():
                for text in ["Hello ", "world", "!"]:
                    yield text

            # Call stream_websocket
            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(text_stream()):
                audio_chunks.append(chunk)

            # Verify audio chunks
            assert audio_chunks == [b"audio1", b"audio2", b"audio3"]

            # Verify WebSocket connection was created
            mock_aconnect_ws.assert_called_once()
            assert mock_aconnect_ws.call_args[0][0] == "/v1/tts/live"

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_with_config(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test async WebSocket streaming with custom config."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            # Custom config
            config = TTSConfig(
                reference_id="voice_123",
                format="wav",
                prosody=Prosody(speed=1.2, volume=0.5),
            )

            async def text_stream():
                yield "Test"

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(
                text_stream(), config=config, model="speech-1.6"
            ):
                audio_chunks.append(chunk)

            # Verify model in headers
            call_args = mock_aconnect_ws.call_args
            assert call_args[1]["headers"]["model"] == "speech-1.6"

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_with_text_events(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test async WebSocket streaming with TextEvent and FlushEvent."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio1"
            yield b"audio2"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            # Mix of strings and events
            async def text_stream():
                yield "Hello "
                yield TextEvent(text="world")
                yield FlushEvent()

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(text_stream()):
                audio_chunks.append(chunk)

            # Should receive audio
            assert len(audio_chunks) == 2
            assert audio_chunks == [b"audio1", b"audio2"]

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_empty_stream(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test async WebSocket streaming with empty text stream."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            return
            yield  # Make it a generator

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):

            async def text_stream():
                return
                yield  # Empty stream

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(text_stream()):
                audio_chunks.append(chunk)

            # Should have no audio
            assert audio_chunks == []

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_with_reference_id_parameter(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test async WebSocket streaming with reference_id as direct parameter."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):

            async def text_stream():
                yield "Test"

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(
                text_stream(), reference_id="voice_456"
            ):
                audio_chunks.append(chunk)

            # Verify WebSocket was called with StartEvent containing reference_id
            assert mock_ws.send_bytes.called
            # Get the first call (StartEvent)
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert start_event_payload["request"]["reference_id"] == "voice_456"

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_parameter_reference_id_overrides_config(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test that parameter reference_id overrides config.reference_id (async)."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            config = TTSConfig(reference_id="voice_from_config")

            async def text_stream():
                yield "Test"

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(
                text_stream(), reference_id="voice_from_param", config=config
            ):
                audio_chunks.append(chunk)

            # Verify parameter reference_id takes precedence
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert start_event_payload["request"]["reference_id"] == "voice_from_param"

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_with_references_parameter(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test async WebSocket streaming with references as direct parameter."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            references = [
                ReferenceAudio(audio=b"ref_audio_1", text="Sample 1"),
                ReferenceAudio(audio=b"ref_audio_2", text="Sample 2"),
            ]

            async def text_stream():
                yield "Test"

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(
                text_stream(), references=references
            ):
                audio_chunks.append(chunk)

            # Verify references in StartEvent
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert len(start_event_payload["request"]["references"]) == 2
            assert start_event_payload["request"]["references"][0]["text"] == "Sample 1"
            assert start_event_payload["request"]["references"][1]["text"] == "Sample 2"

    @pytest.mark.asyncio
    @patch("fishaudio.resources.tts.aconnect_ws")
    async def test_stream_websocket_parameter_references_overrides_config(
        self, mock_aconnect_ws, async_tts_client, async_mock_client_wrapper
    ):
        """Test that parameter references overrides config.references (async)."""
        # Setup mocks
        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=None)
        mock_ws.send_bytes = AsyncMock()
        mock_aconnect_ws.return_value = mock_ws

        async def mock_audio_receiver(ws):
            yield b"audio"

        with patch(
            "fishaudio.resources.tts.aiter_websocket_audio",
            return_value=mock_audio_receiver(mock_ws),
        ):
            config_refs = [ReferenceAudio(audio=b"config_audio", text="Config")]
            param_refs = [ReferenceAudio(audio=b"param_audio", text="Param")]

            config = TTSConfig(references=config_refs)

            async def text_stream():
                yield "Test"

            audio_chunks = []
            async for chunk in async_tts_client.stream_websocket(
                text_stream(), references=param_refs, config=config
            ):
                audio_chunks.append(chunk)

            # Verify parameter references take precedence
            first_call = mock_ws.send_bytes.call_args_list[0]
            start_event_payload = ormsgpack.unpackb(first_call[0][0])
            assert len(start_event_payload["request"]["references"]) == 1
            assert start_event_payload["request"]["references"][0]["text"] == "Param"
