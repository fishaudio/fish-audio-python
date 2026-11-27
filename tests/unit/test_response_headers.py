"""What an accepted call returns carries the headers of its response.

The HTTP tests run the real client against a local HTTP server; the realtime
tests run it against the scripted WebSocket server in realtime_server.py.
"""

import base64
import contextlib
import json
import pickle
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from fishaudio import ASRRealtimeError, AsyncFishAudio, FishAudio
from fishaudio.types import ASRResponse, TTSTimestampResult

from .realtime_server import RealtimeServer
from .test_asr_realtime import (
    CHUNK,
    aiter_chunks,
    astop,
    error_message,
    transcribe_script,
)

SSE_EVENT = (
    "event: message\r\ndata: "
    + json.dumps(
        {
            "audio_base64": base64.b64encode(b"audio").decode(),
            "content": "Hello",
            "alignment": None,
            "chunk_seq": 0,
            "chunk_audio_offset_sec": 0.0,
        }
    )
    + "\r\n\r\n"
).encode()
ASR_BODY = b'{"text":"Hello","duration":1.5,"segments":[],"request_id":"req-123"}'


class _Accept(BaseHTTPRequestHandler):
    """200 on every path, with x-fish-trace-id: trace-<n> for the n-th call."""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        server = self.server
        with server.lock:
            server.calls += 1
            call = server.calls
        if self.path == "/v1/asr":
            body = ASR_BODY
        elif self.path.endswith("/with-timestamp"):
            body = SSE_EVENT
        else:
            body = b"audio"
        self.send_response(200)
        if server.send_trace_id:
            self.send_header("x-fish-trace-id", f"trace-{call}")
        # A broken stream promises more bytes than it sends.
        length = 1000 if server.break_stream else len(body)
        self.send_header("content-length", str(length))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def accepting_server(*, send_trace_id=True, break_stream=False):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Accept)
    server.daemon_threads = True
    server.lock = threading.Lock()
    server.calls = 0
    server.send_trace_id = send_trace_id
    server.break_stream = break_stream
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class TestHTTPStreams:
    def test_headers_are_there_before_and_after_the_body_is_read(self):
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            stream = client.tts.stream(text="hi")
            assert stream.headers["x-fish-trace-id"] == "trace-1"
            assert stream.collect() == b"audio"
            assert stream.headers["X-Fish-Trace-Id"] == "trace-1"  # any casing

    async def test_headers_are_there_before_and_after_the_body_is_read_async(self):
        with accepting_server() as url:
            async with AsyncFishAudio(api_key="k", base_url=url) as client:
                stream = await client.tts.stream(text="hi")
                assert stream.headers["x-fish-trace-id"] == "trace-1"
                assert await stream.collect() == b"audio"
                assert stream.headers["x-fish-trace-id"] == "trace-1"

    def test_a_stream_that_breaks_midway_keeps_its_headers(self):
        with (
            accepting_server(break_stream=True) as url,
            FishAudio(api_key="k", base_url=url) as client,
        ):
            stream = client.tts.stream(text="hi")
            with pytest.raises(httpx.RemoteProtocolError):
                stream.collect()
            assert stream.headers["x-fish-trace-id"] == "trace-1"

    def test_a_stream_closed_before_iteration_keeps_its_headers(self):
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            stream = client.tts.stream(text="hi")
            stream.close()
            assert stream.headers["x-fish-trace-id"] == "trace-1"

    def test_two_open_streams_each_have_their_own_headers(self):
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            first = client.tts.stream(text="one")
            second = client.tts.stream(text="two")
            assert first.headers["x-fish-trace-id"] == "trace-1"
            assert second.headers["x-fish-trace-id"] == "trace-2"
            first.close()
            second.close()

    def test_a_header_the_response_does_not_have_is_absent(self):
        with (
            accepting_server(send_trace_id=False) as url,
            FishAudio(api_key="k", base_url=url) as client,
            client.tts.stream(text="hi") as stream,
        ):
            assert stream.headers.get("x-fish-trace-id") is None

    def test_timestamp_stream_and_its_result_carry_the_headers(self):
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            stream = client.tts.stream_with_timestamps(text="hi")
            assert stream.headers["x-fish-trace-id"] == "trace-1"
            result = stream.collect()
            assert result.audio == b"audio"
            assert result.headers["x-fish-trace-id"] == "trace-1"

            result = client.tts.convert_with_timestamps(text="hi")
            assert result.headers["x-fish-trace-id"] == "trace-2"

    async def test_timestamp_stream_and_its_result_carry_the_headers_async(self):
        with accepting_server() as url:
            async with AsyncFishAudio(api_key="k", base_url=url) as client:
                stream = await client.tts.stream_with_timestamps(text="hi")
                assert stream.headers["x-fish-trace-id"] == "trace-1"
                result = await stream.collect()
                assert result.headers["x-fish-trace-id"] == "trace-1"


