"""Audio saving utility."""

from typing import Iterator, Union


def save(audio: Union[bytes, Iterator[bytes]], filename: str) -> None:
    """
    Save audio to a file.

    Args:
        audio: Audio bytes or iterator of bytes
        filename: Path to save the audio file

    Examples:
        ```python
        from fishaudio import FishAudio, save

        client = FishAudio(api_key="...")
        audio = client.tts.convert(text="Hello world")

        # Save to file
        save(audio, "output.mp3")

        # Works with iterators too
        audio_stream = client.tts.convert(text="Another example")
        save(audio_stream, "another.mp3")
        ```
    """
    # Consolidate iterator to bytes if needed
    if isinstance(audio, Iterator):
        audio = b"".join(audio)

    # Write to file
    with open(filename, "wb") as f:
        f.write(audio)
