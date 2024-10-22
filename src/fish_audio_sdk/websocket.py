import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator, AsyncIterable, Generator, Iterable

import httpx
import ormsgpack
from httpx_ws import WebSocketDisconnect, connect_ws, aconnect_ws

from .exceptions import WebSocketErr

from .schemas import CloseEvent, StartEvent, TTSRequest, TextEvent


class WebSocketSession:
    def __init__(
        self,
        apikey: str,
        *,
        base_url: str = "https://api.fish.audio",
        max_workers: int = 10,
    ):
        self._apikey = apikey
        self._base_url = base_url
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._apikey}"},
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._client.close()

    def tts(
        self, request: TTSRequest, text_stream: Iterable[str]
    ) -> Generator[bytes, None, None]:
        with connect_ws("/v1/tts/live", client=self._client) as ws:

            def sender():
                ws.send_bytes(
                    ormsgpack.packb(
                        StartEvent(request=request),
                        option=ormsgpack.OPT_SERIALIZE_PYDANTIC,
                    )
                )
                for text in text_stream:
                    ws.send_bytes(
                        ormsgpack.packb(
                            TextEvent(text=text),
                            option=ormsgpack.OPT_SERIALIZE_PYDANTIC,
                        )
                    )
                ws.send_bytes(
                    ormsgpack.packb(
                        CloseEvent(), option=ormsgpack.OPT_SERIALIZE_PYDANTIC
                    )
                )

            sender_future = self._executor.submit(sender)

            while True:
                try:
                    message = ws.receive_bytes()
                    data = ormsgpack.unpackb(message)
                    match data["event"]:
                        case "audio":
                            yield data["audio"]
                        case "finish" if data["reason"] == "error":
                            raise WebSocketErr
                        case "finish" if data["reason"] == "stop":
                            break
                except WebSocketDisconnect:
                    raise WebSocketErr

            sender_future.result()


class AsyncWebSocketSession:
    def __init__(
        self,
        apikey: str,
        *,
        base_url: str = "https://api.fish.audio",
    ):
        self._apikey = apikey
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._apikey}"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    async def close(self):
        await self._client.aclose()

    async def tts(
        self, request: TTSRequest, text_stream: AsyncIterable[str]
    ) -> AsyncGenerator[bytes, None]:
        async with aconnect_ws("/v1/tts/live", client=self._client) as ws:

            async def sender():
                await ws.send_bytes(
                    ormsgpack.packb(
                        StartEvent(request=request),
                        option=ormsgpack.OPT_SERIALIZE_PYDANTIC,
                    )
                )
                async for text in text_stream:
                    await ws.send_bytes(
                        ormsgpack.packb(
                            TextEvent(text=text),
                            option=ormsgpack.OPT_SERIALIZE_PYDANTIC,
                        )
                    )
                await ws.send_bytes(
                    ormsgpack.packb(
                        CloseEvent(), option=ormsgpack.OPT_SERIALIZE_PYDANTIC
                    )
                )

            sender_future = asyncio.get_running_loop().create_task(sender())

            while True:
                try:
                    message = await ws.receive_bytes()
                    data = ormsgpack.unpackb(message)
                    match data["event"]:
                        case "audio":
                            yield data["audio"]
                        case "finish" if data["reason"] == "error":
                            raise WebSocketErr
                        case "finish" if data["reason"] == "stop":
                            break
                except WebSocketDisconnect:
                    raise WebSocketErr

            await sender_future
