"""What the README's Tracing section promises, checked through the real transport.

With opentelemetry-instrumentation-httpx enabled, every HTTP call and WebSocket
handshake carries the active trace. Without it, a custom httpx client with a
request event hook reaches the same requests.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider

from fishaudio import AsyncFishAudio, FishAudio

from .realtime_server import WS_PATHS, consume, open_stream, ws_server

ASR_RESPONSE = {"text": "Hello", "duration": 1.0, "segments": []}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["content-length"]))
        self.server.requests.append(self.headers.items())
        body = json.dumps(ASR_RESPONSE).encode() if self.path == "/v1/asr" else b"ID3"
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    """A local HTTP server that records each request's header lines."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def call_http(client, name):
    """Make one HTTP call: tts.convert or asr.transcribe, sync or async."""
    if name.endswith("tts.convert"):
        call = client.tts.convert(text="Hello")
    else:
        call = client.asr.transcribe(audio=b"\x00")
    if name.startswith("async"):

        async def run():
            await call
            await client.close()

        asyncio.run(run())
    else:
        client.close()


HTTP_CALLS = [
    "tts.convert",
    "asr.transcribe",
    "async tts.convert",
    "async asr.transcribe",
]


def sdk_client(url, is_async):
    if is_async:
        return AsyncFishAudio(api_key="test-key", base_url=url)
    return FishAudio(api_key="test-key", base_url=url)


def values(header_list, name):
    return [value for key, value in header_list if key.lower() == name]


def trace_id(traceparent):
    return int(traceparent.split("-")[1], 16)


@pytest.fixture
def tracer():
    provider = TracerProvider()
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    yield provider.get_tracer("app")
    HTTPXClientInstrumentor().uninstrument()


@pytest.mark.parametrize("name", HTTP_CALLS)
def test_instrumented_http_call_carries_the_active_trace(tracer, http_server, name):
    client = sdk_client(http_server.url, name.startswith("async"))
    with tracer.start_as_current_span("request") as span:
        call_http(client, name)

    [traceparent] = values(http_server.requests[0], "traceparent")
    assert trace_id(traceparent) == span.get_span_context().trace_id


@pytest.mark.parametrize("path", WS_PATHS)
def test_instrumented_handshake_carries_the_active_trace(tracer, path):
    with ws_server(path) as (server, client), tracer.start_as_current_span("x") as span:
        consume(open_stream(client, path))

    [traceparent] = values(server.stop().header_list, "traceparent")
    assert trace_id(traceparent) == span.get_span_context().trace_id


@pytest.mark.parametrize("path", WS_PATHS)
def test_stream_iterated_after_the_span_ends_is_not_in_its_trace(tracer, path):
    with ws_server(path) as (server, client):
        with tracer.start_as_current_span("request") as span:
            stream = open_stream(client, path)
        consume(stream)

    # The connection opens on the first iteration, so the instrumentation
    # starts a new trace there.
    [traceparent] = values(server.stop().header_list, "traceparent")
    assert trace_id(traceparent) != span.get_span_context().trace_id


def _hooked_client(url, is_async):
    """The README's alternative: a client whose request hook adds a header."""
    if is_async:

        async def ahook(request):
            request.headers["traceparent"] = "from-hook"

        http = httpx.AsyncClient(base_url=url, event_hooks={"request": [ahook]})
        return AsyncFishAudio(api_key="test-key", httpx_client=http)

    def hook(request):
        request.headers["traceparent"] = "from-hook"

    http = httpx.Client(base_url=url, event_hooks={"request": [hook]})
    return FishAudio(api_key="test-key", httpx_client=http)


@pytest.mark.parametrize("name", HTTP_CALLS)
def test_request_hook_reaches_http_calls(http_server, name):
    call_http(_hooked_client(http_server.url, name.startswith("async")), name)

    assert values(http_server.requests[0], "traceparent") == ["from-hook"]


@pytest.mark.parametrize("path", WS_PATHS)
def test_request_hook_reaches_handshakes(path):
    with ws_server(path, _hooked_client) as (server, client):
        consume(open_stream(client, path))

    assert values(server.stop().header_list, "traceparent") == ["from-hook"]
