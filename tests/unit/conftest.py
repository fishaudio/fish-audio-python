"""Shared pytest fixtures for unit tests."""

import pytest
from unittest.mock import Mock, AsyncMock
import httpx


@pytest.fixture
def mock_api_key():
    """Mock API key for testing."""
    return "test_api_key_12345"


@pytest.fixture
def mock_base_url():
    """Mock base URL for testing."""
    return "https://api.test.fish.audio"


@pytest.fixture
def sample_voice_response():
    """Sample voice API response."""
    return {
        "_id": "voice123",
        "type": "tts",
        "title": "Test Voice",
        "description": "A test voice",
        "cover_image": "https://example.com/image.jpg",
        "train_mode": "fast",
        "state": "trained",
        "tags": ["test", "english"],
        "samples": [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "languages": ["en"],
        "visibility": "private",
        "lock_visibility": False,
        "like_count": 0,
        "mark_count": 0,
        "shared_count": 0,
        "task_count": 0,
        "liked": False,
        "marked": False,
        "author": {
            "_id": "author123",
            "nickname": "Test Author",
            "avatar": "https://example.com/avatar.jpg",
        },
    }


@pytest.fixture
def sample_paginated_voices_response(sample_voice_response):
    """Sample paginated voices API response."""
    return {"total": 1, "items": [sample_voice_response]}


@pytest.fixture
def sample_asr_response():
    """Sample ASR API response."""
    return {
        "text": "Hello world",
        "duration": 1500.0,
        "segments": [
            {"text": "Hello", "start": 0.0, "end": 500.0},
            {"text": "world", "start": 500.0, "end": 1500.0},
        ],
    }


@pytest.fixture
def sample_credits_response():
    """Sample credits API response."""
    return {
        "id": "credit123",
        "user_id": "user123",
        "credit": "100.50",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_package_response():
    """Sample package API response."""
    return {
        "id": "package123",
        "user_id": "user123",
        "type": "standard",
        "total": 1000,
        "balance": 750,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-12-31T23:59:59Z",
    }


def create_mock_response(status_code=200, json_data=None, content=b""):
    """Create a mock httpx.Response."""
    response = Mock(spec=httpx.Response)
    response.status_code = status_code
    response.is_success = 200 <= status_code < 300
    response.json = Mock(return_value=json_data or {})
    response.text = str(json_data) if json_data else ""
    response.content = content
    response.iter_bytes = Mock(return_value=iter([content]))
    response.aiter_bytes = AsyncMock(return_value=iter([content]))
    return response
