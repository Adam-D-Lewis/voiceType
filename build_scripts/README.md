# Build Scripts

Scripts for creating VoiceType distribution packages.

## Quick Start

### Build Windows Installer (Recommended)

Using pixi (all dependencies handled automatically):

```bash
pixi run -e windows-build build-windows
```

This creates `dist/VoiceType-Setup.exe` ready for distribution.

### Alternative: Manual Setup

If not using pixi, install dependencies manually:

```bash
pip install pyinstaller huggingface_hub
# Install NSIS: https://nsis.sourceforge.io/Download or `choco install nsis`
python build_scripts/build_windows.py --clean
```

## Scripts

### build_windows.py

Builds Windows installer using PyInstaller + NSIS.

**Build steps:**
1. Downloads the Whisper `tiny` model (~75MB) from Hugging Face
2. Bundles the model with the application via PyInstaller
3. Creates the NSIS installer

**Usage:**
```bash
# Using pixi (recommended)
pixi run -e windows-build build-windows

# Or directly with Python
python build_scripts/build_windows.py --clean

# PyInstaller only (skip NSIS installer)
python build_scripts/build_windows.py --no-installer
```

**Output:**
- `voicetype/models/` - Downloaded Whisper model (git-ignored)
- `dist/voicetype/` - PyInstaller build (executable + dependencies + model)
- `dist/VoiceType-Setup.exe` - NSIS installer

### windows/installer.nsi

NSIS script for creating the Windows installer.

**Features:**
- Installs to `C:\Program Files\VoiceType\`
- Creates Start Menu shortcuts
- Registers in Add/Remove Programs
- Configures auto-start on login
- Launches VoiceType immediately after install
- Bundles Whisper model (no download required on first use)

**Build manually:**
```bash
makensis build_scripts/windows/installer.nsi
```

## Directory Structure

```
build_scripts/
├── README.md              # This file
├── build_windows.py       # Main build script
└── windows/
    └── installer.nsi      # NSIS installer script
```

## See Also

- [Complete build documentation](../docs/BUILDING.md)
- [Packaging summary](../docs/PACKAGING_SUMMARY.md)
- [PyInstaller spec file](../voicetype.spec)
