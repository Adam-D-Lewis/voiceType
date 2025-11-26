# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for VoiceType Windows installer.
Builds a standalone executable bundling Python + all dependencies.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Project root directory
project_root = Path(SPECPATH)

# Collect all jaraco submodules (namespace packages that pkg_resources needs)
jaraco_imports = collect_submodules('jaraco')

# Path to vendored pynput library
vendored_pynput_path = project_root / 'voicetype' / '_vendor' / 'pynput' / 'lib'

# Hidden imports - modules PyInstaller can't auto-detect
hiddenimports = [
    # Core VoiceType modules
    'voicetype',
    'voicetype.__main__',

    # Vendored pynput (from voicetype/_vendor/pynput/lib/pynput)
    'pynput',
    'pynput.keyboard',
    'pynput.keyboard._win32',
    'pynput.mouse',
    'pynput.mouse._win32',
    'pynput._util',
    'pynput._util.win32',

    # Speech recognition
    'faster_whisper',
    'litellm',

    # Audio libraries
    'sounddevice',
    'soundfile',
    '_soundfile_data',

    # UI and system tray
    'pystray',
    'PIL',
    'PIL._imagingtk',
    'PIL._tkinter_finder',

    # Configuration
    'pydantic',
    'pydantic_settings',
    'dotenv',

    # Logging
    'loguru',

    # Platform-specific
    'ctypes',
    'ctypes.wintypes',
    'win32api',
    'win32con',
    'win32gui',
    'win32clipboard',
    'pyperclip',
]

# Excluded modules - reduce bundle size
excludes = [
    # Heavy ML frameworks not needed
    'torch',
    'tensorflow',
    'keras',

    # Development and testing
    'pytest',
    'pytest_cov',
    'coverage',
    'pre_commit',
    'mypy',
    'black',
    'ruff',
    'hypothesis',

    # Build tools
    # NOTE: setuptools/pkg_resources is needed by jaraco namespace packages at runtime
    # 'setuptools',  # Required by jaraco namespace packages
    # 'wheel',  # Required by setuptools vendored imports
    'pip',

    # Documentation
    'sphinx',
    'docutils',

    # Unused standard library
    'tkinter',
    'unittest',
    'xml.etree',
    'pydoc',

    # Jupyter/IPython
    'IPython',
    'jupyter',
    'notebook',
]

# Data files to include
datas = [
    # VoiceType assets (sounds, icons, etc.)
    (str(project_root / 'voicetype' / 'assets'), 'voicetype/assets'),
]

# Add bundled Whisper models if they exist
models_dir = project_root / 'voicetype' / 'models'
if models_dir.exists():
    for model_path in models_dir.iterdir():
        if model_path.is_dir():
            datas.append((str(model_path), f'voicetype/models/{model_path.name}'))

# Binary files (DLLs, shared libraries)
binaries = []

a = Analysis(
    [str(project_root / 'voicetype' / '__main__.py')],
    pathex=[str(project_root), str(vendored_pynput_path)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + jaraco_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='voicetype',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress binaries (50-70% size reduction)
    console=False,  # Enable console for debugging (set to False for release)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: Add icon file path if available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='voicetype',
)
