"""ASR (Automatic Speech Recognition) related types."""

from typing import List

from pydantic import BaseModel


class ASRSegment(BaseModel):
    """A timestamped segment of transcribed text."""

    text: str
    start: float
    end: float


class ASRResponse(BaseModel):
    """Response from speech-to-text transcription."""

    text: str
    duration: float  # Duration in milliseconds
    segments: List[ASRSegment]
