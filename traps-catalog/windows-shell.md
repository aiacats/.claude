# windows-shell の罠（カタログ）

Git Bash(MSYS)・PowerShell・cmd・.bat・文字コード/BOM/改行・パス・curl で踏んだ罠の全件。トラブル時に grep で引く。厳選版は `~/.claude/rules/traps/windows-shell.md`。

### シェルに Python を埋め込まない（heredoc / python -c / node -e でバックスラッシュが化ける）
- 症状: 正規表現 `\r?\n` が実改行に化けてテストファイルが読めない。`D:\...\Blender 5.2\blender.exe` の `\b` が消えてパスが壊れる。heredoc で書いた config.json の `[^"\\]` が `[^"\]` になり構文エラー。JSX の `/\\/g` が `/\/g`（未終端）になり evalScript が永久に返らない。C# の `Replace('\\','/')`・JS の `split('\\')` が CS1012 / SyntaxError。壊れても実行時まで気付かない
- 原因: シェルを経由する時点でエスケープが解釈される（環境により heredoc でも `\\` が `\` に潰れる）。raw 文字列にしても同じ
- 対策: Write ツールで scratchpad に .py（.js）を書き、`python <パス>` で実行する。1 行の置換は Edit。ソースに `\` を書かずに済むなら `Path.DirectorySeparatorChar` / `path.sep` を使う。直した後は該当箇所を読み返す
- 実例: 2026-09-05 SessionControl / 2026-09-06 lll-12 / 2026-09-16 AEMCP / 2026-09-16 BMCP / 2026-09 MemoryObserver / 2026-09-24（1 日 4 回）
- 自動検出: hook `python-inline-backslash`（python のみ）| 候補 `heredoc-unquoted-backslash`（patterns-shell.md）
- 出典: CLAUDE.md「一括置換のスクリプトをシェルに埋め込まない」, SessionControl/log/claudeLog.txt:49, AEMCP/CLAUDE.md:233-240, AEMCP/log/claudeLog.txt:30-35, BMCP/log/claudeLog.txt:77, MemoryObserver/log/claudeLog.txt:105, lll-12 LLL-LOG:140-142, Notion 3d2e4d4b-751b-816a-bb19-db48bdbdcfc4

### Git Bash の MSYS パス変換で `/` 始まりの引数が化ける（OSC アドレス・schtasks・powercfg・taskkill）
- 症状: `/fader/1` が `C:/Program Files/Git/fader/1` で送られ、送信は成功するのに受信側が黙って捨てる。`schtasks /Create`、`powercfg /change`、`taskkill /PID` も壊れる
- 原因: MSYS2 が `/` 始まりの引数を POSIX パスとみなして Windows パスへ変換する
- 対策: 先頭に `MSYS_NO_PATHCONV=1`（必要なら `MSYS2_ARG_CONV_EXCL='*'`）、または `//Create` のように `//` で始める、または PowerShell 経由で呼ぶ。送信側で実際に送った文字列を print して確かめる
- 実例: 2026-07 Traddist（schtasks）/ 2026-09-05 vortex_urp / 2026-09-06 OSC2MIDI / 2026-09-24 Ext_TokinoSora_2026-pia（/pianokey）/ 2026-09-27 vortex-timeline-export（powercfg）
- 自動検出: hook `osc-address-msys`（OSC）| 候補 `win-cmd-slash-msys`（schtasks / powercfg / taskkill）
- 出典: rules/app.md:160-162, Traddist/log/claudeLog.txt:60, skills/vortex-timeline-export/SKILL.md:36, Notion 3d2e4d4b-751b-819b-b956-f631b1545ea1, 3d3e4d4b-751b-8156-aaad-f3ffd459b4ed
- 備考: OSC 固有の説明は protocol 分野（hook の ref は rules/traps/protocol.md）

