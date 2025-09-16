@echo off
echo Building VoiceType for Windows...
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist VoiceType.exe del /f VoiceType.exe

REM Install/upgrade PyInstaller if needed
echo Installing/upgrading PyInstaller...
pip install --upgrade pyinstaller

REM Build the exe
echo Building executable...
pyinstaller voicetype.spec

REM Check if build was successful
if exist dist\VoiceType.exe (
    echo.
    echo Build successful!
    echo Executable created at: dist\VoiceType.exe

    REM Optionally copy to root directory
    copy dist\VoiceType.exe .
    echo Copied to: VoiceType.exe
) else (
    echo.
    echo Build failed! Check the error messages above.
    exit /b 1
)

echo.
echo Done!
pause