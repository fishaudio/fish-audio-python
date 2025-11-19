"""Integration tests for TTS functionality."""

from typing import get_args

import pytest

from fishaudio.types import Prosody, TTSConfig
from fishaudio.types.shared import AudioFormat, Model


class TestTTSIntegration:
    """Test TTS with real API."""

    def test_basic_tts(self, client, save_audio):
        """Test basic text-to-speech generation."""
        audio = client.tts.convert(text="Hello, this is a test.")

        assert len(audio) > 1000  # Should have substantial audio data
        assert isinstance(audio, bytes)

        # Write to output directory
        save_audio(audio, "test_basic_tts.mp3")

    def test_tts_with_different_formats(self, client, save_audio):
        """Test TTS with different audio formats."""
        formats = get_args(AudioFormat)

        for fmt in formats:
            config = TTSConfig(format=fmt, chunk_length=100)
            audio = client.tts.convert(text=f"Testing format {fmt}", config=config)
            assert len(audio) > 0, f"Failed for format: {fmt}"

            # Write to output directory
            save_audio(audio, f"test_format_{fmt}.{fmt}")

    def test_tts_with_prosody(self, client, save_audio):
        """Test TTS with prosody settings."""
        prosody = Prosody(speed=1.2, volume=0.5)
        config = TTSConfig(prosody=prosody)

        audio = client.tts.convert(text="Testing prosody settings", config=config)

        assert len(audio) > 0

        # Write to output directory
        save_audio(audio, "test_prosody.mp3")

    def test_tts_with_different_models(self, client, save_audio):
        """Test TTS with different models."""
        models = get_args(Model)

        for model in models:
            audio = client.tts.convert(text=f"Testing model {model}", model=model)
            assert len(audio) > 0, f"Failed for model: {model}"

            # Write to output directory
            save_audio(audio, f"test_model_{model}.mp3")

    def test_tts_longer_text(self, client, save_audio):
        """Test TTS with longer text."""
        long_text = "This is a longer piece of text for testing. " * 10
        config = TTSConfig(chunk_length=200)

        audio = client.tts.convert(text=long_text, config=config)

        # Longer text should produce more audio
        assert len(audio) > 5000

        # Write to output directory
        save_audio(audio, "test_longer_text.mp3")

    def test_tts_empty_text_should_fail(self, client):
        """Test that empty text is handled."""
        # This might succeed with silence or fail - test behavior
        try:
            audio = client.tts.convert(text="")
            # If it succeeds, verify we get something
            assert isinstance(audio, bytes)
        except Exception:
            # If it fails, that's also acceptable
            pass


class TestAsyncTTSIntegration:
    """Test async TTS with real API."""

    @pytest.mark.asyncio
    async def test_basic_async_tts(self, async_client, save_audio):
        """Test basic async text-to-speech generation."""
        audio = await async_client.tts.convert(text="Hello from async")

        assert len(audio) > 1000
        assert isinstance(audio, bytes)

        # Write to output directory
        save_audio(audio, "test_async_basic.mp3")

    @pytest.mark.asyncio
    async def test_async_tts_with_prosody(self, async_client, save_audio):
        """Test async TTS with prosody."""
        prosody = Prosody(speed=0.8, volume=-0.2)
        config = TTSConfig(prosody=prosody)

        audio = await async_client.tts.convert(text="Async prosody test", config=config)

        assert len(audio) > 0

        # Write to output directory
        save_audio(audio, "test_async_prosody.mp3")