### Git Bash から cmd を起動しない（`/k` が `K:/` に化ける・相対 .bat が exit 0）
- 症状: `cmd //c start ... cmd /k "..."` でウィンドウだけ開いてコマンドが実行されず、プロンプトが出るだけでエラーも見えない。build-win.bat を cmd 経由で起動すると「コマンドとして認識されません」。`cd X && cmd //c build.bat` は何もビルドされないのに exit=0
- 原因: MSYS のパス変換で `/k` → `K:/`。相対パスの .bat は cmd 側で解決できず、後続 echo の終了コードで成功に見える（`cd` してから渡しても効かない）
- 対策: PowerShell の Start-Process で起動する（`powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/k','...'"`）。.bat はフルパスで渡し、成否は成果物の日時・完了メッセージで見る。起動後はプロセスが実際に立ったか確かめる
- 実例: 2026-07-29 SignalHub / 2026-09-15 ftpDeck / 2026-09-23（1 日 3 回）
- 自動検出: hook `cmd-start-msys` | 候補（相対 .bat）`cmd\s+//c\s+(?![A-Za-z]:[\\/]|"[A-Za-z]:)[^\s]*\.(bat|cmd)\b`
- 出典: CLAUDE.md「--remote-control」節, SH/log/claudeLog.txt:877-879, ftpDeck/log/claudeLog.txt:512, skills/tauri-release/SKILL.md:63

### PowerShell スクリプトは BOM 付き（5.1 / WSH は BOM 無し UTF-8 を ANSI で読む）
- 症状: 日本語コメント入りの .ps1 が、コメントと無関係な行で「予期しないトークン」。エラー文も化ける。.vbs も同様に化ける
- 原因: Windows PowerShell 5.1 は BOM 無しを ANSI(CP932) として読む。WSH（.vbs/.js）は UTF-8 を読めない。Write/Edit ツールは BOM を付けない
- 対策: .ps1 は UTF-8 BOM 付き（`utf-8-sig`）、.vbs は UTF-16LE BOM 付きで保存。または ASCII のみで書く／pwsh 7 で実行
- 実例: 2026-05-04 StreamDeckMIDI / 2026-09-02 / 2026-09-05 SessionControl / 2026-09-16 AEMCP（launch-ae.ps1）
- 自動検出: hook `ps1-non-ascii-without-bom`（.ps1）| 候補 `vbs-non-ascii-without-utf16-bom`
- 出典: CLAUDE.md「作るときの作法」, SessionControl/log/claudeLog.txt:52, AEMCP/CLAUDE.md:227-235, StreamDeckMIDI:28-30, skills/windows-gui-testing/SKILL.md:72, Notion 3cfe4d4b-751b-8184-91d1-ca06985a883b, 3d2e4d4b-751b-816a-bb19-db48bdbdcfc4

### Git Bash の curl で日本語 JSON を送ると化ける
- 症状: ASCII の値は通るのに日本語の値だけ「roles に不正な値」などで弾かれ、サーバの不具合に見える。DB の値が化ける。別の回はデータは正しくコンソール表示だけ化けていた
- 原因: Git Bash のコンソールが非 UTF-8 コードページで、`curl -d '...日本語...'` / heredoc 経由のリテラルが CP932 化する。`--data @file` も Windows パスで失敗しやすい
- 対策: 日本語を含む JSON/SQL はファイル化して `curl --data-binary @file` / `wrangler --file` で渡すか、node の fetch（スクリプトファイル）で送る。結果の確認はコンソール echo ではなく API レスポンス・ブラウザで行う。ASCII だけ通るなら送信側を疑う
- 実例: 2026-06-15 Shifter / 2026-06-27 RigFlow / 2026-07-05 RigFlow
- 自動検出: 候補 `curl-data-non-ascii`
- 出典: Shf/log/claudeLog.txt:353-356, Shifter memory shifter-conventions.md:30, RigFlow/log/claudeLog.txt:123, :368, :1028

