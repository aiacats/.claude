<#
Windows アプリの GUI 検証で、win-gui(MCP)だけでは届かないところを埋める道具。

    gui.ps1 windows <プロセス名>            … そのプロセスの窓を一覧（タイトル・位置・大きさ）
    gui.ps1 focus   <ハンドル>              … 確実に前面へ出す（入力を受けられる状態にする）
    gui.ps1 pin     <ハンドル> [x y w h]    … 最前面に固定して位置と大きさを決める
    gui.ps1 unpin   <ハンドル>              … 最前面の固定を外す
    gui.ps1 modclick <x> <y> <ctrl|shift|ctrl+shift>  … 修飾キーを押しながらクリック
    gui.ps1 shot    <x> <y> <w> <h> <出力先.png>      … 画面の一部を PNG で保存

ハンドルは 10 進で渡す（win-gui の find_window が返す値をそのまま使える）。
#>
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$signature = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint f, IntPtr e);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
'@
$U = Add-Type -MemberDefinition $signature -Name U -Namespace GuiKit -PassThru

function Get-Handle([string]$text) { [IntPtr][int64]$text }

switch ($Command) {
    'windows' {
        # 同じ名前の窓が複数あると取り違える。PID とタイトルの両方で選ぶこと。
        Get-Process -Name $Rest[0] -ErrorAction Stop |
            Select-Object Id, MainWindowTitle, @{n = 'Handle'; e = { [int64]$_.MainWindowHandle } } |
            Format-Table -AutoSize | Out-String -Width 120
    }
    'focus' {
        # SetForegroundWindow は「今の前面ウィンドウのスレッド」に結び付けないと
        # Windows に無視される。無視されると、クリックもキー入力も別のアプリへ行く。
        # ただし**前面のアプリが応答していないときは結び付けない**。入力キューを
        # 繋いだ相手がメッセージを回さないと、こちらの SetForegroundWindow が
        # その場で止まり、呼び出しごと返らなくなる（Unity のモーダル進捗ダイアログで実際に踏んだ）。
        $h = Get-Handle $Rest[0]
        $fg = $U::GetForegroundWindow()
        $tMe = $U::GetCurrentThreadId()
        $attach = ($fg -ne [IntPtr]::Zero) -and ($fg -ne $h) -and (-not $U::IsHungAppWindow($fg))
        if ($attach) {
            $tFg = $U::GetWindowThreadProcessId($fg, [IntPtr]::Zero)
            $U::AttachThreadInput($tMe, $tFg, $true) | Out-Null
        }
        $U::ShowWindow($h, 5) | Out-Null      # SW_SHOW
        $U::BringWindowToTop($h) | Out-Null
        $U::SetForegroundWindow($h) | Out-Null
        if ($attach) { $U::AttachThreadInput($tMe, $tFg, $false) | Out-Null }
        Start-Sleep -Milliseconds 300
        $now = $U::GetForegroundWindow()
        "foreground=$now want=$h" + $(if ($now -eq $h) { "" } else { "  ← 失敗。もう一度呼ぶか、対象が最小化されていないか見る" })
    }
    'pin' {
        # 最前面に固定する。他のウィンドウに隠れてクリックを吸われるのを防ぐ。
        # 位置と大きさを固定すると、キャプチャ座標 → 画面座標の換算が毎回同じになる。
        $h = Get-Handle $Rest[0]
        $x = if ($Rest.Count -ge 5) { [int]$Rest[1] } else { 40 }
        $y = if ($Rest.Count -ge 5) { [int]$Rest[2] } else { 40 }
        $w = if ($Rest.Count -ge 5) { [int]$Rest[3] } else { 1456 }
        $t = if ($Rest.Count -ge 5) { [int]$Rest[4] } else { 939 }
        $U::SetWindowPos($h, [IntPtr](-1), $x, $y, $w, $t, 0x0040) | Out-Null   # HWND_TOPMOST
        "pinned $h at $x,$y ($w x $t)"
    }
    'unpin' {
        $h = Get-Handle $Rest[0]
        $U::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null  # HWND_NOTOPMOST
        "unpinned $h"
    }
    'modclick' {
        # win-gui の click は修飾キーを押しながらのクリックを送れない。
        # 複数選択(Ctrl)・範囲選択(Shift)の検証はこれを使う。
        $x = [int]$Rest[0]; $y = [int]$Rest[1]
        $mod = if ($Rest.Count -ge 3) { $Rest[2] } else { "" }
        $VK_CONTROL = 0x11; $VK_SHIFT = 0x10; $KEYUP = 0x0002
        $U::SetCursorPos($x, $y) | Out-Null
        Start-Sleep -Milliseconds 120
        if ($mod -match 'ctrl') { $U::keybd_event($VK_CONTROL, 0, 0, [IntPtr]::Zero) }
        if ($mod -match 'shift') { $U::keybd_event($VK_SHIFT, 0, 0, [IntPtr]::Zero) }
        Start-Sleep -Milliseconds 60
        $U::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)   # LEFTDOWN
        Start-Sleep -Milliseconds 40
        $U::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)   # LEFTUP
        Start-Sleep -Milliseconds 60
        if ($mod -match 'shift') { $U::keybd_event($VK_SHIFT, 0, $KEYUP, [IntPtr]::Zero) }
        if ($mod -match 'ctrl') { $U::keybd_event($VK_CONTROL, 0, $KEYUP, [IntPtr]::Zero) }
        "clicked $x,$y mod=$mod"
    }
    'shot' {
        # 画面の一部を PNG で保存する。win-gui の screenshot は画像を返すだけで
        # ファイルを残さないので、ユーザーへ送る・後で見比べるときはこちら。
        Add-Type -AssemblyName System.Drawing
        $x = [int]$Rest[0]; $y = [int]$Rest[1]; $w = [int]$Rest[2]; $t = [int]$Rest[3]
        $out = $Rest[4]
        $bmp = New-Object System.Drawing.Bitmap($w, $t)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size($w, $t)))
        $g.Dispose()
        $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        "saved $out"
    }
    default { "使い方は SKILL.md を見る（windows / focus / pin / unpin / modclick / shot）" }
}
