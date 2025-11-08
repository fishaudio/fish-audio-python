"""Integration tests for Account functionality."""

import pytest
from decimal import Decimal

from fishaudio.types import Credits, Package


class TestAccountIntegration:
    """Test Account with real API."""

    def test_get_credits(self, client):
        """Test getting API credits."""
        credits = client.account.get_credits()

        assert isinstance(credits, Credits)
        assert isinstance(credits.credit, Decimal)
        assert credits.user_id
        assert credits.id

    def test_get_package(self, client):
        """Test getting package information."""
        try:
            package = client.account.get_package()

            assert isinstance(package, Package)
            assert package.total >= 0
            assert package.balance >= 0
            assert package.user_id
        except Exception:
            # User might not have a package
            pytest.skip("No package available for this account")


class TestAsyncAccountIntegration:
    """Test async Account with real API."""

    @pytest.mark.asyncio
    async def test_async_get_credits(self, async_client):
        """Test getting credits async."""
        credits = await async_client.account.get_credits()

        assert isinstance(credits, Credits)
        assert isinstance(credits.credit, Decimal)
        assert credits.user_id

    @pytest.mark.asyncio
    async def test_async_get_package(self, async_client):
        """Test getting package async."""
        try:
            package = await async_client.account.get_package()

            assert isinstance(package, Package)
            assert package.total >= 0
            assert package.balance >= 0
        except Exception:
            pytest.skip("No package available for this account")
