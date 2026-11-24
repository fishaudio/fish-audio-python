"""Tests for realtime speech-to-text (client.asr.stream_websocket).

The session tests run the real client against a scripted WebSocket server on a
local TCP socket (see realtime_server.py), so they cover the wire format, the
ordering of messages and how the connection is closed.
"""

import asyncio
import contextlib
import threading
import time

import ormsgpack
import pytest
from httpx_ws import WebSocketNetworkError

from fishaudio import (
    APIError,
    ASRRealtimeError,
    AsyncFishAudio,
    AuthenticationError,
    FishAudio,
    WebSocketError,
)
from fishaudio.resources import asr_realtime
from fishaudio.resources.asr import _realtime_config
from fishaudio.resources.asr_realtime import (
    ASRRealtimeStream,
    AsyncASRRealtimeStream,
    decode_event,
    encode_config,
    encode_message,
)
from fishaudio.types import (
    ASRAgentSpeakingEvent,
    ASRCommittedEvent,
    ASRConfigureEvent,
    ASRContext,
    ASRContextAddEvent,
    ASRContextItem,
    ASRDraftEvent,
    ASRErrorEvent,
    ASRFinalizeEvent,
    ASRRealtimeConfig,
    ASRResults,
    ASRSessionDoneEvent,
    ASRSessionStartedEvent,
    ASRTurnDetection,
)

from .realtime_server import SESSION_STARTED, RealtimeServer

CHUNK = b"\x01\x00" * 320  # 20 ms of 16 kHz audio

SPEECH_START = {"type": "speech_start", "seq": 1, "turn_index": 0, "audio_ms": 300}
DRAFT = {
    "type": "draft",
    "seq": 2,
    "turn_index": 0,
    "text": "what's the weather",
    "settled_text": "",
    "language_code": "en",
    "audio_ms": 1800,
}
COMMITTED = {
    "type": "committed",
    "seq": 3,
    "turn_index": 0,
    "text": "What's the weather like?",
    "language": "English",
    "language_code": "en",
    "audio_start_ms": 300,
    "audio_end_ms": 2880,
    "reason": "audio_done",
    "degraded": False,
    "user_turn": True,
    "turn_kind": "user",
}
SESSION_DONE = {
    "type": "session_done",
    "seq": 4,
    "stats": {"audio_ms": 40, "turns": 1, "request_id": "req_test"},
}


def error_message(error_type, *, recoverable, code=400):
    return {
        "type": "error",
        "seq": 1,
        "code": code,
        "error_type": error_type,
        "message": f"{error_type} happened",
        "request_id": "req_test",
        "recoverable": recoverable,
    }


def transcribe_script(conn):
    """A whole session: config, audio until audio_done, one committed turn."""
    conn.recv()
    assert conn.quiet_for(0.2), "audio was sent before session_started"
    conn.send(SESSION_STARTED)
    conn.send(SPEECH_START)
    conn.recv_until("audio_done")
    conn.send(DRAFT)
    conn.send(COMMITTED)
    conn.send(SESSION_DONE)
    conn.close(1000, "done")


def open_ended_script(conn):
    """Start a session, commit one turn, then keep it open until the client leaves."""
    conn.recv()
    conn.send(SESSION_STARTED)
    conn.send(COMMITTED)


def endless_audio():
    while True:
        yield CHUNK
        time.sleep(0.01)


async def aendless_audio():
    while True:
        yield CHUNK
        await asyncio.sleep(0.01)


async def aiter_chunks(*items):
    for item in items:
        yield item


@contextlib.contextmanager
def serving(script, **server_options):
    server = RealtimeServer(script, **server_options)
    client = FishAudio(api_key="test-key", base_url=server.url)
    try:
        yield server, client
    finally:
        client.close()
        server.close()


@contextlib.asynccontextmanager
async def aserving(script, **server_options):
    server = RealtimeServer(script, **server_options)
    client = AsyncFishAudio(api_key="test-key", base_url=server.url)
    try:
        yield server, client
    finally:
        await client.close()
        server.close()


def sender_threads():
    return [
        t for t in threading.enumerate() if t.name == "fishaudio-asr-realtime-sender"
    ]


