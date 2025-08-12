# Project Progress and Task Breakdown

## 1. Hotkey Detection (Platform Dependent)
- [x] **Define Abstraction:** Create a `HotkeyListener` abstract base class or interface defining methods like `start_listening()`, `stop_listening()`, `set_hotkey()`, and a way to signal hotkey press/release events (e.g., callbacks or event queue).
- [ ] **Implement Configuration:** Design and implement a mechanism to allow users to configure the desired hotkey (e.g., config file, simple UI).
- [ ] **Implement Platform Detection:** Add logic to detect the current operating system (Linux, Windows, Mac) and, specifically for Linux, the display server type (X11/Wayland).
- [x] **Implement Linux X11 Listener:**
    - [x] Create a `LinuxX11HotkeyListener` class inheriting from `HotkeyListener`.
    - [x] Use `pynput` or `keyboard` library to capture global key events.
    - [x] Implement logic to detect the configured hotkey press/release.
    - [x] Signal events according to the abstraction.
- [x] **Implement Linux Wayland Listener:**
    - [x] Create a `LinuxWaylandHotkeyListener` class inheriting from `HotkeyListener`.
    - [x] **Research/Implement DE Integration:** Implement D-Bus integration for GNOME (`org.gnome.settings-daemon.plugins.media-keys`). (KDE TBD).
    - [x] **Fallback/Inform:** If DE integration fails or isn't applicable, attempt fallback using `pynput`/`keyboard` (documenting limitations) or inform the user that manual configuration/alternative methods might be needed. Avoid `evdev`. (Implemented fallback in `__main__.py`).
    - [x] Signal press/release events according to the abstraction (Release simulated immediately after press for Wayland/GNOME).
- [ ] **Implement Windows Listener:**
    - [ ] Create a `WindowsHotkeyListener` class inheriting from `HotkeyListener`.
    - [ ] Use `pywin32` or `ctypes` to call `RegisterHotKey` and listen for `WM_HOTKEY` messages in a dedicated thread or message loop.
    - [ ] Alternatively, investigate `pynput` or `keyboard` library implementation for Windows.
    - [ ] Signal events according to the abstraction.
- [ ] **Implement macOS Listener:**
    - [ ] Create a `MacHotkeyListener` class inheriting from `HotkeyListener`.
    - [ ] Use `pyobjc` to access `AppKit.NSEvent.addGlobalMonitorForEvents(matching:handler:)`. Handle necessary permissions requests.
    - [ ] Alternatively, investigate `pynput` or `keyboard` library implementation for macOS.
    - [ ] Signal events according to the abstraction.
- [x] **Integrate Listener:** In the main application logic, instantiate the appropriate platform-specific listener based on detection results. Connect the listener's press/release signals to the audio capture start/stop functions (`voicetype/__main__.py`).
- [ ] (Optional) Extend support for mouse hotkeys if feasible within the chosen libraries/APIs.

## 2. Audio Capture (Platform Independent)
- [x] Capture audio from the system microphone (voice.py provides this logic).
- [ ] Refactor SpeechProcessor to allow starting/stopping recording based on external signals (hotkey events), not blocking prompt.
- [ ] Enforce a 1-minute max duration for a single recording.
- [ ] Ensure the default mic is used (voice.py already supports device selection).
- [ ] (Optional) Stream audio to the speech-to-text model for lower latency.

## 3. Speech-to-Text Integration (Platform Independent)
- [x] Send the captured audio to a speech-to-text model (voice.py uses Whisper via litellm).
- [ ] Support both local and remote models, configurable by the user (voice.py currently uses litellm; add config options).
- [ ] Manual configuration of model/service is acceptable; auto-detection is a nice-to-have but not required.
- [ ] English language support is required; multi-language support is optional.
- [ ] (Nice-to-have) Support punctuation and formatting commands (e.g., "comma", "new line").

## 4. Text Injection (Platform Dependent)
- [ ] After transcription, inject the text into the currently focused application as if typed.
- [ ] Implement text injection for Linux (X11/Wayland), Windows, and Mac using platform-appropriate tools/libraries.
- [ ] Abstract text injection behind a platform interface for cross-platform support.

## 5. Feedback Mechanism (Mostly Not Platform Dependent b/c Pystray)
- [ ] Provide visual/audio feedback during recording and transcription (e.g., system tray icon, notification, or sound).
- [ ] System tray indicator should also show errors (e.g., if unable to connect to the speech model).
- [ ] Feedback must work on Ubuntu GNOME, Windows, and Mac. Use platform-appropriate libraries or APIs.
- [ ] Abstract feedback mechanism behind a platform interface for cross-platform support.
- Note: Pystray is cross platform and should work here

## 6. Error Handling & Logging
- [x] Log errors (voice.py prints errors; extend to log and show feedback via tray icon or notification).
- [ ] Ensure errors are surfaced in the feedback mechanism (tray icon/notification).

## 7. Configuration & Preferences
- [ ] Allow users to configure hotkey, model selection, and feedback options.
- [ ] Ensure privacy: Audio is only captured during hotkey press.
- [ ] (Nice-to-have) Low latency for all operations.
- [ ] Implement "Run on Startup" functionality:
    - [ ] Detect the operating system (Linux, Windows, macOS). (Linux part started)
    - [ ] Implement logic to create appropriate startup entries:
        - [x] Linux: Create and manage a user systemd service (`~/.config/systemd/user/voicetype.service`). (via `voicetype/install.py`)
        - [ ] Windows: Registry entry (`HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`) or Startup folder shortcut.
        - [ ] macOS: LaunchAgent (`~/Library/LaunchAgents/com.yourdomain.voicetype.plist`).
    - [x] Provide a configuration option for the user to enable/disable running on startup (including enabling/disabling the systemd service on Linux). (via `voicetype/install.py install/uninstall`)
