"""HTTP client wrapper for managing requests and authentication."""

import os
import platform
import re
import sys
from collections.abc import Iterable, Mapping
from json import JSONDecodeError
from typing import Any, Callable, Optional, Union

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
from .tracing import check_trace_continued, sent_traceparents


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


HeaderProvider = Callable[[], Optional[Mapping[str, Optional[str]]]]
"""A function the SDK calls for every outgoing request and WebSocket handshake.

It takes no arguments: read the caller's current state (an OpenTelemetry span,
a ``contextvars.ContextVar``) inside it. It returns the headers to add, or
``None`` to add none; a header whose value is ``None`` is skipped. See
``FishAudio(header_provider=...)``.
"""

# Headers the SDK sets itself or that the HTTP and WebSocket protocols own. A
# header provider can never set them, so it cannot replace the API key or the
# model by accident, e.g. when it copies an inbound request's headers.
_RESERVED_HEADERS = frozenset(
    {
        "authorization",
        "model",
        "user-agent",
        "content-type",
        "content-length",
        "host",
        "connection",
        "upgrade",
        "transfer-encoding",
    }
)

# RFC 9110 token characters, for header names.
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")

# A header value the SDK accepts from a header provider: RFC 9110 section 5.5
# field-value, restricted to ASCII. It is empty, or visible ASCII characters
# (0x21-0x7E) with spaces and tabs only between them, never at either end.
#
# Every value this accepts is also accepted by the transport (httpx encodes
# header values as ASCII; h11 allows the same shape) and reaches the server
# unchanged. It is deliberately stricter than h11 in one respect: h11 also
# sends DEL (0x7F) and the control characters 0x01-0x08, 0x0B, 0x0C and
# 0x0E-0x1F, which RFC 9110 does not allow in a field value and which a server
# or proxy may reject. obs-text (0x80-0xFF) is not allowed either: httpx
# cannot encode it, and RFC 9110 says new values should not use it.
_FIELD_VALUE = re.compile(r"(?:[\x21-\x7e](?:[ \t]*[\x21-\x7e])*)?")
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


def _value_problem(value: str) -> Optional[str]:
    """What is wrong with a header value, as a kind of problem, or None.

    The result never contains the value or any part of it: a header value
    may be a credential.
    """
    if _FIELD_VALUE.fullmatch(value):
        return None
    if not value.isascii():
        return "it contains a non-ASCII character"
    if "\r" in value or "\n" in value:
        return "it contains a line break"
    if _CONTROL.search(value):
        return "it contains a control character"
    # Only visible ASCII, spaces and tabs are left, so a space or tab is at
    # one end (or the value is nothing but spaces and tabs).
    return "it has leading or trailing whitespace"


def _is_reserved(name: str) -> bool:
    lowered = name.lower()
    return lowered in _RESERVED_HEADERS or lowered.startswith("sec-websocket-")


def _provided_headers(
    provider: Optional[HeaderProvider], taken: Iterable[str]
) -> dict[str, str]:
    """Call ``provider`` and return the headers it may add to a request.

    ``taken`` are the names the request already has (any casing): they win
    over the provider, as do the reserved names. Those names are ignored
    before their values are looked at, so an invalid value under them does
    not raise. An exception raised by the provider reaches the caller
    unchanged, before anything is sent.

    Every value kept is accepted by the transport and sent unchanged. A value
    that is not (see ``_FIELD_VALUE``) raises ``ValueError`` before anything
    is sent; the error names the header and the kind of problem, never the
    value, which may be a credential.
    """
    if provider is None:
        return {}
    result = provider()
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise TypeError(
            "header_provider must return a mapping of header names to strings or None, "
            f"not {type(result).__name__}"
        )
    taken_names = {name.lower() for name in taken}
    headers: dict[str, str] = {}
    for name, value in result.items():
        if value is None:
            continue
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError(
                "header_provider must return header names and values as str, "
                f"got {type(name).__name__}: {type(value).__name__}"
            )
        if not _HEADER_NAME.fullmatch(name):
            raise ValueError(
                f"header_provider returned an invalid header name {name!r}"
            )
        if _is_reserved(name) or name.lower() in taken_names:
            continue
        problem = _value_problem(value)
        if problem is not None:
            # Only the name (a validated token) and the kind of problem: the
            # value is not echoed, as it may be a credential.
            raise ValueError(
                f"header_provider returned an invalid value for header {name!r}: "
                f"{problem}. A header value must be visible ASCII characters, "
                "with spaces or tabs only between them (RFC 9110). "
                "The value is not shown."
            )
        # One spelling per name: a later one replaces an earlier one.
        for existing in [n for n in headers if n.lower() == name.lower()]:
            del headers[existing]
        headers[name] = value
    return headers


