# claude-code の罠
全件は ~/.claude/traps-catalog/claude-code.md。ここは再発しやすいものだけ。

### claudeLog を .claude 配下に置かない
`.claude/` への書き込みは allow ルールでも hook の permissionDecision:allow でも毎回確認が出る。原因は設定ディレクトリの保護。→ `log/claudeLog.txt` に置き、Bash の `>>` で追記する。（実例: 2026-07-05 RigFlow）

### MCP を登録したのにツールが出ない
`~/.claude/.mcp.json` と settings.json の mcpServers は読まれない（user スコープの実体は `~/.claude.json`）。プロジェクトの `.mcp.json` は `claude mcp list` で Connected でも、`.claude/settings.local.json` の `enabledMcpjsonServers` に名前が無いと公開されない。→ `claude mcp add -s user|project`、enabledMcpjsonServers を足して再起動。deferred なだけなら ToolSearch でロード。（実例: 2026-03-31 ClaudeVideoReader / 2026-04 MocapSimulator、ほか複数）

### 設定と MCP の変更は再起動まで効かない
`.mcp.json`・settings は起動時にしか読まれず、MCP のツール一覧は接続時に取得される。外部アプリ側のアドオンも起動時のモジュールのまま。→ 触ったら Claude Code（と外部アプリ）を再起動。自作 MCP の exe は稼働中ロックされるので終了してから publish。（実例: 2026-04 WinGuiMcp / 2026-09-26 BMCP で新引数が黙って捨てられた）

### セッションから起動した claude が一覧に出ない
親の `CLAUDE_CODE_CHILD_SESSION` 等を継ぎ transcript が保存されない。→ CLAUDECODE / CLAUDE_PID / CLAUDE_CODE_* を外して Start-Process で起動。`--bg --resume` は新 ID になる（再起動は `claude respawn <短縮ID>`）。interactive に `claude stop` は効かない（`taskkill /T /F`）。CLI の挙動は調査でなく実際に叩いて確かめる。（実例: 2026-09-04, 2026-09-13 SessionControl）

### Claude Code のシェルは非対話
`!` や Bash で対話入力を待つコマンドは stdin が空のまま「成功」する（`wrangler secret put` が空文字を登録した）。→ 値はパイプかファイルで渡し、直後に効いたか確かめる。（実例: 2026-07-05 RigFlow / 2026-09-05 SessionControl の rclone config）

### TaskStop 後もポートが塞がっている
TaskStop は npm ラッパーだけ止め、vite 本体がポートを掴んだまま残る。→ `netstat -ano | grep :<port>` で PID を特定し `taskkill /T /F`。（実例: 2026-07-03 Traddist）
