"""
Fish Audio Python SDK.

A professional Python SDK for Fish Audio's text-to-speech and voice cloning API.

Example:
    ```python
    from fishaudio import FishAudio, play, save

    # Initialize client
    client = FishAudio(api_key="your_api_key")

    # Generate speech
    audio = client.tts.convert(text="Hello, world!")

    # Play it
    play(audio)

    # Or save it
    save(audio, "output.mp3")

    # List available voices
    voices = client.voices.list()
    for voice in voices.items:
        print(f"{voice.title}: {voice.id}")
    ```
"""

from ._version import __version__
from .client import AsyncFishAudio, FishAudio
from .core.iterators import AsyncAudioStream, AudioStream
from .core.websocket_options import WebSocketOptions
from .exceptions import (
    APIError,
    AuthenticationError,
    DependencyError,
    FishAudioError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    ValidationError,
    WebSocketError,
)
from .types import FlushEvent, ReferenceAudio, TextEvent, TTSConfig
from .utils import play, save, stream

# Main exports
__all__ = [
    # Main clients
    "FishAudio",
    "AsyncFishAudio",
    # Utilities
    "play",
    "save",
    "stream",
    # Audio streams
    "AudioStream",
    "AsyncAudioStream",
    # Configuration
    "TTSConfig",
    "WebSocketOptions",
    # Types
    "FlushEvent",
    "ReferenceAudio",
    "TextEvent",
    # Exceptions
    "APIError",
    "AuthenticationError",
    "DependencyError",
    "FishAudioError",
    "NotFoundError",
    "PermissionError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
    "WebSocketError",
    # Version
    "__version__",
]
