"""Integration tests for TTS WebSocket streaming functionality."""

import pytest

from fishaudio.types import Prosody, TTSConfig, TextEvent, FlushEvent
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
        for i in range(3):

            async def text_stream():
                yield f"This is call number {i + 1}."

            audio_chunks = []
            async for chunk in async_client.tts.stream_websocket(text_stream()):
                audio_chunks.append(chunk)

            assert len(audio_chunks) > 0, f"Call {i + 1} should return audio"
            save_audio(audio_chunks, f"test_async_websocket_call_{i + 1}.mp3")

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
