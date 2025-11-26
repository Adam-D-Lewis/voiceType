# Building VoiceType for Distribution

This guide explains how to build VoiceType installers for Windows users who don't have Python installed.

## Overview

VoiceType uses:
- **PyInstaller** - Creates standalone executables (bundles Python + dependencies)
- **NSIS** - Packages executables into user-friendly Windows installers
- **Startup Folder** - Automatically starts VoiceType on login (no admin required)

## Prerequisites

### Windows Build Requirements

1. **Python 3.11+** with VoiceType dependencies installed
2. **PyInstaller**: `pip install pyinstaller`
3. **NSIS (Nullsoft Scriptable Install System)**:
   - Download: https://nsis.sourceforge.io/Download
   - Or via Chocolatey: `choco install nsis`

### Verify Prerequisites

```bash
# Check Python and PyInstaller
python --version
pyinstaller --version

# Check NSIS (Windows)
makensis -VERSION
```

## Quick Start: Building for Windows

### One-Command Build (Using Pixi)

```bash
# Install the windows-build environment (first time only)
pixi install -e windows-build

# Build the complete installer
pixi run -e windows-build build-windows
```

This creates `dist/VoiceType-Setup.exe` ready for distribution.

### Alternative: Direct Python Script

```bash
# Clean build with installer (without pixi)
python build_scripts/build_windows.py --clean
```

### Step-by-Step Build Process

#### 1. Set Up Build Environment

```bash
# Option A: Using Pixi windows-build environment (recommended - includes PyInstaller)
pixi install -e windows-build
pixi shell -e windows-build

# Option B: Using Pixi local environment + manual PyInstaller install
pixi install -e local
pixi shell -e local
pip install pyinstaller

# Option C: Using pip in virtual environment
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install pyinstaller
```

**Note:** The `windows-build` pixi environment includes PyInstaller and all necessary build dependencies. Use pixi tasks for easier building (see below).

#### 2. Build with PyInstaller

**Using Pixi tasks (recommended):**

```bash
# Build complete installer (PyInstaller + NSIS)
pixi run -e windows-build build-windows

# Build executable only (skip NSIS installer)
pixi run -e windows-build build-exe

# Clean build artifacts
pixi run -e windows-build clean-build
```

**Using Python scripts directly:**

```bash
# Automated build with script
python build_scripts/build_windows.py --clean --no-installer

# Or manually with PyInstaller
pyinstaller --clean voicetype.spec
```

**Output:**
- `dist/voicetype/` - Standalone application folder
- `dist/voicetype/voicetype.exe` - Main executable (200-300 MB)

**What gets bundled:**
- ✅ Python 3.11 interpreter
- ✅ All dependencies (faster-whisper, litellm, pynput, etc.)
- ✅ VoiceType assets (sounds, icons)
- ✅ Windows DLLs and runtime libraries
- ❌ CUDA libraries (excluded to reduce size - CPU only by default)
- ❌ Development tools (pytest, pre-commit)

#### 3. Create Windows Installer

```bash
# Build NSIS installer
python build_scripts/build_windows.py

# Or manually
makensis build_scripts/windows/installer.nsi
```

**Output:**
- `dist/VoiceType-Setup.exe` - Windows installer (150-250 MB compressed)

**What the installer does:**
1. ✅ Installs to `C:\Program Files\VoiceType\`
2. ✅ Creates Start Menu shortcuts
3. ✅ Registers in Windows Add/Remove Programs
4. ✅ Creates startup shortcut (auto-start on login)
5. ✅ Launches VoiceType immediately after install
6. ✅ Bundles Whisper `tiny` model (no download on first use)

## Testing the Installer

**Important:** Test on a clean Windows machine without Python!

1. Run `VoiceType-Setup.exe`
2. Follow installation wizard
3. VoiceType should launch automatically and appear in the system tray
4. Test hotkey (default: Insert key)
5. Verify auto-start works after reboot
6. Check logs: `%APPDATA%\voicetype\voicetype.log`

## Configuration

### PyInstaller Spec File ([voicetype.spec](../voicetype.spec))

Controls what gets bundled into the executable:

```python
# Hidden imports - modules PyInstaller can't auto-detect
hiddenimports = [
    'voicetype._vendor.pynput',  # Vendored library
    'faster_whisper',             # Local transcription
    'litellm',                    # API client
    'sounddevice',                # Audio recording
    # ... platform-specific modules
]

# Excluded modules - reduce bundle size
excludes = [
    'torch',          # Heavy ML framework (not needed)
    'tensorflow',     # Not used
    'pytest',         # Dev only
]

# Data files to include
data = [
    ('voicetype/assets', 'voicetype/assets'),  # Sounds, icons
]
```

**To modify the build:**
1. Edit `voicetype.spec`
2. Add/remove hidden imports or exclusions
3. Rebuild: `pyinstaller --clean voicetype.spec`

### NSIS Installer Script ([installer.nsi](../build_scripts/windows/installer.nsi))

Controls installer behavior:

```nsis
!define APPNAME "VoiceType"
!define VERSIONMAJOR 0
!define VERSIONMINOR 1

