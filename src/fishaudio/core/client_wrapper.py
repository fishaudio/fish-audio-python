"""HTTP client wrapper for managing requests and authentication."""

import os
import platform
import re
import sys
from json import JSONDecodeError
from typing import Any, Optional, Union

import httpx

from fishaudio._version import __version__
from fishaudio.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
)

from .request_options import RequestOptions
from .websocket_options import WebSocketOptions


def _api_error(status: int, message: str, body: Optional[str] = None) -> APIError:
    """Build the exception that matches an HTTP error status."""
    if status == 401:
        return AuthenticationError(status, message, body)
    if status == 403:
        return PermissionError(status, message, body)
    if status == 404:
        return NotFoundError(status, message, body)
    if status == 429:
        return RateLimitError(status, message, body)
    if status >= 500:
        return ServerError(status, message, body)
    return APIError(status, message, body)


def _raise_for_status(response: httpx.Response) -> None:
    """Raise appropriate exception based on status code."""
    status = response.status_code

    # Try to extract error message from response
    try:
        error_data = response.json()
        message = error_data.get("message") or error_data.get("detail") or response.text
    except JSONDecodeError:
        message = response.text or httpx.codes.get_reason_phrase(status)

    raise _api_error(status, message, response.text)


PRODUCT = f"fish-audio-python/{__version__}"
"""The SDK's product, ``fish-audio-<language>/<version>``: the format every Fish
Audio SDK sends, so the API can tell which SDK and version made a request."""

_SAFE_PREFIX = re.compile(r"[A-Za-z0-9._+-]+")


def _comment_value(value: object) -> str:
    """Make a value safe inside an RFC 9110 comment.

    Keeps the leading run of letters, digits and ``._+-`` (at most 32
    characters) and drops the rest, so ``(``, ``)``, ``\\``, whitespace and
    control characters never reach the header. Returns ``unknown`` when
    nothing usable is left.
    """
    if not isinstance(value, str):
        return "unknown"
    match = _SAFE_PREFIX.match(value.strip())
    return match.group(0)[:32] if match else "unknown"


def _os_family(sys_platform: object) -> str:
    """The OS family as one short lowercase word: linux, darwin, windows, ..."""
    os_name = _comment_value(
        sys_platform.lower() if isinstance(sys_platform, str) else sys_platform
    )
    if os_name in ("win32", "cygwin", "msys"):
        return "windows"
    # sys.platform carries a version on some systems, e.g. freebsd14.
    return os_name.rstrip("0123456789") or "unknown"


def build_user_agent(python_version: object, sys_platform: object) -> str:
    """Return ``fish-audio-python/<version> (python <python version>; <os>)``.

    Only the runtime, its version and the OS family are included: nothing
    that identifies a person or machine.
    """
    return (
        f"{PRODUCT} (python {_comment_value(python_version)}; "
        f"{_os_family(sys_platform)})"
    )


USER_AGENT = build_user_agent(platform.python_version(), sys.platform)
"""The User-Agent the SDK sends, computed once at import, e.g.
``fish-audio-python/1.6.0 (python 3.12.1; linux)``."""

# What httpx sends when nobody set a User-Agent; only this exact value is ignored.
_HTTPX_DEFAULT_USER_AGENT = f"python-httpx/{httpx.__version__}"


def user_agent(caller: Optional[str] = None) -> str:
    """Return the User-Agent to send: the SDK's own, then ``caller`` if set.

    A caller's value is appended after the SDK's product and runtime comment
    rather than allowed to replace them, so an app can name itself without
    hiding which SDK made the request. A value that already starts with the
    SDK's User-Agent is not doubled.
    """
    value = (caller or "").strip()
    if value == USER_AGENT or value.startswith(f"{USER_AGENT} "):
        value = value[len(USER_AGENT) :].strip()
    return f"{USER_AGENT} {value}" if value else USER_AGENT


def _caller_user_agent(
    client: Union[httpx.Client, httpx.AsyncClient, None],
) -> Optional[str]:
    """The User-Agent on an httpx client, unless it is httpx's unchanged default.

    A customised value that merely starts with httpx's product, such as
    ``python-httpx/0.28.1 my-app/1.0``, is kept.
    """
    if client is None:
        return None
    value = client.headers.get("user-agent")
    if not value or value.strip() == _HTTPX_DEFAULT_USER_AGENT:
        return None
    return value


