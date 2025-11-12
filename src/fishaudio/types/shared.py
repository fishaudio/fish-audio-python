"""Shared types used across the SDK."""

from typing import Generic, List, Literal, TypeVar

from pydantic import BaseModel

# Type variable for generic pagination
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    total: int
    items: List[T]


# Model types
Model = Literal["speech-1.5", "speech-1.6", "s1"]

# Audio format types
AudioFormat = Literal["wav", "pcm", "mp3", "opus"]

# Visibility types
Visibility = Literal["public", "unlist", "private"]

# Training mode types
TrainMode = Literal["fast", "full"]

# Model state types
ModelState = Literal["created", "training", "trained", "failed"]

# Latency modes
LatencyMode = Literal["normal", "balanced"]
