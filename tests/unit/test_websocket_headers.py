"""WebSocketOptions.additional_headers, checked on the handshake each path sends."""

import pytest

from fishaudio.core import WebSocketOptions
from fishaudio.core.client_wrapper import USER_AGENT

from .realtime_server import WS_PATHS, consume, open_stream, ws_server

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


def handshake(path, ws_options=None):
    """The handshake's header lines, in order, as the server read them."""
    with ws_server(path) as (server, client):
        consume(open_stream(client, path, ws_options))
    return server.stop().header_list


def values(header_list, name):
    return [value for key, value in header_list if key == name]


@pytest.mark.parametrize("path", WS_PATHS)
def test_additional_headers_are_sent_on_the_handshake(path):
    extra = {"traceparent": TRACEPARENT, "X-Request-Source": "test"}

    sent = handshake(path, WebSocketOptions(additional_headers=extra))

    assert values(sent, "traceparent") == [TRACEPARENT]
    assert values(sent, "x-request-source") == ["test"]
    assert extra == {"traceparent": TRACEPARENT, "X-Request-Source": "test"}


@pytest.mark.parametrize("path", WS_PATHS)
def test_sdk_headers_win_over_additional_headers_in_any_casing(path):
    default = handshake(path)

    sent = handshake(
        path,
        WebSocketOptions(
            additional_headers={"AUTHORIZATION": "Bearer other", "Model": "other"}
        ),
    )

    for name in ("authorization", "model"):
        assert values(sent, name) == values(default, name)
    assert values(sent, "authorization") == ["Bearer test-key"]


@pytest.mark.parametrize("path", WS_PATHS)
def test_a_user_agent_in_additional_headers_is_appended_to_the_sdks(path):
    assert values(handshake(path), "user-agent") == [USER_AGENT]

    sent = handshake(
        path, WebSocketOptions(additional_headers={"user-agent": "my-app/1.0"})
    )

    assert values(sent, "user-agent") == [f"{USER_AGENT} my-app/1.0"]


@pytest.mark.parametrize("path", WS_PATHS)
def test_the_last_of_two_spellings_of_user_agent_is_the_one_appended(path):
    extra = {"User-Agent": "base/1", "user-agent": "override/2"}

    sent = handshake(path, WebSocketOptions(additional_headers=extra))

    assert values(sent, "user-agent") == [f"{USER_AGENT} override/2"]
    assert extra == {"User-Agent": "base/1", "user-agent": "override/2"}


@pytest.mark.parametrize("path", WS_PATHS)
def test_default_options_send_the_same_header_names(path):
    without_options = handshake(path)
    with_default_options = handshake(path, WebSocketOptions())

    names = [name for name, _ in without_options]
    assert [name for name, _ in with_default_options] == names
    assert {"authorization", "user-agent", "model"} <= set(names)
