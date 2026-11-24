"""Minimal Server-Sent Events decoder."""

from typing import NamedTuple


class ServerSentEvent(NamedTuple):
    """One dispatched SSE event."""

    event: str
    data: str


class SSEDecoder:
    """Incrementally decode a Server-Sent Events byte stream.

    Feed raw response bytes with `feed()`; each call returns the events that
    were completed by those bytes. Lines are split on LF or CRLF only, so
    payloads that contain other Unicode line separators stay intact. An event
    left unterminated when the stream ends is dropped, as the SSE
    specification requires.
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._event = ""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[ServerSentEvent]:
        """Add bytes from the stream and return the events they complete."""
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")

        events = []
        for raw in lines:
            line = raw[:-1] if raw.endswith(b"\r") else raw
            if not line:
                if self._data:
                    events.append(
                        ServerSentEvent(self._event or "message", "\n".join(self._data))
                    )
                self._event = ""
                self._data = []
                continue
            if line.startswith(b":"):
                continue  # comment, used by servers as a keep-alive

            name, _, value = line.decode("utf-8", errors="replace").partition(":")
            if value.startswith(" "):
                value = value[1:]
            if name == "data":
                self._data.append(value)
            elif name == "event":
                self._event = value
        return events
