"""The default header provider: the current OpenTelemetry span as traceparent."""

from __future__ import annotations

import contextlib
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

import pytest
from httpx_ws import WebSocketUpgradeError
from opentelemetry import baggage, propagate, trace
from opentelemetry import context as otel_context
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.utils import (
    suppress_http_instrumentation,
    suppress_instrumentation,
)
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.trace import TraceState
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.util.http import get_excluded_urls

from fishaudio import AsyncFishAudio, FishAudio, RequestOptions, opentelemetry_headers
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
    monkeypatch.setitem(sys.modules, "opentelemetry", None)  # import fails
    monkeypatch.setattr(tracing, "_otel", None)
    yield
    tracing._otel = None


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
        def broken(carrier):
            raise RuntimeError("broken propagator")

        monkeypatch.setattr(tracing._opentelemetry(), "inject", broken)
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


# -- The OpenTelemetry controls that keep trace context off a request -------


@pytest.fixture
def fresh_otel(monkeypatch):
    """The default provider looks OpenTelemetry up again on first use."""
    monkeypatch.setattr(tracing, "_otel", None)
    yield
    tracing._otel = None


@pytest.fixture
def without_instrumentation_utils(monkeypatch, fresh_otel):
    """Behave as if opentelemetry-instrumentation were not installed."""
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.utils", None)


@pytest.fixture
def without_util_http(monkeypatch, fresh_otel):
    """Behave as if opentelemetry-util-http were not installed."""
    monkeypatch.setitem(sys.modules, "opentelemetry.util.http", None)


@pytest.fixture
def no_excluded_urls(monkeypatch):
    monkeypatch.delenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", raising=False)
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS", raising=False)


def sent_by_default(tracer_provider, block=contextlib.nullcontext) -> list[list[str]]:
    """The traceparent values the default provider puts on an HTTP request and
    on both WebSocket handshakes, with ``block()`` around the calls."""
    sent = []
    with recording_server() as (url, seen):
        client = FishAudio(api_key="test-key", base_url=url)
        with tracer_provider.get_tracer("t").start_as_current_span("s"), block():
            client.account.get_credits()
            client.tts.convert(text="hi")
        client.close()
        sent += [values(headers, "traceparent") for _, headers in seen]
    for open_stream in (
        lambda c: list(c.tts.stream_websocket(iter(["hi"]))),
        lambda c: list(c.asr.stream_websocket(iter([b"\x00\x00"]))),
    ):
        server = RealtimeServer(lambda conn: None, reject_status=401)
        try:
            client = FishAudio(api_key="test-key", base_url=server.url)
            with (
                tracer_provider.get_tracer("t").start_as_current_span("s"),
                block(),
                pytest.raises((WebSocketUpgradeError, AuthenticationError)),
            ):
                open_stream(client)
            client.close()
            sent.append(values(server.stop().header_list, "traceparent"))
        finally:
            server.close()
    return sent


async def sent_by_default_async(tracer_provider, block) -> list[list[str]]:
    """As ``sent_by_default``, with ``AsyncFishAudio``."""

    async def text():
        yield "hi"

    async def audio():
        yield b"\x00\x00"

    sent = []
    with recording_server() as (url, seen):
        client = AsyncFishAudio(api_key="test-key", base_url=url)
        with tracer_provider.get_tracer("t").start_as_current_span("s"), block():
            await client.account.get_credits()
            await client.tts.convert(text="hi")
        await client.close()
        sent += [values(headers, "traceparent") for _, headers in seen]

    async def tts(c):
        async for _ in c.tts.stream_websocket(text()):
            pass

    async def stt(c):
        async for _ in c.asr.stream_websocket(audio()):
            pass

    for open_stream in (tts, stt):
        server = RealtimeServer(lambda conn: None, reject_status=401)
        try:
            client = AsyncFishAudio(api_key="test-key", base_url=server.url)
            with (
                tracer_provider.get_tracer("t").start_as_current_span("s"),
                block(),
                pytest.raises((WebSocketUpgradeError, AuthenticationError)),
            ):
                await open_stream(client)
            await client.close()
            sent.append(values(server.stop().header_list, "traceparent"))
        finally:
            server.close()
    return sent


