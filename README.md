# Fish Audio Python SDK

[![PyPI version](https://img.shields.io/pypi/v/fish-audio-sdk.svg)](https://badge.fury.io/py/fish-audio-sdk)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue)](https://pypi.org/project/fish-audio-sdk/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/fish-audio-sdk)](https://pypi.org/project/fish-audio-sdk/)
[![codecov](https://img.shields.io/codecov/c/github/fishaudio/fish-audio-python)](https://codecov.io/gh/fishaudio/fish-audio-python)
[![License](https://img.shields.io/github/license/fishaudio/fish-audio-python)](https://github.com/fishaudio/fish-audio-python/blob/main/LICENSE)

The official Python library for the Fish Audio API.

## Notice: New API Available

The SDK now includes a modern `fishaudio` API with improved ergonomics, better type safety, and enhanced features.

For new projects, use the `fishaudio` module. For existing projects using the legacy API, see the [Legacy SDK section](#legacy-sdk) below

## API Documentation

For complete documentation and API reference, visit the [Python SDK Guide](https://docs.fish.audio/developer-guide/sdk-guide/python/) and [API Reference](https://docs.fish.audio/api-reference/sdk/python/).

## Installation

This package is available on PyPI:

```bash
pip install fish-audio-sdk
```

You may install from source by running the following command in the repository root:

```bash
python -m pip install .
```

## Usage

The client will need to be configured with an API key, which you can obtain from [Fish Audio](https://fish.audio/app/api-keys).

```python
from fishaudio import FishAudio

client = FishAudio() # Automatically reads from the FISH_API_KEY environment variable

client = FishAudio(api_key="your-api-key") # Or provide the API key directly
```

The SDK provides [text-to-speech](#text-to-speech), [voice cloning](#instant-voice-cloning), [speech recognition](#speech-recognition-asr), and [voice management](#voice-management) capabilities.

### Text-to-Speech

Convert text to natural-sounding speech with support for multiple voices, formats, and real-time streaming.

#### Basic

```python
from fishaudio import FishAudio
from fishaudio.utils import save, play

client = FishAudio()

audio = client.tts.convert(text="Hello, world!") # Default voice and settings
play(audio)  # Play audio directly

audio = client.tts.convert(text="Welcome to Fish Audio SDK!")
save(audio, "output.mp3") # You can also save to a file
```

#### With Reference Voice

Use a reference voice ID to ensure consistent voice characteristics across generations:

```python
# Use an existing voice by ID
audio = client.tts.convert(
    text="This will sound like the reference voice!",
    reference_id="802e3bc2b27e49c2995d23ef70e6ac89" # Energetic Male
)
```

#### Instant Voice Cloning

Immediately clone a voice from a short audio sample:

```python
# Clone a voice from audio sample
with open("reference.wav", "rb") as f:
    audio = client.tts.convert(
        text="This will sound like the reference voice!",
        reference_audio=f.read(),
        reference_text="Transcription of the reference audio"
    )
```

#### Streaming Audio Chunks

For processing audio chunks as they're generated:

```python
# Stream and process audio chunks
for chunk in client.tts.stream(text="Long text content..."):
    # Process each chunk as it arrives
    send_to_websocket(chunk)

# Or collect all chunks
audio = client.tts.stream(text="Hello!").collect()
```

#### Real-time WebSocket Streaming

For low-latency bidirectional streaming where you send text chunks and receive audio in real-time:

```python
from fishaudio import FishAudio
from fishaudio.utils import play

client = FishAudio()

# Stream text chunks and receive audio in real-time
def text_chunks():
    yield "Hello, "
    yield "this is "
    yield "streaming audio!"

audio_stream = client.tts.stream_websocket(text_chunks(), latency="balanced")
play(audio_stream)
```

### Speech Recognition (ASR)

To transcribe audio to text:

```python
from fishaudio import FishAudio

client = FishAudio()

# Transcribe audio to text
with open("audio.wav", "rb") as f:
    result = client.asr.transcribe(audio=f.read())
    print(result.text)
```

### Voice Management

Manage voice references and list available voices.

```python
from fishaudio import FishAudio

client = FishAudio()

# List available voices
voices = client.voices.list(language="en", tags="male")

# Get a specific voice by ID
voice = client.voices.get(voice_id="802e3bc2b27e49c2995d23ef70e6ac89")

# Create a custom voice
with open("voice_sample.wav", "rb") as f:
    new_voice = client.voices.create(
        title="My Custom Voice",
        voices=[f.read()],
        description="My cloned voice"
    )
```

### Async Usage

You can also use the SDK in asynchronous applications:

```python
import asyncio
from fishaudio import AsyncFishAudio

async def main():
    client = AsyncFishAudio()

    audio = await client.tts.convert(text="Async text-to-speech!")
    # Process audio...

asyncio.run(main())
```

### Account

Check your remaining API credits, usage, and account details:

```python
from fishaudio import FishAudio

client = FishAudio()
credits = client.account.get_credits()
print(f"Remaining credits: {credits.credit}")
```


### Optional Dependencies

For audio playback utilities to help with playing and saving audio files, install the `utils` extra:

```bash
pip install fish-audio-sdk[utils]
```

## Legacy SDK

The legacy `fish_audio_sdk` module continues to be supported for existing projects:

```python
from fish_audio_sdk import Session

session = Session("your_api_key")
```

For complete legacy SDK documentation, see the [Legacy API Documentation](https://docs.fish.audio/legacy).

We recommend migrating to the new `fishaudio` module - see our [Migration Guide](https://docs.fish.audio) for assistance.
