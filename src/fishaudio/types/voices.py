"""Voice and model management types."""

import datetime
from typing import List, Literal

from pydantic import BaseModel, Field

from .shared import ModelState, TrainMode, Visibility


class Sample(BaseModel):
    """A sample audio for a voice model.

    Attributes:
        title: Title/name of the audio sample
        text: Transcription of the spoken content in the sample
        task_id: Unique identifier for the sample task
        audio: URL or path to the audio file
    """

    title: str
    text: str
    task_id: str
    audio: str


class Author(BaseModel):
    """Voice model author information.

    Attributes:
        id: Unique author identifier
        nickname: Author's display name
        avatar: URL to author's avatar image
    """

    id: str = Field(alias="_id")
    nickname: str
    avatar: str


class Voice(BaseModel):
    """
    A voice model.

    Represents a TTS voice that can be used for synthesis.

    Attributes:
        id: Unique voice model identifier (use as reference_id in TTS)
        type: Model type. Options: "svc" (singing voice conversion), "tts" (text-to-speech)
        title: Voice model title/name
        description: Detailed description of the voice model
        cover_image: URL to the voice model's cover image
        train_mode: Training mode used. Options: "fast"
        state: Current model state (e.g., "ready", "training", "failed")
        tags: List of tags for categorization (e.g., ["male", "english", "young"])
        samples: List of audio samples demonstrating the voice
        created_at: Timestamp when the model was created
        updated_at: Timestamp when the model was last updated
        languages: List of supported language codes (e.g., ["en", "zh"])
        visibility: Model visibility. Options: "public", "private", "unlisted"
        lock_visibility: Whether visibility setting is locked
        like_count: Number of likes the model has received
        mark_count: Number of bookmarks/favorites
        shared_count: Number of times the model has been shared
        task_count: Number of times the model has been used for generation
        liked: Whether the current user has liked this model. Default: False
        marked: Whether the current user has bookmarked this model. Default: False
        author: Information about the voice model's creator
    """

    id: str = Field(alias="_id")
    type: Literal["svc", "tts"]
    title: str
    description: str
    cover_image: str
    train_mode: TrainMode
    state: ModelState
    tags: List[str]
    samples: List[Sample]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    languages: List[str]
    visibility: Visibility
    lock_visibility: bool
    like_count: int
    mark_count: int
    shared_count: int
    task_count: int
    liked: bool = False
    marked: bool = False
    author: Author
