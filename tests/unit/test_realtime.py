"""Tests for realtime WebSocket streaming helpers."""

import pytest
from unittest.mock import Mock
import ormsgpack
from httpx_ws import WebSocketDisconnect

from fishaudio.resources.realtime import (
    _should_stop,
    _process_audio_event,
    iter_websocket_audio,
    aiter_websocket_audio,
)
from fishaudio.exceptions import WebSocketError


class TestShouldStop:
    """Test _should_stop function."""

    def test_returns_true_for_finish_stop_event(self):
        """Test that finish event with stop reason returns True."""
        data = {"event": "finish", "reason": "stop"}
        assert _should_stop(data) is True

    def test_returns_false_for_finish_error_event(self):
        """Test that finish event with error reason returns False."""
        data = {"event": "finish", "reason": "error"}
        assert _should_stop(data) is False

    def test_returns_false_for_audio_event(self):
        """Test that audio event returns False."""
        data = {"event": "audio", "audio": b"data"}
        assert _should_stop(data) is False

    def test_returns_false_for_unknown_event(self):
        """Test that unknown event returns False."""
        data = {"event": "unknown", "data": "something"}
        assert _should_stop(data) is False

    def test_returns_false_for_missing_fields(self):
        """Test that missing event/reason fields returns False."""
        assert _should_stop({}) is False
        assert _should_stop({"event": "finish"}) is False
        assert _should_stop({"reason": "stop"}) is False


class TestProcessAudioEvent:
    """Test _process_audio_event function."""

    def test_audio_event_returns_audio_bytes(self):
        """Test that audio event returns audio bytes."""
        data = {"event": "audio", "audio": b"test_audio_data"}
        result = _process_audio_event(data)
        assert result == b"test_audio_data"

    def test_finish_event_with_error_raises_exception(self):
        """Test that finish event with error reason raises WebSocketError."""
        data = {"event": "finish", "reason": "error"}
        with pytest.raises(WebSocketError, match="WebSocket stream ended with error"):
            _process_audio_event(data)

    def test_finish_event_with_stop_returns_none(self):
        """Test that finish event with stop reason returns None."""
        data = {"event": "finish", "reason": "stop"}
        result = _process_audio_event(data)
        assert result is None

    def test_unknown_event_returns_none(self):
        """Test that unknown event types return None."""
        data = {"event": "unknown_event", "data": "something"}
        result = _process_audio_event(data)
        assert result is None

    def test_finish_event_with_unknown_reason_returns_none(self):
        """Test that finish event with unknown reason returns None."""
        data = {"event": "finish", "reason": "unknown_reason"}
        result = _process_audio_event(data)
        assert result is None


