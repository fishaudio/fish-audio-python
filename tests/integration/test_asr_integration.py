"""Integration tests for ASR functionality."""

import pytest

from fishaudio.types import ASRResponse, TTSConfig


class TestASRIntegration:
    """Test ASR with real API."""

    @pytest.fixture
    def sample_audio(self, client):
        """Generate sample audio for ASR testing."""
        # Generate audio from known text
        config = TTSConfig(format="wav")
        audio_chunks = list(
            client.tts.convert(text="Hello world, this is a test.", config=config)
        )
        return b"".join(audio_chunks)

    def test_basic_asr(self, client, sample_audio):
        """Test basic speech-to-text transcription."""
        result = client.asr.transcribe(audio=sample_audio)

        assert isinstance(result, ASRResponse)
        assert result.text  # Should have transcribed text
        assert result.duration > 0
        assert len(result.segments) > 0
        # Verify segments have timestamps
        for segment in result.segments:
            assert segment.text
            assert segment.start >= 0
            assert segment.end > segment.start

    def test_asr_with_language(self, client, sample_audio):
        """Test ASR with language specification."""
        result = client.asr.transcribe(audio=sample_audio, language="en")

        assert isinstance(result, ASRResponse)
        assert result.text

    def test_asr_without_timestamps(self, client, sample_audio):
        """Test ASR without timestamp information."""
        result = client.asr.transcribe(audio=sample_audio, include_timestamps=False)

        assert isinstance(result, ASRResponse)
        assert result.text
        # Segments might still be present but potentially empty or without timing


class TestAsyncASRIntegration:
    """Test async ASR with real API."""

    @pytest.fixture
    async def async_sample_audio(self, async_client):
        """Generate sample audio for async ASR testing."""
        audio_chunks = []
        config = TTSConfig(format="wav")
        async for chunk in async_client.tts.convert(
            text="Async test audio", config=config
        ):
            audio_chunks.append(chunk)
        return b"".join(audio_chunks)

    @pytest.mark.asyncio
    async def test_async_basic_asr(self, async_client, async_sample_audio):
        """Test basic async transcription."""
        result = await async_client.asr.transcribe(audio=async_sample_audio)

        assert isinstance(result, ASRResponse)
        assert result.text
        assert result.duration > 0
        assert len(result.segments) > 0
