import os

import pytest

from fish_audio_sdk.apis import Session

APIKEY = os.environ["APIKEY"]


@pytest.fixture
def session():
    return Session(APIKEY)
