"""Shared types used across the SDK."""

import warnings
from typing import Generic, Literal, TypeVar

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
    items: list[T]


# Model types
Model = Literal["speech-1.5", "speech-1.6", "s1", "s2-pro"]

# Deprecated models
DEPRECATED_MODELS = {"speech-1.5", "speech-1.6"}


def warn_if_deprecated_model(model: str) -> None:
    """Emit a deprecation warning if a legacy model is used."""
    if model in DEPRECATED_MODELS:
        warnings.warn(
            f"Model '{model}' is deprecated. Use 's1' or 's2-pro' instead.",
            DeprecationWarning,
            stacklevel=3,
        )


# Audio format types
AudioFormat = Literal["wav", "pcm", "mp3", "opus"]

# Visibility types
Visibility = Literal["public", "unlist", "private"]

# Training mode types
TrainMode = Literal["fast"]

# Model state types
ModelState = Literal["created", "training", "trained", "failed"]

# Latency modes
LatencyMode = Literal["normal", "balanced"]