class TestIterWebsocketAudio:
    """Test iter_websocket_audio function (sync)."""

    def test_yields_audio_chunks(self):
        """Test that audio chunks are yielded correctly."""
        # Create mock WebSocket
        mock_ws = Mock()

        # Prepare messages
        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk2"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk3"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        # Collect yielded audio
        audio_chunks = list(iter_websocket_audio(mock_ws))

        assert audio_chunks == [b"chunk1", b"chunk2", b"chunk3"]
        assert mock_ws.receive_bytes.call_count == 4

    def test_stops_on_finish_stop_event(self):
        """Test that iteration stops on finish stop event."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        audio_chunks = list(iter_websocket_audio(mock_ws))

        assert audio_chunks == [b"chunk1"]
        assert mock_ws.receive_bytes.call_count == 2

    def test_raises_on_finish_error_event(self):
        """Test that WebSocketError is raised on error finish event."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "finish", "reason": "error"}),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        with pytest.raises(WebSocketError, match="WebSocket stream ended with error"):
            list(iter_websocket_audio(mock_ws))

    def test_raises_on_websocket_disconnect(self):
        """Test that WebSocketError is raised on unexpected disconnect."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            WebSocketDisconnect(),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        with pytest.raises(WebSocketError, match="WebSocket disconnected unexpectedly"):
            list(iter_websocket_audio(mock_ws))

    def test_ignores_unknown_events(self):
        """Test that unknown events are ignored and iteration continues."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "unknown", "data": "ignored"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk2"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        audio_chunks = list(iter_websocket_audio(mock_ws))

        # Unknown event should be ignored, iteration continues
        assert audio_chunks == [b"chunk1", b"chunk2"]
        assert mock_ws.receive_bytes.call_count == 4

    def test_empty_stream_with_immediate_finish(self):
        """Test handling of stream that immediately finishes."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        mock_ws.receive_bytes = Mock(side_effect=messages)

        audio_chunks = list(iter_websocket_audio(mock_ws))

        assert audio_chunks == []


class TestAiterWebsocketAudio:
    """Test aiter_websocket_audio function (async)."""

    @pytest.mark.asyncio
    async def test_yields_audio_chunks(self):
        """Test that audio chunks are yielded correctly."""
        # Create mock async WebSocket
        mock_ws = Mock()

        # Prepare messages
        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk2"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk3"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        # Collect yielded audio
        audio_chunks = []
        async for chunk in aiter_websocket_audio(mock_ws):
            audio_chunks.append(chunk)

        assert audio_chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @pytest.mark.asyncio
    async def test_stops_on_finish_stop_event(self):
        """Test that iteration stops on finish stop event."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        audio_chunks = []
        async for chunk in aiter_websocket_audio(mock_ws):
            audio_chunks.append(chunk)

        assert audio_chunks == [b"chunk1"]

    @pytest.mark.asyncio
    async def test_raises_on_finish_error_event(self):
        """Test that WebSocketError is raised on error finish event."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "finish", "reason": "error"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        with pytest.raises(WebSocketError, match="WebSocket stream ended with error"):
            async for _ in aiter_websocket_audio(mock_ws):
                pass

    @pytest.mark.asyncio
    async def test_raises_on_websocket_disconnect(self):
        """Test that WebSocketError is raised on unexpected disconnect."""
        mock_ws = Mock()

        call_count = [0]

        async def mock_receive_bytes():
            call_count[0] += 1
            if call_count[0] == 1:
                return ormsgpack.packb({"event": "audio", "audio": b"chunk1"})
            else:
                raise WebSocketDisconnect()

        mock_ws.receive_bytes = mock_receive_bytes

        with pytest.raises(WebSocketError, match="WebSocket disconnected unexpectedly"):
            async for _ in aiter_websocket_audio(mock_ws):
                pass

    @pytest.mark.asyncio
    async def test_ignores_unknown_events(self):
        """Test that unknown events are ignored and iteration continues."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"chunk1"}),
            ormsgpack.packb({"event": "unknown", "data": "ignored"}),
            ormsgpack.packb({"event": "audio", "audio": b"chunk2"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        audio_chunks = []
        async for chunk in aiter_websocket_audio(mock_ws):
            audio_chunks.append(chunk)

        # Unknown event should be ignored, iteration continues
        assert audio_chunks == [b"chunk1", b"chunk2"]

    @pytest.mark.asyncio
    async def test_empty_stream_with_immediate_finish(self):
        """Test handling of stream that immediately finishes."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        audio_chunks = []
        async for chunk in aiter_websocket_audio(mock_ws):
            audio_chunks.append(chunk)

        assert audio_chunks == []

    @pytest.mark.asyncio
    async def test_multiple_audio_events_in_sequence(self):
        """Test handling of multiple consecutive audio events."""
        mock_ws = Mock()

        messages = [
            ormsgpack.packb({"event": "audio", "audio": b"a"}),
            ormsgpack.packb({"event": "audio", "audio": b"b"}),
            ormsgpack.packb({"event": "audio", "audio": b"c"}),
            ormsgpack.packb({"event": "audio", "audio": b"d"}),
            ormsgpack.packb({"event": "audio", "audio": b"e"}),
            ormsgpack.packb({"event": "finish", "reason": "stop"}),
        ]

        async def mock_receive_bytes():
            return messages.pop(0)

        mock_ws.receive_bytes = mock_receive_bytes

        audio_chunks = []
        async for chunk in aiter_websocket_audio(mock_ws):
            audio_chunks.append(chunk)

        assert audio_chunks == [b"a", b"b", b"c", b"d", b"e"]
