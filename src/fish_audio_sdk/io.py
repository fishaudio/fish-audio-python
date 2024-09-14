import dataclasses
import os
import time
import typing
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    TypeVar,
    Generator,
    ParamSpec,
    Generic,
    Concatenate,
)

import httpx
import httpx._client
import httpx._types

from .exceptions import HttpCodeErr


class RemoteCall:
    _base_url: str
    _async_client: httpx.AsyncClient
    _sync_client: httpx.Client

    def __init__(self, apikey: str, *, base_url: str = "https://api.fish.audio"):
        self._apikey = apikey
        self._base_url = base_url
        self.init_async_client()
        self.init_sync_client()

    def init_async_client(self):
        self._async_client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._apikey}"},
        )

    def init_sync_client(self):
        self._sync_client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._apikey}"},
        )

    async def __aenter__(self):
        if self._async_client.is_closed:
            self.init_async_client()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._async_client.aclose()

    def __enter__(self):
        if self._sync_client.is_closed:
            self.init_sync_client()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._sync_client.close()

    @staticmethod
    def _try_raise_http_exception(resp: httpx.Response) -> None:
        if not resp.is_success:
            raise HttpCodeErr(**resp.json())


P = ParamSpec("P")
R = TypeVar("R")


@dataclasses.dataclass
class IOCall(Generic[P, R]):
    _awaitable: Callable[Concatenate[RemoteCall, P], Awaitable[R]]
    _syncable: Callable[Concatenate[RemoteCall, P], R]
    this: RemoteCall

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self._syncable(self.this, *args, **kwargs)

    def awaitable(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        return self._awaitable(self.this, *args, **kwargs)


class IOCallDescriptor(Generic[P, R]):
    def __init__(
        self,
        awaitable: Callable[Concatenate[RemoteCall, P], Awaitable[R]],
        syncable: Callable[Concatenate[RemoteCall, P], R],
    ):
        self.awaitable = awaitable
        self.syncable = syncable

    def __get__(self, instance: RemoteCall, owner: type[RemoteCall]) -> IOCall[P, R]:
        return IOCall(self.awaitable, self.syncable, instance)


@dataclasses.dataclass
class Request:
    method: str
    url: str

    content: httpx._types.RequestContent | None = None
    data: httpx._types.RequestData | None = None
    files: httpx._types.RequestFiles | None = None
    json: Any | None = None
    params: httpx._types.QueryParamTypes | None = None
    headers: httpx._types.HeaderTypes | None = None
    cookies: httpx._types.CookieTypes | None = None
    timeout: httpx._types.TimeoutTypes = None
    extensions: httpx._types.RequestExtensions | None = None


Response = httpx.Response


G = Generator[Request, Response, R]


def convert(
    func: Callable[Concatenate[typing.Any, P], Generator[Request, Response, R]],
) -> IOCallDescriptor[P, R]:
    async def async_wrapper(self: RemoteCall, *args: P.args, **kwargs: P.kwargs) -> R:
        g = func(self, *args, **kwargs)
        request = next(g)

        request = self._async_client.build_request(**dataclasses.asdict(request))
        resp = await self._async_client.send(request)
        self._try_raise_http_exception(resp)
        try:
            g.send(resp)
        except StopIteration as exc:
            return exc.value
        raise RuntimeError("Generator did not stop")

    def sync_wrapper(self: RemoteCall, *args: P.args, **kwargs: P.kwargs) -> R:
        g = func(self, *args, **kwargs)
        request = next(g)

        request = self._sync_client.build_request(**dataclasses.asdict(request))
        resp = self._sync_client.send(request)
        self._try_raise_http_exception(resp)
        try:
            g.send(resp)
        except StopIteration as exc:
            return exc.value
        raise RuntimeError("Generator did not stop")

    call = IOCallDescriptor(async_wrapper, sync_wrapper)
    return call
