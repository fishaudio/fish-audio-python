"""An APIError carries the headers of the error response.

The tests run the real client against a local HTTP server, and a refused
WebSocket handshake against the scripted server in realtime_server.py.
"""

import contextlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from httpx_ws import WebSocketUpgradeError

from fishaudio import APIError, AsyncFishAudio, AuthenticationError, FishAudio
from fishaudio.core.client_wrapper import _raise_for_status
from fishaudio.exceptions import (
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
)

from .realtime_server import RealtimeServer


class _Refuse(BaseHTTPRequestHandler):
    """401 with the API's diagnostic headers on /v1, a bare 404 elsewhere."""

    def _respond(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path.startswith("/v1/"):
            body = b'{"status":401,"message":"Invalid Token"}'
            self.send_response(401)
            self.send_header("x-fish-trace-id", "trace-123")
            self.send_header("x-fish-error-code", "invalid_api_key")
        else:
            body = b'{"status":404,"message":"Not found"}'
            self.send_response(404)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _respond

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def refusing_server():
    server = HTTPServer(("127.0.0.1", 0), _Refuse)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_error_carries_the_response_headers():
    with (
        refusing_server() as url,
        FishAudio(api_key="k", base_url=url) as client,
        pytest.raises(AuthenticationError) as exc_info,
    ):
        client.tts.convert(text="hi")
    error = exc_info.value
    assert error.status == 401
    assert error.message == "Invalid Token"
    assert error.headers["x-fish-trace-id"] == "trace-123"
    assert error.headers["X-Fish-Error-Code"] == "invalid_api_key"  # any casing


async def test_http_error_carries_the_response_headers_async():
    with refusing_server() as url:
        async with AsyncFishAudio(api_key="k", base_url=url) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client.tts.convert(text="hi")
    assert exc_info.value.headers["x-fish-trace-id"] == "trace-123"


def test_headers_the_response_does_not_have_are_absent():
    with (
        refusing_server() as url,
        FishAudio(api_key="k", base_url=url) as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.account.get_credits()
    assert exc_info.value.status == 404
    assert exc_info.value.headers.get("x-fish-trace-id") is None


def test_error_built_without_headers_has_empty_headers():
    error = APIError(400, "Bad Request")
    assert error.headers.get("x-fish-trace-id") is None
    assert len(error.headers) == 0


def test_refused_tts_websocket_exposes_the_headers_on_the_upgrade_error():
    """The README's second path: tts.stream_websocket is not wrapped."""
    server = RealtimeServer(lambda conn: None, reject_status=401)
    try:
        with (
            FishAudio(api_key="k", base_url=server.url) as client,
            pytest.raises(WebSocketUpgradeError) as exc_info,
        ):
            list(client.tts.stream_websocket(iter(["hi"])))
    finally:
        server.close()
    assert exc_info.value.response.status_code == 401
    assert exc_info.value.response.headers["x-fish-trace-id"] == "trace-123"


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, PermissionError),
        (404, NotFoundError),
        (429, RateLimitError),
        (503, ServerError),
    ],
)
def test_every_error_class_carries_the_headers(status, error_class):
    response = httpx.Response(
        status,
        headers={"x-fish-trace-id": "trace-123"},
        json={"message": "refused"},
        request=httpx.Request("GET", "https://api.fish.audio/v1/tts"),
    )

    with pytest.raises(APIError) as caught:
        _raise_for_status(response)

    assert type(caught.value) is error_class
    assert caught.value.headers["x-fish-trace-id"] == "trace-123"