InstallDir "$PROGRAMFILES64\${APPNAME}"
```

**To customize:**
1. Edit `build_scripts/windows/installer.nsi`
2. Update version numbers
3. Modify install directory or shortcuts
4. Rebuild: `makensis installer.nsi`

## Auto-Start Implementation

VoiceType uses the **Windows Startup folder** for auto-start:

### How It Works

**Location:** `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VoiceType.lnk`

**Advantages:**
- ✅ No admin privileges required
- ✅ User-friendly (users can easily disable)
- ✅ Works with Windows Task Manager startup settings
- ✅ No external tools needed

**Installation:**
The NSIS installer automatically creates a shortcut in the user's Startup folder using the `CreateShortCut` command. No separate command is needed.

### Alternative Approaches (Future Consideration)

**Task Scheduler:**
```bash
# More robust, programmatic control
schtasks /create /tn "VoiceType" /tr "C:\Path\voicetype.exe" /sc onlogon
```

**NSSM (Windows Service):**
```bash
# Most professional, requires admin
nssm install VoiceType "C:\Path\voicetype.exe"
```

## Troubleshooting

### PyInstaller Build Issues

**Problem: Missing module errors**
```
ImportError: No module named 'xyz'
```
**Solution:** Add to `hiddenimports` in `voicetype.spec`

**Problem: Large bundle size (>500 MB)**
**Solution:** Check what's included:
```bash
pyinstaller --clean --log-level=DEBUG voicetype.spec
# Review: build/voicetype/warn-voicetype.txt
```

**Problem: Audio not working**
**Solution:** Ensure audio libraries are bundled:
```python
hiddenimports = [
    'sounddevice',
    'soundfile',
    '_soundfile_data',  # Critical
]
```

### NSIS Build Issues

**Problem: NSIS not found**
```
'makensis' is not recognized
```
**Solution:**
- Add NSIS to PATH
- Or install via Chocolatey: `choco install nsis`

**Problem: Files not found during build**
```
File: "..\..\dist\voicetype\*.*" - NO FILES FOUND
```
**Solution:** Run PyInstaller build first

### Runtime Issues

**Problem: Startup shortcut not created**
**Solution:** The NSIS installer creates the shortcut directly. Check if the shortcut exists at:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VoiceType.lnk`

If missing, you can manually create a shortcut to `C:\Program Files\VoiceType\voicetype.exe` in that folder.

**Problem: Hotkey not working**
**Solution:** Check if another app is using the Pause/Break key

**Problem: API key not loading**
**Solution:** Verify `.env` file exists:
```bash
type %APPDATA%\voicetype\.env
```

## Size Optimization

### Current Bundle Sizes

- PyInstaller build: ~200-300 MB (CPU-only)
- NSIS installer: ~150-250 MB (compressed)

### Reduce Size

**1. Exclude unnecessary modules** in `voicetype.spec`:
```python
excludes = [
    'numpy.testing',       # Test utilities
    'PIL',                 # If not using images
    'matplotlib',          # Plotting (not needed)
]
```

**2. Use UPX compression** (already enabled):
```python
upx=True,  # Compresses binaries 50-70%
```

**3. Remove unused assets**:
```python
data = [
    # Only include necessary sounds
    ('voicetype/assets/sounds/start.wav', 'voicetype/assets/sounds'),
    ('voicetype/assets/sounds/error.wav', 'voicetype/assets/sounds'),
]
```

## Distribution Checklist

Before releasing a new version:

- [ ] Update version in `installer.nsi` (VERSIONMAJOR, VERSIONMINOR)
- [ ] Update version in `pyproject.toml`
- [ ] Test build on clean Windows VM
- [ ] Verify installer creates shortcuts
- [ ] Test auto-start after reboot
- [ ] Test both local and litellm providers
- [ ] Check installer size (<300 MB target)
- [ ] Scan with Windows Defender (avoid false positives)
- [ ] Test uninstaller removes all files

## CI/CD Integration (Future)

Example GitHub Actions workflow:

```yaml
# .github/workflows/build-windows.yml
name: Build Windows Installer

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install pyinstaller
          choco install nsis

      - name: Build installer
        run: python build_scripts/build_windows.py --clean

      - name: Upload release asset
        uses: softprops/action-gh-release@v1
        with:
          files: dist/VoiceType-Setup.exe
```

## Advanced: Code Signing (Future)

For production releases, sign the executable and installer:

```bash
# Sign PyInstaller exe
signtool sign /f certificate.pfx /p password dist/voicetype/voicetype.exe

# Sign NSIS installer
signtool sign /f certificate.pfx /p password dist/VoiceType-Setup.exe
```

Benefits:
- ✅ Removes Windows SmartScreen warnings
- ✅ Builds user trust
- ✅ Prevents tampering

## Next Steps

- [ ] Add code signing for production releases
- [ ] Create macOS .app bundle and .dmg installer
- [ ] Add auto-update functionality
- [ ] GPU-enabled build variant (with CUDA)
- [ ] Reduce bundle size with lazy imports
- [ ] Package for Linux (.deb, .rpm, AppImage)

## Resources

- **PyInstaller**: https://pyinstaller.org/en/stable/
- **NSIS**: https://nsis.sourceforge.io/Docs/
- **Windows Startup**: https://learn.microsoft.com/en-us/windows/win32/shell/app-registration
- **Task Scheduler**: https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-start-page
