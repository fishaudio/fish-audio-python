"""TTS (Text-to-Speech) namespace client."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterable, Iterable, Iterator, List, Optional, Union

import ormsgpack
from httpx_ws import AsyncWebSocketSession, WebSocketSession, aconnect_ws, connect_ws

from .realtime import aiter_websocket_audio, iter_websocket_audio
from ..core import AsyncClientWrapper, ClientWrapper, RequestOptions, WebSocketOptions
from ..core.iterators import AsyncAudioStream, AudioStream
from ..types import (
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
)


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


class TTSClient:
    """Synchronous TTS operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def stream(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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

        # Make request with streaming
        response = self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Create generator and wrap with AudioStream
        def _stream():
            for chunk in response.iter_bytes():
                if chunk:
                    yield chunk

        return AudioStream(_stream())

    def convert(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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

    def stream_websocket(
        self,
        text_stream: Iterable[Union[str, TextEvent, FlushEvent]],
        *,
        reference_id: Optional[str] = None,
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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

                # Process incoming audio messages
                for audio_chunk in iter_websocket_audio(ws):
                    yield audio_chunk

                sender_future.result()
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
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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

        # Make request with streaming
        response = await self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Create async generator and wrap with AsyncAudioStream
        async def _stream():
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk

        return AsyncAudioStream(_stream())

    async def convert(
        self,
        *,
        text: str,
        reference_id: Optional[str] = None,
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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

    async def stream_websocket(
        self,
        text_stream: AsyncIterable[Union[str, TextEvent, FlushEvent]],
        *,
        reference_id: Optional[str] = None,
        references: Optional[List[ReferenceAudio]] = None,
        format: Optional[AudioFormat] = None,
        latency: Optional[LatencyMode] = None,
        speed: Optional[float] = None,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
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
