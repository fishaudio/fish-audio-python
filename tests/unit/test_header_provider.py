"""The header provider and per-call headers, against real local servers.

Each test records the raw headers a request arrived with, repeated names
included, so a header sent twice is caught.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Callable, Optional

import httpx
import pytest
from httpx_ws import WebSocketUpgradeError

from fishaudio import AsyncFishAudio, FishAudio, RequestOptions
from fishaudio.core.client_wrapper import USER_AGENT
from fishaudio.exceptions import AuthenticationError, ServerError

from .realtime_server import RealtimeServer

if TYPE_CHECKING:
    from collections.abc import Iterator

VOICE = {
    "_id": "v",
    "type": "tts",
    "title": "v",
    "description": "",
    "cover_image": "",
    "train_mode": "fast",
    "state": "trained",
    "tags": [],
    "samples": [],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "languages": [],
    "visibility": "private",
    "lock_visibility": False,
    "like_count": 0,
    "mark_count": 0,
    "shared_count": 0,
    "task_count": 0,
    "liked": False,
    "marked": False,
    "author": {"_id": "a", "nickname": "a", "avatar": ""},
}

TRACE_A = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
TRACE_B = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

current_trace: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_trace", default=None
)


def from_contextvar() -> Optional[dict[str, Optional[str]]]:
    return {"traceparent": current_trace.get()}


class _Recorder(BaseHTTPRequestHandler):
    """Records each request's headers and answers ``status``.

    ``trace_id``, if set, names the ``x-fish-trace-id`` to answer with, from
    the request's headers (None: no such header).
    """

    seen: list[tuple[str, list[tuple[str, str]]]]
    status = 200
    trace_id: Optional[Callable[[list[tuple[str, str]]], Optional[str]]] = None

    def _answer(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).seen.append((self.path, list(self.headers.items())))
        if self.status != 200:
            body, content_type = b'{"message": "nope"}', "application/json"
        elif self.path.startswith("/v1/tts"):
            body, content_type = b"\x01\x02", "audio/mpeg"
        elif self.path.startswith("/v1/asr"):
            body = b'{"text": "", "duration": 0, "segments": []}'
            content_type = "application/json"
        elif self.path.startswith("/model") and self.command == "GET":
            body, content_type = b'{"items": [], "total": 0}', "application/json"
        elif self.path.startswith("/model"):
            body, content_type = json.dumps(VOICE).encode(), "application/json"
        else:
            body = (
                b'{"_id": "c", "user_id": "u", "credit": "1",'
                b' "created_at": "2026-01-01", "updated_at": "2026-01-01"}'
            )
            content_type = "application/json"
        self.send_response(self.status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        trace_id = type(self).trace_id
        if trace_id is not None:
            value = trace_id(list(self.headers.items()))
            if value is not None:
                self.send_header("x-fish-trace-id", value)
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PATCH = do_DELETE = _answer

    def log_message(self, *args: Any) -> None:
        pass


@contextlib.contextmanager
def recording_server(
    status: int = 200,
    trace_id: Optional[Callable[[list[tuple[str, str]]], Optional[str]]] = None,
) -> Iterator[tuple[str, list]]:
    handler = type(
        "Handler",
        (_Recorder,),
        {"seen": [], "status": status, "trace_id": staticmethod(trace_id)},
    )
    # The default listen backlog (5) refuses bursts of concurrent connections.
    server_class = type("Server", (ThreadingHTTPServer,), {"request_queue_size": 128})
    server = server_class(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler.seen
    finally:
        server.shutdown()
        server.server_close()


def values(headers: list[tuple[str, str]], name: str) -> list[str]:
    return [v for k, v in headers if k.lower() == name.lower()]


@contextlib.contextmanager
def refusing_ws_server() -> Iterator[RealtimeServer]:
    """Records the handshake, then refuses it with 401."""
    server = RealtimeServer(lambda conn: None, reject_status=401)
    try:
        yield server
    finally:
        server.close()


class Counter:
    """A provider that counts its calls and returns the contextvar's trace."""

    def __init__(self) -> None:
        self.calls = 0
        self.threads: list[int] = []

    def __call__(self) -> dict[str, Optional[str]]:
        self.calls += 1
        self.threads.append(threading.get_ident())
        return {"traceparent": current_trace.get()}


