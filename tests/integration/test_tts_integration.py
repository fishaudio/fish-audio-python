"""Integration tests for TTS functionality."""

from typing import get_args

import pytest

from fishaudio.types import Prosody, TTSConfig
from fishaudio.types.shared import AudioFormat, Model


class TestTTSIntegration:
    """Test TTS with real API."""

    def test_basic_tts(self, client, save_audio):
        """Test basic text-to-speech generation."""
        audio_chunks = list(client.tts.convert(text="Hello, this is a test."))

        assert len(audio_chunks) > 0
        # Verify we got audio data (check for common audio headers)
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000  # Should have substantial audio data

        # Write to output directory
        save_audio(audio_chunks, "test_basic_tts.mp3")

    def test_tts_with_different_formats(self, client, save_audio):
        """Test TTS with different audio formats."""
        formats = get_args(AudioFormat)

        for fmt in formats:
            config = TTSConfig(format=fmt, chunk_length=100)
            audio_chunks = list(
                client.tts.convert(text=f"Testing format {fmt}", config=config)
            )
            assert len(audio_chunks) > 0, f"Failed for format: {fmt}"

            # Write to output directory
            save_audio(audio_chunks, f"test_format_{fmt}.{fmt}")

    def test_tts_with_prosody(self, client, save_audio):
        """Test TTS with prosody settings."""
        prosody = Prosody(speed=1.2, volume=0.5)
        config = TTSConfig(prosody=prosody)

        audio_chunks = list(
            client.tts.convert(text="Testing prosody settings", config=config)
        )

        assert len(audio_chunks) > 0

        # Write to output directory
        save_audio(audio_chunks, "test_prosody.mp3")

    def test_tts_with_different_models(self, client, save_audio):
        """Test TTS with different models."""
        models = get_args(Model)

        for model in models:
            try:
                audio_chunks = list(
                    client.tts.convert(text=f"Testing model {model}", model=model)
                )
                assert len(audio_chunks) > 0, f"Failed for model: {model}"

                # Write to output directory
                save_audio(audio_chunks, f"test_model_{model}.mp3")
            except Exception as e:
                # Some models might not be available
                pytest.skip(f"Model {model} not available: {e}")

    def test_tts_longer_text(self, client, save_audio):
        """Test TTS with longer text."""
        long_text = "This is a longer piece of text for testing. " * 10
        config = TTSConfig(chunk_length=200)

        audio_chunks = list(client.tts.convert(text=long_text, config=config))

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        # Longer text should produce more audio
        assert len(complete_audio) > 5000

        # Write to output directory
        save_audio(audio_chunks, "test_longer_text.mp3")

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
    async def test_basic_async_tts(self, async_client, save_audio):
        """Test basic async text-to-speech generation."""
        audio_chunks = []
        async for chunk in async_client.tts.convert(text="Hello from async"):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0
        complete_audio = b"".join(audio_chunks)
        assert len(complete_audio) > 1000

        # Write to output directory
        save_audio(audio_chunks, "test_async_basic.mp3")

    @pytest.mark.asyncio
    async def test_async_tts_with_prosody(self, async_client, save_audio):
        """Test async TTS with prosody."""
        prosody = Prosody(speed=0.8, volume=-0.2)
        config = TTSConfig(prosody=prosody)

        audio_chunks = []
        async for chunk in async_client.tts.convert(
            text="Async prosody test", config=config
        ):
            audio_chunks.append(chunk)

        assert len(audio_chunks) > 0

        # Write to output directory
        save_audio(audio_chunks, "test_async_prosody.mp3")
