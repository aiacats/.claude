param(
  [string]$TitlePrefix,          # e.g. "unity_vortex_urp - "
  [string]$Folder,               # folder to watch
  [string]$Filter = "*_setupped.png",
  [int]$TimeoutSec = 240
)
# Keep the Unity main window whose title starts with TitlePrefix in front (the facial capture window and MCP
# only advance on editor updates, which stall when Unity is in the background) until a file matching
# Filter appears in Folder. ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class KeepFront {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
$p = Get-Process -Name Unity | Where-Object { $_.MainWindowTitle.StartsWith($TitlePrefix) } | Select-Object -First 1
if (-not $p) { "unity window not found: $TitlePrefix"; exit 1 }
$sw = [Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
  [KeepFront]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
  $hit = Get-ChildItem -LiteralPath $Folder -Filter $Filter -ErrorAction SilentlyContinue
  if ($hit) { "done after $([int]$sw.Elapsed.TotalSeconds)s"; exit 0 }
  Start-Sleep -Seconds 3
}
"timeout; png count: " + (Get-ChildItem -LiteralPath $Folder -Filter *.png -ErrorAction SilentlyContinue).Count
exit 2
