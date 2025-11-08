"""HTTP client wrapper for managing requests and authentication."""

import os
from json import JSONDecodeError
from typing import Any, Dict, Optional

import httpx

from .._version import __version__
from ..exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
)
from .request_options import RequestOptions


def _raise_for_status(response: httpx.Response) -> None:
    """Raise appropriate exception based on status code."""
    status = response.status_code

    # Try to extract error message from response
    try:
        error_data = response.json()
        message = error_data.get("message") or error_data.get("detail") or response.text
    except JSONDecodeError:
        message = response.text or httpx.codes.get_reason_phrase(status)

    # Raise specific exception based on status code
    if status == 401:
        raise AuthenticationError(status, message, response.text)
    elif status == 403:
        raise PermissionError(status, message, response.text)
    elif status == 404:
        raise NotFoundError(status, message, response.text)
    elif status == 429:
        raise RateLimitError(status, message, response.text)
    elif status >= 500:
        raise ServerError(status, message, response.text)
    else:
        raise APIError(status, message, response.text)


class BaseClientWrapper:
    """Base wrapper with shared logic for sync/async clients."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
    ):
        self.api_key = api_key or os.getenv("FISH_AUDIO_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key must be provided either as argument or via FISH_AUDIO_API_KEY environment variable"
            )
        self.base_url = base_url

    def _get_headers(
        self, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build headers including authentication."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": f"fish-audio/python/{__version__}",
        }
        if additional_headers:
            headers.update(additional_headers)
        return headers

    def _prepare_request_kwargs(
        self, request_options: Optional[RequestOptions], kwargs: Dict[str, Any]
    ) -> None:
        """Prepare request kwargs by merging headers, timeout, and query params."""
        # Merge headers
        headers = self._get_headers()
        if request_options and request_options.additional_headers:
            headers.update(request_options.additional_headers)
        kwargs["headers"] = {**headers, **kwargs.get("headers", {})}

        # Apply timeout override if provided
        if request_options and request_options.timeout is not None:
            kwargs["timeout"] = httpx.Timeout(request_options.timeout)

        # Add query params override if provided
        if request_options and request_options.additional_query_params:
            params = kwargs.get("params", {})
            if isinstance(params, dict):
                params.update(request_options.additional_query_params)
                kwargs["params"] = params


class ClientWrapper(BaseClientWrapper):
    """Wrapper for httpx.Client that handles authentication and error handling."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        timeout: float = 240.0,
        httpx_client: Optional[httpx.Client] = None,
    ):
        super().__init__(api_key=api_key, base_url=base_url)

        if httpx_client is not None:
            self._client = httpx_client
        else:
            self._client = httpx.Client(
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
                headers=self._get_headers(),
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        request_options: Optional[RequestOptions] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            request_options: Optional request-level overrides
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            httpx.Response object

        Raises:
            APIError: On non-2xx responses
        """
        self._prepare_request_kwargs(request_options, kwargs)

        # Make the request
        response = self._client.request(method, path, **kwargs)

        # Handle errors
        if not response.is_success:
            _raise_for_status(response)

        return response

    @property
    def client(self) -> httpx.Client:
        """Get underlying httpx.Client for advanced usage (e.g., WebSockets)."""
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncClientWrapper(BaseClientWrapper):
    """Wrapper for httpx.AsyncClient that handles authentication and error handling."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        timeout: float = 240.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(api_key=api_key, base_url=base_url)

        if httpx_client is not None:
            self._client = httpx_client
        else:
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
                headers=self._get_headers(),
            )

    async def request(
        self,
        method: str,
        path: str,
        *,
        request_options: Optional[RequestOptions] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an async HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            request_options: Optional request-level overrides
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            httpx.Response object

        Raises:
            APIError: On non-2xx responses
        """
        self._prepare_request_kwargs(request_options, kwargs)

        # Make the request
        response = await self._client.request(method, path, **kwargs)

        # Handle errors
        if not response.is_success:
            _raise_for_status(response)

        return response

    @property
    def client(self) -> httpx.AsyncClient:
        """Get underlying httpx.AsyncClient for advanced usage (e.g., WebSockets)."""
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
