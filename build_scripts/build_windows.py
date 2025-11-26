#!/usr/bin/env python3
"""
Build script for creating VoiceType Windows installer.
Creates a standalone .exe using PyInstaller, then packages it into an .exe installer using NSIS.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "voicetype.spec"
MODELS_DIR = PROJECT_ROOT / "voicetype" / "models"

# Default model to bundle with the installer
DEFAULT_WHISPER_MODEL = "tiny"


def clean_build_artifacts():
    """Remove previous build artifacts."""
    print("🧹 Cleaning previous build artifacts...")
    for dir_path in [DIST_DIR, BUILD_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"   Removed {dir_path}")


def download_whisper_model(model_name: str = DEFAULT_WHISPER_MODEL):
    """Download the Whisper model and save it to the models directory.

    Args:
        model_name: Name of the model to download (e.g., 'tiny', 'base', 'small')
    """
    print(f"📥 Downloading Whisper model '{model_name}'...")

    model_dir = MODELS_DIR / f"faster-whisper-{model_name}"

    # Check if model already exists
    if model_dir.exists() and any(model_dir.iterdir()):
        print(f"   Model already exists at {model_dir}")
        return True

    # Create models directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        # Download the model from Hugging Face
        repo_id = f"Systran/faster-whisper-{model_name}"
        print(f"   Downloading from {repo_id}...")

        snapshot_download(
            repo_id=repo_id,
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
        )

        print(f"✅ Model downloaded to {model_dir}")
        return True

    except ImportError:
        print("❌ huggingface_hub not installed. Install it with: pip install huggingface_hub")
        return False
    except Exception as e:
        print(f"❌ Failed to download model: {e}")
        return False


def build_with_pyinstaller():
    """Build the application using PyInstaller."""
    print("📦 Building with PyInstaller...")

    if not SPEC_FILE.exists():
        print(f"❌ Error: Spec file not found at {SPEC_FILE}")
        sys.exit(1)

    # Use sys.executable to run pyinstaller as a module to ensure we use
    # the correct Python environment (especially important in pixi/conda envs)
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", str(SPEC_FILE)]

    try:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        print("✅ PyInstaller build completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller build failed: {e}")
        return False
    except FileNotFoundError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        return False


def create_windows_installer():
    """Create Windows installer using NSIS."""
    print("🪟 Creating Windows installer...")

    nsis_script = PROJECT_ROOT / "build_scripts" / "windows" / "installer.nsi"

    if not nsis_script.exists():
        print(f"❌ NSIS script not found at {nsis_script}")
        print(f"   Expected location: {nsis_script}")
        return False

    # Check if NSIS is installed
    try:
        result = subprocess.run(
            ["makensis", "-VERSION"], capture_output=True, check=True
        )
        print(f"   Found NSIS: {result.stdout.decode().strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ NSIS not found. Please install NSIS:")
        print("   Option 1: choco install nsis")
        print("   Option 2: Download from https://nsis.sourceforge.io/Download")
        return False

    try:
        subprocess.run(["makensis", str(nsis_script)], check=True, cwd=PROJECT_ROOT)
        print("✅ Windows installer created successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Windows installer creation failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Build VoiceType Windows installer")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts before building",
    )
    parser.add_argument(
        "--no-installer",
        action="store_true",
        help="Skip NSIS installer creation (PyInstaller only)",
    )

    args = parser.parse_args()

    print("🚀 Starting VoiceType Windows build process...\n")

    if args.clean:
        clean_build_artifacts()

    # Step 1: Download the Whisper model
    if not download_whisper_model():
        print("\n❌ Build failed at model download stage")
        sys.exit(1)

    # Step 2: Build with PyInstaller
    if not build_with_pyinstaller():
        print("\n❌ Build failed at PyInstaller stage")
        sys.exit(1)

    if args.no_installer:
        print("\n✅ Build completed (PyInstaller only)")
        print(f"📦 Executable files are in: {DIST_DIR / 'voicetype'}")
        return

    # Step 3: Create Windows installer with NSIS
    if not create_windows_installer():
        print("\n❌ Installer creation failed")
        print("   You can still use the PyInstaller build in: dist/voicetype/")
        sys.exit(1)

    print("\n✅ Build completed successfully!")
    print(f"📦 Installer is in: {DIST_DIR}")
    print("   Look for: VoiceType-Setup.exe")


if __name__ == "__main__":
    main()
