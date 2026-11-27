"""Tests for the warning emitted when a deprecated model is used."""

import threading
import warnings
from collections.abc import Awaitable, Callable
from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest

from fishaudio.core import AsyncClientWrapper, ClientWrapper, RequestOptions
from fishaudio.resources.asr import ASRClient, AsyncASRClient
from fishaudio.resources.tts import AsyncTTSClient, TTSClient
from fishaudio.types.shared import warn_if_deprecated_model

S1_MESSAGE = (
    "Model 's1' is deprecated and will be retired on December 31, 2026. "
    "After that date, requests that specify 's1' are served by 's2.1-pro' "
    "and billed as 's2.1-pro'. Use 's2.1-pro' instead."
)
TRANSCRIBE_1_MESSAGE = (
    "Model 'transcribe-1' is deprecated and will be retired on December 31, "
    "2026. After that date, requests that specify 'transcribe-1' are served "
    "by 'transcribe-1-pro' and billed as 'transcribe-1-pro'. "
    "Use 'transcribe-1-pro' instead."
)


class _Stop(Exception):
    """Raised by the mocked transport so a call ends right after the check."""


def _sync_wrapper() -> Mock:
    wrapper = Mock(spec=ClientWrapper)
    wrapper.client = Mock()
    wrapper.get_headers.return_value = {}
    wrapper.request.side_effect = _Stop()
    return wrapper


def _async_wrapper() -> Mock:
    wrapper = Mock(spec=AsyncClientWrapper)
    wrapper.client = Mock()
    wrapper.get_headers.return_value = {}
    wrapper.request.side_effect = _Stop()
    return wrapper


def _tts_stream(model: str) -> None:
    TTSClient(_sync_wrapper()).stream(text="hi", model=model)


def _tts_convert(model: str) -> None:
    TTSClient(_sync_wrapper()).convert(text="hi", model=model)


def _tts_stream_websocket(model: str) -> None:
    with patch("fishaudio.resources.tts.connect_ws", side_effect=_Stop()):
        list(TTSClient(_sync_wrapper()).stream_websocket(iter(["hi"]), model=model))


def _tts_stream_with_timestamps(model: str) -> None:
    TTSClient(_sync_wrapper()).stream_with_timestamps(text="hi", model=model)


def _tts_convert_with_timestamps(model: str) -> None:
    TTSClient(_sync_wrapper()).convert_with_timestamps(text="hi", model=model)


def _asr_transcribe(model: str) -> None:
    ASRClient(_sync_wrapper()).transcribe(audio=b"audio", model=model)


def _asr_transcribe_header(model: str) -> None:
    ASRClient(_sync_wrapper()).transcribe(
        audio=b"audio",
        request_options=RequestOptions(additional_headers={"Model": model}),
    )


async def _async_tts_stream(model: str) -> None:
    await AsyncTTSClient(_async_wrapper()).stream(text="hi", model=model)


async def _async_tts_convert(model: str) -> None:
    await AsyncTTSClient(_async_wrapper()).convert(text="hi", model=model)


async def _async_tts_stream_websocket(model: str) -> None:
    async def text():
        yield "hi"

    with patch("fishaudio.resources.tts.aconnect_ws", side_effect=_Stop()):
        async for _ in AsyncTTSClient(_async_wrapper()).stream_websocket(
            text(), model=model
        ):
            pass


async def _async_tts_stream_with_timestamps(model: str) -> None:
    await AsyncTTSClient(_async_wrapper()).stream_with_timestamps(
        text="hi", model=model
    )


async def _async_tts_convert_with_timestamps(model: str) -> None:
    await AsyncTTSClient(_async_wrapper()).convert_with_timestamps(
        text="hi", model=model
    )


async def _async_asr_transcribe(model: str) -> None:
    await AsyncASRClient(_async_wrapper()).transcribe(audio=b"audio", model=model)


async def _async_asr_transcribe_header(model: str) -> None:
    await AsyncASRClient(_async_wrapper()).transcribe(
        audio=b"audio",
        request_options=RequestOptions(additional_headers={"model": model}),
    )


SYNC_TTS = [
    _tts_stream,
    _tts_convert,
    _tts_stream_websocket,
    _tts_stream_with_timestamps,
    _tts_convert_with_timestamps,
]
SYNC_ASR = [_asr_transcribe, _asr_transcribe_header]
ASYNC_TTS = [
    _async_tts_stream,
    _async_tts_convert,
    _async_tts_stream_websocket,
    _async_tts_stream_with_timestamps,
    _async_tts_convert_with_timestamps,
]
ASYNC_ASR = [_async_asr_transcribe, _async_asr_transcribe_header]

SYNC_CASES = [(call, "s1", S1_MESSAGE) for call in SYNC_TTS] + [
    (call, "transcribe-1", TRANSCRIBE_1_MESSAGE) for call in SYNC_ASR
]
ASYNC_CASES = [(call, "s1", S1_MESSAGE) for call in ASYNC_TTS] + [
    (call, "transcribe-1", TRANSCRIBE_1_MESSAGE) for call in ASYNC_ASR
]


def _ids(case: Any) -> Optional[str]:
    return case.__name__ if callable(case) else None


def _deprecation_warnings(
    record: list[warnings.WarningMessage],
) -> list[warnings.WarningMessage]:
    return [w for w in record if issubclass(w.category, FutureWarning)]


def _run_sync(call: Callable[[str], None], model: str) -> None:
    with pytest.raises(_Stop):
        call(model)


async def _run_async(call: Callable[[str], Awaitable[None]], model: str) -> None:
    with pytest.raises(_Stop):
        await call(model)


