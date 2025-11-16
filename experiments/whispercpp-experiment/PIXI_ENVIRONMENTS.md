# Pixi Environments for voiceType

The pyproject.toml now includes multiple pixi environments for different use cases.

## Available Environments

### 1. `local` (default)
**Purpose:** Standard local development with GPU support

**Includes:**
- voiceType2 (editable install)
- faster-whisper
- CUDA dependencies (libcublas=12, cudnn) on Linux/Windows

**Use when:**
- You have an NVIDIA GPU
- You want the best performance
- Local development on a GPU-enabled machine

**Activate:**
```bash
pixi shell          # Uses default environment
pixi shell -e local
```

### 2. `dev`
**Purpose:** Development environment with all testing dependencies

**Includes:**
- Everything from `local`
- pywhispercpp (for whisper.cpp testing)
- pre-commit
- pytest

**Use when:**
- Running experiments and benchmarks
- Testing different backends
- Contributing to the project

**Activate:**
```bash
pixi shell -e dev
```

**Run benchmark:**
```bash
pixi run -e dev python experiments/test_whisper_backends.py
```

### 3. `cpu` (new!)
**Purpose:** CPU-only deployment without CUDA dependencies

**Includes:**
- voiceType2 (editable install)
- faster-whisper (CPU mode)
- pywhispercpp (optimized for CPU)
- NO CUDA dependencies (smaller, more portable)

**Use when:**
- No GPU available
- Deploying on CPU-only systems
- Testing CPU performance
- Smaller installation footprint

**Activate:**
```bash
pixi shell -e cpu
```

**Run app:**
```bash
pixi run -e cpu run-voicetype
```

### 4. `build`
**Purpose:** Building and packaging

**Includes:**
- hatch
- hatch-vcs

**Use when:**
- Building distributions
- Creating releases

**Activate:**
```bash
pixi shell -e build
```

## Switching Between Environments

You can easily switch between GPU and CPU modes:

```bash
# Use GPU (default)
pixi shell -e local
run-voicetype

# Use CPU only
pixi shell -e cpu
run-voicetype
```

Make sure your `settings.toml` is configured appropriately for the environment you're using.

## Configuration Recommendations

### For GPU environment (`local` or `dev`)
```toml
[stage_configs.Transcribe]
backend = "faster-whisper"
device = "cuda"
model = "large-v3-turbo"
```

### For CPU environment (`cpu`)
```toml
[stage_configs.Transcribe]
backend = "pywhispercpp"  # or "faster-whisper"
device = "cpu"
model = "base.en"
n_threads = 4
```

## Installing Dependencies

After updating pyproject.toml, sync the environment:

```bash
# Update specific environment
pixi install -e cpu
pixi install -e dev

# Or update all environments
pixi install
```

## Benefits of the New `cpu` Environment

1. **No CUDA dependencies** - Smaller installation, faster setup
2. **Includes pywhispercpp** - Pre-configured for best CPU performance
3. **Portable** - Run on any machine without GPU
4. **Easy testing** - Quickly test CPU vs GPU performance

## Example Workflow

**Develop on GPU, deploy on CPU:**

```bash
# Develop with GPU
pixi shell -e dev
# ... make changes ...

# Test on CPU
pixi shell -e cpu
pixi run -e cpu python experiments/test_whisper_backends.py

# Update config for CPU
# Edit settings.toml to use CPU mode

# Run with CPU
pixi run -e cpu run-voicetype
```
