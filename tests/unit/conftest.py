"""Shared pytest fixtures for unit tests."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest


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
    """Sample ASR API response (times in seconds)."""
    return {
        "text": "Hello world",
        "duration": 1.5,
        "segments": [
            {"text": "Hello", "start": 0.0, "end": 0.5},
            {"text": "world", "start": 0.5, "end": 1.5},
        ],
    }


@pytest.fixture
def sample_asr_standard_response():
    """Sample transcribe-1 ASR API response with timestamps requested."""
    return {
        "language": "English",
        "language_code": "en",
        "text": "Hello, world.",
        "segments": [
            {"text": "Hello", "start": 0.24, "end": 0.64},
            {"text": "world", "start": 0.64, "end": 1.2},
        ],
        "duration": 1.62,
    }


@pytest.fixture
def sample_asr_pro_response():
    """Sample transcribe-1-pro ASR API response with timestamps requested."""
    return {
        "duration": 3.5,
        "language": "English",
        "language_code": "en",
        "request_id": "0b9e4f5c-7d2a-4f1e-9c3b-5a8d6e2f1c07",
        "segments": [
            {"end": 0.64, "start": 0.24, "text": "Hello"},
            {"end": 1.2, "start": 0.64, "text": "there"},
            {"end": 2.1, "start": 1.8, "text": "Hi"},
            {"end": 3.1, "start": 2.1, "text": "back"},
        ],
        "speaker_turns": [
            {"speaker": "speaker:0", "text": "Hello there.", "start": 0.24, "end": 1.2},
            {"speaker": "speaker:1", "text": "Hi back.", "start": 1.8, "end": 3.1},
        ],
        "text": "<|speaker:0|>Hello there.<|speaker:1|>Hi back.",
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
