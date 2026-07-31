"""Tests for utility functions."""

import importlib
from unittest.mock import Mock, patch

import pytest

from fishaudio.exceptions import DependencyError
from fishaudio.utils import play, save, stream

# fishaudio.utils re-exports the functions, which shadows the module names, so
# reach the modules explicitly to reach their private helpers.
play_module = importlib.import_module("fishaudio.utils.play")
stream_module = importlib.import_module("fishaudio.utils.stream")


class TestSave:
    """Test save() function."""

    def test_save_bytes(self, tmp_path):
        """Test saving bytes to file."""
        audio = b"fake audio data"
        output_file = tmp_path / "output.mp3"

        save(audio, str(output_file))

        assert output_file.read_bytes() == audio

    def test_save_iterator(self, tmp_path):
        """Test saving iterator to file."""
        audio = iter([b"chunk1", b"chunk2", b"chunk3"])
        output_file = tmp_path / "output.mp3"

        save(audio, str(output_file))

        # Should consolidate chunks
        assert output_file.read_bytes() == b"chunk1chunk2chunk3"


class TestPlay:
    """Test play() function."""

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/ffplay")
    def test_play_with_ffmpeg(self, _mock_which, mock_run):
        """Test playing audio with ffplay."""
        mock_run.return_value = Mock(returncode=0)

        play(b"fake audio", use_ffmpeg=True)

        # Should invoke ffplay itself
        assert mock_run.call_count >= 1
        assert "ffplay" in str(mock_run.call_args_list)

    def test_play_ffmpeg_not_installed(self):
        """Test error when ffplay not installed."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(DependencyError) as exc_info:
                play(b"audio", use_ffmpeg=True)

            assert "ffplay" in str(exc_info.value)

    def test_play_sounddevice_mode(self):
        """Test using sounddevice for playback."""
        mock_sd = Mock()
        mock_sf = Mock()
        mock_sf.read.return_value = ([0.1, 0.2], 44100)

        with patch.dict("sys.modules", {"sounddevice": mock_sd, "soundfile": mock_sf}):
            play(b"audio", use_ffmpeg=False)

            mock_sf.read.assert_called_once()
            mock_sd.play.assert_called_once()
            mock_sd.wait.assert_called_once()

    def test_play_sounddevice_not_installed(self):
        """Test error when sounddevice not installed."""
        with patch.dict("sys.modules", {"sounddevice": None, "soundfile": None}):
            with pytest.raises(DependencyError) as exc_info:
                play(b"audio", use_ffmpeg=False)

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
    @patch("shutil.which", return_value="/usr/bin/mpv")
    def test_stream_audio(self, mock_which, mock_popen):
        """Test streaming audio with mpv."""
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
        with patch("shutil.which", return_value=None):
            with pytest.raises(DependencyError) as exc_info:
                stream(iter([b"audio"]))

            assert "mpv" in str(exc_info.value)


class TestIsInstalled:
    """Test the PATH lookup behind play() and stream()."""

    @pytest.mark.parametrize("module", [play_module, stream_module])
    def test_missing_command_returns_false(self, module):
        """A missing binary is reported as absent, not raised."""
        assert module._is_installed("fishaudio-definitely-not-a-real-binary") is False

    @pytest.mark.parametrize("module", [play_module, stream_module])
    @patch("subprocess.run", side_effect=AssertionError("must not shell out"))
    @patch("shutil.which", return_value=None)
    def test_uses_shutil_not_a_which_subprocess(self, mock_which, _mock_run, module):
        """The lookup must not shell out.

        Shelling out to ``which`` raises FileNotFoundError on Windows, where no
        such binary exists. That escapes the handler, so play() and stream()
        died with WinError 2 instead of raising DependencyError, on the very
        platform whose install instructions those errors document.
        """
        assert module._is_installed("mpv") is False
        mock_which.assert_called_once_with("mpv")

    @pytest.mark.parametrize(
        ("module", "command"), [(play_module, "ffplay"), (stream_module, "mpv")]
    )
    @patch(
        "subprocess.run",
        side_effect=FileNotFoundError(2, "The system cannot find the file specified"),
    )
    @patch("shutil.which", return_value=None)
    def test_windows_without_which_still_raises_dependency_error(
        self, _mock_which, _mock_run, module, command
    ):
        """Simulate Windows: no `which` binary on PATH, and the tool absent."""
        with pytest.raises(DependencyError) as exc_info:
            if module is play_module:
                play(b"audio", use_ffmpeg=True)
            else:
                stream(iter([b"audio"]))

        assert command in str(exc_info.value)