def wait_for_no_sender_threads(timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and sender_threads():
        time.sleep(0.01)
    return not sender_threads()


async def astop(server):
    """Wait for the server script without blocking the event loop."""
    return await asyncio.get_running_loop().run_in_executor(None, server.stop)


class TestEncoding:
    def test_config_defaults_send_only_the_audio_format(self):
        assert ormsgpack.unpackb(encode_config(ASRRealtimeConfig())) == {
            "type": "config",
            "audio": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1},
        }

    def test_config_with_every_option(self):
        config = ASRRealtimeConfig(
            sample_rate=48000,
            turn_detection=ASRTurnDetection(
                mode="vad", eager=False, silence_timeout_ms=900
            ),
            results=ASRResults(drafts=True, ignore_timestamps=False, diarize=False),
            context=ASRContext(
                history=[ASRContextItem(role="assistant", text="Hello.")],
                terms=["Fish Audio"],
            ),
            client_reference_id="call-42",
        )
        assert ormsgpack.unpackb(encode_config(config)) == {
            "type": "config",
            "audio": {"format": "pcm_s16le", "sample_rate": 48000, "channels": 1},
            "turn_detection": {
                "mode": "vad",
                "eager": False,
                "silence_timeout_ms": 900,
            },
            "results": {"drafts": True, "ignore_timestamps": False, "diarize": False},
            "context": {
                "history": [{"role": "assistant", "text": "Hello."}],
                "terms": ["Fish Audio"],
            },
            "client_reference_id": "call-42",
        }

    def test_config_rejects_unsupported_sample_rate(self):
        with pytest.raises(ValueError):
            ASRRealtimeConfig(sample_rate=11025)

    def test_direct_parameters_override_config_without_mutating_it(self):
        base = ASRRealtimeConfig(
            sample_rate=8000,
            turn_detection=ASRTurnDetection(mode="vad", silence_timeout_ms=900),
            context=ASRContext(terms=["old"]),
        )
        merged = _realtime_config(
            base,
            sample_rate=24000,
            turn_detection="auto",
            eager=True,
            drafts=True,
            diarize=False,
            terms=["Fish Audio"],
        )
        assert merged.sample_rate == 24000
        assert merged.turn_detection == ASRTurnDetection(
            mode="auto", eager=True, silence_timeout_ms=900
        )
        assert merged.results == ASRResults(drafts=True, diarize=False)
        assert merged.context == ASRContext(terms=["Fish Audio"])
        assert base.sample_rate == 8000
        assert base.turn_detection.mode == "vad"
        assert base.context.terms == ["old"]

    def test_omitted_parameters_keep_config(self):
        base = ASRRealtimeConfig(results=ASRResults(drafts=True))
        merged = _realtime_config(
            base,
            sample_rate=None,
            turn_detection=None,
            eager=None,
            drafts=None,
            diarize=None,
            terms=None,
        )
        assert merged == base

    def test_diarize_keeps_other_result_settings(self):
        base = ASRRealtimeConfig(results=ASRResults(drafts=True, diarize=True))
        merged = _realtime_config(
            base,
            sample_rate=None,
            turn_detection=None,
            eager=None,
            drafts=None,
            diarize=False,
            terms=None,
        )
        assert merged.results == ASRResults(drafts=True, diarize=False)
        assert base.results.diarize is True

    def test_audio_is_packed_as_msgpack_bin(self):
        packed = encode_message(b"\x01\x02\x03")
        assert ormsgpack.unpackb(packed) == {"type": "audio", "data": b"\x01\x02\x03"}
        # bin 8 marker + length: the server drops audio sent as str or array
        assert b"\xc4\x03\x01\x02\x03" in packed
        assert encode_message(bytearray(b"\x01\x02\x03")) == packed
        assert encode_message(memoryview(b"\x01\x02\x03")) == packed

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            (ASRFinalizeEvent(), {"type": "finalize"}),
            (
                ASRAgentSpeakingEvent(speaking=True),
                {"type": "agent_speaking", "speaking": True},
            ),
            (
                ASRContextAddEvent(
                    items=[ASRContextItem(role="assistant", text="Sure.")]
                ),
                {
                    "type": "context_add",
                    "items": [{"role": "assistant", "text": "Sure."}],
                    "reset_history": False,
                },
            ),
            (
                ASRConfigureEvent(context=ASRContext(terms=["Main Street"])),
                {"type": "configure", "context": {"terms": ["Main Street"]}},
            ),
        ],
    )
    def test_control_messages(self, message, expected):
        assert ormsgpack.unpackb(encode_message(message)) == expected


class TestDecoding:
    def test_committed(self):
        event = decode_event(
            ormsgpack.packb(
                {
                    **COMMITTED,
                    "words": [{"text": "What's", "start_ms": 300, "end_ms": 620}],
                }
            )
        )
        assert isinstance(event, ASRCommittedEvent)
        assert event.text == "What's the weather like?"
        assert event.reason == "audio_done"
        assert event.user_turn is True
        assert event.turn_kind == "user"
        assert event.words[0].start_ms == 300
        assert (event.audio_start_ms, event.audio_end_ms) == (300, 2880)

    def test_committed_treats_missing_user_turn_as_true(self):
        event = decode_event(
            ormsgpack.packb({"type": "committed", "turn_index": 1, "text": ""})
        )
        assert event.user_turn is True
        assert event.words is None
        assert event.language_code is None

    def test_draft(self):
        event = decode_event(ormsgpack.packb(DRAFT))
        assert isinstance(event, ASRDraftEvent)
        assert (event.text, event.settled_text) == ("what's the weather", "")
        assert event.language is None

    @pytest.mark.parametrize(
        "message",
        [
            SESSION_STARTED,
            SPEECH_START,
            {"type": "user_turn_taken", "seq": 3, "turn_index": 0, "audio_ms": 1280},
            DRAFT,
            {"type": "eager_end_of_turn", "seq": 5, "turn_index": 0, "text": "Hi."},
            {"type": "turn_resumed", "seq": 6, "turn_index": 0},
            {"type": "user_backchannel", "seq": 8, "turn_index": 1, "audio_ms": 3840},
            COMMITTED,
            {"type": "vad", "seq": 12, "audio_ms": 1100, "score": 0.93},
            {
                "type": "eot_prob",
                "seq": 13,
                "turn_index": 0,
                "audio_ms": 2200,
                "prob": 0.42,
            },
            {"type": "configured", "seq": 1, "ok": False, "config": {}, "message": "x"},
            {"type": "progress", "seq": 30, "audio_received_ms": 12000},
            error_message("invalid_request", recoverable=True),
            SESSION_DONE,
        ],
        ids=lambda message: message["type"],
    )
    def test_every_server_message_type_has_a_model(self, message):
        event = decode_event(ormsgpack.packb(message))
        assert event.type == message["type"]
        assert event.seq == message["seq"]

    def test_unknown_message_type_is_ignored(self):
        assert decode_event(ormsgpack.packb({"type": "from_the_future"})) is None

    def test_unknown_fields_are_kept(self):
        event = decode_event(ormsgpack.packb({**SPEECH_START, "confidence": 0.8}))
        assert event.confidence == 0.8


