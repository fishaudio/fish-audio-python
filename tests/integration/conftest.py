"""Fixtures for integration tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from fishaudio import AsyncFishAudio, FishAudio

load_dotenv()


def pytest_collection_modifyitems(items):
    """Mark all integration tests as flaky with auto-retry."""
    for item in items:
        # Check if test is in the integration directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.flaky(reruns=9, reruns_delay=1))


# Create output directory for test audio files
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Test reference voice ID for testing reference voice features
TEST_REFERENCE_ID = "ca3007f96ae7499ab87d27ea3599956a"


@pytest.fixture
def api_key():
    """Get API key from environment."""
    key = os.getenv("FISH_API_KEY")
    if not key:
        pytest.skip("No API key available (set FISH_API_KEY)")
    return key


@pytest.fixture(scope="function")
def client(api_key):
    """Sync Fish Audio client (function-scoped for test isolation)."""
    import time

    client = FishAudio(api_key=api_key)
    yield client
    client.close()
    # Brief delay to avoid API rate limits on WebSocket connections
    time.sleep(0.3)


@pytest.fixture
async def async_client(api_key):
    """Async Fish Audio client."""
    import asyncio

    client = AsyncFishAudio(api_key=api_key)
    yield client
    await client.close()
    # Brief delay to avoid API rate limits on WebSocket connections
    await asyncio.sleep(0.3)


@pytest.fixture
def save_audio():
    """Fixture that provides a helper to save audio chunks to the output directory.

    Returns:
        A callable that takes audio chunks and filename and saves to output/
    """

    def _save(audio: bytes | list[bytes], filename: str) -> Path:
        """Save audio to output directory.

        Args:
            audio: Audio bytes or list of audio byte chunks
            filename: Name of the output file (including extension)

        Returns:
            Path to the saved file
        """
        if isinstance(audio, bytes):
            complete_audio = audio
        else:
            complete_audio = b"".join(audio)
        output_file = OUTPUT_DIR / filename
        output_file.write_bytes(complete_audio)
        return output_file

    return _save
