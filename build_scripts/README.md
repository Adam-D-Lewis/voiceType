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

**Output:**
- `dist/voicetype/` - PyInstaller build (executable + dependencies)
- `dist/VoiceType-Setup.exe` - NSIS installer

### windows/installer.nsi

NSIS script for creating the Windows installer.

**Features:**
- Installs to `C:\Program Files\VoiceType\`
- Creates Start Menu shortcuts
- Registers in Add/Remove Programs
- Configures auto-start on login

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
