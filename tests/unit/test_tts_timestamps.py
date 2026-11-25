"""Tests for TTS with timestamps over real httpx transports.

The responses replay the Server-Sent Events framing recorded from the live
`POST /v1/tts/stream/with-timestamp` endpoint: `event: message` lines, one JSON
payload per event, snapshots that grow per chunk, and a closing event with
empty audio that only corrects timings.
"""

import base64
import json

import httpx
import ormsgpack
import pytest

from fishaudio import (
    AsyncTTSTimestampStream,
    TTSConfig,
    TTSTimestampEvent,
    TTSTimestampResult,
    TTSTimestampStream,
)
from fishaudio.core import AsyncClientWrapper, ClientWrapper, RequestOptions
from fishaudio.core._sse import ServerSentEvent, SSEDecoder
from fishaudio.exceptions import APIError, FishAudioError
from fishaudio.resources.tts import AsyncTTSClient, TTSClient

BASE_URL = "https://api.test.fish.audio"


def _seg(text, start, end):
    return {"text": text, "start": start, "end": end}


def _payload(audio, *, seq=0, offset=0.0, content="Hello world.", alignment=None):
    return {
        "audio_base64": base64.b64encode(audio).decode(),
        "content": content,
        "alignment": alignment,
        "chunk_seq": seq,
        "chunk_audio_offset_sec": offset,
    }


def _sse(payload):
    return f"event: message\r\ndata: {json.dumps(payload)}\r\n\r\n".encode()


# Two text chunks. Chunk 0 starts without timings, grows, and its last word is
# corrected by a later snapshot; chunk 1 ends with an audio-less correction.
PAYLOADS = [
    _payload(b"aa"),
    _payload(
        b"bb",
        alignment={"segments": [_seg("Hello", 0.0, 0.5)], "audio_duration": 0.6},
    ),
    _payload(
        b"cc",
        alignment={
            "segments": [_seg("Hello", 0.0, 0.4), _seg("world", 0.5, 1.0)],
            "audio_duration": 1.25,
        },
    ),
    _payload(
        b"dd",
        seq=1,
        offset=1.25,
        content="你好",
        alignment={"segments": [_seg("你", 0.0, 0.25)], "audio_duration": 0.5},
    ),
    _payload(
        b"",
        seq=1,
        offset=1.25,
        content="你好",
        alignment={
            "segments": [_seg("你", 0.0, 0.25), _seg("好", 0.25, 0.5)],
            "audio_duration": 0.75,
        },
    ),
]
BODY = [_sse(p) for p in PAYLOADS]
FINAL = [("Hello", 0.0, 0.4), ("world", 0.5, 1.0), ("你", 1.25, 1.5), ("好", 1.5, 1.75)]


# What the live API sends when the text has nothing to align (for example
# "[sigh]" or punctuation only): audio, and `alignment: null` on every event.
NO_ALIGNMENT_BODY = [
    _sse(_payload(audio, content="[sigh]")) for audio in (b"aa", b"bb", b"cc")
]
_WORLD = {"segments": [_seg("world", 0.0, 0.5)], "audio_duration": 0.75}
# Chunk 0 never gets timings, chunk 1 does.
FIRST_CHUNK_UNALIGNED_BODY = [
    _sse(_payload(b"aa", content="...")),
    _sse(_payload(b"bb", seq=1, offset=1.5, content="world", alignment=_WORLD)),
]
# Chunk 0 gets timings, the last chunk never does.
LAST_CHUNK_UNALIGNED_BODY = [
    _sse(_payload(b"aa", content="world", alignment=_WORLD)),
    _sse(_payload(b"bb", seq=1, offset=0.75, content="[sigh]")),
]


def _timings(segments):
    return [(s.text, s.start, s.end) for s in segments]


class _SyncBody(httpx.SyncByteStream):
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


def _ok(body):
    return lambda request: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, stream=body
    )


