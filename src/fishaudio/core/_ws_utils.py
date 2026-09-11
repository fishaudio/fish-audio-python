"""Internal helpers for synchronous httpx-ws sessions."""

from __future__ import annotations

import contextlib
import logging
import socket
from typing import Any

import wsproto.events

logger = logging.getLogger(__name__)


def drain_reader(ws: Any) -> None:
    """Send the close frame, shut the socket down, and wait for httpx-ws's reader
    thread to exit before the session's own ``close()`` frees the fd.

    Why this is needed (Linux only in practice):

    httpx-ws's sync ``WebSocketSession`` reads on a background thread and closes the
    socket from the calling thread. A read that has *not started yet* is harmless:
    CPython's ``SSLSocket._real_close`` sets ``_sslobj = None`` before closing the
    fd, so a later read falls through to ``socket.recv`` on fd ``-1`` and fails with
    ``EBADF``. The problem is the read that is *already in flight*. On Linux,
    ``close()`` does not interrupt a thread blocked in ``recv()``. OpenSSL (with
    read_ahead off) fetches a TLS record header and body with separate ``read(fd)``
    calls on the fd number cached in its BIO, so when the server's close-frame reply
    arrives the second ``read()`` can land on a brand-new connection that has since
    reused the same fd number, and that new session fails with
    ``[SSL: WRONG_VERSION_NUMBER]`` or a similar TLS error. macOS wakes the blocked
    reader with ``EBADF`` on ``close()``, so it is unaffected.

    The fix is to end the in-flight read *before* the fd is freed: send the close
    frame (so the server still sees a clean 1000 close rather than 1006), then
    ``shutdown(SHUT_RDWR)`` the socket, which wakes the blocked reader with EOF, and
    join the reader thread. The later ``close()`` sees ``LOCAL_CLOSING`` and skips
    sending a second frame.

    Residual risk: if httpx-ws has already closed the socket on one of its own error
    paths (keepalive ping timeout, or a sender ``WriteError`` triggering ``close()``),
    the fd is already freed, ``shutdown()`` fails with ``EBADF``, and the in-flight
    read can still race. That can only be fixed inside httpx-ws's ``close()``.
    """
    try:
        stream = getattr(ws, "stream", None)
        if stream is None:
            response = getattr(ws, "response", None)
            stream = response.extensions.get("network_stream") if response else None
        sock = stream.get_extra_info("socket") if stream is not None else None

        # Moves the wsproto state to LOCAL_CLOSING; later close() calls skip the frame.
        with contextlib.suppress(Exception):
            ws.send(wsproto.events.CloseConnection(1000))

        if sock is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

        thread = getattr(ws, "_background_receive_task", None)
        if thread is not None:
            # 5 s is the worst case only when the reader is stuck; httpx-ws's own
            # untimed join in __exit__ would hang afterwards anyway.
            thread.join(timeout=5)
    except Exception:
        logger.debug("drain_reader failed; falling back to plain close", exc_info=True)
