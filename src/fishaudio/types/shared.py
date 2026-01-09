"""Shared types used across the SDK."""

from typing import Generic, List, Literal, TypeVar

from pydantic import BaseModel

# Type variable for generic pagination
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response.

    Attributes:
        total: Total number of items across all pages
        items: List of items on the current page
    """

    total: int
    items: List[T]


# Model types
Model = Literal["speech-1.5", "speech-1.6", "s1"]

# Audio format types
AudioFormat = Literal["wav", "pcm", "mp3", "opus"]

# Visibility types
Visibility = Literal["public", "unlisted", "private"]

# Training mode types
TrainMode = Literal["fast"]

# Model state types
ModelState = Literal["created", "training", "trained", "failed"]

# Latency modes
LatencyMode = Literal["normal", "balanced"]
