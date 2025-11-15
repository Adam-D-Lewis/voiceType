# Whisper Backend Experiments

This directory contains experiments for testing different Whisper backends and configurations, with a focus on CPU-only deployments.

## Quick Links

- **[QUICKSTART_CPU.md](QUICKSTART_CPU.md)** - Fast guide to enable CPU mode
- **[WHISPER_BACKENDS.md](WHISPER_BACKENDS.md)** - Detailed explanation of backends and options
- **[PIXI_ENVIRONMENTS.md](PIXI_ENVIRONMENTS.md)** - Guide to using pixi environments
- **[whisper_config_examples.toml](whisper_config_examples.toml)** - Copy-paste config examples

## TL;DR - Enable CPU Mode

### Fastest Way (Using pixi)

```bash
# Switch to CPU environment
pixi shell -e cpu

# Your app now runs on CPU!
run-voicetype
```

### Manual Configuration

Edit `settings.toml`:

```toml
[stage_configs.Transcribe]
device = "cpu"
model = "base"
```

## What's New

### Code Changes

1. **[transcribe.py](../voicetype/pipeline/stages/transcribe.py)** - Now supports:
   - Multiple backends: `faster-whisper` and `pywhispercpp` (whisper.cpp)
   - Configurable device: `cuda` or `cpu`
   - Configurable model size
   - Auto-selects optimal settings for CPU/GPU

2. **[settings.py](../voicetype/settings.py)** - New config options documented

3. **[pyproject.toml](../pyproject.toml)** - New `cpu` pixi environment

### Experiment Files

- **test_whisper_backends.py** - Benchmark script comparing all backends
- **whisper_config_examples.toml** - Ready-to-use configurations
- Documentation files (this README and guides above)

## Running the Benchmark

Test which backend works best on your system:

```bash
# With pixi
pixi run -e dev python experiments/test_whisper_backends.py

# Without pixi
pip install pywhispercpp
python experiments/test_whisper_backends.py
```

The benchmark will show you:
- Speed comparison across backends and model sizes
- GPU vs CPU performance
- Recommendations for your hardware

## Backend Options

### 1. faster-whisper (Current Default)
- **Best for:** GPU users, proven stability
- **Device:** CUDA or CPU
- **Models:** tiny, base, small, medium, large-v3-turbo

### 2. pywhispercpp (whisper.cpp)
- **Best for:** CPU-only users, maximum CPU performance
- **Device:** CPU only
- **Models:** tiny.en, base.en, small.en, medium.en

## Model Size Guide

| Model | Parameters | Speed (CPU) | Accuracy | Best For |
|-------|-----------|-------------|----------|----------|
| tiny | 39M | ⚡⚡⚡ | ⭐⭐ | Real-time on old CPUs |
| base | 74M | ⚡⚡ | ⭐⭐⭐ | **Recommended for CPU** |
| small | 244M | ⚡ | ⭐⭐⭐⭐ | Modern CPUs, better accuracy |
| medium | 769M | 🐌 | ⭐⭐⭐⭐⭐ | High accuracy, slow on CPU |
| large-v3-turbo | 1550M | 🐌🐌 | ⭐⭐⭐⭐⭐ | **GPU only** |

Note: `.en` models (English-only) are ~20% faster than multilingual versions.

## Configuration Examples

### GPU Mode (Default)
```toml
[stage_configs.Transcribe]
backend = "faster-whisper"
device = "cuda"
model = "large-v3-turbo"
```

### CPU Mode - Balanced
```toml
[stage_configs.Transcribe]
backend = "pywhispercpp"
device = "cpu"
model = "base.en"
n_threads = 4
```

### CPU Mode - Fast
```toml
[stage_configs.Transcribe]
backend = "pywhispercpp"
device = "cpu"
model = "tiny.en"
n_threads = 4
```

## Pixi Environments

The project now has dedicated pixi environments:

- `local` - Default, GPU-enabled
- `dev` - Development with all test dependencies
- `cpu` - **New!** CPU-only without CUDA (smaller, portable)
- `build` - For packaging

See [PIXI_ENVIRONMENTS.md](PIXI_ENVIRONMENTS.md) for details.

## Next Steps

1. **Run the benchmark** to see performance on your hardware
2. **Choose a configuration** based on the results
3. **Update settings.toml** with your chosen backend/model
4. **Test in the app** to verify it works for your use case
5. **Fine-tune** model size and threads as needed

## Questions?

- **Which backend should I use?** Run the benchmark to see!
- **CPU too slow?** Try a smaller model (tiny.en instead of base.en)
- **Accuracy too low?** Try a larger model (small instead of base)
- **How to switch back to GPU?** Just set `device = "cuda"` in settings.toml

## Related Files

Implementation:
- [voicetype/pipeline/stages/transcribe.py](../voicetype/pipeline/stages/transcribe.py)
- [voicetype/settings.py](../voicetype/settings.py)

Tests:
- [tests/test_integration.py](../tests/test_integration.py)
- [experiments/test_transcribe.py](test_transcribe.py)
