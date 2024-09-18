from fish_audio_sdk import Session, HttpCodeErr, TTSRequest, ASRRequest


def test_tts(session: Session):
    buffer = bytearray()
    for chunk in session.tts(TTSRequest(text="Hello, world!")):
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


def test_get_model(session: Session):
    res = session.get_model(model_id="7f92f8afb8ec43bf81429cc1c9199cb1")
    assert res.id == "7f92f8afb8ec43bf81429cc1c9199cb1"


def test_get_model_not_found(session: Session):
    try:
        session.get_model(model_id="123")
    except HttpCodeErr as e:
        assert e.status == 404
