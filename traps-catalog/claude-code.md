# claude-code の罠（カタログ）
Claude Code 本体（hooks・settings・permissions・MCP の登録/有効化・CLI 起動・Remote Control・worktree・transcript・サブエージェント）と、自作 MCP サーバー側の罠の全件。厳選版は ~/.claude/rules/traps/claude-code.md。

## 設定・権限

### `.claude/` 配下への書き込みは毎回確認が出る（claudeLog の置き場）
- 症状: `.claude/claudeLog.txt` への追記のたびに許可プロンプトが出る。
- 原因: 設定ディレクトリの保護。`Edit(**/...)` の allow も hook の `permissionDecision:allow` も外せない。Edit/Write でも Bash でも同じ。
- 対策: claudeLog は `log/claudeLog.txt` に置き、Bash の `>>` で追記する。既存の `.claude/claudeLog.txt` は `log/` へ移す（追跡中なら `git mv`）。
- 実例: 2026-07-05 RigFlow
- 自動検出: 候補 `claudelog-under-dotclaude`（patterns-claude.md）
- 出典: CLAUDE.md:109-111 / RigFlow/log/claudeLog.txt:847-860 / D---Personal-Project-RigFlow/memory/claudelog-auto-approve.md:12

### settings.json の許可 glob `**` がドット始まりディレクトリを跨がない
- 症状: `Edit(**/claudeLog.txt)` を許可しても `.claude/claudeLog.txt` の編集で毎回プロンプト。`**/.claude/...` に直しても出続けた。
- 原因: picomatch の `**` は既定でドットディレクトリを跨がない。Claude Code 実体の照合（バックスラッシュのパス）は picomatch の実測とも一致しなかった。
- 対策: 置き場所を `log/` へ移す（採用済み）か、区切り文字非依存の PreToolUse フックで許可する。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:847-860

### セッションによって PowerShell が拒否される
- 症状: PowerShell 実行が拒否され、virtual-desktop.ps1 も走らず、GUI 確認は win-gui だけになった。
- 原因: そのセッションの権限設定（詳細はログに無し）。
- 対策: セッション冒頭で PowerShell が使えるか確かめ、使えなければ報告に明記する。
- 実例: 2026-09-23 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2852, 2860

## MCP の登録・有効化

### `~/.claude/.mcp.json` や settings.json の mcpServers に書いても MCP は登録されない
- 症状: 手書きで登録した MCP のツールがセッションに出ない。
- 原因: user スコープの実体は `C:\Users\komao\.claude.json`（`.claude/` フォルダの中ではない）。settings.json に mcpServers フィールドは無い。`.mcp.json` はプロジェクトルート専用の別形式。
- 対策: `claude mcp add -s user <name> -- <cmd>`（プロジェクト限定は `-s project`）→ `claude mcp list` で確認 → Claude Code 再起動。
- 実例: 2026-03-31 ClaudeVideoReader / 2026-04-12 MocapSimulator・WinGuiMcp
- 自動検出: 候補 `mcp-json-in-dotclaude` / `settings-mcpservers`（patterns-claude.md）
- 出典: ClaudeVideoReader:13-14 / MocapSimulator:326-329 / MEM(MocapSimulator)/feedback_mcp_registration.md:9 / MS/.claude/claudeLog.txt:352

### `.mcp.json` があり Connected なのにツールが公開されない（enabledMcpjsonServers 漏れ）
- 症状: `claude mcp list` で「Connected」なのに、セッションで MCP ツールが見当たらない・呼べない。
- 原因: プロジェクトスコープの MCP はユーザーの明示承認が要る。`.claude/settings.local.json` のトップレベルに `"enabledMcpjsonServers": ["<名前>"]` が無いと公開されない。別に、deferred tools（スキーマ未ロード）の状態で出るのは仕様。
- 対策: 未設定なら追記して Claude Code を再起動。deferred なら `ToolSearch` の `select:<tool>` でロードしてから使う。切り分けは `claude mcp list` → （HTTP 型なら）`netstat -ano | grep :<port>` → enabledMcpjsonServers の順。
- 実例: 複数プロジェクトで再発（日付の記録なし。CLAUDE.md に「過去に複数プロジェクトで同じ詰まり方を再発」）
- 自動検出: 不可
- 出典: CLAUDE.md:467-486