class TestHTTP:
    def test_every_endpoint_type_gets_it_once_per_request(self):
        provider = Counter()
        token = current_trace.set(TRACE_A)
        try:
            with recording_server() as (url, seen):
                client = FishAudio(
                    api_key="test-key", base_url=url, header_provider=provider
                )
                client.account.get_credits()
                client.voices.list()
                client.voices.create(title="v", voices=[b"\x00"])
                client.tts.convert(text="hi")
                client.tts.stream(text="hi").collect()
                client.asr.transcribe(audio=b"\x00\x01")
                client.close()
        finally:
            current_trace.reset(token)
        assert provider.calls == len(seen) == 6
        for path, headers in seen:
            assert values(headers, "traceparent") == [TRACE_A], path
            assert values(headers, "authorization") == ["Bearer test-key"], path

    def test_called_at_send_time_with_the_callers_context(self):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=from_contextvar
            )
            for trace in (TRACE_A, TRACE_B):
                token = current_trace.set(trace)
                try:
                    client.account.get_credits()
                finally:
                    current_trace.reset(token)
            client.account.get_credits()  # no trace in context: no header
            client.close()
        assert [values(h, "traceparent") for _, h in seen] == [
            [TRACE_A],
            [TRACE_B],
            [],
        ]

    def test_called_once_for_a_failing_request(self):
        provider = Counter()
        with recording_server(status=500) as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=provider
            )
            with pytest.raises(ServerError):
                client.account.get_credits()
            client.close()
        assert provider.calls == 1
        assert len(seen) == 1

    def test_concurrent_threads_each_send_their_own_value(self):
        provider = Counter()
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=provider
            )
            barrier = threading.Barrier(16)

            def call(i: int) -> None:
                current_trace.set(f"00-{i:032x}-00f067aa0ba902b7-01")
                barrier.wait()
                client.account.get_credits(
                    request_options=RequestOptions(
                        additional_headers={"x-call": str(i)}
                    )
                )

            threads = [threading.Thread(target=call, args=(i,)) for i in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            client.close()
        assert len(seen) == 16
        for _, headers in seen:
            (call_id,) = values(headers, "x-call")
            assert values(headers, "traceparent") == [
                f"00-{int(call_id):032x}-00f067aa0ba902b7-01"
            ]
        # Called on the calling threads only.
        assert len(set(provider.threads)) == 16

    async def test_async_tasks_each_send_their_own_value(self):
        with recording_server() as (url, seen):
            client = AsyncFishAudio(
                api_key="test-key", base_url=url, header_provider=from_contextvar
            )

            async def call(i: int) -> None:
                current_trace.set(f"00-{i:032x}-00f067aa0ba902b7-01")
                await asyncio.sleep(0)  # let the other tasks interleave
                await client.account.get_credits(
                    request_options=RequestOptions(
                        additional_headers={"x-call": str(i)}
                    )
                )

            await asyncio.gather(*(call(i) for i in range(32)))
            await client.close()
        assert len(seen) == 32
        for _, headers in seen:
            (call_id,) = values(headers, "x-call")
            assert values(headers, "traceparent") == [
                f"00-{int(call_id):032x}-00f067aa0ba902b7-01"
            ]

    async def test_async_every_endpoint_type(self):
        token = current_trace.set(TRACE_B)
        try:
            with recording_server() as (url, seen):
                client = AsyncFishAudio(
                    api_key="test-key", base_url=url, header_provider=from_contextvar
                )
                await client.account.get_credits()
                await client.voices.list()
                await client.tts.convert(text="hi")
                await client.asr.transcribe(audio=b"\x00\x01")
                await client.close()
        finally:
            current_trace.reset(token)
        assert len(seen) == 4
        for path, headers in seen:
            assert values(headers, "traceparent") == [TRACE_B], path

    def test_per_call_header_wins_over_the_provider(self):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {"traceparent": TRACE_A, "baggage": "k=v"},
            )
            client.tts.convert(
                text="hi",
                request_options=RequestOptions(
                    additional_headers={"TraceParent": TRACE_B}
                ),
            )
            client.close()
        headers = seen[0][1]
        assert values(headers, "traceparent") == [TRACE_B]
        assert values(headers, "baggage") == ["k=v"]

    def test_headers_on_a_custom_httpx_client_win_over_the_provider(self):
        with recording_server() as (url, seen):
            own = httpx.Client(base_url=url, headers={"x-request-id": "static"})
            client = FishAudio(
                api_key="test-key",
                httpx_client=own,
                header_provider=lambda: {
                    "X-Request-Id": "dynamic",
                    "traceparent": TRACE_A,
                },
            )
            client.account.get_credits()
            own.close()
        headers = seen[0][1]
        assert values(headers, "x-request-id") == ["static"]
        assert values(headers, "traceparent") == [TRACE_A]

    def test_cannot_replace_sdk_headers(self):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {
                    "authorization": "Bearer stolen",
                    "Authorization": "Bearer stolen",
                    "model": "s1",
                    "User-Agent": "evil/1",
                    "Content-Type": "text/plain",
                    "Content-Length": "1",
                    "Host": "example.com",
                    "Connection": "close",
                    "Sec-WebSocket-Key": "x",
                    "traceparent": TRACE_A,
                },
            )
            client.tts.convert(text="hi", model="s2-pro")
            client.close()
        headers = seen[0][1]
        assert values(headers, "authorization") == ["Bearer test-key"]
        assert values(headers, "model") == ["s2-pro"]
        assert values(headers, "user-agent") == [USER_AGENT]
        assert values(headers, "content-type") == ["application/msgpack"]
        assert values(headers, "host") != ["example.com"]
        assert values(headers, "sec-websocket-key") == []
        assert values(headers, "traceparent") == [TRACE_A]

    @pytest.mark.parametrize("result", [None, {}, {"traceparent": None}])
    def test_returning_nothing_adds_nothing(self, result):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=lambda: result
            )
            client.account.get_credits()
            client.close()
        assert values(seen[0][1], "traceparent") == []

    def test_an_exception_reaches_the_caller_unchanged_and_nothing_is_sent(self):
        error = RuntimeError("tracer is down")

        def provider():
            raise error

        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=provider
            )
            with pytest.raises(RuntimeError) as info:
                client.tts.convert(text="hi")
            client.close()
        assert info.value is error
        assert seen == []

    @pytest.mark.parametrize(
        "result, error",
        [
            (["traceparent", TRACE_A], TypeError),
            ({"traceparent": 1}, TypeError),
            ({1: "x"}, TypeError),
            ({"traceparent": b"00-..."}, TypeError),
            ({"traceparent": "a\r\nInjected: yes"}, ValueError),
            ({"bad name": "x"}, ValueError),
        ],
    )
    def test_invalid_results_fail_before_sending(self, result, error):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key", base_url=url, header_provider=lambda: result
            )
            with pytest.raises(error) as info:
                client.account.get_credits()
            client.close()
        assert seen == []
        assert "Injected" not in str(info.value)  # the value is never echoed

    def test_must_be_callable(self):
        with pytest.raises(TypeError):
            FishAudio(api_key="test-key", header_provider={"traceparent": TRACE_A})  # type: ignore[arg-type]

    def test_without_a_provider_nothing_changes(self):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            client.account.get_credits()
            client.close()
        assert values(seen[0][1], "traceparent") == []
        assert values(seen[0][1], "authorization") == ["Bearer test-key"]


