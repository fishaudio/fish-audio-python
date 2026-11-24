"""Tests that TTS streaming delivers chunks incrementally over real httpx transports.

These use httpx.MockTransport instead of mocking ClientWrapper.request, so they
exercise the actual request/response path and would catch the SDK buffering the
whole response body before yielding.
"""

import httpx
import pytest

from fishaudio.core import AsyncClientWrapper, ClientWrapper
from fishaudio.exceptions import APIError, RateLimitError
from fishaudio.resources.tts import AsyncTTSClient, TTSClient

BASE_URL = "https://api.test.fish.audio"
CHUNKS = [b"chunk-1", b"chunk-2", b"chunk-3"]


class _SyncBody(httpx.SyncByteStream):
    """Response body that records how far the server has been read."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.produced = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.produced += 1
            yield chunk

    def close(self):
        self.closed = True


class _AsyncBody(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.produced = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.produced += 1
            yield chunk

    async def aclose(self):
        self.closed = True


def _sync_tts(handler):
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return TTSClient(ClientWrapper(api_key="test", httpx_client=http))


def _async_tts(handler):
    http = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return AsyncTTSClient(AsyncClientWrapper(api_key="test", httpx_client=http))


class TestSyncStreaming:
    def test_first_chunk_arrives_before_body_is_read(self):
        body = _SyncBody(CHUNKS)
        tts = _sync_tts(lambda request: httpx.Response(200, stream=body))

        stream = iter(tts.stream(text="Hello"))
        assert body.produced == 0  # nothing read until the caller iterates

        assert next(stream) == b"chunk-1"
        assert body.produced == 1  # the rest of the body is still unread

        assert list(stream) == [b"chunk-2", b"chunk-3"]
        assert body.closed

    def test_with_block_closes_after_early_break(self):
        body = _SyncBody(CHUNKS)
        tts = _sync_tts(lambda request: httpx.Response(200, stream=body))

        with tts.stream(text="Hello") as stream:
            for _ in stream:
                break
            assert not body.closed

        assert body.produced == 1
        assert body.closed

    def test_close_before_iteration_releases_response(self):
        body = _SyncBody(CHUNKS)
        tts = _sync_tts(lambda request: httpx.Response(200, stream=body))

        stream = tts.stream(text="Hello")
        stream.close()
        stream.close()  # idempotent

        assert body.produced == 0
        assert body.closed
        assert list(stream) == []

    def test_collect_closes_response(self):
        body = _SyncBody(CHUNKS)
        tts = _sync_tts(lambda request: httpx.Response(200, stream=body))

        assert tts.stream(text="Hello").collect() == b"".join(CHUNKS)
        assert body.closed

    def test_convert_still_returns_full_audio(self):
        tts = _sync_tts(lambda request: httpx.Response(200, stream=_SyncBody(CHUNKS)))
        assert tts.convert(text="Hello") == b"".join(CHUNKS)

    def test_error_raises_with_server_message(self):
        tts = _sync_tts(
            lambda request: httpx.Response(429, json={"message": "Too many requests"})
        )
        with pytest.raises(RateLimitError) as exc:
            tts.stream(text="Hello")
        assert exc.value.status == 429
        assert "Too many requests" in str(exc.value)

    def test_error_raised_at_call_time_not_on_iteration(self):
        tts = _sync_tts(lambda request: httpx.Response(402, text="Insufficient credit"))
        with pytest.raises(APIError) as exc:
            tts.stream(text="Hello")
        assert exc.value.status == 402

    def test_request_options_timeout_applies(self):
        seen = {}

        def handler(request):
            seen["timeout"] = request.extensions["timeout"]
            return httpx.Response(200, stream=_SyncBody(CHUNKS))

        from fishaudio.core import RequestOptions

        tts = _sync_tts(handler)
        tts.stream(text="Hello", request_options=RequestOptions(timeout=12.5)).collect()
        assert seen["timeout"]["read"] == 12.5


class TestAsyncStreaming:
    async def test_first_chunk_arrives_before_body_is_read(self):
        body = _AsyncBody(CHUNKS)
        tts = _async_tts(lambda request: httpx.Response(200, stream=body))

        stream = (await tts.stream(text="Hello")).__aiter__()
        assert body.produced == 0

        assert await stream.__anext__() == b"chunk-1"
        assert body.produced == 1

        rest = [chunk async for chunk in stream]
        assert rest == [b"chunk-2", b"chunk-3"]
        assert body.closed

    async def test_async_with_closes_after_early_break(self):
        body = _AsyncBody(CHUNKS)
        tts = _async_tts(lambda request: httpx.Response(200, stream=body))

        async with await tts.stream(text="Hello") as stream:
            async for _ in stream:
                break
            assert not body.closed

        assert body.produced == 1
        assert body.closed

    async def test_aclose_before_iteration_releases_response(self):
        body = _AsyncBody(CHUNKS)
        tts = _async_tts(lambda request: httpx.Response(200, stream=body))

        stream = await tts.stream(text="Hello")
        await stream.aclose()
        await stream.aclose()  # idempotent

        assert body.produced == 0
        assert body.closed
        assert [chunk async for chunk in stream] == []

    async def test_collect_closes_response(self):
        body = _AsyncBody(CHUNKS)
        tts = _async_tts(lambda request: httpx.Response(200, stream=body))

        assert await (await tts.stream(text="Hello")).collect() == b"".join(CHUNKS)
        assert body.closed

    async def test_convert_still_returns_full_audio(self):
        tts = _async_tts(lambda request: httpx.Response(200, stream=_AsyncBody(CHUNKS)))
        assert await tts.convert(text="Hello") == b"".join(CHUNKS)

    async def test_error_raises_with_server_message(self):
        tts = _async_tts(
            lambda request: httpx.Response(429, json={"message": "Too many requests"})
        )
        with pytest.raises(RateLimitError) as exc:
            await tts.stream(text="Hello")
        assert exc.value.status == 429
        assert "Too many requests" in str(exc.value)
