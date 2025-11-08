"""
Simple Text-to-Speech Example

This example demonstrates the most basic usage of the Fish Audio SDK:
- Initialize the client
- Convert text to speech
- Save the audio to an MP3 file

Requirements:
    pip install fishaudio

Environment Setup:
    export FISH_AUDIO_API_KEY="your_api_key_here"
    # Or pass api_key directly to the client

Expected Output:
    - Creates "output.mp3" in the current directory
    - Audio file contains the spoken text
"""

import os
from fishaudio import FishAudio
from fishaudio.utils import save


def main():
    # Initialize the client with your API key
    # Option 1: Use environment variable FISH_AUDIO_API_KEY
    # Option 2: Pass api_key directly: FishAudio(api_key="your_key")
    client = FishAudio()

    # The text you want to convert to speech
    text = "Hello! This is a simple text-to-speech example using the Fish Audio SDK."

    print(f"Converting text to speech: '{text}'")

    # Convert text to speech
    # This returns an iterator of audio bytes
    audio = client.tts.convert(text=text)

    # Save the audio to a file
    output_file = "output.mp3"
    save(audio, output_file)

    print(f"✓ Audio saved to {output_file}")
    print(f"  File size: {os.path.getsize(output_file) / 1024:.2f} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have set your API key:")
        print("  export FISH_AUDIO_API_KEY='your_api_key'")
