; VoiceType Windows Installer Script
; Uses NSIS (Nullsoft Scriptable Install System)
; Builds: VoiceType-Setup.exe

; Build with: makensis installer.nsi

!define APPNAME "VoiceType"
!define COMPANYNAME "VoiceType"
!define DESCRIPTION "Type with your voice using hotkey-activated speech recognition"
!define VERSIONMAJOR 0
!define VERSIONMINOR 1
!define VERSIONBUILD 0
!define HELPURL "https://github.com/Adam-D-Lewis/voicetype"
!define UPDATEURL "https://github.com/Adam-D-Lewis/voicetype/releases"
!define ABOUTURL "https://github.com/Adam-D-Lewis/voicetype"

; Installation directory
InstallDir "$PROGRAMFILES64\${APPNAME}"

; Request application privileges for Windows Vista+
RequestExecutionLevel admin

; Name of the installer
Name "${APPNAME}"
OutFile "..\..\dist\VoiceType-Setup.exe"

; Icon for the installer (if you have one)
; Icon "..\..\voicetype\assets\imgs\icon.ico"

; Modern UI
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; MUI Settings
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"

; Installer sections
Section "Install"
    SetOutPath "$INSTDIR"

    ; Copy all files from PyInstaller build
    File /r "..\..\dist\voicetype\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Create start menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\voicetype.exe"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Registry information for Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$\"$INSTDIR$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$\"$INSTDIR\voicetype.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1

    ; Get install size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" "$0"

    ; Configure VoiceType to start on login (create shortcut in user's Startup folder)
    DetailPrint "Configuring VoiceType to start on login..."
    SetShellVarContext current  ; Switch to current user context for Startup folder
    CreateShortCut "$SMSTARTUP\${APPNAME}.lnk" "$INSTDIR\voicetype.exe" "" "$INSTDIR\voicetype.exe" 0
    SetShellVarContext all  ; Switch back to all users context

    ; Launch VoiceType now (don't wait for it to exit)
    DetailPrint "Starting VoiceType..."
    Exec '"$INSTDIR\voicetype.exe"'

    ; Show completion message
    MessageBox MB_OK "${APPNAME} has been installed successfully!$\n$\nVoiceType is now running in the system tray.$\n$\nIt will start automatically when you log in."

SectionEnd

; Uninstaller section
Section "Uninstall"
    ; Remove from startup (current user's Startup folder)
    DetailPrint "Removing VoiceType from startup..."
    SetShellVarContext current
    Delete "$SMSTARTUP\${APPNAME}.lnk"
    SetShellVarContext all

    ; Remove files
    RMDir /r "$INSTDIR"

    ; Remove start menu shortcuts
    RMDir /r "$SMPROGRAMS\${APPNAME}"

    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"

    MessageBox MB_OK "${APPNAME} has been uninstalled."

SectionEnd
