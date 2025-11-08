"""Real-time WebSocket streaming helpers."""

from typing import Any, AsyncIterator, Dict, Iterator, Optional

import ormsgpack
from httpx_ws import WebSocketDisconnect

from ..exceptions import WebSocketError


def _process_audio_event(data: Dict[str, Any]) -> Optional[bytes]:
    """
    Process a WebSocket audio event.

    Args:
        data: Unpacked WebSocket message data

    Returns:
        Audio bytes if audio event, None if should stop

    Raises:
        WebSocketError: If finish event has error reason
    """
    if data["event"] == "audio":
        return data["audio"]
    elif data["event"] == "finish" and data["reason"] == "error":
        raise WebSocketError("WebSocket stream ended with error")
    elif data["event"] == "finish" and data["reason"] == "stop":
        return None  # Signal to stop
    return None  # Ignore unknown events


def iter_websocket_audio(ws) -> Iterator[bytes]:
    """
    Process WebSocket audio messages (sync).

    Receives messages from WebSocket, yields audio chunks, handles errors.

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
            audio = _process_audio_event(data)
            if audio is None:
                break
            yield audio
        except WebSocketDisconnect:
            raise WebSocketError("WebSocket disconnected unexpectedly")


async def aiter_websocket_audio(ws) -> AsyncIterator[bytes]:
    """
    Process WebSocket audio messages (async).

    Receives messages from WebSocket, yields audio chunks, handles errors.

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
            audio = _process_audio_event(data)
            if audio is None:
                break
            yield audio
        except WebSocketDisconnect:
            raise WebSocketError("WebSocket disconnected unexpectedly")
