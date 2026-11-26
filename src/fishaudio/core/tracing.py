"""Trace context: the default header provider, and the check that the trace
the SDK sent is the one the API used."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import re
import sys
import threading
import warnings
from typing import TYPE_CHECKING, Any, Callable, Optional

from httpx_ws import WebSocketUpgradeError

from fishaudio.exceptions import TraceNotContinuedWarning

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence

    import httpx

logger = logging.getLogger(__name__)


class _OpenTelemetry:
    """The parts of OpenTelemetry the default provider uses, imported on first
    use. Each optional package is looked up once, not on every request."""

    def __init__(self) -> None:
        from opentelemetry import context, propagate

        self.inject: Callable[[dict[str, str]], None] = propagate.inject
        self.get_value: Callable[[str], object] = context.get_value
        self.is_http_instrumentation_enabled: Optional[Callable[[], bool]] = None
        try:
            # opentelemetry-instrumentation: the check every OpenTelemetry
            # HTTP client instrumentation makes before it injects headers.
            from opentelemetry.instrumentation.utils import (
                is_http_instrumentation_enabled,
            )
        except ImportError:
            pass
        else:
            self.is_http_instrumentation_enabled = is_http_instrumentation_enabled
        # Without that package, the same check on the API's own context keys
        # (the SDK's span and metric exporters set the first one).
        self.suppress_keys = [
            key
            for key in (
                getattr(context, "_SUPPRESS_INSTRUMENTATION_KEY", None),
                "suppress_instrumentation",
                getattr(context, "_SUPPRESS_HTTP_INSTRUMENTATION_KEY", None),
            )
            if key is not None
        ]
        self.get_excluded_urls: Callable[[str], Any] = _get_excluded_urls
        try:
            # opentelemetry-util-http: how instrumentations read
            # OTEL_PYTHON_<NAME>_EXCLUDED_URLS and OTEL_PYTHON_EXCLUDED_URLS.
            from opentelemetry.util.http import get_excluded_urls
        except ImportError:
            pass
        else:
            self.get_excluded_urls = get_excluded_urls

    def suppressed(self) -> bool:
        if self.is_http_instrumentation_enabled is not None:
            return not self.is_http_instrumentation_enabled()
        return any(self.get_value(key) for key in self.suppress_keys)

    def excluded(self, url: str) -> bool:
        return bool(self.get_excluded_urls("HTTPX").url_disabled(url))


class _ExcludeList:
    """``opentelemetry.util.http.ExcludeList``, for when that package is absent."""

    def __init__(self, patterns: list[str]) -> None:
        self._regex = re.compile("|".join(patterns)) if patterns else None

    def url_disabled(self, url: str) -> bool:
        return self._regex is not None and self._regex.search(url) is not None


def _get_excluded_urls(instrumentation: str) -> _ExcludeList:
    """``opentelemetry.util.http.get_excluded_urls``, for when that package is
    absent: the instrumentation's own variable, else the generic one, as a
    comma-separated list of regular expressions searched in the URL."""
    value = os.environ.get(
        f"OTEL_PYTHON_{instrumentation}_EXCLUDED_URLS",
        os.environ.get("OTEL_PYTHON_EXCLUDED_URLS", ""),
    )
    return _ExcludeList([p.strip() for p in value.split(",")] if value else [])


# None until first use, False when the opentelemetry-api package is not
# installed (not retried on every request).
_otel: Any = None


def _opentelemetry() -> Any:
    global _otel
    if _otel is None:
        try:
            _otel = _OpenTelemetry()
        except ImportError:
            _otel = False
        except Exception:
            # OpenTelemetry is installed but cannot be loaded as configured:
            # importing opentelemetry.propagate raises ValueError when
            # OTEL_PROPAGATORS names a propagator whose package is missing.
            # Optional tracing must never fail a request, so send nothing.
            logger.debug("OpenTelemetry could not be loaded", exc_info=True)
            _otel = False
    return _otel


# The URL of the request whose headers the header provider is building, set by
# the SDK around each call of the provider: the default provider checks it
# against the excluded-URL settings. None outside such a call.
request_url: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "fishaudio_request_url", default=None
)


def opentelemetry_headers() -> Optional[dict[str, str]]:
    """The current OpenTelemetry trace context as a W3C ``traceparent`` header,
    or None.

    The default ``header_provider`` of ``FishAudio`` and ``AsyncFishAudio``.
    It needs no dependency: when the ``opentelemetry-api`` package is not
    installed, or no span is active (also when the API is installed but no
    OpenTelemetry SDK is configured), it returns None and no header is sent.

    It follows the OpenTelemetry settings that keep an HTTP client
    instrumentation such as ``opentelemetry-instrumentation-httpx`` from
    sending trace context, and returns None where they apply:

    - inside ``suppress_instrumentation()`` or
      ``suppress_http_instrumentation()`` (``opentelemetry.instrumentation.utils``),
      also without that package installed;
    - for a request whose URL matches ``OTEL_PYTHON_HTTPX_EXCLUDED_URLS`` (or,
      when that is not set, ``OTEL_PYTHON_EXCLUDED_URLS``): comma-separated
      regular expressions, searched in the full URL as the instrumentation
      sees it, such as ``https://api.fish.audio/v1/tts``. The SDK makes the
      URL known to it while it calls the header provider, so this also works
      inside a provider of your own that calls it; called anywhere else, it
      does not know the URL and checks no exclusion;
    - when the configured propagators (``OTEL_PROPAGATORS``,
      ``opentelemetry.propagate.set_global_textmap``) do not write a
      ``traceparent``, for example ``none`` or ``b3`` alone.

    It returns ``traceparent`` only, as the configured propagators write it:
    no ``baggage``, which can carry application data, and no ``tracestate``.
    This covers what the SDK adds; an HTTP instrumentation, if you use one,
    adds whatever its propagators are configured to send (by default also
    ``tracestate`` and ``baggage``), with or without this SDK.

    It never fails a request: an error inside OpenTelemetry is logged at
    debug level and no header is sent.

    To combine it with headers of your own::

        FishAudio(header_provider=lambda: {**(opentelemetry_headers() or {}), **mine()})
    """
    otel = _opentelemetry()
    if not otel:
        return None
    try:
        if otel.suppressed():
            return None
        url = request_url.get()
        if url is not None and otel.excluded(url):
            return None
        carrier: dict[str, str] = {}
        otel.inject(carrier)
        values = [v for k, v in carrier.items() if k.lower() == "traceparent"]
        if len(values) != 1 or not isinstance(values[0], str):
            return None
        return {"traceparent": values[0]}
    except Exception:
        logger.debug("Could not read the OpenTelemetry trace context", exc_info=True)
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
    """Warn once if ``response`` shows that the API used another trace than
    the one in ``sent``.

    ``sent`` are the ``traceparent`` values the SDK put on the request (from
    ``sent_traceparents``); ``response`` is the HTTP response, or the
    WebSocket handshake response. Nothing happens when no traceparent was
    sent, or when the response has no ``x-fish-trace-id`` (another server, a
    proxy that drops it) or one that is not a trace ID.

    The request httpx records on the response (``response.request``) is the
    one the transport was handed, with whatever an event hook or an
    instrumented transport changed in it; it tells a value changed in this
    process from one that left it unchanged.

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
        _warn_once(_mismatch(sent, _request_traceparents(response), received))
    except Exception:
        logger.debug("Could not check the trace ID of the response", exc_info=True)