### `.mcp.json`・settings・自作 MCP の更新は起動時にしか読まれない
- 症状: 設定を変えても効かない。新しいツールが見えない。BMCP では更新後も新しい引数が黙って捨てられ、10KB の FBX で上書きされた。
- 原因: `.mcp.json` と settings は Claude Code の起動時にしか読まれない。MCP クライアントは接続時にツール一覧を取得する。外部アプリ側（Blender）も起動時に読んだモジュールを使い続ける。
- 対策: 触ったら Claude Code を再起動する（`--remote-control` 付き）。外部アプリ側のアドオンを更新したらアプリも再起動。書き出し後はバイト数とオブジェクト数を見る。
- 実例: 2026-04 WinGuiMcp / 2026-09-26 BMCP
- 自動検出: 不可
- 出典: CLAUDE.md:310-312, 626-631 / skills/blender-stage/SKILL.md:52-58 / BMCP/log/claudeLog.txt:286-296, 352

### 稼働中の自作 MCP の exe は上書きできない
- 症状: publish / build が MSB3027（ファイルロック）で失敗。
- 原因: MCP クライアント（Claude Code）やテスト中のアプリが exe を掴んでいる。
- 対策: Claude Code を終了してから publish 先を上書きする（WinGui MCP）。または別フォルダへ publish してから入れ替える。アプリは先にプロセスを止めてから build。
- 実例: 2026-04-12 WinGuiMcp / MocapSimulator
- 自動検出: 不可（`dotnet build|publish` は正常な用途が大半）
- 出典: CLAUDE.md:626-631 / MS/.claude/claudeLog.txt:357, 388 / MEM(MocapSimulator)/feedback_kill_before_build.md

### winget で入れた uv が MCP から見えず -32000
- 症状: `/mcp` で MCP サーバーが `-32000` で接続失敗。
- 原因: PATH 更新は新規プロセスにしか反映されない。Claude Code を再起動しても、親（エクスプローラ等）が旧 PATH なら子の MCP も uv/uvx を解決できない。
- 対策: `.mcp.json` の `command` を絶対パスで書く（例: `C:/Users/<u>/AppData/Local/Microsoft/WinGet/Links/uv.exe`）。
- 実例: 2026-06 totolive_202511
- 自動検出: 不可（`"command": "uvx"` は PATH が正しければ動くため誤検知が多い）
- 出典: totolive_202511/.claude/claudeLog.txt:136-156

## CLI 起動・Remote Control・セッション管理

### Claude セッション内から起動した claude は transcript を保存しない（CLAUDE_CODE_CHILD_SESSION）
- 症状: 起動したのに一覧に出ない・`--resume` できない。画面に「Transcript saving is off - inherited CLAUDE_CODE_CHILD_SESSION marker」と出るだけ。
- 原因: Claude セッションで動かしたデーモン（npm run dev 等）が親セッションの環境変数を子へ引き継ぐ。
- 対策: 起動時に CLAUDECODE / CLAUDE_PID / CLAUDE_EFFORT / CLAUDE_JOB_DIR / CLAUDE_CODE_{CHILD_SESSION,SESSION_ID,SESSION_ATTENDED,ENTRYPOINT,EXECPATH,MESSAGING_SOCKET,MESSAGING_TOKEN,BRIDGE_SESSION_ID,ALT_SCREEN_FULL_REPAINT} を外す（CLAUDE_CONFIG_DIR 等の利用者設定は残す）。端末は PowerShell の Start-Process で開く。
- 実例: 2026-09-13 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:78 / Notion 3dae4d4b-751b-8130-b478-c12360da4b20

