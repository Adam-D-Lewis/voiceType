# Handy - Speech-to-Text Tool Analysis

**Repository:** https://github.com/cjpais/Handy
**License:** MIT
**Type:** Free, open-source, offline speech-to-text desktop app
**Architecture:** Tauri (Rust backend + React/TypeScript frontend)
**Platforms:** macOS (Intel & Apple Silicon), Windows (x64), Linux (x64)

## Features Potentially Worth Adding to VoiceType

### Parakeet V3 Model Support
CPU-optimized ASR model (alternative to Whisper) claiming ~5x real-time speed on mid-range hardware. No GPU required. Minimum Intel Skylake (6th gen) or equivalent AMD. Interesting option for users without GPU access.

### Apple Intelligence Post-Processing
On-device LLM post-processing on supported Macs via Apple Intelligence. Free, private, no API key needed. Unique approach to text cleanup that doesn't require any external API.

### LLM Post-Processing with Structured JSON Output
Sends transcribed text through any OpenAI-compatible LLM API with `strict: true` JSON schema validation for reliable structured output. Supports configurable providers (OpenAI, Anthropic, etc.) and saveable custom prompt templates for different use cases.

### Auto-Submit
Can automatically press Enter/Ctrl+Enter/Cmd+Enter after pasting transcription. Useful for chat applications where you want hands-free send.

### Multiple Paste Methods + External Script Hook
Supports CtrlV, Direct, ShiftInsert, CtrlShiftV, and notably ExternalScript - allows running a custom script on the transcribed text before pasting. Good extensibility point.

### Silero VAD (Voice Activity Detection)
Automatic end-of-speech detection that filters silence, so the user doesn't need to manually stop recording. The recording just processes when you stop talking.

### Push-to-Talk Mode
Hold-to-talk as a distinct mode alongside toggle (press once to start, once to stop).

### CLI Remote Control + Unix Signals
Running instance can be controlled via CLI flags (`--toggle-transcription`, `--cancel`, etc.) or Unix signals (SIGUSR1/SIGUSR2). Enables integration with window manager keybindings, scripts, and automation.

### Model Memory Management
Configurable model unload timeout (never, immediately, 2/5/10/15 min, 1 hour). Useful for balancing memory usage vs. transcription latency.

### Audio Feedback with Themes
Audible sounds (Marimba, Pop, or Custom themes) to signal recording start/stop, with configurable volume.

### Custom Words/Vocabulary
User-defined word list to improve transcription accuracy for domain-specific terms.

### Transcription History with Retention Policies
Saves transcription history with configurable retention (never delete, 3 days, 2 weeks, 3 months, or limit count). Stores both original and post-processed text.

### Chinese Variant Conversion
Automatic Simplified/Traditional Chinese conversion via OpenCC library.

## Architecture Notes
- Built on Tauri (Rust backend, React frontend) - very lightweight compared to Electron
- Uses whisper-rs and transcription-rs for local model inference
- Supports custom Whisper GGML models dropped into a models directory
- Silero VAD for voice activity detection
- Cross-platform audio via CPAL
- rdev for global keyboard shortcuts
