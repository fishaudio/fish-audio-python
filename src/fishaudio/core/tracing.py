"""The default header provider: the current OpenTelemetry span as ``traceparent``."""

from __future__ import annotations

import logging
from typing import Any, Optional

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

    It sends ``traceparent`` only, built from the span's IDs and flags. It
    sends no ``baggage``, which can carry application data, and no
    ``tracestate``, and it does not use the configured propagator, because
    Fish Audio reads the W3C ``traceparent`` only.

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