### claude CLI の実測仕様（--bg・--resume・stop・respawn）
- 症状: ID が合わない。`claude stop` が "No job matching"。終了した interactive が `claude agents --all` から消える。
- 原因: CLI の実装（claude 2.1.270 で実測）。`--bg` は `--session-id` を無視して独自採番（標準出力の `backgrounded · <8桁hex>` から短縮 ID を読み、`claude agents --json` で実 sessionId を引く）。`--bg --resume <id>` は会話を引き継がず新 ID。interactive には `claude stop` が効かず、taskkill も /F 無しでは失敗。`--remote-control` の名前は agents の name に反映されない。
- 対策: 再起動は `claude respawn <短縮ID>`（ID・会話・スマホ側 URL を据え置き、stopped にも効く）。interactive は `--session-id` / `--resume=<id>`（sessionId も Remote Control URL も据え置き）。停止は `taskkill /T /F`（端末も閉じる）。停止中の一覧と表示名は自前で記録する。Remote Control URL は transcript の `{"type":"system","subtype":"bridge_status"}` 行の url。
- 旧説: 「Remote Control は非対話起動できない」（ドキュメント調査による結論。誤り。`claude --bg --remote-control <名前>` で TTY 無しで起動できる）
- 実例: 2026-09-04 / 2026-09-05 / 2026-09-13 SessionControl
- 自動検出: 候補 `claude-bg-resume`（patterns-claude.md）
- 出典: SessionControl/log/claudeLog.txt:12-29, 616-622 / SessionControl/CLAUDE.md:96-112 / Notion 3d2e4d4b-751b-81d8-a2dd-d2d0e68c7fcf, 3dae4d4b-751b-8130-b478-c12360da4b20

### 調査サブエージェントの結論が実測と矛盾する（CLI の挙動）
- 症状: 「Remote Control は非対話起動できない」と結論されたが、実際は起動できた。
- 原因: ドキュメント・推測ベースの調査。
- 対策: CLI の挙動は実際に叩いて確かめ、実測を採る。
- 実例: 2026-09-04 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:16

### `--remote-control` を付け忘れる／既に付いているのに重ねて起動する
- 症状: 付け忘れるとそのセッションを他デバイスから触れない。確認せずに起動すると Remote Control 無しの余分なウィンドウが増える。
- 原因: 起動経路が複数ある（ユーザーはランチャーから `--resume=<id> --remote-control=<名前> --name=<名前>` で起動している）。
- 対策: 起動前に `Get-CimInstance Win32_Process -Filter "Name='claude.exe'" | Select ProcessId,CommandLine` で `--remote-control=` の有無を見る。起動は PowerShell の Start-Process で `--remote-control=<プロジェクト名>` を付ける。起動後は同じ方法で新しい PID が出たか確かめる（ウィンドウが開いたことは中のコマンドが走ったことを意味しない）。
- 実例: 2026-09-23（3 回。うち `cmd //c start` の `/k` 化けは windows-shell 側の罠）
- 自動検出: 候補 `claude-launch-no-remote-control`（patterns-claude.md）
- 出典: CLAUDE.md:287-305

### 未信頼フォルダで起動すると信頼確認で止まる（git リポジトリ内は親の信頼を見ない）
- 症状: 新規フォルダで起動したセッションが 30 秒で失敗・一覧に出ない。
- 原因: 「このフォルダを信頼しますか？」待ち。親フォルダを信頼しても git リポジトリ内には効かない（実測）。
- 対策: `~/.claude.json` の `projects[<path>].hasTrustDialogAccepted: true` を書く（稼働中の claude も書くので直前に読み直す）。
- 実例: 2026-09-13 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:87

### 入力待ちの状態名がセッション種別で違う
- 症状: 通常セッションの入力待ちが件数にも通知にも出ない。
- 原因: background は `state: "blocked"`、interactive は `status: "waiting"` 等。
- 対策: 判定を 1 関数に集約し、画面・件数・通知は状態名を直接見ない。
- 実例: 2026-09-14 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:99

