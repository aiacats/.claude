# タスクバーの「自動的に隠す」を切り替える（SHAppBarMessage ABM_SETSTATE）。エクスプローラーの再起動は不要。
# 使い方: taskbar_autohide.ps1 on|off|get
param([ValidateSet('on', 'off', 'get')][string]$Mode = 'get')
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AppBar {
  [StructLayout(LayoutKind.Sequential)]
  public struct APPBARDATA { public int cbSize; public IntPtr hWnd; public uint uCallbackMessage; public uint uEdge; public RECT rc; public IntPtr lParam; }
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int L, T, R, B; }
  [DllImport("shell32.dll")] public static extern IntPtr SHAppBarMessage(uint msg, ref APPBARDATA data);
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string name);
  const uint ABM_GETSTATE = 4, ABM_SETSTATE = 10;
  public const int ABS_AUTOHIDE = 1, ABS_ALWAYSONTOP = 2;
  public static int Get() {
    var d = new APPBARDATA(); d.cbSize = Marshal.SizeOf(d);
    return (int)SHAppBarMessage(ABM_GETSTATE, ref d);
  }
  public static void Set(int state) {
    var d = new APPBARDATA(); d.cbSize = Marshal.SizeOf(d);
    d.hWnd = FindWindow("Shell_TrayWnd", null);
    d.lParam = (IntPtr)state;
    SHAppBarMessage(ABM_SETSTATE, ref d);
  }
}
"@
switch ($Mode) {
  'on'  { [AppBar]::Set([AppBar]::ABS_AUTOHIDE) }
  'off' { [AppBar]::Set([AppBar]::ABS_ALWAYSONTOP) }
}
"autohide={0}" -f (([AppBar]::Get() -band [AppBar]::ABS_AUTOHIDE) -ne 0)
