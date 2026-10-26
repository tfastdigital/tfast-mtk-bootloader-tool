#requires -Version 5.1
<#
.SYNOPSIS
    Create a branded desktop / Start Menu shortcut for TFast MTK Bootloader Tool.

.DESCRIPTION
    Points the shortcut at tfast-gui.bat and attaches assets\tfast.ico so the app
    appears with the TFast Digital icon in the taskbar, Start Menu and on the
    desktop.

    Copyright (c) 2025-2026 TFast Digital Agency. All rights reserved.

.PARAMETER StartMenu
    Also create a Start Menu shortcut (default: on).

.PARAMETER NoDesktop
    Skip the desktop shortcut.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
#>
[CmdletBinding()]
param(
    [switch]$StartMenu = $true,
    [switch]$NoDesktop
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'tfast-gui.bat'
$cliTarget = Join-Path $root 'tfast-cli.bat'
$icon = Join-Path $root 'assets\tfast.ico'

if (-not (Test-Path -LiteralPath $target)) { throw "Launcher not found: $target" }
if (-not (Test-Path -LiteralPath $icon)) { throw "Icon not found: $icon (run tools\make_icon.py first)" }

$shell = New-Object -ComObject WScript.Shell
$name = 'TFast MTK Bootloader Tool.lnk'
$created = @()

function New-Shortcut {
    param([string]$Path, [string]$Target = $target, [string]$Desc = 'TFast MTK Bootloader Tool - MediaTek / Transsion unlock and patch suite')
    $sc = $shell.CreateShortcut($Path)
    $sc.TargetPath = $Target
    $sc.WorkingDirectory = $root
    $sc.IconLocation = "$icon,0"
    $sc.Description = $Desc
    $sc.WindowStyle = 1
    $sc.Save()
}

if (-not $NoDesktop) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop) {
        $p = Join-Path $desktop $name
        New-Shortcut -Path $p
        $created += $p
    }
}

if ($StartMenu) {
    $programs = [Environment]::GetFolderPath('Programs')
    if ($programs) {
        $folder = Join-Path $programs 'TFast Digital'
        if (-not (Test-Path -LiteralPath $folder)) {
            New-Item -ItemType Directory -Path $folder -Force | Out-Null
        }
        $p = Join-Path $folder $name
        New-Shortcut -Path $p
        $created += $p

        if (Test-Path -LiteralPath $cliTarget) {
            $c = Join-Path $folder 'TFast MTK Bootloader Tool (CLI).lnk'
            New-Shortcut -Path $c -Target $cliTarget -Desc 'TFast MTK Bootloader Tool - command line edition'
            $created += $c
        }
    }
}

Write-Host ''
Write-Host '  TFast MTK Bootloader Tool - shortcut(s) created:' -ForegroundColor Cyan
foreach ($p in $created) { Write-Host "    $p" -ForegroundColor Gray }
Write-Host ''
Write-Host '  (c) 2025-2026 TFast Digital Agency. All rights reserved.' -ForegroundColor DarkGray
Write-Host '  https://tfastdigital.com/' -ForegroundColor DarkGray
Write-Host ''
