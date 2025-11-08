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