def _set_context_value(key):
    """A block that sets an OpenTelemetry context value to True, as the
    suppress_* context managers do."""

    @contextlib.contextmanager
    def block():
        token = otel_context.attach(otel_context.set_value(key, True))
        try:
            yield
        finally:
            otel_context.detach(token)

    return block


@pytest.mark.usefixtures("no_excluded_urls")
class TestSuppression:
    """``suppress_instrumentation()`` and ``suppress_http_instrumentation()``
    keep the default provider's traceparent off every request, as they keep
    the httpx instrumentation's off."""

    def test_control(self, tracer_provider):
        sent = sent_by_default(tracer_provider)
        assert [len(s) for s in sent] == [1, 1, 1, 1]

    @pytest.mark.parametrize(
        "block", [suppress_instrumentation, suppress_http_instrumentation]
    )
    def test_sync(self, tracer_provider, block):
        assert sent_by_default(tracer_provider, block) == [[], [], [], []]

    @pytest.mark.parametrize(
        "block", [suppress_instrumentation, suppress_http_instrumentation]
    )
    async def test_async(self, tracer_provider, block):
        assert await sent_by_default_async(tracer_provider, block) == [[], [], [], []]

    @pytest.mark.parametrize(
        "key",
        [
            otel_context._SUPPRESS_INSTRUMENTATION_KEY,
            otel_context._SUPPRESS_HTTP_INSTRUMENTATION_KEY,
            "suppress_instrumentation",
        ],
    )
    def test_without_opentelemetry_instrumentation_installed(
        self, tracer_provider, without_instrumentation_utils, key
    ):
        """The same context keys are read from the API itself."""
        assert sent_by_default(tracer_provider) != [[], [], [], []]
        assert tracing._opentelemetry().is_http_instrumentation_enabled is None
        assert sent_by_default(tracer_provider, _set_context_value(key)) == [
            [],
            [],
            [],
            [],
        ]

    def test_also_with_the_httpx_instrumentation(self, instrumented):
        """With the instrumentation on, neither adds a traceparent."""
        assert sent_by_default(instrumented, suppress_http_instrumentation) == [
            [],
            [],
            [],
            [],
        ]

    def test_is_how_to_send_no_traceparent_on_one_call(self, tracer_provider):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                client.account.get_credits()
                with suppress_http_instrumentation():
                    client.account.get_credits()
                client.account.get_credits()
            client.close()
        assert [len(values(h, "traceparent")) for _, h in seen] == [1, 0, 1]


