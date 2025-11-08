"""Audio playback utility."""

import io
import subprocess
from typing import Iterator, Union

from ..exceptions import DependencyError


def _is_installed(command: str) -> bool:
    """Check if a command is available in PATH."""
    try:
        subprocess.run(["which", command], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def play(
    audio: Union[bytes, Iterator[bytes]],
    *,
    notebook: bool = False,
    use_ffmpeg: bool = True,
) -> None:
    """
    Play audio using various playback methods.

    Args:
        audio: Audio bytes or iterator of bytes
        notebook: Use Jupyter notebook playback (IPython.display.Audio)
        use_ffmpeg: Use ffplay for playback (default, falls back to sounddevice)

    Raises:
        DependencyError: If required playback tool is not installed

    Examples:
        ```python
        from fishaudio import FishAudio, play

        client = FishAudio(api_key="...")
        audio = client.tts.convert(text="Hello world")

        # Play directly
        play(audio)

        # In Jupyter notebook
        play(audio, notebook=True)

        # Force sounddevice fallback
        play(audio, use_ffmpeg=False)
        ```
    """
    # Consolidate iterator to bytes
    if isinstance(audio, Iterator):
        audio = b"".join(audio)

    # Notebook mode
    if notebook:
        try:
            from IPython.display import Audio, display

            display(Audio(audio, rate=44100, autoplay=True))
            return
        except ImportError:
            raise DependencyError("IPython", "pip install ipython")

    # FFmpeg mode (default)
    if use_ffmpeg:
        if not _is_installed("ffplay"):
            raise DependencyError(
                "ffplay",
                "brew install ffmpeg  # macOS\n"
                "sudo apt install ffmpeg  # Linux\n"
                "https://ffmpeg.org/download.html  # Windows",
            )

        try:
            subprocess.run(
                ["ffplay", "-autoexit", "-", "-nodisp"],
                input=audio,
                capture_output=True,
                check=True,
            )
            return
        except subprocess.CalledProcessError:
            # Fall through to sounddevice if ffplay fails
            pass

    # Sounddevice fallback
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError:
        raise DependencyError(
            "sounddevice and soundfile",
            "pip install 'fishaudio[utils]'  # or\npip install sounddevice soundfile",
        )

    # Load and play audio
    data, samplerate = sf.read(io.BytesIO(audio))
    sd.play(data, samplerate)
    sd.wait()  # Wait until playback finishes