class TestRetiringModelWarning:
    """s1 and transcribe-1 warn on every entry point that accepts them."""

    @pytest.mark.parametrize("call,model,message", SYNC_CASES, ids=_ids)
    def test_sync_entry_point_warns(self, call, model, message):
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            _run_sync(call, model)

        emitted = _deprecation_warnings(record)
        assert [str(w.message) for w in emitted] == [message]
        # The warning points at the code that called the SDK, not at the SDK.
        assert emitted[0].filename == __file__

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call,model,message", ASYNC_CASES, ids=_ids)
    async def test_async_entry_point_warns(self, call, model, message):
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            await _run_async(call, model)

        emitted = _deprecation_warnings(record)
        assert [str(w.message) for w in emitted] == [message]
        assert emitted[0].filename == __file__


def _python_default_filters() -> None:
    """Install the filters a plain `python app.py` run starts with."""
    warnings.resetwarnings()
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", category=ImportWarning)
    warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("default", category=DeprecationWarning, module="__main__")


class TestWarningFilters:
    """No state of its own: Python's warning filters decide what is shown."""

    def test_shown_under_default_filters(self):
        """The default filters hide DeprecationWarning outside __main__, but
        not this warning."""
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            _run_sync(_tts_stream, "s1")

        assert len(_deprecation_warnings(record)) == 1

    @pytest.mark.parametrize("call,model,message", SYNC_CASES, ids=_ids)
    def test_sync_loop_on_one_line_shows_once(self, call, model, message):
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            for _ in range(5):
                _run_sync(call, model)

        assert [str(w.message) for w in _deprecation_warnings(record)] == [message]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call,model,message", ASYNC_CASES, ids=_ids)
    async def test_async_loop_on_one_line_shows_once(self, call, model, message):
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            for _ in range(5):
                await _run_async(call, model)

        assert [str(w.message) for w in _deprecation_warnings(record)] == [message]

    def test_each_calling_line_shows_once(self):
        client = TTSClient(_sync_wrapper())
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            for _ in range(3):
                with pytest.raises(_Stop):
                    client.stream(text="hi", model="s1")  # first line
                with pytest.raises(_Stop):
                    client.stream(text="hi", model="s1")  # second line

        emitted = _deprecation_warnings(record)
        assert [str(w.message) for w in emitted] == [S1_MESSAGE, S1_MESSAGE]
        assert emitted[0].lineno != emitted[1].lineno

    def test_each_model_shows_once(self):
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            for model in ["s1", "speech-1.5", "s1", "speech-1.5"]:
                _run_sync(_tts_stream, model)

        assert [str(w.message) for w in _deprecation_warnings(record)] == [
            S1_MESSAGE,
            "Model 'speech-1.5' is deprecated. Use 's2.1-pro' instead.",
        ]

    def test_always_filter_shows_every_call(self):
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            for _ in range(3):
                _run_sync(_tts_stream, "s1")

        assert len(_deprecation_warnings(record)) == 3

    @pytest.mark.parametrize("call,model,message", SYNC_CASES, ids=_ids)
    def test_error_filter_raises_on_every_call(self, call, model, message):
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            for _ in range(3):
                with pytest.raises(FutureWarning) as exc_info:
                    call(model)
                assert str(exc_info.value) == message

    def test_error_after_ignore_raises(self):
        """An earlier call under an ignore filter does not mute a later one."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            _run_sync(_tts_stream, "s1")
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            with pytest.raises(FutureWarning, match="December 31, 2026"):
                _tts_stream("s1")

    def test_shown_after_earlier_ignore(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            _run_sync(_tts_stream, "s1")
        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            _run_sync(_tts_stream, "s1")

        assert len(_deprecation_warnings(record)) == 1

    def test_threads_on_one_line_show_once(self):
        threads, start = 16, threading.Barrier(16)
        errors: list[BaseException] = []

        def work() -> None:
            try:
                start.wait()
                for _ in range(20):
                    _run_sync(_tts_stream, "s1")
            except BaseException as e:  # noqa: BLE001 - re-raised below
                errors.append(e)

        with warnings.catch_warnings(record=True) as record:
            _python_default_filters()
            workers = [threading.Thread(target=work) for _ in range(threads)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()

        assert errors == []
        assert [str(w.message) for w in _deprecation_warnings(record)] == [S1_MESSAGE]


class TestCurrentModelsDoNotWarn:
    @pytest.mark.parametrize("call", SYNC_TTS, ids=_ids)
    @pytest.mark.parametrize(
        "model", ["s2.1-pro", "s2.1-pro-free", "s2-pro", "drama-3"]
    )
    def test_sync_tts(self, call, model):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _run_sync(call, model)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call", ASYNC_TTS, ids=_ids)
    @pytest.mark.parametrize("model", ["s2.1-pro", "s2-pro", "drama-3"])
    async def test_async_tts(self, call, model):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await _run_async(call, model)

    @pytest.mark.parametrize("call", SYNC_ASR, ids=_ids)
    def test_sync_asr(self, call):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            _run_sync(call, "transcribe-1-pro")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("call", ASYNC_ASR, ids=_ids)
    async def test_async_asr(self, call):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            await _run_async(call, "transcribe-1-pro")

    def test_asr_without_model(self):
        """No model named: no warning, although the API default is transcribe-1."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(_Stop):
                ASRClient(_sync_wrapper()).transcribe(audio=b"audio")

    def test_tts_default_model(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(_Stop):
                TTSClient(_sync_wrapper()).stream(text="hi")

    def test_none_is_ignored(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            warn_if_deprecated_model(None)

    def test_model_ids_match_exactly(self):
        """Lookalike IDs are not treated as the retiring models."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            for model in ["S1", "s1 ", "transcribe-1-pro", "transcribe-10"]:
                warn_if_deprecated_model(model)
