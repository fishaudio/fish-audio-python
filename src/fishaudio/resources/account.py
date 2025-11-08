"""Account namespace client for billing and credits."""

from typing import Optional

from ..core import AsyncClientWrapper, ClientWrapper, RequestOptions
from ..types import Credits, Package


class AccountClient:
    """Synchronous account operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def get_credits(
        self,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Credits:
        """
        Get API credit balance.

        Args:
            request_options: Request-level overrides

        Returns:
            Credits information

        Example:
            ```python
            client = FishAudio(api_key="...")
            credits = client.account.get_credits()
            print(f"Available credits: {float(credits.credit)}")
            ```
        """
        response = self._client.request(
            "GET",
            "/wallet/self/api-credit",
            request_options=request_options,
        )
        return Credits.model_validate(response.json())

    def get_package(
        self,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Package:
        """
        Get package information.

        Args:
            request_options: Request-level overrides

        Returns:
            Package information

        Example:
            ```python
            client = FishAudio(api_key="...")
            package = client.account.get_package()
            print(f"Balance: {package.balance}/{package.total}")
            ```
        """
        response = self._client.request(
            "GET",
            "/wallet/self/package",
            request_options=request_options,
        )
        return Package.model_validate(response.json())


class AsyncAccountClient:
    """Asynchronous account operations."""

    def __init__(self, client_wrapper: AsyncClientWrapper):
        self._client = client_wrapper

    async def get_credits(
        self,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Credits:
        """
        Get API credit balance (async).

        Args:
            request_options: Request-level overrides

        Returns:
            Credits information

        Example:
            ```python
            client = AsyncFishAudio(api_key="...")
            credits = await client.account.get_credits()
            print(f"Available credits: {float(credits.credit)}")
            ```
        """
        response = await self._client.request(
            "GET",
            "/wallet/self/api-credit",
            request_options=request_options,
        )
        return Credits.model_validate(response.json())

    async def get_package(
        self,
        *,
        request_options: Optional[RequestOptions] = None,
    ) -> Package:
        """
        Get package information (async).

        Args:
            request_options: Request-level overrides

        Returns:
            Package information

        Example:
            ```python
            client = AsyncFishAudio(api_key="...")
            package = await client.account.get_package()
            print(f"Balance: {package.balance}/{package.total}")
            ```
        """
        response = await self._client.request(
            "GET",
            "/wallet/self/package",
            request_options=request_options,
        )
        return Package.model_validate(response.json())
