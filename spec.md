# Requirement Specifications

## Overview
Create a tool that, when a configurable hotkey is pressed, captures audio from the system microphone and sends it to a speech-to-text model. When the hotkey is released, the transcribed text is "typed" into the active application as if entered by the user.

## Functional Requirements
1. **Button Activation (Platform Dependent)**
   - The system listens for a configurable hotkey press.
   - Audio capture starts when the hotkey is pressed and stops when released.
   - Hotkey detection must work on Linux (X11/Wayland), Windows, and Mac. Use platform-appropriate libraries or APIs.
     - **Linux:** Consider libraries like `pynput` (may have limitations on Wayland) or `keyboard`. Direct interaction with `evdev` or desktop environment APIs (like GNOME's settings daemon via D-Bus) might be necessary for robust Wayland support.
     - **Windows:** Libraries like `pynput` or `keyboard` are suitable. Direct WinAPI calls via `pywin32` or `ctypes` are also an option.
     - **Mac:** Libraries like `pynput` or `keyboard` can be used. Accessing macOS's event tap mechanism via `pyobjc` is another possibility.

2. **Audio Capture (Platform Independent)**
   - Capture audio from the system microphone during the hotkey press duration.
   - Maximum duration for a single recording is 1 minute.
   - (Optional) Stream audio to the speech-to-text model for lower latency.
   - Use cross-platform libraries for audio capture where possible.

3. **Speech-to-Text (Platform Independent)**
   - Send the captured audio to a speech-to-text model (local or cloud-based).
   - Support for both local models (e.g., OpenAI Whisper) and remote services.
   - English language support is required; multi-language support is optional.
   - Receive and process the transcribed text.

4. **Text Injection (Platform Dependent)**
   - After hotkey release, inject the transcribed text into the currently focused application as if typed by the user.
   - Implement text injection for Linux (X11/Wayland), Windows, and Mac using platform-appropriate tools/libraries.

5. **Feedback (Platform Dependent)**
   - Provide visual or audio feedback during recording and transcription (e.g., system tray icon or notification).
   - Feedback must work on Ubuntu GNOME, Windows, and Mac. Use platform-appropriate libraries or APIs.
   - System tray indicator should also show errors (e.g., if unable to connect to the speech model).

## Non-Functional Requirements
- Should work on Linux (must support Ubuntu GNOME), Windows, and Mac.
- Must support both X11 and Wayland display servers on Linux.
- Low latency is preferred but not required.
- Privacy: Audio is only captured during hotkey press.
- No visible UI is required except for feedback/indicators.
- Punctuation and formatting commands (e.g., "comma", "new line") are a nice-to-have feature, not mandatory.
- **Reliability:** The application should automatically restart if it crashes or encounters a fatal error.
- **Logging:** The application should log significant events, errors, and diagnostic information to a standard location (e.g., system log/journald, user-specific log file).

## Architecture Notes
- Hotkey detection, text injection, and feedback mechanisms should be abstracted behind a platform interface, with platform-specific implementations for Linux, Windows, and Mac.
- Audio capture and speech-to-text logic should be platform-independent, using cross-platform libraries where possible.
