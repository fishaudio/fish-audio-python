"""Integration tests for TTS with timestamps."""

import io

import soundfile as sf

TEXT = "Hello! Welcome to Fish Audio."
WORDS = ["Hello", "Welcome", "to", "Fish", "Audio"]


def _check(result):
    """Timings cover the spoken words, in order, inside the decoded audio."""
    info = sf.info(io.BytesIO(result.audio))
    assert result.duration is not None
    assert abs(info.duration - result.duration) < 0.1
    assert [s.text for s in result.segments] == WORDS
    starts = [s.start for s in result.segments]
    assert starts == sorted(starts)
    assert all(0 <= s.start <= s.end <= info.duration + 0.1 for s in result.segments)


class TestTTSTimestampsIntegration:
    """Test TTS with timestamps against the real API."""

    def test_convert_with_timestamps(self, client, save_audio):
        result = client.tts.convert_with_timestamps(text=TEXT, format="wav")
        save_audio(result.audio, "test_timestamps.wav")
        _check(result)

    def test_stream_with_timestamps(self, client):
        with client.tts.stream_with_timestamps(text=TEXT, format="wav") as stream:
            audio = b"".join(event.audio for event in stream)
            segments = stream.segments

        info = sf.info(io.BytesIO(audio))
        assert [s.text for s in segments] == WORDS
        assert all(0 <= s.start <= s.end <= info.duration + 0.1 for s in segments)


class TestAsyncTTSTimestampsIntegration:
    """Test async TTS with timestamps against the real API."""

    async def test_convert_with_timestamps(self, async_client, save_audio):
        result = await async_client.tts.convert_with_timestamps(text=TEXT, format="wav")
        save_audio(result.audio, "test_timestamps_async.wav")
        _check(result)