### 子プロセスの出力が cp932 で化ける（PowerShell・Python・Windows 付属コマンド）
- 症状: 子プロセスとして起動した PowerShell のエラー文・プロセス名が化ける。Python のログ・JSON の日本語が化ける。shutdown.exe などの出力が読めない
- 原因: 日本語 Windows の既定出力コードページが 932
- 対策: PowerShell はスクリプト冒頭で `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。Python は起動直後に `sys.stdout.reconfigure(encoding="utf-8")`（stdin/stderr も）。stdio MCP なら fd 1 を JSON 専用に複製し fd 1 自体は stderr へ向け直す。付属コマンドは出力を読まず終了コードで判断する（shutdown なら 5 / 1115 / 1190）
- 実例: 2026-07 Traddist / 2026-09-13 SessionControl / 2026-09 MemoryObserver / 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:644, MemoryObserver/CLAUDE.md:49-50, MemoryObserver/log/claudeLog.txt:103, DvcMCP/CLAUDE.md:71-73, Traddist/log/claudeLog.txt:17

### PowerShell を `-Command -`（標準入力）で呼ぶと複数行パイプラインが黙って捨てられる
- 症状: stdout 空・stderr 空・終了コード 0
- 原因: 標準入力は対話プロンプトとして 1 行ずつ解釈され、`ForEach-Object { ... }` を挟んだ複数行が成立しない
- 対策: `-EncodedCommand <UTF-16LE の base64>` で渡す。失敗判定は終了コードで行う
- 実例: 2026-09-22 MemoryObserver
- 自動検出: 候補 `powershell-command-stdin`
- 出典: MemoryObserver/CLAUDE.md:42-45, MemoryObserver/log/claudeLog.txt:11-13, Notion 3e3e4d4b-751b-8105-b033-c1f0cf260ab3

### Get-CimInstance の初回呼び出しは stderr に CLIXML の進捗を吐く
- 症状: 正常終了なのに stderr に出力があり、失敗と誤判定する
- 原因: 進捗ストリームが CLIXML として stderr に出る
- 対策: 成否は終了コードで判定し、stderr の有無で判定しない
- 実例: 2026-09 MemoryObserver
- 自動検出: 不可
- 出典: MemoryObserver/CLAUDE.md:51-52

### PowerShell の二重引用符内のバッククォートはエスケープになる
- 症状: install-task.ps1 で文字列が意図せず変わる
- 原因: `"..."` 内の `` ` `` は PowerShell のエスケープ文字
- 対策: 展開不要な文字列は単一引用符で書く
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:79

### Bash で PowerShell のヒアストリング `@'...'@` を使うとコミットメッセージ先頭に @ が混入
- 症状: コミットメッセージが `@...` で始まる
- 原因: Bash ツールで PowerShell の構文を使った
- 対策: Bash では heredoc（`git commit -F - <<'EOF'`）
- 実例: 2026-09-06 lll-12（unity-mcp f6e2410）
- 自動検出: 候補 `git commit[^\n]*@'`（Bash ツール説明にも記載あり）
- 出典: LLL-LOG:66-67

### Start-Process -WorkingDirectory はワイルドカード扱い
- 症状: `p[ab]` のようなフォルダを作業場所にすると、隣の `pa` で起動する
- 原因: Windows PowerShell 5.1 の `Start-Process -WorkingDirectory` はパスをワイルドカード展開する（`-LiteralPath` 相当が無い）
- 対策: `System.Diagnostics.ProcessStartInfo` で起動する
- 実例: 2026-09-13 SessionControl
- 自動検出: 候補 `Start-Process[^\n]*-WorkingDirectory`（`[` を含むパスのときだけ実害。warn）
- 出典: SessionControl/CLAUDE.md:85

### ProcessStartInfo.Arguments は 1 本の文字列。cmd /c start は & | % を解釈する
- 症状: 名前に空白や `"` があると引数が割れる。`cmd /c start` 経由では利用者入力が構文解釈される
- 原因: Arguments はそのままコマンドラインになる
- 対策: CommandLineToArgvW 規則でクォートする関数を通す。利用者入力を `cmd /c start` に渡さない。値は環境変数で渡すのも手
- 実例: 2026-09-13 SessionControl
- 自動検出: 候補 `cmd(\.exe)?['"]?\s*,\s*\[?['"]/c['"]\s*,\s*['"]start`（.ts/.rs/.cs）
- 出典: SessionControl/CLAUDE.md:82

