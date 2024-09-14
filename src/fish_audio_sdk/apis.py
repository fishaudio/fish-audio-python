from typing import Literal

import ormsgpack

from .schemas import ASRRequest, ASRResponse, ModelEntity, PaginatedResponse, TTSRequest
from .io import RemoteCall, convert, G, Request


class Session(RemoteCall):
    @convert
    def tts(self, request: TTSRequest) -> G[bytes]:
        response = yield Request(
            method="POST",
            url="/v1/tts",
            headers={"Content-Type": "application/msgpack"},
            content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        )
        return response.content

    @convert
    def asr(self, request: ASRRequest) -> G[ASRResponse]:
        response = yield Request(
            method="POST",
            url="/v1/asr",
            headers={"Content-Type": "application/msgpack"},
            content=ormsgpack.packb(request, option=ormsgpack.OPT_SERIALIZE_PYDANTIC),
        )
        return ASRResponse(**response.json())

    @convert
    def list_models(
        this,
        *,
        page_size: int = 10,
        page_number: int = 1,
        title: str | None = None,
        tag: list[str] | str | None = None,
        self: bool = False,
        author_id: str | None = None,
        language: list[str] | str | None = None,
        title_language: list[str] | str | None = None,
        sort_by: Literal["task_count", "created_at"] = "task_count",
    ) -> G[PaginatedResponse[ModelEntity]]:
        response = yield Request(
            method="GET",
            url="/model",
            params=filter_none(
                {
                    "page_size": page_size,
                    "page_number": page_number,
                    "title": title,
                    "tag": tag,
                    "self": self,
                    "author_id": author_id,
                    "language": language,
                    "title_language": title_language,
                    "sort_by": sort_by,
                }
            ),
        )
        return PaginatedResponse[ModelEntity].model_validate(response.json())

    @convert
    def get_model(this, model_id: str) -> G[ModelEntity]:
        response = yield Request(method="GET", url=f"/model/{model_id}")
        return ModelEntity.model_validate(response.json())

    @convert
    def create_model(
        this,
        *,
        visibility: Literal["public", "unlist", "private"] = "private",
        type: Literal["tts"] = "tts",
        title: str,
        description: str | None = None,
        cover_image: bytes | None = None,
        train_model: Literal["fast"] = "fast",
        voices: list[bytes],
        texts: list[str],
        tags: list[str] = [],
    ) -> G[ModelEntity]:
        files = [("voices", voice) for voice in voices]
        if cover_image is not None:
            files.append(("cover_image", cover_image))
        response = yield Request(
            method="POST",
            url="/model",
            data=filter_none(
                {
                    "visibility": visibility,
                    "type": type,
                    "title": title,
                    "description": description,
                    "train_model": train_model,
                    "texts": texts,
                    "tags": tags,
                }
            ),
            files=files,
        )
        return ModelEntity.model_validate(response.json())

    @convert
    def delete_model(this, model_id: str) -> G[None]:
        yield Request(method="DELETE", url=f"/model/{model_id}")

    @convert
    def update_model(
        this,
        model_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        cover_image: bytes | None = None,
        visibility: Literal["public", "unlist", "private"] | None = None,
        tags: list[str] | None = None,
    ) -> G[None]:
        files = []
        if cover_image is not None:
            files.append(("cover_image", cover_image))
        yield Request(
            method="PATCH",
            url=f"/model/{model_id}",
            data=filter_none(
                {
                    "title": title,
                    "description": description,
                    "visibility": visibility,
                    "tags": tags,
                }
            ),
            files=files,
        )


filter_none = lambda d: {k: v for k, v in d.items() if v is not None}