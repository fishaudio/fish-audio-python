"""Tests for main client classes."""

import pytest
from unittest.mock import patch

from fishaudio import FishAudio, AsyncFishAudio
from fishaudio.resources import (
    TTSClient,
    AsyncTTSClient,
    VoicesClient,
    AsyncVoicesClient,
)


class TestFishAudio:
    """Test sync FishAudio client."""

    def test_init_with_api_key(self, mock_api_key):
        client = FishAudio(api_key=mock_api_key)
        assert client._client_wrapper.api_key == mock_api_key

    def test_init_with_env_var(self, mock_api_key):
        with patch.dict("os.environ", {"FISH_AUDIO_API_KEY": mock_api_key}):
            client = FishAudio()
            assert client._client_wrapper.api_key == mock_api_key

    def test_init_with_custom_base_url(self, mock_api_key, mock_base_url):
        client = FishAudio(api_key=mock_api_key, base_url=mock_base_url)
        assert client._client_wrapper.base_url == mock_base_url

    def test_tts_lazy_loading(self, mock_api_key):
        client = FishAudio(api_key=mock_api_key)
        assert client._tts is None  # Not loaded yet
        tts = client.tts
        assert client._tts is not None  # Now loaded
        assert isinstance(tts, TTSClient)
        # Second access returns same instance
        assert client.tts is tts

    def test_asr_lazy_loading(self, mock_api_key):
        client = FishAudio(api_key=mock_api_key)
        assert client._asr is None
        asr = client.asr
        assert client._asr is not None
        assert client.asr is asr

    def test_voices_lazy_loading(self, mock_api_key):
        client = FishAudio(api_key=mock_api_key)
        assert client._voices is None
        voices = client.voices
        assert client._voices is not None
        assert isinstance(voices, VoicesClient)

    def test_account_lazy_loading(self, mock_api_key):
        client = FishAudio(api_key=mock_api_key)
        assert client._account is None
        _ = client.account
        assert client._account is not None

    def test_context_manager(self, mock_api_key):
        with FishAudio(api_key=mock_api_key) as client:
            assert client._client_wrapper is not None


class TestAsyncFishAudio:
    """Test async AsyncFishAudio client."""

    def test_init_with_api_key(self, mock_api_key):
        client = AsyncFishAudio(api_key=mock_api_key)
        assert client._client_wrapper.api_key == mock_api_key

    def test_init_with_custom_base_url(self, mock_api_key, mock_base_url):
        client = AsyncFishAudio(api_key=mock_api_key, base_url=mock_base_url)
        assert client._client_wrapper.base_url == mock_base_url

    def test_tts_lazy_loading(self, mock_api_key):
        client = AsyncFishAudio(api_key=mock_api_key)
        assert client._tts is None
        tts = client.tts
        assert client._tts is not None
        assert isinstance(tts, AsyncTTSClient)
        assert client.tts is tts

    def test_voices_lazy_loading(self, mock_api_key):
        client = AsyncFishAudio(api_key=mock_api_key)
        assert client._voices is None
        voices = client.voices
        assert client._voices is not None
        assert isinstance(voices, AsyncVoicesClient)

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_api_key):
        async with AsyncFishAudio(api_key=mock_api_key) as client:
            assert client._client_wrapper is not None
