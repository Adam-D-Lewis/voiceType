# Build Scripts

Scripts for creating VoiceType distribution packages.

## Quick Start

### Build Windows Installer

```bash
python build_scripts/build_windows.py --clean
```

This creates `dist/VoiceType-Setup.exe` ready for distribution.

## Scripts

### build_windows.py

Builds Windows installer using PyInstaller + NSIS.

**Build steps:**
1. Downloads the Whisper `tiny` model (~75MB) from Hugging Face
2. Bundles the model with the application via PyInstaller
3. Creates the NSIS installer

**Usage:**
```bash
# Clean build (recommended)
python build_scripts/build_windows.py --clean

# Build without cleaning previous artifacts
python build_scripts/build_windows.py

# PyInstaller only (skip NSIS installer)
python build_scripts/build_windows.py --no-installer
```

**Requirements:**
- Python 3.11+
- PyInstaller: `pip install pyinstaller`
- NSIS: https://nsis.sourceforge.io/Download
- huggingface_hub: `pip install huggingface_hub` (for model download)

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
