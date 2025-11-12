"""TTS-related types."""

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .shared import AudioFormat, LatencyMode


class ReferenceAudio(BaseModel):
    """Reference audio for voice cloning/style."""

    audio: bytes
    text: str


class Prosody(BaseModel):
    """Speech prosody settings (speed and volume)."""

    speed: Annotated[float, Field(ge=0.5, le=2.0)] = 1.0
    volume: Annotated[float, Field(ge=-20.0, le=20.0)] = 0.0

    @classmethod
    def from_speed_override(
        cls, speed: float, base: Optional["Prosody"] = None
    ) -> "Prosody":
        """
        Create Prosody with speed override, preserving volume from base.

        Args:
            speed: Speed value to use
            base: Base prosody to preserve volume from (if any)

        Returns:
            New Prosody instance with overridden speed
        """
        if base:
            return cls(speed=speed, volume=base.volume)
        return cls(speed=speed)


class TTSConfig(BaseModel):
    """
    TTS generation configuration.

    Reusable configuration for text-to-speech requests. Create once, use multiple times.
    All parameters have sensible defaults.
    """

    # Audio output settings
    format: AudioFormat = "mp3"
    sample_rate: Optional[int] = None
    mp3_bitrate: Literal[64, 128, 192] = 128
    opus_bitrate: Literal[-1000, 24, 32, 48, 64] = 32
    normalize: bool = True

    # Generation settings
    chunk_length: Annotated[int, Field(ge=100, le=300, strict=True)] = 200
    latency: LatencyMode = "balanced"

    # Voice/style settings
    reference_id: Optional[str] = None
    references: List[ReferenceAudio] = []
    prosody: Optional[Prosody] = None

    # Model parameters
    top_p: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7
    temperature: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7


class TTSRequest(BaseModel):
    """
    Request parameters for text-to-speech generation.

    This model is used internally for WebSocket streaming.
    For the HTTP API, parameters are passed directly to methods.
    """

    text: str
    chunk_length: Annotated[int, Field(ge=100, le=300, strict=True)] = 200
    format: AudioFormat = "mp3"
    sample_rate: Optional[int] = None
    mp3_bitrate: Literal[64, 128, 192] = 128
    opus_bitrate: Literal[-1000, 24, 32, 48, 64] = 32
    references: List[ReferenceAudio] = []
    reference_id: Optional[str] = None
    normalize: bool = True
    latency: LatencyMode = "balanced"
    prosody: Optional[Prosody] = None
    top_p: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7
    temperature: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7


# WebSocket event types for streaming TTS
class StartEvent(BaseModel):
    """WebSocket start event."""

    event: Literal["start"] = "start"
    request: TTSRequest


class TextEvent(BaseModel):
    """WebSocket text chunk event."""

    event: Literal["text"] = "text"
    text: str


class FlushEvent(BaseModel):
    """WebSocket flush event - forces buffer to generate audio immediately."""

    event: Literal["flush"] = "flush"


class CloseEvent(BaseModel):
    """WebSocket close event."""

    event: Literal["stop"] = "stop"
