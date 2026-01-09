"""TTS-related types."""

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .shared import AudioFormat, LatencyMode


class ReferenceAudio(BaseModel):
    """Reference audio for voice cloning/style.

    Attributes:
        audio: Audio file bytes for the reference sample
        text: Transcription of what is spoken in the reference audio. Should match exactly
            what's spoken and include punctuation for proper prosody.
    """

    audio: bytes
    text: str


class Prosody(BaseModel):
    """Speech prosody settings (speed and volume).

    Attributes:
        speed: Speech speed multiplier. Range: 0.5-2.0. Default: 1.0.
            Examples: 1.5 = 50% faster, 0.8 = 20% slower
        volume: Volume adjustment in decibels. Range: -20.0 to 20.0. Default: 0.0 (no change).
            Positive values increase volume, negative values decrease it.
    """

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

    Attributes:
        format: Audio output format. Options: "mp3", "wav", "pcm", "opus". Default: "mp3"
        sample_rate: Audio sample rate in Hz. If None, uses format-specific default.
        mp3_bitrate: MP3 bitrate in kbps. Options: 64, 128, 192. Default: 128
        opus_bitrate: Opus bitrate in kbps. Options: -1000, 24, 32, 48, 64. Default: 32
        normalize: Whether to normalize/clean the input text. Default: True
        chunk_length: Characters per generation chunk. Range: 100-300. Default: 200.
            Lower values = faster initial response, higher values = better quality
        latency: Generation mode. Options: "normal" (higher quality), "balanced" (faster). Default: "balanced"
        reference_id: Voice model ID from fish.audio (e.g., "802e3bc2b27e49c2995d23ef70e6ac89").
            Find IDs in voice URLs or via voices.list()
        references: List of reference audio samples for instant voice cloning. Default: []
        prosody: Speech speed and volume settings. Default: None (uses natural prosody)
        top_p: Nucleus sampling parameter for token selection. Range: 0.0-1.0. Default: 0.7
        temperature: Randomness in generation. Range: 0.0-1.0. Default: 0.7.
            Higher = more varied, lower = more consistent
        max_new_tokens: Maximum number of tokens to generate. Default: 1024
        repetition_penalty: Penalty for repeated tokens. Default: 1.2
        min_chunk_length: Minimum chunk length for generation. Default: 50
        condition_on_previous_chunks: Whether to condition generation on previous chunks. Default: True
        early_stop_threshold: Threshold for early stopping. Default: 1.0
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

    # Advanced generation parameters
    max_new_tokens: int = 1024
    repetition_penalty: float = 1.2
    min_chunk_length: int = 50
    condition_on_previous_chunks: bool = True
    early_stop_threshold: float = 1.0


class TTSRequest(BaseModel):
    """
    Request parameters for text-to-speech generation.

    This model is used internally for WebSocket streaming.
    For the HTTP API, parameters are passed directly to methods.

    Attributes:
        text: Text to synthesize into speech
        chunk_length: Characters per generation chunk. Range: 100-300. Default: 200
        format: Audio output format. Options: "mp3", "wav", "pcm", "opus". Default: "mp3"
        sample_rate: Audio sample rate in Hz. If None, uses format-specific default
        mp3_bitrate: MP3 bitrate in kbps. Options: 64, 128, 192. Default: 128
        opus_bitrate: Opus bitrate in kbps. Options: -1000, 24, 32, 48, 64. Default: 32
        references: List of reference audio samples for voice cloning. Default: []
        reference_id: Voice model ID for using a specific voice. Default: None
        normalize: Whether to normalize/clean the input text. Default: True
        latency: Generation mode. Options: "normal", "balanced". Default: "balanced"
        prosody: Speech speed and volume settings. Default: None
        top_p: Nucleus sampling for token selection. Range: 0.0-1.0. Default: 0.7
        temperature: Randomness in generation. Range: 0.0-1.0. Default: 0.7
        max_new_tokens: Maximum number of tokens to generate. Default: 1024
        repetition_penalty: Penalty for repeated tokens. Default: 1.2
        min_chunk_length: Minimum chunk length for generation. Default: 50
        condition_on_previous_chunks: Whether to condition generation on previous chunks. Default: True
        early_stop_threshold: Threshold for early stopping. Default: 1.0
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
    max_new_tokens: int = 1024
    repetition_penalty: float = 1.2
    min_chunk_length: int = 50
    condition_on_previous_chunks: bool = True
    early_stop_threshold: float = 1.0


# WebSocket event types for streaming TTS
class StartEvent(BaseModel):
    """WebSocket start event to initiate TTS streaming.

    Attributes:
        event: Event type identifier, always "start"
        request: TTS configuration for the streaming session
    """

    event: Literal["start"] = "start"
    request: TTSRequest


class TextEvent(BaseModel):
    """WebSocket event to send a text chunk for synthesis.

    Attributes:
        event: Event type identifier, always "text"
        text: Text chunk to synthesize
    """

    event: Literal["text"] = "text"
    text: str


class FlushEvent(BaseModel):
    """WebSocket event to force immediate audio generation from buffered text.

    Use this to ensure all buffered text is synthesized without waiting for more input.

    Attributes:
        event: Event type identifier, always "flush"
    """

    event: Literal["flush"] = "flush"


class CloseEvent(BaseModel):
    """WebSocket event to end the streaming session.

    Attributes:
        event: Event type identifier, always "stop"
    """

    event: Literal["stop"] = "stop"
