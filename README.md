# Fish Audio Python SDK

[![PyPI version](https://badge.fury.io/py/fish-audio-sdk.svg)](https://badge.fury.io/py/fish-audio-sdk)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue)](https://pypi.org/project/fish-audio-sdk/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/fish-audio-sdk)](https://pypi.org/project/fish-audio-sdk/)
[![codecov](https://img.shields.io/codecov/c/github/fishaudio/fish-audio-python)](https://codecov.io/gh/fishaudio/fish-audio-python)
[![License](https://img.shields.io/github/license/fishaudio/fish-audio-python)](https://github.com/fishaudio/fish-audio-python/blob/main/LICENSE)

The official Python library for the Fish Audio API.

[Documentation](https://docs.fish.audio) | [API Reference](https://docs.fish.audio) | [Examples](./examples/) | [Discord](https://fish.audio)

---

## Important: New API Available

> **We've released a major update to the Fish Audio Python SDK!**
>
> The new API (`fishaudio` module) offers improved ergonomics, better type safety, and enhanced features. The legacy SDK (`fish_audio_sdk` module) continues to be supported for existing projects, but we recommend using the new API for all new development.
>
> **Migration:** Both APIs are available in the same package. You can migrate at your own pace. See our [Migration Guide](https://docs.fish.audio) for details.

---

## Quick Start

### Installation

```bash
pip install fish-audio-sdk
```

### Basic Usage

```python
from fishaudio import FishAudio
from fishaudio.utils import save

# Set your API key via environment variable: export FISH_AUDIO_API_KEY="your-api-key"
# Or pass it directly: FishAudio(api_key="your-api-key")
client = FishAudio()

# Convert text to speech
audio = client.tts.convert(text="Hello from Fish Audio!")
save(audio, "output.mp3")
```

[Get your API key](https://fish.audio) | [Full Getting Started Guide](https://docs.fish.audio)

---

## Key Features

- **Text-to-Speech** - Natural-sounding voice synthesis with multiple voice options
- **Voice Cloning** - Create custom voices using reference audio samples
- **Real-time Streaming** - Low-latency audio generation via WebSocket connections
- **Speech-to-Text (ASR)** - Accurate automatic speech recognition with language detection
- **Voice Management** - Create, update, and organize custom voice models
- **Sync and Async APIs** - Full support for both synchronous and asynchronous operations
- **Type Safety** - Complete type hints with Pydantic models throughout

---

## Examples

### Text-to-Speech

```python
from fishaudio import FishAudio
from fishaudio.utils import save

client = FishAudio()
audio = client.tts.convert(text="Hello, world!")
save(audio, "output.mp3")
```

### Voice Cloning with Reference Audio

```python
from fishaudio import FishAudio

client = FishAudio()

# Use a reference voice for cloning
with open("reference.wav", "rb") as f:
    audio = client.tts.convert(
        text="This will sound like the reference voice!",
        reference_audio=f.read(),
        reference_text="Transcription of the reference audio"
    )
```

### Real-time Streaming

```python
from fishaudio import FishAudio
from fishaudio.utils import play

client = FishAudio()

# Stream audio in real-time
audio_stream = client.tts.stream(
    text="This audio streams as it's generated",
    latency="balanced"
)

play(audio_stream)
```

### Speech Recognition (ASR)

```python
from fishaudio import FishAudio

client = FishAudio()

# Transcribe audio to text
with open("audio.wav", "rb") as f:
    result = client.asr.transcribe(audio=f.read())
    print(result.text)
```

### List and Filter Voices

```python
from fishaudio import FishAudio

client = FishAudio()

# List available voices
voices = client.voices.list(language="en")

for voice in voices:
    print(f"{voice.title} - {voice.id}")
```

### Async Usage

```python
import asyncio
from fishaudio import AsyncFishAudio

async def main():
    client = AsyncFishAudio()

    audio = await client.tts.convert(text="Async text-to-speech!")
    # Process audio...

asyncio.run(main())
```

### Check Account Credits

```python
from fishaudio import FishAudio

client = FishAudio()
credits = client.account.get_credits()
print(f"Remaining credits: {credits.credit}")
```

[More examples in /examples directory](./examples/)

---

## Documentation

- [API Reference](https://docs.fish.audio) - Complete API documentation with all parameters and options
- [Tutorials & Guides](https://docs.fish.audio) - Step-by-step tutorials for common use cases
- [Examples](./examples/) - Sample code demonstrating various features
- [Migration Guide](https://docs.fish.audio) - Guide for upgrading from the legacy SDK

---

## Requirements

- Python 3.9 or higher
- Fish Audio API key - [Get one here](https://fish.audio)

### Optional Dependencies

For audio playback utilities:

```bash
pip install fish-audio-sdk[utils]
```

This installs `sounddevice` and `soundfile` for the `play()` utility function.

---

## Community & Support

- [Discord Community](https://fish.audio) - Join our community for discussions and support
- [GitHub Issues](https://github.com/fishaudio/fish-audio-python/issues) - Report bugs or request features
- [Documentation](https://docs.fish.audio) - Comprehensive guides and API reference

---

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## Legacy SDK

The legacy `fish_audio_sdk` module is still available for existing projects:

```python
from fish_audio_sdk import Session

session = Session("your_api_key")
```

We recommend migrating to the new `fishaudio` module for new projects. See our [Migration Guide](https://docs.fish.audio) for assistance.
