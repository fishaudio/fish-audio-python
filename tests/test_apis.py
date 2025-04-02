import pytest

from fish_audio_sdk import ASRRequest, HttpCodeErr, Session, TTSRequest
from fish_audio_sdk.schemas import APICreditEntity, PackageEntity


def test_tts(session: Session):
    buffer = bytearray()
    for chunk in session.tts(TTSRequest(text="Hello, world!")):
        buffer.extend(chunk)
    assert len(buffer) > 0

def test_tts_model_1_6(session: Session):
    buffer = bytearray()
    for chunk in session.tts(TTSRequest(text="Hello, world!"), backend="speech-1.6"):
        buffer.extend(chunk)
    assert len(buffer) > 0


async def test_tts_async(session: Session):
    buffer = bytearray()
    async for chunk in session.tts.awaitable(TTSRequest(text="Hello, world!")):
        buffer.extend(chunk)
    assert len(buffer) > 0


def test_asr(session: Session):
    buffer = bytearray()
    for chunk in session.tts(TTSRequest(text="Hello, world!")):
        buffer.extend(chunk)
    res = session.asr(ASRRequest(audio=buffer, language="zh"))
    assert res.text


async def test_asr_async(session: Session):
    buffer = bytearray()
    async for chunk in session.tts.awaitable(TTSRequest(text="Hello, world!")):
        buffer.extend(chunk)
    res = await session.asr.awaitable(ASRRequest(audio=buffer, language="zh"))
    assert res.text


def test_list_models(session: Session):
    res = session.list_models()
    assert res.total > 0


async def test_list_models_async(session: Session):
    res = await session.list_models.awaitable()
    assert res.total > 0


def test_list_self_models(session: Session):
    res = session.list_models(self_only=True)
    assert res.total > 0


def test_get_model(session: Session):
    res = session.get_model(model_id="7f92f8afb8ec43bf81429cc1c9199cb1")
    assert res.id == "7f92f8afb8ec43bf81429cc1c9199cb1"


def test_get_model_not_found(session: Session):
    with pytest.raises(HttpCodeErr) as exc_info:
        session.get_model(model_id="123")
    assert exc_info.value.status == 404


def test_invalid_token(session: Session):
    session._apikey = "invalid"
    session.init_async_client()
    session.init_sync_client()

    with pytest.raises(HttpCodeErr) as exc_info:
        test_tts(session)

    assert exc_info.value.status in [401, 402]


def test_get_api_credit(session: Session):
    res = session.get_api_credit()
    assert isinstance(res, APICreditEntity)


def test_get_package(session: Session):
    res = session.get_package()
    assert isinstance(res, PackageEntity)
