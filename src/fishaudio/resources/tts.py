"""TTS (Text-to-Speech) namespace client."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterable, Iterable, Iterator, Optional, Union

import ormsgpack
from httpx_ws import AsyncWebSocketSession, WebSocketSession, aconnect_ws, connect_ws

from .realtime import aiter_websocket_audio, iter_websocket_audio
from ..core import AsyncClientWrapper, ClientWrapper, RequestOptions
from ..types import (
    CloseEvent,
    FlushEvent,
    Model,
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

    def convert(
        self,
        *,
        text: str,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
        request_options: Optional[RequestOptions] = None,
    ) -> Iterator[bytes]:
        """
        Convert text to speech.

        Args:
            text: Text to synthesize
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            Iterator of audio bytes

        Example:
            ```python
            from fishaudio import FishAudio, TTSConfig

            client = FishAudio(api_key="...")

            # Simple usage with defaults
            audio = client.tts.convert(text="Hello world")

            # Custom configuration
            config = TTSConfig(format="wav", mp3_bitrate=192)
            audio = client.tts.convert(text="Hello world", config=config)

            with open("output.mp3", "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            ```
        """
        # Build request payload from config
        request = _config_to_tts_request(config, text)
        payload = request.model_dump(exclude_none=True)

        # Make request with streaming
        response = self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Stream response chunks
        for chunk in response.iter_bytes():
            if chunk:
                yield chunk

    def stream_websocket(
        self,
        text_stream: Iterable[Union[str, TextEvent, FlushEvent]],
        *,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
        max_workers: int = 10,
    ) -> Iterator[bytes]:
        """
        Stream text and receive audio in real-time via WebSocket.

        Perfect for conversational AI, live captioning, and streaming applications.

        Args:
            text_stream: Iterator of text chunks to stream
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            max_workers: ThreadPoolExecutor workers for concurrent sender

        Returns:
            Iterator of audio bytes

        Example:
            ```python
            from fishaudio import FishAudio, TTSConfig

            client = FishAudio(api_key="...")

            def text_generator():
                yield "Hello, "
                yield "this is "
                yield "streaming text!"

            # Simple usage with defaults
            with open("output.mp3", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(text_generator()):
                    f.write(audio_chunk)

            # Custom configuration
            config = TTSConfig(format="wav", latency="normal")
            with open("output.wav", "wb") as f:
                for audio_chunk in client.tts.stream_websocket(text_generator(), config=config):
                    f.write(audio_chunk)
            ```
        """
        # Build TTSRequest from config
        tts_request = _config_to_tts_request(config, text="")

        executor = ThreadPoolExecutor(max_workers=max_workers)

        try:
            ws: WebSocketSession
            with connect_ws(
                "/v1/tts/live",
                client=self._client.client,
                headers={
                    "model": model,
                    "Authorization": f"Bearer {self._client.api_key}",
                },
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

    async def convert(
        self,
        *,
        text: str,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
        request_options: Optional[RequestOptions] = None,
    ):
        """
        Convert text to speech (async).

        Args:
            text: Text to synthesize
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use
            request_options: Request-level overrides

        Returns:
            Async iterator of audio bytes

        Example:
            ```python
            from fishaudio import AsyncFishAudio, TTSConfig

            client = AsyncFishAudio(api_key="...")

            # Simple usage with defaults
            audio = await client.tts.convert(text="Hello world")

            # Custom configuration
            config = TTSConfig(format="wav", mp3_bitrate=192)
            audio = await client.tts.convert(text="Hello world", config=config)

            async with aiofiles.open("output.mp3", "wb") as f:
                async for chunk in audio:
                    await f.write(chunk)
            ```
        """
        # Build request payload from config
        request = _config_to_tts_request(config, text)
        payload = request.model_dump(exclude_none=True)

        # Make request with streaming
        response = await self._client.request(
            "POST",
            "/v1/tts",
            headers={"Content-Type": "application/msgpack", "model": model},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Stream response chunks
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk

    async def stream_websocket(
        self,
        text_stream: AsyncIterable[Union[str, TextEvent, FlushEvent]],
        *,
        config: TTSConfig = TTSConfig(),
        model: Model = "s1",
    ):
        """
        Stream text and receive audio in real-time via WebSocket (async).

        Perfect for conversational AI, live captioning, and streaming applications.

        Args:
            text_stream: Async iterator of text chunks to stream
            config: TTS configuration (audio settings, voice, model parameters)
            model: TTS model to use

        Returns:
            Async iterator of audio bytes

        Example:
            ```python
            from fishaudio import AsyncFishAudio, TTSConfig

            client = AsyncFishAudio(api_key="...")

            async def text_generator():
                yield "Hello, "
                yield "this is "
                yield "async streaming!"

            # Simple usage with defaults
            async with aiofiles.open("output.mp3", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(text_generator()):
                    await f.write(audio_chunk)

            # Custom configuration
            config = TTSConfig(format="wav", latency="normal")
            async with aiofiles.open("output.wav", "wb") as f:
                async for audio_chunk in client.tts.stream_websocket(text_generator(), config=config):
                    await f.write(audio_chunk)
            ```
        """
        # Build TTSRequest from config
        tts_request = _config_to_tts_request(config, text="")

        ws: AsyncWebSocketSession
        async with aconnect_ws(
            "/v1/tts/live",
            client=self._client.client,
            headers={"model": model, "Authorization": f"Bearer {self._client.api_key}"},
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