class TestWebSockets:
    """Both handshakes, sync and async. The server refuses them after recording."""

    def test_tts_handshake_sync(self):
        provider = Counter()
        with refusing_ws_server() as server:
            client = FishAudio(
                api_key="test-key", base_url=server.url, header_provider=provider
            )
            stream = client.tts.stream_websocket(
                iter(["hi"]),
                model="s2-pro",
                request_options=RequestOptions(additional_headers={"x-call": "1"}),
            )
            assert provider.calls == 0  # nothing happens before iteration
            token = current_trace.set(TRACE_A)
            try:
                with pytest.raises(WebSocketUpgradeError):
                    list(stream)
            finally:
                current_trace.reset(token)
            client.close()
            conn = server.stop()
        assert provider.calls == 1
        assert conn.path == "/v1/tts/live"
        assert values(conn.header_list, "traceparent") == [TRACE_A]
        assert values(conn.header_list, "x-call") == ["1"]
        assert values(conn.header_list, "model") == ["s2-pro"]
        assert values(conn.header_list, "authorization") == ["Bearer test-key"]

    async def test_tts_handshake_async(self):
        with refusing_ws_server() as server:
            client = AsyncFishAudio(
                api_key="test-key", base_url=server.url, header_provider=from_contextvar
            )

            async def text():
                yield "hi"

            current_trace.set(TRACE_B)
            with pytest.raises(WebSocketUpgradeError):
                async for _ in client.tts.stream_websocket(
                    text(),
                    request_options=RequestOptions(
                        additional_headers={"traceparent": TRACE_A}
                    ),
                ):
                    pass
            await client.close()
            conn = server.stop()
        # The per-call header wins over the provider.
        assert values(conn.header_list, "traceparent") == [TRACE_A]

    def test_asr_realtime_handshake_sync_reads_context_when_iterated(self):
        with refusing_ws_server() as server:
            client = FishAudio(
                api_key="test-key", base_url=server.url, header_provider=from_contextvar
            )
            token = current_trace.set(TRACE_A)
            stream = client.asr.stream_websocket(
                iter([b"\x00\x00"]),
                request_options=RequestOptions(
                    additional_headers={"x-call": "2"},
                    additional_query_params={"q": "1"},
                ),
            )
            current_trace.reset(token)
            token = current_trace.set(TRACE_B)
            try:
                with pytest.raises(AuthenticationError):
                    list(stream)
            finally:
                current_trace.reset(token)
            client.close()
            conn = server.stop()
        assert conn.path == "/v1/asr/realtime?q=1"
        assert values(conn.header_list, "traceparent") == [TRACE_B]
        assert values(conn.header_list, "x-call") == ["2"]
        assert values(conn.header_list, "model") == ["transcribe-stream-1"]
        assert values(conn.header_list, "user-agent") == [USER_AGENT]

    async def test_asr_realtime_handshake_async_reads_the_iterating_task(self):
        with refusing_ws_server() as server:
            client = AsyncFishAudio(
                api_key="test-key",
                base_url=server.url,
                header_provider=lambda: {
                    "traceparent": current_trace.get(),
                    "Authorization": "Bearer stolen",
                    "Sec-WebSocket-Version": "8",
                },
            )

            async def audio():
                yield b"\x00\x00"

            stream = client.asr.stream_websocket(audio())

            async def consume() -> None:
                current_trace.set(TRACE_A)
                async for _ in stream:
                    pass

            with pytest.raises(AuthenticationError):
                await asyncio.create_task(consume())
            await client.close()
            conn = server.stop()
        assert values(conn.header_list, "traceparent") == [TRACE_A]
        assert values(conn.header_list, "authorization") == ["Bearer test-key"]

    def test_provider_error_on_a_handshake_reaches_the_caller_sync(self):
        error = LookupError("no span")

        def provider():
            raise error

        with refusing_ws_server() as server:
            client = FishAudio(
                api_key="test-key", base_url=server.url, header_provider=provider
            )
            with pytest.raises(LookupError) as tts_info:
                list(client.tts.stream_websocket(iter(["hi"])))
            with pytest.raises(LookupError) as asr_info:
                list(client.asr.stream_websocket(iter([b"\x00\x00"])))
            client.close()
        assert tts_info.value is error and asr_info.value is error
        assert server.connection is None  # nothing was sent

    async def test_provider_error_on_a_handshake_reaches_the_caller_async(self):
        error = LookupError("no span")

        def provider():
            raise error

        async def text():
            yield "hi"

        async def audio():
            yield b"\x00\x00"

        with refusing_ws_server() as server:
            client = AsyncFishAudio(
                api_key="test-key", base_url=server.url, header_provider=provider
            )
            with pytest.raises(LookupError) as tts_info:
                async for _ in client.tts.stream_websocket(text()):
                    pass
            with pytest.raises(LookupError) as asr_info:
                async for _ in client.asr.stream_websocket(audio()):
                    pass
            await client.close()
        assert tts_info.value is error and asr_info.value is error
        assert server.connection is None

    async def test_concurrent_async_sessions_each_send_their_own_value(self):
        servers = [
            RealtimeServer(lambda conn: None, reject_status=401) for _ in range(8)
        ]
        try:

            async def session(i: int) -> None:
                current_trace.set(f"00-{i:032x}-00f067aa0ba902b7-01")
                client = AsyncFishAudio(
                    api_key="test-key",
                    base_url=servers[i].url,
                    header_provider=from_contextvar,
                )

                async def audio():
                    yield b"\x00\x00"

                with pytest.raises(AuthenticationError):
                    async for _ in client.asr.stream_websocket(audio()):
                        pass
                await client.close()

            await asyncio.gather(*(session(i) for i in range(8)))
            for i, server in enumerate(servers):
                conn = server.stop()
                assert values(conn.header_list, "traceparent") == [
                    f"00-{i:032x}-00f067aa0ba902b7-01"
                ]
        finally:
            for server in servers:
                server.close()
