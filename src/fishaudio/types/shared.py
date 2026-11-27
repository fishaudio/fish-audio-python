"""Shared types used across the SDK."""

import os
import sys
import warnings
from pathlib import Path
from typing import Generic, Literal, Optional, TypeVar

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
Model = Literal["s1", "s2-pro", "s2.1-pro", "s2.1-pro-free", "drama-3"]

# Deprecated models, mapped to the warning shown when one is used.
_SPEECH_1_MESSAGE = "Model '{model}' is deprecated. Use 's2.1-pro' instead."
_S1_MESSAGE = (
    "Model 's1' is deprecated and will be retired on December 31, 2026. "
    "After that date, requests that specify 's1' are served by 's2.1-pro' "
    "and billed as 's2.1-pro'. Use 's2.1-pro' instead."
)
_TRANSCRIBE_1_MESSAGE = (
    "Model 'transcribe-1' is deprecated and will be retired on December 31, "
    "2026. After that date, requests that specify 'transcribe-1' are served "
    "by 'transcribe-1-pro' and billed as 'transcribe-1-pro'. "
    "Use 'transcribe-1-pro' instead."
)

DEPRECATED_TTS_MODELS: dict[str, str] = {
    "speech-1.5": _SPEECH_1_MESSAGE.format(model="speech-1.5"),
    "speech-1.6": _SPEECH_1_MESSAGE.format(model="speech-1.6"),
    "s1": _S1_MESSAGE,
}
DEPRECATED_ASR_MODELS: dict[str, str] = {
    "transcribe-1": _TRANSCRIBE_1_MESSAGE,
}
# All deprecated model IDs (TTS and ASR).
DEPRECATED_MODELS = frozenset(DEPRECATED_TTS_MODELS) | frozenset(DEPRECATED_ASR_MODELS)

# Not resolved, so it matches code objects' filenames (module __file__ paths
# are absolute).
_PACKAGE_DIR = str(Path(__file__).parent.parent) + os.sep


def _stacklevel_outside_package() -> int:
    """Return the stacklevel of the first frame outside the fishaudio package.

    Counted for a ``warnings.warn`` call made by the caller of this function,
    so the warning points at the user's code whichever SDK method was called.
    """
    level = 1
    frame = sys._getframe(1)  # The function that calls warnings.warn.
    while frame is not None and frame.f_code.co_filename.startswith(_PACKAGE_DIR):
        frame = frame.f_back
        level += 1
    return level


def warn_if_deprecated_model(model: Optional[str]) -> None:
    """Emit a FutureWarning if a deprecated model is used.

    FutureWarning, unlike DeprecationWarning, is shown by default in any
    module, so applications that call the SDK see it. The warning is
    attributed to the caller's line, so Python's warning filters decide how
    often it is shown: by default once per calling line, so a loop does not
    repeat it.
    """
    if model is None:
        return
    message = DEPRECATED_TTS_MODELS.get(model) or DEPRECATED_ASR_MODELS.get(model)
    if message is None:
        return
    warnings.warn(message, FutureWarning, stacklevel=_stacklevel_outside_package())


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
