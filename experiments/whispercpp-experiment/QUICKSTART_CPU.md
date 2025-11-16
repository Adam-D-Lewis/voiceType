# Quick Start: Running voiceType on CPU

This guide shows you how to run voiceType without a GPU using CPU-based transcription.

## Option 1: Use faster-whisper on CPU (Easiest)

This uses the same backend you already have installed, just switches to CPU mode.

### Configuration

Edit your `settings.toml` (or create one if it doesn't exist):

```toml
[stage_configs.Transcribe]
provider = "local"
backend = "faster-whisper"
device = "cpu"
model = "base"  # Smaller model for reasonable CPU performance
```

**Model recommendations for CPU:**
- `tiny`: Fastest, lowest accuracy (~1-2s per 5s audio)
- `base`: **Recommended** - good balance (~2-4s per 5s audio)
- `small`: Better accuracy, slower (~5-10s per 5s audio)

## Option 2: Use whisper.cpp (Best CPU Performance)

whisper.cpp is highly optimized for CPU inference and may be faster than faster-whisper on CPU.

### Installation

**With pixi (recommended):**

Use the CPU-only environment that doesn't require CUDA:

```bash
pixi shell -e cpu
```

**Or install manually:**

```bash
pip install pywhispercpp
```

### Configuration

Edit your `settings.toml`:

```toml
[stage_configs.Transcribe]
provider = "local"
backend = "pywhispercpp"
device = "cpu"
model = "base.en"  # English-only models are faster
n_threads = 4      # Adjust based on your CPU cores
```

**Model recommendations:**
- `tiny.en`: Ultra-fast (~0.5-1s per 5s audio)
- `base.en`: **Recommended** - good balance (~1-2s per 5s audio)
- `small.en`: Better accuracy (~2-5s per 5s audio)

Note: `.en` models are English-only but faster than multilingual versions.

## Benchmarking

Before committing to a configuration, run the benchmark to see what works best on your system:

```bash
python experiments/test_whisper_backends.py
```

This will test multiple configurations and show you:
- Speed comparison between backends and models
- Transcription quality
- Recommendations for your hardware

## Example settings.toml

Create `settings.toml` in your project root:

```toml
# CPU-optimized configuration

[stage_configs]

[stage_configs.RecordAudio]
minimum_duration = 0.25

[stage_configs.Transcribe]
provider = "local"
backend = "faster-whisper"  # or "pywhispercpp" for better CPU performance
device = "cpu"
model = "base"              # or "base.en" for pywhispercpp
# n_threads = 4             # Uncomment if using pywhispercpp

[stage_configs.CorrectTypos]
case_sensitive = false
whole_word_only = true
corrections = []

[stage_configs.TypeText]

[[pipelines]]
name = "default"
enabled = true
hotkey = "<pause>"
stages = ["RecordAudio", "Transcribe", "CorrectTypos", "TypeText"]
```

## Switching Back to GPU

To switch back to GPU mode, just change the config:

```toml
[stage_configs.Transcribe]
provider = "local"
backend = "faster-whisper"
device = "cuda"
model = "large-v3-turbo"
```

## Performance Tips

1. **Use English-only models** (`.en`) if you only need English transcription
2. **Adjust thread count** for pywhispercpp based on your CPU cores (try 4, 8, or 16)
3. **Start with smaller models** (tiny/base) and increase if accuracy is insufficient
4. **Consider model quantization** - int8 compute_type is automatically used for CPU with faster-whisper

## Troubleshooting

**If pywhispercpp import fails:**
```bash
pip install pywhispercpp
# or
pixi add --pypi pywhispercpp
```

**If transcription is too slow:**
- Try a smaller model (tiny instead of base)
- Try pywhispercpp backend instead of faster-whisper
- Increase n_threads for pywhispercpp

**If accuracy is poor:**
- Try a larger model (small instead of base)
- Use non-.en models for better quality (but slower)
- Stick with faster-whisper backend for better quality
