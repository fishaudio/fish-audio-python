"""The SDK sends ``User-Agent: fish-audio-python/<version>`` on every path."""

from __future__ import annotations

import base64
import contextlib
import json
import platform
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from fishaudio import AsyncFishAudio, FishAudio, __version__
from fishaudio.core import AsyncClientWrapper, ClientWrapper, RequestOptions
from fishaudio.core.client_wrapper import (
    PRODUCT,
    USER_AGENT,
    _comment_value,
    _os_family,
    build_user_agent,
    user_agent,
)
from fishaudio.exceptions import APIError

from .realtime_server import RealtimeServer

if TYPE_CHECKING:
    from collections.abc import Iterator

# RFC 9110 section 5.6.2: tchar; a product is token ["/" product-version].
TCHAR = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]"
PRODUCT_GRAMMAR = re.compile(rf"^{TCHAR}+/{TCHAR}+$")
# product, then one or more comments with nothing RFC 9110 ctext excludes.
USER_AGENT_GRAMMAR = re.compile(rf"^{TCHAR}+/{TCHAR}+( \([^()\\\x00-\x1f\x7f]*\))+$")


class TestFormat:
    def test_product_is_fish_audio_python_and_the_version(self):
        assert f"fish-audio-python/{__version__}" == PRODUCT

    def test_product_is_valid_rfc_9110_grammar(self):
        assert PRODUCT_GRAMMAR.match(PRODUCT), PRODUCT

    def test_user_agent_names_python_its_version_and_the_os(self):
        expected_os = _os_family(sys.platform)
        assert (
            f"{PRODUCT} (python {platform.python_version()}; {expected_os})"
        ) == USER_AGENT
        assert USER_AGENT_GRAMMAR.match(USER_AGENT), USER_AGENT

    def test_version_matches_pyproject(self):
        pyproject = (Path(__file__).parents[2] / "pyproject.toml").read_text()
        match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
        assert match is not None
        assert __version__ == match.group(1)


class TestRuntimeComment:
    def test_shape(self):
        assert (
            build_user_agent("3.12.1", "linux") == f"{PRODUCT} (python 3.12.1; linux)"
        )

    @pytest.mark.parametrize(
        ("sys_platform", "expected"),
        [
            ("linux", "linux"),
            ("darwin", "darwin"),
            ("win32", "windows"),
            ("cygwin", "windows"),
            ("freebsd14", "freebsd"),
            ("Emscripten", "emscripten"),
            (None, "unknown"),
            ("", "unknown"),
        ],
    )
    def test_os_family(self, sys_platform, expected):
        assert _os_family(sys_platform) == expected

    @pytest.mark.parametrize(
        "hostile",
        [
            "3.12.1 (evil)",
            "3.12.1)",
            "3.12.1\\(",
            "3.12.1\r\nX-Injected: 1",
            "3.12.1\x00",
            "3.12.1; host=alice-laptop",
            "3.12.1 /home/alice",
        ],
    )
    def test_odd_values_are_cut_to_their_safe_prefix(self, hostile):
        assert _comment_value(hostile) == "3.12.1"
        assert USER_AGENT_GRAMMAR.match(build_user_agent(hostile, hostile))

    def test_nothing_usable_becomes_unknown(self):
        assert _comment_value("(x)") == "unknown"
        assert _comment_value("\\") == "unknown"
        assert _comment_value("") == "unknown"
        assert _comment_value(None) == "unknown"
        assert _comment_value("1" * 100) == "1" * 32


class TestUserAgentValue:
    def test_alone(self):
        assert user_agent() == USER_AGENT
        assert user_agent("   ") == USER_AGENT

    def test_caller_value_is_appended(self):
        assert user_agent("my-app/1.0") == f"{USER_AGENT} my-app/1.0"

    def test_not_doubled(self):
        assert user_agent(USER_AGENT) == USER_AGENT
        assert user_agent(f"{USER_AGENT} my-app/1.0") == f"{USER_AGENT} my-app/1.0"