class TestSSEDecoder:
    def test_event_split_across_arbitrary_byte_boundaries(self):
        raw = b"".join(BODY)
        for size in (1, 7, 64):
            decoder = SSEDecoder()
            events = []
            for i in range(0, len(raw), size):
                events += decoder.feed(raw[i : i + size])
            assert [json.loads(e.data) for e in events] == PAYLOADS
            assert {e.event for e in events} == {"message"}

    def test_framing_rules(self):
        decoder = SSEDecoder()
        events = decoder.feed(
            b": keep-alive\n\n"  # comment only: no event
            b"data: plain\n\n"  # LF endings, default event name
            b"event: error\ndata:no-space\nid: 7\n\n"  # named, no space, unknown field
            b"data: line1\ndata: line2\n\n"  # multi-line data
            b"data: unterminated\n"  # dropped: stream ends before the blank line
        )
        assert events == [
            ServerSentEvent("message", "plain"),
            ServerSentEvent("error", "no-space"),
            ServerSentEvent("message", "line1\nline2"),
        ]

    @pytest.mark.parametrize("newline", [b"\r", b"\n", b"\r\n"])
    def test_every_line_ending_at_every_chunk_boundary(self, newline):
        raw = b"".join(BODY).replace(b"\r\n", newline)
        raw += b"event: ping" + newline + b"data: last" + newline + newline
        for size in (1, 2, 3, 7, len(raw)):
            decoder = SSEDecoder()
            events = []
            for i in range(0, len(raw), size):
                events += decoder.feed(raw[i : i + size])
            assert [json.loads(e.data) for e in events[:-1]] == PAYLOADS
            assert events[-1] == ServerSentEvent("ping", "last")

    def test_cr_terminated_event_is_dispatched_without_waiting_for_more_bytes(self):
        decoder = SSEDecoder()
        assert decoder.feed(b"data: one\r\r") == [ServerSentEvent("message", "one")]
        # A CRLF pair split across chunks must not count as two line endings.
        assert decoder.feed(b"data: two\r") == []
        assert decoder.feed(b"\ndata: three\r") == []
        assert decoder.feed(b"\n\r\n") == [ServerSentEvent("message", "two\nthree")]

    def test_unicode_line_separators_stay_inside_data(self):
        text = "a b\u0085c"
        events = SSEDecoder().feed(f"data: {text}\n\n".encode())
        assert events == [ServerSentEvent("message", text)]