def _request_traceparents(response: Any) -> Optional[list[str]]:
    """The traceparent values on the request httpx recorded on ``response``,
    or None when it has none."""
    try:
        headers = response.request.headers
    except Exception:  # httpx raises RuntimeError when no request is set
        return None
    values = headers.get_list("traceparent")
    return values if all(isinstance(v, str) for v in values) else None


def _api_trace_id(value: str) -> Optional[str]:
    """The trace ID of ``value`` if the API accepts it as a traceparent: a
    valid W3C traceparent of version 00, lowercase, with exactly four fields.
    Otherwise None."""
    if not value.strip(" \t").startswith("00-"):
        return None
    return traceparent_trace_id(value)


def _describe(values: Sequence[str]) -> str:
    """A set of traceparent values, as a trace ID or a count: never a header
    value as sent, which may be anything a header provider returned."""
    if not values:
        return "no traceparent"
    if len(values) > 1:
        return f"{len(values)} traceparent headers"
    trace_id = _api_trace_id(values[0])
    if trace_id is None:
        return "a traceparent the API does not accept"
    return f"trace id {trace_id}"


_ACCEPTED_FORM = (
    "The API continues a trace only when a request carries exactly one "
    "traceparent, and only a lowercase version-00 W3C traceparent, "
    "00-<32 hex trace id>-<16 hex parent id>-<2 hex flags>; anything else "
    "starts a new trace."
)


