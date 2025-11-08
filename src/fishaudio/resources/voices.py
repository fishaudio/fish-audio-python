"""Voice management namespace client."""

from typing import List, Optional, Union

from ..core import OMIT, AsyncClientWrapper, ClientWrapper, RequestOptions
from ..types import PaginatedResponse, Visibility, Voice


def _filter_none(d: dict) -> dict:
    """Remove None and OMIT values from dictionary."""
    return {k: v for k, v in d.items() if v is not None and v is not OMIT}


class VoicesClient:
    """Synchronous voice management operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def list(
        self,
        *,
        page_size: int = 10,
        page_number: int = 1,
        title: Optional[str] = OMIT,
        tags: Optional[Union[List[str], str]] = OMIT,
        self_only: bool = False,
        author_id: Optional[str] = OMIT,
        language: Optional[Union[List[str], str]] = OMIT,
        title_language: Optional[Union[List[str], str]] = OMIT,
        sort_by: str = "task_count",
        request_options: Optional[RequestOptions] = None,
    ) -> PaginatedResponse[Voice]:
        """
        List available voices/models.

        Args:
            page_size: Number of results per page
            page_number: Page number (1-indexed)
            title: Filter by title
            tags: Filter by tags (single tag or list)
            self_only: Only return user's own voices
            author_id: Filter by author ID
            language: Filter by language(s)
            title_language: Filter by title language(s)
            sort_by: Sort field ("task_count" or "created_at")
            request_options: Request-level overrides

        Returns:
            Paginated response with total count and voice items

        Example:
            ```python
            client = FishAudio(api_key="...")

            # List all voices
            voices = client.voices.list(page_size=20)
            print(f"Total: {voices.total}")
            for voice in voices.items:
                print(f"{voice.title}: {voice.id}")

            # Filter by tags
            tagged = client.voices.list(tags=["male", "english"])
            ```
        """
        # Build query parameters
        params = _filter_none(
            {
                "page_size": page_size,
                "page_number": page_number,
                "title": title,
                "tag": tags,
                "self": self_only,
                "author_id": author_id,
                "language": language,
                "title_language": title_language,
                "sort_by": sort_by,
            }
        )

        # Make request
        response = self._client.request(
            "GET",
            "/model",
            params=params,
            request_options=request_options,
        )

        # Parse and return
        return PaginatedResponse[Voice].model_validate(response.json())

    def get(
        self,
        voice_id: str,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Voice:
        """
        Get voice by ID.

        Args:
            voice_id: Voice model ID
            request_options: Request-level overrides

        Returns:
            Voice model details

        Example:
            ```python
            client = FishAudio(api_key="...")
            voice = client.voices.get("voice_id_here")
            print(voice.title, voice.description)
            ```
        """
        response = self._client.request(
            "GET",
            f"/model/{voice_id}",
            request_options=request_options,
        )
        return Voice.model_validate(response.json())

    def create(
        self,
        *,
        title: str,
        voices: List[bytes],
        description: Optional[str] = OMIT,
        texts: Optional[List[str]] = OMIT,
        tags: Optional[List[str]] = OMIT,
        cover_image: Optional[bytes] = OMIT,
        visibility: Visibility = "private",
        train_mode: str = "fast",
        enhance_audio_quality: bool = True,
        request_options: Optional[RequestOptions] = None,
    ) -> Voice:
        """
        Create/clone a new voice.

        Args:
            title: Voice model name
            voices: List of audio file bytes for training
            description: Voice description
            texts: Transcripts for voice samples
            tags: Tags for categorization
            cover_image: Cover image bytes
            visibility: Visibility setting (public, unlist, private)
            train_mode: Training mode (currently only "fast" supported)
            enhance_audio_quality: Whether to enhance audio quality
            request_options: Request-level overrides

        Returns:
            Created voice model

        Example:
            ```python
            client = FishAudio(api_key="...")

            with open("voice1.wav", "rb") as f1, open("voice2.wav", "rb") as f2:
                voice = client.voices.create(
                    title="My Voice",
                    voices=[f1.read(), f2.read()],
                    description="Custom voice clone",
                    tags=["custom", "english"]
                )
            print(f"Created: {voice.id}")
            ```
        """
        # Build form data
        data = _filter_none(
            {
                "title": title,
                "description": description,
                "visibility": visibility,
                "type": "tts",
                "train_mode": train_mode,
                "texts": texts or [],
                "tags": tags or [],
                "enhance_audio_quality": enhance_audio_quality,
            }
        )

        # Build files
        files = [("voices", voice) for voice in voices]
        if cover_image is not OMIT and cover_image is not None:
            files.append(("cover_image", cover_image))

        # Make request
        response = self._client.request(
            "POST",
            "/model",
            data=data,
            files=files,
            request_options=request_options,
        )

        return Voice.model_validate(response.json())

    def update(
        self,
        voice_id: str,
        *,
        title: Optional[str] = OMIT,
        description: Optional[str] = OMIT,
        cover_image: Optional[bytes] = OMIT,
        visibility: Optional[Visibility] = OMIT,
        tags: Optional[List[str]] = OMIT,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        """
        Update voice metadata.

        Args:
            voice_id: Voice model ID
            title: New title
            description: New description
            cover_image: New cover image bytes
            visibility: New visibility setting
            tags: New tags
            request_options: Request-level overrides

        Example:
            ```python
            client = FishAudio(api_key="...")
            client.voices.update(
                "voice_id_here",
                title="Updated Title",
                visibility="public"
            )
            ```
        """
        # Build form data
        data = _filter_none(
            {
                "title": title,
                "description": description,
                "visibility": visibility,
                "tags": tags,
            }
        )

        # Build files if needed
        files = []
        if cover_image is not OMIT and cover_image is not None:
            files.append(("cover_image", cover_image))

        # Make request
        self._client.request(
            "PATCH",
            f"/model/{voice_id}",
            data=data,
            files=files if files else None,
            request_options=request_options,
        )

    def delete(
        self,
        voice_id: str,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        """
        Delete a voice.

        Args:
            voice_id: Voice model ID
            request_options: Request-level overrides

        Example:
            ```python
            client = FishAudio(api_key="...")
            client.voices.delete("voice_id_here")
            ```
        """
        self._client.request(
            "DELETE",
            f"/model/{voice_id}",
            request_options=request_options,
        )


class AsyncVoicesClient:
    """Asynchronous voice management operations."""

    def __init__(self, client_wrapper: AsyncClientWrapper):
        self._client = client_wrapper

    async def list(
        self,
        *,
        page_size: int = 10,
        page_number: int = 1,
        title: Optional[str] = OMIT,
        tags: Optional[Union[List[str], str]] = OMIT,
        self_only: bool = False,
        author_id: Optional[str] = OMIT,
        language: Optional[Union[List[str], str]] = OMIT,
        title_language: Optional[Union[List[str], str]] = OMIT,
        sort_by: str = "task_count",
        request_options: Optional[RequestOptions] = None,
    ) -> PaginatedResponse[Voice]:
        """List available voices/models (async). See sync version for details."""
        params = _filter_none(
            {
                "page_size": page_size,
                "page_number": page_number,
                "title": title,
                "tag": tags,
                "self": self_only,
                "author_id": author_id,
                "language": language,
                "title_language": title_language,
                "sort_by": sort_by,
            }
        )

        response = await self._client.request(
            "GET",
            "/model",
            params=params,
            request_options=request_options,
        )

        return PaginatedResponse[Voice].model_validate(response.json())

    async def get(
        self,
        voice_id: str,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Voice:
        """Get voice by ID (async). See sync version for details."""
        response = await self._client.request(
            "GET",
            f"/model/{voice_id}",
            request_options=request_options,
        )
        return Voice.model_validate(response.json())

    async def create(
        self,
        *,
        title: str,
        voices: List[bytes],
        description: Optional[str] = OMIT,
        texts: Optional[List[str]] = OMIT,
        tags: Optional[List[str]] = OMIT,
        cover_image: Optional[bytes] = OMIT,
        visibility: Visibility = "private",
        train_mode: str = "fast",
        enhance_audio_quality: bool = True,
        request_options: Optional[RequestOptions] = None,
    ) -> Voice:
        """Create/clone a new voice (async). See sync version for details."""
        data = _filter_none(
            {
                "title": title,
                "description": description,
                "visibility": visibility,
                "type": "tts",
                "train_mode": train_mode,
                "texts": texts or [],
                "tags": tags or [],
                "enhance_audio_quality": enhance_audio_quality,
            }
        )

        files = [("voices", voice) for voice in voices]
        if cover_image is not OMIT and cover_image is not None:
            files.append(("cover_image", cover_image))

        response = await self._client.request(
            "POST",
            "/model",
            data=data,
            files=files,
            request_options=request_options,
        )

        return Voice.model_validate(response.json())

    async def update(
        self,
        voice_id: str,
        *,
        title: Optional[str] = OMIT,
        description: Optional[str] = OMIT,
        cover_image: Optional[bytes] = OMIT,
        visibility: Optional[Visibility] = OMIT,
        tags: Optional[List[str]] = OMIT,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        """Update voice metadata (async). See sync version for details."""
        data = _filter_none(
            {
                "title": title,
                "description": description,
                "visibility": visibility,
                "tags": tags,
            }
        )

        files = []
        if cover_image is not OMIT and cover_image is not None:
            files.append(("cover_image", cover_image))

        await self._client.request(
            "PATCH",
            f"/model/{voice_id}",
            data=data,
            files=files if files else None,
            request_options=request_options,
        )

    async def delete(
        self,
        voice_id: str,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        """Delete a voice (async). See sync version for details."""
        await self._client.request(
            "DELETE",
            f"/model/{voice_id}",
            request_options=request_options,
        )
