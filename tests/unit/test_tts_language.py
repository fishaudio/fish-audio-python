"""Tests for the text-to-speech `language` option on every entry point.

HTTP requests go through real httpx transports and WebSocket sessions through a
local server (see realtime_server.py), so the assertions read the bytes the SDK
actually sends. An unset language must not appear on the wire at all, not even
as nil.
"""

import contextlib

import httpx
import ormsgpack
import pytest

from fishaudio import AsyncFishAudio, FishAudio, TTSConfig
from fishaudio.core import AsyncClientWrapper, ClientWrapper
from fishaudio.exceptions import WebSocketError
from fishaudio.resources.tts import AsyncTTSClient, TTSClient
from fishaudio.types import StartEvent, TTSRequest

from .realtime_server import RealtimeServer

BASE_URL = "https://api.test.fish.audio"

SSE_BODY = (
    b'event: message\ndata: {"audio_base64": "", "content": "", "alignment": null}\n\n'
)

# (call kwargs, expected "language" in the body; None means absent)
CASES = [
    pytest.param({}, None, id="unset"),
    pytest.param({"config": TTSConfig()}, None, id="default-config"),
    pytest.param({"language": "es-MX"}, "es-MX", id="parameter"),
    pytest.param({"config": TTSConfig(language="zh-CN")}, "zh-CN", id="config"),
    pytest.param(
        {"language": "es-MX", "config": TTSConfig(language="en")},
        "es-MX",
        id="parameter-overrides-config",
    ),
    pytest.param({"language": "ES_mx"}, "ES_mx", id="sent-as-given"),
    pytest.param({"language": ""}, "", id="empty-string-sent-as-given"),
]


def _check(body, expected):
    if expected is None:
        assert "language" not in body
    else:
        assert body["language"] == expected


def _capture(seen, response_body):
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=response_body)

    return handler


def _sync_tts(seen, response_body=b"audio"):
    transport = httpx.MockTransport(_capture(seen, response_body))
    http = httpx.Client(base_url=BASE_URL, transport=transport)
    return TTSClient(ClientWrapper(api_key="test", httpx_client=http))


def _async_tts(seen, response_body=b"audio"):
    transport = httpx.MockTransport(_capture(seen, response_body))
    http = httpx.AsyncClient(base_url=BASE_URL, transport=transport)
    return AsyncTTSClient(AsyncClientWrapper(api_key="test", httpx_client=http))


class TestTypes:
    def test_config_defaults_to_unset(self):
        assert TTSConfig().language is None

    def test_request_omits_unset_language_in_every_dump(self):
        request = TTSRequest(text="hi")
        assert "language" not in request.model_dump()
        assert "language" not in request.model_dump(exclude_none=True)
        assert "language" not in StartEvent(request=request).model_dump()["request"]

    def test_request_keeps_a_set_language(self):
        request = TTSRequest(text="hi", language="es-MX")
        assert request.model_dump()["language"] == "es-MX"
        assert StartEvent(request=request).model_dump()["request"]["language"] == (
            "es-MX"
        )

    def test_other_none_fields_are_unchanged(self):
        # Only language is dropped when unset; the start event keeps sending the
        # other optional fields as nil, as it did before.
        dumped = StartEvent(request=TTSRequest(text="")).model_dump()["request"]
        assert dumped["reference_id"] is None
        assert dumped["sample_rate"] is None
        assert dumped["prosody"] is None


class TestHTTP:
    @pytest.mark.parametrize("kwargs, expected", CASES)
    def test_convert(self, kwargs, expected):
        seen = []
        _sync_tts(seen).convert(text="La entrada cuesta $300.", **kwargs)
        assert seen[0].url.path == "/v1/tts"
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    def test_stream(self, kwargs, expected):
        seen = []
        _sync_tts(seen).stream(text="Hi", **kwargs).collect()
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    def test_convert_with_timestamps(self, kwargs, expected):
        seen = []
        _sync_tts(seen, SSE_BODY).convert_with_timestamps(text="Hi", **kwargs)
        assert seen[0].url.path == "/v1/tts/stream/with-timestamp"
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    def test_stream_with_timestamps(self, kwargs, expected):
        seen = []
        _sync_tts(seen, SSE_BODY).stream_with_timestamps(text="Hi", **kwargs).close()
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    async def test_async_convert(self, kwargs, expected):
        seen = []
        await _async_tts(seen).convert(text="Hi", **kwargs)
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    async def test_async_stream(self, kwargs, expected):
        seen = []
        stream = await _async_tts(seen).stream(text="Hi", **kwargs)
        await stream.collect()
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    async def test_async_convert_with_timestamps(self, kwargs, expected):
        seen = []
        await _async_tts(seen, SSE_BODY).convert_with_timestamps(text="Hi", **kwargs)
        _check(ormsgpack.unpackb(seen[0].content), expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    async def test_async_stream_with_timestamps(self, kwargs, expected):
        seen = []
        stream = await _async_tts(seen, SSE_BODY).stream_with_timestamps(
            text="Hi", **kwargs
        )
        await stream.aclose()
        _check(ormsgpack.unpackb(seen[0].content), expected)


def tts_script(conn):
    """Read the start event and the text, then answer with audio and finish."""
    while conn.recv().get("event") != "stop":
        pass
    conn.send({"event": "audio", "audio": b"audio"})
    conn.send({"event": "finish", "reason": "stop"})


def rejecting_script(conn):
    """What the API does with an invalid start event: an error event, then silence."""
    conn.recv()
    conn.send({"event": "error", "error": 'Invalid language "en us".'})


@contextlib.contextmanager
def serving(script):
    server = RealtimeServer(script)
    client = FishAudio(api_key="test-key", base_url=server.url)
    try:
        yield server, client
    finally:
        client.close()
        server.close()


@contextlib.asynccontextmanager
async def aserving(script):
    server = RealtimeServer(script)
    client = AsyncFishAudio(api_key="test-key", base_url=server.url)
    try:
        yield server, client
    finally:
        await client.close()
        server.close()


async def _aiter(*items):
    for item in items:
        yield item


class TestWebSocket:
    @pytest.mark.parametrize("kwargs, expected", CASES)
    def test_start_event(self, kwargs, expected):
        with serving(tts_script) as (server, client):
            audio = b"".join(client.tts.stream_websocket(iter(["Hola"]), **kwargs))
            conn = server.stop()
        assert audio == b"audio"
        assert conn.path == "/v1/tts/live"
        start = conn.received[0]
        assert start["event"] == "start"
        _check(start["request"], expected)

    @pytest.mark.parametrize("kwargs, expected", CASES)
    async def test_async_start_event(self, kwargs, expected):
        async with aserving(tts_script) as (server, client):
            chunks = [
                chunk
                async for chunk in client.tts.stream_websocket(_aiter("Hola"), **kwargs)
            ]
            conn = server.stop()
        assert b"".join(chunks) == b"audio"
        _check(conn.received[0]["request"], expected)

    def test_rejected_start_event_raises_instead_of_hanging(self):
        with serving(rejecting_script) as (server, client):
            with pytest.raises(WebSocketError, match='Invalid language "en us"'):
                list(client.tts.stream_websocket(iter(["Hola"]), language="en us"))
            server.stop()

    async def test_async_rejected_start_event_raises_instead_of_hanging(self):
        async with aserving(rejecting_script) as (server, client):
            with pytest.raises(WebSocketError, match='Invalid language "en us"'):
                async for _ in client.tts.stream_websocket(
                    _aiter("Hola"), language="en us"
                ):
                    pass
            server.stop()
