"""Annotations that use names imported for typing still resolve at runtime."""

import typing

import pytest
from typing_extensions import Self

from fishaudio.core.iterators import AsyncAudioStream, AudioStream
from fishaudio.resources.asr_realtime import ASRRealtimeStream, AsyncASRRealtimeStream


@pytest.mark.parametrize(
    "method",
    [
        AudioStream.__enter__,
        AsyncAudioStream.__aenter__,
        ASRRealtimeStream.__enter__,
        AsyncASRRealtimeStream.__aenter__,
    ],
    ids=lambda method: method.__qualname__,
)
def test_enter_methods_resolve_to_self(method):
    assert typing.get_type_hints(method) == {"return": Self}