def _mismatch(
    sent: Sequence[str], final: Optional[Sequence[str]], received: str
) -> str:
    """The warning's text: what was sent, the trace the API used, and what
    the SDK can tell about why they differ."""
    headline = (
        "The trace this SDK sent is not the one Fish Audio used "
        f"(sent {_describe(sent)}; the API used {received})."
    )
    if len(sent) > 1 or _api_trace_id(sent[0]) is None:
        cause = _ACCEPTED_FORM
    elif final is None:
        cause = (
            "The value the SDK sent is valid, so another traceparent replaced "
            "it or was added after the SDK set it, or the API did not continue "
            "it. Possible causes: opentelemetry-instrumentation-httpx (it "
            "replaces the value with its own span's when the current span is "
            "in another trace), a custom httpx transport, an event hook, or a "
            "proxy."
        )
    elif list(final) != list(sent):
        cause = (
            "The value the SDK sent is valid. It was changed in this process "
            "after the SDK set it: the request went out with "
            f"{_describe(final)}."
        )
        if len(final) == 1 and _api_trace_id(final[0]) is not None:
            cause += (
                " opentelemetry-instrumentation-httpx does this when the "
                "current OpenTelemetry span is in another trace: it replaces "
                "the value with its own span's, in that trace. A custom httpx "
                "transport or an event hook can do the same."
            )
        else:
            cause += (
                " A custom httpx transport or an event hook can do this. "
                + _ACCEPTED_FORM
            )
    else:
        cause = (
            "The value the SDK sent is valid and was still on the request "
            "when httpx handed it to the transport. So it was replaced, or a "
            "second traceparent added, after that point (for example by a "
            "custom transport that sends a modified copy, or by a proxy), or "
            "the API did not continue it."
        )
    return f"{headline} {cause} See {OBSERVABILITY_DOCS}"


# While set, a mismatch found in this context is queued here instead of being
# issued, for the caller's task to issue (``issue_deferred``): the async
# realtime speech-to-text handshake runs in a task the SDK starts, where no
# caller frame is on the stack for the warning to name.
_deferred: contextvars.ContextVar[Optional[list[str]]] = contextvars.ContextVar(
    "fishaudio_deferred_trace_warnings", default=None
)


@contextlib.contextmanager
def deferring_warnings(queue: list[str]) -> Iterator[None]:
    """Queue the trace warnings of tasks started in this block in ``queue``."""
    token = _deferred.set(queue)
    try:
        yield
    finally:
        _deferred.reset(token)


def issue_deferred(queue: list[str]) -> None:
    """Issue the warnings queued in ``queue``, naming the caller's code."""
    while queue:
        _issue(queue.pop(0))


def _warn_once(message: str) -> None:
    global _warned
    with _warned_lock:
        if _warned:
            return
        _warned = True
    queue = _deferred.get()
    if queue is not None:
        queue.append(message)
        return
    _issue(message)


def _issue(message: str) -> None:
    try:
        warnings.warn(message, TraceNotContinuedWarning, stacklevel=_stacklevel())
    except Exception:
        # The caller's warning filters turned it into an exception: the
        # request has succeeded or failed on its own, so log it instead.
        logger.warning("%s", message)


def _stacklevel() -> int:
    """The stack level for warnings.warn: the first frame outside the SDK, so
    the warning names the caller's line. Level 1 is ``_issue``.

    Should no caller frame be on the stack (a task the SDK starts that does
    not defer its warnings), the warning names this module instead of a line
    inside asyncio.
    """
    level = 2
    frame = sys._getframe(2)  # The caller of _issue, at level 2.
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
