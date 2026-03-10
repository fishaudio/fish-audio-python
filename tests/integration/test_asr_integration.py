"""Integration tests for ASR functionality."""

from pathlib import Path

import pytest

from fishaudio.types import ASRResponse, TTSConfig

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"


class TestASRIntegration:
    """Test ASR with real API."""

    @pytest.fixture
    def sample_audio(self, client):
        """Generate sample audio for ASR testing."""
        # Generate audio from known text
        config = TTSConfig(format="wav")
        return client.tts.convert(text="Hello world, this is a test.", config=config)

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


class TestASRFromFileIntegration:
    """Test ASR using a sample audio file with known content."""

    @pytest.fixture
    def jfk_audio(self):
        """Load the JFK sample audio file."""
        return (SAMPLES_DIR / "jfk.wav").read_bytes()

    def test_asr_from_file(self, client, jfk_audio):
        """Test transcription of a known audio file."""
        result = client.asr.transcribe(audio=jfk_audio, language="en")

        assert isinstance(result, ASRResponse)
        assert result.duration > 0
        # JFK's famous quote
        text = result.text.lower()
        assert "ask not what your country can do for you" in text

    def test_asr_from_file_with_timestamps(self, client, jfk_audio):
        """Test transcription with timestamps from a known audio file."""
        result = client.asr.transcribe(audio=jfk_audio, language="en")

        assert len(result.segments) > 0
        for segment in result.segments:
            assert segment.text
            assert segment.start >= 0
            assert segment.end > segment.start

    def test_asr_from_file_without_timestamps(self, client, jfk_audio):
        """Test transcription without timestamps from a known audio file."""
        result = client.asr.transcribe(audio=jfk_audio, include_timestamps=False)

        assert isinstance(result, ASRResponse)
        assert result.text


class TestAsyncASRFromFileIntegration:
    """Test async ASR using a sample audio file."""

    @pytest.fixture
    def jfk_audio(self):
        """Load the JFK sample audio file."""
        return (SAMPLES_DIR / "jfk.wav").read_bytes()

    @pytest.mark.asyncio
    async def test_async_asr_from_file(self, async_client, jfk_audio):
        """Test async transcription of a known audio file."""
        result = await async_client.asr.transcribe(audio=jfk_audio, language="en")

        assert isinstance(result, ASRResponse)
        assert result.text
        assert result.duration > 0
        assert "ask not what your country can do for you" in result.text.lower()


class TestAsyncASRIntegration:
    """Test async ASR with real API."""

    @pytest.fixture
    async def async_sample_audio(self, async_client):
        """Generate sample audio for async ASR testing."""
        config = TTSConfig(format="wav")
        return await async_client.tts.convert(text="Async test audio", config=config)

    @pytest.mark.asyncio
    async def test_async_basic_asr(self, async_client, async_sample_audio):
        """Test basic async transcription."""
        result = await async_client.asr.transcribe(audio=async_sample_audio)

        assert isinstance(result, ASRResponse)
        assert result.text
        assert result.duration > 0
        assert len(result.segments) > 0
