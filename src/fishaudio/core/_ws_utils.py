"""Internal helpers for synchronous httpx-ws sessions."""

from __future__ import annotations

import contextlib
import socket
from typing import Any


def drain_reader(ws: Any) -> None:
    """Wake httpx-ws's background reader and wait for it to exit before the socket is
    closed, so it can never read() a reused fd that belongs to the next connection.

    httpx-ws's sync ``WebSocketSession`` reads on a background thread. When the
    session is closed, the socket is closed while that reader may be about to call
    ``read()``. If the OS hands the same file descriptor to the next connection, the
    stale reader consumes the new connection's bytes through the old SSL object and
    the new session fails with ``[SSL: WRONG_VERSION_NUMBER]`` or similar errors.
    """
    try:
        response = getattr(ws, "response", None)
        stream = response.extensions.get("network_stream") if response else None
        sock = stream.get_extra_info("socket") if stream is not None else None
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
        thread = getattr(ws, "_background_receive_task", None)
        if thread is not None:
            thread.join(timeout=5)
    except Exception:
        pass