class TestExcludedURLs:
    """``OTEL_PYTHON_HTTPX_EXCLUDED_URLS`` (else ``OTEL_PYTHON_EXCLUDED_URLS``):
    regular expressions searched in the request's full URL."""

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_httpx_variable(self, tracer_provider, monkeypatch):
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"/v1/tts")
        # account (/wallet/...): sent; tts.convert, the TTS handshake: not;
        # the realtime STT handshake (/v1/asr/realtime): sent.
        sent = sent_by_default(tracer_provider)
        assert [len(s) for s in sent] == [1, 0, 0, 1]

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_generic_variable_when_the_httpx_one_is_unset(
        self, tracer_provider, monkeypatch
    ):
        monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", r"127\.0\.0\.1:\d+/v1/asr/")
        assert [len(s) for s in sent_by_default(tracer_provider)] == [1, 1, 1, 0]
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", "nothing-matches")
        assert [len(s) for s in sent_by_default(tracer_provider)] == [1, 1, 1, 1]

    @pytest.mark.usefixtures("no_excluded_urls")
    async def test_async(self, tracer_provider, monkeypatch):
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"/v1/tts, /wallet/")
        sent = await sent_by_default_async(tracer_provider, contextlib.nullcontext)
        assert [len(s) for s in sent] == [0, 0, 0, 1]

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_matches_the_url_with_its_query(self, tracer_provider, monkeypatch):
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"\?q=skip")
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                for q in ("skip", "keep"):
                    client.account.get_credits(
                        request_options=RequestOptions(additional_query_params={"q": q})
                    )
            client.close()
        assert [len(values(h, "traceparent")) for _, h in seen] == [0, 1]

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_also_inside_your_own_provider(self, tracer_provider, monkeypatch):
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"/v1/tts")
        with recording_server() as (url, seen):
            client = FishAudio(
                api_key="test-key",
                base_url=url,
                header_provider=lambda: {
                    **(opentelemetry_headers() or {}),
                    "x-request-id": "r1",
                },
            )
            with tracer_provider.get_tracer("t").start_as_current_span("s"):
                client.account.get_credits()
                client.tts.convert(text="hi")
            client.close()
        assert [len(values(h, "traceparent")) for _, h in seen] == [1, 0]
        assert [values(h, "x-request-id") for _, h in seen] == [["r1"], ["r1"]]

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_called_outside_the_sdk_it_knows_no_url(self, tracer_provider, monkeypatch):
        monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", ".*")
        with tracer_provider.get_tracer("t").start_as_current_span("s"):
            assert opentelemetry_headers() is not None

    @pytest.mark.usefixtures("no_excluded_urls")
    def test_without_opentelemetry_util_http_installed(
        self, tracer_provider, monkeypatch, without_util_http
    ):
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"/v1/tts")
        assert [len(s) for s in sent_by_default(tracer_provider)] == [1, 0, 0, 1]
        assert tracing._opentelemetry().get_excluded_urls is tracing._get_excluded_urls

    @pytest.mark.parametrize(
        "httpx_value, generic_value",
        [
            (None, None),
            ("", "x"),
            (None, "a, b ,c"),
            ("v1/tts,wallet", "x"),
            (r"^https://api\.fish\.audio/v1/tts$", None),
            ("tts,", None),
        ],
    )
    def test_fallback_reads_the_variables_as_opentelemetry_util_http_does(
        self, monkeypatch, httpx_value, generic_value
    ):
        for name, value in (
            ("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", httpx_value),
            ("OTEL_PYTHON_EXCLUDED_URLS", generic_value),
        ):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        theirs = get_excluded_urls("HTTPX")
        ours = tracing._get_excluded_urls("HTTPX")
        for url in (
            "https://api.fish.audio/v1/tts",
            "https://api.fish.audio/wallet/self/api-credit",
            "http://x/a",
            "http://x/b?c=1",
            "",
        ):
            assert ours.url_disabled(url) == theirs.url_disabled(url), url

    def test_also_with_the_httpx_instrumentation(self, tracer_provider, monkeypatch):
        """Set before the instrumentation is turned on (it reads the variable
        then): neither adds a traceparent to an excluded URL."""
        monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS", raising=False)
        monkeypatch.setenv("OTEL_PYTHON_HTTPX_EXCLUDED_URLS", r"/v1/tts")
        instrumentor = HTTPXClientInstrumentor()
        instrumentor.instrument(tracer_provider=tracer_provider)
        try:
            sent = sent_by_default(tracer_provider)
        finally:
            instrumentor.uninstrument()
        assert [len(s) for s in sent] == [1, 0, 0, 1]


class TestPropagators:
    """The configured propagators decide whether a traceparent is written."""

    @pytest.fixture
    def textmap(self):
        previous = propagate.get_global_textmap()
        yield propagate.set_global_textmap
        propagate.set_global_textmap(previous)

    def test_none_configured_sends_nothing(self, tracer_provider, textmap):
        textmap(CompositePropagator([]))  # OTEL_PROPAGATORS=none
        with tracer_provider.get_tracer("t").start_as_current_span("s"):
            assert opentelemetry_headers() is None

    def test_baggage_alone_sends_nothing(self, tracer_provider, textmap):
        textmap(W3CBaggagePropagator())
        with tracer_provider.get_tracer("t").start_as_current_span("s"):
            assert opentelemetry_headers() is None

    def test_tracecontext_sends_only_traceparent(self, tracer_provider, textmap):
        textmap(
            CompositePropagator(
                [TraceContextTextMapPropagator(), W3CBaggagePropagator()]
            )
        )
        state = TraceState([("vendor", "v")])
        with tracer_provider.get_tracer("t").start_as_current_span("s") as span:
            parent = span.get_span_context()
            ctx = trace.set_span_in_context(
                trace.NonRecordingSpan(
                    trace.SpanContext(
                        parent.trace_id,
                        parent.span_id,
                        is_remote=False,
                        trace_flags=parent.trace_flags,
                        trace_state=state,
                    )
                ),
                baggage.set_baggage("user", "secret"),
            )
            token = otel_context.attach(ctx)
            try:
                headers = opentelemetry_headers()
            finally:
                otel_context.detach(token)
        assert headers == {"traceparent": traceparent_of(span)}
