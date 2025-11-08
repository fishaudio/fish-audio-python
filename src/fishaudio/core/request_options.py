"""Request-level options for API calls."""

from typing import Dict, Optional

import httpx


class RequestOptions:
    """
    Options that can be provided on a per-request basis to override client defaults.

    Attributes:
        timeout: Override the client's default timeout (in seconds)
        max_retries: Override the client's default max retries
        additional_headers: Additional headers to include in the request
        additional_query_params: Additional query parameters to include
    """

    def __init__(
        self,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        additional_headers: Optional[Dict[str, str]] = None,
        additional_query_params: Optional[Dict[str, str]] = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.additional_headers = additional_headers or {}
        self.additional_query_params = additional_query_params or {}

    def get_timeout(self) -> Optional[httpx.Timeout]:
        """Convert timeout to httpx.Timeout if set."""
        if self.timeout is not None:
            return httpx.Timeout(self.timeout)
        return None
