"""Real-time WebSocket streaming helpers."""

from typing import Any, AsyncIterator, Dict, Iterator, Optional

import ormsgpack
from httpx_ws import WebSocketDisconnect

from ..exceptions import WebSocketError


def _should_stop(data: Dict[str, Any]) -> bool:
    """
    Check if WebSocket event signals stream should stop.

    Args:
        data: Unpacked WebSocket message data

    Returns:
        True if stream should stop, False otherwise
    """
    return data.get("event") == "finish" and data.get("reason") == "stop"


def _process_audio_event(data: Dict[str, Any]) -> Optional[bytes]:
    """
    Process a WebSocket audio event.

    Args:
        data: Unpacked WebSocket message data

    Returns:
        Audio bytes if audio event, None for unknown events

    Raises:
        WebSocketError: If finish event has error reason
    """
    if data.get("event") == "audio":
        return data.get("audio")
    elif data.get("event") == "finish" and data.get("reason") == "error":
        raise WebSocketError("WebSocket stream ended with error")
    return None  # Ignore unknown events


def iter_websocket_audio(ws) -> Iterator[bytes]:
    """
    Process WebSocket audio messages (sync).

    Receives messages from WebSocket, yields audio chunks, handles errors.
    Unknown events are ignored and iteration continues.

    Args:
        ws: WebSocket connection from httpx_ws.connect_ws

    Yields:
        Audio bytes

    Raises:
        WebSocketError: On disconnect or error finish event
    """
    while True:
        try:
            message = ws.receive_bytes()
            data = ormsgpack.unpackb(message)

            if _should_stop(data):
                break

            audio = _process_audio_event(data)
            if audio is not None:
                yield audio

        except WebSocketDisconnect:
            raise WebSocketError("WebSocket disconnected unexpectedly")


async def aiter_websocket_audio(ws) -> AsyncIterator[bytes]:
    """
    Process WebSocket audio messages (async).

    Receives messages from WebSocket, yields audio chunks, handles errors.
    Unknown events are ignored and iteration continues.

    Args:
        ws: WebSocket connection from httpx_ws.aconnect_ws

    Yields:
        Audio bytes

    Raises:
        WebSocketError: On disconnect or error finish event
    """
    while True:
        try:
            message = await ws.receive_bytes()
            data = ormsgpack.unpackb(message)

            if _should_stop(data):
                break

            audio = _process_audio_event(data)
            if audio is not None:
                yield audio

        except WebSocketDisconnect:
            raise WebSocketError("WebSocket disconnected unexpectedly")
