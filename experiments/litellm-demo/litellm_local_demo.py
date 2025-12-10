"""
Demonstration of using LiteLLM with locally running LLMs.

LiteLLM provides a unified interface for various LLM providers including
local models running via Ollama, VLLM, LM Studio, etc.
"""

from litellm import completion

# ============================================================================
# Example 1: Using Ollama (default port 11434)
# ============================================================================
# First, make sure Ollama is running with a model:
#   ollama serve
#   ollama pull gemma3:270m   # Very small/fast model (291 MB)
#   ollama pull gemma3:1b     # Small model (815 MB)
#   ollama pull llama3.2      # Medium model (2.0 GB)


def query_ollama(prompt: str, model: str = "gemma3:270m"):
    """
    Query a locally running Ollama instance.

    Args:
        prompt: The text prompt to send
        model: The Ollama model name (e.g., "gemma3:270m", "gemma3:1b", "llama3.2")
    """
    print(f"\n{'='*60}")
    print(f"Querying Ollama with model: {model}")
    print(f"{'='*60}")

    response = completion(
        model=f"ollama/{model}",
        messages=[{"role": "user", "content": prompt}],
        api_base="http://localhost:11434",  # Default Ollama port
        temperature=0.7,
        max_tokens=500,
    )

    print(f"Response: {response.choices[0].message.content}")
    return response


# ============================================================================
# Example 2: Using VLLM (OpenAI-compatible server)
# ============================================================================
# Start VLLM with:
#   vllm serve <model_name> --port 8000
#   e.g., vllm serve meta-llama/Llama-2-7b-chat-hf --port 8000


def query_vllm(prompt: str, model: str = "meta-llama/Llama-2-7b-chat-hf"):
    """
    Query a locally running VLLM instance.

    Args:
        prompt: The text prompt to send
        model: The model name that VLLM is serving
    """
    print(f"\n{'='*60}")
    print(f"Querying VLLM with model: {model}")
    print(f"{'='*60}")

    response = completion(
        model=f"openai/{model}",  # VLLM uses OpenAI-compatible API
        messages=[{"role": "user", "content": prompt}],
        api_base="http://localhost:8000/v1",  # VLLM's OpenAI-compatible endpoint
        temperature=0.7,
        max_tokens=500,
    )

    print(f"Response: {response.choices[0].message.content}")
    return response


# ============================================================================
# Example 3: Using LM Studio (OpenAI-compatible server)
# ============================================================================
# Start LM Studio and load a model, then start the local server
# (default port is usually 1234)


def query_lm_studio(prompt: str, model: str = "local-model"):
    """
    Query a locally running LM Studio instance.

    Args:
        prompt: The text prompt to send
        model: Can be any identifier, LM Studio uses whatever is loaded
    """
    print(f"\n{'='*60}")
    print(f"Querying LM Studio")
    print(f"{'='*60}")

    response = completion(
        model=f"openai/{model}",
        messages=[{"role": "user", "content": prompt}],
        api_base="http://localhost:1234/v1",  # Default LM Studio port
        temperature=0.7,
        max_tokens=500,
    )

    print(f"Response: {response.choices[0].message.content}")
    return response


# ============================================================================
# Example 4: Streaming responses
# ============================================================================


def query_ollama_streaming(prompt: str, model: str = "gemma3:270m"):
    """
    Query Ollama with streaming response.
    """
    print(f"\n{'='*60}")
    print(f"Streaming from Ollama with model: {model}")
    print(f"{'='*60}")
    print("Response: ", end="", flush=True)

    response = completion(
        model=f"ollama/{model}",
        messages=[{"role": "user", "content": prompt}],
        api_base="http://localhost:11434",
        stream=True,
        temperature=0.7,
        max_tokens=500,
    )

    full_response = ""
    for chunk in response:
        content = chunk.choices[0].delta.content or ""
        print(content, end="", flush=True)
        full_response += content

    print("\n")
    return full_response


# ============================================================================
# Example 5: Multi-turn conversation
# ============================================================================


def multi_turn_conversation(model: str = "gemma3:270m"):
    """
    Demonstrate a multi-turn conversation.
    """
    print(f"\n{'='*60}")
    print(f"Multi-turn conversation with Ollama/{model}")
    print(f"{'='*60}")

    messages = [
        {"role": "user", "content": "What is the capital of France?"},
    ]

    # First turn
    response = completion(
        model=f"ollama/{model}",
        messages=messages,
        api_base="http://localhost:11434",
        temperature=0.7,
    )

    assistant_msg = response.choices[0].message.content
    print(f"User: {messages[0]['content']}")
    print(f"Assistant: {assistant_msg}\n")

    # Add response to conversation history
    messages.append({"role": "assistant", "content": assistant_msg})

    # Second turn
    messages.append({"role": "user", "content": "What is the population of that city?"})

    response = completion(
        model=f"ollama/{model}",
        messages=messages,
        api_base="http://localhost:11434",
        temperature=0.7,
    )

    assistant_msg = response.choices[0].message.content
    print(f"User: {messages[-1]['content']}")
    print(f"Assistant: {assistant_msg}")

    return messages


# ============================================================================
# Example 6: Error handling
# ============================================================================


def query_with_error_handling(prompt: str, model: str = "gemma3:270m"):
    """
    Query with proper error handling.
    """
    try:
        response = completion(
            model=f"ollama/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_base="http://localhost:11434",
            temperature=0.7,
            max_tokens=500,
            timeout=30,  # Add timeout
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error querying LLM: {e}")
        print(f"Make sure your local LLM server is running!")
        print(f"For Ollama: ollama serve")
        print(f"For VLLM: vllm serve <model> --port 8000")
        return None


# ============================================================================
# Main demo
# ============================================================================

if __name__ == "__main__":
    # Example prompt
    prompt = "Explain what a binary search tree is in one sentence."

    print("\n" + "=" * 60)
    print("LiteLLM Local LLM Demo")
    print("=" * 60)

    # Uncomment the examples you want to try:

    # Example 1: Basic Ollama query
    print("\n--- Example 1: Basic Ollama Query ---")
    try:
        query_ollama(prompt, model="gemma3:270m")
    except Exception as e:
        print(f"Failed: {e}")
        print("Make sure Ollama is running: ollama serve")

    # Example 2: VLLM query
    # print("\n--- Example 2: VLLM Query ---")
    # try:
    #     query_vllm(prompt, model="your-model-name")
    # except Exception as e:
    #     print(f"Failed: {e}")

    # Example 3: LM Studio query
    # print("\n--- Example 3: LM Studio Query ---")
    # try:
    #     query_lm_studio(prompt)
    # except Exception as e:
    #     print(f"Failed: {e}")

    # Example 4: Streaming
    print("\n--- Example 4: Streaming Response ---")
    try:
        query_ollama_streaming(prompt, model="gemma3:270m")
    except Exception as e:
        print(f"Failed: {e}")

    # Example 5: Multi-turn conversation
    print("\n--- Example 5: Multi-turn Conversation ---")
    try:
        multi_turn_conversation(model="gemma3:1b")
    except Exception as e:
        print(f"Failed: {e}")

    # Example 6: With error handling
    print("\n--- Example 6: With Error Handling ---")
    result = query_with_error_handling(prompt, model="fake-model:270m")
    if result:
        print(f"Success! Got response: {result[:100]}...")
