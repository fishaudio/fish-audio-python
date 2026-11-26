"""Shared types used across the SDK."""

import warnings
from typing import Generic, Literal, TypeVar

import httpx
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


# Response headers of a result model are kept as a plain instance attribute,
# not as a pydantic field: they are not part of the response body, so they
# stay out of model_dump(), equality and the model's schema.
def set_response_headers(model: BaseModel, headers: httpx.Headers) -> None:
    object.__setattr__(model, "_response_headers", headers)


def get_response_headers(model: BaseModel) -> httpx.Headers:
    return model.__dict__.get("_response_headers", httpx.Headers())


# Model types
Model = Literal["s1", "s2-pro", "s2.1-pro", "s2.1-pro-free", "drama-3"]

# Deprecated models
DEPRECATED_MODELS = {"speech-1.5", "speech-1.6"}


def warn_if_deprecated_model(model: str) -> None:
    """Emit a deprecation warning if a legacy model is used."""
    if model in DEPRECATED_MODELS:
        warnings.warn(
            f"Model '{model}' is deprecated. Use 's2.1-pro' instead.",
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
