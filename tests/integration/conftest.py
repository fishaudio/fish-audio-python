"""Fixtures for integration tests."""

import os

import pytest
from dotenv import load_dotenv

from fishaudio import AsyncFishAudio, FishAudio

load_dotenv()


@pytest.fixture
def api_key():
    """Get API key from environment."""
    key = os.getenv("FISH_AUDIO_API_KEY")
    if not key:
        pytest.skip("No API key available (set FISH_AUDIO_API_KEY)")
    return key


@pytest.fixture
def client(api_key):
    """Sync Fish Audio client."""
    client = FishAudio(api_key=api_key)
    yield client
    client.close()


@pytest.fixture
async def async_client(api_key):
    """Async Fish Audio client."""
    client = AsyncFishAudio(api_key=api_key)
    yield client
    await client.close()