class TestResults:
    def test_transcription_carries_the_headers_and_the_request_id(self):
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            result = client.asr.transcribe(audio=b"audio")
        assert result.request_id == "req-123"
        assert result.headers["x-fish-trace-id"] == "trace-1"

    async def test_transcription_carries_the_headers_async(self):
        with accepting_server() as url:
            async with AsyncFishAudio(api_key="k", base_url=url) as client:
                result = await client.asr.transcribe(audio=b"audio")
        assert result.headers["x-fish-trace-id"] == "trace-1"

    def test_headers_are_not_part_of_the_model(self):
        """They stay out of equality, model_dump() and the schema.

        A copy and a pickle round trip keep them, and still equal the plain model.
        """
        with accepting_server() as url, FishAudio(api_key="k", base_url=url) as client:
            asr = client.asr.transcribe(audio=b"audio")
            timed = client.tts.convert_with_timestamps(text="hi")
        plain_asr = ASRResponse.model_validate(json.loads(ASR_BODY))
        plain_timed = TTSTimestampResult(audio=b"audio", segments=[])

        for result, plain in ((asr, plain_asr), (timed, plain_timed)):
            assert result.headers["x-fish-trace-id"].startswith("trace-")
            assert result == plain
            assert result.model_dump() == plain.model_dump()
            assert "headers" not in result.model_dump_json()
            for clone in (result.model_copy(), pickle.loads(pickle.dumps(result))):
                assert clone == plain
                assert clone.headers == result.headers
            assert type(result).model_json_schema() == type(plain).model_json_schema()

    def test_a_model_you_build_yourself_has_empty_headers(self):
        result = TTSTimestampResult(audio=b"audio", segments=[])
        assert result.headers.get("x-fish-trace-id") is None


class TestRealtime:
    def test_handshake_headers_once_connected_and_after_the_session(self):
        server = RealtimeServer(transcribe_script)
        with FishAudio(api_key="k", base_url=server.url) as client:
            stream = client.asr.stream_websocket(iter([CHUNK]))
            # The connection opens on the first iteration.
            assert stream.headers.get("x-fish-trace-id") is None
            first = next(stream)
            assert first.type == "session_started"
            assert stream.headers["x-fish-trace-id"] == "trace-123"
            list(stream)
            assert stream.headers["x-fish-trace-id"] == "trace-123"
        server.stop()

    def test_a_stream_closed_before_iteration_has_no_headers(self):
        server = RealtimeServer(transcribe_script)
        with FishAudio(api_key="k", base_url=server.url) as client:
            stream = client.asr.stream_websocket(iter([CHUNK]))
            stream.close()
            assert len(stream.headers) == 0
        server.close()

    def test_a_session_that_fails_after_it_opened_keeps_its_headers(self):
        def script(conn):
            conn.recv()
            conn.send(error_message("internal_error", recoverable=False, code=500))
            conn.close(1011, "internal_error")

        server = RealtimeServer(script)
        with FishAudio(api_key="k", base_url=server.url) as client:
            stream = client.asr.stream_websocket(iter([CHUNK]))
            with pytest.raises(ASRRealtimeError):
                list(stream)
            assert stream.headers["x-fish-trace-id"] == "trace-123"
        server.stop()

    async def test_handshake_headers_once_connected_and_after_the_session_async(self):
        server = RealtimeServer(transcribe_script)
        async with AsyncFishAudio(api_key="k", base_url=server.url) as client:
            stream = client.asr.stream_websocket(aiter_chunks(CHUNK))
            assert stream.headers.get("x-fish-trace-id") is None
            first = await stream.__anext__()
            assert first.type == "session_started"
            assert stream.headers["x-fish-trace-id"] == "trace-123"
            async for _ in stream:
                pass
            assert stream.headers["x-fish-trace-id"] == "trace-123"
        await astop(server)
