"""Realtime speech-to-text sessions over WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import queue
import threading
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Union,
)

import httpx
import ormsgpack
from httpx_ws import HTTPXWSException, WebSocketDisconnect, WebSocketUpgradeError

from fishaudio.core._ws_utils import drain_reader, interrupt_writes
from fishaudio.core.client_wrapper import _api_error
from fishaudio.exceptions import ASRRealtimeError, WebSocketError
from fishaudio.types.asr_realtime import (
    ASRAgentSpeakingEvent,
    ASRCommittedEvent,
    ASRConfiguredEvent,
    ASRConfigureEvent,
    ASRContext,
    ASRContextAddEvent,
    ASRContextItem,
    ASRDraftEvent,
    ASREagerEndOfTurnEvent,
    ASREotProbEvent,
    ASRErrorEvent,
    ASRFinalizeEvent,
    ASRKeepaliveEvent,
    ASRProgressEvent,
    ASRRealtimeConfig,
    ASRRealtimeControl,
    ASRRealtimeEvent,
    ASRResults,
    ASRSessionDoneEvent,
    ASRSessionStartedEvent,
    ASRSpeechStartEvent,
    ASRTurnDetection,
    ASRTurnResumedEvent,
    ASRUserBackchannelEvent,
    ASRUserTurnTakenEvent,
    ASRVadEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Generator, Iterable, Iterator
    from contextlib import AbstractAsyncContextManager, AbstractContextManager

    from httpx_ws import AsyncWebSocketSession, WebSocketSession

logger = logging.getLogger(__name__)

REALTIME_PATH = "/v1/asr/realtime"

# Events the async session may hold for a consumer that reads slowly. When it is
# full the session stops reading from the socket, so the server sees backpressure
# instead of the SDK buffering without limit.
_EVENT_QUEUE_SIZE = 256

# How often a blocked receive wakes up to check that the audio sender is alive.
_POLL_SECONDS = 0.25
# Once the sender has failed, only messages that already arrived are read.
_DRAIN_SECONDS = 0.05
# How long the async session waits for the cancelled audio sender, and with it
# the audio stream's own cleanup, before it closes the connection anyway.
_SENDER_CLEANUP_SECONDS = 1.0
# How long closing waits for a write to the socket. A write does not finish while
# the server is not reading; after this the connection is cut instead.
_CLOSE_WRITE_SECONDS = 0.5

_EVENT_TYPES: dict[str, type[ASRRealtimeEvent]] = {
    "session_started": ASRSessionStartedEvent,
    "speech_start": ASRSpeechStartEvent,
    "user_turn_taken": ASRUserTurnTakenEvent,
    "draft": ASRDraftEvent,
    "eager_end_of_turn": ASREagerEndOfTurnEvent,
    "turn_resumed": ASRTurnResumedEvent,
    "user_backchannel": ASRUserBackchannelEvent,
    "committed": ASRCommittedEvent,
    "vad": ASRVadEvent,
    "eot_prob": ASREotProbEvent,
    "configured": ASRConfiguredEvent,
    "progress": ASRProgressEvent,
    "error": ASRErrorEvent,
    "session_done": ASRSessionDoneEvent,
}

_AUDIO_DONE = ormsgpack.packb({"type": "audio_done"})


def encode_config(config: ASRRealtimeConfig) -> bytes:
    """Pack the ``config`` message that opens a session."""
    return ormsgpack.packb(
        {
            "type": "config",
            "audio": {
                "format": "pcm_s16le",
                "sample_rate": config.sample_rate,
                "channels": 1,
            },
            **config.model_dump(exclude_none=True, exclude={"sample_rate"}),
        }
    )


def encode_message(item: Union[bytes, ASRRealtimeControl]) -> bytes:
    """Pack an audio chunk or a control message for the wire."""
    if isinstance(item, (bytes, bytearray, memoryview)):
        # MessagePack bin: the server drops audio sent as a string or an array.
        return ormsgpack.packb({"type": "audio", "data": bytes(item)})
    return ormsgpack.packb(item.model_dump(exclude_none=True))


def decode_event(message: bytes) -> Optional[ASRRealtimeEvent]:
    """Parse a server message. Returns None for message types this SDK does not know."""
    data = ormsgpack.unpackb(message)
    event_type = _EVENT_TYPES.get(data.get("type")) if isinstance(data, dict) else None
    return event_type.model_validate(data) if event_type else None


def _upgrade_error(response: httpx.Response) -> Exception:
    """The WebSocket upgrade was refused (401, 402, 429, ...): map the HTTP status."""
    status = response.status_code
    # httpx-ws closes the response before the body can be read.
    return _api_error(status, httpx.codes.get_reason_phrase(status) or "Upgrade failed")


class _Protocol:
    """Turns server messages and closes into events or exceptions (sync and async)."""

    def __init__(self) -> None:
        self._last_error: Optional[ASRErrorEvent] = None

    def on_message(self, message: bytes) -> Optional[ASRRealtimeEvent]:
        event = decode_event(message)
        if event is None:
            return None
        if not isinstance(event, ASRErrorEvent):
            self._last_error = None
            return event
        if not event.recoverable:
            raise ASRRealtimeError(
                event.message,
                error_type=event.error_type,
                code=event.code,
                request_id=event.request_id,
            )
        # server_restarting is recoverable but is followed by close 1012.
        self._last_error = event
        return event

    def on_close(self, code: int, reason: str) -> None:
        if code == 1000:
            return
        error = self._last_error
        raise ASRRealtimeError(
            (error.message if error else reason) or "WebSocket closed unexpectedly",
            error_type=error.error_type if error else None,
            code=error.code if error else None,
            request_id=error.request_id if error else None,
            close_code=code,
        )


def _configure_event(
    turn_detection: Optional[ASRTurnDetection],
    results: Optional[ASRResults],
    terms: Optional[list[str]],
) -> ASRConfigureEvent:
    return ASRConfigureEvent(
        turn_detection=turn_detection,
        results=results,
        context=ASRContext(terms=terms) if terms is not None else None,
    )


_NOT_OPEN = "Realtime session is not open"


# Synchronous


class _Link:
    """The open connection, shared by the audio sender thread and control methods."""

    def __init__(self) -> None:
        self._ws: Optional[WebSocketSession] = None
        self._lock = threading.Lock()
        self.closed = False

    def open(self, ws: WebSocketSession) -> None:
        with self._lock:
            self._ws = ws

    def close(self) -> None:
        """End the link. Does not wait for a write that is blocked."""
        self.closed = True  # the sender stops at its next chunk
        ws = self._ws
        if not self._lock.acquire(timeout=_CLOSE_WRITE_SECONDS):
            # A send holds the lock across a socket write that is not finishing.
            # Cut the connection so that it fails; nothing else can be sent
            # before it does, the close frame included.
            interrupt_writes(ws)
            if not self._lock.acquire(timeout=_CLOSE_WRITE_SECONDS):
                self._ws = None
                return
        self._ws = None
        self._lock.release()

    def send(self, data: bytes) -> None:
        with self._lock:
            if self._ws is None:
                raise WebSocketError(_NOT_OPEN)
            try:
                self._ws.send_bytes(data)
            except HTTPXWSException as e:
                raise WebSocketError("Failed to send: WebSocket closed") from e


def _send_audio(
    link: _Link,
    audio_stream: Iterable[Union[bytes, ASRRealtimeControl]],
    failure: list[BaseException],
) -> None:
    try:
        for item in audio_stream:
            if link.closed:  # the session is over: stop at the next chunk
                return
            if item:
                link.send(encode_message(item))
        link.send(_AUDIO_DONE)
    except BaseException as e:
        if not link.closed:  # otherwise the consumer left: nobody to tell
            failure.append(e)
    finally:
        # Closed here, by the thread that runs it: a generator cannot be closed
        # from another thread while it is executing.
        if inspect.isgenerator(audio_stream):
            try:
                audio_stream.close()
            except Exception:
                logger.debug("Closing the audio stream failed", exc_info=True)


def _iter_session(
    link: _Link,
    connect: Callable[[], AbstractContextManager[WebSocketSession]],
    config: bytes,
    audio_stream: Iterable[Union[bytes, ASRRealtimeControl]],
) -> Generator[ASRRealtimeEvent, None, None]:
    protocol = _Protocol()
    failure: list[BaseException] = []
    sender: Optional[threading.Thread] = None
    done: Optional[ASRSessionDoneEvent] = None
    drain_until: Optional[float] = None
    try:
        with connect() as ws:
            try:
                try:
                    ws.send_bytes(config)
                except HTTPXWSException as e:
                    raise WebSocketError("WebSocket connection lost") from e
                while done is None:
                    if failure and drain_until is None:
                        # One deadline for the whole drain: events that keep
                        # arriving must not postpone the audio stream's error.
                        drain_until = time.monotonic() + _DRAIN_SECONDS
                    if drain_until is not None and time.monotonic() >= drain_until:
                        raise failure[0]
                    try:
                        message = ws.receive_bytes(
                            timeout=_POLL_SECONDS
                            if drain_until is None
                            else max(drain_until - time.monotonic(), 0.001)
                        )
                    except (queue.Empty, TimeoutError):  # httpx-ws < 0.8 / >= 0.8
                        continue
                    except WebSocketDisconnect as e:
                        protocol.on_close(e.code, e.reason)
                        if (
                            failure
                        ):  # a normal close does not hide a failed audio stream
                            raise failure[0] from None
                        return
                    except HTTPXWSException as e:
                        raise WebSocketError("WebSocket connection lost") from e

                    event = protocol.on_message(message)
                    if event is None:
                        continue
                    if isinstance(event, ASRSessionDoneEvent):
                        done = event
                        continue
                    if isinstance(event, ASRSessionStartedEvent) and sender is None:
                        link.open(ws)
                        sender = threading.Thread(
                            target=_send_audio,
                            args=(link, audio_stream, failure),
                            name="fishaudio-asr-realtime-sender",
                            daemon=True,
                        )
                        sender.start()
                    yield event
            finally:
                link.close()
                # Stop httpx-ws's reader thread before the socket is closed so it
                # cannot read from a reused fd belonging to the next connection.
                drain_reader(ws)
        # The connection is closed before the last event is handed out, so a
        # caller that stops at session_done does not leave it open.
        if done is not None:
            yield done
    except WebSocketUpgradeError as e:
        raise _upgrade_error(e.response) from e


class ASRRealtimeStream:
    """A realtime speech-to-text session (sync).

    Iterate it for the server's events. The connection opens on the first
    iteration and closes when the session ends, when an error is raised, or when
    you leave the loop early. Use it as a context manager (or call ``close()``)
    if you keep a reference to it after leaving the loop.

    The audio stream is read on a background thread. When the session ends
    before the audio does, that thread stops as soon as the audio stream yields
    its next chunk, and closes the stream if it is a generator. The SDK cannot
    interrupt an audio stream that is blocked waiting for audio (for example a
    microphone read with no timeout): make your audio source end, or yield
    regularly, so the thread can exit.

    Closing does not wait for a server that has stopped reading: a write that
    is still pending after half a second is interrupted by cutting the
    connection, without a close frame.

    Read the events from one thread at a time.

    The control methods send a message at the current position in the audio
    stream; they can be called from any thread once ``session_started`` has
    been received.
    """

    def __init__(
        self,
        connect: Callable[[], AbstractContextManager[WebSocketSession]],
        config: ASRRealtimeConfig,
        audio_stream: Iterable[Union[bytes, ASRRealtimeControl]],
    ):
        # The generator must not reference this object: it is closed, and the
        # connection with it, as soon as the stream is garbage collected.
        self._link = _Link()
        self._events = _iter_session(
            self._link, connect, encode_config(config), audio_stream
        )

    def __iter__(self) -> Iterator[ASRRealtimeEvent]:
        return self

    def __next__(self) -> ASRRealtimeEvent:
        return next(self._events)

    def __enter__(self) -> ASRRealtimeStream:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection. Safe to call more than once."""
        self._events.close()

    def send(self, message: ASRRealtimeControl) -> None:
        """Send a control message.

        Raises:
            WebSocketError: If the session is not open (not started yet, or closed)
        """
        self._link.send(encode_message(message))

    def finalize(self) -> None:
        """Commit the current turn now (push-to-talk: the button was released)."""
        self.send(ASRFinalizeEvent())

    def agent_speaking(self, speaking: bool) -> None:
        """Tell the server that your voice agent started or stopped speaking."""
        self.send(ASRAgentSpeakingEvent(speaking=speaking))

    def add_context(
        self, items: list[ASRContextItem], *, reset_history: bool = False
    ) -> None:
        """Add conversation context, typically each line your agent speaks."""
        self.send(ASRContextAddEvent(items=items, reset_history=reset_history))

    def configure(
        self,
        *,
        turn_detection: Optional[ASRTurnDetection] = None,
        results: Optional[ASRResults] = None,
        terms: Optional[list[str]] = None,
    ) -> None:
        """Change settings during the session. The server answers with a configured event."""
        self.send(_configure_event(turn_detection, results, terms))

    def keepalive(self) -> None:
        """Keep an idle session open. Rarely needed: WebSocket pings count as activity."""
        self.send(ASRKeepaliveEvent())


