import datetime
from typing import Annotated, Literal, Generic, TypeVar

from pydantic import BaseModel, Field, conint

Item = TypeVar("Item")


class PaginatedResponse(BaseModel, Generic[Item]):
    total: int
    items: list[Item]


class ReferenceAudio(BaseModel):
    audio: bytes
    text: str


class TTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, conint(ge=100, le=300, strict=True)] = 200
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    mp3_bitrate: Literal[64, 128, 192] = 128
    references: list[ReferenceAudio] = []
    reference_id: str | None = None
    normalize: bool = True
    latency: Literal["normal", "balanced"] = "balanced"


class ASRRequest(BaseModel):
    audio: bytes
    language: str | None = None


class ASRResponse(BaseModel):
    text: str
    # Duration in milliseconds
    duration: float


class SampleEntity(BaseModel):
    title: str
    text: str
    task_id: str
    audio: str


class AuthorEntity(BaseModel):
    id: str = Field(alias="_id")
    nickname: str
    avatar: str


class ModelEntity(BaseModel):
    id: str = Field(alias="_id")
    type: Literal["svc", "tts"]
    title: str
    description: str
    cover_image: str
    train_mode: Literal["fast", "full"]
    state: Literal["created", "training", "trained", "failed"]
    tags: list[str]
    samples: list[SampleEntity]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    languages: list[str]
    visibility: Literal["public", "unlist", "private"]
    lock_visibility: bool

    like_count: int
    mark_count: int
    shared_count: int
    task_count: int

    liked: bool = False
    marked: bool = False

    author: AuthorEntity
