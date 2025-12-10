"""Test LiteLLM connection to remote Ollama instance."""

import litellm

# Enable debug mode
litellm._turn_on_debug()

OLLAMA_BASE_URL = "http://mantra.adamdlewis.com:11434"
MODEL = "ollama/ministral-3:8b"


def test_basic_completion():
    """Test basic completion with remote Ollama."""
    print(f"Testing connection to {OLLAMA_BASE_URL}")
    print(f"Model: {MODEL}")
    print("-" * 50)

    try:
        response = litellm.completion(
            model=MODEL,
            api_base=OLLAMA_BASE_URL,
            messages=[
                {
                    "role": "user",
                    "content": "What model are you? Reply in one sentence.",
                }
            ],
            timeout=60,  # Longer timeout for testing
        )

        print("Success!")
        print(f"Response: {response.choices[0].message.content}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


def test_with_requests():
    """Test direct HTTP request to Ollama API."""
    import requests

    print("\n" + "=" * 50)
    print("Testing direct HTTP request to Ollama API")
    print("=" * 50)

    # Test version endpoint
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/version", timeout=10)
        print(f"Version endpoint: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Version endpoint error: {e}")

    # Test tags (list models)
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        print(f"Available models: {resp.json()}")
    except Exception as e:
        print(f"Tags endpoint error: {e}")

    # Test generate endpoint directly
    print("\nTesting generate endpoint directly...")
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "ministral-3:8b",
                "prompt": "What model are you? Reply in one sentence.",
                "stream": False,
            },
            timeout=60,
        )
        print(f"Generate response: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Response: {resp.json().get('response', 'No response field')}")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Generate endpoint error: {e}")


if __name__ == "__main__":
    test_with_requests()
    print("\n" + "=" * 50)
    print("Testing LiteLLM completion")
    print("=" * 50)
    test_basic_completion()