# Asynchronous


class _AsyncLink:
    """The open connection, shared by the audio sender task and control methods."""

    def __init__(self) -> None:
        self._ws: Optional[AsyncWebSocketSession] = None

    def open(self, ws: AsyncWebSocketSession) -> None:
        self._ws = ws

    def close(self) -> None:
        self._ws = None

    async def send(self, data: bytes) -> None:
        if self._ws is None:
            raise WebSocketError(_NOT_OPEN)
        try:
            await self._ws.send_bytes(data)
        except HTTPXWSException as e:
            raise WebSocketError("Failed to send: WebSocket closed") from e


async def _asend_audio(
    link: _AsyncLink, audio_stream: AsyncIterable[Union[bytes, ASRRealtimeControl]]
) -> None:
    try:
        async for item in audio_stream:
            if item:
                await link.send(encode_message(item))
        await link.send(_AUDIO_DONE)
    finally:
        # A cancelled task leaves an async generator suspended at its yield;
        # close it now rather than whenever the event loop finalizes it.
        if inspect.isasyncgen(audio_stream):
            try:
                await audio_stream.aclose()
            except Exception:
                logger.debug("Closing the audio stream failed", exc_info=True)


def _retrieve_exception(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        task.exception()  # mark it as retrieved: nobody else will look


def _failure(task: Optional[asyncio.Task[None]]) -> Optional[BaseException]:
    """Why the audio sender stopped early, if it did."""
    if task is None or not task.done():
        return None
    if task.cancelled():
        # Not our doing (cleanup cancels it only after the receive loop has ended):
        # the audio stream awaited something that was cancelled.
        return WebSocketError("Audio stream was cancelled before the session ended")
    return task.exception()


class _End:
    """Queue marker: the session is over, normally or with an error."""

    def __init__(self, error: Optional[BaseException] = None) -> None:
        self.error = error


async def _run_session(
    link: _AsyncLink,
    events: asyncio.Queue[Union[ASRRealtimeEvent, _End]],
    connect: Callable[[], AbstractAsyncContextManager[AsyncWebSocketSession]],
    config: bytes,
    audio_stream: AsyncIterable[Union[bytes, ASRRealtimeControl]],
) -> None:
    """Run one session from connect to close, inside a single task.

    httpx-ws keeps an anyio task group open for the lifetime of the connection,
    and a task group must be exited by the task that entered it. An async
    generator cannot promise that: when the consumer leaves ``async for`` early,
    asyncio finalizes the generator from a different task. So the connection
    lives in this task, which is simply cancelled to close it.
    """
    protocol = _Protocol()
    sender: Optional[asyncio.Task[None]] = None
    error: Optional[BaseException] = None
    try:
        async with connect() as ws:
            try:
                try:
                    await ws.send_bytes(config)
                except HTTPXWSException as e:
                    raise WebSocketError("WebSocket connection lost") from e
                drain_until: Optional[float] = None
                while True:
                    failure = _failure(sender)
                    if failure and drain_until is None:
                        # One deadline for the whole drain: events that keep
                        # arriving must not postpone the audio stream's error.
                        drain_until = time.monotonic() + _DRAIN_SECONDS
                    if (
                        failure is not None
                        and drain_until is not None
                        and time.monotonic() >= drain_until
                    ):
                        raise failure
                    try:
                        message = await ws.receive_bytes(
                            timeout=_POLL_SECONDS
                            if drain_until is None
                            else max(drain_until - time.monotonic(), 0.001)
                        )
                    except TimeoutError:
                        continue
                    except WebSocketDisconnect as e:
                        protocol.on_close(e.code, e.reason)
                        failure = _failure(sender)
                        if (
                            failure
                        ):  # a normal close does not hide a failed audio stream
                            raise failure from None
                        break
                    except HTTPXWSException as e:
                        raise WebSocketError("WebSocket connection lost") from e

                    event = protocol.on_message(message)
                    if event is None:
                        continue
                    if isinstance(event, ASRSessionStartedEvent) and sender is None:
                        link.open(ws)
                        sender = asyncio.create_task(_asend_audio(link, audio_stream))
                    await events.put(event)  # waits while the consumer is behind
                    if isinstance(event, ASRSessionDoneEvent):
                        break
            except Exception as e:
                # Leave the connection block without an exception: newer httpx-ws
                # wraps one that crosses it in an ExceptionGroup.
                error = e
            finally:
                link.close()
                if sender is not None:
                    sender.cancel()
                    # Bounded: an audio stream whose cleanup never finishes must
                    # not keep the connection open and the consumer waiting.
                    await asyncio.wait({sender}, timeout=_SENDER_CLEANUP_SECONDS)
                    sender.add_done_callback(_retrieve_exception)
                # The close frame is a write like any other: it does not finish
                # while the server is not reading, or while a control message
                # sent from another task is stuck in the same way. Bound it here;
                # leaving the block then closes the transport without the frame.
                try:
                    await asyncio.wait_for(ws.close(), _CLOSE_WRITE_SECONDS)
                except Exception:  # includes the timeout
                    logger.debug("Close frame was not sent", exc_info=True)
    except WebSocketUpgradeError as e:
        error = _upgrade_error(e.response)
        error.__cause__ = e
    except Exception as e:
        error = error or e  # keep the session's own error over one from closing
    # The connection is closed by now. If the queue is full this waits for the
    # consumer; one that has left cancels the task (aclose, or garbage collection).
    await events.put(_End(error))


class AsyncASRRealtimeStream:
    """A realtime speech-to-text session (async).

    Iterate it with ``async for`` for the server's events. The connection opens
    on the first iteration and closes when the session ends, when an error is
    raised, or when you leave the loop early. Use it as an async context manager
    (or call ``aclose()``) if you keep a reference to it after leaving the loop.

    Closing cancels the task that reads the audio stream and closes the stream
    if it is an async generator. Up to 256 events are buffered for a consumer
    that reads slowly; beyond that the session stops reading from the server
    until the consumer catches up.

    Read the events from one task at a time: a read started while another is
    waiting raises ``RuntimeError``. A read that was cancelled (for example by
    ``asyncio.wait_for``) loses nothing; just read again.

    The control methods send a message at the current position in the audio
    stream; they can be awaited once ``session_started`` has been received.

    Keep reading: when you stop, the SDK buffers a few hundred events and then
    stops reading from the connection, which also stops it answering keepalive
    pings. A consumer that stays stalled past the keepalive timeout (20 s by
    default, see ``ws_options``) while events keep arriving loses the connection.
    """

    def __init__(
        self,
        connect: Callable[[], AbstractAsyncContextManager[AsyncWebSocketSession]],
        config: ASRRealtimeConfig,
        audio_stream: AsyncIterable[Union[bytes, ASRRealtimeControl]],
    ):
        self._link = _AsyncLink()
        self._connect = connect
        self._config = encode_config(config)
        self._audio_stream = audio_stream
        self._events: Optional[asyncio.Queue[Union[ASRRealtimeEvent, _End]]] = None
        self._task: Optional[asyncio.Task[None]] = None
        # The pending read of the queue. It outlives a cancelled __anext__, so an
        # event it has already taken is handed to the next read instead of lost.
        self._getter: Optional[asyncio.Future[Union[ASRRealtimeEvent, _End]]] = None
        self._reading = False
        self._finished = False

    def __aiter__(self) -> AsyncASRRealtimeStream:
        return self

    async def __anext__(self) -> ASRRealtimeEvent:
        if self._finished:
            raise StopAsyncIteration
        if self._events is None:
            # The session task must not reference this object: it is cancelled,
            # and the connection closed, when the stream is garbage collected.
            self._events = asyncio.Queue(_EVENT_QUEUE_SIZE)
            self._task = asyncio.create_task(
                _run_session(
                    self._link,
                    self._events,
                    self._connect,
                    self._config,
                    self._audio_stream,
                )
            )
        if self._reading:
            # Events have one order and one reader. Two reads waiting together
            # would be handed the same event, so refuse the second, as Python
            # does for a generator that is already running.
            raise RuntimeError(
                "Another read of this stream is already waiting for an event"
            )
        self._reading = True
        try:
            item = await self._next_item()
        finally:
            self._reading = False
        if item is None:  # closed by aclose() while waiting
            self._finished = True
            raise StopAsyncIteration
        if isinstance(item, _End):
            self._finished = True
            if item.error is not None:
                raise item.error
            raise StopAsyncIteration
        return item

    async def _next_item(self) -> Union[ASRRealtimeEvent, _End, None]:
        """The next queue item, or None once the session task is gone and the queue is empty.

        A session that ends by itself always queues an ``_End`` first. One that is
        cancelled (``aclose()`` from another task) queues nothing, so waiting on
        the queue alone would block this consumer forever: wait for the queue and
        the session task together.
        """
        events, task = self._events, self._task
        assert events is not None and task is not None
        if self._getter is None:
            with contextlib.suppress(asyncio.QueueEmpty):
                return events.get_nowait()
            self._getter = asyncio.ensure_future(events.get())
        getter = self._getter
        if not getter.done():
            # Cancelling this wait (asyncio.wait_for around __anext__, for example)
            # leaves the getter in place for the next call.
            await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
        self._getter = None
        if getter.done() and not getter.cancelled():
            return getter.result()
        # The session task ended first, or aclose() dropped the getter. Either way
        # the getter has taken nothing: what the session queued last is still there.
        getter.cancel()
        with contextlib.suppress(asyncio.QueueEmpty):
            return events.get_nowait()
        return None

    def _drop_getter(self) -> None:
        getter, self._getter = self._getter, None
        if getter is not None and not getter.done():
            # RuntimeError: the event loop is already closed
            with contextlib.suppress(RuntimeError):
                getter.cancel()

    async def __aenter__(self) -> AsyncASRRealtimeStream:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the connection. Safe to call more than once."""
        self._finished = True
        self._drop_getter()
        if self._task is not None:
            self._task.cancel()
            await asyncio.wait({self._task})

    def __del__(self) -> None:
        if getattr(self, "_getter", None) is not None:
            self._drop_getter()
        task = getattr(self, "_task", None)
        if task is not None and not task.done():
            # RuntimeError: the event loop is already closed
            with contextlib.suppress(RuntimeError):
                task.cancel()

    async def send(self, message: ASRRealtimeControl) -> None:
        """Send a control message.

        Raises:
            WebSocketError: If the session is not open (not started yet, or closed)
        """
        await self._link.send(encode_message(message))

    async def finalize(self) -> None:
        """Commit the current turn now (push-to-talk: the button was released)."""
        await self.send(ASRFinalizeEvent())

    async def agent_speaking(self, speaking: bool) -> None:
        """Tell the server that your voice agent started or stopped speaking."""
        await self.send(ASRAgentSpeakingEvent(speaking=speaking))

    async def add_context(
        self, items: list[ASRContextItem], *, reset_history: bool = False
    ) -> None:
        """Add conversation context, typically each line your agent speaks."""
        await self.send(ASRContextAddEvent(items=items, reset_history=reset_history))

    async def configure(
        self,
        *,
        turn_detection: Optional[ASRTurnDetection] = None,
        results: Optional[ASRResults] = None,
        terms: Optional[list[str]] = None,
    ) -> None:
        """Change settings during the session. The server answers with a configured event."""
        await self.send(_configure_event(turn_detection, results, terms))

    async def keepalive(self) -> None:
        """Keep an idle session open. Rarely needed: WebSocket pings count as activity."""
        await self.send(ASRKeepaliveEvent())
