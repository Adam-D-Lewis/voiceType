# Pi-Mono + Local LLM (llama.cpp) Setup Guide

## Overview

[Pi](https://github.com/badlogic/pi-mono) is a minimal terminal coding harness that supports
multiple LLM providers. It can connect to a local llama.cpp server via its OpenAI-compatible API,
giving you a fully offline agentic coding tool.

## Prerequisites

- Node.js 22+
- A GPU with sufficient VRAM (6GB minimum, 24GB recommended)
- llama.cpp built from source or prebuilt binary

## 1. Install Pi Coding Agent

```bash
npm install -g @mariozechner/pi-coding-agent
```

Verify installation:
```bash
pi --version
```

## 2. Install llama.cpp

### From source (Linux)

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DGGML_CUDA=ON   # Use -DGGML_METAL=ON on macOS
cmake --build build --config Release -j
```

The server binary will be at `build/bin/llama-server`.

### Pre-built binaries

Download from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases).

## 3. Download a Model

Recommended models for agentic coding (GGUF format from Hugging Face):

| Model | Parameters | Min VRAM | Notes |
|-------|-----------|----------|-------|
| Devstral-Small-2507 | 24B | 16GB (Q4_K_M) | Best overall for coding |
| Qwen3-30B-A3B | 30B (3B active) | 6GB (IQ4_XS) | MoE, runs on less VRAM |
| Qwen3-Coder-Flash | 30B (3B active) | 6GB (IQ4_XS) | Coding-optimized MoE |

Download example:
```bash
# Using huggingface-cli
pip install huggingface-hub
huggingface-cli download bartowski/Devstral-Small-2507-GGUF \
  Devstral-Small-2507-Q4_K_M.gguf --local-dir ./models
```

## 4. Start llama-server

### 24GB GPU (e.g., RTX 4090)

```bash
llama-server \
  -m ./models/Devstral-Small-2507-Q4_K_M.gguf \
  -a Devstral-Small-2507 \
  -c 131072 \
  -fa \
  -ngl 99 \
  -ctk q4_0 -ctv q4_0 \
  --jinja
```

### 12GB GPU (e.g., RTX 3060/4070)

```bash
llama-server \
  -m ./models/Devstral-Small-2507-Q2_K_L.gguf \
  -a Devstral-Small-2507 \
  -c 131072 \
  -fa \
  -ngl 99 \
  -ot ".ffn_(up|down)_exps.=CPU" \
  -ctk q8_0 -ctv q8_0 \
  -nkvo \
  --jinja
```

### 6GB GPU (e.g., RTX 3060 6GB)

```bash
llama-server \
  -m ./models/Qwen3-30B-A3B-Instruct-2507-IQ4_XS.gguf \
  -a Qwen3-30B-A3B \
  -c 131072 \
  -fa \
  -ngl 20 \
  -nkvo \
  --jinja
```

### Key flags

| Flag | Purpose |
|------|---------|
| `-c` | Context size in tokens (131072 = 128k) |
| `-fa` | Flash attention (faster, less VRAM) |
| `-ngl` | GPU layers to offload (99 = all) |
| `-ctk/-ctv` | KV cache quantization (saves VRAM) |
| `-nkvo` | Keep KV cache in system RAM |
| `--jinja` | Enable Jinja templates (required for tool calling) |
| `-ot` | Offload specific tensor patterns to CPU |

The server will start on `http://localhost:8080` by default.

## 5. Configure Pi to Use llama.cpp

Create or edit `~/.pi/agent/models.json`:

```json
{
  "providers": {
    "llama-cpp": {
      "baseUrl": "http://localhost:8080/v1",
      "api": "openai-completions",
      "apiKey": "not-needed",
      "compat": {
        "supportsUsageInStreaming": false,
        "supportsStore": false,
        "maxTokensField": "max_tokens"
      },
      "models": [
        {
          "id": "devstral-small",
          "name": "Devstral Small 2507 (Local llama.cpp)",
          "reasoning": false,
          "input": ["text"],
          "contextWindow": 131072,
          "maxTokens": 32000,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```

The model `id` should match the alias you set with `-a` when starting llama-server,
or the model name the server reports at its `/v1/models` endpoint.

**Note:** This config hot-reloads — edit it while pi is running and open `/model` to
pick up changes without restarting.

### Compat field reference

| Field | Default | Description |
|-------|---------|-------------|
| `supportsUsageInStreaming` | `true` | Set `false` if server doesn't support `stream_options.include_usage` |
| `supportsStore` | `true` | Set `false` — llama.cpp doesn't support the `store` field |
| `maxTokensField` | `max_completion_tokens` | Use `max_tokens` for llama.cpp compatibility |
| `supportsDeveloperRole` | `true` | Whether to use `developer` vs `system` role |
| `supportsReasoningEffort` | depends | Set `true` for reasoning models |

## 6. Run Pi

```bash
# Start pi and select your local model
pi

# Then press Ctrl+L or type /model to select llama-cpp provider
```

Select the `llama-cpp` provider and your model from the list.

### Direct model selection

```bash
pi --provider llama-cpp --model devstral-small "Help me refactor this function"
```

Or using prefix notation:
```bash
pi --model llama-cpp/devstral-small "Explain this codebase"
```

## 7. Adding More Models

To add another model, just append to the `models` array in `models.json`:

```json
{
  "id": "qwen3-coder-flash",
  "name": "Qwen3 Coder Flash (Local)",
  "reasoning": true,
  "input": ["text"],
  "contextWindow": 131072,
  "maxTokens": 65536,
  "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
}
```

If using a reasoning model (like Qwen3), set `"reasoning": true` so Pi will send
the `reasoning_effort` parameter and handle thinking tokens in responses.

## Troubleshooting

### "Context overflow" errors
Increase the `-c` flag on llama-server or reduce `contextWindow` in models.json.
Minimum recommended: 64k tokens for effective agentic coding.

### Tool calling not working
Make sure `--jinja` flag is passed to llama-server. This enables the chat template
processing needed for function/tool calling.

### Slow generation
- Increase `-ngl` to offload more layers to GPU
- Use a smaller quantization (Q2_K_L instead of Q4_K_M)
- Use a MoE model (Qwen3-30B-A3B) which only activates 3B params per token

### Server connection refused
Verify llama-server is running and the port matches `baseUrl` in models.json.
Default is `http://localhost:8080/v1`.
