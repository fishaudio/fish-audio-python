"""Integration tests for TTS WebSocket streaming functionality."""

from typing import get_args

import pytest

from fishaudio import WebSocketOptions
from fishaudio.types import Prosody, TTSConfig, TextEvent, FlushEvent
from fishaudio.types.shared import Model
from .conftest import TEST_REFERENCE_ID


class TestTTSWebSocketIntegration:
    """Test TTS WebSocket streaming with real API."""

    def test_basic_websocket_streaming(self, client, save_audio):
        """Test basic WebSocket streaming with simple text."""

        # Create a simple text stream
        def text_stream():
            yield "Hello, "
            yield "this is "
            yield "a streaming test."

        # Stream audio via WebSocket
        audio_chunks = list(client.tts.stream_websocket(text_stream()))

        assert len(audio_chunks) > 0, "Should receive audio chunks"

        # Verify we got audio data
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000, "Should have substantial audio data"

        # Save the audio
        save_audio(audio_chunks, "test_websocket_streaming.mp3")

    @pytest.mark.parametrize(
        "model",
        [
            pytest.param(
                m,
                marks=pytest.mark.xfail(
                    reason="WebSocket unreliable for legacy models"
                ),
            )
            if not m.startswith("s1")
            else m
            for m in get_args(Model)
        ],
    )
    def test_websocket_streaming_with_model(self, client, save_audio, model):
        """Test WebSocket streaming with a specific model."""

        def text_stream():
            yield f"Testing model {model} via WebSocket."

        audio_chunks = list(client.tts.stream_websocket(text_stream(), model=model))
        assert len(audio_chunks) > 0, f"Failed for model: {model}"

        # Write to output directory
        save_audio(audio_chunks, f"test_websocket_model_{model}.mp3")

    def test_websocket_streaming_with_wav_format(self, client, save_audio):
        """Test WebSocket streaming with WAV format."""
        config = TTSConfig(format="wav", chunk_length=200)

        def text_stream():
            yield "Testing WAV format."

        audio_chunks = list(client.tts.stream_websocket(text_stream(), config=config))

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_websocket_wav.wav")

    def test_websocket_streaming_with_prosody(self, client, save_audio):
        """Test WebSocket streaming with prosody settings."""
        prosody = Prosody(speed=1.3, volume=0.8)
        config = TTSConfig(prosody=prosody)

        def text_stream():
            yield "This audio "
            yield "should have "
            yield "faster speed."

        audio_chunks = list(client.tts.stream_websocket(text_stream(), config=config))

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_websocket_prosody.mp3")

    def test_websocket_streaming_with_text_events(self, client, save_audio):
        """Test WebSocket streaming with TextEvent and FlushEvent."""

        def text_stream():
            yield "First sentence. "
            yield TextEvent(text="Second sentence with event. ")
            yield FlushEvent()
            yield "Third sentence after flush."

        audio_chunks = list(client.tts.stream_websocket(text_stream()))

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_websocket_text_events.mp3")

    def test_websocket_streaming_long_text(self, client, save_audio):
        """Test WebSocket streaming with longer text chunks."""

        def text_stream():
            sentences = [
                "The quick brown fox jumps over the lazy dog. ",
                "This is a longer piece of text to test streaming. ",
                "We want to make sure the WebSocket can handle multiple chunks. ",
                "And that all audio is received correctly. ",
                "Finally, we end the stream here.",
            ]
            for sentence in sentences:
                yield sentence

        audio_chunks = list(client.tts.stream_websocket(text_stream()))

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 5000, "Should have more audio for longer text"
        save_audio(audio_chunks, "test_websocket_long_text.mp3")

    def test_websocket_streaming_with_reference(self, client, save_audio):
        """Test WebSocket streaming with reference voice."""
        config = TTSConfig(
            reference_id=TEST_REFERENCE_ID,
            chunk_length=200,
        )

        def text_stream():
            yield "Testing with reference voice."

        audio_chunks = list(client.tts.stream_websocket(text_stream(), config=config))
        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_websocket_reference.mp3")

    def test_websocket_streaming_empty_text(self, client, save_audio):
        """Test WebSocket streaming with empty text stream raises error."""
        from fishaudio.exceptions import WebSocketError

        def text_stream():
            return
            yield  # Make it a generator

        # Empty stream should raise WebSocketError as API returns error
        with pytest.raises(WebSocketError, match="WebSocket stream ended with error"):
            list(client.tts.stream_websocket(text_stream()))

    def test_websocket_very_long_generation_with_timeout(self, client, save_audio):
        """
        Test that very long text generation succeeds with increased timeout.

        This test generates a very long response that could potentially take >20 seconds
        to fully generate, which would cause a WebSocketNetworkError with the default
        keepalive_ping_timeout_seconds=20. By using an increased timeout of 60 seconds,
        we can handle longer generation times without disconnection.

        This is the SOLUTION to issue #47. To reproduce the timeout issue, run:
        python reproduce_issue_47.py --mode=both
        """
        # Use significantly increased timeout to handle very long generations
        ws_options = WebSocketOptions(
            keepalive_ping_timeout_seconds=60.0,
            keepalive_ping_interval_seconds=30.0,
        )

        def text_stream():
            # Generate a very long piece of text that will take significant time to process
            long_text = [
                "This is a test of very long form text-to-speech generation. ",
                "We are testing the ability to handle extended generation times without timing out. ",
                "The default WebSocket keepalive timeout of 20 seconds can be insufficient for long responses. ",
                "By increasing the keepalive_ping_timeout_seconds to 60 seconds, we allow for longer gaps between chunks. ",
                "This is particularly important for conversational AI applications where responses can be quite lengthy. ",
                "The WebSocket connection should remain stable throughout the entire generation process. ",
                "We include enough text here to ensure the generation takes a substantial amount of time. ",
                "This helps verify that the increased timeout setting is working correctly. ",
                "The audio streaming should continue smoothly without any network errors. ",
                "Each sentence adds more content to be synthesized into speech. ",
                "The system should handle this gracefully with the custom WebSocket options. ",
                "This demonstrates the practical value of the WebSocketOptions feature. ",
                "Users can now configure timeouts based on their specific use case requirements. ",
                "Long-form content generation is now much more reliable. ",
                "The implementation passes through all necessary parameters to the underlying httpx_ws library. ",
            ]
            for sentence in long_text:
                yield sentence

        # This should succeed with increased timeout
        audio_chunks = list(
            client.tts.stream_websocket(text_stream(), ws_options=ws_options)
        )

        assert len(audio_chunks) > 0, "Should receive audio chunks for very long text"
        complete_audio = b"".join(audio_chunks)
        # Very long text should produce substantial audio
        assert len(complete_audio) > 10000, (
            "Very long text should produce substantial audio data"
        )
        save_audio(audio_chunks, "test_websocket_very_long_with_timeout.mp3")