class TestGetHeaders:
    def test_additional_user_agent_of_any_casing_is_appended_once(self):
        headers = ClientWrapper(api_key="k").get_headers({"user-agent": "my-app/1.0"})
        names = [name for name in headers if name.lower() == "user-agent"]
        assert names == ["User-Agent"]
        assert headers["User-Agent"] == f"{USER_AGENT} my-app/1.0"

    def test_user_agent_of_a_user_httpx_client_is_appended(self):
        client = httpx.Client(headers={"User-Agent": "my-app/1.0"})
        wrapper = ClientWrapper(api_key="k", httpx_client=client)
        assert wrapper.get_headers()["User-Agent"] == f"{USER_AGENT} my-app/1.0"
        # A request option replaces the client's value.
        headers = wrapper.get_headers({"User-Agent": "my-script/2.0"})
        assert headers["User-Agent"] == f"{USER_AGENT} my-script/2.0"

    def test_httpx_default_user_agent_is_not_appended(self):
        wrapper = ClientWrapper(api_key="k", httpx_client=httpx.Client())
        assert wrapper.get_headers()["User-Agent"] == USER_AGENT

    def test_customised_value_starting_with_httpx_product_is_kept(self):
        client = httpx.Client(
            headers={"User-Agent": f"python-httpx/{httpx.__version__} my-app/1.0"}
        )
        wrapper = ClientWrapper(api_key="k", httpx_client=client)
        assert wrapper.get_headers()["User-Agent"] == (
            f"{USER_AGENT} python-httpx/{httpx.__version__} my-app/1.0"
        )

    def test_user_agent_changed_on_the_client_after_construction_is_used(self):
        client = httpx.Client()
        wrapper = ClientWrapper(api_key="k", httpx_client=client)
        assert wrapper.get_headers()["User-Agent"] == USER_AGENT
        client.headers["User-Agent"] = "my-app/2.0"
        assert wrapper.get_headers()["User-Agent"] == f"{USER_AGENT} my-app/2.0"
        del client.headers["User-Agent"]
        assert wrapper.get_headers()["User-Agent"] == USER_AGENT

    async def test_async_wrapper_reads_the_client_user_agent_too(self):
        client = httpx.AsyncClient()
        wrapper = AsyncClientWrapper(api_key="k", httpx_client=client)
        client.headers["User-Agent"] = "my-app/2.0"
        assert wrapper.get_headers()["User-Agent"] == f"{USER_AGENT} my-app/2.0"
        await client.aclose()

    def test_sdk_own_client_does_not_double_the_product(self):
        wrapper = ClientWrapper(api_key="k")
        assert wrapper.client.headers["User-Agent"] == USER_AGENT
        assert wrapper.get_headers()["User-Agent"] == USER_AGENT


