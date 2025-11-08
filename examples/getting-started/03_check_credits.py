"""
Check Account Credits Example

This example demonstrates how to:
- Check your API account balance and credits
- View prepaid package information

This is useful for:
- Verifying your API setup
- Monitoring usage and remaining credits

Requirements:
    pip install fishaudio

Environment Setup:
    export FISH_AUDIO_API_KEY="your_api_key_here"

Expected Output:
    - Displays account credit balance
    - Shows prepaid package details (if any)
"""

from fishaudio import FishAudio


def main():
    # Initialize the client
    client = FishAudio()

    print("=" * 60)
    print("Fish Audio - Account Information")
    print("=" * 60)

    # Check account credits
    print("\nAccount Credits:")
    print("-" * 60)
    try:
        credits = client.account.get_credits()
        print(f"  Balance: {float(credits.credit):,.2f} credits")

        # Note: Credits are consumed based on usage
        # Check the Fish Audio pricing page for current rates

    except Exception as e:
        print(f"  Error fetching credits: {e}")

    # Check prepaid package information
    print("\nPrepaid Package:")
    print("-" * 60)
    try:
        package = client.account.get_package()
        if package:
            print("  Package details available")
            # Display package information based on the response structure
            print(f"  {package}")
        else:
            print("  No active prepaid package")

    except Exception as e:
        print(f"  Error fetching package: {e}")

    print("\n" + "=" * 60)
    print("Account information retrieved successfully")
    print("=" * 60)


def check_api_setup():
    """
    Quick check to verify your API is set up correctly.
    Returns True if everything is working, False otherwise.
    """
    try:
        client = FishAudio()

        # Try to fetch credits as a simple API test
        credits = client.account.get_credits()

        print("API setup is correct!")
        print(f"  Your current balance: {float(credits.credit):,.2f} credits")
        return True

    except Exception as e:
        print("API setup failed!")
        print(f"  Error: {e}")
        print("\nPlease check:")
        print("  1. Your API key is correct")
        print("  2. Environment variable is set: export FISH_AUDIO_API_KEY='your_key'")
        print("  3. You have an active internet connection")
        return False


if __name__ == "__main__":
    try:
        main()

        # Uncomment to run the quick setup check:
        # print("\n\nRunning quick API setup check...")
        # check_api_setup()

    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure you have set your API key:")
        print("  export FISH_AUDIO_API_KEY='your_api_key'")
        print("\nOr pass it directly when creating the client:")
        print("  client = FishAudio(api_key='your_api_key')")
