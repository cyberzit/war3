Unicode true
SetCompressor /SOLID lzma

!define PRODUCT_NAME "MongolRanger"
!define PRODUCT_VERSION "4.8.0.0"
!define PRODUCT_PUBLISHER "MongolRanger Platform"

Name "${PRODUCT_NAME} v4.8"
OutFile "MongolRanger_4.8_x64-setup.exe"
InstallDir "$LOCALAPPDATA\MongolRanger"
RequestExecutionLevel highest
SilentInstall silent
CRCCheck on
XPStyle on

VIProductVersion "4.8.0.0"
VIAddVersionKey "ProductName" "MongolRanger"
VIAddVersionKey "CompanyName" "MongolRanger Platform"
VIAddVersionKey "FileDescription" "MongolRanger Official Installer (Windows 7/8/10/11)"
VIAddVersionKey "FileVersion" "4.8.0.0"
VIAddVersionKey "ProductVersion" "4.8.0.0"
VIAddVersionKey "LegalCopyright" "MongolRanger"

Section "Install"
  ; 1. Automatically repair .NET Framework InstallRoot, Policy & TLS 1.2 StrongCrypto registry keys (32-bit WOW64 & 64-bit native)
  SetRegView 32
  WriteRegStr HKLM "Software\Microsoft\.NETFramework" "InstallRoot" "$WINDIR\Microsoft.NET\Framework\"
  WriteRegStr HKLM "Software\Microsoft\.NETFramework\Policy\v4.0" "30319" "30319-30319"
  WriteRegStr HKLM "Software\Microsoft\.NETFramework\Policy\Upgrades" "4.0.30319" "4.0.0-4.0.30319"
  WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\Policy\standards\Standard CLI 2005" "v4.0.30319" 0x00000fff
  WriteRegStr HKLM "Software\Microsoft\.NETFramework\v4.0.30319\SKUs\.NETFramework,Version=v4.0" "" ""
  WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v4.0.30319" "SchUseStrongCrypto" 0x00000001
  WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v4.0.30319" "SystemDefaultTlsVersions" 0x00000001
  WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v2.0.50727" "SchUseStrongCrypto" 0x00000001
  WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v2.0.50727" "SystemDefaultTlsVersions" 0x00000001

  IfFileExists "$WINDIR\Microsoft.NET\Framework64\*.*" 0 +11
    SetRegView 64
    WriteRegStr HKLM "Software\Microsoft\.NETFramework" "InstallRoot" "$WINDIR\Microsoft.NET\Framework64\"
    WriteRegStr HKLM "Software\Microsoft\.NETFramework\Policy\v4.0" "30319" "30319-30319"
    WriteRegStr HKLM "Software\Microsoft\.NETFramework\Policy\Upgrades" "4.0.30319" "4.0.0-4.0.30319"
    WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\Policy\standards\Standard CLI 2005" "v4.0.30319" 0x00000fff
    WriteRegStr HKLM "Software\Microsoft\.NETFramework\v4.0.30319\SKUs\.NETFramework,Version=v4.0" "" ""
    WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v4.0.30319" "SchUseStrongCrypto" 0x00000001
    WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v4.0.30319" "SystemDefaultTlsVersions" 0x00000001
    WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v2.0.50727" "SchUseStrongCrypto" 0x00000001
    WriteRegDWORD HKLM "Software\Microsoft\.NETFramework\v2.0.50727" "SystemDefaultTlsVersions" 0x00000001
  SetRegView 32
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.1\Client" "DisabledByDefault" 0x00000000
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.1\Client" "Enabled" 0x00000001
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Client" "DisabledByDefault" 0x00000000
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Client" "Enabled" 0x00000001

  ; 2. Install AnyCPU MongolRanger.exe and config
  nsExec::Exec 'taskkill /F /IM MongolRanger.exe'
  Sleep 250
  SetOutPath "$INSTDIR"
  File "/oname=MongolRanger.exe" "MongolRanger-Setup.exe"
  File "MongolRanger.exe.config"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\MongolRanger.lnk" "$INSTDIR\MongolRanger.exe" "" "$INSTDIR\MongolRanger.exe" 0
  CreateDirectory "$SMPROGRAMS\MongolRanger"
  CreateShortCut "$SMPROGRAMS\MongolRanger\MongolRanger.lnk" "$INSTDIR\MongolRanger.exe" "" "$INSTDIR\MongolRanger.exe" 0
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger" "DisplayName" "MongolRanger"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger" "DisplayIcon" "$INSTDIR\MongolRanger.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger" "Publisher" "MongolRanger Platform"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger" "DisplayVersion" "4.8.0"
  Exec '"$INSTDIR\MongolRanger.exe"'
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM MongolRanger.exe'
  Delete "$DESKTOP\MongolRanger.lnk"
  Delete "$SMPROGRAMS\MongolRanger\MongolRanger.lnk"
  RMDir "$SMPROGRAMS\MongolRanger"
  Delete "$INSTDIR\MongolRanger.exe"
  Delete "$INSTDIR\MongolRanger.exe.config"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MongolRanger"
SectionEnd
