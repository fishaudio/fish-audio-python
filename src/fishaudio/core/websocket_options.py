"""WebSocket-level options for WebSocket connections."""

from typing import Any, Optional


class WebSocketOptions:
    """
    Options for configuring WebSocket connections.

    All options except ``additional_headers`` are passed directly to httpx_ws's
    connect_ws/aconnect_ws functions. For complete documentation, see
    https://frankie567.github.io/httpx-ws/reference/httpx_ws/

    Attributes:
        keepalive_ping_timeout_seconds: Maximum delay the client will wait for an answer
            to its Ping event. If the delay is exceeded, WebSocketNetworkError will be
            raised and the connection closed. Default: 20 seconds.
        keepalive_ping_interval_seconds: Interval at which the client will automatically
            send a Ping event to keep the connection alive. Set to None to disable this
            mechanism. Default: 20 seconds.
        max_message_size_bytes: Message size in bytes to receive from the server.
            Default: 65536 bytes (64 KiB).
        queue_size: Size of the queue where received messages will be held until they
            are consumed. If the queue is full, the client will stop receiving messages
            from the server until the queue has room available. Default: 512.
        additional_headers: Extra headers to send on the WebSocket handshake, for
            example ``{"traceparent": ...}``. The headers the SDK sets itself
            (``Authorization``, ``User-Agent``, ``model``) are kept, whatever the
            casing of a name given here. The dict is not modified.

    Note:
        Descriptions of the httpx_ws options adapted from httpx_ws documentation.
    """

    def __init__(
        self,
        *,
        keepalive_ping_timeout_seconds: Optional[float] = None,
        keepalive_ping_interval_seconds: Optional[float] = None,
        max_message_size_bytes: Optional[int] = None,
        queue_size: Optional[int] = None,
        additional_headers: Optional[dict[str, str]] = None,
    ):
        self.keepalive_ping_timeout_seconds = keepalive_ping_timeout_seconds
        self.keepalive_ping_interval_seconds = keepalive_ping_interval_seconds
        self.max_message_size_bytes = max_message_size_bytes
        self.queue_size = queue_size
        self.additional_headers = additional_headers

    def to_httpx_ws_kwargs(self) -> dict[str, Any]:
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