class TestAsyncTTSWebSocketIntegration:
    """Test async TTS WebSocket streaming with real API."""

    @pytest.mark.asyncio
    async def test_basic_async_websocket_streaming(self, async_client, save_audio):
        """Test basic async WebSocket streaming."""

        async def text_stream():
            yield "Hello, "
            yield "this is "
            yield "async streaming."

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(text_stream()):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0, "Should receive audio chunks"
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000, "Should have substantial audio data"

        save_audio(audio_chunks, "test_async_websocket_streaming.mp3")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "model",
        [
            pytest.param(
                m,
                marks=pytest.mark.xfail(
                    reason="WebSocket unreliable for legacy models"
                ),
            )
            if not m.startswith("s1")
            else m
            for m in get_args(Model)
        ],
    )
    async def test_async_websocket_streaming_with_model(
        self, async_client, save_audio, model
    ):
        """Test async WebSocket streaming with a specific model."""

        async def text_stream():
            yield f"Testing model {model} via async WebSocket."

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(
            text_stream(), model=model
        ):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0, f"Failed for model: {model}"

        # Write to output directory
        save_audio(audio_chunks, f"test_async_websocket_model_{model}.mp3")

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_with_format(
        self, async_client, save_audio
    ):
        """Test async WebSocket streaming with different formats."""
        config = TTSConfig(format="wav", chunk_length=200)

        async def text_stream():
            yield "Testing async "
            yield "WAV format."

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(
            text_stream(), config=config
        ):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_async_websocket_wav.wav")

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_with_prosody(
        self, async_client, save_audio
    ):
        """Test async WebSocket streaming with prosody."""
        prosody = Prosody(speed=0.8, volume=1.0)
        config = TTSConfig(prosody=prosody)

        async def text_stream():
            yield "This should "
            yield "sound slower "
            yield "than normal."

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(
            text_stream(), config=config
        ):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_async_websocket_prosody.mp3")

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_with_events(
        self, async_client, save_audio
    ):
        """Test async WebSocket streaming with text events."""

        async def text_stream():
            yield "First part. "
            yield TextEvent(text="Second part with event. ")
            yield FlushEvent()
            yield "Third part."

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(text_stream()):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        save_audio(audio_chunks, "test_async_websocket_events.mp3")

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_long_text(self, async_client, save_audio):
        """Test async WebSocket streaming with longer text."""

        async def text_stream():
            sentences = [
                "The quick brown fox jumps over the lazy dog. ",
                "This is an async streaming test with multiple chunks. ",
                "We're testing the async WebSocket implementation. ",
                "It should handle all chunks correctly. ",
                "And return complete audio data.",
            ]
            for sentence in sentences:
                yield sentence

        audio_chunks = []
        async for chunk in async_client.tts.stream_websocket(text_stream()):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 5000, "Should have more audio for longer text"
        save_audio(audio_chunks, "test_async_websocket_long_text.mp3")

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_multiple_calls(
        self, async_client, save_audio
    ):
        """Test multiple async WebSocket streaming calls in sequence."""
        import asyncio

        for i in range(3):

            async def text_stream():
                yield f"This is call number {i + 1}."

            audio_chunks = []
            async for chunk in async_client.tts.stream_websocket(text_stream()):
                audio_chunks.append(chunk)

            assert len(audio_chunks) > 0, f"Call {i + 1} should return audio"
            save_audio(audio_chunks, f"test_async_websocket_call_{i + 1}.mp3")

            # Brief delay to avoid SSL errors when opening next WebSocket connection
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_async_websocket_streaming_empty_text(self, async_client, save_audio):
        """Test async WebSocket streaming with empty text stream raises error."""
        from fishaudio.exceptions import WebSocketError

        async def text_stream():
            return
            yield  # Make it an async generator

        # Empty stream should raise WebSocketError as API returns error
        with pytest.raises(WebSocketError, match="WebSocket stream ended with error"):
            async for chunk in async_client.tts.stream_websocket(text_stream()):
                pass