class BaseClientWrapper:
    """Base wrapper with shared logic for sync/async clients."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
    ):
        # Without the whitespace around it: a key read from a file or an
        # environment variable often ends with a newline, which httpx refuses
        # with an error that prints the whole Authorization header.
        self.api_key = (api_key or os.getenv("FISH_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError(
                "API key must be provided either as argument or via FISH_API_KEY environment variable"
            )
        self.base_url = base_url

    def get_headers(
        self, additional_headers: Optional[dict[str, str]] = None
    ) -> dict[str, str]:
        """Build headers including authentication and user agent.

        A name in ``additional_headers`` replaces the SDK's header of that
        name whatever its case, so the two are never sent side by side. The
        exception is ``User-Agent``: one in ``additional_headers`` (any
        casing), or else one set on a user-supplied httpx client, is appended
        to the SDK's own.
        """
        headers: dict[str, str] = {"Authorization": f"Bearer {self.api_key}"}
        # Read from the client on every call, so a User-Agent changed on a
        # supplied httpx client after construction is used. The SDK's own
        # client carries USER_AGENT, which user_agent() does not double.
        caller = _caller_user_agent(getattr(self, "_client", None))
        extra = {}
        for name, value in (additional_headers or {}).items():
            if name.lower() == "user-agent":
                caller = value
            else:
                extra[name] = value
        replaced = {name.lower() for name in extra}
        headers = {k: v for k, v in headers.items() if k.lower() not in replaced}
        headers.update(extra)
        headers["User-Agent"] = user_agent(caller)
        return headers

    def _prepare_request_kwargs(
        self, request_options: Optional[RequestOptions], kwargs: dict[str, Any]
    ) -> None:
        """Prepare request kwargs by merging headers, timeout, and query params."""
        # Merge headers
        headers = self.get_headers(
            request_options.additional_headers if request_options else None
        )
        # Headers set by the calling method win, whatever the case of the name:
        # {"Model": ...} from request options must not travel next to {"model": ...}.
        explicit = kwargs.get("headers", {})
        explicit_names = {name.lower() for name in explicit}
        kwargs["headers"] = {
            **{k: v for k, v in headers.items() if k.lower() not in explicit_names},
            **explicit,
        }

        # Apply timeout override if provided
        if request_options and request_options.timeout is not None:
            kwargs["timeout"] = httpx.Timeout(request_options.timeout)

        # Add query params override if provided
        if request_options and request_options.additional_query_params:
            params = kwargs.get("params", {})
            if isinstance(params, dict):
                params.update(request_options.additional_query_params)
                kwargs["params"] = params


def handshake_headers(
    client_wrapper: BaseClientWrapper,
    model: str,
    ws_options: Optional[WebSocketOptions],
) -> httpx.Headers:
    """Build the headers of a WebSocket handshake.

    ``ws_options.additional_headers`` come first; the SDK's own headers replace
    any spelling of the same name. The exception is ``User-Agent``, which is
    appended to the SDK's own, as on HTTP calls.
    """
    additional = dict((ws_options.additional_headers if ws_options else None) or {})
    own = {"model": model}
    for name in list(additional):
        if name.lower() == "user-agent":
            # The last spelling wins, as in get_headers().
            own["User-Agent"] = additional.pop(name)
    headers = httpx.Headers(additional)
    headers.update(client_wrapper.get_headers(own))
    return headers


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
                headers=self.get_headers(),
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        request_options: Optional[RequestOptions] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            request_options: Optional request-level overrides
            stream: If True, return as soon as the response headers arrive and
                leave the body unread. The caller must consume it with
                `iter_bytes()` and then call `close()` on the response.
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            httpx.Response object

        Raises:
            APIError: On non-2xx responses
        """
        self._prepare_request_kwargs(request_options, kwargs)

        if stream:
            timeout = kwargs.pop("timeout", httpx.USE_CLIENT_DEFAULT)
            http_request = self._client.build_request(
                method, path, timeout=timeout, **kwargs
            )
            response = self._client.send(http_request, stream=True)
            if not response.is_success:
                try:
                    response.read()
                finally:
                    response.close()
                _raise_for_status(response)
            return response

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
                headers=self.get_headers(),
            )

    async def request(
        self,
        method: str,
        path: str,
        *,
        request_options: Optional[RequestOptions] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an async HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            request_options: Optional request-level overrides
            stream: If True, return as soon as the response headers arrive and
                leave the body unread. The caller must consume it with
                `aiter_bytes()` and then call `aclose()` on the response.
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            httpx.Response object

        Raises:
            APIError: On non-2xx responses
        """
        self._prepare_request_kwargs(request_options, kwargs)

        if stream:
            timeout = kwargs.pop("timeout", httpx.USE_CLIENT_DEFAULT)
            http_request = self._client.build_request(
                method, path, timeout=timeout, **kwargs
            )
            response = await self._client.send(http_request, stream=True)
            if not response.is_success:
                try:
                    await response.aread()
                finally:
                    await response.aclose()
                _raise_for_status(response)
            return response

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