### npx / wrangler に空白入り値を渡すと引数が割れる
- 症状: `"public, max-age=31536000, immutable"` が 3 引数に割れ、wrangler が Unknown arguments
- 原因: Windows で npx を spawn するには shell が必須で、shell を通すと配列引数の空白が再分割される
- 対策: shell: true で呼ぶときは全値をクォートした 1 本のコマンド文字列で渡す。または npx を経由せず node で CLI の JS を直接起動
- 実例: 2026-08-21 SignalHub（publish-update.mjs）
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1089-1092

### cmd では空文字の環境変数を作れない（`set VAR=` は削除）
- 症状: 署名鍵パスワードを空で渡せず、tauri build が対話プロンプトで無限停止（10 分以上）
- 原因: cmd の `set VAR=` は変数の削除になる
- 対策: .bat では `CI=true` など無人実行を示す別の手段で対話を抑止する。bash 経由なら `VAR=""` で空を明示
- 実例: 2026-08-21 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1078-1082

### .bat の中のパス区切り `\f` が改ページ文字に化ける
- 症状: `can't open file 'scripts\x0cetch-tools.py'`
- 原因: 書き換えツールを通したときに `\f` がエスケープとして解釈された
- 対策: skill tauri-release に記載（.bat 内のパス区切りをスラッシュにする）
- 実例: 日付不明 tauri-release
- 自動検出: 候補 `bat-formfeed`
- 出典: skills/tauri-release/SKILL.md:66

### GNU tar に `C:\...` を渡すとリモートホスト指定になる／zip・wheel が読めない
- 症状: `tar` が "Cannot connect to C:" / 「D: に接続できない」「tar アーカイブに見えない」で失敗
- 原因: Git Bash の tar は GNU tar。引数中の `host:path` をリモート指定と解釈し、zip も読めない
- 対策: パスは相対にして基準は `-C` か spawn の `cwd` で渡す（または `--force-local`）。zip/whl は Windows 同梱の bsdtar（`C:\Windows\System32\tar.exe`）を絶対パスで呼ぶ
- 実例: 2026-08-23 SignalHub / 2026-09-23 BMCP
- 自動検出: 候補 `gnu-tar-drive-path`, `gnu-tar-zip`
- 出典: SH/log/claudeLog.txt:1196-1198, BMCP/CLAUDE.md:162, BMCP/log/claudeLog.txt:149-151, :166, :168

### pip と python が別の Python を指す
- 症状: `pip install` が成功したのに `import` できない（opencv-python / PySide6 が見つからない）
- 原因: この PC では `python` = rye 管理の cpython 3.12.5、`pip` = `AppData\Local\Programs\Python\Python312` 側。2 系統が共存
- 対策: 常に `python -m pip install ...`。uv プロジェクトなら `uv add` / `uv run`
- 実例: 2026-03-31 ClaudeVideoReader / 2026-05-23 KachinkoShot
- 自動検出: 候補 `bare-pip-install`
- 出典: ClaudeVideoReader:10-12, KachinkoShot:45, KachinkoShot memory python_env_quirk.md:10

### Git Bash が注入する `Git\mingw64\bin` で standalone mingw の gcc が無言で死ぬ
- 症状: `go build`（CGO）が `runtime/cgo: cgo.exe: exit status 2` だけ出して失敗。cc1.exe が起動直後に無言終了。通常のターミナルからなら成功。以前の成功はビルドキャッシュで成功に見えていただけ
- 原因: git-bash が子プロセスに注入する `C:\Program Files\Git\mingw64\bin` の zlib1.dll / libgmp-10.dll / libzstd.dll を choco の mingw-w64 の cc1.exe が拾う
- 対策: ビルドスクリプトでプロセスの PATH から `*\Git\mingw64*` を除去してからビルド
- 実例: 2026-07 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:476-500