class TestSyncTimestamps:
    def test_request_matches_plain_tts_request(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return httpx.Response(200, stream=_SyncBody(BODY))

        _sync_tts(handler).stream_with_timestamps(
            text="Hello world.",
            reference_id="voice-1",
            format="opus",
            latency="normal",
            speed=1.5,
            config=TTSConfig(opus_bitrate=24),
            model="s2-pro",
        ).close()

        request = seen["request"]
        assert request.method == "POST"
        assert request.url.path == "/v1/tts/stream/with-timestamp"
        assert request.headers["content-type"] == "application/msgpack"
        assert request.headers["accept"] == "text/event-stream"
        assert request.headers["model"] == "s2-pro"
        assert request.headers["authorization"] == "Bearer test"
        body = ormsgpack.unpackb(request.content)
        assert body["text"] == "Hello world."
        assert body["reference_id"] == "voice-1"
        assert body["format"] == "opus"
        assert body["latency"] == "normal"
        assert body["prosody"]["speed"] == 1.5
        assert body["opus_bitrate"] == 24000

    def test_events_are_typed_and_arrive_incrementally(self):
        body = _SyncBody(BODY)
        stream = _sync_tts(_ok(body)).stream_with_timestamps(text="Hello world.")
        assert isinstance(stream, TTSTimestampStream)
        assert body.produced == 0  # nothing read until the caller iterates

        first = next(stream)
        assert isinstance(first, TTSTimestampEvent)
        assert body.produced == 1
        assert (first.audio, first.alignment, first.segments) == (b"aa", None, [])
        assert stream.segments == []

        second = next(stream)
        assert second.content == "Hello world."
        assert second.alignment.audio_duration == 0.6
        assert _timings(stream.segments) == [("Hello", 0.0, 0.5)]

        rest = list(stream)
        assert [e.audio for e in rest] == [b"cc", b"dd", b""]
        assert rest[1].chunk_seq == 1
        assert rest[1].chunk_audio_offset_sec == 1.25
        # event.segments is that event's own snapshot on the full-audio timeline
        assert _timings(rest[1].segments) == [("你", 1.25, 1.5)]
        # stream.segments replaces snapshots per chunk and joins chunks in order
        assert _timings(stream.segments) == FINAL
        assert body.closed

    def test_collect_returns_audio_final_timings_and_duration(self):
        body = _SyncBody(BODY)
        result = _sync_tts(_ok(body)).stream_with_timestamps(text="Hi").collect()
        assert isinstance(result, TTSTimestampResult)
        assert result.audio == b"aabbccdd"
        assert _timings(result.segments) == FINAL
        assert result.duration == 2.0
        assert body.closed

    def test_convert_with_timestamps(self):
        tts = _sync_tts(_ok(_SyncBody(BODY)))
        result = tts.convert_with_timestamps(text="Hello world.")
        assert result.audio == b"aabbccdd"
        assert _timings(result.segments) == FINAL

    def test_audio_without_alignment_has_no_duration(self):
        tts = _sync_tts(_ok(_SyncBody(NO_ALIGNMENT_BODY)))
        result = tts.stream_with_timestamps(text="[sigh]").collect()
        assert result.audio == b"aabbcc"
        assert result.segments == []
        assert result.duration is None

        tts = _sync_tts(_ok(_SyncBody(NO_ALIGNMENT_BODY)))
        assert tts.convert_with_timestamps(text="[sigh]") == result

    def test_streaming_audio_without_alignment(self):
        tts = _sync_tts(_ok(_SyncBody(NO_ALIGNMENT_BODY)))
        with tts.stream_with_timestamps(text="[sigh]") as stream:
            events = list(stream)
            assert stream.segments == []
        assert [e.audio for e in events] == [b"aa", b"bb", b"cc"]
        assert all(e.alignment is None and e.segments == [] for e in events)

    def test_chunk_without_alignment_does_not_shift_later_chunks(self):
        tts = _sync_tts(_ok(_SyncBody(FIRST_CHUNK_UNALIGNED_BODY)))
        result = tts.convert_with_timestamps(text="... world")
        assert result.audio == b"aabb"
        assert _timings(result.segments) == [("world", 1.5, 2.0)]
        assert result.duration == 2.25

    def test_last_chunk_without_alignment_has_no_duration(self):
        tts = _sync_tts(_ok(_SyncBody(LAST_CHUNK_UNALIGNED_BODY)))
        result = tts.convert_with_timestamps(text="world [sigh]")
        assert result.audio == b"aabb"
        assert _timings(result.segments) == [("world", 0.0, 0.5)]
        assert result.duration is None

    def test_collect_after_iteration_started_is_refused(self):
        body = _SyncBody(BODY)
        stream = _sync_tts(_ok(body)).stream_with_timestamps(text="Hi")
        assert next(stream).audio == b"aa"
        with pytest.raises(RuntimeError, match="collect"):
            stream.collect()
        # The stream is left usable: nothing was read or closed by the refusal.
        assert body.produced == 1
        assert not body.closed
        assert [e.audio for e in stream] == [b"bb", b"cc", b"dd", b""]
        assert _timings(stream.segments) == FINAL

    def test_with_block_closes_after_early_break(self):
        body = _SyncBody(BODY)
        with _sync_tts(_ok(body)).stream_with_timestamps(text="Hi") as stream:
            for _ in stream:
                break
            assert not body.closed
        assert body.produced == 1
        assert body.closed
        stream.close()  # idempotent
        assert list(stream) == []

    def test_close_before_iteration_releases_response(self):
        body = _SyncBody(BODY)
        stream = _sync_tts(_ok(body)).stream_with_timestamps(text="Hi")
        stream.close()
        assert body.produced == 0
        assert body.closed

    def test_unknown_fields_and_event_names_are_tolerated(self):
        payload = _payload(b"aa", alignment={"segments": [], "audio_duration": 0.0})
        payload["new_field"] = 1
        body = [b"event: ping\ndata: {}\n\n", b": keep-alive\n\n", _sse(payload)]
        events = list(_sync_tts(_ok(_SyncBody(body))).stream_with_timestamps(text="x"))
        assert [e.audio for e in events] == [b"aa"]
        assert events[0].model_extra == {"new_field": 1}

    def test_http_error_raised_at_call_time(self):
        tts = _sync_tts(
            lambda request: httpx.Response(
                400, json={"message": "Reference not found", "status": 400}
            )
        )
        with pytest.raises(APIError) as exc:
            tts.stream_with_timestamps(text="Hello", reference_id="missing")
        assert exc.value.status == 400
        assert "Reference not found" in str(exc.value)

    @pytest.mark.parametrize(
        "frame",
        [
            b"event: error\ndata: backend unavailable\n\n",
            b'data: {"message": "backend unavailable"}\n\n',
            b"data: not json\n\n",
            b'data: {"audio_base64": "!", "chunk_seq": 0}\n\n',
            b"data: null\n\n",
            b'data: "text"\n\n',
            b"data: 5\n\n",
            b'data: ["audio_base64"]\n\n',
        ],
    )
    def test_unusable_event_raises_and_closes(self, frame):
        body = _SyncBody([BODY[0], frame, BODY[1]])
        stream = _sync_tts(_ok(body)).stream_with_timestamps(text="Hello")
        assert next(stream).audio == b"aa"
        with pytest.raises(FishAudioError):
            next(stream)
        assert body.closed

    def test_request_options_timeout_applies(self):
        seen = {}

        def handler(request):
            seen["timeout"] = request.extensions["timeout"]
            return httpx.Response(200, stream=_SyncBody(BODY))

        _sync_tts(handler).convert_with_timestamps(
            text="Hello", request_options=RequestOptions(timeout=12.5)
        )
        assert seen["timeout"]["read"] == 12.5


class TestAsyncTimestamps:
    async def test_request_path_and_headers(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return httpx.Response(200, stream=_AsyncBody(BODY))

        stream = await _async_tts(handler).stream_with_timestamps(
            text="Hello world.", format="wav", model="s2-pro"
        )
        await stream.aclose()

        request = seen["request"]
        assert request.url.path == "/v1/tts/stream/with-timestamp"
        assert request.headers["content-type"] == "application/msgpack"
        assert request.headers["model"] == "s2-pro"
        assert ormsgpack.unpackb(request.content)["format"] == "wav"

    async def test_events_are_typed_and_arrive_incrementally(self):
        body = _AsyncBody(BODY)
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hi")
        assert isinstance(stream, AsyncTTSTimestampStream)
        assert body.produced == 0

        first = await stream.__anext__()
        assert body.produced == 1
        assert (first.audio, first.alignment) == (b"aa", None)

        audio = [event.audio async for event in stream]
        assert audio == [b"bb", b"cc", b"dd", b""]
        assert _timings(stream.segments) == FINAL
        assert body.closed

    async def test_collect_and_convert(self):
        body = _AsyncBody(BODY)
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hi")
        result = await stream.collect()
        assert result.audio == b"aabbccdd"
        assert _timings(result.segments) == FINAL
        assert result.duration == 2.0
        assert body.closed

        tts = _async_tts(_ok(_AsyncBody(BODY)))
        converted = await tts.convert_with_timestamps(text="Hi")
        assert converted == result

    async def test_audio_without_alignment_has_no_duration(self):
        tts = _async_tts(_ok(_AsyncBody(NO_ALIGNMENT_BODY)))
        stream = await tts.stream_with_timestamps(text="[sigh]")
        result = await stream.collect()
        assert result.audio == b"aabbcc"
        assert result.segments == []
        assert result.duration is None

        tts = _async_tts(_ok(_AsyncBody(NO_ALIGNMENT_BODY)))
        assert await tts.convert_with_timestamps(text="[sigh]") == result

    async def test_streaming_audio_without_alignment(self):
        tts = _async_tts(_ok(_AsyncBody(NO_ALIGNMENT_BODY)))
        async with await tts.stream_with_timestamps(text="[sigh]") as stream:
            events = [event async for event in stream]
            assert stream.segments == []
        assert [e.audio for e in events] == [b"aa", b"bb", b"cc"]
        assert all(e.alignment is None and e.segments == [] for e in events)

    async def test_chunk_without_alignment_does_not_shift_later_chunks(self):
        tts = _async_tts(_ok(_AsyncBody(FIRST_CHUNK_UNALIGNED_BODY)))
        result = await tts.convert_with_timestamps(text="... world")
        assert _timings(result.segments) == [("world", 1.5, 2.0)]
        assert result.duration == 2.25

    async def test_last_chunk_without_alignment_has_no_duration(self):
        tts = _async_tts(_ok(_AsyncBody(LAST_CHUNK_UNALIGNED_BODY)))
        result = await tts.convert_with_timestamps(text="world [sigh]")
        assert _timings(result.segments) == [("world", 0.0, 0.5)]
        assert result.duration is None

    async def test_collect_after_iteration_started_is_refused(self):
        body = _AsyncBody(BODY)
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hi")
        assert (await stream.__anext__()).audio == b"aa"
        with pytest.raises(RuntimeError, match="collect"):
            await stream.collect()
        assert body.produced == 1
        assert not body.closed
        assert [e.audio async for e in stream] == [b"bb", b"cc", b"dd", b""]
        assert _timings(stream.segments) == FINAL

    async def test_async_with_closes_after_early_break(self):
        body = _AsyncBody(BODY)
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hi")
        async with stream:
            async for _ in stream:
                break
            assert not body.closed
        assert body.produced == 1
        assert body.closed
        await stream.aclose()  # idempotent

    async def test_close_before_iteration_releases_response(self):
        body = _AsyncBody(BODY)
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hi")
        await stream.aclose()
        assert body.produced == 0
        assert body.closed

    async def test_http_error_raised_at_call_time(self):
        tts = _async_tts(
            lambda request: httpx.Response(402, json={"message": "No credit"})
        )
        with pytest.raises(APIError) as exc:
            await tts.stream_with_timestamps(text="Hello")
        assert exc.value.status == 402

    async def test_unusable_event_raises_and_closes(self):
        body = _AsyncBody([BODY[0], b"data: not json\n\n"])
        stream = await _async_tts(_ok(body)).stream_with_timestamps(text="Hello")
        assert (await stream.__anext__()).audio == b"aa"
        with pytest.raises(FishAudioError):
            await stream.__anext__()
        assert body.closed
