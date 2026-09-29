# Windows の仮想デスクトップ操作ヘルパー
#
# 背景: 複数プロジェクトを並行して進めると画面が埋まるため、プロジェクトごとに
# 仮想デスクトップを分ける（グローバル CLAUDE.md の恒久ルール）。
#
# Windows には仮想デスクトップの公式 CLI が無く、win-gui MCP の key_press は
# 修飾キーが Ctrl/Shift/Alt のみで Win キーを送れない。そのため keybd_event を
# 直接叩いてショートカットを送る。
#
# 使い方:
#   powershell -NoProfile -File virtual-desktop.ps1 new     新規デスクトップを作成（作成先へ自動で切り替わる）
#   powershell -NoProfile -File virtual-desktop.ps1 left    左のデスクトップへ
#   powershell -NoProfile -File virtual-desktop.ps1 right   右のデスクトップへ
#   powershell -NoProfile -File virtual-desktop.ps1 close   現在のデスクトップを閉じる（ウィンドウは隣へ移る）
#   powershell -NoProfile -File virtual-desktop.ps1 taskview タスクビューを開く
#
# 注意:
# - 新規作成すると「そのデスクトップへ切り替わった状態」になる。
#   この状態でアプリを起動すると、そのデスクトップに配置される。
# - 既に起動しているウィンドウを後から別デスクトップへ移すのは、標準機能では
#   タスクビューでのドラッグが必要で自動化できない。
#   必要なら MScholtes/VirtualDesktop のような CLI の導入を検討する。

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('new', 'left', 'right', 'close', 'taskview')]
    [string]$Action
)

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class VDKeys
{
    [DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    private const uint KEYEVENTF_KEYUP = 0x0002;

    private const byte VK_LWIN    = 0x5B;
    private const byte VK_CONTROL = 0x11;
    private const byte VK_TAB     = 0x09;
    private const byte VK_LEFT    = 0x25;
    private const byte VK_RIGHT   = 0x27;
    private const byte VK_D       = 0x44;
    private const byte VK_F4      = 0x73;

    private static void Tap(byte[] downOrder, byte target)
    {
        foreach (byte k in downOrder) keybd_event(k, 0, 0, UIntPtr.Zero);
        keybd_event(target, 0, 0, UIntPtr.Zero);
        keybd_event(target, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
        for (int i = downOrder.Length - 1; i >= 0; i--)
            keybd_event(downOrder[i], 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
    }

    public static void NewDesktop()   { Tap(new byte[] { VK_LWIN, VK_CONTROL }, VK_D); }
    public static void CloseDesktop() { Tap(new byte[] { VK_LWIN, VK_CONTROL }, VK_F4); }
    public static void Left()         { Tap(new byte[] { VK_LWIN, VK_CONTROL }, VK_LEFT); }
    public static void Right()        { Tap(new byte[] { VK_LWIN, VK_CONTROL }, VK_RIGHT); }
    public static void TaskView()     { Tap(new byte[] { VK_LWIN }, VK_TAB); }
}
'@

switch ($Action) {
    'new'      { [VDKeys]::NewDesktop();   Write-Output '新しい仮想デスクトップを作成し、そこへ切り替えました。' }
    'left'     { [VDKeys]::Left();         Write-Output '左の仮想デスクトップへ切り替えました。' }
    'right'    { [VDKeys]::Right();        Write-Output '右の仮想デスクトップへ切り替えました。' }
    'close'    { [VDKeys]::CloseDesktop(); Write-Output '現在の仮想デスクトップを閉じました（ウィンドウは隣へ移動）。' }
    'taskview' { [VDKeys]::TaskView();     Write-Output 'タスクビューを開きました。' }
}

# 切り替えアニメーションが終わる前に次の操作をすると取りこぼすため、少し待つ。
Start-Sleep -Milliseconds 500
