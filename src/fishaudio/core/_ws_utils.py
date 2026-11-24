"""Internal helpers for synchronous httpx-ws sessions."""

from __future__ import annotations

import contextlib
import logging
import queue
import socket
import threading
import time
from typing import Any

import wsproto.events

logger = logging.getLogger(__name__)

# How long a close frame may take to be written before the socket is shut down
# without it.
_CLOSE_FRAME_SECONDS = 0.5


def _send_close_frame(ws: Any) -> None:
    with contextlib.suppress(Exception):
        ws.send(wsproto.events.CloseConnection(1000))


def _socket(ws: Any) -> Any:
    stream = getattr(ws, "stream", None)
    if stream is None:
        response = getattr(ws, "response", None)
        stream = response.extensions.get("network_stream") if response else None
    return stream.get_extra_info("socket") if stream is not None else None


def interrupt_writes(ws: Any) -> None:
    """Make a socket write that is blocked in another thread fail now.

    A write blocks for as long as the peer does not read, and httpx-ws holds its
    write lock meanwhile, so nothing else can be sent either, not even the close
    frame. Shutting the socket down is the only way to end that from outside.
    """
    try:
        sock = _socket(ws)
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        logger.debug("interrupt_writes failed", exc_info=True)


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
    frame (so the server still sees a clean 1000 close rather than 1006; a peer
    that has stopped reading does not get one, see below), then
    ``shutdown(SHUT_RDWR)`` the socket, which wakes the blocked reader with EOF, and
    join the reader thread. The later ``close()`` sees ``LOCAL_CLOSING`` and skips
    sending a second frame.

    Residual risk: if httpx-ws has already closed the socket on one of its own error
    paths (keepalive ping timeout, or a sender ``WriteError`` triggering ``close()``),
    the fd is already freed, ``shutdown()`` fails with ``EBADF``, and the in-flight
    read can still race. That can only be fixed inside httpx-ws's ``close()``.
    """
    try:
        sock = _socket(ws)

        # Moves the wsproto state to LOCAL_CLOSING; later close() calls skip the frame.
        # The frame is a socket write, and httpx-ws writes without a timeout: it
        # does not finish while the peer is not reading and the send buffer is
        # full. So it is sent from a helper thread and given a deadline. The
        # shutdown below makes a write that is still blocked fail.
        closer = threading.Thread(
            target=_send_close_frame,
            args=(ws,),
            name="fishaudio-ws-close-frame",
            daemon=True,
        )
        closer.start()
        closer.join(timeout=_CLOSE_FRAME_SECONDS)

        if sock is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
        closer.join(timeout=_CLOSE_FRAME_SECONDS)

        events = getattr(ws, "_events", None)

        def discard_unread_events() -> None:
            if isinstance(events, queue.Queue):
                with contextlib.suppress(queue.Empty):
                    while True:
                        events.get_nowait()

        thread = getattr(ws, "_background_receive_task", None)
        if thread is not None:
            # The reader can also be blocked putting an event into httpx-ws's
            # bounded queue (the consumer stopped reading). Nothing will read
            # those events any more, so discard them until the thread exits;
            # httpx-ws's own untimed join in __exit__ would hang otherwise.
            deadline = time.monotonic() + 5
            thread.join(timeout=0.02)
            while thread.is_alive() is True and time.monotonic() < deadline:
                discard_unread_events()
                thread.join(timeout=0.02)

        # The keepalive thread writes to the same queue: after a ping timeout it
        # closes the transport and puts an error. With the queue still full and
        # the reader gone it would block there, and httpx-ws joins it without a
        # timeout too. Make room once more now that the reader adds nothing.
        discard_unread_events()
    except Exception:
        logger.debug("drain_reader failed; falling back to plain close", exc_info=True)
