# Whisper Backend Comparison Experiment

This experiment explores different options for running Whisper speech-to-text models, with a focus on CPU-only deployments for better portability.

## Current Implementation

The voiceType package currently uses:
- **Backend**: `faster-whisper` (via `speech_recognition` library)
- **Device**: CUDA (NVIDIA GPU)
- **Model**: `large-v3-turbo`

This works great if you have an NVIDIA GPU, but won't work on systems without one.

## Alternative Options

### 1. faster-whisper on CPU
**Pros:**
- Same backend as current implementation (familiar)
- No code changes needed, just configuration
- Good accuracy with proper model selection

**Cons:**
- Slower than GPU
- Not as optimized for CPU as whisper.cpp

### 2. pywhispercpp (whisper.cpp)
**Pros:**
- Highly optimized for CPU inference
- C++ implementation with minimal overhead
- Supports multi-threading for better CPU utilization
- Potentially faster than faster-whisper on CPU

**Cons:**
- Different API (requires code changes)
- Less mature Python bindings
- Need to install separately

## Running the Benchmark

### Prerequisites

The benchmark requires `pywhispercpp` to test the whisper.cpp backend.

**Option 1: Using pixi (recommended)**

Switch to the dev environment which includes pywhispercpp:

```bash
pixi shell -e dev
```

Or use the new CPU-only environment:

```bash
pixi shell -e cpu
```

**Option 2: Install manually**

```bash
pip install pywhispercpp
```

### Run the Benchmark

```bash
# With pixi dev environment
pixi run -e dev python experiments/test_whisper_backends.py

# With pixi CPU environment
pixi run -e cpu python experiments/test_whisper_backends.py

# Or if you installed pywhispercpp manually
python experiments/test_whisper_backends.py
```

This will test:
- faster-whisper with CUDA (current setup)
- faster-whisper with CPU (tiny, base, small models)
- pywhispercpp with CPU (tiny.en, base.en, small.en models)

The script will output:
- Transcription results for each configuration
- Processing time for each
- Recommendations for CPU-only deployment

## Expected Results

Based on typical performance:

1. **GPU (current)**: ~0.1-0.5s (fastest)
2. **pywhispercpp CPU (tiny.en)**: ~1-3s (fast, lower accuracy)
3. **pywhispercpp CPU (base.en)**: ~2-5s (good balance)
4. **faster-whisper CPU (base)**: ~3-8s (slower but accurate)
5. **faster-whisper CPU (small)**: ~5-15s (slower, higher accuracy)

## Configuration Examples

See `whisper_config_examples.toml` for ready-to-use configuration snippets.

### Quick Start: Enable CPU mode

Add to your `settings.toml`:

```toml
[stage_configs.Transcribe]
provider = "local"
backend = "faster-whisper"  # or "pywhispercpp"
device = "cpu"
model = "base"  # or "tiny" for faster, "small" for more accurate
```

## Model Size Recommendations

| Model | Size | Use Case |
|-------|------|----------|
| tiny | 39M | Ultra-fast, lower accuracy, real-time on older CPUs |
| base | 74M | **Recommended for CPU**: good balance |
| small | 244M | Better accuracy, still reasonable on modern CPUs |
| medium | 769M | High accuracy, slow on CPU |
| large-v3-turbo | 1550M | Best accuracy, GPU recommended |

## Next Steps

After running the benchmark:

1. Review the results to see which backend/model works best for your CPU
2. Update your `settings.toml` with the chosen configuration
3. Test in the actual voiceType application
4. Consider making backend/device configurable via settings (see implementation task below)

## Implementation Task

To make this fully configurable in the main codebase, we would need to:

1. Update `voicetype/pipeline/stages/transcribe.py` to support multiple backends
2. Add configuration options for:
   - `backend` (faster-whisper vs pywhispercpp)
   - `device` (cuda vs cpu)
   - `model` (size)
   - `compute_type` (for faster-whisper)
   - `n_threads` (for pywhispercpp)
3. Update documentation to explain the trade-offs
