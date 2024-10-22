import os

import pytest

from fish_audio_sdk import Session, WebSocketSession, AsyncWebSocketSession

APIKEY = os.environ["APIKEY"]


@pytest.fixture
def session():
    return Session(APIKEY)


@pytest.fixture
def sync_websocket():
    return WebSocketSession(APIKEY)


@pytest.fixture
def async_websocket():
    return AsyncWebSocketSession(APIKEY)
