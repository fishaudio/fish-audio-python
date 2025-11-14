"""Audio stream wrappers with collection utilities."""

from typing import AsyncIterator, Iterator


class AudioStream:
    """Wrapper for sync audio byte streams with collection utilities.

    This class wraps an iterator of audio bytes and provides a convenient
    `.collect()` method to gather all chunks into a single bytes object.

    Examples:
        ```python
        from fishaudio import FishAudio

        client = FishAudio(api_key="...")

        # Collect all audio at once
        audio = client.tts.stream(text="Hello!").collect()

        # Or stream chunks manually
        for chunk in client.tts.stream(text="Hello!"):
            process_chunk(chunk)
        ```
    """

    def __init__(self, iterator: Iterator[bytes]):
        """Initialize the audio iterator wrapper.

        Args:
            iterator: The underlying iterator of audio bytes
        """
        self._iter = iterator

    def __iter__(self) -> Iterator[bytes]:
        """Allow direct iteration over audio chunks."""
        return self._iter

    def collect(self) -> bytes:
        """Collect all audio chunks into a single bytes object.

        This consumes the iterator and returns all audio data as bytes.
        After calling this method, the iterator cannot be used again.

        Returns:
            Complete audio data as bytes

        Examples:
            ```python
            audio = client.tts.stream(text="Hello!").collect()
            with open("output.mp3", "wb") as f:
                f.write(audio)
            ```
        """
        chunks = []
        for chunk in self._iter:
            chunks.append(chunk)
        return b"".join(chunks)


class AsyncAudioStream:
    """Wrapper for async audio byte streams with collection utilities.

    This class wraps an async iterator of audio bytes and provides a convenient
    `.collect()` method to gather all chunks into a single bytes object.

    Examples:
        ```python
        from fishaudio import AsyncFishAudio

        client = AsyncFishAudio(api_key="...")

        # Collect all audio at once
        stream = await client.tts.stream(text="Hello!")
        audio = await stream.collect()

        # Or stream chunks manually
        async for chunk in await client.tts.stream(text="Hello!"):
            await process_chunk(chunk)
        ```
    """

    def __init__(self, async_iterator: AsyncIterator[bytes]):
        """Initialize the async audio iterator wrapper.

        Args:
            async_iterator: The underlying async iterator of audio bytes
        """
        self._iter = async_iterator

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Allow direct async iteration over audio chunks."""
        return self._iter

    async def collect(self) -> bytes:
        """Collect all audio chunks into a single bytes object.

        This consumes the async iterator and returns all audio data as bytes.
        After calling this method, the iterator cannot be used again.

        Returns:
            Complete audio data as bytes

        Examples:
            ```python
            stream = await client.tts.stream(text="Hello!")
            audio = await stream.collect()
            with open("output.mp3", "wb") as f:
                f.write(audio)
            ```
        """
        chunks = []
        async for chunk in self._iter:
            chunks.append(chunk)
        return b"".join(chunks)
