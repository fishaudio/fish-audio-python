"""Header provider values: what the SDK accepts is what the transport sends.

The rule is RFC 9110 section 5.5, ASCII only: a value is empty, or visible
ASCII characters (0x21-0x7E) with spaces and tabs only between them.

- Every value the SDK accepts reaches the server unchanged.
- Every value it rejects raises the SDK's own ``ValueError`` before anything
  is sent, naming the header and the kind of problem, never the value: no
  ``UnicodeEncodeError`` or ``httpx.LocalProtocolError`` reaches the caller.
- Names the provider may not set, and names already set, are ignored before
  their value is looked at.

Checked against real local servers, on HTTP and on both WebSocket
handshakes, sync and async.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pytest
from httpx_ws import WebSocketUpgradeError

from fishaudio import AsyncFishAudio, FishAudio, RequestOptions
from fishaudio.exceptions import AuthenticationError

from .test_header_provider import (
    TRACE_A,
    TRACE_B,
    recording_server,
    refusing_ws_server,
    values,
)

Provider = Callable[[], dict[str, str]]
Headers = list[tuple[str, str]]


class NothingSent(Exception):
    """The call raised before any request reached the server."""

    def __init__(self, error: BaseException):
        super().__init__(repr(error))
        self.error = error


# Each sender makes one call with ``provider`` and returns the headers the
# server received, or raises NothingSent with the call's exception.


def http_sync(provider: Provider, options: Optional[RequestOptions] = None) -> Headers:
    with recording_server() as (url, seen):
        client = FishAudio(api_key="test-key", base_url=url, header_provider=provider)
        try:
            client.tts.convert(text="hi", request_options=options)
        except Exception as error:
            assert seen == []
            raise NothingSent(error) from error
        finally:
            client.close()
    (request,) = seen
    return request[1]


async def http_async(
    provider: Provider, options: Optional[RequestOptions] = None
) -> Headers:
    with recording_server() as (url, seen):
        client = AsyncFishAudio(
            api_key="test-key", base_url=url, header_provider=provider
        )
        try:
            await client.account.get_credits(request_options=options)
        except Exception as error:
            assert seen == []
            raise NothingSent(error) from error
        finally:
            await client.close()
    (request,) = seen
    return request[1]


def _ws_result(server: Any, error: BaseException) -> Headers:
    """The handshake headers, if the server saw the handshake (it refuses
    every one after recording it), else NothingSent."""
    if isinstance(error, (WebSocketUpgradeError, AuthenticationError)):
        conn = server.stop()
        return conn.header_list
    server.close()
    assert server.connection is None
    raise NothingSent(error) from error


def ws_sync(kind: str) -> Callable[..., Headers]:
    def send(provider: Provider, options: Optional[RequestOptions] = None) -> Headers:
        with refusing_ws_server() as server:
            client = FishAudio(
                api_key="test-key", base_url=server.url, header_provider=provider
            )
            try:
                if kind == "tts":
                    list(
                        client.tts.stream_websocket(
                            iter(["hi"]), request_options=options
                        )
                    )
                else:
                    list(
                        client.asr.stream_websocket(
                            iter([b"\x00\x00"]), request_options=options
                        )
                    )
            except Exception as error:
                return _ws_result(server, error)
            finally:
                client.close()
        raise AssertionError("the server refuses every handshake")

    return send


def ws_async(kind: str) -> Callable[..., Any]:
    async def send(
        provider: Provider, options: Optional[RequestOptions] = None
    ) -> Headers:
        async def text():
            yield "hi"

        async def audio():
            yield b"\x00\x00"

        with refusing_ws_server() as server:
            client = AsyncFishAudio(
                api_key="test-key", base_url=server.url, header_provider=provider
            )
            try:
                if kind == "tts":
                    async for _ in client.tts.stream_websocket(
                        text(), request_options=options
                    ):
                        pass
                else:
                    async for _ in client.asr.stream_websocket(
                        audio(), request_options=options
                    ):
                        pass
            except Exception as error:
                return _ws_result(server, error)
            finally:
                await client.close()
        raise AssertionError("the server refuses every handshake")

    return send


SENDERS: dict[str, Callable[..., Any]] = {
    "http-sync": http_sync,
    "http-async": http_async,
    "ws-tts-sync": ws_sync("tts"),
    "ws-tts-async": ws_async("tts"),
    "ws-asr-sync": ws_sync("asr"),
    "ws-asr-async": ws_async("asr"),
}


async def send(transport: str, provider: Provider, **kwargs: Any) -> Headers:
    result = SENDERS[transport](provider, **kwargs)
    if transport.endswith("-async"):
        result = await result
    return result


def assert_sdk_error(
    error: BaseException, name: str, value: str, kind: str, *, strict: bool = True
) -> None:
    """The SDK's own ValueError, naming the header and the kind of problem.

    ``strict``: the message has no character of the value other than those of
    the name. A space is allowed: the message is prose, and a value with a
    space at one end is one of the rejected kinds. For values made of common
    letters (``café``), ``strict=False`` checks that the value is not echoed
    and that none of its characters outside visible ASCII is in the message.
    """
    assert type(error) is ValueError, repr(error)  # not UnicodeEncodeError
    message = str(error)
    assert repr(name) in message
    assert kind in message
    if strict:
        leaked = set(value) - set(name) - {" "}
    else:
        assert repr(value) not in message
        leaked = {c for c in value if not "!" <= c <= "~"} - {" "}
    assert not [c for c in leaked if c in message], (repr(value), message)


SENT = "sent"
IGNORED = "ignored"

# The gateway owner's table, plus the neighbouring cases.
TABLE = [
    ("x-name", "café", "a non-ASCII character"),
    ("x-name", " a", "leading or trailing whitespace"),
    ("x-name", "a ", "leading or trailing whitespace"),
    ("x-name", "\ta", "leading or trailing whitespace"),
    ("x-name", " ", "leading or trailing whitespace"),
    ("x-name", "a\x7fb", "a control character"),
    ("x-name", "a\x01b", "a control character"),
    ("x-name", "a\x00b", "a control character"),
    ("x-name", "a\r\nb", "a line break"),
    ("x-name", "a\nInjected: yes", "a line break"),
    ("Authorization", "a\r\nb", IGNORED),
    ("Authorization", "café", IGNORED),
    ("x-name", "a \t  b", SENT),
    ("x-name", "", SENT),
    ("x-name", "!~", SENT),
]


@pytest.mark.parametrize("transport", list(SENDERS))
@pytest.mark.parametrize("name, value, expected", TABLE)
async def test_reviewer_table(transport, name, value, expected):
    provider = lambda: {name: value, "traceparent": TRACE_A}  # noqa: E731
    if expected in (SENT, IGNORED):
        headers = await send(transport, provider)
        assert values(headers, "traceparent") == [TRACE_A]
        if expected == SENT:
            assert values(headers, name) == [value]
        else:
            assert values(headers, name) == ["Bearer test-key"]
        return
    with pytest.raises(NothingSent) as info:
        await send(transport, provider)
    assert_sdk_error(info.value.error, name, value, expected, strict=False)
    assert "Injected" not in str(info.value.error)


@pytest.mark.parametrize("transport", list(SENDERS))
async def test_names_already_set_are_ignored_whatever_their_value(transport):
    """A reserved name, or one a per-call header sets, with an illegal value:
    no error, and the provider's value is not sent."""
    provider = lambda: {  # noqa: E731
        "Authorization": "x\r\nInjected: yes",
        "model": "\x00",
        "User-Agent": "café",
        "Sec-WebSocket-Key": " x ",
        "traceparent": "bad\nvalue",
    }
    headers = await send(
        transport,
        provider,
        options=RequestOptions(additional_headers={"TraceParent": TRACE_B}),
    )
    assert values(headers, "traceparent") == [TRACE_B]
    assert values(headers, "authorization") == ["Bearer test-key"]
    assert values(headers, "injected") == []