### winget で入れたツールが、古い PATH を持つ親から起動した Claude Code / MCP から見えない
- 症状: `/mcp` で MCP サーバーが `-32000` で接続失敗
- 原因: PATH 更新は新規プロセスにしか反映されない。Claude Code を再起動しても親（エクスプローラ等）が旧 PATH なら子の MCP も uv/uvx を解決できない
- 対策: `.mcp.json` の `command` を絶対パス（例: `C:/Users/<u>/AppData/Local/Microsoft/WinGet/Links/uv.exe`）で書く
- 実例: 2026-06 totolive_202511
- 自動検出: 不可（素の `"command": "uv"` が常に壊れるわけではない）
- 出典: totolive_202511/.claude/claudeLog.txt:136-156

### Chrome の --user-data-dir を長いパス（scratchpad）に置くと 260 文字を超える
- 症状: Service Worker のキャッシュが空のまま／`cache.put` が「Entry already exists」で必ず失敗（紛らわしい文言）
- 原因: Windows のパス長上限 260（実測 251 文字の階層の下に作ろうとする）
- 対策: プロファイルは `%TEMP%\moc` のような短いパスに置く
- 実例: 2026-09-26 MemoryObserver
- 自動検出: 候補 `--user-data-dir=?[^\s]*scratchpad`
- 出典: MemoryObserver/CLAUDE.md:83-86

### vcpkg を C:\Program Files に置くと権限エラー／FFmpeg はパスの空白で失敗
- 症状: vcpkg install が buildtrees への書き込みで失敗。ffmpeg のビルドが失敗
- 原因: Program Files 配下は非管理者で書き込めない。空白を含むパスでビルドスクリプトが壊れる
- 対策: プロジェクトローカル（空白の無いパス）に vcpkg を git clone し、CMakePresets のツールチェーンをそちらへ向ける。FFmpeg はプリビルド（BtbN / gyan.dev）を external/ へ展開してもよい
- 実例: 2026-02 freed-decorder / 2026-02-17 XRCaliblator
- 自動検出: 候補 `Program Files[/\\]+vcpkg`（CMakePresets.json / CMakeLists.txt）
- 出典: freed-decorder:39-42, XRCaliblator:26-27

### 管理者権限が要る操作の UAC を自分で押せない（MSI 1603）
- 症状: `Start-Process -Verb RunAs` の同意画面を win-gui で操作できない。MSI の無人インストールが 1603 で失敗
- 原因: 同意画面はセキュアデスクトップに出る（`PromptOnSecureDesktop` を変えるにも管理者権限が要る）
- 対策: ユーザー領域で済む方法を先に探す（ポータブル版 zip の展開、`winget --scope user`、`msiexec /a`、HKCU への設定）。それでも要るならユーザーの判断を仰ぎ、UAC を何度も出さない
- 実例: 2026-09-24 BMCP（Blender 5.2 の MSI → 公式 zip をユーザー領域へ展開）
- 自動検出: 候補 `-Verb\s+RunAs\b|\brunas\s+/user`（warn）
- 出典: CLAUDE.md「管理者権限が要る操作」, BMCP/log/claudeLog.txt:125-128

### cmd の assoc は HKLM 側しか映さない
- 症状: HKCU で関連付けを変えたのに assoc は旧設定を表示
- 原因: assoc は HKLM\Software\Classes を見る。実際は HKCU が優先
- 対策: 一時ファイルを Start-Process で開き、起動したプロセスのコマンドラインで確認する
- 実例: 2026-09-24 BMCP
- 自動検出: 不可
- 出典: BMCP/log/claudeLog.txt:199-204

### Windows の予約名（CON / NUL 等）をファイル名にすると分かりにくいエラー
- 症状: 既定ファイル名が予約名になると保存時に意味の取りにくいエラー（懸念として記録）
- 原因: ファイル名の正規化が予約名と制御文字を素通し
- 対策: 正規化で予約名（CON PRN AUX NUL COM1-9 LPT1-9、拡張子付きも）と制御文字を弾く
- 実例: 2026-09-13 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2567-2569
