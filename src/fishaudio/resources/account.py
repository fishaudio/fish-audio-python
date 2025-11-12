"""Account namespace client for billing and credits."""

from typing import Optional

from ..core import OMIT, AsyncClientWrapper, ClientWrapper, RequestOptions
from ..types import Credits, Package


class AccountClient:
    """Synchronous account operations."""

    def __init__(self, client_wrapper: ClientWrapper):
        self._client = client_wrapper

    def get_credits(
        self,
        *,
        check_free_credit: Optional[bool] = OMIT,
        request_options: Optional[RequestOptions] = None,
    ) -> Credits:
        """
        Get API credit balance.

        Args:
            check_free_credit: Whether to check free credit availability
            request_options: Request-level overrides

        Returns:
            Credits information

        Example:
            ```python
            client = FishAudio(api_key="...")
            credits = client.account.get_credits()
            print(f"Available credits: {float(credits.credit)}")

            # Check free credit availability
            credits = client.account.get_credits(check_free_credit=True)
            if credits.has_free_credit:
                print("Free credits available!")
            ```
        """
        params = {}
        if check_free_credit is not OMIT:
            params["check_free_credit"] = check_free_credit

        response = self._client.request(
            "GET",
            "/wallet/self/api-credit",
            params=params,
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
        check_free_credit: Optional[bool] = OMIT,
        request_options: Optional[RequestOptions] = None,
    ) -> Credits:
        """
        Get API credit balance (async).

        Args:
            check_free_credit: Whether to check free credit availability
            request_options: Request-level overrides

        Returns:
            Credits information

        Example:
            ```python
            client = AsyncFishAudio(api_key="...")
            credits = await client.account.get_credits()
            print(f"Available credits: {float(credits.credit)}")

            # Check free credit availability
            credits = await client.account.get_credits(check_free_credit=True)
            if credits.has_free_credit:
                print("Free credits available!")
            ```
        """
        params = {}
        if check_free_credit is not OMIT:
            params["check_free_credit"] = check_free_credit

        response = await self._client.request(
            "GET",
            "/wallet/self/api-credit",
            params=params,
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
