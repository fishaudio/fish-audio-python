"""TTS (Text-to-Speech) namespace client."""

import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Union

import ormsgpack
from httpx_ws import AsyncWebSocketSession, WebSocketSession, aconnect_ws, connect_ws

from fishaudio.core import (
    AsyncClientWrapper,
    ClientWrapper,
    RequestOptions,
    WebSocketOptions,
)
from fishaudio.core._sse import ServerSentEvent, SSEDecoder
from fishaudio.core._ws_utils import drain_reader
from fishaudio.core.iterators import (
    AsyncAudioStream,
    AsyncTTSTimestampStream,
    AudioStream,
    TTSTimestampStream,
)
from fishaudio.exceptions import FishAudioError
from fishaudio.types import (
    AudioFormat,
    CloseEvent,
    FlushEvent,
    LatencyMode,
    Model,
    Prosody,
    ReferenceAudio,
    StartEvent,
    TextEvent,
    TTSConfig,
    TTSRequest,
    TTSTimestampEvent,
    TTSTimestampResult,
)
from fishaudio.types.shared import warn_if_deprecated_model

from .realtime import aiter_websocket_audio, iter_websocket_audio


def _config_to_tts_request(config: TTSConfig, text: str) -> TTSRequest:
    """Convert TTSConfig to TTSRequest with text."""
    return TTSRequest(
        text=text,
        chunk_length=config.chunk_length,
        format=config.format,
        sample_rate=config.sample_rate,
        mp3_bitrate=config.mp3_bitrate,
        opus_bitrate=config.opus_bitrate,
        references=config.references,
        reference_id=config.reference_id,
        normalize=config.normalize,
        latency=config.latency,
        prosody=config.prosody,
        top_p=config.top_p,
        temperature=config.temperature,
        max_new_tokens=config.max_new_tokens,
        repetition_penalty=config.repetition_penalty,
        min_chunk_length=config.min_chunk_length,
        condition_on_previous_chunks=config.condition_on_previous_chunks,
        early_stop_threshold=config.early_stop_threshold,
    )


def _normalize_to_event(
    item: Union[str, TextEvent, FlushEvent],
) -> Union[TextEvent, FlushEvent]:
    """Normalize string input to TextEvent, pass through event types unchanged."""
    if isinstance(item, (TextEvent, FlushEvent)):
        return item
    return TextEvent(text=item)


_TIMESTAMP_PATH = "/v1/tts/stream/with-timestamp"
_TIMESTAMP_HEADERS = {
    "Content-Type": "application/msgpack",
    "Accept": "text/event-stream",
}


def _build_tts_payload(
    text: str,
    config: TTSConfig,
    *,
    reference_id: Optional[str],
    references: Optional[list[ReferenceAudio]],
    format: Optional[AudioFormat],
    latency: Optional[LatencyMode],
    speed: Optional[float],
) -> bytes:
    """Build the MessagePack request body; direct parameters override config."""
    request = _config_to_tts_request(config, text)
    if reference_id is not None:
        request.reference_id = reference_id
    if references is not None:
        request.references = references
    if format is not None:
        request.format = format
    if latency is not None:
        request.latency = latency
    if speed is not None:
        request.prosody = Prosody.from_speed_override(speed, base=config.prosody)
    return ormsgpack.packb(request.model_dump(exclude_none=True))


def _parse_timestamp_event(sse: ServerSentEvent) -> Optional[TTSTimestampEvent]:
    """Turn one SSE event into a TTSTimestampEvent; None for events to skip."""
    if sse.event == "error":
        raise FishAudioError(f"Text-to-speech stream failed: {sse.data}")
    if sse.event != "message":
        return None
    try:
        payload = json.loads(sse.data)
        if not isinstance(payload, dict):
            raise TypeError("event payload is not a JSON object")
        payload["audio"] = base64.b64decode(payload.pop("audio_base64"), validate=True)
        return TTSTimestampEvent.model_validate(payload)
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise FishAudioError(
            f"Unexpected event in text-to-speech stream: {sse.data[:200]}"
        ) from exc


