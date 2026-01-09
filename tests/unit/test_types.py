"""Tests for type definitions."""

from decimal import Decimal

from fishaudio.types import (
    Voice,
    PaginatedResponse,
    ASRResponse,
    ASRSegment,
    Credits,
    Package,
    ReferenceAudio,
    Prosody,
    TTSConfig,
    TTSRequest,
)


class TestVoice:
    """Test Voice model."""

    def test_voice_from_dict(self, sample_voice_response):
        voice = Voice.model_validate(sample_voice_response)
        assert voice.id == "voice123"
        assert voice.title == "Test Voice"
        assert voice.type == "tts"
        assert voice.state == "trained"
        assert len(voice.tags) == 2
        assert voice.author.id == "author123"

    def test_voice_alias_mapping(self, sample_voice_response):
        # Test that _id gets mapped to id
        voice = Voice.model_validate(sample_voice_response)
        assert voice.id == sample_voice_response["_id"]


class TestPaginatedResponse:
    """Test PaginatedResponse model."""

    def test_paginated_voices(self, sample_paginated_voices_response):
        paginated = PaginatedResponse[Voice].model_validate(
            sample_paginated_voices_response
        )
        assert paginated.total == 1
        assert len(paginated.items) == 1
        assert isinstance(paginated.items[0], Voice)
        assert paginated.items[0].id == "voice123"


class TestASRTypes:
    """Test ASR-related types."""

    def test_asr_segment(self):
        segment = ASRSegment(text="Hello", start=0.0, end=500.0)
        assert segment.text == "Hello"
        assert segment.start == 0.0
        assert segment.end == 500.0

    def test_asr_response(self, sample_asr_response):
        response = ASRResponse.model_validate(sample_asr_response)
        assert response.text == "Hello world"
        assert response.duration == 1500.0
        assert len(response.segments) == 2
        assert isinstance(response.segments[0], ASRSegment)


class TestAccountTypes:
    """Test account-related types."""

    def test_credits(self, sample_credits_response):
        credits = Credits.model_validate(sample_credits_response)
        assert credits.id == "credit123"
        assert credits.user_id == "user123"
        assert isinstance(credits.credit, Decimal)
        assert credits.credit == Decimal("100.50")

    def test_package(self, sample_package_response):
        package = Package.model_validate(sample_package_response)
        assert package.id == "package123"
        assert package.total == 1000
        assert package.balance == 750


class TestTTSTypes:
    """Test TTS-related types."""

    def test_reference_audio(self):
        ref = ReferenceAudio(audio=b"audio_data", text="Sample text")
        assert ref.audio == b"audio_data"
        assert ref.text == "Sample text"

    def test_prosody_defaults(self):
        prosody = Prosody()
        assert prosody.speed == 1.0
        assert prosody.volume == 0.0

    def test_prosody_custom(self):
        prosody = Prosody(speed=1.5, volume=0.5)
        assert prosody.speed == 1.5
        assert prosody.volume == 0.5

    def test_tts_config_defaults(self):
        """Test TTSConfig default values including new parameters."""
        config = TTSConfig()
        # Existing defaults
        assert config.format == "mp3"
        assert config.mp3_bitrate == 128
        assert config.opus_bitrate == 32
        assert config.normalize is True
        assert config.chunk_length == 200
        assert config.latency == "balanced"
        assert config.top_p == 0.7
        assert config.temperature == 0.7
        # New parameter defaults
        assert config.max_new_tokens == 1024
        assert config.repetition_penalty == 1.2
        assert config.min_chunk_length == 50
        assert config.condition_on_previous_chunks is True
        assert config.early_stop_threshold == 1.0

    def test_tts_config_custom_new_parameters(self):
        """Test TTSConfig with custom values for new parameters."""
        config = TTSConfig(
            max_new_tokens=2048,
            repetition_penalty=1.5,
            min_chunk_length=100,
            condition_on_previous_chunks=False,
            early_stop_threshold=0.8,
        )
        assert config.max_new_tokens == 2048
        assert config.repetition_penalty == 1.5
        assert config.min_chunk_length == 100
        assert config.condition_on_previous_chunks is False
        assert config.early_stop_threshold == 0.8

    def test_tts_request_defaults(self):
        """Test TTSRequest default values including new parameters."""
        request = TTSRequest(text="Hello world")
        # Existing defaults
        assert request.text == "Hello world"
        assert request.format == "mp3"
        assert request.chunk_length == 200
        assert request.latency == "balanced"
        # New parameter defaults
        assert request.max_new_tokens == 1024
        assert request.repetition_penalty == 1.2
        assert request.min_chunk_length == 50
        assert request.condition_on_previous_chunks is True
        assert request.early_stop_threshold == 1.0

    def test_tts_request_custom_new_parameters(self):
        """Test TTSRequest with custom values for new parameters."""
        request = TTSRequest(
            text="Hello world",
            max_new_tokens=512,
            repetition_penalty=1.0,
            min_chunk_length=25,
            condition_on_previous_chunks=False,
            early_stop_threshold=0.5,
        )
        assert request.max_new_tokens == 512
        assert request.repetition_penalty == 1.0
        assert request.min_chunk_length == 25
        assert request.condition_on_previous_chunks is False
        assert request.early_stop_threshold == 0.5


class TestVoiceVisibility:
    """Test Voice model with updated visibility."""

    def test_voice_with_unlisted_visibility(self, sample_voice_response):
        """Test Voice model with 'unlisted' visibility."""
        sample_voice_response["visibility"] = "unlisted"
        voice = Voice.model_validate(sample_voice_response)
        assert voice.visibility == "unlisted"
