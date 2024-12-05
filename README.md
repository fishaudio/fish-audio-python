# Fish Audio Python SDK

To provide convenient Python program integration for https://docs.fish.audio.

## Install

```bash
pip install fish-audio-sdk
```

## Usage

Initialize a `Session` to use APIs. All APIs have synchronous and asynchronous versions. If you want to use the asynchronous version of the API, you only need to rewrite the original `session.api_call(...)` to `session.api_call.awaitable(...)`.

```python
from fish_audio_sdk import Session

session = Session("your_api_key")
```

Sometimes, you may need to change our endpoint to another address. You can use

```python
from fish_audio_sdk import Session

session = Session("your_api_key", base_url="https://your-proxy-domain")
```

### Text to speech

```python
from fish_audio_sdk import Session, TTSRequest

session = Session("your_api_key")

with open("r.mp3", "wb") as f:
    for chunk in session.tts(TTSRequest(text="Hello, world!")):
        f.write(chunk)
```

Or use async version:

```python
import asyncio
import aiofiles

from fish_audio_sdk import Session, TTSRequest

session = Session("your_api_key")


async def main():
    async with aiofiles.open("r.mp3", "wb") as f:
        async for chunk in session.tts.awaitable(
            TTSRequest(text="Hello, world!"),
        ):
            await f.write(chunk)


asyncio.run(main())
```

#### Reference Audio

```python
from fish_audio_sdk import TTSRequest

TTSRequest(
    text="Hello, world!",
    reference_id="your_model_id",
)
```

Or just use `ReferenceAudio` in `TTSRequest`:

```python
from fish_audio_sdk import TTSRequest, ReferenceAudio

TTSRequest(
    text="Hello, world!",
    references=[
        ReferenceAudio(
            audio=audio_file.read(),
            text="reference audio text",
        )
    ],
)
```

### List models

```python
models = session.list_models()
print(models)
```

Or use async version:

```python
import asyncio


async def main():
    models = await session.list_models.awaitable()
    print(models)


asyncio.run(main())
```



### Get a model info by id

```python
model = session.get_model("your_model_id")
print(model)
```

Or use async version:

```python
import asyncio


async def main():
    model = await session.get_model.awaitable("your_model_id")
    print(model)


asyncio.run(main())
```

### Create a model

```python
model = session.create_model(
    title="test",
    description="test",
    voices=[voice_file.read(), other_voice_file.read()],
    cover_image=image_file.read(),
)
print(model)
```

Or use async version:

```python
import asyncio


async def main():
    model = await session.create_model.awaitable(
        title="test",
        description="test",
        voices=[voice_file.read(), other_voice_file.read()],
        cover_image=image_file.read(),
    )
    print(model)


asyncio.run(main())
```


### Delete a model

```python
session.delete_model("your_model_id")
```

Or use async version:

```python
import asyncio


async def main():
    await session.delete_model.awaitable("your_model_id")


asyncio.run(main())
```
