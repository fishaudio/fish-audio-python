"""Custom exceptions for the Fish Audio SDK."""

from typing import Optional


class FishAudioError(Exception):
    """Base exception for all Fish Audio SDK errors."""

    pass


class APIError(FishAudioError):
    """Raised when the API returns an error response."""

    def __init__(self, status: int, message: str, body: Optional[str] = None):
        self.status = status
        self.message = message
        self.body = body
        super().__init__(f"HTTP {status}: {message}")


class AuthenticationError(APIError):
    """Raised when authentication fails (401)."""

    pass


class PermissionError(APIError):
    """Raised when permission is denied (403)."""

    pass


class NotFoundError(APIError):
    """Raised when a resource is not found (404)."""

    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded (429)."""

    pass


class ServerError(APIError):
    """Raised when the server encounters an error (5xx)."""

    pass


class WebSocketError(FishAudioError):
    """Raised when WebSocket connection or streaming fails."""

    pass


class ASRRealtimeError(WebSocketError):
    """Raised when a realtime speech-to-text session ends with an error.

    Attributes:
        message: A short English description, for humans
        error_type: Machine-readable error type from the server's error event
            (e.g., "invalid_config", "idle_timeout"). None if the connection closed
            without one
        code: HTTP-style status from the server's error event. None if not sent
        request_id: Identifier of the request; quote it when reporting a problem
        close_code: WebSocket close code (e.g., 4400, 4408, 1012). None if the error
            was raised before the connection closed
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: Optional[str] = None,
        code: Optional[int] = None,
        request_id: Optional[str] = None,
        close_code: Optional[int] = None,
    ):
        self.message = message
        self.error_type = error_type
        self.code = code
        self.request_id = request_id
        self.close_code = close_code
        details = [
            f"close code {close_code}" if close_code is not None else None,
            f"request {request_id}" if request_id else None,
        ]
        suffix = ", ".join(d for d in details if d)
        super().__init__(
            (f"{error_type}: " if error_type else "")
            + message
            + (f" ({suffix})" if suffix else "")
        )


class ValidationError(FishAudioError):
    """Raised when request validation fails."""

    pass


class DependencyError(FishAudioError):
    """Raised when a required dependency is missing."""

    def __init__(self, dependency: str, install_command: str):
        self.dependency = dependency
        self.install_command = install_command
        super().__init__(
            f"Missing required dependency: {dependency}\n"
            f"Install it with: {install_command}"
        )
