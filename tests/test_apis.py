from fish_audio_sdk import Session, HttpCodeErr


def test_list_models(session: Session):
    res = session.list_models()
    assert res.total > 0


async def test_list_models_async(session: Session):
    res = await session.list_models.awaitable()
    assert res.total > 0


def test_get_model_not_found(session: Session):
    try:
        session.get_model(model_id="123")
    except HttpCodeErr as e:
        assert e.status == 404
