"""Tests for the sync WebSocket reader-draining helper."""

import socket
import threading
from unittest.mock import Mock, patch

import httpx_ws
import pytest
import wsproto
from httpcore._backends.sync import SyncStream

from fishaudio.core._ws_utils import drain_reader


def _make_ws(sock=None, thread=None):
    ws = Mock()
    stream = Mock()
    stream.get_extra_info.return_value = sock
    ws.stream = stream
    ws._background_receive_task = thread
    return ws


class TestDrainReader:
    def test_sends_close_frame_then_shuts_down_socket_and_joins_reader(self):
        sock = Mock()
        thread = Mock()
        ws = _make_ws(sock, thread)
        parent = Mock()
        parent.attach_mock(ws.send, "send")
        parent.attach_mock(sock.shutdown, "shutdown")
        parent.attach_mock(thread.join, "join")

        drain_reader(ws)

        assert [c[0] for c in parent.mock_calls] == ["send", "shutdown", "join"]
        (event,) = ws.send.call_args.args
        assert isinstance(event, wsproto.events.CloseConnection)
        assert event.code == 1000
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        thread.join.assert_called_once_with(timeout=5)

    def test_falls_back_to_response_network_stream(self):
        sock = Mock()
        ws = Mock()
        ws.stream = None
        stream = Mock()
        stream.get_extra_info.return_value = sock
        ws.response.extensions = {"network_stream": stream}
        ws._background_receive_task = Mock()
        drain_reader(ws)
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)

    def test_shuts_down_socket_when_close_frame_send_fails(self):
        sock = Mock()
        ws = _make_ws(sock, Mock())
        ws.send.side_effect = httpx_ws.WebSocketNetworkError()
        drain_reader(ws)
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)

    def test_joins_reader_when_socket_shutdown_fails(self):
        sock = Mock()
        sock.shutdown.side_effect = OSError("already closed")
        thread = Mock()
        drain_reader(_make_ws(sock, thread))
        thread.join.assert_called_once_with(timeout=5)

    def test_tolerates_missing_socket_and_thread(self):
        ws = Mock()
        ws.stream = None
        ws.response = None
        del ws._background_receive_task
        drain_reader(ws)  # must not raise

    def test_swallows_unexpected_errors(self, caplog):
        ws = Mock()
        ws.stream = Mock()
        ws.stream.get_extra_info.side_effect = RuntimeError("boom")
        with caplog.at_level("DEBUG", logger="fishaudio.core._ws_utils"):
            drain_reader(ws)  # must not raise
        assert "drain_reader failed" in caplog.text


class TestDrainReaderRealSession:
    def test_real_httpx_ws_session_over_socketpair(self):
        client_sock, server_sock = socket.socketpair()
        server_sock.settimeout(1)
        hook_calls = []
        old_hook = threading.excepthook
        threading.excepthook = lambda args: hook_calls.append(args)
        try:
            ws = httpx_ws.WebSocketSession(
                SyncStream(client_sock), keepalive_ping_interval_seconds=None
            )
            with ws:
                drain_reader(ws)
                assert not ws._background_receive_task.is_alive()
                assert (
                    ws.connection.state
                    is wsproto.connection.ConnectionState.LOCAL_CLOSING
                )

            # The peer must have received a clean close frame before FIN.
            received = b""
            while True:
                chunk = server_sock.recv(4096)
                if not chunk:
                    break
                received += chunk
            server = wsproto.connection.Connection(wsproto.ConnectionType.SERVER)
            server.receive_data(received)
            events = list(server.events())
            assert len(events) == 1
            assert isinstance(events[0], wsproto.events.CloseConnection)
            assert events[0].code == 1000
            assert hook_calls == []
        finally:
            threading.excepthook = old_hook
            server_sock.close()
            client_sock.close()


class TestDrainReaderIsCalledFromSyncPaths:
    @patch("fishaudio.resources.tts.drain_reader")
    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_new_client_calls_drain_reader_on_success(
        self, mock_executor, mock_connect_ws, mock_drain
    ):
        from fishaudio.core import ClientWrapper
        from fishaudio.resources.tts import TTSClient

        ws = Mock()
        ws.__enter__ = Mock(return_value=ws)
        ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = ws
        mock_executor.return_value.submit.return_value.result.return_value = None
        parent = Mock()
        parent.attach_mock(mock_drain, "drain")
        parent.attach_mock(ws.__exit__, "exit")

        client = TTSClient(ClientWrapper(api_key="k", base_url="https://x"))
        with patch("fishaudio.resources.tts.iter_websocket_audio") as recv:
            recv.return_value = iter([b"a"])
            assert list(client.stream_websocket(iter(["hi"]))) == [b"a"]

        mock_drain.assert_called_once_with(ws)
        # drain must happen before the session's __exit__ closes the socket
        assert [c[0] for c in parent.mock_calls] == ["drain", "exit"]

    @patch("fishaudio.resources.tts.drain_reader")
    @patch("fishaudio.resources.tts.connect_ws")
    @patch("fishaudio.resources.tts.ThreadPoolExecutor")
    def test_new_client_calls_drain_reader_on_error(
        self, mock_executor, mock_connect_ws, mock_drain
    ):
        from fishaudio.core import ClientWrapper
        from fishaudio.resources.tts import TTSClient

        ws = Mock()
        ws.__enter__ = Mock(return_value=ws)
        ws.__exit__ = Mock(return_value=None)
        mock_connect_ws.return_value = ws

        client = TTSClient(ClientWrapper(api_key="k", base_url="https://x"))
        with patch("fishaudio.resources.tts.iter_websocket_audio") as recv:
            recv.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError):
                list(client.stream_websocket(iter(["hi"])))

        mock_drain.assert_called_once_with(ws)

    def test_legacy_session_calls_drain_reader(self):
        import ormsgpack

        try:
            from fish_audio_sdk import WebSocketSession
        except TypeError:  # legacy schemas use `X | None`, which fails on 3.9
            pytest.skip("fish_audio_sdk does not import on this Python version")

        ws = Mock()
        ws.__enter__ = Mock(return_value=ws)
        ws.__exit__ = Mock(return_value=None)
        ws.receive_bytes.side_effect = [
            ormsgpack.packb({"event": "audio", "audio": b"a"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        connect = patch("fish_audio_sdk.websocket.connect_ws", return_value=ws)
        drain = patch("fish_audio_sdk.websocket.drain_reader")
        with connect, drain as mock_drain, WebSocketSession("k") as session:
            # Bypass the real sender thread; only the receive path is under test.
            session._executor = Mock()
            session._executor.submit.return_value.result.return_value = None
            chunks = list(session.tts(Mock(), iter(["hi"])))

        assert chunks == [b"a"]
        mock_drain.assert_called_once_with(ws)
