"""Audio streaming utility."""

import subprocess
from typing import Iterator

from ..exceptions import DependencyError


def _is_installed(command: str) -> bool:
    """Check if a command is available in PATH."""
    try:
        subprocess.run(["which", command], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def stream(audio_stream: Iterator[bytes]) -> bytes:
    """
    Stream audio in real-time while playing it with mpv.

    This function plays the audio as it's being generated and
    simultaneously captures it to return the complete audio buffer.

    Args:
        audio_stream: Iterator of audio byte chunks

    Returns:
        Complete audio bytes after streaming finishes

    Raises:
        DependencyError: If mpv is not installed

    Examples:
        ```python
        from fishaudio import FishAudio, stream

        client = FishAudio(api_key="...")
        audio_stream = client.tts.convert(text="Hello world")

        # Stream and play in real-time, get complete audio
        complete_audio = stream(audio_stream)

        # Save the captured audio
        with open("output.mp3", "wb") as f:
            f.write(complete_audio)
        ```
    """
    if not _is_installed("mpv"):
        raise DependencyError(
            "mpv",
            "brew install mpv  # macOS\n"
            "sudo apt install mpv  # Linux\n"
            "https://mpv.io/installation/  # Windows",
        )

    # Launch mpv process
    mpv_process = subprocess.Popen(
        ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Stream chunks to mpv while accumulating
    audio_buffer = b""
    try:
        for chunk in audio_stream:
            if chunk and mpv_process.stdin:
                mpv_process.stdin.write(chunk)
                mpv_process.stdin.flush()
                audio_buffer += chunk
    finally:
        # Cleanup
        if mpv_process.stdin:
            mpv_process.stdin.close()
        mpv_process.wait()

    return audio_buffer
