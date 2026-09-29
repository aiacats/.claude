---
paths:
  - "**/*.{csproj,sln,xaml}"
---

# dotnet の罠

全件は ~/.claude/traps-catalog/dotnet.md。ここは再発しやすいものだけ。

### 起動中の exe がビルドを止める
`dotnet build` / `publish` / `test` が MSB3027 で失敗し、リトライで時間を溶かす。原因は前回起動したアプリや MCP プロセスが exe を掴んでいること。→ ビルド前に `taskkill /F /T /IM <App>.exe`。MCP は別フォルダへ publish して差し替える。（実例: 2026-04 MocapSimulator / 2026-04 WinGuiMcp）

### dotnet test では App の exe が更新されない
直したはずの GUI が古いまま、存在しない不具合を追う。原因はテストが Core しか参照せず App を再ビルドしないこと、変異チェックで修正を外した回の bin が残ること。→ GUI 検証の前に `dotnet build <sln>` を挟み、exe の更新時刻を確かめる。（実例: 2026-06-10 Handive / 2026-09-17 MotionForge）

### stdio MCP では Hosting の既定ログが stdout を汚す
MCP サーバーが応答不能・プロトコルエラー。原因は Microsoft.Extensions.Hosting のコンソールログが stdout に出ること。→ `LogToStandardErrorThreshold = LogLevel.Trace` で全ログを stderr へ。（実例: 2026-04 WinGuiMcp）

### ImGui の Text や SetTooltip は printf 書式
「100%」が化け、`%n` でプロセスが落ちる。原因は渡した文字列が fmt として解釈されること。→ TextUnformatted のラッパに統一し、直接呼び出しを禁じるテストを置く。（実例: 2026-09-17 MotionForge）

### System.Text.Json は Vector3 を {} と書く
保存して読み戻すと値がゼロになる（例外なし）。原因は X/Y/Z がフィールドなこと。→ 専用 JsonConverter を書き、往復テストは 1 プロパティずつ動かす。（実例: 2026-08-24 MotionForge）

### ソケットの Dispose でプロセスが落ちる
停止・終了のたびにクラッシュする。原因は Poll 中のバックグラウンドスレッドに WSAEINTR が上がり、未処理例外でプロセスが終わること。→ Interrupted / OperationAborted / ObjectDisposed 等を正常終了扱いにし、スレッド本体を try/catch で包む。（実例: 2026-08-24 MotionForge）

### Avalonia の派生コントロールは不可視になる
TreeView 派生が何も描かず、イベントも来ない。原因は既定テンプレートが型一致でしか当たらないこと。→ `protected override Type StyleKeyOverride => typeof(TreeView);`（実例: 2026-04 MocapSimulator）
