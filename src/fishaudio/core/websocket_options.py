"""WebSocket-level options for WebSocket connections."""

from typing import Any, Dict, Optional


class WebSocketOptions:
    """
    Options that can be provided to configure WebSocket connections.

    Attributes:
        keepalive_ping_timeout_seconds: Maximum time to wait for a pong response
            to a keepalive ping before considering the connection dead (default: 20s)
        keepalive_ping_interval_seconds: Interval between keepalive pings (default: 20s)
        max_message_size_bytes: Maximum size for incoming messages (default: 65,536 bytes)
        queue_size: Size of the message receive queue (default: 512)
    """

    def __init__(
        self,
        *,
        keepalive_ping_timeout_seconds: Optional[float] = None,
        keepalive_ping_interval_seconds: Optional[float] = None,
        max_message_size_bytes: Optional[int] = None,
        queue_size: Optional[int] = None,
    ):
        self.keepalive_ping_timeout_seconds = keepalive_ping_timeout_seconds
        self.keepalive_ping_interval_seconds = keepalive_ping_interval_seconds
        self.max_message_size_bytes = max_message_size_bytes
        self.queue_size = queue_size

    def to_httpx_ws_kwargs(self) -> Dict[str, Any]:
        """Convert to kwargs dict for httpx_ws aconnect_ws/connect_ws."""
        kwargs = {}
        if self.keepalive_ping_timeout_seconds is not None:
            kwargs["keepalive_ping_timeout_seconds"] = (
                self.keepalive_ping_timeout_seconds
            )
        if self.keepalive_ping_interval_seconds is not None:
            kwargs["keepalive_ping_interval_seconds"] = (
                self.keepalive_ping_interval_seconds
            )
        if self.max_message_size_bytes is not None:
            kwargs["max_message_size_bytes"] = self.max_message_size_bytes
        if self.queue_size is not None:
            kwargs["queue_size"] = self.queue_size
        return kwargs
