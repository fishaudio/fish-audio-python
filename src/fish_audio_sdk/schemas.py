import datetime
import decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, Field


Backends = Literal["speech-1.5", "speech-1.6", "agent-x0", "s1", "s1-mini"]

Item = TypeVar("Item")


class PaginatedResponse(BaseModel, Generic[Item]):
    total: int
    items: list[Item]


class ReferenceAudio(BaseModel):
    audio: bytes
    text: str


class Prosody(BaseModel):
    speed: float = 1.0
    volume: float = 0.0


class TTSRequest(BaseModel):
    text: str
    chunk_length: Annotated[int, Field(ge=100, le=300, strict=True)] = 200
    format: Literal["wav", "pcm", "mp3"] = "mp3"
    sample_rate: int | None = None
    mp3_bitrate: Literal[64, 128, 192] = 128
    opus_bitrate: Literal[-1000, 24, 32, 48, 64] = 32
    references: list[ReferenceAudio] = []
    reference_id: str | None = None
    normalize: bool = True
    latency: Literal["normal", "balanced"] = "balanced"
    prosody: Prosody | None = None
    top_p: float = 0.7
    temperature: float = 0.7


class ASRRequest(BaseModel):
    audio: bytes
    language: str | None = None
    ignore_timestamps: bool | None = None


class ASRSegment(BaseModel):
    text: str
    start: float
    end: float


class ASRResponse(BaseModel):
    text: str
    # Duration in milliseconds
    duration: float
    segments: list[ASRSegment]


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


class APICreditEntity(BaseModel):
    _id: str
    user_id: str
    credit: decimal.Decimal
    created_at: str
    updated_at: str


class PackageEntity(BaseModel):
    _id: str
    user_id: str
    type: str
    total: int
    balance: int
    created_at: str
    updated_at: str
    finished_at: str


class StartEvent(BaseModel):
    event: Literal["start"] = "start"
    request: TTSRequest


class TextEvent(BaseModel):
    event: Literal["text"] = "text"
    text: str


class CloseEvent(BaseModel):
    event: Literal["stop"] = "stop"
