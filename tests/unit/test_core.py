"""Tests for core components."""

import pytest
from unittest.mock import patch
import httpx

from fishaudio.core import (
    OMIT,
    ClientWrapper,
    AsyncClientWrapper,
    RequestOptions,
    WebSocketOptions,
)


class TestOMIT:
    """Test OMIT sentinel."""

    def test_omit_is_falsy(self):
        assert not OMIT

    def test_omit_repr(self):
        assert repr(OMIT) == "OMIT"

    def test_omit_identity(self):
        # OMIT should be a singleton-like value
        value = OMIT
        assert value is OMIT


class TestRequestOptions:
    """Test RequestOptions class."""

    def test_defaults(self):
        options = RequestOptions()
        assert options.timeout is None
        assert options.max_retries is None
        assert options.additional_headers == {}
        assert options.additional_query_params == {}

    def test_with_values(self):
        options = RequestOptions(
            timeout=30.0,
            max_retries=3,
            additional_headers={"X-Custom": "value"},
            additional_query_params={"param": "value"},
        )
        assert options.timeout == 30.0
        assert options.max_retries == 3
        assert options.additional_headers == {"X-Custom": "value"}
        assert options.additional_query_params == {"param": "value"}

    def test_get_timeout(self):
        options = RequestOptions(timeout=30.0)
        timeout = options.get_timeout()
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 30.0


class TestWebSocketOptions:
    """Test WebSocketOptions class."""

    def test_to_httpx_ws_kwargs_all_options(self):
        """Test to_httpx_ws_kwargs with all options set."""
        options = WebSocketOptions(
            keepalive_ping_timeout_seconds=60.0,
            keepalive_ping_interval_seconds=30.0,
            max_message_size_bytes=131072,
            queue_size=1024,
        )
        kwargs = options.to_httpx_ws_kwargs()
        assert kwargs == {
            "keepalive_ping_timeout_seconds": 60.0,
            "keepalive_ping_interval_seconds": 30.0,
            "max_message_size_bytes": 131072,
            "queue_size": 1024,
        }

    def test_to_httpx_ws_kwargs_partial_options(self):
        """Test to_httpx_ws_kwargs with only some options set."""
        options = WebSocketOptions(keepalive_ping_timeout_seconds=60.0)
        kwargs = options.to_httpx_ws_kwargs()
        assert kwargs == {"keepalive_ping_timeout_seconds": 60.0}
        assert "keepalive_ping_interval_seconds" not in kwargs

    def test_to_httpx_ws_kwargs_no_options(self):
        """Test to_httpx_ws_kwargs with no options set."""
        options = WebSocketOptions()
        assert options.to_httpx_ws_kwargs() == {}


class TestClientWrapper:
    """Test sync ClientWrapper."""

    def test_init_with_api_key(self, mock_api_key, mock_base_url):
        wrapper = ClientWrapper(
            api_key=mock_api_key, base_url=mock_base_url, timeout=60.0
        )
        assert wrapper.api_key == mock_api_key
        assert wrapper.base_url == mock_base_url

    def test_init_without_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key must be provided"):
                ClientWrapper()

    def test_init_with_env_var(self, mock_api_key):
        with patch.dict("os.environ", {"FISH_API_KEY": mock_api_key}):
            wrapper = ClientWrapper()
            assert wrapper.api_key == mock_api_key

    def test_get_headers(self, mock_api_key):
        wrapper = ClientWrapper(api_key=mock_api_key)
        headers = wrapper.get_headers()
        assert headers["Authorization"] == f"Bearer {mock_api_key}"
        assert "User-Agent" in headers

    def test_get_headers_with_additional(self, mock_api_key):
        wrapper = ClientWrapper(api_key=mock_api_key)
        headers = wrapper.get_headers({"X-Custom": "value"})
        assert headers["X-Custom"] == "value"
        assert headers["Authorization"] == f"Bearer {mock_api_key}"


class TestAsyncClientWrapper:
    """Test async AsyncClientWrapper."""

    def test_init_with_api_key(self, mock_api_key, mock_base_url):
        wrapper = AsyncClientWrapper(
            api_key=mock_api_key, base_url=mock_base_url, timeout=60.0
        )
        assert wrapper.api_key == mock_api_key
        assert wrapper.base_url == mock_base_url

    def test_init_without_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key must be provided"):
                AsyncClientWrapper()

    def test_get_headers(self, mock_api_key):
        wrapper = AsyncClientWrapper(api_key=mock_api_key)
        headers = wrapper.get_headers()
        assert headers["Authorization"] == f"Bearer {mock_api_key}"
        assert "User-Agent" in headers
