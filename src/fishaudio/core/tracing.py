"""Trace context: the default header provider, and the check that the API
continued the trace the SDK sent."""

from __future__ import annotations

import contextlib
import logging
import re
import sys
import threading
import warnings
from typing import TYPE_CHECKING, Any, Optional

from httpx_ws import WebSocketUpgradeError

from fishaudio.exceptions import TraceNotContinuedWarning

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence

    import httpx

logger = logging.getLogger(__name__)

# The OpenTelemetry API's get_current_span, imported on first use: None until
# then, False when the API is not installed (not retried on every request).
_get_current_span: Any = None


def _current_span_getter() -> Any:
    global _get_current_span
    if _get_current_span is None:
        try:
            from opentelemetry.trace import get_current_span
        except ImportError:
            _get_current_span = False
        else:
            _get_current_span = get_current_span
    return _get_current_span


def opentelemetry_headers() -> Optional[dict[str, str]]:
    """The current OpenTelemetry span as a W3C ``traceparent`` header, or None.

    The default ``header_provider`` of ``FishAudio`` and ``AsyncFishAudio``.
    It needs no dependency: when the ``opentelemetry-api`` package is not
    installed, or no span is active (also when the API is installed but no
    OpenTelemetry SDK is configured), it returns None and no header is sent.

    It returns ``traceparent`` only, built from the span's IDs and flags:
    no ``baggage``, which can carry application data, and no ``tracestate``.
    It does not use the configured propagator, because Fish Audio reads the
    W3C ``traceparent`` only. This covers what the SDK adds; an HTTP
    instrumentation such as ``opentelemetry-instrumentation-httpx``, if you
    use one, adds whatever its propagators are configured to send (by
    default also ``tracestate`` and ``baggage``), with or without this SDK.

    It never fails a request: an error inside OpenTelemetry is logged at
    debug level and no header is sent.

    To combine it with headers of your own::

        FishAudio(header_provider=lambda: {**(opentelemetry_headers() or {}), **mine()})
    """
    get_current_span = _current_span_getter()
    if not get_current_span:
        return None
    try:
        context = get_current_span().get_span_context()
        if not context.is_valid:
            return None
        return {
            "traceparent": f"00-{context.trace_id:032x}-{context.span_id:016x}"
            f"-{int(context.trace_flags):02x}"
        }
    except Exception:
        logger.debug("Could not read the current OpenTelemetry span", exc_info=True)
        return None


# -- Did the API continue the trace the SDK sent? ---------------------------

TRACE_ID_HEADER = "x-fish-trace-id"
"""The response header that names the trace the API used for a request."""

OBSERVABILITY_DOCS = "https://docs.fish.audio/api-reference/observability"

# W3C Trace Context, section 3.2: version, trace-id, parent-id, trace-flags,
# lowercase hex. Version ff is invalid; a version after 00 may append fields.
_TRACEPARENT = re.compile(
    r"(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<parent_id>[0-9a-f]{16})"
    r"-[0-9a-f]{2}(?P<rest>-.*)?"
)
_TRACE_ID = re.compile(r"[0-9a-fA-F]{32}")

# Set once the warning has been issued (or attempted): it is issued at most
# once per process, whichever thread, task or call site sees the mismatch.
_warned = False
_warned_lock = threading.Lock()


def traceparent_trace_id(value: str) -> Optional[str]:
    """The trace ID of a valid W3C ``traceparent``, or None if it is not one."""
    match = _TRACEPARENT.fullmatch(value.strip(" \t"))
    if match is None:
        return None
    version, trace_id = match.group("version"), match.group("trace_id")
    if version == "ff" or (version == "00" and match.group("rest") is not None):
        return None
    if int(trace_id, 16) == 0 or int(match.group("parent_id"), 16) == 0:
        return None
    return trace_id


def sent_traceparents(
    headers: Any, client_headers: Optional[httpx.Headers] = None
) -> list[str]:
    """The ``traceparent`` values a request sends, as httpx merges them.

    ``headers`` are the request's own (they win over the client's, name by
    name, in any casing); ``client_headers`` those set on the httpx client.
    Never raises: anything unreadable gives an empty list.
    """
    if _warned:
        return []  # Nothing left to check.
    try:
        import httpx

        merged = httpx.Headers(client_headers)
        merged.update(headers)
        return merged.get_list("traceparent")
    except Exception:
        return []