# Guarantee A, byte by byte: the SDK is never laxer than the transport.

PROBE_NAME = "x-probe"
POSITIONS = {
    "start": lambda c: f"{c}QZ",
    "middle": lambda c: f"Q{c}Z",
    "end": lambda c: f"QZ{c}",
}
PROBES = [
    (b, position, build(chr(b)))
    for b in range(256)
    for position, build in POSITIONS.items()
]


def rule_accepts(b: int, position: str) -> bool:
    """The rule, stated independently of the SDK's code."""
    if 0x21 <= b <= 0x7E:
        return True
    return b in (0x20, 0x09) and position == "middle"


def _check_probes(results: list[tuple[int, str, str, Any]]) -> None:
    for b, position, value, outcome in results:
        if isinstance(outcome, NothingSent):
            assert not rule_accepts(b, position), (hex(b), position)
            assert_sdk_error(outcome.error, PROBE_NAME, value, "it ")
        else:
            assert rule_accepts(b, position), (hex(b), position)
            # Exactly the value, byte for byte, once.
            assert values(outcome, PROBE_NAME) == [value], (hex(b), position)


def test_every_byte_http_sync():
    results = []
    with recording_server() as (url, seen):
        current: dict[str, str] = {}
        client = FishAudio(
            api_key="test-key", base_url=url, header_provider=lambda: current
        )
        for b, position, value in PROBES:
            current = {PROBE_NAME: value}
            before = len(seen)
            try:
                client.account.get_credits()
            except Exception as error:
                assert len(seen) == before, (hex(b), position)  # nothing sent
                results.append((b, position, value, NothingSent(error)))
            else:
                assert len(seen) == before + 1
                results.append((b, position, value, seen[-1][1]))
        client.close()
    _check_probes(results)


async def test_every_byte_http_async():
    results = []
    with recording_server() as (url, seen):
        current: dict[str, str] = {}
        client = AsyncFishAudio(
            api_key="test-key", base_url=url, header_provider=lambda: current
        )
        for b, position, value in PROBES:
            current = {PROBE_NAME: value}
            before = len(seen)
            try:
                await client.account.get_credits()
            except Exception as error:
                assert len(seen) == before, (hex(b), position)
                results.append((b, position, value, NothingSent(error)))
            else:
                assert len(seen) == before + 1
                results.append((b, position, value, seen[-1][1]))
        await client.close()
    _check_probes(results)


@pytest.mark.parametrize("kind", ["tts", "asr"])
def test_every_byte_websocket_handshake(kind):
    send_ws = ws_sync(kind)
    results = []
    for b, position, value in PROBES:
        try:
            headers = send_ws(lambda: {PROBE_NAME: value})
        except NothingSent as outcome:
            results.append((b, position, value, outcome))
        else:
            results.append((b, position, value, headers))
    _check_probes(results)


def test_default_opentelemetry_provider_output_passes():
    """The default provider's output always satisfies the rule."""
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("t")
    with recording_server() as (url, seen):
        client = FishAudio(api_key="test-key", base_url=url)
        with tracer.start_as_current_span("s") as span:
            client.account.get_credits()
            context = span.get_span_context()
        client.close()
    assert values(seen[0][1], "traceparent") == [
        f"00-{context.trace_id:032x}-{context.span_id:016x}-01"
    ]
