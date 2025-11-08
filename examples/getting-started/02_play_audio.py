"""
Play Audio Example

This example demonstrates how to play generated audio immediately:
- Generate text-to-speech audio
- Play audio using the play() utility
- Different playback methods (ffmpeg, sounddevice)

Requirements:
    pip install fishaudio

    # For audio playback (choose one):
    # Option 1 (recommended): Install ffmpeg
    #   macOS: brew install ffmpeg
    #   Ubuntu: sudo apt install ffmpeg
    #   Windows: Download from ffmpeg.org

    # Option 2: Use sounddevice (Python-only)
    #   pip install sounddevice soundfile

Environment Setup:
    export FISH_AUDIO_API_KEY="your_api_key_here"

Expected Output:
    - Plays the generated audio through your speakers
    - No file is saved (unless you uncomment the save section)
"""

from fishaudio import FishAudio
from fishaudio.utils import play


def main():
    # Initialize the client
    client = FishAudio()

    # Text to convert to speech
    text = "Welcome to Fish Audio! This audio will play immediately after generation."

    print(f"Generating speech: '{text}'")
    print("Please ensure your speakers are on...\n")

    # Generate the audio
    audio = client.tts.convert(text=text)

    # Play the audio immediately
    # By default, this uses ffplay (from ffmpeg) if available,
    # otherwise falls back to sounddevice
    print("▶ Playing audio...")
    play(audio)
    print("✓ Playback complete!")

    # Optional: Save the audio to a file as well
    # Uncomment the following lines if you want to save it:
    # print("\nSaving audio to file...")
    # audio = client.tts.convert(text=text)  # Regenerate since audio was consumed
    # save(audio, "playback_example.mp3")
    # print("✓ Saved to playback_example.mp3")


def demo_playback_methods():
    """
    Demonstrate different playback methods.

    Note: The play() function automatically chooses the best available method,
    but you can force specific methods by modifying the code.
    """
    client = FishAudio()
    text = "This is a demonstration of different playback methods."

    # Method 1: Default (uses ffmpeg if available)
    print("Method 1: Default playback")
    audio = client.tts.convert(text=text)
    play(audio, use_ffmpeg=True)

    # Method 2: Using sounddevice (requires pip install sounddevice soundfile)
    print("\nMethod 2: Sounddevice playback")
    audio = client.tts.convert(text=text)
    play(audio, use_ffmpeg=False)

    # Method 3: Jupyter notebook mode (for .ipynb files)
    # This returns an IPython.display.Audio object
    # Uncomment if running in a notebook:
    # audio = client.tts.convert(text=text)
    # play(audio, notebook=True)


if __name__ == "__main__":
    try:
        main()

        # Uncomment to try different playback methods:
        # print("\n" + "="*50)
        # print("Testing different playback methods...")
        # print("="*50 + "\n")
        # demo_playback_methods()

    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure your API key is set: export FISH_AUDIO_API_KEY='your_key'")
        print("2. Install ffmpeg for audio playback:")
        print("   - macOS: brew install ffmpeg")
        print("   - Ubuntu: sudo apt install ffmpeg")
        print("3. Or install sounddevice: pip install sounddevice soundfile")
