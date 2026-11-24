"""Audio stream wrappers with collection utilities."""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Optional


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

        # Use a with-block (or call close()) if you may stop early,
        # so the HTTP connection is released right away
        with client.tts.stream(text="Hello!") as stream:
            for chunk in stream:
                if done(chunk):
                    break
        ```
    """

    def __init__(
        self,
        iterator: Iterator[bytes],
        *,
        on_close: Optional[Callable[[], None]] = None,
    ):
        """Initialize the audio iterator wrapper.

        Args:
            iterator: The underlying iterator of audio bytes
            on_close: Called by close() to release the underlying resource,
                for example the open HTTP response
        """
        self._iter = iterator
        self._on_close = on_close
        self._closed = False

    def __iter__(self) -> Iterator[bytes]:
        """Allow direct iteration over audio chunks."""
        return self._iter

    def close(self) -> None:
        """Stop the stream and release the underlying connection.

        Safe to call more than once, and before iteration has started.
        """
        if self._closed:
            return
        self._closed = True
        try:
            close_iter = getattr(self._iter, "close", None)
            if close_iter is not None:
                close_iter()
        finally:
            if self._on_close is not None:
                self._on_close()

    def __enter__(self) -> "AudioStream":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

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
        try:
            chunks = []
            for chunk in self._iter:
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            self.close()


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

        # Use async with (or await aclose()) if you may stop early,
        # so the HTTP connection is released right away
        async with await client.tts.stream(text="Hello!") as stream:
            async for chunk in stream:
                if done(chunk):
                    break
        ```
    """

    def __init__(
        self,
        async_iterator: AsyncIterator[bytes],
        *,
        on_close: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """Initialize the async audio iterator wrapper.

        Args:
            async_iterator: The underlying async iterator of audio bytes
            on_close: Awaited by aclose() to release the underlying resource,
                for example the open HTTP response
        """
        self._iter = async_iterator
        self._on_close = on_close
        self._closed = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Allow direct async iteration over audio chunks."""
        return self._iter

    async def aclose(self) -> None:
        """Stop the stream and release the underlying connection.

        Safe to call more than once, and before iteration has started.
        """
        if self._closed:
            return
        self._closed = True
        try:
            close_iter = getattr(self._iter, "aclose", None)
            if close_iter is not None:
                await close_iter()
        finally:
            if self._on_close is not None:
                await self._on_close()

    async def __aenter__(self) -> "AsyncAudioStream":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

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
        try:
            chunks = []
            async for chunk in self._iter:
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            await self.aclose()
