"""ASR (Automatic Speech Recognition) namespace client."""

from collections.abc import AsyncIterable, Iterable
from typing import Optional, Union

import ormsgpack
from httpx_ws import aconnect_ws, connect_ws

from fishaudio.core import (
    OMIT,
    AsyncClientWrapper,
    ClientWrapper,
    RequestOptions,
    WebSocketOptions,
)
from fishaudio.types import (
    ASRContext,
    ASRRealtimeConfig,
    ASRRealtimeControl,
    ASRResponse,
    ASRResults,
    ASRSampleRate,
    ASRTurnDetection,
    TurnDetectionMode,
)

from .asr_realtime import REALTIME_PATH, ASRRealtimeStream, AsyncASRRealtimeStream


def _realtime_config(
    config: ASRRealtimeConfig,
    *,
    sample_rate: Optional[ASRSampleRate],
    turn_detection: Optional[TurnDetectionMode],
    eager: Optional[bool],
    drafts: Optional[bool],
    diarize: Optional[bool],
    terms: Optional[list[str]],
) -> ASRRealtimeConfig:
    """Apply direct parameters on top of config (they win when provided)."""
    config = config.model_copy(deep=True)
    if sample_rate is not None:
        config.sample_rate = sample_rate
    if turn_detection is not None or eager is not None:
        config.turn_detection = config.turn_detection or ASRTurnDetection()
        if turn_detection is not None:
            config.turn_detection.mode = turn_detection
        if eager is not None:
            config.turn_detection.eager = eager
    if drafts is not None or diarize is not None:
        config.results = config.results or ASRResults()
        if drafts is not None:
            config.results.drafts = drafts
        if diarize is not None:
            config.results.diarize = diarize
    if terms is not None:
        config.context = config.context or ASRContext()
        config.context.terms = terms
    return config


