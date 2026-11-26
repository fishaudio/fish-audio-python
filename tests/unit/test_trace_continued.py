"""The warning when the API did not continue the trace the SDK sent.

The local servers answer like the Fish Audio gateway: a request with exactly
one valid ``traceparent`` continues its trace, anything else gets a new one,
and the trace ID used comes back in ``x-fish-trace-id``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import subprocess
import sys
import textwrap
import threading
import warnings
from typing import TYPE_CHECKING, Any, Callable

import httpx
import pytest
from httpx_ws import WebSocketUpgradeError
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

import fishaudio
from fishaudio import AsyncFishAudio, FishAudio, RequestOptions
from fishaudio.core import tracing
from fishaudio.exceptions import AuthenticationError, ServerError

from .realtime_server import SESSION_STARTED, RealtimeServer
from .test_asr_realtime import SESSION_DONE
from .test_header_provider import TRACE_A, recording_server, values

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .realtime_server import Connection

TRACE_A_ID = TRACE_A.split("-")[1]
OTHER_ID = "0af7651916cd43dd8448eb211c80319c"
SECRET_VALUE = "not-a-traceparent-s3cr3t"

_W3C = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}")


def gateway(headers: list[tuple[str, str]]) -> str:
    """The trace ID the gateway uses: the one sent, if exactly one valid
    traceparent arrived, else a new one."""
    sent = values(headers, "traceparent")
    if len(sent) == 1:
        match = _W3C.fullmatch(sent[0])
        if match and int(match.group(1), 16) and int(match.group(2), 16):
            return match.group(1)
    return secrets.token_hex(16)


def ws_gateway(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [("x-fish-trace-id", gateway(headers))]


def provide(value: str) -> Callable[[], dict[str, str]]:
    return lambda: {"traceparent": value}


@pytest.fixture(autouse=True)
def fresh_process_state(monkeypatch):
    """Each test starts as a process that has not warned yet."""
    monkeypatch.setattr(tracing, "_warned", False)


@contextlib.contextmanager
def recorded() -> Iterator[list[warnings.WarningMessage]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield caught


def trace_warnings(caught: list[warnings.WarningMessage]) -> list[str]:
    return [
        str(w.message)
        for w in caught
        if issubclass(w.category, fishaudio.TraceNotContinuedWarning)
    ]


class DuplicatingTransport(httpx.BaseTransport):
    """Adds a second traceparent after the SDK, like a custom transport, an
    event hook or a proxy could."""

    def __init__(self) -> None:
        self._inner = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.headers = httpx.Headers(
            [*request.headers.multi_items(), ("traceparent", TRACE_A)]
        )
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


# Every HTTP path type: plain, streamed, multipart, and each failing.
SYNC_CALLS: dict[str, Callable[[FishAudio], Any]] = {
    "json": lambda c: c.account.get_credits(),
    "list": lambda c: c.voices.list(),
    "multipart": lambda c: c.asr.transcribe(audio=b"\x00\x01"),
    "bytes": lambda c: c.tts.convert(text="hi"),
    "stream": lambda c: c.tts.stream(text="hi").collect(),
}


async def _astream(c: AsyncFishAudio) -> Any:
    return await (await c.tts.stream(text="hi")).collect()


ASYNC_CALLS: dict[str, Callable[[AsyncFishAudio], Any]] = {
    "json": lambda c: c.account.get_credits(),
    "list": lambda c: c.voices.list(),
    "multipart": lambda c: c.asr.transcribe(audio=b"\x00\x01"),
    "bytes": lambda c: c.tts.convert(text="hi"),
    "stream": _astream,
}


class TestHTTP:
    @pytest.mark.parametrize("status", [200, 401, 500])
    @pytest.mark.parametrize("call", list(SYNC_CALLS))
    def test_continued_trace_no_warning(self, call, status):
        with recording_server(status, gateway) as (url, seen), recorded() as caught:
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            with contextlib.suppress(AuthenticationError, ServerError):
                SYNC_CALLS[call](client)
            client.close()
        assert values(seen[0][1], "traceparent") == [TRACE_A]
        assert trace_warnings(caught) == []

    @pytest.mark.parametrize("status", [200, 401, 500])
    @pytest.mark.parametrize("call", list(SYNC_CALLS))
    def test_not_continued_warns_sync(self, call, status):
        with recording_server(status, gateway) as (url, seen), recorded() as caught:
            client = FishAudio(
                api_key="k",
                base_url=url,
                header_provider=provide(TRACE_A),
                httpx_client=httpx.Client(
                    base_url=url, transport=DuplicatingTransport()
                ),
            )
            with contextlib.suppress(AuthenticationError, ServerError):
                SYNC_CALLS[call](client)
            client.close()
        assert values(seen[0][1], "traceparent") == [TRACE_A, TRACE_A]
        (message,) = trace_warnings(caught)
        assert f"sent trace id {TRACE_A_ID}" in message
        assert re.search(r"the API used [0-9a-f]{32}\)", message)
        assert "The value the SDK sent is valid" in message
        assert "added a second traceparent or replaced it" in message
        assert "instrumentation" not in message
        assert "https://docs.fish.audio/api-reference/observability" in message
        # It names the caller's line, not the SDK's.
        (warning,) = [w for w in caught if "Fish Audio" in str(w.message)]
        assert warning.filename == __file__

    @pytest.mark.parametrize("status", [200, 401, 500])
    @pytest.mark.parametrize("call", list(ASYNC_CALLS))
    async def test_async(self, call, status):
        with recording_server(status, gateway) as (url, _), recorded() as caught:
            matching = AsyncFishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            with contextlib.suppress(AuthenticationError, ServerError):
                await ASYNC_CALLS[call](matching)
            await matching.close()
            assert trace_warnings(caught) == []

        # A traceparent on a custom httpx client counts as sent by the SDK.
        other_trace = f"00-{'1' * 32}-{'2' * 16}-01"
        with (
            recording_server(status, lambda _: OTHER_ID) as (url, _),
            recorded() as caught,
        ):
            other = AsyncFishAudio(
                api_key="k",
                base_url=url,
                header_provider=None,
                httpx_client=httpx.AsyncClient(
                    base_url=url, headers={"traceparent": other_trace}
                ),
            )
            with contextlib.suppress(AuthenticationError, ServerError):
                await ASYNC_CALLS[call](other)
            await other.close()
        (message,) = trace_warnings(caught)
        assert f"sent trace id {'1' * 32}" in message
        assert f"the API used {OTHER_ID}" in message

    def test_once_across_many_calls_and_threads(self):
        with recording_server(200, gateway) as (url, seen), recorded() as caught:
            client = FishAudio(
                api_key="k",
                base_url=url,
                header_provider=provide(TRACE_A),
                httpx_client=httpx.Client(
                    base_url=url, transport=DuplicatingTransport()
                ),
            )
            barrier = threading.Barrier(16)

            def call() -> None:
                barrier.wait()
                for _ in range(5):
                    client.account.get_credits()
                    client.tts.convert(text="hi")

            threads = [threading.Thread(target=call) for _ in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            client.close()
        assert len(seen) == 160
        assert len(trace_warnings(caught)) == 1

    async def test_once_across_many_tasks(self):
        with recording_server(200, lambda _: OTHER_ID) as (url, seen):
            client = AsyncFishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            with recorded() as caught:
                await asyncio.gather(
                    *(client.account.get_credits() for _ in range(32)),
                    *(_astream(client) for _ in range(8)),
                )
            await client.close()
        assert len(seen) == 40
        assert len(trace_warnings(caught)) == 1

    def test_per_call_header_is_checked(self):
        with (
            recording_server(200, lambda _: OTHER_ID) as (url, _),
            recorded() as caught,
        ):
            client = FishAudio(api_key="k", base_url=url, header_provider=None)
            client.account.get_credits(
                request_options=RequestOptions(
                    additional_headers={"traceparent": TRACE_A}
                )
            )
            client.close()
        assert len(trace_warnings(caught)) == 1

    def test_missing_response_header_no_warning(self):
        with recording_server(200, None) as (url, _), recorded() as caught:
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            client.account.get_credits()
            client.tts.stream(text="hi").collect()
            client.close()
        assert trace_warnings(caught) == []

    @pytest.mark.parametrize("received", ["", "abc", "not-a-trace-id-at-all", "x" * 32])
    def test_response_header_that_is_not_a_trace_id_is_ignored(self, received):
        with (
            recording_server(200, lambda _: received) as (url, _),
            recorded() as caught,
        ):
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            client.account.get_credits()
            client.close()
        assert trace_warnings(caught) == []

    def test_nothing_sent_no_check(self):
        with (
            recording_server(200, lambda _: OTHER_ID) as (url, _),
            recorded() as caught,
        ):
            client = FishAudio(api_key="k", base_url=url, header_provider=None)
            client.account.get_credits()
            client.close()
        assert trace_warnings(caught) == []
        assert tracing._warned is False

    def test_case_of_the_response_id_does_not_matter(self):
        with (
            recording_server(200, lambda _: TRACE_A_ID.upper()) as (url, _),
            recorded() as caught,
        ):
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            client.account.get_credits()
            client.close()
        assert trace_warnings(caught) == []

    @pytest.mark.parametrize(
        "sent",
        [
            SECRET_VALUE,
            TRACE_A.upper(),  # W3C requires lowercase
            f"00-{'0' * 32}-00f067aa0ba902b7-01",  # all-zero trace ID
            f"00-{TRACE_A_ID}-{'0' * 16}-01",  # all-zero parent ID
            f"ff-{TRACE_A_ID}-00f067aa0ba902b7-01",  # version ff
            f"{TRACE_A}-extra",  # version 00 has exactly four fields
        ],
    )
    def test_invalid_sent_value_warns_without_echoing_it(self, sent):
        with recording_server(200, gateway) as (url, _), recorded() as caught:
            client = FishAudio(api_key="k", base_url=url, header_provider=provide(sent))
            client.account.get_credits()
            client.close()
        (message,) = trace_warnings(caught)
        assert "the traceparent it sent is not one the API accepts" in message
        assert "lowercase version-00 W3C traceparent" in message
        assert sent not in message
        assert SECRET_VALUE not in message
        assert "sent trace id" not in message

    def test_future_version_with_more_fields_is_valid(self):
        sent = f"01-{TRACE_A_ID}-00f067aa0ba902b7-01-more"
        with (
            recording_server(200, lambda _: TRACE_A_ID) as (url, _),
            recorded() as caught,
        ):
            client = FishAudio(api_key="k", base_url=url, header_provider=provide(sent))
            client.account.get_credits()
            client.close()
        assert trace_warnings(caught) == []

    def test_future_version_not_continued_is_not_one_the_api_accepts(self):
        """The API continues version 00 only: a valid later version that gets
        a new trace is reported as a value the API does not accept."""
        sent = f"01-{TRACE_A_ID}-00f067aa0ba902b7-01-more"
        with recording_server(200, gateway) as (url, _), recorded() as caught:
            client = FishAudio(api_key="k", base_url=url, header_provider=provide(sent))
            client.account.get_credits()
            client.close()
        (message,) = trace_warnings(caught)
        assert "the traceparent it sent is not one the API accepts" in message
        assert TRACE_A_ID not in message.split("the API used")[0]

    def test_more_than_one_sent_is_counted(self):
        other = f"00-{'1' * 32}-{'2' * 16}-01"
        with recording_server(200, gateway) as (url, seen), recorded() as caught:
            client = FishAudio(
                api_key="k",
                base_url=url,
                header_provider=None,
                httpx_client=httpx.Client(
                    base_url=url,
                    headers=[("traceparent", TRACE_A), ("traceparent", other)],
                ),
            )
            client.account.get_credits()
            client.close()
        assert values(seen[0][1], "traceparent") == [TRACE_A, other]
        (message,) = trace_warnings(caught)
        assert "(2 traceparent headers;" in message
        assert "exactly one traceparent" in message


class TestWarningsAsErrors:
    @pytest.mark.parametrize("status", [200, 500])
    def test_simplefilter_error_does_not_fail_the_request(self, status, caplog):
        with recording_server(status, lambda _: OTHER_ID) as (url, _):
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            with warnings.catch_warnings(), caplog.at_level(logging.WARNING):
                warnings.simplefilter("error")
                if status == 200:
                    assert client.account.get_credits().credit is not None
                else:
                    # The API's own error, not the warning.
                    with pytest.raises(ServerError):
                        client.account.get_credits()
            client.close()
        # The message is not lost: it is logged instead.
        assert [
            r.levelno for r in caplog.records if "Fish Audio did not" in r.message
        ] == [logging.WARNING]

    async def test_simplefilter_error_async_and_websocket(self):
        server = RealtimeServer(
            lambda conn: None,
            reject_status=401,
            response_headers=lambda _: [("x-fish-trace-id", OTHER_ID)],
        )
        try:
            client = AsyncFishAudio(
                api_key="k", base_url=server.url, header_provider=provide(TRACE_A)
            )

            async def audio():
                yield b"\x00\x00"

            with warnings.catch_warnings():
                warnings.simplefilter("error")
                # The handshake's own failure, not the warning.
                with pytest.raises((WebSocketUpgradeError, AuthenticationError)):
                    async for _ in client.asr.stream_websocket(audio()):
                        pass
            await client.close()
        finally:
            server.close()
        assert tracing._warned is True

    def test_python_dash_w_error(self):
        with recording_server(200, lambda _: OTHER_ID) as (url, seen):
            script = textwrap.dedent(
                f"""
                from fishaudio import FishAudio
                client = FishAudio(
                    api_key="k",
                    base_url={url!r},
                    header_provider=lambda: {{"traceparent": {TRACE_A!r}}},
                )
                client.account.get_credits()
                client.account.get_credits()
                print("ok")
                """
            )
            result = subprocess.run(
                [sys.executable, "-W", "error", "-c", script],
                capture_output=True,
                text=True,
                timeout=60,
            )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"
        assert len(seen) == 2
        assert result.stderr.count("Fish Audio did not continue the trace") == 1

    def test_filterable_by_category(self):
        with recording_server(200, lambda _: OTHER_ID) as (url, _):
            client = FishAudio(
                api_key="k", base_url=url, header_provider=provide(TRACE_A)
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                warnings.filterwarnings(
                    "ignore", category=fishaudio.TraceNotContinuedWarning
                )
                client.account.get_credits()
            client.close()
        assert caught == []


# -- WebSocket handshakes ---------------------------------------------------


def tts_script(conn: Connection) -> None:
    while conn.recv().get("event") != "stop":
        pass
    conn.send({"event": "finish", "reason": "stop"})


def stt_script(conn: Connection) -> None:
    conn.recv()
    conn.send(SESSION_STARTED)
    conn.recv_until("audio_done")
    conn.send(SESSION_DONE)
    conn.close(1000, "done")


def sync_tts(client: FishAudio) -> None:
    list(client.tts.stream_websocket(iter(["hi"])))


def sync_stt(client: FishAudio) -> None:
    list(client.asr.stream_websocket(iter([b"\x00\x00"])))


async def async_tts(client: AsyncFishAudio) -> None:
    async def text():
        yield "hi"

    async for _ in client.tts.stream_websocket(text()):
        pass


async def async_stt(client: AsyncFishAudio) -> None:
    async def audio():
        yield b"\x00\x00"

    async for _ in client.asr.stream_websocket(audio()):
        pass


SCRIPTS = {"tts": tts_script, "stt": stt_script}
SYNC_WS = {"tts": sync_tts, "stt": sync_stt}
ASYNC_WS = {"tts": async_tts, "stt": async_stt}


def ws_server(
    kind: str, refused: bool, response_headers: Any = ws_gateway
) -> RealtimeServer:
    return RealtimeServer(
        (lambda conn: None) if refused else SCRIPTS[kind],
        reject_status=401 if refused else None,
        response_headers=response_headers,
    )


@pytest.mark.parametrize("refused", [False, True], ids=["accepted", "refused"])
@pytest.mark.parametrize("kind", ["tts", "stt"])
class TestWebSocket:
    def run_sync(self, kind, refused, header_provider, **server_options) -> Connection:
        server = ws_server(kind, refused, **server_options)
        try:
            client = FishAudio(
                api_key="k", base_url=server.url, header_provider=header_provider
            )
            if refused:
                with pytest.raises((WebSocketUpgradeError, AuthenticationError)):
                    SYNC_WS[kind](client)
            else:
                SYNC_WS[kind](client)
            client.close()
            return server.stop()
        finally:
            server.close()

    async def run_async(
        self, kind, refused, header_provider, **server_options
    ) -> Connection:
        server = ws_server(kind, refused, **server_options)
        try:
            client = AsyncFishAudio(
                api_key="k", base_url=server.url, header_provider=header_provider
            )
            if refused:
                with pytest.raises((WebSocketUpgradeError, AuthenticationError)):
                    await ASYNC_WS[kind](client)
            else:
                await ASYNC_WS[kind](client)
            await client.close()
            return await asyncio.get_running_loop().run_in_executor(None, server.stop)
        finally:
            server.close()

    def test_sync_continued(self, kind, refused):
        with recorded() as caught:
            conn = self.run_sync(kind, refused, provide(TRACE_A))
        assert values(conn.header_list, "traceparent") == [TRACE_A]
        assert trace_warnings(caught) == []

    def test_sync_not_continued(self, kind, refused):
        with recorded() as caught:
            self.run_sync(kind, refused, provide(SECRET_VALUE))
        (message,) = trace_warnings(caught)
        assert "not one the API accepts" in message
        assert SECRET_VALUE not in message

    def test_sync_no_response_header(self, kind, refused):
        with recorded() as caught:
            self.run_sync(kind, refused, provide(TRACE_A), response_headers=None)
        assert trace_warnings(caught) == []

    async def test_async_continued(self, kind, refused):
        with recorded() as caught:
            conn = await self.run_async(kind, refused, provide(TRACE_A))
        assert values(conn.header_list, "traceparent") == [TRACE_A]
        assert trace_warnings(caught) == []

    async def test_async_not_continued(self, kind, refused):
        with recorded() as caught:
            await self.run_async(
                kind,
                refused,
                provide(TRACE_A),
                response_headers=lambda _: [("x-fish-trace-id", OTHER_ID)],
            )
        (message,) = trace_warnings(caught)
        assert f"sent trace id {TRACE_A_ID}" in message
        assert f"the API used {OTHER_ID}" in message


# -- With opentelemetry-instrumentation-httpx -------------------------------


@pytest.fixture
def instrumented():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = HTTPXClientInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    yield provider
    instrumentor.uninstrument()
    provider.shutdown()


class TestHTTPXInstrumentation:
    """The instrumentation replaces the default provider's traceparent with
    its client span's, in the same trace: the API continues it, no warning."""

    def test_http_sync(self, instrumented):
        tracer = instrumented.get_tracer("t")
        with recording_server(200, gateway) as (url, seen), recorded() as caught:
            client = FishAudio(api_key="k", base_url=url)
            with tracer.start_as_current_span("outer") as outer:
                for call in SYNC_CALLS.values():
                    call(client)
            client.close()
        trace_id = f"{outer.get_span_context().trace_id:032x}"
        for _, headers in seen:
            (sent,) = values(headers, "traceparent")
            assert sent.split("-")[1] == trace_id
            # Replaced by the instrumentation's own span.
            assert sent.split("-")[2] != f"{outer.get_span_context().span_id:016x}"
        assert trace_warnings(caught) == []

    async def test_http_async(self, instrumented):
        tracer = instrumented.get_tracer("t")
        with recording_server(500, gateway) as (url, seen), recorded() as caught:
            client = AsyncFishAudio(api_key="k", base_url=url)
            with tracer.start_as_current_span("outer"):
                for call in ASYNC_CALLS.values():
                    with pytest.raises(ServerError):
                        await call(client)
            await client.close()
        assert len(seen) == len(ASYNC_CALLS)
        assert trace_warnings(caught) == []

    @pytest.mark.parametrize("kind", ["tts", "stt"])
    def test_handshakes_sync(self, instrumented, kind):
        tracer = instrumented.get_tracer("t")
        server = ws_server(kind, refused=False)
        try:
            with recorded() as caught:
                client = FishAudio(api_key="k", base_url=server.url)
                with tracer.start_as_current_span("outer") as outer:
                    SYNC_WS[kind](client)
                client.close()
            conn = server.stop()
        finally:
            server.close()
        (sent,) = values(conn.header_list, "traceparent")
        assert sent.split("-")[1] == f"{outer.get_span_context().trace_id:032x}"
        assert trace_warnings(caught) == []

    @pytest.mark.parametrize("kind", ["tts", "stt"])
    async def test_handshakes_async(self, instrumented, kind):
        tracer = instrumented.get_tracer("t")
        server = ws_server(kind, refused=False)
        try:
            with recorded() as caught:
                client = AsyncFishAudio(api_key="k", base_url=server.url)
                with tracer.start_as_current_span("outer"):
                    await ASYNC_WS[kind](client)
                await client.close()
            conn = await asyncio.get_running_loop().run_in_executor(None, server.stop)
        finally:
            server.close()
        assert len(values(conn.header_list, "traceparent")) == 1
        assert trace_warnings(caught) == []


def test_exported():
    assert issubclass(fishaudio.TraceNotContinuedWarning, UserWarning)
    assert "TraceNotContinuedWarning" in fishaudio.__all__


def test_flag_is_not_a_one_per_location_filter():
    """Two different call sites still give one warning per process."""
    sent = [TRACE_A]
    response = httpx.Response(200, headers={"x-fish-trace-id": OTHER_ID})
    with recorded() as caught:
        tracing.check_trace_continued(sent, response)
        tracing.check_trace_continued(sent, response)
    assert len(trace_warnings(caught)) == 1


def test_never_raises_on_odd_inputs():
    tracing.check_trace_continued([TRACE_A], object())
    tracing.check_trace_continued([TRACE_A], None)
    assert tracing.sent_traceparents(object()) == []
    assert tracing._warned is False


def test_traceparent_trace_id():
    assert tracing.traceparent_trace_id(f" {TRACE_A}\t") == TRACE_A_ID
    assert tracing.traceparent_trace_id(TRACE_A.upper()) is None