### Windows ConPTY は孫プロセスが残る限り EOF を返さない（claude の終了を検知できない）
- 症状: claude を exit しても終了を検知できない（MCP を使うプロジェクトでだけ起きる）。
- 原因: claude が起動した MCP サーバー等の孫プロセスが PTY ハンドルを保持する。
- 対策: 終了検知を PTY EOF に依存させず、直接の子の `try_wait()` を別スレッドで見る。kill は `taskkill /T /F` でツリーごと。
- 実例: 2026-06-20 Claudes（kill 側は 2026-06 初期にも）
- 自動検出: 不可
- 出典: Claudes:44-47, 412-427

### PTY で claude(Ink) を包むと起動直後の DSR を取りこぼして永久待機
- 症状: ペインが真っ黒（カーソルのみ）、入力もできない。PTY 出力は最初の 4 バイトで止まる。
- 原因: claude(Ink) は起動時に ESC[6n を送り応答を待つ。フロントのリスナが付く前に emit され、xterm が応答しない。
- 対策: バックエンドで出力をバッファし、リスナ取り付け後にスナップショットを再生する（tmux 方式）。
- 実例: 2026-06-11 Claudes
- 自動検出: 不可
- 出典: Claudes:109-126

### Claude Code(Ink) の改行は ESC+CR（meta+Enter）
- 症状: 端末エミュレータから Shift+Enter で改行を入れたい。
- 原因: Ink は stdin 先頭の ESC を meta 修飾とみなし、meta+Enter を改行に割り当てている（/terminal-setup と同じ）。
- 対策: `"\x1b\r"` を送る（キーハンドラ側で preventDefault も）。`\\\r`（バックスラッシュ trick）は PTY 一括書き込みで submit される。
- 実例: 2026-06-12/13 Claudes
- 自動検出: 不可
- 出典: Claudes:177-184, 346-348

### ツール呼び出しがテキストとして出力されて止まる（上流の不具合）
- 症状: ペイン内の claude が `<invoke name=...>` をそのまま出力し「Worked for Ns」で停止。
- 原因: モデル / CLI 側のツール呼び出しのパース失敗。ラッパー（PTY 転送）は無関係。
- 対策: ラッパーを疑って調べ直さない。Esc → 再指示、または「続けて」。`claude -c` で再開可。頻発なら `/bug`。例外的にストリーミング中のリサイズ（SIGWINCH）だけは疑う余地あり。
- 実例: 2026-06-20 Claudes
- 自動検出: 不可
- 出典: D---Personal-Project-Claudes/memory/claude-tool-leak-is-upstream.md:10-14

## worktree・バックグラウンドセッション

### バックグラウンドセッションが共有チェックアウトへの編集を拒否し、worktree を強制する
- 症状: 「worktree を作らない」方針のプロジェクトでも、bg セッションが隔離を強制して編集できない。
- 原因: バックグラウンドセッションの既定は EnterWorktree で隔離。
- 対策: 黙って worktree を作らずユーザーに伝える（アプリから通常セッションとして起動し直せば隔離の強制は掛からない）。作った worktree は用が済み次第削除。
- 実例: 2026-09-13 SessionControl
- 自動検出: 不可
- 出典: D---Personal-Project-SessionControl/memory/no-worktrees.md:17

### `claude rm` が worktree を消せない（未 push 判定・EBUSY）
- 症状: 「N unpushed commits ... exist on no remote」で拒否され続ける。`--discard-unpushed` で進めると EBUSY で worktree が消えず、git の登録だけ外れて `--force-remove-worktree` も効かなくなる。
- 原因: リモートの無いリポジトリでは全履歴を未 push と数える。セッションが検証用に起動したサーバー（相対パス起動の python など）が worktree を cwd として掴んだまま残る（コマンドラインに worktree のパスが出ない）。
- 対策: `git cherry master <branch>` で失われるコミットを確認 → 必要なら早送りマージ → `claude rm <id> --discard-unpushed <値>` → EBUSY なら `~/.claude/jobs/<短縮ID>` を含むプロセスや、セッション開始前後に起動した残骸を `Get-CimInstance Win32_Process` の CreationDate で探して終了 → 空ディレクトリを rmdir → 再実行。
- 実例: 2026-09-13 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:807 / Notion 3dae4d4b-751b-819e-8543-d14d0d5844fa

### サブエージェントが途中で止まって応答しない
- 症状: worktree で修正中のサブエージェントが途中から無応答。
- 原因: 不明。
- 対策: 5 分ルールで見切り、止めて差分を読んで引き継ぐ。
- 実例: 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1193

## シェル・タスク・サンドボックス

### Claude Code のシェルは非対話（`!` や Bash で対話入力を待つコマンドが空値で成功する）
- 症状: `wrangler secret put` が Success と出たのに、登録されたのは空文字のシークレット。
- 原因: `!` 実行・Bash ツールは TTY が無く stdin が空。
- 対策: 対話入力が要るコマンドは値をパイプかファイルで渡し、直後に動作確認する。
- 実例: 2026-07-05 RigFlow（rclone config の非 TTY で EOF になる件は gdrive 側、2026-09-05 SessionControl）
- 自動検出: 候補 `wrangler-secret-put-no-stdin`（patterns-claude.md）
- 出典: RigFlow/log/claudeLog.txt:298 / SessionControl/log/claudeLog.txt:215, 273

### TaskStop は npm ラッパーだけ止め、vite 本体がポートを掴んだまま残る
- 症状: 次回 dev サーバーが 5173 を取れない。
- 原因: `npm run dev` の子（vite）が残る。
- 対策: 停止後 `netstat -ano | grep :5173` で PID を特定し `taskkill /T /F`。
- 実例: 2026-07-03 Traddist
- 自動検出: 不可
- 出典: Traddist/log/claudeLog.txt:30

### Bash サンドボックス下では headless Chrome が起動しない／連続起動で空画像
- 症状: headless Chrome が起動できない。`--user-data-dir` を使い回した連続起動で空画像。
- 原因: サンドボックスの制約／プロファイルのロック。
- 対策: `dangerouslyDisableSandbox` が要る。連続生成は 1 回だけ大きく作って縮小する。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:411

### クラウドルーチンのサンドボックスから `*.workers.dev` へ到達できない
- 症状: ルーチンが API に到達できず curl exit 56 / HTTP 000。
- 原因: サンドボックスの egress プロキシが `*.workers.dev` への CONNECT を 403 で拒否。当時は Gmail コネクタにも送信ツールが無かった（create/update/list_drafts のみ）。
- 対策: 定期通知はクラウドルーチンではなく Worker の cron + Email Sending / Webhook / Web Push で組む。ルーチンに外部 API 到達を前提とした設計をしない。
- 旧説: 「Gmail コネクタは送信できない」は 2026-08-12 時点の話。2026-09-29 時点のコネクタには send_message がある（要再確認）。
- 実例: 2026-08-12 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2037-2052

## 自作 MCP サーバー（作る側）

### stdio MCP サーバーで stdout に書くとプロトコルが壊れる
- 症状: MCP の通信が壊れる・応答不能。print や fusionscript のネイティブ出力、Microsoft.Extensions.Hosting のコンソールログが JSON に混ざる。
- 原因: stdout は MCP（JSON-RPC / JSON Lines）が占有する。
- 対策: ログはファイル（`log/server-*.log`）か stderr へ。.NET は `LogToStandardErrorThreshold = LogLevel.Trace`。Python ワーカは fd 1 を JSON 専用に複製し、fd 1 自体は stderr へ向け直す。
- 実例: 2026-04 WinGuiMcp / 2026-09 AEMCP / 2026-09 DvcMCP
- 自動検出: 不可（MCP サーバーのソースをパスで特定できず、console.log は他で正常）
- 出典: AEMCP/CLAUDE.md:64 / DvcMCP/CLAUDE.md:73-74 / traps-personal（dotnet: MS Hosting の既定ログ）

### MCP の stdio クライアントは子プロセスの環境変数を 12 個に絞る（外部 exe が無言で止まる）
- 症状: MCP サーバーから起動した aerender が `aerender version 26.5x89` の 1 行だけ出して 10 分以上停止（メモリ 4.4MB・CPU 0）。素の node やコマンドラインからは正常。
- 原因: MCP SDK の StdioClientTransport は既定で `APPDATA HOMEDRIVE HOMEPATH LOCALAPPDATA PATH PROCESSOR_ARCHITECTURE PROGRAMFILES SYSTEMDRIVE SYSTEMROOT TEMP USERNAME USERPROFILE` だけ渡す。`CommonProgramFiles` 系 3 つが全部落ちると AE が初期化できない（1 つでもあれば動く）。
- 対策: 外部アプリを spawn するときは不足する環境変数をレジストリ（`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion` の CommonFilesDir 等）から補って渡す。既定値の決め打ちはしない。
- 実例: 2026-09-16〜17 AEMCP
- 自動検出: 不可
- 出典: AEMCP/CLAUDE.md:117-123 / AEMCP/log/claudeLog.txt:580-594 / Notion 3dde4d4b-751b-81e8-a3dd-dcdb532aa2d8

### 外部プロセスの stdout はパイプ相手だとブロックバッファリングされる
- 症状: 進んでいてもログが数十行たまるまで出ない。「1 行しか出ていない = 止まっている」と誤認する。
- 原因: パイプ接続時の stdio バッファリング（aerender、ffmpeg の avio 出力も同類）。
- 対策: 進行は出力ファイルの有無・プロセスのメモリ/CPU で判断する。ffmpeg の `ametadata` なら `direct=1`。
- 実例: 2026-07-19 SRT-Blue / 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP/CLAUDE.md:124-126 / SRT-Blue/log/claudeLog.txt:762-767

### ブリッジの HTTP ハンドラで例外を出すと無言タイムアウトになる
- 症状: /health など一部のエンドポイントだけが無言でタイムアウト。
- 原因: 切り出したモジュールで未定義参照の例外が出たが、レスポンスを書かない経路だった。
- 対策: HTTP ハンドラは例外時も必ずエラー応答を書く。疎通確認で全エンドポイントを 1 度は通す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP/log/claudeLog.txt:220-223

### キューの見張りがタイムアウト後に busy を解放しないと以後全 RPC が詰まる
- 症状: 1 回の取りこぼしで以後すべての RPC が無言で詰まり、/health は正常を返し続ける。
- 原因: 見張りがログを書くだけで reject・キュー続行をしていなかった。
- 対策: タイムアウト時は reject してキューを進める（呼び出しごとのコールバックなら取り違えない）。/health に busy・queueLength・currentJob を出す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP/log/claudeLog.txt:114-120 / AEMCP/CLAUDE.md:190-193

### MCP で画像を base64 テキストで返すとトークン上限で受け取れない
- 症状: 218KB の base64 が受信できない。
- 原因: テキストとして返すとトークンに計上される。
- 対策: ImageContent（MCP の画像コンテンツ）で返し、max_width で縮小する。JPEG にするとさらに 1/3〜1/7。
- 実例: 2026-03 unity-mcp / 2026-03-31 ClaudeVideoReader / 2026-04-12 WinGuiMcp
- 自動検出: 不可
- 出典: MocapSimulator:340-342, 386 / unity-mcp:102-104 / ClaudeVideoReader:30-33 / MS/.claude/claudeLog.txt:353-356, 385

### Claude の画像入力は長辺 1568px を超えると受け側で縮小される
- 症状: 大きい画像を返すと転送量だけ増え、焼き込んだ小さいラベルが潰れる（15.9MB）。
- 原因: 受け側の縮小。
- 対策: 上限から逆算して最初から小さく組む（15.9MB → 1.5MB）。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP/log/claudeLog.txt:429-432, 519-529

### stdio MCP を `echo ... | server` でテストすると応答前に終わる
- 症状: 応答が返らない。
- 原因: echo が即 stdin を閉じ、サーバーが応答前に終了する。
- 対策: `(echo ...; sleep N) | server` で stdin を保持する、またはクライアントスクリプトで叩く。
- 実例: 2026-04 WinGuiMcp
- 自動検出: 候補 `stdio-mcp-echo-pipe`（patterns-claude.md）
- 出典: MocapSimulator:323-324

### TS ⇔ Python の契約テストを正規表現で書くと CRLF・入れ子ジェネリクスで取りこぼす
- 症状: 契約テストが通るのに op が素通り（偽陽性）。
- 原因: CRLF でコメント除去が効かず引数を飲み込む。`(?:<[^>]*>)?` が入れ子ジェネリクスを拾えない。
- 対策: ソースを LF 固定（.gitattributes）。型引数を先に落とす。「呼び出し回数と拾えた数の一致」を検査する。
- 実例: 2026-09-17 AEMCP / 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DVC/CLAUDE.md:81-82 / AEMCP/log/claudeLog.txt:804-809

### CsWinRT で COM インターフェースへ直接キャストすると失敗する
- 症状: `(IMemoryBufferByteAccess)reference` が `Invalid cast from WinRT.IInspectable`。
- 原因: CsWinRT の投影では C# キャストが効かない。
- 対策: `using WinRT;` + `reference.As<IMemoryBufferByteAccess>()`。
- 実例: 2026-04-12 WinGuiMcp（OCR）
- 自動検出: 候補（正規表現案 `\(IMemoryBufferByteAccess\)`、.cs の編集。頻度が低いので未提案）
- 出典: MS/.claude/claudeLog.txt:353

### x64 の INPUT 構造体は union を FieldOffset(8) にしないと SendInput が効かない
- 症状: SendInput が効かない。
- 原因: x64 ではアラインメントで union が 8 バイト目から始まる。
- 対策: `[FieldOffset(8)]`。
- 実例: 2026-04 MocapSimulator（WinGuiMcp の前身テスト）
- 自動検出: 候補（正規表現案 `struct INPUT[\s\S]{0,200}FieldOffset\(4\)`。頻度が低いので未提案）
- 出典: MS/.claude/claudeLog.txt:87

### 変異チェック後の bin に変異入りの exe が残り、存在しない不具合を追う
- 症状: 「読み込み完了と出るのにキャラクターが空」という存在しない不具合を追った。
- 原因: 修正を外して `dotnet test` → ソースを戻す、の最後の回の bin がそのまま残る。ソースは戻っても bin は戻らない。
- 対策: 変異チェック（回帰テストが落ちることの確認）の後、GUI 確認の前にソース復元後のビルドを 1 回挟む。辻褄の合わない挙動はまず「その行が入った exe か」をログで確かめる。
- 実例: 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: D---Personal-Project-MotionForge/memory/rebuild-after-mutation-check.md:10-15

### 許可の挙動を claude -p で試しても対話セッションの代わりにならない
- 症状: `claude -p --permission-mode auto` で `rm -rf <作業フォルダ内>` を試すと、許可ルールを外しても「needs approval」で拒否される。
- 原因: ヘッドレスのセッションでは、シェルがファイルを作る・変える・消す操作に、作業フォルダの中でも Claude Code 本体が確認を出す（`Claude Code asks before a shell command creates, changes or removes files there`）。確認できないので拒否になる。
- 対策: 許可ルールや hook の permissionDecision の効き目は、実際の対話セッションで試す。`-p` で見られるのは hook の出力と拒否の理由まで（`--output-format stream-json --verbose` で tool_result の文面を読む）。
- 実例: 2026-09-29 ~/.claude（rm-guard の導入）
- 自動検出: 不可
- 出典: ~/.claude/log/claudeLog.txt 2026-09-29