class ASRClient:
    """Synchronous ASR operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def transcribe(
        self,
        *,
        audio: bytes,
        language: Optional[str] = OMIT,
        include_timestamps: bool = True,
        model: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> ASRResponse:
        """
        Transcribe audio to text.

        Args:
            audio: Audio file bytes
            language: Language code (e.g., "en", "zh"). Auto-detected if not provided.
            include_timestamps: Whether to include timestamp information for segments
                (and speaker turns, on models that return them)
            model: ASR model, e.g. "transcribe-1-pro" (recommended). Sent as the
                ``model`` header and takes precedence over one in request_options.
                If not provided and request_options sets no ``model`` header, the
                request runs on the API's default model, transcribe-1
            request_options: Request-level overrides

        Returns:
            ASRResponse with transcription text, duration (in seconds), and segments,
            plus language, request ID and speaker turns when the API returns them

        Example:
            ```python
            client = FishAudio(api_key="...")

            with open("audio.mp3", "rb") as f:
                audio_bytes = f.read()

            result = client.asr.transcribe(
                audio=audio_bytes, model="transcribe-1-pro"
            )
            print(result.text)
            for segment in result.segments:
                print(f"{segment.start}-{segment.end}: {segment.text}")
            ```
        """
        # Build request payload
        payload = {
            "audio": audio,
            "ignore_timestamps": not include_timestamps,
            **({"language": language} if language is not OMIT else {}),
        }

        # Make request
        response = self._client.request(
            "POST",
            "/v1/asr",
            headers={
                "Content-Type": "application/msgpack",
                **({"model": model} if model is not None else {}),
            },
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Parse and return response
        return ASRResponse.model_validate(response.json())

    def stream_websocket(
        self,
        audio_stream: Iterable[Union[bytes, ASRRealtimeControl]],
        *,
        sample_rate: Optional[ASRSampleRate] = None,
        turn_detection: Optional[TurnDetectionMode] = None,
        eager: Optional[bool] = None,
        drafts: Optional[bool] = None,
        diarize: Optional[bool] = None,
        terms: Optional[list[str]] = None,
        config: ASRRealtimeConfig = ASRRealtimeConfig(),
        model: str = "transcribe-stream-1",
        ws_options: Optional[WebSocketOptions] = None,
    ) -> ASRRealtimeStream:
        """
        Stream audio and receive transcripts in real-time via WebSocket.

        Audio is divided into turns. Each turn ends with one committed event that
        holds its final transcript; with drafts=True you also get live draft events
        while the turn is open. The session ends with a session_done event once
        audio_stream is exhausted.

        By default the transcript text starts with a speaker tag, e.g.
        ``<|speaker:0|> Hello.``, and can contain sound tags such as ``[laughter]``.
        Pass diarize=False for text without speaker tags; sound tags are turned off
        with config=ASRRealtimeConfig(results=ASRResults(tag_audio_events=False)).

        Args:
            audio_stream: Iterator of raw audio chunks: 16-bit little-endian mono PCM,
                ideally 20-40 ms each, sent as you capture them. It can also yield
                control messages (e.g. ASRFinalizeEvent()), which are sent at that
                position in the audio
            sample_rate: Sample rate of the audio in Hz: 8000, 12000, 16000, 22050,
                24000, 32000, 44100 or 48000 (overrides config.sample_rate if provided)
            turn_detection: When a turn ends - "auto" (the server judges that the user
                has finished), "vad" (after a fixed silence) or "manual" (when you send
                finalize) (overrides config.turn_detection.mode if provided)
            eager: Send eager_end_of_turn events in auto mode
                (overrides config.turn_detection.eager if provided)
            drafts: Send live draft events (overrides config.results.drafts if provided)
            diarize: Speaker tags such as ``<|speaker:0|>`` in the transcript text. The
                server adds them by default; pass False for plain text
                (overrides config.results.diarize if provided)
            terms: Names, products and jargon to recognize
                (overrides config.context.terms if provided)
            config: Session configuration (audio, turn detection, results, context)
            model: Realtime speech-to-text model
            ws_options: WebSocket connection options for configuring timeouts, message size limits, etc.
                See WebSocketOptions class for available parameters.

        Returns:
            ASRRealtimeStream: an iterator of typed events (check event.type), with
            methods to send control messages during the session: finalize(),
            agent_speaking(), add_context() and configure()

        Raises:
            ASRRealtimeError: If the server reports an error that ends the session, or
                closes the connection abnormally (see error_type and close_code)
            APIError: If the connection is refused (e.g. AuthenticationError for 401)
            WebSocketError: If the connection is lost

        Example:
            ```python
            import wave

            from fishaudio import FishAudio

            client = FishAudio(api_key="...")

            def audio_chunks():
                with wave.open("speech.wav", "rb") as wav:  # 16-bit mono PCM
                    while chunk := wav.readframes(640):  # 40 ms at 16 kHz
                        yield chunk

            # Final transcript of each turn (diarize=False: no <|speaker:0|> tags)
            for event in client.asr.stream_websocket(
                audio_chunks(), sample_rate=16000, diarize=False
            ):
                if event.type == "committed":
                    print(event.text)

            # Live captions: drafts while the turn is open, then the final text
            for event in client.asr.stream_websocket(audio_chunks(), drafts=True):
                if event.type == "draft":
                    print("...", event.text)
                elif event.type == "committed":
                    print(event.text)

            # Voice agent: answer the user's turns, and tell the server while you speak
            with client.asr.stream_websocket(audio_chunks(), eager=True) as stream:
                for event in stream:
                    if event.type == "committed" and event.user_turn:
                        stream.agent_speaking(True)
                        ...  # reply, then stream.agent_speaking(False)
            ```
        """
        ws_kwargs = ws_options.to_httpx_ws_kwargs() if ws_options else {}
        headers = self._client.get_headers({"model": model})
        client = self._client.client

        return ASRRealtimeStream(
            lambda: connect_ws(
                REALTIME_PATH, client=client, headers=headers, **ws_kwargs
            ),
            _realtime_config(
                config,
                sample_rate=sample_rate,
                turn_detection=turn_detection,
                eager=eager,
                drafts=drafts,
                diarize=diarize,
                terms=terms,
            ),
            audio_stream,
        )


class AsyncASRClient:
    """Asynchronous ASR operations."""

    def __init__(self, client_wrapper: AsyncClientWrapper):
        self._client = client_wrapper

    async def transcribe(
        self,
        *,
        audio: bytes,
        language: Optional[str] = OMIT,
        include_timestamps: bool = True,
        model: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> ASRResponse:
        """
        Transcribe audio to text (async).

        Args:
            audio: Audio file bytes
            language: Language code (e.g., "en", "zh"). Auto-detected if not provided.
            include_timestamps: Whether to include timestamp information for segments
                (and speaker turns, on models that return them)
            model: ASR model, e.g. "transcribe-1-pro" (recommended). Sent as the
                ``model`` header and takes precedence over one in request_options.
                If not provided and request_options sets no ``model`` header, the
                request runs on the API's default model, transcribe-1
            request_options: Request-level overrides

        Returns:
            ASRResponse with transcription text, duration (in seconds), and segments,
            plus language, request ID and speaker turns when the API returns them

        Example:
            ```python
            client = AsyncFishAudio(api_key="...")

            async with aiofiles.open("audio.mp3", "rb") as f:
                audio_bytes = await f.read()

            result = await client.asr.transcribe(
                audio=audio_bytes, model="transcribe-1-pro"
            )
            print(result.text)
            for segment in result.segments:
                print(f"{segment.start}-{segment.end}: {segment.text}")
            ```
        """
        # Build request payload
        payload = {
            "audio": audio,
            "ignore_timestamps": not include_timestamps,
            **({"language": language} if language is not OMIT else {}),
        }

        # Make request
        response = await self._client.request(
            "POST",
            "/v1/asr",
            headers={
                "Content-Type": "application/msgpack",
                **({"model": model} if model is not None else {}),
            },
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Parse and return response
        return ASRResponse.model_validate(response.json())

    def stream_websocket(
        self,
        audio_stream: AsyncIterable[Union[bytes, ASRRealtimeControl]],
        *,
        sample_rate: Optional[ASRSampleRate] = None,
        turn_detection: Optional[TurnDetectionMode] = None,
        eager: Optional[bool] = None,
        drafts: Optional[bool] = None,
        diarize: Optional[bool] = None,
        terms: Optional[list[str]] = None,
        config: ASRRealtimeConfig = ASRRealtimeConfig(),
        model: str = "transcribe-stream-1",
        ws_options: Optional[WebSocketOptions] = None,
    ) -> AsyncASRRealtimeStream:
        """
        Stream audio and receive transcripts in real-time via WebSocket (async).

        Audio is divided into turns. Each turn ends with one committed event that
        holds its final transcript; with drafts=True you also get live draft events
        while the turn is open. The session ends with a session_done event once
        audio_stream is exhausted.

        By default the transcript text starts with a speaker tag, e.g.
        ``<|speaker:0|> Hello.``, and can contain sound tags such as ``[laughter]``.
        Pass diarize=False for text without speaker tags; sound tags are turned off
        with config=ASRRealtimeConfig(results=ASRResults(tag_audio_events=False)).

        Args:
            audio_stream: Async iterator of raw audio chunks: 16-bit little-endian mono PCM,
                ideally 20-40 ms each, sent as you capture them. It can also yield
                control messages (e.g. ASRFinalizeEvent()), which are sent at that
                position in the audio
            sample_rate: Sample rate of the audio in Hz: 8000, 12000, 16000, 22050,
                24000, 32000, 44100 or 48000 (overrides config.sample_rate if provided)
            turn_detection: When a turn ends - "auto" (the server judges that the user
                has finished), "vad" (after a fixed silence) or "manual" (when you send
                finalize) (overrides config.turn_detection.mode if provided)
            eager: Send eager_end_of_turn events in auto mode
                (overrides config.turn_detection.eager if provided)
            drafts: Send live draft events (overrides config.results.drafts if provided)
            diarize: Speaker tags such as ``<|speaker:0|>`` in the transcript text. The
                server adds them by default; pass False for plain text
                (overrides config.results.diarize if provided)
            terms: Names, products and jargon to recognize
                (overrides config.context.terms if provided)
            config: Session configuration (audio, turn detection, results, context)
            model: Realtime speech-to-text model
            ws_options: WebSocket connection options for configuring timeouts, message size limits, etc.
                See WebSocketOptions class for available parameters.

        Returns:
            AsyncASRRealtimeStream: an async iterator of typed events (check event.type), with
            methods to send control messages during the session: finalize(),
            agent_speaking(), add_context() and configure()

        Raises:
            ASRRealtimeError: If the server reports an error that ends the session, or
                closes the connection abnormally (see error_type and close_code)
            APIError: If the connection is refused (e.g. AuthenticationError for 401)
            WebSocketError: If the connection is lost

        Example:
            ```python
            import wave

            from fishaudio import AsyncFishAudio

            client = AsyncFishAudio(api_key="...")

            async def audio_chunks():
                with wave.open("speech.wav", "rb") as wav:  # 16-bit mono PCM
                    while chunk := wav.readframes(640):  # 40 ms at 16 kHz
                        yield chunk

            # Final transcript of each turn (diarize=False: no <|speaker:0|> tags)
            async for event in client.asr.stream_websocket(
                audio_chunks(), sample_rate=16000, diarize=False
            ):
                if event.type == "committed":
                    print(event.text)

            # Live captions: drafts while the turn is open, then the final text
            async for event in client.asr.stream_websocket(audio_chunks(), drafts=True):
                if event.type == "draft":
                    print("...", event.text)
                elif event.type == "committed":
                    print(event.text)

            # Voice agent: answer the user's turns, and tell the server while you speak
            async with client.asr.stream_websocket(audio_chunks(), eager=True) as stream:
                async for event in stream:
                    if event.type == "committed" and event.user_turn:
                        await stream.agent_speaking(True)
                        ...  # reply, then await stream.agent_speaking(False)
            ```
        """
        ws_kwargs = ws_options.to_httpx_ws_kwargs() if ws_options else {}
        headers = self._client.get_headers({"model": model})
        client = self._client.client

        return AsyncASRRealtimeStream(
            lambda: aconnect_ws(
                REALTIME_PATH, client=client, headers=headers, **ws_kwargs
            ),
            _realtime_config(
                config,
                sample_rate=sample_rate,
                turn_detection=turn_detection,
                eager=eager,
                drafts=drafts,
                diarize=diarize,
                terms=terms,
            ),
            audio_stream,
        )