def check_trace_continued(sent: Sequence[str], response: Any) -> None:
    """Warn once if ``response`` shows that the API did not continue ``sent``.

    ``sent`` are the ``traceparent`` values the SDK put on the request (from
    ``sent_traceparents``); ``response`` is the HTTP response, or the
    WebSocket handshake response. Nothing happens when no traceparent was
    sent, or when the response has no ``x-fish-trace-id`` (another server, a
    proxy that drops it) or one that is not a trace ID.

    It never raises into the caller's call path: a failure inside it is
    logged at debug level, and a warning that the caller's filters turn into
    an exception (``-W error``) is caught and logged instead.
    """
    if _warned or not sent:
        return
    try:
        received = response.headers.get(TRACE_ID_HEADER)
        if not isinstance(received, str) or not _TRACE_ID.fullmatch(received.strip()):
            return
        received = received.strip().lower()
        if len(sent) == 1 and traceparent_trace_id(sent[0]) == received:
            return
        _warn_once(_mismatch_cause(sent), received)
    except Exception:
        logger.debug("Could not check the trace ID of the response", exc_info=True)


def _api_trace_id(value: str) -> Optional[str]:
    """The trace ID of ``value`` if the API accepts it as a traceparent: a
    valid W3C traceparent of version 00, lowercase, with exactly four fields.
    Otherwise None."""
    if not value.strip(" \t").startswith("00-"):
        return None
    return traceparent_trace_id(value)


def _mismatch_cause(sent: Sequence[str]) -> tuple[str, str]:
    """What the SDK sent, and the cause of the mismatch it points to.

    Only a trace ID or a count is ever included: never a header value as
    sent, which may be anything a header provider returned.
    """
    if len(sent) > 1:
        return (
            f"{len(sent)} traceparent headers",
            "The API continues a trace only when a request carries exactly "
            "one traceparent.",
        )
    sent_id = _api_trace_id(sent[0])
    if sent_id is None:
        return (
            "the traceparent it sent is not one the API accepts",
            "The API continues only a lowercase version-00 W3C traceparent, "
            "00-<32 hex trace id>-<16 hex parent id>-<2 hex flags>; any other "
            "value starts a new trace.",
        )
    return (
        f"sent trace id {sent_id}",
        "The value the SDK sent is valid, so something on the request path "
        "after the SDK (a custom httpx transport, an event hook or a proxy) "
        "added a second traceparent or replaced it with one from another trace.",
    )


def _warn_once(cause: tuple[str, str], received: str) -> None:
    global _warned
    with _warned_lock:
        if _warned:
            return
        _warned = True
    sent_part, explanation = cause
    message = (
        f"Fish Audio did not continue the trace this SDK sent ({sent_part}; "
        f"the API used {received}). {explanation} See {OBSERVABILITY_DOCS}"
    )
    try:
        warnings.warn(message, TraceNotContinuedWarning, stacklevel=_stacklevel())
    except Exception:
        # The caller's warning filters turned it into an exception: the
        # request has succeeded or failed on its own, so log it instead.
        logger.warning("%s", message)


def _stacklevel() -> int:
    """The stack level for warnings.warn: the first frame outside the SDK, so
    the warning names the caller's line. Level 1 is ``_warn_once``.

    The async realtime handshake is checked in a task the SDK starts, where no
    caller frame is on the stack; the warning then names this module instead of
    a line inside asyncio.
    """
    level = 2
    frame = sys._getframe(2)  # The caller of _warn_once, at level 2.
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if not (
            module.startswith("fishaudio.")
            or module == "contextlib"
            or module == "asyncio"
            or module.startswith("asyncio.")
        ):
            return level
        frame = frame.f_back
        level += 1
    return 1


@contextlib.contextmanager
def checked_websocket(connection: Any, sent: Sequence[str]) -> Iterator[Any]:
    """Enter an httpx-ws ``connect_ws`` and check its handshake response.

    A refused handshake (``WebSocketUpgradeError``) is checked too.
    """
    with contextlib.ExitStack() as stack:
        try:
            ws = stack.enter_context(connection)
        except WebSocketUpgradeError as exc:
            check_trace_continued(sent, getattr(exc, "response", None))
            raise
        check_trace_continued(sent, getattr(ws, "response", None))
        yield ws


@contextlib.asynccontextmanager
async def achecked_websocket(
    connection: Any, sent: Sequence[str]
) -> AsyncIterator[Any]:
    """Enter an httpx-ws ``aconnect_ws`` and check its handshake response."""
    async with contextlib.AsyncExitStack() as stack:
        try:
            ws = await stack.enter_async_context(connection)
        except WebSocketUpgradeError as exc:
            check_trace_continued(sent, getattr(exc, "response", None))
            raise
        check_trace_continued(sent, getattr(ws, "response", None))
        yield ws
