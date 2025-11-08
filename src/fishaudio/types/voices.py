"""Voice and model management types."""

import datetime
from typing import List, Literal

from pydantic import BaseModel, Field

from .shared import ModelState, TrainMode, Visibility


class Sample(BaseModel):
    """A sample audio for a voice model."""

    title: str
    text: str
    task_id: str
    audio: str


class Author(BaseModel):
    """Voice model author information."""

    id: str = Field(alias="_id")
    nickname: str
    avatar: str


class Voice(BaseModel):
    """
    A voice model

    Represents a TTS voice that can be used for synthesis.
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
