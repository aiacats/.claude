# mcp-external の罠
全件は ~/.claude/traps-catalog/mcp-external.md。ここは再発しやすいものだけ。win-gui の基本（ハンドルで指す・pin+focus・座標換算・日本語 OCR）は skill windows-gui-testing。

### MCP は正常応答でも別プロジェクトに繋がっている
先着の別プロジェクトが固定ポートを持つ、またはドメインリロード・再起動でポートが移り空きを別の Unity が取る。→ 状態を変える前に接続先を確かめる（ウィンドウタイトル、Unity は `Library/ClaudeCodeMCP/endpoint.json` の processId）。`.mcp.json` に `MCP_UNITY_HTTP_URL` を書かない（自動解決より優先され取り違えの元）。（実例: 2026-08-27 Unity_ArtNetRecorder / 2026-09-06 lll-12 / 2026-09-23 vortex_urp / 2026-09-24 Ext_TokinoSora_2026-pia）

### MCP が全部タイムアウトしたらモーダルを疑う
ファイル選択・保存確認・更新案内・開いたままのプルダウンがメインスレッドを止め、全ツールが timeout か None になる。HTTP は 200 を返すので死活監視では分からない。→ 全画面 `screenshot` でダイアログを探して閉じる（`capture_window` は対象窓しか写らない）。（実例: 2026-06-01 LiveMultiRecorder / 2026-09-23 DvcMCP / 2026-09-24 SinkaiFes2026）

### capture_window では前面かどうか分からない
PrintWindow なので隠れていても正常に撮れるが、座標クリックと入力は前面の別アプリ（他セッションの AE・Unity・Fork、オーバーレイ）へ落ちる。focus_window は foreground lock で効かないことがある。→ 操作前に全画面 `screenshot` で前面を確かめる。前面にできなければ PostMessage で HWND へ直接送るか「未検証」と報告。（実例: 2026-09-02/13/23 Sequence / 2026-09-17 MotionForge / 2026-09-23 SinkaiFes2026 / 2026-09-24 ModelChecker）

### Chrome は capture_window で真っ黒
PrintWindow は GPU 合成を拾えない。SSE を張るページは headless `--screenshot` も戻らない。→ playwright か、`--remote-debugging-port` で CDP の Page.captureScreenshot（SessionControl の `scripts/uiprobe.mjs`）。（実例: 2026-09-05 SessionControl / 2026-09 MemoryObserver）

### 別の仮想デスクトップの窓は扱えない
win-gui は別デスクトップの窓を撮れず操作もできない。key_press は Win キーを送れない。→ `~/.claude/tools/virtual-desktop.ps1` で対象のデスクトップへ切り替えてから触り、どこにいるかを報告に書く。（出典: CLAUDE.md 2026-09-23）
