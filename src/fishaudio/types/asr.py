"""ASR (Automatic Speech Recognition) related types."""

from typing import Optional

import httpx
from pydantic import BaseModel

from .shared import get_response_headers


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


class SpeakerTurn(BaseModel):
    """A stretch of the transcript spoken by one speaker.

    Attributes:
        speaker: Speaker label (e.g., "speaker:0"). Labels identify speakers within one response only
        text: What the speaker said in this turn, without inline speaker markers
        start: Turn start time in seconds
        end: Turn end time in seconds
    """

    speaker: str
    text: str
    start: float
    end: float


class ASRResponse(BaseModel):
    """Response from speech-to-text transcription.

    Attributes:
        text: Complete transcription of the entire audio
        duration: Total audio duration in seconds
        segments: List of timestamped text segments. Empty if include_timestamps=False
        language: Display name of the transcript's language (e.g., "English"). None if not returned
        language_code: Language code of the transcript (e.g., "en"): the detected language, or the requested language if none was detected. None if not returned
        request_id: Identifier of this request; quote it when reporting a problem with the request. None if not returned
        speaker_turns: Speaker turns in order, with times in seconds. Returned only by models with speaker diarization, and only if include_timestamps=True; empty if no speech was found. None otherwise
    """

    text: str
    duration: float  # Duration in seconds
    segments: list[ASRSegment]
    language: Optional[str] = None
    language_code: Optional[str] = None
    request_id: Optional[str] = None
    speaker_turns: Optional[list[SpeakerTurn]] = None

    @property
    def headers(self) -> httpx.Headers:
        """Headers of the HTTP response, for example ``x-fish-trace-id``.

        Empty on a model that was not returned by the client.
        """
        return get_response_headers(self)
