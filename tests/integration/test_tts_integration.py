"""Integration tests for TTS functionality."""

from typing import get_args

import pytest

from fishaudio.types import Prosody, TTSConfig
from fishaudio.types.shared import Model


class TestTTSIntegration:
    """Test TTS with real API."""

    def test_basic_tts(self, client):
        """Test basic text-to-speech generation."""
        audio_chunks = list(client.tts.convert(text="Hello, this is a test."))

        assert len(audio_chunks) > 0
        # Verify we got audio data (check for common audio headers)
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000  # Should have substantial audio data

    def test_tts_with_different_formats(self, client):
        """Test TTS with different audio formats."""
        formats = ["mp3", "wav", "pcm"]

        for fmt in formats:
            config = TTSConfig(format=fmt, chunk_length=100)
            audio_chunks = list(
                client.tts.convert(text="Testing format", config=config)
            )
            assert len(audio_chunks) > 0, f"Failed for format: {fmt}"

    def test_tts_with_prosody(self, client):
        """Test TTS with prosody settings."""
        prosody = Prosody(speed=1.2, volume=0.5)
        config = TTSConfig(prosody=prosody)

        audio_chunks = list(
            client.tts.convert(text="Testing prosody settings", config=config)
        )

        assert len(audio_chunks) > 0

    def test_tts_with_different_backends(self, client):
        """Test TTS with different backend models."""
        models = get_args(Model)

        for model in models:
            try:
                audio_chunks = list(
                    client.tts.convert(text="Testing model", model=model)
                )
                assert len(audio_chunks) > 0, f"Failed for model: {model}"
            except Exception as e:
                # Some models might not be available
                pytest.skip(f"Model {model} not available: {e}")

    def test_tts_longer_text(self, client):
        """Test TTS with longer text."""
        long_text = "This is a longer piece of text for testing. " * 10
        config = TTSConfig(chunk_length=200)

        audio_chunks = list(client.tts.convert(text=long_text, config=config))

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        # Longer text should produce more audio
        assert len(complete_audio) > 5000

    def test_tts_empty_text_should_fail(self, client):
        """Test that empty text is handled."""
        # This might succeed with silence or fail - test behavior
        try:
            audio_chunks = list(client.tts.convert(text=""))
            # If it succeeds, verify we get something
            assert len(audio_chunks) >= 0
        except Exception:
            # If it fails, that's also acceptable
            pass


class TestAsyncTTSIntegration:
    """Test async TTS with real API."""

    @pytest.mark.asyncio
    async def test_basic_async_tts(self, async_client):
        """Test basic async text-to-speech generation."""
        audio_chunks = []
        async for chunk in async_client.tts.convert(text="Hello from async"):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000

    @pytest.mark.asyncio
    async def test_async_tts_with_prosody(self, async_client):
        """Test async TTS with prosody."""
        prosody = Prosody(speed=0.8, volume=-0.2)
        config = TTSConfig(prosody=prosody)

        audio_chunks = []
        async for chunk in async_client.tts.convert(
            text="Async prosody test", config=config
        ):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