class TestSyncSession:
    def test_streams_audio_and_yields_typed_events(self):
        with serving(transcribe_script) as (server, client):
            events = list(
                client.asr.stream_websocket(
                    iter([CHUNK, b"", CHUNK]), sample_rate=16000, drafts=True
                )
            )
        conn = server.stop()

        assert [event.type for event in events] == [
            "session_started",
            "speech_start",
            "draft",
            "committed",
            "session_done",
        ]
        assert isinstance(events[0], ASRSessionStartedEvent)
        assert events[0].session_id == "s_test"
        assert events[3].text == "What's the weather like?"
        assert isinstance(events[4], ASRSessionDoneEvent)
        assert events[4].stats.turns == 1

        assert conn.path == "/v1/asr/realtime"
        assert conn.headers["authorization"] == "Bearer test-key"
        assert conn.headers["model"] == "transcribe-stream-1"
        assert conn.received == [
            {
                "type": "config",
                "audio": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1},
                "results": {"drafts": True},
            },
            {"type": "audio", "data": CHUNK},
            {"type": "audio", "data": CHUNK},
            {"type": "audio_done"},
        ]
        assert conn.close_code == 1000

    def test_control_messages_in_the_audio_stream_keep_their_position(self):
        with serving(transcribe_script) as (server, client):
            list(
                client.asr.stream_websocket(
                    iter([CHUNK, ASRFinalizeEvent(), CHUNK]), turn_detection="manual"
                )
            )
        conn = server.stop()
        assert conn.received[0]["turn_detection"] == {"mode": "manual"}
        assert [m["type"] for m in conn.received[1:]] == [
            "audio",
            "finalize",
            "audio",
            "audio_done",
        ]

    def test_control_methods_send_during_the_session(self):
        release = threading.Event()

        def audio():
            yield CHUNK
            release.wait(5)

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(COMMITTED)
            conn.recv_until("audio_done")
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        with serving(script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            with pytest.raises(WebSocketError, match="not open"):
                stream.finalize()
            for event in stream:
                if event.type == "committed":
                    stream.agent_speaking(True)
                    stream.add_context([ASRContextItem(role="assistant", text="Hi.")])
                    stream.configure(
                        turn_detection=ASRTurnDetection(mode="vad"),
                        terms=["Fish Audio"],
                    )
                    stream.finalize()
                    stream.keepalive()
                    release.set()
            with pytest.raises(WebSocketError, match="not open"):
                stream.finalize()
        conn = server.stop()

        control = [m for m in conn.received[1:] if m["type"] != "audio"]
        assert control == [
            {"type": "agent_speaking", "speaking": True},
            {
                "type": "context_add",
                "items": [{"role": "assistant", "text": "Hi."}],
                "reset_history": False,
            },
            {
                "type": "configure",
                "turn_detection": {"mode": "vad"},
                "context": {"terms": ["Fish Audio"]},
            },
            {"type": "finalize"},
            {"type": "keepalive"},
            {"type": "audio_done"},
        ]

    def test_unknown_messages_are_skipped(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send({"type": "from_the_future", "seq": 1})
            conn.recv_until("audio_done")
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        with serving(script) as (server, client):
            events = list(client.asr.stream_websocket(iter([CHUNK])))
        server.stop()
        assert [event.type for event in events] == ["session_started", "session_done"]

    def test_recoverable_error_is_an_event_and_the_session_continues(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(error_message("invalid_request", recoverable=True))
            conn.recv_until("audio_done")
            conn.send(COMMITTED)
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        with serving(script) as (server, client):
            events = list(client.asr.stream_websocket(iter([CHUNK])))
        server.stop()
        assert [event.type for event in events] == [
            "session_started",
            "error",
            "committed",
            "session_done",
        ]
        assert isinstance(events[1], ASRErrorEvent)
        assert events[1].error_type == "invalid_request"

    def test_fatal_error_event_raises(self):
        def script(conn):
            conn.recv()
            conn.send(error_message("unsupported_audio", recoverable=False))
            conn.close(4400, "unsupported_audio")

        with (
            serving(script) as (server, client),
            pytest.raises(ASRRealtimeError) as exc_info,
        ):
            list(client.asr.stream_websocket(iter([CHUNK])))
        conn = server.stop()

        error = exc_info.value
        assert isinstance(error, WebSocketError)
        assert error.error_type == "unsupported_audio"
        assert error.code == 400
        assert error.request_id == "req_test"
        assert "unsupported_audio happened" in str(error)
        assert [m["type"] for m in conn.received] == ["config"]  # no audio was sent
        assert conn.close_code is not None  # the client closed its side

    def test_server_restarting_yields_the_error_then_raises_with_close_code(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(error_message("server_restarting", recoverable=True, code=503))
            conn.close(1012, "restarting")

        events = []
        with (
            serving(script) as (server, client),
            pytest.raises(ASRRealtimeError) as exc_info,
        ):
            for event in client.asr.stream_websocket(endless_audio()):
                events.append(event)
        server.stop()

        assert [event.type for event in events] == ["session_started", "error"]
        assert exc_info.value.close_code == 1012
        assert exc_info.value.error_type == "server_restarting"

    def test_abnormal_close_without_error_event_raises_with_close_code(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.close(1011, "boom")

        with (
            serving(script) as (server, client),
            pytest.raises(ASRRealtimeError) as exc_info,
        ):
            list(client.asr.stream_websocket(endless_audio()))
        server.stop()
        assert exc_info.value.close_code == 1011
        assert exc_info.value.error_type is None
        assert "boom" in str(exc_info.value)

    def test_dropped_connection_raises_websocket_error(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.drop()

        with serving(script) as (server, client), pytest.raises(WebSocketError):
            list(client.asr.stream_websocket(endless_audio()))
        server.stop()

    def test_audio_failure_is_not_delayed_by_a_steady_stream_of_events(self):
        def audio():
            yield CHUNK
            raise RuntimeError("microphone unplugged")

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv()  # the one audio chunk
            with contextlib.suppress(OSError):  # the client leaves before the end
                for seq in range(200):  # an event every 10 ms for 2 s
                    conn.send({**DRAFT, "seq": seq})
                    time.sleep(0.01)

        with serving(script) as (server, client):
            started = time.monotonic()
            with pytest.raises(RuntimeError, match="microphone unplugged"):
                list(client.asr.stream_websocket(audio()))
            assert time.monotonic() - started < 1.0
            server.stop()

    def test_audio_failure_is_raised_when_the_server_closes_normally(self, monkeypatch):
        # The server must close only after the SDK has recorded the failure:
        # receiving the chunk does not prove that, so wait for the sender to end.
        sender_ended = threading.Event()
        send_audio = asr_realtime._send_audio

        def send_audio_then_signal(*args):
            try:
                send_audio(*args)
            finally:
                sender_ended.set()

        monkeypatch.setattr(asr_realtime, "_send_audio", send_audio_then_signal)

        def audio():
            yield CHUNK
            time.sleep(0.05)  # the failure comes well after the chunk was sent
            raise RuntimeError("microphone unplugged")

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv()  # the one audio chunk
            assert sender_ended.wait(5)
            conn.close(1000, "bye")

        with (
            serving(script) as (server, client),
            pytest.raises(RuntimeError, match="microphone unplugged"),
        ):
            list(client.asr.stream_websocket(audio()))
        server.stop()

    def test_connection_is_closed_once_session_done_is_returned(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv_until("audio_done")
            conn.send(SESSION_DONE)

        with serving(script) as (server, client):
            stream = client.asr.stream_websocket(iter([CHUNK]))
            assert next(stream).type == "session_started"
            assert next(stream).type == "session_done"
            # No further next() or close(): the client must already be gone.
            conn = server.stop()
            assert list(stream) == []
        assert conn.close_code == 1000

    def test_close_does_not_hang_when_many_events_are_unread(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            for seq in range(800):  # more than httpx-ws's receive queue holds
                conn.send({**DRAFT, "seq": seq})

        with serving(script) as (server, client):
            stream = client.asr.stream_websocket(endless_audio())
            assert next(stream).type == "session_started"
            time.sleep(0.5)  # the consumer stops reading; the transport queue fills

            closer = threading.Thread(target=stream.close, daemon=True)
            closer.start()
            closer.join(3)
            assert not closer.is_alive(), "close() is stuck"
            server.stop()

    def test_connection_lost_while_sending_config_raises_websocket_error(self):
        """A network failure on the first frame is a WebSocketError, not httpx-ws's own."""

        class LostSession:
            def send_bytes(self, data):
                raise WebSocketNetworkError

        @contextlib.contextmanager
        def connect():
            yield LostSession()

        stream = ASRRealtimeStream(connect, ASRRealtimeConfig(), endless_audio())
        with pytest.raises(WebSocketError) as exc_info:
            list(stream)
        assert not isinstance(exc_info.value, ASRRealtimeError)
        assert isinstance(exc_info.value.__cause__, WebSocketNetworkError)

    @pytest.mark.parametrize(
        ("status", "error_class"), [(401, AuthenticationError), (402, APIError)]
    )
    def test_refused_upgrade_raises_api_error(self, status, error_class):
        with (
            serving(lambda conn: None, reject_status=status) as (server, client),
            pytest.raises(error_class) as exc_info,
        ):
            list(client.asr.stream_websocket(iter([CHUNK])))
        assert exc_info.value.status == status

    def test_leaving_the_loop_early_closes_the_connection(self):
        with serving(open_ended_script) as (server, client):
            for event in client.asr.stream_websocket(endless_audio()):
                if event.type == "committed":
                    break
            conn = server.stop()  # returns only once the client has gone
        assert conn.close_code == 1000

    def test_context_manager_closes_the_connection(self):
        with serving(open_ended_script) as (server, client):
            with client.asr.stream_websocket(endless_audio()) as stream:
                assert next(stream).type == "session_started"
            conn = server.stop()
            stream.close()  # safe to call again
            assert list(stream) == []
        assert conn.close_code == 1000

    def test_audio_stream_failure_is_raised_and_closes_the_connection(self):
        def audio():
            yield CHUNK
            raise RuntimeError("microphone unplugged")

        with serving(open_ended_script) as (server, client):
            with pytest.raises(RuntimeError, match="microphone unplugged"):
                list(client.asr.stream_websocket(audio()))
            conn = server.stop()
        assert conn.close_code == 1000
        assert [m["type"] for m in conn.received] == ["config", "audio"]

    def test_diarize_parameter_is_sent_in_config(self):
        with serving(transcribe_script) as (server, client):
            list(client.asr.stream_websocket(iter([CHUNK]), diarize=False))
        conn = server.stop()
        assert conn.received[0]["results"] == {"diarize": False}

    def test_early_exit_stops_the_sender_and_closes_the_audio_generator(self):
        closed = threading.Event()

        def audio():
            try:
                while True:
                    yield CHUNK
                    time.sleep(0.01)
            finally:
                closed.set()

        with serving(open_ended_script) as (server, client):
            with client.asr.stream_websocket(audio()) as stream:
                next(stream)
            server.stop()
        assert closed.wait(2)
        assert wait_for_no_sender_threads()

    def test_blocked_audio_stream_is_not_interrupted_but_stops_at_its_next_chunk(
        self,
    ):
        waiting = threading.Event()
        release = threading.Event()
        closed = threading.Event()

        def audio():
            try:
                yield CHUNK
                waiting.set()
                release.wait(10)  # a microphone read that blocks
                yield CHUNK
                yield CHUNK
            finally:
                closed.set()

        with serving(open_ended_script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            for event in stream:
                if event.type == "committed":
                    break
            assert waiting.wait(2)
            stream.close()  # the generator is running in the sender thread
            conn = server.stop()

        # The SDK cannot interrupt the blocked read: the thread is still there.
        assert sender_threads()
        assert not closed.is_set()

        release.set()
        assert closed.wait(2)  # closed by the sender thread at the next chunk
        assert wait_for_no_sender_threads()
        assert [m["type"] for m in conn.received] == ["config", "audio"]

    def test_close_interrupts_a_blocked_write(self):
        """The server stops reading, so the sender blocks in a socket write while
        it holds the link. Closing must not wait for that write."""
        release = threading.Event()
        sent = []

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            release.wait(10)  # read nothing: the client's socket buffer fills up

        def audio():
            while True:
                sent.append(time.monotonic())
                yield b"\x00" * (1 << 20)

        def sender_is_blocked():
            return bool(sent) and time.monotonic() - sent[-1] > 0.3

        with serving(script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            try:
                assert next(stream).type == "session_started"
                deadline = time.monotonic() + 5
                while not sender_is_blocked() and time.monotonic() < deadline:
                    time.sleep(0.05)
                assert sender_is_blocked()

                closing = threading.Thread(target=stream.close, daemon=True)
                started = time.monotonic()
                closing.start()
                closing.join(3)
                assert not closing.is_alive(), "close() is stuck behind the write"
                assert time.monotonic() - started < 2
                assert wait_for_no_sender_threads()
                with pytest.raises(WebSocketError):
                    stream.finalize()
            finally:
                release.set()
            server.stop()

    def test_a_second_thread_cannot_read_while_one_is_reading(self):
        """Two threads never get the same event: Python refuses the second read."""
        finish = threading.Event()

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            finish.wait(10)
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        with serving(script) as (server, client):
            stream = client.asr.stream_websocket(iter(()))
            assert next(stream).type == "session_started"
            first = []
            reader = threading.Thread(target=lambda: first.append(next(stream)))
            reader.start()
            try:
                time.sleep(0.1)  # the reader is now waiting for an event
                with pytest.raises(ValueError, match="already executing"):
                    next(stream)
            finally:
                finish.set()
                reader.join(5)
            assert [event.type for event in first] == ["session_done"]
            server.stop()

    def test_audio_stream_that_is_not_a_generator_is_not_closed(self):
        class Source:
            closed = False

            def __iter__(self):
                return iter([CHUNK])

            def close(self):
                self.closed = True

        source = Source()
        with serving(transcribe_script) as (server, client):
            list(client.asr.stream_websocket(source))
        server.stop()
        assert wait_for_no_sender_threads()
        assert source.closed is False

    def test_failing_generator_cleanup_does_not_reach_the_consumer(self):
        def audio():
            try:
                while True:
                    yield CHUNK
                    time.sleep(0.01)
            finally:
                raise RuntimeError("cleanup failed")

        with serving(open_ended_script) as (server, client):
            with client.asr.stream_websocket(audio()) as stream:
                next(stream)
            server.stop()
        assert wait_for_no_sender_threads()


class TestAsyncSession:
    async def test_streams_audio_and_yields_typed_events(self):
        async with aserving(transcribe_script) as (server, client):
            events = [
                event
                async for event in client.asr.stream_websocket(
                    aiter_chunks(CHUNK, b"", CHUNK), sample_rate=16000, drafts=True
                )
            ]
            conn = await astop(server)

        assert [event.type for event in events] == [
            "session_started",
            "speech_start",
            "draft",
            "committed",
            "session_done",
        ]
        assert events[3].text == "What's the weather like?"
        assert conn.path == "/v1/asr/realtime"
        assert conn.headers["authorization"] == "Bearer test-key"
        assert conn.headers["model"] == "transcribe-stream-1"
        assert conn.received == [
            {
                "type": "config",
                "audio": {"format": "pcm_s16le", "sample_rate": 16000, "channels": 1},
                "results": {"drafts": True},
            },
            {"type": "audio", "data": CHUNK},
            {"type": "audio", "data": CHUNK},
            {"type": "audio_done"},
        ]
        assert conn.close_code == 1000

    async def test_control_messages_in_the_audio_stream_keep_their_position(self):
        async with aserving(transcribe_script) as (server, client):
            async for _ in client.asr.stream_websocket(
                aiter_chunks(CHUNK, ASRFinalizeEvent(), CHUNK)
            ):
                pass
            conn = await astop(server)
        assert [m["type"] for m in conn.received[1:]] == [
            "audio",
            "finalize",
            "audio",
            "audio_done",
        ]

    async def test_control_methods_send_during_the_session(self):
        release = asyncio.Event()

        async def audio():
            yield CHUNK
            await asyncio.wait_for(release.wait(), 5)

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(COMMITTED)
            conn.recv_until("audio_done")
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            with pytest.raises(WebSocketError, match="not open"):
                await stream.finalize()
            async for event in stream:
                if event.type == "committed":
                    await stream.agent_speaking(True)
                    await stream.add_context(
                        [ASRContextItem(role="assistant", text="Hi.")]
                    )
                    await stream.configure(results=ASRResults(drafts=True))
                    await stream.finalize()
                    await stream.keepalive()
                    release.set()
            with pytest.raises(WebSocketError, match="not open"):
                await stream.finalize()
            conn = await astop(server)

        control = [m for m in conn.received[1:] if m["type"] != "audio"]
        assert control == [
            {"type": "agent_speaking", "speaking": True},
            {
                "type": "context_add",
                "items": [{"role": "assistant", "text": "Hi."}],
                "reset_history": False,
            },
            {"type": "configure", "results": {"drafts": True}},
            {"type": "finalize"},
            {"type": "keepalive"},
            {"type": "audio_done"},
        ]

    async def test_recoverable_error_is_an_event_and_the_session_continues(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(error_message("invalid_request", recoverable=True))
            conn.recv_until("audio_done")
            conn.send(SESSION_DONE)
            conn.close(1000, "done")

        async with aserving(script) as (server, client):
            events = [
                event
                async for event in client.asr.stream_websocket(aiter_chunks(CHUNK))
            ]
            await astop(server)
        assert [event.type for event in events] == [
            "session_started",
            "error",
            "session_done",
        ]

    async def test_fatal_error_event_raises(self):
        def script(conn):
            conn.recv()
            conn.send(error_message("invalid_config", recoverable=False))
            conn.close(4400, "invalid_config")

        async with aserving(script) as (server, client):
            with pytest.raises(ASRRealtimeError) as exc_info:
                async for _ in client.asr.stream_websocket(aiter_chunks(CHUNK)):
                    pass
            conn = await astop(server)
        assert exc_info.value.error_type == "invalid_config"
        assert exc_info.value.code == 400
        assert [m["type"] for m in conn.received] == ["config"]
        assert conn.close_code is not None

    async def test_server_restarting_yields_the_error_then_raises_with_close_code(
        self,
    ):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.send(error_message("server_restarting", recoverable=True, code=503))
            conn.close(1012, "restarting")

        events = []
        async with aserving(script) as (server, client):
            with pytest.raises(ASRRealtimeError) as exc_info:
                async for event in client.asr.stream_websocket(aendless_audio()):
                    events.append(event)
            await astop(server)
        assert [event.type for event in events] == ["session_started", "error"]
        assert exc_info.value.close_code == 1012
        assert exc_info.value.error_type == "server_restarting"

    async def test_dropped_connection_raises_websocket_error(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.drop()

        async with aserving(script) as (server, client):
            with pytest.raises(WebSocketError):
                async for _ in client.asr.stream_websocket(aendless_audio()):
                    pass
            await astop(server)

    async def test_connection_lost_while_sending_config_raises_websocket_error(self):
        """A network failure on the first frame is a WebSocketError, not httpx-ws's own."""

        class LostSession:
            async def send_bytes(self, data):
                raise WebSocketNetworkError

        @contextlib.asynccontextmanager
        async def connect():
            yield LostSession()

        stream = AsyncASRRealtimeStream(connect, ASRRealtimeConfig(), aendless_audio())
        with pytest.raises(WebSocketError) as exc_info:
            async for _ in stream:
                pass
        assert not isinstance(exc_info.value, ASRRealtimeError)
        assert isinstance(exc_info.value.__cause__, WebSocketNetworkError)

    @pytest.mark.parametrize(
        ("status", "error_class"), [(401, AuthenticationError), (402, APIError)]
    )
    async def test_refused_upgrade_raises_api_error(self, status, error_class):
        async with aserving(lambda conn: None, reject_status=status) as (_, client):
            with pytest.raises(error_class) as exc_info:
                async for _ in client.asr.stream_websocket(aiter_chunks(CHUNK)):
                    pass
        assert exc_info.value.status == status

    async def test_leaving_the_loop_early_closes_the_connection(self):
        async with aserving(open_ended_script) as (server, client):
            async for event in client.asr.stream_websocket(aendless_audio()):
                if event.type == "committed":
                    break
            conn = await astop(server)  # returns only once the client has gone
        assert conn.close_code == 1000

    async def test_context_manager_closes_the_connection(self):
        async with aserving(open_ended_script) as (server, client):
            async with client.asr.stream_websocket(aendless_audio()) as stream:
                assert (await stream.__anext__()).type == "session_started"
            conn = await astop(server)
            await stream.aclose()  # safe to call again
            assert [event async for event in stream] == []
        assert conn.close_code == 1000

    async def test_audio_stream_failure_is_raised_and_closes_the_connection(self):
        async def audio():
            yield CHUNK
            raise RuntimeError("microphone unplugged")

        async with aserving(open_ended_script) as (server, client):
            with pytest.raises(RuntimeError, match="microphone unplugged"):
                async for _ in client.asr.stream_websocket(audio()):
                    pass
            conn = await astop(server)
        assert conn.close_code == 1000
        assert [m["type"] for m in conn.received] == ["config", "audio"]

    async def test_diarize_parameter_is_sent_in_config(self):
        async with aserving(transcribe_script) as (server, client):
            async for _ in client.asr.stream_websocket(
                aiter_chunks(CHUNK), diarize=False
            ):
                pass
            conn = await astop(server)
        assert conn.received[0]["results"] == {"diarize": False}

    async def test_closing_closes_the_audio_generator(self):
        closed = asyncio.Event()

        async def audio():
            try:
                while True:
                    yield CHUNK
                    await asyncio.sleep(0.01)
            finally:
                closed.set()

        async with aserving(open_ended_script) as (server, client):
            async with client.asr.stream_websocket(audio()) as stream:
                await stream.__anext__()
            assert closed.is_set()  # already closed when aclose() returns
            await astop(server)

    async def test_audio_failure_is_not_delayed_by_a_steady_stream_of_events(self):
        async def audio():
            yield CHUNK
            raise RuntimeError("microphone unplugged")

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv()
            with contextlib.suppress(OSError):  # the client leaves before the end
                for seq in range(200):
                    conn.send({**DRAFT, "seq": seq})
                    time.sleep(0.01)

        async with aserving(script) as (server, client):
            started = time.monotonic()
            with pytest.raises(RuntimeError, match="microphone unplugged"):
                async for _ in client.asr.stream_websocket(audio()):
                    pass
            assert time.monotonic() - started < 1.0
            await astop(server)

    async def test_audio_failure_is_raised_when_the_server_closes_normally(
        self, monkeypatch
    ):
        # As in the sync test: close only once the sender task has failed. The
        # task is done in the same event-loop step that sets the flag.
        sender_ended = threading.Event()
        asend_audio = asr_realtime._asend_audio

        async def asend_audio_then_signal(*args):
            try:
                await asend_audio(*args)
            finally:
                sender_ended.set()

        monkeypatch.setattr(asr_realtime, "_asend_audio", asend_audio_then_signal)

        async def audio():
            yield CHUNK
            await asyncio.sleep(0.05)  # the failure comes well after the chunk
            raise RuntimeError("microphone unplugged")

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv()  # the one audio chunk
            assert sender_ended.wait(5)
            conn.close(1000, "bye")

        async with aserving(script) as (server, client):
            with pytest.raises(RuntimeError, match="microphone unplugged"):
                async for _ in client.asr.stream_websocket(audio()):
                    pass
            await astop(server)

    async def test_audio_stream_cleanup_that_never_finishes_does_not_hang_the_session(
        self, monkeypatch
    ):
        monkeypatch.setattr(asr_realtime, "_SENDER_CLEANUP_SECONDS", 0.05)
        release = asyncio.Event()

        async def audio():
            try:
                while True:
                    yield CHUNK
                    await asyncio.sleep(0.01)
            finally:
                await release.wait()  # cleanup that does not finish

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv()  # the first audio chunk
            conn.close(1011, "boom")

        async def read_all(stream):
            async for _ in stream:
                pass

        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            with pytest.raises(ASRRealtimeError) as exc_info:
                await asyncio.wait_for(read_all(stream), 2)
            assert exc_info.value.close_code == 1011
            await astop(server)  # the connection was closed, not left open

            release.set()  # let the abandoned cleanup finish
            await asyncio.sleep(0.05)

    async def test_aclose_from_another_task_wakes_a_waiting_consumer(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.wait_gone()  # no more events: the consumer blocks in __anext__

        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(aendless_audio())

            async def consume():
                return [event.type async for event in stream]

            consumer = asyncio.create_task(consume())
            await asyncio.sleep(0.3)  # session_started received, now waiting
            await asyncio.wait_for(stream.aclose(), 2)

            assert await asyncio.wait_for(consumer, 2) == ["session_started"]
            await astop(server)

    async def test_cancelled_audio_stream_ends_the_session_with_an_error(self):
        async def audio():
            yield CHUNK
            cancelled = asyncio.get_running_loop().create_future()
            cancelled.cancel()
            await (
                cancelled
            )  # e.g. the capture task this iterator waits on was cancelled

        async def consume(stream):
            async for _ in stream:
                pass

        async with aserving(open_ended_script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            with pytest.raises(WebSocketError, match="cancelled"):
                await asyncio.wait_for(consume(stream), 3)
            conn = await astop(server)
        assert conn.close_code == 1000

    async def test_slow_consumer_gets_backpressure_instead_of_unbounded_buffering(
        self,
    ):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            for seq in range(1, 601):
                conn.send({**DRAFT, "seq": seq})

        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(aendless_audio())
            assert (await stream.__anext__()).type == "session_started"
            await asyncio.sleep(0.5)  # the consumer stops reading

            assert stream._events.maxsize == asr_realtime._EVENT_QUEUE_SIZE
            assert stream._events.qsize() == asr_realtime._EVENT_QUEUE_SIZE

            # The session task is waiting on the full queue: closing must still work.
            await asyncio.wait_for(stream.aclose(), 2)
            assert stream._task.done()
            await astop(server)

    async def test_events_and_final_error_are_delivered_through_a_full_queue(
        self, monkeypatch
    ):
        monkeypatch.setattr(asr_realtime, "_EVENT_QUEUE_SIZE", 2)

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            for seq in range(1, 6):
                conn.send({**DRAFT, "seq": seq})
            conn.close(1011, "boom")

        events = []
        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(aendless_audio())
            events.append(await stream.__anext__())
            await asyncio.sleep(0.3)  # let the queue fill up
            assert stream._events.qsize() == 2
            with pytest.raises(ASRRealtimeError) as exc_info:
                async for event in stream:
                    events.append(event)
            await astop(server)
        assert [event.seq for event in events] == [0, 1, 2, 3, 4, 5]
        assert exc_info.value.close_code == 1011

    async def test_leaving_the_loop_with_a_full_queue_closes_the_connection(
        self, monkeypatch
    ):
        monkeypatch.setattr(asr_realtime, "_EVENT_QUEUE_SIZE", 1)

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            for seq in range(1, 6):
                conn.send({**DRAFT, "seq": seq})

        async with aserving(script) as (server, client):
            async for _ in client.asr.stream_websocket(aendless_audio()):
                await asyncio.sleep(0.2)  # the session task blocks on the queue
                break
            await astop(server)  # returns only once the client has gone

    async def test_cancelled_read_does_not_lose_the_event_it_had_taken(self):
        """A read cancelled after it took an event from the queue (for example by
        asyncio.wait_for) must hand that event to the next read."""

        async def read_cancelled_after(steps, marker):
            read = asyncio.ensure_future(stream.__anext__())
            await asyncio.sleep(0)  # the read is now waiting for an event
            stream._events.put_nowait(marker)
            for _ in range(steps):  # let the read get this far before cancelling
                await asyncio.sleep(0)
            read.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                return await read
            return await asyncio.wait_for(stream.__anext__(), 1)

        async with aserving(open_ended_script) as (server, client):
            async with client.asr.stream_websocket(aendless_audio()) as stream:
                assert (await stream.__anext__()).type == "session_started"
                assert (await stream.__anext__()).type == "committed"

                # Cancel at every point between "event queued" and "read returned".
                received = []
                for steps in range(8):
                    marker = ASRDraftEvent(turn_index=0, text="marker", seq=steps)
                    received.append(await read_cancelled_after(steps, marker))
            await astop(server)
        assert [event.seq for event in received] == list(range(8))

    async def test_reading_with_timeouts_delivers_every_event_in_order(self):
        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            conn.recv_until("audio_done")
            for seq in range(1, 61):
                conn.send({**DRAFT, "seq": seq})
                time.sleep(0.003)
            conn.send({**SESSION_DONE, "seq": 61})
            conn.close(1000, "done")

        seqs = []
        timeouts = 0
        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(aiter_chunks(CHUNK))
            while True:
                try:
                    event = await asyncio.wait_for(stream.__anext__(), 0.002)
                except asyncio.TimeoutError:
                    timeouts += 1
                    continue
                except StopAsyncIteration:
                    break
                seqs.append(event.seq)
            await astop(server)
        assert seqs == list(range(62))
        assert timeouts > 0  # the reads really were interrupted

    async def test_closing_after_a_cancelled_read_leaves_no_pending_task(self):
        async with aserving(open_ended_script) as (server, client):
            stream = client.asr.stream_websocket(aendless_audio())
            assert (await stream.__anext__()).type == "session_started"
            assert (await stream.__anext__()).type == "committed"
            with pytest.raises(asyncio.TimeoutError):  # nothing more is coming
                await asyncio.wait_for(stream.__anext__(), 0.05)

            await stream.aclose()
            await stream.aclose()  # safe to call again
            await asyncio.sleep(0)  # let cancelled tasks finish
            pending = [
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task() and not task.done()
            ]
            assert pending == []
            assert [event async for event in stream] == []
            await astop(server)

    async def test_concurrent_reads_do_not_deliver_an_event_twice(self):
        async with aserving(open_ended_script) as (server, client):
            async with client.asr.stream_websocket(aendless_audio()) as stream:
                assert (await stream.__anext__()).type == "session_started"
                assert (await stream.__anext__()).type == "committed"

                first = asyncio.ensure_future(stream.__anext__())
                await asyncio.sleep(0)  # the first read is now waiting
                second = asyncio.ensure_future(stream.__anext__())
                await asyncio.sleep(0)
                stream._events.put_nowait(ASRDraftEvent(turn_index=0, text="once"))
                done, pending = await asyncio.wait({first, second}, timeout=0.5)
                for read in pending:
                    read.cancel()

                delivered = [r.result() for r in done if r.exception() is None]
                assert [event.text for event in delivered] == ["once"]
                assert first in done and first.exception() is None
                with pytest.raises(RuntimeError, match="already waiting"):
                    await second
                # The refused read took nothing and broke nothing.
                stream._events.put_nowait(ASRDraftEvent(turn_index=0, text="next"))
                assert (await asyncio.wait_for(stream.__anext__(), 1)).text == "next"
            await astop(server)

    async def test_aclose_interrupts_a_blocked_write(self):
        release = threading.Event()
        sent = []

        def script(conn):
            conn.recv()
            conn.send(SESSION_STARTED)
            release.wait(10)  # read nothing: the client's socket buffer fills up

        async def audio():
            while True:
                sent.append(time.monotonic())
                yield b"\x00" * (1 << 20)

        def sender_is_blocked():
            return bool(sent) and time.monotonic() - sent[-1] > 0.3

        async with aserving(script) as (server, client):
            stream = client.asr.stream_websocket(audio())
            try:
                assert (await stream.__anext__()).type == "session_started"
                deadline = time.monotonic() + 5
                while not sender_is_blocked() and time.monotonic() < deadline:
                    await asyncio.sleep(0.05)
                assert sender_is_blocked()
                await asyncio.wait_for(stream.aclose(), 2)
            finally:
                release.set()
            await astop(server)
