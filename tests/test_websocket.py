from fish_audio_sdk import TTSRequest, WebSocketSession, AsyncWebSocketSession

story = """
修炼了六千三百七十九年又三月零六天后，天门因她终于洞开。

她凭虚站立在黄山峰顶，因天门洞开而鼓起的飓风不停拍打着她身上的黑袍，在催促她快快登仙而去；黄山间壮阔的云海也随之翻涌，为这一场天地幸事欢呼雀跃。她没有抬头看向那似隐似现、若有若无、形态万千变化的天门，只是呆立在原处自顾自地看向远方。
"""


def test_tts(sync_websocket: WebSocketSession):
    buffer = bytearray()

    def stream():
        for line in story.split("\n"):
            yield line

    for chunk in sync_websocket.tts(TTSRequest(text=""), stream()):
        buffer.extend(chunk)
    assert len(buffer) > 0


async def test_async_tts(async_websocket: AsyncWebSocketSession):
    buffer = bytearray()

    async def stream():
        for line in story.split("\n"):
            yield line

    async for chunk in async_websocket.tts(TTSRequest(text=""), stream()):
        buffer.extend(chunk)
    assert len(buffer) > 0
