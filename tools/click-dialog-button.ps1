param([Int64]$Dialog, [string]$Button)
# Find a child button of a Win32 dialog by its text and send BM_CLICK (no screen coordinates, so no other window gets the click).
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class DlgClick {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
    public static List<string> Children(IntPtr p) {
        var list = new List<string>();
        EnumChildWindows(p, (h, l) => {
            var t = new StringBuilder(256); GetWindowText(h, t, 256);
            var c = new StringBuilder(256); GetClassName(h, c, 256);
            list.Add(h.ToInt64() + "|" + c + "|" + t);
            return true;
        }, IntPtr.Zero);
        return list;
    }
}
"@
$kids = [DlgClick]::Children([IntPtr]$Dialog)
$kids | ForEach-Object { Write-Output $_ }
$hit = $kids | Where-Object { (($_ -split '\|')[2] -replace '&','') -eq $Button } | Select-Object -First 1
if (-not $hit) { Write-Output "button not found: $Button"; exit 1 }
$h = [IntPtr][Int64](($hit -split '\|')[0])
[DlgClick]::SendMessage($h, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
Write-Output "clicked $Button"
