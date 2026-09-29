# windows-shell の罠

全件は ~/.claude/traps-catalog/windows-shell.md。ここは再発しやすいものだけ。

### シェルに Python を埋め込まない
`python -c` / heredoc / `node -e` に書いた `\r\n` `\b` `\\` が実改行・制御文字に化け、ファイルやパスを壊す（実行時まで気付かない）。原因はシェルを通る時点でのエスケープ解釈。→ Write で scratchpad に .py を書き `python <パス>` で実行。1 行の置換は Edit。（実例: 2026-09-24 に 1 日 4 回 / 2026-09-16 AEMCP）

### Git Bash の MSYS パス変換
`/` で始まる引数（`/fader/1`、`schtasks /Create`、`powercfg /change`、`taskkill /PID`）が `C:/Program Files/Git/...` に書き換わる。送信やコマンドは成功扱いで、相手が黙って無視する。→ 先頭に `MSYS_NO_PATHCONV=1`、または `//Create`、または PowerShell 経由。（実例: 2026-07 Traddist / 2026-09-24 Ext_TokinoSora）

### Git Bash から cmd を起動しない
`cmd //c start ... cmd /k` は `/k` が `K:/` に化け、窓だけ開いて何も走らない。`cmd //c build.bat`（相対）は .bat を見つけられないまま exit 0。→ PowerShell の `Start-Process` で起動し、.bat はフルパス。成否は成果物の日時か完了メッセージで見る。（実例: 2026-09-23 に 3 回 / 2026-09-15 ftpDeck）

### PowerShell スクリプトは BOM 付き
日本語を含む .ps1 がコメントと無関係な行で構文エラー。原因は Windows PowerShell 5.1 が BOM 無しを ANSI(CP932) で読むこと（Write/Edit は BOM を付けない）。WSH の .vbs も同様。→ .ps1 は UTF-8 BOM 付き、.vbs は UTF-16LE BOM 付き、または ASCII のみ。（実例: 2026-05-04 StreamDeckMIDI / 2026-09-05 SessionControl / 2026-09-16 AEMCP）

### Git Bash の curl で日本語を送ると化ける
ASCII は通るのに日本語の値だけサーバに弾かれ、サーバの不具合に見える。原因は Git Bash のコードページで `curl -d '日本語'` が化けること。→ JSON をファイルにして `--data-binary @file`、または node の fetch をスクリプトファイルで。確認は API レスポンスで。（実例: 2026-06-15 Shifter / 2026-07-05 RigFlow）

### 子プロセスの出力は cp932
起動した PowerShell / Python / 付属コマンドの日本語が化ける。→ PowerShell は `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`、Python は `sys.stdout.reconfigure(encoding="utf-8")`。付属コマンドは終了コードで判断。（実例: 2026-07 Traddist / 2026-09-23 DvcMCP）

### PowerShell を `-Command -` で呼ばない
標準入力で渡した複数行パイプラインが、出力なし・終了コード 0 で黙って捨てられる。→ `-EncodedCommand`（UTF-16LE の base64）で渡す。Get-CimInstance は初回 stderr に CLIXML を吐くので、成否は終了コードで見る。（実例: 2026-09-22 MemoryObserver）

### pip と python が別の Python
`pip install` が成功したのに import できない。この PC は python=rye、pip=AppData の Python。→ 常に `python -m pip` か `uv`。（実例: 2026-03-31 ClaudeVideoReader / 2026-05-23 KachinkoShot）

### Git Bash の tar は GNU tar
`C:\...` を渡すと「Cannot connect to C:」、zip/whl は読めない。→ パスは相対 + `-C`。zip は `C:\Windows\System32\tar.exe` を絶対パスで。（実例: 2026-08-23 SignalHub / 2026-09-23 BMCP）

### UAC の同意は自分で押せない
`Start-Process -Verb RunAs` の同意画面はセキュアデスクトップに出るため win-gui で操作できず、MSI の無人インストールは 1603 で落ちる。→ ポータブル版 zip の展開、`winget --scope user`、`msiexec /a`、HKCU への設定を先に探す。（実例: 2026-09-24 BMCP）
