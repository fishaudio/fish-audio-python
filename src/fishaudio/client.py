"""Main Fish Audio client classes."""

from typing import Optional

import httpx

from .core import AsyncClientWrapper, ClientWrapper
from .core.client_wrapper import HeaderProvider
from .core.tracing import opentelemetry_headers
from .resources import (
    AccountClient,
    ASRClient,
    AsyncAccountClient,
    AsyncASRClient,
    AsyncTTSClient,
    AsyncVoicesClient,
    TTSClient,
    VoicesClient,
)


class FishAudio:
    """
    Synchronous Fish Audio API client.

    Example:
        ```python
        from fishaudio import FishAudio

        client = FishAudio(api_key="your_api_key")

        # Generate speech
        audio = client.tts.convert(text="Hello world")
        with open("output.mp3", "wb") as f:
            for chunk in audio:
                f.write(chunk)

        # List voices
        voices = client.voices.list(page_size=20)
        print(f"Found {voices.total} voices")
        ```
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        timeout: float = 240.0,
        httpx_client: Optional[httpx.Client] = None,
        header_provider: Optional[HeaderProvider] = opentelemetry_headers,
    ):
        """
        Initialize Fish Audio client.

        Args:
            api_key: API key (can also use FISH_API_KEY env var)
            base_url: API base URL
            timeout: Request timeout in seconds
            httpx_client: Optional custom HTTP client
            header_provider: Function the SDK calls for every request and
                WebSocket handshake, right before it is sent, to add headers such
                as the W3C ``traceparent`` of your current request. It takes no
                arguments and returns a mapping of header names to values, or
                None. The default, ``opentelemetry_headers``, sends the current
                OpenTelemetry span as ``traceparent`` when your app uses
                OpenTelemetry, so you can find your requests in Fish Audio's
                traces; it sends no other trace data. Pass None to turn this
                off, or your own function to replace it. It runs on the thread (sync client) or in the task (async
                client) that makes the call, so it can read ``contextvars`` and
                the current OpenTelemetry span; keep it fast and free of I/O.
                Headers the SDK sets (``Authorization``, ``model``,
                ``User-Agent``, ``Content-Type``, WebSocket handshake headers),
                per-call ``additional_headers`` and headers on ``httpx_client``
                win over it. An exception it raises fails the call, unchanged,
                before anything is sent. If a response shows that Fish Audio
                did not continue the ``traceparent`` the SDK sent, the SDK
                issues one ``TraceNotContinuedWarning`` per process. See the
                README's "Tracing" section.
        """
        self._client_wrapper = ClientWrapper(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            httpx_client=httpx_client,
            header_provider=header_provider,
        )

        # Lazy-loaded namespace clients
        self._tts: Optional[TTSClient] = None
        self._asr: Optional[ASRClient] = None
        self._voices: Optional[VoicesClient] = None
        self._account: Optional[AccountClient] = None

    @property
    def tts(self) -> TTSClient:
        """Access TTS (text-to-speech) operations."""
        if self._tts is None:
            self._tts = TTSClient(self._client_wrapper)
        return self._tts

    @property
    def asr(self) -> ASRClient:
        """Access ASR (speech-to-text) operations."""
        if self._asr is None:
            self._asr = ASRClient(self._client_wrapper)
        return self._asr

    @property
    def voices(self) -> VoicesClient:
        """Access voice management operations."""
        if self._voices is None:
            self._voices = VoicesClient(self._client_wrapper)
        return self._voices

    @property
    def account(self) -> AccountClient:
        """Access account/billing operations."""
        if self._account is None:
            self._account = AccountClient(self._client_wrapper)
        return self._account

    def close(self) -> None:
        """Close the HTTP client."""
        self._client_wrapper.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncFishAudio:
    """
    Asynchronous Fish Audio API client.

    Example:
        ```python
        from fishaudio import AsyncFishAudio

        async def main():
            client = AsyncFishAudio(api_key="your_api_key")

            # Generate speech
            audio = client.tts.convert(text="Hello world")
            async with aiofiles.open("output.mp3", "wb") as f:
                async for chunk in audio:
                    await f.write(chunk)

            # List voices
            voices = await client.voices.list(page_size=20)
            print(f"Found {voices.total} voices")

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fish.audio",
        timeout: float = 240.0,
        httpx_client: Optional[httpx.AsyncClient] = None,
        header_provider: Optional[HeaderProvider] = opentelemetry_headers,
    ):
        """
        Initialize async Fish Audio client.

        Args:
            api_key: API key (can also use FISH_API_KEY env var)
            base_url: API base URL
            timeout: Request timeout in seconds
            httpx_client: Optional custom async HTTP client
            header_provider: Function the SDK calls for every request and
                WebSocket handshake, right before it is sent, to add headers such
                as the W3C ``traceparent`` of your current request. It takes no
                arguments and returns a mapping of header names to values, or
                None. The default, ``opentelemetry_headers``, sends the current
                OpenTelemetry span as ``traceparent`` when your app uses
                OpenTelemetry, so you can find your requests in Fish Audio's
                traces; it sends no other trace data. Pass None to turn this
                off, or your own function to replace it. It runs on the thread (sync client) or in the task (async
                client) that makes the call, so it can read ``contextvars`` and
                the current OpenTelemetry span; keep it fast and free of I/O.
                Headers the SDK sets (``Authorization``, ``model``,
                ``User-Agent``, ``Content-Type``, WebSocket handshake headers),
                per-call ``additional_headers`` and headers on ``httpx_client``
                win over it. An exception it raises fails the call, unchanged,
                before anything is sent. If a response shows that Fish Audio
                did not continue the ``traceparent`` the SDK sent, the SDK
                issues one ``TraceNotContinuedWarning`` per process. See the
                README's "Tracing" section.
        """
        self._client_wrapper = AsyncClientWrapper(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            httpx_client=httpx_client,
            header_provider=header_provider,
        )

        # Lazy-loaded namespace clients
        self._tts: Optional[AsyncTTSClient] = None
        self._asr: Optional[AsyncASRClient] = None
        self._voices: Optional[AsyncVoicesClient] = None
        self._account: Optional[AsyncAccountClient] = None

    @property
    def tts(self) -> AsyncTTSClient:
        """Access TTS (text-to-speech) operations."""
        if self._tts is None:
            self._tts = AsyncTTSClient(self._client_wrapper)
        return self._tts

    @property
    def asr(self) -> AsyncASRClient:
        """Access ASR (speech-to-text) operations."""
        if self._asr is None:
            self._asr = AsyncASRClient(self._client_wrapper)
        return self._asr

    @property
    def voices(self) -> AsyncVoicesClient:
        """Access voice management operations."""
        if self._voices is None:
            self._voices = AsyncVoicesClient(self._client_wrapper)
        return self._voices

    @property
    def account(self) -> AsyncAccountClient:
        """Access account/billing operations."""
        if self._account is None:
            self._account = AsyncAccountClient(self._client_wrapper)
        return self._account

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client_wrapper.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
