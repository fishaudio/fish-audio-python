"""ASR (Automatic Speech Recognition) namespace client."""

from typing import Optional

import ormsgpack

from ..core import OMIT, AsyncClientWrapper, ClientWrapper, RequestOptions
from ..types import ASRResponse


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
        request_options: Optional[RequestOptions] = None,
    ) -> ASRResponse:
        """
        Transcribe audio to text.

        Args:
            audio: Audio file bytes
            language: Language code (e.g., "en", "zh"). Auto-detected if not provided.
            include_timestamps: Whether to include timestamp information for segments
            request_options: Request-level overrides

        Returns:
            ASRResponse with transcription text, duration, and segments

        Example:
            ```python
            client = FishAudio(api_key="...")

            with open("audio.mp3", "rb") as f:
                audio_bytes = f.read()

            result = client.asr.transcribe(audio=audio_bytes, language="en")
            print(result.text)
            for segment in result.segments:
                print(f"{segment.start}-{segment.end}: {segment.text}")
            ```
        """
        # Build request payload
        payload = {
            "audio": audio,
            "ignore_timestamps": not include_timestamps,
        }

        # Add optional fields
        if language is not OMIT:
            payload["language"] = language

        # Make request
        response = self._client.request(
            "POST",
            "/v1/asr",
            headers={"Content-Type": "application/msgpack"},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Parse and return response
        return ASRResponse.model_validate(response.json())


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
        request_options: Optional[RequestOptions] = None,
    ) -> ASRResponse:
        """
        Transcribe audio to text (async).

        Args:
            audio: Audio file bytes
            language: Language code (e.g., "en", "zh"). Auto-detected if not provided.
            include_timestamps: Whether to include timestamp information for segments
            request_options: Request-level overrides

        Returns:
            ASRResponse with transcription text, duration, and segments

        Example:
            ```python
            client = AsyncFishAudio(api_key="...")

            async with aiofiles.open("audio.mp3", "rb") as f:
                audio_bytes = await f.read()

            result = await client.asr.transcribe(audio=audio_bytes, language="en")
            print(result.text)
            for segment in result.segments:
                print(f"{segment.start}-{segment.end}: {segment.text}")
            ```
        """
        # Build request payload
        payload = {
            "audio": audio,
            "ignore_timestamps": not include_timestamps,
        }

        # Add optional fields
        if language is not OMIT:
            payload["language"] = language

        # Make request
        response = await self._client.request(
            "POST",
            "/v1/asr",
            headers={"Content-Type": "application/msgpack"},
            content=ormsgpack.packb(payload),
            request_options=request_options,
        )

        # Parse and return response
        return ASRResponse.model_validate(response.json())
