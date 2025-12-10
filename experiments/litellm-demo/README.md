# LiteLLM Local LLM Demo

This directory contains examples of using the LiteLLM Python package to query locally running LLMs.

## Installation

```bash
pip install litellm
```

## Supported Local LLM Servers

### 1. Ollama (Recommended for beginners)

**Setup:**
```bash
# Install Ollama from https://ollama.ai
ollama serve

# Pull and run a model
ollama pull llama2
ollama pull mistral
ollama pull codellama
```

**Usage in LiteLLM:**
```python
from litellm import completion

response = completion(
    model="ollama/llama2",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:11434"
)
```

### 2. VLLM (High-performance inference)

**Setup:**
```bash
pip install vllm

# Start VLLM server
vllm serve meta-llama/Llama-2-7b-chat-hf --port 8000
```

**Usage in LiteLLM:**
```python
response = completion(
    model="openai/meta-llama/Llama-2-7b-chat-hf",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:8000/v1"
)
```

### 3. LM Studio (GUI-based)

**Setup:**
1. Download and install LM Studio
2. Load a model through the GUI
3. Start the local server (usually port 1234)

**Usage in LiteLLM:**
```python
response = completion(
    model="openai/local-model",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:1234/v1"
)
```

### 4. Text Generation WebUI (oobabooga)

**Setup:**
```bash
# Install from https://github.com/oobabooga/text-generation-webui
# Start with OpenAI-compatible API enabled
python server.py --api --extensions openai
```

**Usage in LiteLLM:**
```python
response = completion(
    model="openai/your-model",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:5000/v1"
)
```

## Running the Demo

```bash
# Make sure you have a local LLM running (e.g., Ollama)
ollama serve
ollama pull llama2

# Run the demo
python litellm_local_demo.py
```

## Key Features Demonstrated

1. **Basic queries** - Simple request/response
2. **Streaming responses** - Real-time token generation
3. **Multi-turn conversations** - Maintaining context
4. **Error handling** - Graceful failures
5. **Different backends** - Ollama, VLLM, LM Studio

## Common Issues

### Connection Refused
- Make sure your local LLM server is running
- Check the port number matches your server's port
- Try `curl http://localhost:11434` (for Ollama) to verify

### Model Not Found
- For Ollama: Run `ollama list` to see available models
- For VLLM: Make sure the model name matches what you started the server with

### Timeout Errors
- Increase the `timeout` parameter in the completion call
- Check if your model is loaded (some servers lazy-load)

## Environment Variables

You can also configure LiteLLM via environment variables:

```bash
export OLLAMA_API_BASE="http://localhost:11434"
export VLLM_API_BASE="http://localhost:8000/v1"
```

## Resources

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [VLLM Documentation](https://docs.vllm.ai/)
