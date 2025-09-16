#!/usr/bin/env python
"""
Build script for creating Windows executable with PyInstaller.
Alternative to the .bat file - can be run with: python build_windows.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_build_dirs():
    """Remove previous build artifacts."""
    print("Cleaning previous builds...")
    dirs_to_remove = ['build', 'dist', '__pycache__']
    files_to_remove = ['VoiceType.exe', '*.spec.bak']

    for dir_name in dirs_to_remove:
        if Path(dir_name).exists():
            shutil.rmtree(dir_name, ignore_errors=True)
            print(f"  Removed {dir_name}/")

    for pattern in files_to_remove:
        for file in Path('.').glob(pattern):
            file.unlink()
            print(f"  Removed {file}")

def install_pyinstaller():
    """Install or upgrade PyInstaller."""
    print("\nInstalling/upgrading PyInstaller...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pyinstaller'], check=True)

def build_exe():
    """Build the executable with PyInstaller."""
    print("\nBuilding executable...")

    # First, let's check if we need to use the spec file or create it
    spec_file = Path('voicetype.spec')

    if spec_file.exists():
        # Use existing spec file
        print("Using existing voicetype.spec file...")
        result = subprocess.run(['pyinstaller', 'voicetype.spec'], capture_output=True, text=True)
    else:
        # Build with command line options
        print("Building with PyInstaller options...")
        cmd = [
            'pyinstaller',
            '--onefile',           # Single exe file
            '--windowed',          # No console window
            '--name=VoiceType',    # Output name
            '--clean',             # Clean cache
            '--noupx',             # Don't use UPX (can cause antivirus false positives)
            'voicetype/__main__.py'
        ]

        # Add icon if it exists
        icon_file = Path('voicetype.ico')
        if icon_file.exists():
            cmd.extend(['--icon', str(icon_file)])

        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("Build failed!")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False

    return True

def copy_to_root():
    """Copy the built exe to project root."""
    exe_path = Path('dist/VoiceType.exe')
    if exe_path.exists():
        print(f"\nCopying {exe_path} to project root...")
        shutil.copy2(exe_path, '.')
        print(f"Executable available at: ./VoiceType.exe")
        return True
    return False

def main():
    """Main build process."""
    print("="*50)
    print("Building VoiceType for Windows")
    print("="*50)

    try:
        # Change to project root directory
        os.chdir(Path(__file__).parent)

        # Clean previous builds
        clean_build_dirs()

        # Install PyInstaller
        install_pyinstaller()

        # Build the exe
        if not build_exe():
            print("\nBuild failed! Check the errors above.")
            sys.exit(1)

        # Copy to root
        if copy_to_root():
            print("\n" + "="*50)
            print("Build successful!")
            print("="*50)
            print("\nYou can now run VoiceType.exe")
            print("\nTo add to Windows startup:")
            print("1. Press Win+R, type: shell:startup")
            print("2. Copy VoiceType.exe to the opened folder")
        else:
            print("\nWarning: Build may have succeeded but exe not found in expected location.")
            print("Check the dist/ folder manually.")

    except Exception as e:
        print(f"\nError during build: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()