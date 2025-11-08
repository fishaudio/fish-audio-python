"""Integration tests for Voices functionality."""

import pytest

from fishaudio.types import PaginatedResponse, Voice


class TestVoicesIntegration:
    """Test Voices with real API."""

    def test_list_voices(self, client):
        """Test listing available voices."""
        voices = client.voices.list(page_size=10)

        assert isinstance(voices, PaginatedResponse)
        assert voices.total >= 0
        assert len(voices.items) <= 10
        for voice in voices.items:
            assert isinstance(voice, Voice)
            assert voice.id
            assert voice.title

    def test_list_voices_with_filters(self, client):
        """Test listing voices with filters."""
        voices = client.voices.list(page_size=5, sort_by="created_at")

        assert len(voices.items) <= 5

    def test_list_self_voices(self, client):
        """Test listing only user's own voices."""
        voices = client.voices.list(page_size=10, self_only=True)

        assert isinstance(voices, PaginatedResponse)
        # All voices should belong to this user
        for voice in voices.items:
            assert isinstance(voice, Voice)

    def test_get_voice_by_id(self, client):
        """Test getting a specific voice by ID."""
        # First get a list to find a voice ID
        voices = client.voices.list(page_size=1)

        if voices.total > 0 and len(voices.items) > 0:
            voice_id = voices.items[0].id

            # Now get that specific voice
            voice = client.voices.get(voice_id)

            assert isinstance(voice, Voice)
            assert voice.id == voice_id
            assert voice.title
        else:
            pytest.skip("No voices available to test get()")

    def test_pagination(self, client):
        """Test voice pagination works."""
        page1 = client.voices.list(page_size=5, page_number=1)
        page2 = client.voices.list(page_size=5, page_number=2)

        # Both should be valid responses
        assert isinstance(page1, PaginatedResponse)
        assert isinstance(page2, PaginatedResponse)

        # If there are enough voices, items should be different
        if page1.total > 5:
            page1_ids = {v.id for v in page1.items}
            page2_ids = {v.id for v in page2.items}
            # Pages should have different voices
            assert page1_ids != page2_ids


class TestAsyncVoicesIntegration:
    """Test async Voices with real API."""

    @pytest.mark.asyncio
    async def test_async_list_voices(self, async_client):
        """Test listing voices async."""
        voices = await async_client.voices.list(page_size=10)

        assert isinstance(voices, PaginatedResponse)
        assert voices.total >= 0
        assert len(voices.items) <= 10

    @pytest.mark.asyncio
    async def test_async_get_voice(self, async_client):
        """Test getting voice by ID async."""
        voices = await async_client.voices.list(page_size=1)

        if voices.total > 0 and len(voices.items) > 0:
            voice_id = voices.items[0].id
            voice = await async_client.voices.get(voice_id)

            assert isinstance(voice, Voice)
            assert voice.id == voice_id
        else:
            pytest.skip("No voices available")
