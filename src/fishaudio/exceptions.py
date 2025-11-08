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