class _Recorder(BaseHTTPRequestHandler):
    """Records each request's User-Agent values and answers with ``status``."""

    seen: list[tuple[str, str, list[str]]]
    status = 200

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        type(self).seen.append(
            (self.command, self.path, self.headers.get_all("User-Agent") or [])
        )
        if self.path.startswith("/v1/tts/stream/with-timestamp") and self.status == 200:
            payload = {
                "audio_base64": base64.b64encode(b"\x01").decode(),
                "content": "hi",
                "alignment": None,
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
            }
            body = f"event: message\r\ndata: {json.dumps(payload)}\r\n\r\n".encode()
            content_type = "text/event-stream"
        elif self.path.startswith("/v1/tts") and self.status == 200:
            body, content_type = b"\x01\x02", "audio/mpeg"
        elif self.path.startswith("/model") and self.command == "GET":
            body, content_type = b'{"items": [], "total": 0}', "application/json"
        elif self.path.startswith("/v1/asr"):
            body, content_type = (
                b'{"text": "", "duration": 0, "segments": []}',
                "application/json",
            )
        else:
            body, content_type = (
                b'{"_id": "c", "user_id": "u", "credit": "1",'
                b' "created_at": "2026-01-01", "updated_at": "2026-01-01"}',
                "application/json",
            )
        if self.status != 200:
            body, content_type = b'{"message": "nope"}', "application/json"
        self.send_response(self.status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PATCH = do_DELETE = _answer

    def log_message(self, *args):  # silence
        pass


@contextlib.contextmanager
def recording_server(status: int = 200) -> Iterator[tuple[str, list]]:
    handler = type("Handler", (_Recorder,), {"seen": [], "status": status})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler.seen
    finally:
        server.shutdown()
        server.server_close()


class TestHTTP:
    def test_every_endpoint_type_sends_it_once(self):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            client.account.get_credits()
            client.voices.list()
            client.tts.convert(text="hi")
            client.asr.transcribe(audio=b"\x00\x01")
            client.close()
        assert len(seen) == 4
        for method, path, values in seen:
            assert values == [USER_AGENT], f"{method} {path}"

    def test_timestamps_entry_points_send_it(self):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            client.tts.convert_with_timestamps(text="hi")
            client.tts.stream_with_timestamps(text="hi").collect()
            client.close()
        assert [(m, p, v) for m, p, v in seen] == [
            ("POST", "/v1/tts/stream/with-timestamp", [USER_AGENT]),
            ("POST", "/v1/tts/stream/with-timestamp", [USER_AGENT]),
        ]

    async def test_async_timestamps_entry_points_send_it(self):
        with recording_server() as (url, seen):
            client = AsyncFishAudio(api_key="test-key", base_url=url)
            await client.tts.convert_with_timestamps(text="hi")
            stream = await client.tts.stream_with_timestamps(text="hi")
            await stream.collect()
            await client.close()
        assert [v for _, _, v in seen] == [[USER_AGENT], [USER_AGENT]]

    def test_request_options_user_agent_is_appended(self):
        with recording_server() as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            client.account.get_credits(
                request_options=RequestOptions(
                    additional_headers={"user-agent": "my-app/1.0"}
                )
            )
            client.close()
        assert seen[0][2] == [f"{USER_AGENT} my-app/1.0"]

    def test_user_httpx_client_user_agent_is_appended(self):
        with recording_server() as (url, seen):
            own = httpx.Client(base_url=url, headers={"User-Agent": "my-app/1.0"})
            client = FishAudio(api_key="test-key", httpx_client=own)
            client.account.get_credits()
            own.close()
        assert seen[0][2] == [f"{USER_AGENT} my-app/1.0"]

    def test_a_failing_request_sent_it_and_still_raises(self):
        with recording_server(status=500) as (url, seen):
            client = FishAudio(api_key="test-key", base_url=url)
            with pytest.raises(APIError):
                client.account.get_credits()
            client.close()
        assert seen[0][2] == [USER_AGENT]

    async def test_async_client_sends_it(self):
        with recording_server() as (url, seen):
            client = AsyncFishAudio(api_key="test-key", base_url=url)
            await client.account.get_credits()
            await client.voices.list()
            await client.close()
        assert [values for _, _, values in seen] == [[USER_AGENT], [USER_AGENT]]


@contextlib.contextmanager
def refusing_ws_server() -> Iterator[RealtimeServer]:
    """A WebSocket server that records the handshake and refuses it with 401."""
    server = RealtimeServer(lambda conn: None, reject_status=401)
    try:
        yield server
    finally:
        server.close()


class TestWebSockets:
    def test_tts_websocket_handshake(self):
        with refusing_ws_server() as server:
            client = FishAudio(api_key="test-key", base_url=server.url)
            with pytest.raises(Exception):
                for _ in client.tts.stream_websocket(iter(["hi"])):
                    pass
            client.close()
            conn = server.stop()
        assert conn.path == "/v1/tts/live"
        assert conn.headers["user-agent"] == USER_AGENT

    async def test_async_tts_websocket_handshake(self):
        with refusing_ws_server() as server:
            client = AsyncFishAudio(api_key="test-key", base_url=server.url)

            async def text():
                yield "hi"

            with pytest.raises(Exception):
                async for _ in client.tts.stream_websocket(text()):
                    pass
            await client.close()
            conn = server.stop()
        assert conn.headers["user-agent"] == USER_AGENT

    def test_asr_realtime_handshake_with_a_client_user_agent(self):
        with refusing_ws_server() as server:
            own = httpx.Client(base_url=server.url, headers={"User-Agent": "app/2"})
            client = FishAudio(api_key="test-key", httpx_client=own)
            with pytest.raises(Exception):
                for _ in client.asr.stream_websocket(iter([b"\x00\x00"])):
                    pass
            own.close()
            conn = server.stop()
        assert conn.path == "/v1/asr/realtime"
        assert conn.headers["user-agent"] == f"{USER_AGENT} app/2"

    async def test_async_asr_realtime_handshake(self):
        with refusing_ws_server() as server:
            client = AsyncFishAudio(api_key="test-key", base_url=server.url)

            async def audio():
                yield b"\x00\x00"

            with pytest.raises(Exception):
                async for _ in client.asr.stream_websocket(audio()):
                    pass
            await client.close()
            conn = server.stop()
        assert conn.headers["user-agent"] == USER_AGENT


class TestLegacy:
    def test_legacy_package_sends_the_product_with_a_legacy_comment(self):
        try:
            from fish_audio_sdk import Session, WebSocketSession
        except TypeError:
            pytest.skip("fish_audio_sdk does not import on this Python version")
        expected = f"{USER_AGENT} (legacy)"
        assert USER_AGENT_GRAMMAR.match(expected)
        session = Session("k")
        assert session._sync_client.headers["user-agent"] == expected
        assert session._async_client.headers["user-agent"] == expected
        assert WebSocketSession("k")._client.headers["user-agent"] == expected
