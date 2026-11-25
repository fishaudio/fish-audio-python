"""The default header provider: the current OpenTelemetry span as traceparent."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

import pytest
from httpx_ws import WebSocketUpgradeError
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

from fishaudio import AsyncFishAudio, FishAudio, opentelemetry_headers
from fishaudio.core import tracing
from fishaudio.exceptions import AuthenticationError

from .realtime_server import RealtimeServer
from .test_header_provider import recording_server, values

if TYPE_CHECKING:
    from opentelemetry.trace import Span


def traceparent_of(span: Span) -> str:
    context = span.get_span_context()
    return (
        f"00-{context.trace_id:032x}-{context.span_id:016x}"
        f"-{int(context.trace_flags):02x}"
    )


@pytest.fixture
def tracer_provider():
    """A local tracer provider: the global one is never set by these tests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.exporter = exporter  # type: ignore[attr-defined]
    yield provider
    provider.shutdown()


@pytest.fixture
def no_opentelemetry(monkeypatch):
    """Behave as if the opentelemetry-api package were not installed."""
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)  # import fails
    monkeypatch.setattr(tracing, "_get_current_span", None)
    yield
    tracing._get_current_span = None


def get_credits_headers(client: FishAudio, seen: list) -> list[tuple[str, str]]:
    client.account.get_credits()
    return seen[-1][1]


class TestDefault:
    def test_is_the_default_of_both_clients(self):
        assert (
            FishAudio(api_key="k")._client_wrapper.header_provider
            is opentelemetry_headers
        )
        assert (
            AsyncFishAudio(api_key="k")._client_wrapper.header_provider
            is opentelemetry_headers
        )

    def test_sends_the_current_span(self, tracer_provider):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with tracer_provider.get_tracer("t").start_as_current_span("s") as span:
                headers = get_credits_headers(client, seen)
            client.close()
        assert values(headers, "traceparent") == [traceparent_of(span)]
        assert values(headers, "tracestate") == []
        assert values(headers, "baggage") == []

    def test_unsampled_span_keeps_its_flags(self):
        provider = TracerProvider(sampler=ALWAYS_OFF)
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with provider.get_tracer("t").start_as_current_span("s") as span:
                headers = get_credits_headers(client, seen)
            client.close()
        assert not span.get_span_context().trace_flags.sampled
        assert values(headers, "traceparent") == [traceparent_of(span)]

    def test_no_span_or_an_invalid_one_sends_nothing(self):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            outside = get_credits_headers(client, seen)
            with trace.use_span(trace.INVALID_SPAN):
                invalid = get_credits_headers(client, seen)
            client.close()
        assert values(outside, "traceparent") == []
        assert values(invalid, "traceparent") == []

    def test_api_installed_without_an_sdk_sends_nothing(self):
        # A fresh interpreter, so no test's tracer provider can be in place.
        with recording_server() as (url, seen):
            script = textwrap.dedent(
                f"""
                from opentelemetry import trace
                from fishaudio import FishAudio, opentelemetry_headers
                with trace.get_tracer("t").start_as_current_span("s"):
                    assert opentelemetry_headers() is None
                    FishAudio(api_key="k", base_url={url!r}).account.get_credits()
                """
            )
            subprocess.run([sys.executable, "-c", script], check=True, timeout=60)
        assert len(seen) == 1
        assert values(seen[0][1], "traceparent") == []

    def test_api_absent_sends_nothing(self, no_opentelemetry, tracer_provider):
        assert opentelemetry_headers() is None
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                headers = get_credits_headers(client, seen)
            client.close()
        assert values(headers, "traceparent") == []

    def test_an_opentelemetry_error_never_fails_the_request(self, monkeypatch):
        def broken():
            raise RuntimeError("broken tracer")

        monkeypatch.setattr(tracing, "_get_current_span", broken)
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            headers = get_credits_headers(client, seen)
            client.close()
        assert values(headers, "traceparent") == []

    def test_none_turns_it_off(self, tracer_provider):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url, header_provider=None)
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                headers = get_credits_headers(client, seen)
            client.close()
        assert values(headers, "traceparent") == []

    def test_your_own_provider_replaces_it(self, tracer_provider):
        own = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {"x-request-id": "r1"},
            )
            client_own_trace = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {"traceparent": own},
            )
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                replaced = get_credits_headers(client, seen)
                own_trace = get_credits_headers(client_own_trace, seen)
            client.close()
            client_own_trace.close()
        assert values(replaced, "traceparent") == []
        assert values(replaced, "x-request-id") == ["r1"]
        assert values(own_trace, "traceparent") == [own]

    def test_combined_with_your_own_headers(self, tracer_provider):
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {
                    **(opentelemetry_headers() or {}),
                    "x-request-id": "r1",
                },
            )
            with tracer_provider.get_tracer("t").start_as_current_span("s") as span:
                headers = get_credits_headers(client, seen)
            client.close()
        assert values(headers, "traceparent") == [traceparent_of(span)]
        assert values(headers, "x-request-id") == ["r1"]


