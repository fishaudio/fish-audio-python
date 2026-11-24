"""Minimal Server-Sent Events decoder."""

from typing import NamedTuple


class ServerSentEvent(NamedTuple):
    """One dispatched SSE event."""

    event: str
    data: str


class SSEDecoder:
    """Incrementally decode a Server-Sent Events byte stream.

    Feed raw response bytes with `feed()`; each call returns the events that
    were completed by those bytes. Lines end with CRLF, LF or CR, the three
    endings the SSE specification allows; other Unicode line separators stay
    inside the payload. An event left unterminated when the stream ends is
    dropped, as the specification requires.
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._skip_lf = False
        self._event = ""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[ServerSentEvent]:
        """Add bytes from the stream and return the events they complete."""
        if not chunk:
            return []
        # A CR ends its line at once, so a CR-only stream is never held back.
        # If the previous chunk ended with CR, a leading LF here is the second
        # half of a CRLF pair and not another line ending.
        if self._skip_lf and chunk.startswith(b"\n"):
            chunk = chunk[1:]
        self._skip_lf = chunk.endswith(b"\r")

        chunk = chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        *lines, self._buffer = (self._buffer + chunk).split(b"\n")

        events = []
        for line in lines:
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