class BaseClientWrapper:
    """Base wrapper with shared logic for sync/async clients."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        header_provider: Optional[HeaderProvider] = None,
    ):
        self.api_key = api_key or os.getenv("FISH_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key must be provided either as argument or via FISH_API_KEY environment variable"
            )
        if header_provider is not None and not callable(header_provider):
            raise TypeError("header_provider must be callable")
        self.base_url = base_url
        self.header_provider = header_provider

    def get_headers(
        self, additional_headers: Optional[dict[str, str]] = None
    ) -> dict[str, str]:
        """Build headers including authentication and user agent.

        A ``User-Agent`` in ``additional_headers`` (any casing), or else one set
        on a user-supplied httpx client, is appended to the SDK's own.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        # Read from the client on every call, so a User-Agent changed on a
        # supplied httpx client after construction is used. The SDK's own
        # client carries USER_AGENT, which user_agent() does not double.
        caller = _caller_user_agent(getattr(self, "_client", None))
        for name, value in (additional_headers or {}).items():
            if name.lower() == "user-agent":
                caller = value
            else:
                headers[name] = value
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
        merged = {
            **{k: v for k, v in headers.items() if k.lower() not in explicit_names},
            **explicit,
        }
        # The header provider runs last, once per request, on the caller's
        # thread or task, so it sees the caller's context at the moment the
        # request is sent. Every header set so far, and the headers set on the
        # httpx client, win over it. (A retry loop added here later must call
        # this once per attempt.)
        client = getattr(self, "_client", None)
        merged.update(
            _provided_headers(
                self.header_provider,
                [*merged, *(client.headers.keys() if client is not None else [])],
            )
        )
        kwargs["headers"] = merged

        # Apply timeout override if provided
        if request_options and request_options.timeout is not None:
            kwargs["timeout"] = httpx.Timeout(request_options.timeout)

        # Add query params override if provided
        if request_options and request_options.additional_query_params:
            params = kwargs.get("params", {})
            if isinstance(params, dict):
                params.update(request_options.additional_query_params)
                kwargs["params"] = params

    def traceparents_sent(self, headers: Mapping[str, str]) -> list[str]:
        """The ``traceparent`` values a request with ``headers`` carries, as
        httpx merges them with the client's headers: what the SDK put there
        (the header provider, per-call headers, the httpx client's headers).
        Compared with the response by ``check_trace_continued``."""
        client = getattr(self, "_client", None)
        return sent_traceparents(headers, getattr(client, "headers", None))

    def websocket_kwargs(
        self, model: str, request_options: Optional[RequestOptions]
    ) -> dict[str, Any]:
        """Headers and query parameters for a WebSocket handshake.

        Call it when the connection is opened, not before, so the header
        provider sees the caller's context of that moment. Request options
        apply as on HTTP requests, except ``timeout``: WebSocket timeouts are
        set with ``WebSocketOptions``.
        """
        kwargs: dict[str, Any] = {"headers": {"model": model}}
        self._prepare_request_kwargs(request_options, kwargs)
        kwargs.pop("timeout", None)
        return kwargs


class ClientWrapper(BaseClientWrapper):
    """Wrapper for httpx.Client that handles authentication and error handling."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        timeout: float = 240.0,
        httpx_client: Optional[httpx.Client] = None,
        header_provider: Optional[HeaderProvider] = None,
    ):
        super().__init__(
            api_key=api_key, base_url=base_url, header_provider=header_provider
        )

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
        sent = self.traceparents_sent(kwargs["headers"])

        if stream:
            timeout = kwargs.pop("timeout", httpx.USE_CLIENT_DEFAULT)
            http_request = self._client.build_request(
                method, path, timeout=timeout, **kwargs
            )
            response = self._client.send(http_request, stream=True)
            check_trace_continued(sent, response)
            if not response.is_success:
                try:
                    response.read()
                finally:
                    response.close()
                _raise_for_status(response)
            return response

        # Make the request
        response = self._client.request(method, path, **kwargs)
        check_trace_continued(sent, response)

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
        header_provider: Optional[HeaderProvider] = None,
    ):
        super().__init__(
            api_key=api_key, base_url=base_url, header_provider=header_provider
        )

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
        sent = self.traceparents_sent(kwargs["headers"])

        if stream:
            timeout = kwargs.pop("timeout", httpx.USE_CLIENT_DEFAULT)
            http_request = self._client.build_request(
                method, path, timeout=timeout, **kwargs
            )
            response = await self._client.send(http_request, stream=True)
            check_trace_continued(sent, response)
            if not response.is_success:
                try:
                    await response.aread()
                finally:
                    await response.aclose()
                _raise_for_status(response)
            return response

        # Make the request
        response = await self._client.request(method, path, **kwargs)
        check_trace_continued(sent, response)

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
