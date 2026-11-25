"""Audio stream wrappers with collection utilities."""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Optional

from fishaudio.types.tts import (
    TTSAlignment,
    TTSTimestampEvent,
    TTSTimestampResult,
    TTSTimestampSegment,
)


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


class _Timeline:
    """Keeps the newest timing snapshot of every text chunk."""

    def __init__(self) -> None:
        self._chunks: dict[int, tuple[float, TTSAlignment]] = {}
        self._last_seq = -1

    def add(self, event: TTSTimestampEvent) -> None:
        self._last_seq = max(self._last_seq, event.chunk_seq)
        if event.alignment is not None:
            self._chunks[event.chunk_seq] = (
                event.chunk_audio_offset_sec,
                event.alignment,
            )

    @property
    def segments(self) -> list[TTSTimestampSegment]:
        return [
            TTSTimestampSegment(
                text=segment.text,
                start=segment.start + offset,
                end=segment.end + offset,
            )
            for offset, alignment in (self._chunks[k] for k in sorted(self._chunks))
            for segment in alignment.segments
        ]

    @property
    def duration(self) -> Optional[float]:
        """End of the last text chunk, or None when the API did not report it.

        The API reports audio length only inside timing snapshots. Without a
        snapshot for the last chunk, the end of the audio is unknown: earlier
        chunks would give a length that is too short, and no chunk gives none.
        """
        last = self._chunks.get(self._last_seq)
        if last is None:
            return None
        offset, alignment = last
        return offset + alignment.audio_duration


class TTSTimestampStream:
    """Sync stream of text-to-speech audio with timestamps.

    Iterating yields `TTSTimestampEvent` objects as the server produces them.
    While you iterate, `segments` holds the timings received so far, measured
    from the start of the complete audio. Alternatively, call `collect()`
    instead of iterating to get the complete audio with its final timings.

    Examples:
        ```python
        from fishaudio import FishAudio

        client = FishAudio(api_key="...")

        # Play audio as it arrives and keep the timings up to date
        with client.tts.stream_with_timestamps(text="Hello world") as stream:
            for event in stream:
                player.write(event.audio)
                show_captions(stream.segments)

        # Or collect everything at once
        result = client.tts.stream_with_timestamps(text="Hello world").collect()
        ```
    """

    def __init__(
        self,
        iterator: Iterator[TTSTimestampEvent],
        *,
        on_close: Optional[Callable[[], None]] = None,
    ):
        """Initialize the stream.

        Args:
            iterator: The underlying iterator of events
            on_close: Called by close() to release the underlying resource,
                for example the open HTTP response
        """
        self._iter = iterator
        self._on_close = on_close
        self._closed = False
        self._timeline = _Timeline()
        self._started = False

    def __iter__(self) -> "TTSTimestampStream":
        return self

    def __next__(self) -> TTSTimestampEvent:
        self._started = True
        event = next(self._iter)
        self._timeline.add(event)
        return event

    @property
    def segments(self) -> list[TTSTimestampSegment]:
        """Timings received so far, in speaking order.

        Times are in seconds from the start of the complete audio. Entries near
        the end can still be corrected by later events, so read this again
        after each event instead of appending to an earlier copy.

        Empty until the first timings arrive, and it stays empty when the API
        has no timings for the text (for example text without words). The
        audio still arrives in full.
        """
        return self._timeline.segments

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

    def __enter__(self) -> "TTSTimestampStream":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def collect(self) -> TTSTimestampResult:
        """Read the whole stream and return the complete audio with its timings.

        Call this instead of iterating, not after it. Events that were already
        yielded are not kept, so the complete audio can no longer be returned
        once iteration has started; in that case use the audio you received
        and read `segments` when the stream ends.

        Returns:
            TTSTimestampResult with the complete audio and final timings. When
            the API has no timings for the text, `segments` is empty and
            `duration` is None; the audio is still complete.

        Raises:
            RuntimeError: If iteration has already started
        """
        if self._started:
            raise RuntimeError(
                "collect() must be called before iterating: events already "
                "yielded are not kept, so the complete audio is no longer "
                "available. Join event.audio yourself and read stream.segments."
            )
        try:
            audio = b"".join(event.audio for event in self)
            return TTSTimestampResult(
                audio=audio,
                segments=self._timeline.segments,
                duration=self._timeline.duration,
            )
        finally:
            self.close()


class AsyncTTSTimestampStream:
    """Async stream of text-to-speech audio with timestamps.

    Iterating yields `TTSTimestampEvent` objects as the server produces them.
    While you iterate, `segments` holds the timings received so far, measured
    from the start of the complete audio. Alternatively, call `collect()`
    instead of iterating to get the complete audio with its final timings.

    Examples:
        ```python
        from fishaudio import AsyncFishAudio

        client = AsyncFishAudio(api_key="...")

        # Play audio as it arrives and keep the timings up to date
        async with await client.tts.stream_with_timestamps(text="Hello world") as stream:
            async for event in stream:
                await player.write(event.audio)
                show_captions(stream.segments)

        # Or collect everything at once
        stream = await client.tts.stream_with_timestamps(text="Hello world")
        result = await stream.collect()
        ```
    """

    def __init__(
        self,
        async_iterator: AsyncIterator[TTSTimestampEvent],
        *,
        on_close: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """Initialize the stream.

        Args:
            async_iterator: The underlying async iterator of events
            on_close: Awaited by aclose() to release the underlying resource,
                for example the open HTTP response
        """
        self._iter = async_iterator
        self._on_close = on_close
        self._closed = False
        self._timeline = _Timeline()
        self._started = False

    def __aiter__(self) -> "AsyncTTSTimestampStream":
        return self

    async def __anext__(self) -> TTSTimestampEvent:
        self._started = True
        event = await self._iter.__anext__()
        self._timeline.add(event)
        return event

    @property
    def segments(self) -> list[TTSTimestampSegment]:
        """Timings received so far, in speaking order.

        Times are in seconds from the start of the complete audio. Entries near
        the end can still be corrected by later events, so read this again
        after each event instead of appending to an earlier copy.

        Empty until the first timings arrive, and it stays empty when the API
        has no timings for the text (for example text without words). The
        audio still arrives in full.
        """
        return self._timeline.segments

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

    async def __aenter__(self) -> "AsyncTTSTimestampStream":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def collect(self) -> TTSTimestampResult:
        """Read the whole stream and return the complete audio with its timings.

        Call this instead of iterating, not after it. Events that were already
        yielded are not kept, so the complete audio can no longer be returned
        once iteration has started; in that case use the audio you received
        and read `segments` when the stream ends.

        Returns:
            TTSTimestampResult with the complete audio and final timings. When
            the API has no timings for the text, `segments` is empty and
            `duration` is None; the audio is still complete.

        Raises:
            RuntimeError: If iteration has already started
        """
        if self._started:
            raise RuntimeError(
                "collect() must be called before iterating: events already "
                "yielded are not kept, so the complete audio is no longer "
                "available. Join event.audio yourself and read stream.segments."
            )
        try:
            chunks = []
            async for event in self:
                chunks.append(event.audio)
            return TTSTimestampResult(
                audio=b"".join(chunks),
                segments=self._timeline.segments,
                duration=self._timeline.duration,
            )
        finally:
            await self.aclose()