class TTSClient:
    """Synchronous TTS operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def stream(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> AudioStream:
        """
        Stream text-to-speech audio chunks.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            AudioStream object that can be iterated for audio chunks

        Example:
            ```python
            from fishaudio import FishAudio

            client = FishAudio(api_key="...")

            # Stream and process chunks
            for chunk in client.tts.stream(text="Hello world"):
                process_audio_chunk(chunk)

            # Or collect all at once
            audio = client.tts.stream(text="Hello world").collect()
            ```
        """
        warn_if_deprecated_model(model)

        # Build request payload from config
        request = _config_to_tts_request(config, text)

        # Apply direct parameters (always override config when provided)
        if reference_id is not None:
            request.reference_id = reference_id

        if references is not None:
            request.references = references

        if format is not None:
            request.format = format

        if latency is not None:
            request.latency = latency

        if speed is not None:
            request.prosody = Prosody.from_speed_override(speed, base=config.prosody)

        payload = request.model_dump(exclude_none=True)

        # Send the request and return once headers arrive; the body is read
        # lazily so chunks reach the caller as the server produces them.
        response = self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
            stream=True,
        )

        # Create generator and wrap with AudioStream
        def _stream():
            try:
                for chunk in response.iter_bytes():
                    if chunk:
                        yield chunk
            finally:
                response.close()

        return AudioStream(_stream(), on_close=response.close)

    def convert(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> bytes:
        """
        Convert text to speech and return complete audio as bytes.

        This is a convenience method that streams all audio chunks and combines them.
        For chunk-by-chunk processing, use stream() instead.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            Complete audio as bytes

        Example:
            ```python
            from fishaudio import FishAudio
            from fishaudio.utils import play, save

            client = FishAudio(api_key="...")

            # Get complete audio
            audio = client.tts.convert(text="Hello world")

            # Play it
            play(audio)

            # Or save it
            save(audio, "output.mp3")
            ```
        """
        return self.stream(
            text=text,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
            config=config,
            model=model,
            request_options=request_options,
        ).collect()

    def stream_with_timestamps(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> TTSTimestampStream:
        """
        Stream text-to-speech audio together with word-level timestamps.

        Each event carries the next audio bytes and the newest timing snapshot.
        The returned stream keeps the timings up to date in `stream.segments`.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided).
                "opus" is the best fit for playing audio while it streams; "wav" and "pcm"
                are uncompressed, which keeps sample positions exact.
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            TTSTimestampStream that yields TTSTimestampEvent objects

        Example:
            ```python
            from fishaudio import FishAudio

            client = FishAudio(api_key="...")

            with client.tts.stream_with_timestamps(text="Hello world") as stream:
                for event in stream:
                    player.write(event.audio)
                    show_captions(stream.segments)  # timings received so far

            # Or collect the audio and final timings at once
            result = client.tts.stream_with_timestamps(text="Hello world").collect()
            ```
        """
        warn_if_deprecated_model(model)

        content = _build_tts_payload(
            text,
            config,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
        )

        # Return once headers arrive; events are read lazily as they are produced.
        response = self._client.request(
            "POST",
            _TIMESTAMP_PATH,
            headers={**_TIMESTAMP_HEADERS, "model": model},
            content=content,
            request_options=request_options,
            stream=True,
        )

        def _events():
            decoder = SSEDecoder()
            try:
                for chunk in response.iter_bytes():
                    for sse in decoder.feed(chunk):
                        event = _parse_timestamp_event(sse)
                        if event is not None:
                            yield event
            finally:
                response.close()

        return TTSTimestampStream(_events(), on_close=response.close)

    def convert_with_timestamps(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> TTSTimestampResult:
        """
        Convert text to speech and return the audio with word-level timestamps.

        This is a convenience method that reads the whole stream. To use audio
        and timings while they arrive, use stream_with_timestamps() instead.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided).
                "opus" is the best fit for playing audio while it streams; "wav" and "pcm"
                are uncompressed, which keeps sample positions exact.
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            TTSTimestampResult with the complete audio, the timing of each word
            in seconds from the start of the audio, and the audio duration.
            When the API has no timings for the text (for example text without
            words), `segments` is empty and `duration` is None.

        Example:
            ```python
            from fishaudio import FishAudio
            from fishaudio.utils import save

            client = FishAudio(api_key="...")

            result = client.tts.convert_with_timestamps(text="Hello world")
            save(result.audio, "output.mp3")

            for segment in result.segments:
                print(f"{segment.start:.2f}-{segment.end:.2f} {segment.text}")
            ```
        """
        return self.stream_with_timestamps(
            text=text,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
            config=config,
            model=model,
            request_options=request_options,
        ).collect()

    def stream_websocket(
        self,
        text_stream: Iterable[Union[str, TextEvent, FlushEvent]],
        *,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        max_workers: int = 10,
        ws_options: Optional[WebSocketOptions] = None,
    ) -> Iterator[bytes]:
        """
        Stream text and receive audio in real-time via WebSocket.

        Perfect for conversational AI, live captioning, and streaming applications.

        Args:
            text_stream: Iterator of text chunks to stream
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            max_workers: ThreadPoolExecutor workers for concurrent sender
            ws_options: WebSocket connection options for configuring timeouts, message size limits, etc.
                Useful for long-running generations that may exceed default timeout values.
                See WebSocketOptions class for available parameters.

        Returns:
            Iterator of audio bytes

        Example:
            ```python
            from fishaudio import FishAudio, TTSConfig, ReferenceAudio, WebSocketOptions

            client = FishAudio(api_key="...")

            def text_generator():
                yield "Hello, "
                yield "this is "
                yield "streaming text!"

            # Simple usage with defaults
            with open("output.mp3", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(text_generator()):
                    f.write(audio_chunk)

            # With format and speed parameters
            with open("output.wav", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    format="wav",
                    speed=1.3
                ):
                    f.write(audio_chunk)

            # With reference_id parameter
            with open("output.mp3", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(text_generator(), reference_id="your_model_id"):
                    f.write(audio_chunk)

            # With references parameter
            with open("output.mp3", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    references=[ReferenceAudio(audio=audio_bytes, text="sample")]
                ):
                    f.write(audio_chunk)

            # With WebSocket options for long-running generations
            # Useful if you're generating very long responses that may take >20 seconds
            ws_options = WebSocketOptions(keepalive_ping_timeout_seconds=60.0)
            with open("output.mp3", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    ws_options=ws_options
                ):
                    f.write(audio_chunk)

            # Parameters override config values
            config = TTSConfig(format="mp3", latency="balanced")
            with open("output.wav", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    format="wav",  # Parameter wins
                    config=config
                ):
                    f.write(audio_chunk)
            ```
        """
        warn_if_deprecated_model(model)

        # Build TTSRequest from config
        tts_request = _config_to_tts_request(config, text="")

        # Apply direct parameters (always override config when provided)
        if reference_id is not None:
            tts_request.reference_id = reference_id

        if references is not None:
            tts_request.references = references

        if format is not None:
            tts_request.format = format

        if latency is not None:
            tts_request.latency = latency

        if speed is not None:
            tts_request.prosody = Prosody.from_speed_override(
                speed, base=config.prosody
            )

        # Prepare WebSocket connection kwargs
        ws_kwargs = ws_options.to_httpx_ws_kwargs() if ws_options else {}

        executor = ThreadPoolExecutor(max_workers=max_workers)

        try:
            ws: WebSocketSession
            with connect_ws(
                "/v1/tts/live",
                client=self._client.client,
                headers=self._client.get_headers({"model": model}),
                **ws_kwargs,
            ) as ws:

                def sender():
                    ws.send_bytes(
                        ormsgpack.packb(StartEvent(request=tts_request).model_dump())
                    )
                    # Normalize strings to TextEvent
                    for item in text_stream:
                        event = _normalize_to_event(item)
                        ws.send_bytes(ormsgpack.packb(event.model_dump()))
                    ws.send_bytes(ormsgpack.packb(CloseEvent().model_dump()))

                sender_future = executor.submit(sender)

                try:
                    # Process incoming audio messages
                    yield from iter_websocket_audio(ws)

                    sender_future.result()
                finally:
                    # Stop httpx-ws's reader thread before the socket is closed so it
                    # cannot read from a reused fd belonging to the next connection.
                    drain_reader(ws)
        finally:
            executor.shutdown(wait=False)


class AsyncTTSClient:
    """Asynchronous TTS operations."""

    def __init__(self, client_wrapper: AsyncClientWrapper):
        self._client = client_wrapper

    async def stream(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> AsyncAudioStream:
        """
        Stream text-to-speech audio chunks (async).

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            AsyncAudioStream object that can be iterated for audio chunks

        Example:
            ```python
            from fishaudio import AsyncFishAudio

            client = AsyncFishAudio(api_key="...")

            # Stream and process chunks
            async for chunk in await client.tts.stream(text="Hello world"):
                await process_audio_chunk(chunk)

            # Or collect all at once
            stream = await client.tts.stream(text="Hello world")
            audio = await stream.collect()
            ```
        """
        warn_if_deprecated_model(model)

        # Build request payload from config
        request = _config_to_tts_request(config, text)

        # Apply direct parameters (always override config when provided)
        if reference_id is not None:
            request.reference_id = reference_id

        if references is not None:
            request.references = references

        if format is not None:
            request.format = format

        if latency is not None:
            request.latency = latency

        if speed is not None:
            request.prosody = Prosody.from_speed_override(speed, base=config.prosody)

        payload = request.model_dump(exclude_none=True)

        # Send the request and return once headers arrive; the body is read
        # lazily so chunks reach the caller as the server produces them.
        response = await self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
            stream=True,
        )

        # Create async generator and wrap with AsyncAudioStream
        async def _stream():
            try:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await response.aclose()

        return AsyncAudioStream(_stream(), on_close=response.aclose)

    async def convert(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> bytes:
        """
        Convert text to speech and return complete audio as bytes (async).

        This is a convenience method that streams all audio chunks and combines them.
        For chunk-by-chunk processing, use stream() instead.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            Complete audio as bytes

        Example:
            ```python
            from fishaudio import AsyncFishAudio
            from fishaudio.utils import play, save

            client = AsyncFishAudio(api_key="...")

            # Get complete audio
            audio = await client.tts.convert(text="Hello world")

            # Play it
            play(audio)

            # Or save it
            save(audio, "output.mp3")
            ```
        """
        stream = await self.stream(
            text=text,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
            config=config,
            model=model,
            request_options=request_options,
        )
        return await stream.collect()

    async def stream_with_timestamps(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> AsyncTTSTimestampStream:
        """
        Stream text-to-speech audio together with word-level timestamps (async).

        Each event carries the next audio bytes and the newest timing snapshot.
        The returned stream keeps the timings up to date in `stream.segments`.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided).
                "opus" is the best fit for playing audio while it streams; "wav" and "pcm"
                are uncompressed, which keeps sample positions exact.
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            AsyncTTSTimestampStream that yields TTSTimestampEvent objects

        Example:
            ```python
            from fishaudio import AsyncFishAudio

            client = AsyncFishAudio(api_key="...")

            async with await client.tts.stream_with_timestamps(text="Hello world") as stream:
                async for event in stream:
                    await player.write(event.audio)
                    show_captions(stream.segments)  # timings received so far

            # Or collect the audio and final timings at once
            stream = await client.tts.stream_with_timestamps(text="Hello world")
            result = await stream.collect()
            ```
        """
        warn_if_deprecated_model(model)

        content = _build_tts_payload(
            text,
            config,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
        )

        # Return once headers arrive; events are read lazily as they are produced.
        response = await self._client.request(
            "POST",
            _TIMESTAMP_PATH,
            headers={**_TIMESTAMP_HEADERS, "model": model},
            content=content,
            request_options=request_options,
            stream=True,
        )

        async def _events():
            decoder = SSEDecoder()
            try:
                async for chunk in response.aiter_bytes():
                    for sse in decoder.feed(chunk):
                        event = _parse_timestamp_event(sse)
                        if event is not None:
                            yield event
            finally:
                await response.aclose()

        return AsyncTTSTimestampStream(_events(), on_close=response.aclose)

    async def convert_with_timestamps(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        request_options: Optional[RequestOptions] = None,
    ) -> TTSTimestampResult:
        """
        Convert text to speech and return the audio with word-level timestamps (async).

        This is a convenience method that reads the whole stream. To use audio
        and timings while they arrive, use stream_with_timestamps() instead.

        Args:
            text: Text to synthesize
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided).
                "opus" is the best fit for playing audio while it streams; "wav" and "pcm"
                are uncompressed, which keeps sample positions exact.
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            TTSTimestampResult with the complete audio, the timing of each word
            in seconds from the start of the audio, and the audio duration.
            When the API has no timings for the text (for example text without
            words), `segments` is empty and `duration` is None.

        Example:
            ```python
            from fishaudio import AsyncFishAudio
            from fishaudio.utils import save

            client = AsyncFishAudio(api_key="...")

            result = await client.tts.convert_with_timestamps(text="Hello world")
            save(result.audio, "output.mp3")

            for segment in result.segments:
                print(f"{segment.start:.2f}-{segment.end:.2f} {segment.text}")
            ```
        """
        stream = await self.stream_with_timestamps(
            text=text,
            reference_id=reference_id,
            references=references,
            format=format,
            latency=latency,
            speed=speed,
            config=config,
            model=model,
            request_options=request_options,
        )
        return await stream.collect()

    async def stream_websocket(
        self,
        text_stream: AsyncIterable[Union[str, TextEvent, FlushEvent]],
        *,
        reference_id: Optional[str] = None,
        references: Optional[list[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Union[Model, str] = "s2.1-pro",
        ws_options: Optional[WebSocketOptions] = None,
    ):
        """
        Stream text and receive audio in real-time via WebSocket (async).

        Perfect for conversational AI, live captioning, and streaming applications.

        Args:
            text_stream: Async iterator of text chunks to stream
            reference_id: Voice reference ID (overrides config.reference_id if provided)
            references: Reference audio samples (overrides config.references if provided)
            format: Audio format - "mp3", "wav", "pcm", or "opus" (overrides config.format if provided)
            latency: Latency mode - "normal" or "balanced" (overrides config.latency if provided)
            speed: Speech speed multiplier, e.g. 1.5 for 1.5x speed (overrides config.prosody.speed if provided)
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            ws_options: WebSocket connection options for configuring timeouts, message size limits, etc.
                Useful for long-running generations that may exceed default timeout values.
                See WebSocketOptions class for available parameters.

        Returns:
            Async iterator of audio bytes

        Example:
            ```python
            from fishaudio import AsyncFishAudio, TTSConfig, ReferenceAudio, WebSocketOptions

            client = AsyncFishAudio(api_key="...")

            async def text_generator():
                yield "Hello, "
                yield "this is "
                yield "async streaming!"

            # Simple usage with defaults
            async with aiofiles.open("output.mp3", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(text_generator()):
                    await f.write(audio_chunk)

            # With format and speed parameters
            async with aiofiles.open("output.wav", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    format="wav",
                    speed=1.3
                ):
                    await f.write(audio_chunk)

            # With reference_id parameter
            async with aiofiles.open("output.mp3", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(text_generator(), reference_id="your_model_id"):
                    await f.write(audio_chunk)

            # With references parameter
            async with aiofiles.open("output.mp3", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    references=[ReferenceAudio(audio=audio_bytes, text="sample")]
                ):
                    await f.write(audio_chunk)

            # With WebSocket options for long-running generations
            # Useful if you're generating very long responses that may take >20 seconds
            ws_options = WebSocketOptions(keepalive_ping_timeout_seconds=60.0)
            async with aiofiles.open("output.mp3", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    ws_options=ws_options
                ):
                    await f.write(audio_chunk)

            # Parameters override config values
            config = TTSConfig(format="mp3", latency="balanced")
            async with aiofiles.open("output.wav", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(
                    text_generator(),
                    format="wav",  # Parameter wins
                    config=config
                ):
                    await f.write(audio_chunk)
            ```
        """
        warn_if_deprecated_model(model)

        # Build TTSRequest from config
        tts_request = _config_to_tts_request(config, text="")

        # Apply direct parameters (always override config when provided)
        if reference_id is not None:
            tts_request.reference_id = reference_id

        if references is not None:
            tts_request.references = references

        if format is not None:
            tts_request.format = format

        if latency is not None:
            tts_request.latency = latency

        if speed is not None:
            tts_request.prosody = Prosody.from_speed_override(
                speed, base=config.prosody
            )

        # Prepare WebSocket connection kwargs
        ws_kwargs = ws_options.to_httpx_ws_kwargs() if ws_options else {}

        ws: AsyncWebSocketSession
        async with aconnect_ws(
            "/v1/tts/live",
            client=self._client.client,
            headers=self._client.get_headers({"model": model}),
            **ws_kwargs,
        ) as ws:

            async def sender():
                await ws.send_bytes(
                    ormsgpack.packb(StartEvent(request=tts_request).model_dump())
                )
                # Normalize strings to TextEvent
                async for item in text_stream:
                    event = _normalize_to_event(item)
                    await ws.send_bytes(ormsgpack.packb(event.model_dump()))
                await ws.send_bytes(ormsgpack.packb(CloseEvent().model_dump()))

            sender_task = asyncio.create_task(sender())

            # Process incoming audio messages
            async for audio_chunk in aiter_websocket_audio(ws):
                yield audio_chunk

            await sender_task
