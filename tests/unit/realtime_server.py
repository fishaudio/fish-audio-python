"""A scripted WebSocket server that speaks the server side of /v1/asr/realtime.

It listens on a real TCP socket and frames messages with wsproto, so the tests
exercise the SDK's actual transport (httpx + httpx-ws) rather than mocks of it.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

import ormsgpack
from wsproto import ConnectionType, WSConnection
from wsproto.events import (
    AcceptConnection,
    BytesMessage,
    CloseConnection,
    Ping,
    RejectConnection,
    Request,
)

SESSION_STARTED = {
    "type": "session_started",
    "seq": 0,
    "session_id": "s_test",
    "request_id": "req_test",
    "config": {"model": "transcribe-stream-1"},
    "limits": {"max_session_ms": 3600000},
}


class ClientGone(Exception):
    """The client closed the connection."""


class Connection:
    """One client connection, as seen by a server script."""

    def __init__(self, sock: socket.socket, reject_status: Optional[int]):
        self._sock = sock
        self._ws = WSConnection(ConnectionType.SERVER)
        self._reject_status = reject_status
        self._pending: deque[dict[str, Any]] = deque()
        self._partial = b""
        self.headers: dict[str, str] = {}
        self.path: Optional[str] = None
        self.received: list[dict[str, Any]] = []
        self.close_code: Optional[int] = None

    def _write(self, event: Any) -> None:
        self._sock.sendall(self._ws.send(event))

    def _read(self) -> None:
        try:
            data = self._sock.recv(65536)
        except socket.timeout:
            raise
        except OSError:
            data = b""
        if not data:
            raise ClientGone
        self._ws.receive_data(data)
        for event in self._ws.events():
            if isinstance(event, Request):
                self.path = event.target
                self.headers = {k.decode(): v.decode() for k, v in event.extra_headers}
                if self._reject_status is not None:
                    self._write(RejectConnection(status_code=self._reject_status))
                    raise ClientGone
                self._write(AcceptConnection())
            elif isinstance(event, BytesMessage):
                self._partial += bytes(event.data)
                if event.message_finished:
                    self._pending.append(ormsgpack.unpackb(self._partial))
                    self._partial = b""
            elif isinstance(event, Ping):
                self._write(event.response())
            elif isinstance(event, CloseConnection):
                self.close_code = event.code
                with contextlib.suppress(Exception):
                    self._write(event.response())
                raise ClientGone

    def handshake(self) -> None:
        while self.path is None:
            self._read()

    def recv(self) -> dict[str, Any]:
        """The next message from the client. Raises ClientGone when it has left."""
        while not self._pending:
            self._read()
        message = self._pending.popleft()
        self.received.append(message)
        return message

    def recv_until(self, message_type: str) -> list[dict[str, Any]]:
        """Read up to and including the first message of the given type."""
        messages = []
        while not messages or messages[-1]["type"] != message_type:
            messages.append(self.recv())
        return messages

    def quiet_for(self, seconds: float) -> bool:
        """True if the client sends no message for the whole of the given time.

        Pings and partial frames do not end the wait early.
        """
        deadline = time.monotonic() + seconds
        try:
            while not self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._sock.settimeout(remaining)
                try:
                    self._read()
                except socket.timeout:
                    break
        finally:
            self._sock.settimeout(5)
        return not self._pending

    def send(self, message: dict[str, Any]) -> None:
        self._write(BytesMessage(data=ormsgpack.packb(message)))

    def send_raw(self, data: bytes) -> None:
        self._write(BytesMessage(data=data))

    def close(self, code: int = 1000, reason: str = "") -> None:
        self._write(CloseConnection(code=code, reason=reason))

    def drop(self) -> None:
        """Cut the TCP connection without a close frame."""
        self._sock.close()

    def wait_gone(self) -> None:
        """Block until the client has closed the connection."""
        with contextlib.suppress(ClientGone):
            while True:
                self.recv()
        # Messages that arrived in the same read as the close frame.
        self.received.extend(self._pending)
        self._pending.clear()


class RealtimeServer:
    """Runs ``script(connection)`` for the first client that connects."""

    def __init__(
        self,
        script: Callable[[Connection], None],
        *,
        reject_status: Optional[int] = None,
    ):
        self._script = script
        self._reject_status = reject_status
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(5)
        self.url = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        self.connection: Optional[Connection] = None
        self.error: Optional[BaseException] = None
        self.finished = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            sock, _ = self._listener.accept()
        except OSError:
            self.finished.set()
            return
        sock.settimeout(5)
        self.connection = Connection(sock, self._reject_status)
        try:
            self.connection.handshake()
            self._script(self.connection)
            self.connection.wait_gone()
        except ClientGone:
            pass
        except BaseException as e:
            self.error = e
        finally:
            with contextlib.suppress(OSError):
                sock.close()
            self.finished.set()

    def stop(self) -> Connection:
        """Wait for the script to end, re-raise its failure, return the connection."""
        assert self.finished.wait(10), "server script did not finish"
        self.close()
        if self.error is not None:
            raise self.error
        assert self.connection is not None, "no client connected"
        return self.connection

    def close(self) -> None:
        """Stop listening. Called by stop(); safe to call again."""
        self._listener.close()
