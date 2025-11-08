"""Type definitions for the Fish Audio SDK."""

from .account import Credits, Package
from .asr import ASRResponse, ASRSegment
from .shared import (
    AudioFormat,
    LatencyMode,
    Model,
    ModelState,
    PaginatedResponse,
    TrainMode,
    Visibility,
)
from .tts import (
    CloseEvent,
    FlushEvent,
    Prosody,
    ReferenceAudio,
    StartEvent,
    TextEvent,
    TTSConfig,
    TTSRequest,
)
from .voices import Author, Sample, Voice

__all__ = [
    # Account types
    "Credits",
    "Package",
    # ASR types
    "ASRResponse",
    "ASRSegment",
    # Shared types
    "AudioFormat",
    "LatencyMode",
    "Model",
    "ModelState",
    "PaginatedResponse",
    "TrainMode",
    "Visibility",
    # TTS types
    "CloseEvent",
    "FlushEvent",
    "Prosody",
    "ReferenceAudio",
    "StartEvent",
    "TextEvent",
    "TTSConfig",
    "TTSRequest",
    # Voice types
    "Author",
    "Sample",
    "Voice",
]
