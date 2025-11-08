"""Tests for Account namespace client."""

import pytest
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from fishaudio.core import ClientWrapper, AsyncClientWrapper, RequestOptions
from fishaudio.resources.account import AccountClient, AsyncAccountClient
from fishaudio.types import Credits, Package


@pytest.fixture
def mock_client_wrapper(mock_api_key):
    """Mock client wrapper."""
    wrapper = Mock(spec=ClientWrapper)
    wrapper.api_key = mock_api_key
    return wrapper


@pytest.fixture
def async_mock_client_wrapper(mock_api_key):
    """Mock async client wrapper."""
    wrapper = Mock(spec=AsyncClientWrapper)
    wrapper.api_key = mock_api_key
    return wrapper


@pytest.fixture
def account_client(mock_client_wrapper):
    """AccountClient instance with mocked wrapper."""
    return AccountClient(mock_client_wrapper)


@pytest.fixture
def async_account_client(async_mock_client_wrapper):
    """AsyncAccountClient instance with mocked wrapper."""
    return AsyncAccountClient(async_mock_client_wrapper)


class TestAccountClient:
    """Test synchronous AccountClient."""

    def test_get_credits(
        self, account_client, mock_client_wrapper, sample_credits_response
    ):
        """Test getting API credit balance."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_credits_response
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        result = account_client.get_credits()

        # Verify result
        assert isinstance(result, Credits)
        assert result.id == "credit123"
        assert result.user_id == "user123"
        assert isinstance(result.credit, Decimal)
        assert result.credit == Decimal("100.50")

        # Verify request
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/wallet/self/api-credit"
        assert call_args[1]["request_options"] is None

    def test_get_credits_with_request_options(
        self, account_client, mock_client_wrapper, sample_credits_response
    ):
        """Test getting credits with custom request options."""
        mock_response = Mock()
        mock_response.json.return_value = sample_credits_response
        mock_client_wrapper.request.return_value = mock_response

        request_options = RequestOptions(timeout=60.0)
        account_client.get_credits(request_options=request_options)

        # Verify request options passed through
        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options

    def test_get_package(
        self, account_client, mock_client_wrapper, sample_package_response
    ):
        """Test getting package information."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_package_response
        mock_client_wrapper.request.return_value = mock_response

        # Call method
        result = account_client.get_package()

        # Verify result
        assert isinstance(result, Package)
        assert result.id == "package123"
        assert result.user_id == "user123"
        assert result.type == "standard"
        assert result.total == 1000
        assert result.balance == 750

        # Verify request
        mock_client_wrapper.request.assert_called_once()
        call_args = mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/wallet/self/package"

    def test_get_package_with_request_options(
        self, account_client, mock_client_wrapper, sample_package_response
    ):
        """Test getting package with custom request options."""
        mock_response = Mock()
        mock_response.json.return_value = sample_package_response
        mock_client_wrapper.request.return_value = mock_response

        request_options = RequestOptions(
            timeout=30.0, additional_headers={"X-Custom": "header"}
        )
        account_client.get_package(request_options=request_options)

        # Verify request options passed through
        call_args = mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options


class TestAsyncAccountClient:
    """Test asynchronous AsyncAccountClient."""

    @pytest.mark.asyncio
    async def test_get_credits(
        self, async_account_client, async_mock_client_wrapper, sample_credits_response
    ):
        """Test getting API credit balance (async)."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_credits_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        # Call method
        result = await async_account_client.get_credits()

        # Verify result
        assert isinstance(result, Credits)
        assert result.id == "credit123"
        assert result.user_id == "user123"
        assert result.credit == Decimal("100.50")

        # Verify request
        async_mock_client_wrapper.request.assert_called_once()
        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/wallet/self/api-credit"

    @pytest.mark.asyncio
    async def test_get_credits_with_request_options(
        self, async_account_client, async_mock_client_wrapper, sample_credits_response
    ):
        """Test getting credits with custom request options (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_credits_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        request_options = RequestOptions(timeout=60.0)
        await async_account_client.get_credits(request_options=request_options)

        # Verify request options passed through
        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options

    @pytest.mark.asyncio
    async def test_get_package(
        self, async_account_client, async_mock_client_wrapper, sample_package_response
    ):
        """Test getting package information (async)."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = sample_package_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        # Call method
        result = await async_account_client.get_package()

        # Verify result
        assert isinstance(result, Package)
        assert result.id == "package123"
        assert result.total == 1000
        assert result.balance == 750

        # Verify request
        async_mock_client_wrapper.request.assert_called_once()
        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/wallet/self/package"

    @pytest.mark.asyncio
    async def test_get_package_with_request_options(
        self, async_account_client, async_mock_client_wrapper, sample_package_response
    ):
        """Test getting package with custom request options (async)."""
        mock_response = Mock()
        mock_response.json.return_value = sample_package_response
        async_mock_client_wrapper.request = AsyncMock(return_value=mock_response)

        request_options = RequestOptions(timeout=30.0)
        await async_account_client.get_package(request_options=request_options)

        # Verify request options passed through
        call_args = async_mock_client_wrapper.request.call_args
        assert call_args[1]["request_options"] == request_options
