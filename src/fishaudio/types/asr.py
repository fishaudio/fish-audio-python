"""ASR (Automatic Speech Recognition) related types."""

from typing import List

from pydantic import BaseModel


class ASRSegment(BaseModel):
    """A timestamped segment of transcribed text.

    Attributes:
        text: The transcribed text for this segment
        start: Segment start time in seconds
        end: Segment end time in seconds
    """

    text: str
    start: float
    end: float


class ASRResponse(BaseModel):
    """Response from speech-to-text transcription.

    Attributes:
        text: Complete transcription of the entire audio
        duration: Total audio duration in milliseconds
        segments: List of timestamped text segments. Empty if include_timestamps=False
    """

    text: str
    duration: float  # Duration in milliseconds
    segments: List[ASRSegment]