@pytest.fixture
def instrumented(tracer_provider):
    """opentelemetry-instrumentation-httpx, on for one test."""
    instrumentor = HTTPXClientInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    yield tracer_provider
    instrumentor.uninstrument()


class TestWithHttpxInstrumentation:
    """The instrumentation replaces the default's header with its client span's:
    one header, and that span is a child of the caller's span in the same trace."""

    @staticmethod
    def assert_one_correct_trace(headers, outer: Span, exporter) -> None:
        (sent,) = values(headers, "traceparent")
        _, trace_id, span_id, _ = sent.split("-")
        outer_context = outer.get_span_context()
        assert trace_id == f"{outer_context.trace_id:032x}"
        assert span_id != f"{outer_context.span_id:016x}"  # not the caller's span
        client_spans = {
            f"{s.context.span_id:016x}": s for s in exporter.get_finished_spans()
        }
        assert span_id in client_spans  # the instrumentation's span ...
        parent = client_spans[span_id].parent
        assert (
            parent is not None and parent.span_id == outer_context.span_id
        )  # ... a child

    def test_http_sync(self, instrumented):
        tracer = instrumented.get_tracer("t")
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with tracer.start_as_current_span("outer") as outer:
                client.tts.convert(text="hi")
            client.close()
            self.assert_one_correct_trace(seen[0][1], outer, instrumented.exporter)

    async def test_http_async(self, instrumented):
        tracer = instrumented.get_tracer("t")
        with recording_server() as (url, seen):
            client = AsyncFishAudio(api_key="test-key", base_url=url)
            with tracer.start_as_current_span("outer") as outer:
                await client.asr.transcribe(audio=b"\x00")
            await client.close()
            self.assert_one_correct_trace(seen[0][1], outer, instrumented.exporter)

    def test_tts_and_realtime_stt_handshakes_sync(self, instrumented):
        tracer = instrumented.get_tracer("t")
        for open_stream in (
            lambda c: list(c.tts.stream_websocket(iter(["hi"]))),
            lambda c: list(c.asr.stream_websocket(iter([b"\x00\x00"]))),
        ):
            server = RealtimeServer(lambda conn: None, reject_status=401)
            try:
                client = FishAudio(api_key="test-key", base_url=server.url)
                with (
                    tracer.start_as_current_span("outer") as outer,
                    pytest.raises((WebSocketUpgradeError, AuthenticationError)),
                ):
                    open_stream(client)
                client.close()
                conn = server.stop()
            finally:
                server.close()
            self.assert_one_correct_trace(
                conn.header_list, outer, instrumented.exporter
            )

    async def test_tts_and_realtime_stt_handshakes_async(self, instrumented):
        tracer = instrumented.get_tracer("t")

        async def text():
            yield "hi"

        async def audio():
            yield b"\x00\x00"

        async def tts(client):
            async for _ in client.tts.stream_websocket(text()):
                pass

        async def stt(client):
            async for _ in client.asr.stream_websocket(audio()):
                pass

        for open_stream in (tts, stt):
            server = RealtimeServer(lambda conn: None, reject_status=401)
            try:
                client = AsyncFishAudio(api_key="test-key", base_url=server.url)
                with (
                    tracer.start_as_current_span("outer") as outer,
                    pytest.raises((WebSocketUpgradeError, AuthenticationError)),
                ):
                    await open_stream(client)
                await client.close()
                conn = server.stop()
            finally:
                server.close()
            self.assert_one_correct_trace(
                conn.header_list, outer, instrumented.exporter
            )
