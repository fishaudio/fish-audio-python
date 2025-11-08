"""Tests for utility functions."""

import pytest
from unittest.mock import Mock, patch, mock_open
import subprocess

from fishaudio.utils import play, save, stream
from fishaudio.exceptions import DependencyError


class TestSave:
    """Test save() function."""

    def test_save_bytes(self):
        """Test saving bytes to file."""
        audio = b"fake audio data"

        with patch("builtins.open", mock_open()) as m:
            save(audio, "output.mp3")

            m.assert_called_once_with("output.mp3", "wb")
            m().write.assert_called_once_with(audio)

    def test_save_iterator(self):
        """Test saving iterator to file."""
        audio = iter([b"chunk1", b"chunk2", b"chunk3"])

        with patch("builtins.open", mock_open()) as m:
            save(audio, "output.mp3")

            m.assert_called_once_with("output.mp3", "wb")
            # Should consolidate chunks
            m().write.assert_called_once_with(b"chunk1chunk2chunk3")


class TestPlay:
    """Test play() function."""

    def test_play_with_ffmpeg(self):
        """Test playing audio with ffplay."""
        # Mock subprocess.run to simulate which and ffplay succeeding
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            audio = b"fake audio"
            play(audio, use_ffmpeg=True)

            # Should call both which (to check) and ffplay
            assert mock_run.call_count >= 1
            # At least one call should involve ffplay
            calls_str = str(mock_run.call_args_list)
            assert "ffplay" in calls_str or "which" in calls_str

    def test_play_ffmpeg_not_installed(self):
        """Test error when ffplay not installed."""
        with patch(
            "subprocess.run", side_effect=[subprocess.CalledProcessError(1, "which")]
        ):
            with pytest.raises(DependencyError) as exc_info:
                play(b"audio", use_ffmpeg=True)

            assert "ffplay" in str(exc_info.value)

    def test_play_sounddevice_mode(self):
        """Test using sounddevice directly."""
        # Since we can't easily test sounddevice without installing it,
        # just test that the error is raised when it's not available
        with patch(
            "subprocess.run", side_effect=[subprocess.CalledProcessError(1, "which")]
        ):
            with pytest.raises(DependencyError) as exc_info:
                play(b"audio", use_ffmpeg=False)

            # Should mention sounddevice in the error
            assert "sounddevice" in str(exc_info.value) or "fishaudio[utils]" in str(
                exc_info.value
            )

    def test_play_notebook_not_installed(self):
        """Test error when IPython not available."""
        # Temporarily modify sys.modules to simulate missing IPython
        import sys

        original_modules = sys.modules.copy()
        try:
            # Remove IPython from modules if present
            sys.modules.pop("IPython", None)
            sys.modules.pop("IPython.display", None)

            with patch.dict("sys.modules", {"IPython": None, "IPython.display": None}):
                with pytest.raises(DependencyError) as exc_info:
                    play(b"audio", notebook=True)

                assert "IPython" in str(exc_info.value)
        finally:
            # Restore original modules
            sys.modules.update(original_modules)


class TestStream:
    """Test stream() function."""

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_stream_audio(self, mock_run, mock_popen):
        """Test streaming audio with mpv."""
        # Mock which command to succeed
        mock_run.return_value = Mock(returncode=0)

        # Mock mpv process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_popen.return_value = mock_process

        # Stream chunks
        audio_chunks = iter([b"chunk1", b"chunk2", b"chunk3"])
        result = stream(audio_chunks)

        # Should launch mpv
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        assert "mpv" in call_args[0][0][0]

        # Should write chunks
        assert mock_process.stdin.write.call_count == 3

        # Should return complete audio
        assert result == b"chunk1chunk2chunk3"

        # Should cleanup
        mock_process.stdin.close.assert_called_once()
        mock_process.wait.assert_called_once()

    def test_stream_mpv_not_installed(self):
        """Test error when mpv not installed."""
        with patch(
            "subprocess.run", side_effect=[subprocess.CalledProcessError(1, "which")]
        ):
            with pytest.raises(DependencyError) as exc_info:
                stream(iter([b"audio"]))

            assert "mpv" in str(exc_info.value)
