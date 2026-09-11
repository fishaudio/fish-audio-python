"""Tests for the sync WebSocket reader-draining helper."""

import socket
from unittest.mock import Mock, patch

import pytest

from fishaudio.core._ws_utils import drain_reader


def _make_ws(sock=None, thread=None):
    ws = Mock()
    stream = Mock()
    stream.get_extra_info.return_value = sock
    ws.response.extensions = {"network_stream": stream}
    ws._background_receive_task = thread
    return ws


class TestDrainReader:
    def test_shuts_down_socket_and_joins_reader(self):
        sock = Mock()
        thread = Mock()
        drain_reader(_make_ws(sock, thread))
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        thread.join.assert_called_once_with(timeout=5)

    def test_joins_reader_when_socket_shutdown_fails(self):
        sock = Mock()
        sock.shutdown.side_effect = OSError("already closed")
        thread = Mock()
        drain_reader(_make_ws(sock, thread))
        thread.join.assert_called_once_with(timeout=5)

    def test_tolerates_missing_socket_and_thread(self):
        ws = Mock()
        ws.response = None
        del ws._background_receive_task
        drain_reader(ws)  # must not raise

    def test_swallows_unexpected_errors(self):
        ws = Mock()
        ws.response.extensions = Mock()
        ws.response.extensions.get.side_effect = RuntimeError("boom")
        drain_reader(ws)  # must not raise


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

        client = TTSClient(ClientWrapper(api_key="k", base_url="https://x"))
        with patch("fishaudio.resources.tts.iter_websocket_audio") as recv:
            recv.return_value = iter([b"a"])
            assert list(client.stream_websocket(iter(["hi"]))) == [b"a"]

        mock_drain.assert_called_once_with(ws)
        # drain must happen before the session's __exit__ closes the socket
        assert ws.__exit__.called

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
