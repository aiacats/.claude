// 機械検出できる罠の一覧。trap-guard.mjs が照合し、test-hooks.mjs が examples を全件流す。
// 罠を足すときはここへ 1 件足し（examples 必須）、説明本体は rules/traps/<分野>.md か traps-catalog/<分野>.md へ書く。
//
// 項目:
//   id        一意な名前。誤検知で通したいときはコマンド/コードに `trap-ok:<id>` と書けば素通りする
//   severity  block = 実行すれば確実に壊れる（実行前に止める。bash/shell のみ）
//             warn  = 書き方の注意（実行後・編集後に知らせて直させる）
//   tool      bash  = Bash ツールのコマンド（Git Bash。MSYS のパス変換が効く）
//             shell = Bash と PowerShell の両方
//             edit  = Edit / Write / MultiEdit で書いた文字列
//             mcp-code = 自作 MCP の「任意コードを実行」ツールに渡したコード（下の MCP_CODE_TOOLS）。
//                        実行前に中身が分かるので block も使える
//             配列で複数指定できる（例: ['edit', 'mcp-code']。同じ本文の罠をファイルにも MCP にも当てる）
//   files     edit / mcp-code のとき対象にするファイルパスの正規表現（/ 区切りに正規化して照合）。
//             mcp-code は MCP_CODE_TOOLS の仮のパス（mcp:bmcp/run_python.py など）で照合する
//   exclude   edit / mcp-code のとき対象外にするファイルパスの正規表現
//   scope     edit のとき "new"（書き足した文字列だけ。既定）| "file"（編集後のファイル全体）
//   when      一致したら罠
//   unless    これにも一致したら罠ではない
//   check     正規表現で書けない判定（引数: { text, filePath, bytes }、true で罠）
//   message   Claude に返す文。何が壊れるか → どう直すか
//   ref       説明本体の場所（~/.claude からの相対 + 見出しのアンカー。テストが見出しの実在を確かめる）
//   examples  { hit: [...], miss: [...] }。bash/shell はコマンド文字列、edit は [相対パス, 内容]、
//             mcp-code は [MCP_CODE_TOOLS の仮のパス, コード]。
//             check でバイト列を見るものは examples が書けないので test-hooks.mjs に個別のテストを書く

// mcp-code の対象。ツール名 → 照合するコードのフィールド（各 MCP のツール定義で確認済み）と仮のパス。
// 仮のパスの拡張子で、.py / .jsx 向けの edit のパターンを files の指定だけで流用できる。
//   BMCP   server/src/tools/core.ts  blender_run_python { source }
//   AEMCP  server/src/tools/core.ts  ae_run_script      { source, undoGroup }
//   DvcMCP server/src/tools/core.ts  resolve_run_python { source }
// ツールを足したら settings.json の PreToolUse / PostToolUse の matcher にも足すこと。
export const MCP_CODE_TOOLS = {
  mcp__bmcp__blender_run_python: { field: 'source', path: 'mcp:bmcp/run_python.py' },
  mcp__aemcp__ae_run_script: { field: 'source', path: 'mcp:aemcp/run_script.jsx' },
  mcp__dvcmcp__resolve_run_python: { field: 'source', path: 'mcp:dvcmcp/run_python.py' },
};

const ANY = /[\s\S]*/; // パスだけで判定する edit 用
// ExtendScript のファイルかどうか。React の .jsx と区別するため、AE 固有の書き方があるときだけ対象にする
const AE_CONTEXT = /\bapp\.project\b|\$\.(?:global|writeln|evalFile|fileName)\b|#target\b|#include\b|\bCompItem\b/;
// ExtendScript の正規表現リテラルで、文字クラスの中に素の / があるもの（/[\\/]+$/ など）
const AE_REGEX_SLASH_IN_CLASS = /(?:^|[=(,:;!&|?{}[\s])\/\[(?:\\.|[^\]\\\n/])*\//m;
// mcp-code の仮のパスのうち、指定の MCP 以外を外す（.py は BMCP と DvcMCP の両方にあるため）
const NOT_BMCP = /^mcp:(?!bmcp\/)/;
const NOT_AEMCP = /^mcp:(?!aemcp\/)/;

export default [
  // ─── Windows / Git Bash ───────────────────────────────
  {
    id: 'python-inline-backslash',
    severity: 'block',
    tool: 'bash',
    when: /\bpython[0-9.]*(?:\.exe)?\s+(?:-\s*<<|-c\s)[\s\S]*\\/,
    message:
      'シェルに埋め込んだ Python にバックスラッシュがあります。\\r\\n \\b \\P などが実改行や制御文字に化け、' +
      'ファイルやパスを壊します。Write ツールで scratchpad に .py を書き、`python <パス>` で実行してください。',
    ref: 'rules/traps/windows-shell.md#シェルに-python-を埋め込まない',
    examples: {
      hit: [`python - <<'EOF'\ns = s.replace('\\r\\n', '\\n')\nEOF`, `python -c "open('D:\\\\a\\\\b.txt')"`],
      miss: [`python -c "print(1)"`, `python scratch/fix.py`],
    },
  },
  {
    id: 'heredoc-unquoted-backslash',
    severity: 'warn',
    tool: 'bash',
    when: /<<-?[ \t]*(?!['"\\])(\w+)(?!\w)[^\n]*\n(?:(?!^\1$)[\s\S])*?\\\\/m,
    message:
      '引用符なしの heredoc（`<<EOF`）の中では `\\\\` が `\\` に潰れ、`\\$` も展開されます。書き出したコードやパスが壊れています。' +
      '`<<\'EOF\'` と引用符を付けるか、Write ツールでファイルに書き直してください。',
    ref: 'rules/traps/windows-shell.md#シェルに-python-を埋め込まない',
    examples: {
      hit: [`cat > a.js <<EOF\nconst p = s.split('\\\\');\nEOF`, `node - <<JS\nconsole.log('a\\\\b')\nJS`],
      miss: [`cat > a.js <<'EOF'\nconst p = s.split('\\\\');\nEOF`, `cat <<EOF\nhello\nEOF`],
    },
  },
  {
    id: 'cmd-start-msys',
    severity: 'block',
    tool: 'bash',
    when: /\bcmd(?:\.exe)?\s+\/\/c\s+start\b/i,
    message:
      'Git Bash から `cmd //c start ... cmd /k` で起動すると、MSYS のパス変換で /k が K:/ に化け、' +
      'ウィンドウだけ開いてコマンドが実行されません。PowerShell の Start-Process を使ってください ' +
      '(`powershell -NoProfile -Command "Start-Process cmd -ArgumentList \'/k\',\'...\'"`)。',
    ref: 'rules/traps/windows-shell.md#git-bash-から-cmd-を起動しない',
    examples: {
      hit: [`cmd //c start "" cmd /k "cd /d D:\\x && claude"`],
      miss: [`powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/k','claude'"`, `cmd //c "dir"`],
    },
  },
  {
    id: 'win-cmd-slash-msys',
    severity: 'block',
    tool: 'bash',
    when: /(?:^|[;&|(]\s*)(?:schtasks|powercfg|taskkill)(?:\.exe)?\s+(?:[^\n;&|]*\s)?\/[A-Za-z?]/m,
    unless: /MSYS_NO_PATHCONV=1|MSYS2_ARG_CONV_EXCL|\bpowershell(?:\.exe)?\b|\bpwsh\b|\bcmd(?:\.exe)?\s+\/\/c\b/i,
    message:
      'Git Bash では `/Create` `/PID` `/F` のような `/` 始まりの引数が MSYS のパス変換で `C:/Program Files/Git/...` や `F:/` に書き換わり、' +
      'schtasks / powercfg / taskkill が壊れます。先頭に `MSYS_NO_PATHCONV=1` を付けるか、`//PID` のように `//` で始めるか、PowerShell 経由で呼んでください。',
    ref: 'rules/traps/windows-shell.md#git-bash-の-msys-パス変換',
    examples: {
      hit: ['taskkill /F /PID 1234', 'schtasks /Create /TN foo /TR "node x.js" /SC ONLOGON', 'cd x && powercfg /change monitor-timeout-ac 0'],
      miss: ['MSYS_NO_PATHCONV=1 schtasks /Query /TN foo', 'taskkill //F //PID 1234', 'powershell -NoProfile -Command "taskkill /F /PID 1234"', 'grep -n "taskkill /F" notes.md'],
    },
  },
  {
    id: 'osc-address-msys',
    severity: 'block',
    tool: 'bash',
    when: /osc[\w.-]*\s[^|;&\n]*\s['"]?\/[A-Za-z][\w-]*\//i,
    unless: /MSYS_NO_PATHCONV=1/,
    message:
      '`/` で始まる OSC アドレスを Git Bash から引数で渡すと、MSYS が C:/Program Files/Git/... に書き換えます。' +
      '送信は成功するので受信側が黙って反応しません。コマンドの先頭に `MSYS_NO_PATHCONV=1` を付けてください。',
    ref: 'rules/traps/protocol.md#git-bash-から-osc-アドレスを渡す',
    examples: {
      hit: ['python tools/osc_send.py 127.0.0.1 9000 /pianokey/L002 1', 'oscsend localhost 9000 /cinecam/position/1 f 0.5'],
      miss: ['MSYS_NO_PATHCONV=1 python tools/osc_send.py 127.0.0.1 9000 /pianokey/L002 1', 'ls /d/_Personal/Project/OSC2MIDI/src'],
    },
  },
  {
    id: 'curl-data-non-ascii',
    severity: 'warn',
    tool: 'bash',
    when: /\bcurl\b[^\n]*\s(?:-d|--data(?:-raw|-urlencode)?)(?:\s+|=)['"][^\n]*[^\x00-\x7F]/,
    message:
      'Git Bash の curl に日本語をリテラルで渡すと CP932 に化けて送られ、サーバ側の不具合に見えます。' +
      'JSON をファイルにして `--data-binary @file` で渡すか、node の fetch をスクリプトファイルで実行してください。',
    ref: 'rules/traps/windows-shell.md#git-bash-の-curl-で日本語を送ると化ける',
    examples: {
      hit: [`curl -X POST -d '{"name":"山田"}' http://localhost/api`, `curl --data='{"t":"テスト"}' http://x`],
      miss: ['curl --data-binary @body.json http://x', 'curl -H "X-Name: テスト" http://x', `curl -d '{"a":1}' http://x`],
    },
  },
  {
    id: 'bare-pip-install',
    severity: 'warn',
    tool: 'bash',
    when: /(?:^|[;&|]\s*)pip3?(?:\.exe)?\s+install\b/m,
    message:
      'この PC では `pip` と `python` が別の Python を指しており（pip = AppData の Python、python = rye）、入れたのに import できません。' +
      '`python -m pip install ...` か `uv add` / `uv run` を使ってください（venv を activate 済みなら問題ない）。',
    ref: 'rules/traps/windows-shell.md#pip-と-python-が別の-python',
    examples: {
      hit: ['pip install opencv-python', 'cd tools && pip install -r requirements.txt'],
      miss: ['python -m pip install opencv-python', 'uv pip install numpy', 'echo "run pip install x"'],
    },
  },
  {
    id: 'powershell-command-stdin',
    severity: 'warn',
    tool: 'shell',
    when: /\bpowershell(?:\.exe)?\b[^\n]*\s-Command\s+-(?:\s|$)/im,
    message:
      'PowerShell を `-Command -`（標準入力）で呼ぶと、複数行のパイプラインが出力なし・終了コード 0 で黙って捨てられます。' +
      '`-EncodedCommand <UTF-16LE の base64>` で渡すか、.ps1 に書いて `-File` で実行してください。',
    ref: 'rules/traps/windows-shell.md#powershell-を--command---で呼ばない',
    examples: {
      hit: ['echo "$script" | powershell -NoProfile -Command -'],
      miss: ['powershell -NoProfile -Command "Get-Process"', 'powershell -NoProfile -Command -Name'],
    },
  },
  {
    id: 'powershell-command-stdin-code',
    severity: 'warn',
    tool: 'edit',
    files: /\.(?:[cm]?[jt]sx?|py|go|rs|cs)$/i,
    when: /['"]-Command['"]\s*,\s*['"]-['"]/,
    message:
      'PowerShell を `-Command -`（標準入力）で起動するコードです。複数行のパイプラインが出力なし・終了コード 0 で黙って捨てられます。' +
      '`-EncodedCommand <UTF-16LE の base64>` で渡してください。',
    ref: 'rules/traps/windows-shell.md#powershell-を--command---で呼ばない',
    examples: {
      hit: [['src/run.ts', "spawn('powershell.exe', ['-NoProfile', '-Command', '-'])"], ['tools/a.py', '["powershell", "-NoProfile", "-Command", "-"]']],
      miss: [['src/run.ts', "spawn('powershell.exe', ['-NoProfile', '-Command', script])"], ['src/run.ts', "['-NoProfile', '-EncodedCommand', b64]"]],
    },
  },

  // ─── プロセス操作 ─────────────────────────────────────
  {
    id: 'kill-unity',
    severity: 'block',
    tool: 'shell',
    when: /\b(?:taskkill\b[^\n]*unity|stop-process\b[^\n]*unity|kill\s+-9?\s*[^\n]*unity)/i,
    message:
      'Unity を強制終了すると Library の書き戻しが飛び、次回起動が遅くなります。' +
      '`(Get-Process -Id <pid>).CloseMainWindow()` で正常終了させてください（タイトルの * で未保存を先に確認）。',
    ref: 'rules/traps/unity-editor.md#unity-を強制終了しない',
    examples: {
      hit: ['taskkill //F //IM Unity.exe', 'powershell -Command "Stop-Process -Name Unity -Force"'],
      miss: ['powershell -Command "(Get-Process -Id 1234).CloseMainWindow()"', 'taskkill //F //IM node.exe'],
    },
  },
  {
    id: 'taskkill-im-without-tree',
    severity: 'warn',
    tool: 'shell',
    when: /\btaskkill\b(?![^\n]*\s\/{1,2}T\b)[^\n]*\s\/{1,2}IM\s/i,
    message:
      '`/T` 無しの `taskkill /IM` は子プロセスを残します（WebView2 の msedgewebview2.exe が EBWebView をロックしたまま、shim の先の ffmpeg がパイプを握ったまま）。' +
      '残っていないか確かめ、`/T` を付けてツリーごと止めてください。',
    ref: 'rules/traps/process.md#kill-してもツリーの本体が残る',
    examples: {
      hit: ['taskkill //F //IM sequence.exe'],
      miss: ['taskkill //F //T //IM app.exe', 'taskkill //F //PID 1234'],
    },
  },
  {
    id: 'kill-by-commandline-without-name',
    severity: 'warn',
    tool: 'shell',
    when: /CommandLine\s+-(?:i?like|match)\b[\s\S]*(?:Stop-Process|taskkill|Terminate|\.Kill\(\))/i,
    unless: /Name\s*=\s*'|Name\s*=\s*\\?"|-Name\s|\.Name\s+-(?:eq|like)|ProcessName|-Filter\s+["']Name/i,
    message:
      'コマンドラインの部分一致だけでプロセスを止めると、同じ構成の他プロジェクトのデーモンや MCP サーバー、絞り込み文字列を引数に持つ自分のシェルまで止まります。' +
      '巻き添えが出ていないか確かめ、次からはプロセス名（`-Filter "Name=\'node.exe\'"`）とプロジェクト名を含む絶対パスの両方で絞り、対象を列挙してから止めてください。',
    ref: 'rules/traps/process.md#コマンドラインの部分一致でプロセスを落とさない',
    examples: {
      hit: [
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server\\dist\\index.js*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
        "Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'run-hidden' } | Invoke-CimMethod -MethodName Terminate",
      ],
      miss: [
        `Get-CimInstance Win32_Process -Filter "Name='node.exe'" | ? { $_.CommandLine -like '*SessionControl*' } | % { Stop-Process -Id $_.ProcessId }`,
        "Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*dist*' } | Select ProcessId,CommandLine",
      ],
    },
  },
  {
    id: 'kill-by-window-title',
    severity: 'warn',
    tool: 'shell',
    when: /MainWindowTitle[\s\S]*(?:Stop-Process|CloseMainWindow|\.Kill\(\)|taskkill)/i,
    unless: /StartTime/i,
    message:
      'ウィンドウタイトルだけでプロセスを同定して閉じました。WindowsTerminal は前面タブのタイトルを出すため、他プロジェクトのセッションを巻き添えにします。' +
      '巻き添えが出ていないか確かめ、次からは `ProcessName` と `StartTime` を確かめてから閉じてください。',
    ref: 'rules/traps/process.md#ウィンドウタイトルで同定して閉じない',
    examples: {
      hit: ["Get-Process | ? { $_.MainWindowTitle -like '*Claude Code - lll*' } | Stop-Process", "(Get-Process | ? MainWindowTitle -match 'SinkaiFes').CloseMainWindow()"],
      miss: ['Get-Process | ? { $_.MainWindowTitle } | Select Id,ProcessName,MainWindowTitle', 'Get-Process -Id 42 | Select ProcessName,StartTime,MainWindowTitle; (Get-Process -Id 42).CloseMainWindow()'],
    },
  },

  // ─── git ────────────────────────────────────────────
  {
    id: 'git-commit-option-after-dashdash',
    severity: 'block',
    tool: 'bash',
    when: /\bgit\s+commit\b(?:(?!\s-[mF]\b)[^\n|;&])*\s--\s[^\n|;&]*\s-[mF]\b/,
    message:
      '`git commit` の `--` より後ろは全てパスとして扱われ、`-m` / `-F` が `pathspec \'-m\' did not match` で失敗します。' +
      '`git commit -F <msg> -- <paths>` の順に並べてください。',
    ref: 'traps-catalog/git.md',
    examples: {
      hit: ['git commit -- src/a.cs -m "fix"'],
      miss: ['git commit -m "fix" -- src/a.cs', 'git commit -m "fix -- use -m flag"', 'git commit -F msg.txt -- a b'],
    },
  },
  {
    id: 'lfs-migrate-without-checkout',
    severity: 'warn',
    tool: 'bash',
    when: /\bgit\s+lfs\s+migrate\s+import\b/,
    unless: /\bgit\s+lfs\s+(?:checkout|pull)\b|--(?:dry-run|help)\b/,
    message:
      '`git lfs migrate import` は履歴を書き換えるだけで作業コピーを smudge しません。そのままだと Unity がポインタファイルを読んで壊れます。' +
      '続けて `git lfs checkout` を実行してください（.meta は LFS に入れない）。',
    ref: 'rules/traps/git.md#lfs-migrate-の後は-checkout',
    examples: {
      hit: ['git lfs migrate import --include="*.vrm" --everything'],
      miss: ['git lfs migrate import --include="*.vrm" --everything && git lfs checkout', 'git lfs migrate info'],
    },
  },
  {
    id: 'gitignore-unanchored-source-dir',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)\.gitignore$/,
    when: /^(?:tools|src|scripts)\/[ \t]*$/m,
    message:
      '`.gitignore` の `tools/` のように先頭 `/` の無いディレクトリは全階層に当たり、`server/src/tools/` のようなソースまで黙って無視されます。' +
      'ルート直下だけなら `/tools/` と書き、`git check-ignore -v <path>` で確かめてください。',
    ref: 'rules/traps/git.md#gitignore-は先頭--で固定する',
    examples: {
      hit: [['.gitignore', 'tools/'], ['.gitignore', 'node_modules/\nscripts/']],
      miss: [['.gitignore', '/tools/'], ['.gitignore', 'build/'], ['.gitignore', 'server/tools/']],
    },
  },
  {
    id: 'gitignore-tilde',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /(?:^|\/)\.gitignore$/,
    when: /^\*~[ \t]*$/m,
    unless: /^!\*~\/[ \t]*$/m,
    message:
      '`.gitignore` の `*~` は Unity の隠しフォルダ（UPM パッケージの `Server~` / `Samples~`）にも当たり、コミットされません。' +
      'Unity のパッケージを含むなら `!*~/` を足してください。',
    ref: 'traps-catalog/git.md',
    examples: {
      hit: [['.gitignore', '*.swp\n*~']],
      miss: [['.gitignore', '*~\n!*~/'], ['.gitignore', '*.bak']],
    },
  },

  // ─── Claude Code ─────────────────────────────────────
  {
    id: 'claude-launch-no-remote-control',
    severity: 'block',
    tool: 'shell',
    when: /(?:Start-Process|\/k['"]?\s*,|&&|^)\s*[^\n]*?\bclaude(?:\.exe)?\s+(?:--continue|--resume|-c\b|--bg\b|--session-id|--name)/m,
    unless: /--remote-control|\b(?:grep|rg|Select-String)\b[^\n]*\bclaude(?:\.exe)?\s+--/,
    message:
      'claude を --remote-control 無しで起動しようとしています。付け忘れると他デバイスから触れません。' +
      '`--remote-control=<プロジェクト名>` を付けてください。起動前に `Get-CimInstance Win32_Process -Filter "Name=\'claude.exe\'"` の CommandLine で、既に付いたセッションが無いかも見ること。',
    ref: 'rules/traps/claude-code.md#セッションから起動した-claude-が一覧に出ない',
    examples: {
      hit: [`powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/k','cd /d D:\\x && claude --continue'"`, 'claude --bg --name foo'],
      miss: [
        `powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/k','cd /d D:\\x && claude --continue --remote-control=x'"`,
        'claude mcp add -s user foo -- node a.js',
        'grep -rn "claude --continue" ~/.claude/CLAUDE.md',
        'claude -p --model haiku "hello"',
      ],
    },
  },
  {
    id: 'claude-bg-resume',
    severity: 'warn',
    tool: 'shell',
    when: /\bclaude(?:\.exe)?\s+(?:[^\n|;&]*\s)?--bg\b[^\n|;&]*\s--resume\b|\bclaude(?:\.exe)?\s+(?:[^\n|;&]*\s)?--resume\b[^\n|;&]*\s--bg\b/,
    message:
      '`claude --bg --resume <id>` は会話を引き継がず新しい ID を採番します（2.1.270 実測）。' +
      '同じセッションを起こし直すなら `claude respawn <短縮ID>`（ID・会話・Remote Control URL を据え置き）を使ってください。',
    ref: 'rules/traps/claude-code.md#セッションから起動した-claude-が一覧に出ない',
    examples: {
      hit: ['claude --resume abc --bg --remote-control=x'],
      miss: ['claude respawn 1234abcd', 'claude --bg --remote-control=SessionControl'],
    },
  },
  {
    id: 'claudelog-under-dotclaude',
    severity: 'warn',
    tool: 'shell',
    when: /(?:>>?|\btee\b(?:\s+-a)?)\s*['"]?[^\s'"|;&]*\.claude[\\/]claudeLog\.txt/,
    unless: /\bgit\s+mv\b/,
    message:
      'claudeLog を .claude/ 配下へ書いています。.claude/ への書き込みは許可ルールでも hook でも毎回確認が出ます。' +
      '`log/claudeLog.txt` へ追記してください（既存の .claude/claudeLog.txt は git mv で log/ へ移す）。',
    ref: 'rules/traps/claude-code.md#claudelog-を-claude-配下に置かない',
    examples: {
      hit: [`printf '%s\\n' 'x' >> .claude/claudeLog.txt`, 'echo x | tee -a .claude\\claudeLog.txt'],
      miss: [`printf '%s\\n' 'x' >> log/claudeLog.txt`, 'git mv .claude/claudeLog.txt log/claudeLog.txt', 'tail -200 .claude/claudeLog.txt'],
    },
  },
  {
    id: 'claudelog-under-dotclaude-edit',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)\.claude\/claudeLog\.txt$/i,
    when: ANY,
    message:
      'claudeLog を .claude/ 配下に書いています。.claude/ への書き込みは毎回確認が出ます。`log/claudeLog.txt` へ移してください（追跡中なら git mv）。',
    ref: 'rules/traps/claude-code.md#claudelog-を-claude-配下に置かない',
    examples: {
      hit: [['app/.claude/claudeLog.txt', 'x']],
      miss: [['app/log/claudeLog.txt', 'x']],
    },
  },
  {
    id: 'mcp-json-in-dotclaude',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)\.claude\/\.mcp\.json$/i,
    when: ANY,
    message:
      '.claude/ フォルダの中の .mcp.json は読まれません（user スコープの実体は ~/.claude.json、.mcp.json はプロジェクトルート専用）。' +
      '`claude mcp add -s user <name> -- <cmd>`（または -s project）で登録し、`claude mcp list` で確かめてから再起動してください。',
    ref: 'rules/traps/claude-code.md#mcp-を登録したのにツールが出ない',
    examples: {
      hit: [['app/.claude/.mcp.json', '{}']],
      miss: [['app/.mcp.json', '{}']],
    },
  },
  {
    id: 'settings-mcpservers',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)\.claude\/settings(?:\.local)?\.json$/i,
    when: /"mcpServers"\s*:/,
    message:
      'settings.json に mcpServers フィールドはありません（書いても MCP は登録されない）。' +
      '`claude mcp add` で登録し、プロジェクトの .mcp.json を使うなら settings.local.json の enabledMcpjsonServers に名前を足してください。',
    ref: 'rules/traps/claude-code.md#mcp-を登録したのにツールが出ない',
    examples: {
      hit: [['app/.claude/settings.local.json', '{ "mcpServers": { "x": {} } }']],
      miss: [['app/.claude/settings.local.json', '{ "enabledMcpjsonServers": ["x"] }']],
    },
  },
  {
    id: 'mcp-unity-url-fixed',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)\.mcp\.json$/i,
    when: /"MCP_UNITY_HTTP_URL"\s*:/,
    message:
      '.mcp.json で MCP_UNITY_HTTP_URL を固定すると endpoint.json による自動解決より優先され、' +
      '同じポートを持つ別プロジェクトの Unity に正常応答のまま繋がります。unity-mcp v1.5.0 以降では書かずに自動解決に任せてください。',
    ref: 'rules/traps/mcp-external.md#mcp-は正常応答でも別プロジェクトに繋がっている',
    examples: {
      hit: [['proj/.mcp.json', '"env": { "MCP_UNITY_HTTP_URL": "http://localhost:8090" }']],
      miss: [['proj/.mcp.json', '"env": { "UNITY_PROJECT": "x" }']],
    },
  },
  {
    id: 'wrangler-secret-put-no-stdin',
    severity: 'block',
    tool: 'shell',
    when: /\bwrangler\s+secret\s+put\s+[A-Za-z_][\w-]*(?:\s+--?[\w-]+(?:[= ][^\s|;&<]+)?)*\s*(?:$|&&|;|\|\|)/m,
    unless: /\|\s*(?:npx\s+|pnpm\s+(?:exec\s+|dlx\s+)?|bunx\s+)?wrangler\s+secret\s+put|wrangler\s+secret\s+put[^\n|;&]*<|wrangler\s+secret\s+bulk/,
    message:
      'Claude Code のシェルは非対話で stdin が空です。wrangler secret put を値なしで実行すると、空文字のシークレットが「Success」で登録されます。' +
      '`printf %s "$VALUE" | npx wrangler secret put NAME` のようにパイプで値を渡してください。',
    ref: 'rules/traps/claude-code.md#claude-code-のシェルは非対話',
    examples: {
      hit: ['npx wrangler secret put API_KEY', 'cd api && npx wrangler secret put TOKEN --env production && npx wrangler deploy'],
      miss: ['echo -n "$KEY" | npx wrangler secret put API_KEY', 'npx wrangler secret put API_KEY < key.txt', 'npx wrangler secret list'],
    },
  },
  {
    id: 'stdio-mcp-echo-pipe',
    severity: 'warn',
    tool: 'bash',
    when: /\becho\s+(?:-[a-z]+\s+)?(['"])[^\n]*?jsonrpc[^\n]*?\1\s*\|\s*(?!.*\bsleep\b)\S/,
    unless: /\(\s*echo\b[^)]*;\s*sleep\b/,
    message:
      'stdio MCP サーバーに echo でパイプすると、echo が即 stdin を閉じてサーバーが応答前に終了します（応答が返らないのはそのため）。' +
      '`(echo \'...\'; sleep 3) | server` で stdin を保持するか、クライアントスクリプトで叩いてください。',
    ref: 'traps-catalog/claude-code.md',
    examples: {
      hit: [`echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node dist/index.js`],
      miss: [`(echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'; sleep 3) | node dist/index.js`, `echo '{"jsonrpc":"2.0"}' > req.json`],
    },
  },

  // ─── Unity (C#) ──────────────────────────────────────
  {
    id: 'cs-culture-string-compare',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /\.(?:StartsWith|EndsWith)\((?![^()\n]*StringComparison)[^()\n]*\)|\.IndexOf\(\s*(?:"[^"]*"|\$"[^"]*")\s*\)/,
    message:
      'StartsWith / EndsWith / IndexOf(string) に StringComparison.Ordinal がありません。' +
      '既定はカルチャ依存比較で、Unity の Mono では呼ぶたびにヒープを確保します（受信ハンドラや Update では GC スパイクの元）。' +
      '`StringComparison.Ordinal` を付けてください。',
    ref: 'rules/traps/unity-gc.md#文字列比較に-ordinal-を付ける',
    examples: {
      hit: [['Assets/A.cs', 'if (addr.StartsWith("/cam")) return;'], ['Assets/A.cs', 'var i = s.IndexOf("/play/");']],
      miss: [['Assets/A.cs', 'if (addr.StartsWith("/cam", StringComparison.Ordinal)) return;'], ['Assets/A.cs', "var i = s.IndexOf('/');"], ['src/a.ts', 'if (s.startsWith("/cam")) {}']],
    },
  },
  {
    id: 'cs-getcomponent-null-coalesce',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /GetComponent(?:InChildren|InParent)?<[^>\n]+>\(\)\s*(?:\?\?|\?\.)/,
    message:
      'GetComponent の結果に ?? / ?. を使っています。Unity の偽 null は C# の null 判定を素通りし、' +
      '後で MissingComponentException になります。`TryGetComponent(out var c)` か `if (c == null)` にしてください。',
    ref: 'rules/traps/unity-runtime.md#getcomponent-に--を使わない',
    examples: {
      hit: [['Assets/A.cs', 'var r = GetComponent<Renderer>() ?? gameObject.AddComponent<Renderer>();'], ['Assets/A.cs', 'GetComponentInChildren<Animator>()?.Play("x");']],
      miss: [['Assets/A.cs', 'if (TryGetComponent(out Renderer r)) {}']],
    },
  },
  {
    id: 'cs-gc-alloc-thread-stub',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /GC\.GetAllocatedBytesForCurrentThread|GC\.GetTotalMemory/,
    message:
      'GC.GetAllocatedBytesForCurrentThread は Unity の Mono では常に 0 を返すスタブ、GC.GetTotalMemory は分解能が足りません。' +
      '「割り当て 0」という誤った結論になります。ProfilerRecorder(ProfilerCategory.Memory, "GC Allocated In Frame") で測ってください。',
    ref: 'rules/traps/unity-gc.md#gc-の測り方',
    examples: {
      hit: [['Assets/A.cs', 'long a = GC.GetAllocatedBytesForCurrentThread();']],
      miss: [['Assets/A.cs', 'var r = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame");']],
    },
  },
  {
    id: 'cs-runtime-unityeditor',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    exclude: /\/Editor\/|\/Editor[^/]*\//i,
    when: /^\s*using\s+UnityEditor\b/m,
    unless: /#if\s+UNITY_EDITOR/,
    message:
      'Editor フォルダ外の .cs で using UnityEditor が #if UNITY_EDITOR に囲まれていません。' +
      'エディタのコンパイルは通りますが Player ビルドで落ちます。Editor 専用アセンブリへ移すか、using からクラス末尾までを #if UNITY_EDITOR で囲んでください' +
      '（asmdef が Editor 限定なら問題ありません。その場合は無視してよい）。',
    ref: 'rules/traps/unity-build.md#player-ビルドを壊さない',
    examples: {
      hit: [['Assets/Scripts/A.cs', 'using UnityEditor;\nusing UnityEngine;\npublic class A : MonoBehaviour {}']],
      miss: [['Assets/Scripts/B.cs', '#if UNITY_EDITOR\nusing UnityEditor;\n#endif\npublic class B {}'], ['Assets/Editor/C.cs', 'using UnityEditor;\npublic class C : Editor {}']],
    },
  },
  {
    id: 'cs-codice-using',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /^\s*using\s+Codice\./m,
    message:
      'using Codice.* は Plastic SCM の Editor 専用型で、IDE の自動 using で紛れ込みます。Player ビルドが落ちるので消してください。',
    ref: 'rules/traps/unity-build.md#player-ビルドを壊さない',
    examples: {
      hit: [['Assets/A.cs', 'using Codice.CM.Common;']],
      miss: [['Assets/A.cs', 'using System.Collections;']],
    },
  },
  {
    id: 'cs-editor-namespace-clash',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    when: /namespace\s+vortex\.EditorTools[\s\S]*:\s*Editor\s*(?:\{|$|,)/m,
    message:
      'namespace vortex.EditorTools の中で `: Editor` と書くと、vortex.Editor 名前空間に解決されて CS0118 になります。' +
      '`: UnityEditor.Editor` と完全修飾してください。',
    ref: 'rules/traps/unity-editor.md#vortexeditortools-で-editor-を継承する',
    examples: {
      hit: [['Assets/Editor/D.cs', 'namespace vortex.EditorTools {\n  public class D : Editor {\n  }\n}']],
      miss: [['Assets/Editor/E.cs', 'namespace vortex.EditorTools {\n  public class E : UnityEditor.Editor {\n  }\n}']],
    },
  },

  // ─── Tauri / Rust ────────────────────────────────────
  {
    id: 'tauri-sync-command',
    severity: 'warn',
    tool: 'edit',
    files: /\.rs$/i,
    when: /#\[tauri::command[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?fn\s/,
    message:
      '同期の Tauri コマンド（fn）はウェブビューの IPC ハンドラ = UI スレッドで走り、待つ間は画面ごと固まります。' +
      '入力量に比例して伸びうる処理なら `async fn` + `tauri::async_runtime::spawn_blocking` にしてください（一瞬で終わる getter ならそのままでよい）。',
    ref: 'rules/traps/tauri.md#同期コマンドは-ui-スレッドで走る',
    examples: {
      hit: [['src-tauri/src/commands.rs', '#[tauri::command]\npub fn export_all(state: State<App>) -> Result<(), String> {'], ['src-tauri/src/commands.rs', '#[tauri::command(rename_all = "snake_case")]\nfn scan() {}']],
      miss: [['src-tauri/src/commands.rs', '#[tauri::command]\npub async fn export_all() -> Result<(), String> {']],
    },
  },

  {
    id: 'tauri-signing-key-path',
    severity: 'block',
    tool: 'shell',
    when: /\bTAURI_SIGNING_PRIVATE_KEY_PATH\b/,
    unless: /^\s*(?:grep|rg|git\s+grep|Select-String|findstr)\b/,
    message:
      '`TAURI_SIGNING_PRIVATE_KEY_PATH` は tauri-cli に読まれず、"A public key has been found, but no private key" で署名されません。' +
      '`TAURI_SIGNING_PRIVATE_KEY=<鍵のパス>` を使ってください（パスでも中身でも可）。パスワード無しの鍵でも `TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""` が無いと対話待ちで止まります。',
    ref: 'rules/traps/tauri.md#updater-の鍵の環境変数',
    examples: {
      hit: ['TAURI_SIGNING_PRIVATE_KEY_PATH=~/.tauri/sh.key npm run tauri build', '$env:TAURI_SIGNING_PRIVATE_KEY_PATH="C:\\keys\\sh.key"; npm run tauri build'],
      miss: ['TAURI_SIGNING_PRIVATE_KEY=~/.tauri/sh.key TAURI_SIGNING_PRIVATE_KEY_PASSWORD="" npm run tauri build', 'grep -rn TAURI_SIGNING_PRIVATE_KEY_PATH scripts/'],
    },
  },
  {
    id: 'tauri-signing-key-path-edit',
    severity: 'warn',
    tool: 'edit',
    files: /\.(?:bat|cmd|sh|command|ps1|ya?ml|mjs|js)$/i,
    when: /\bTAURI_SIGNING_PRIVATE_KEY_PATH\b/,
    message:
      '`TAURI_SIGNING_PRIVATE_KEY_PATH` は tauri-cli に読まれず、署名されません。`TAURI_SIGNING_PRIVATE_KEY=<鍵のパス>` にし、' +
      'パスワード無しの鍵でも `TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""` を渡してください（無いと対話待ちで止まる）。',
    ref: 'rules/traps/tauri.md#updater-の鍵の環境変数',
    examples: {
      hit: [['build-win.bat', 'set TAURI_SIGNING_PRIVATE_KEY_PATH=%USERPROFILE%\\.tauri\\sh.key'], ['build-mac.command', 'export TAURI_SIGNING_PRIVATE_KEY_PATH="$HOME/.tauri/sh.key"']],
      miss: [['build-win.bat', 'set TAURI_SIGNING_PRIVATE_KEY=%USERPROFILE%\\.tauri\\sh.key'], ['build-win.bat', 'set CI=true']],
    },
  },
  {
    id: 'tauri-custom-protocol-missing',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /(?:^|\/)src-tauri\/Cargo\.toml$/i,
    when: /^\s*(?:tauri\s*=|\[dependencies\.tauri\])/m,
    unless: /custom-protocol/,
    message:
      'src-tauri/Cargo.toml に `custom-protocol` フィーチャがありません。無いと `is_dev()` が真になり、`cargo build --release` した exe でも devUrl を読みに行き、' +
      'そのポートで動いている別プロジェクトの画面が出ます。`[features] default = ["custom-protocol"]` と `custom-protocol = ["tauri/custom-protocol"]` を足してください。',
    ref: 'rules/traps/tauri.md#別プロジェクトの画面が出る',
    examples: {
      hit: [['src-tauri/Cargo.toml', '[dependencies]\ntauri = { version = "2", features = [] }'], ['src-tauri/Cargo.toml', '[dependencies.tauri]\nversion = "2"']],
      miss: [
        ['src-tauri/Cargo.toml', '[dependencies]\ntauri = { version = "2" }\n[features]\ndefault = ["custom-protocol"]\ncustom-protocol = ["tauri/custom-protocol"]'],
        ['src-tauri/Cargo.toml', '[dependencies]\nserde = "1"'],
      ],
    },
  },
  {
    id: 'tauri-devurl-1420',
    severity: 'warn',
    tool: 'edit',
    files: /(?:tauri\.conf\.json|vite\.config\.[cm]?[jt]s)$/i,
    when: /"devUrl"\s*:\s*"https?:\/\/(?:localhost|127\.0\.0\.1):1420\/?"|\bport\s*:\s*1420\b/,
    message:
      'Tauri の既定ポート 1420 は全プロジェクト共通で、先に動いている別プロジェクトの Vite に繋がり別アプリの画面が出ます。' +
      'プロジェクト固有のポートにし、vite.config の `strictPort: true` と tauri.conf.json の devUrl を揃えてください。',
    ref: 'rules/traps/tauri.md#別プロジェクトの画面が出る',
    examples: {
      hit: [['src-tauri/tauri.conf.json', '"build": { "devUrl": "http://localhost:1420" }'], ['vite.config.ts', 'server: { port: 1420, strictPort: true }']],
      miss: [['src-tauri/tauri.conf.json', '"devUrl": "http://localhost:1437"'], ['vite.config.ts', 'server: { port: 14200, strictPort: true, hmr: { port: 1421 } }']],
    },
  },
  {
    id: 'tauri-log-under-src-tauri',
    severity: 'warn',
    tool: 'edit',
    files: /\.rs$/i,
    when: /current_dir\(\)\s*(?:\?|\.unwrap\(\)|\.expect\([^)]*\))?\s*\.join\(\s*"logs?"|env!\(\s*"CARGO_MANIFEST_DIR"\s*\)\s*\)?\s*\.join\(\s*"logs?"/,
    message:
      '`tauri dev` の作業ディレクトリ（と CARGO_MANIFEST_DIR）は src-tauri で、そこへログを書くと dev の監視が拾ってアプリが再起動し、開いては閉じるを繰り返します。' +
      'dev は `package.json` を上方向に探したプロジェクトルート/log、配布 exe は exe の隣の log へ書いてください。',
    ref: 'rules/traps/tauri.md#src-tauri-配下へ実行時生成物を書かない',
    examples: {
      hit: [['src-tauri/src/log.rs', 'let dir = std::env::current_dir()?.join("log");'], ['src-tauri/src/log.rs', 'let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("log");']],
      miss: [['src-tauri/src/log.rs', 'let dir = find_project_root(std::env::current_dir()?)?.join("log");'], ['src-tauri/src/log.rs', 'let dir = exe_dir.join("log");']],
    },
  },
  {
    id: 'tauri-opener-scope-empty',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)capabilities\/[^/]+\.json$/i,
    when: /(?<!"identifier"\s*:\s*)"opener:allow-(?:open-path|reveal-item-in-dir)"\s*[,\]]/,
    message:
      '`"opener:allow-open-path"` を文字列だけで書くとパスのスコープが空で、すべて "Not allowed to open path" になります。' +
      '`{ "identifier": "opener:allow-open-path", "allow": [{ "path": "**" }] }` とスコープ付きで書いてください（capability はビルド時に組み込まれるので再ビルドが要る）。',
    ref: 'rules/traps/tauri.md#webview-の既定挙動が効かない',
    examples: {
      hit: [['src-tauri/capabilities/default.json', '"permissions": ["core:default", "opener:allow-open-path"]'], ['src-tauri/capabilities/default.json', '  "opener:allow-reveal-item-in-dir",']],
      miss: [['src-tauri/capabilities/default.json', '{ "identifier": "opener:allow-open-path", "allow": [{ "path": "**" }] }'], ['src-tauri/capabilities/default.json', '"opener:default"']],
    },
  },
  {
    id: 'tauri-identifier-dot-app',
    severity: 'warn',
    tool: 'edit',
    files: /tauri\.conf\.json$/i,
    when: /"identifier"\s*:\s*"[^"]*\.app"/,
    message:
      'identifier が `.app` で終わると macOS のバンドル拡張子と衝突して警告が出ます。新規なら `jp.<組織>.<アプリ名>` にしてください。' +
      '既存アプリの identifier を変えると利用者の設定とウィンドウ位置が消えるので、既存は据え置きます。',
    ref: 'rules/traps/tauri.md#identifier-を変えると利用者の設定が消える',
    examples: {
      hit: [['src-tauri/tauri.conf.json', '"identifier": "com.signalhub.app"'], ['src-tauri/tauri.conf.json', '"identifier":"jp.aiacats.ftpdeck.app",']],
      miss: [['src-tauri/tauri.conf.json', '"identifier": "jp.aiacats.signalhub"'], ['src-tauri/tauri.conf.json', '"identifier": "jp.aiacats.appstore"']],
    },
  },
  {
    id: 'rust-channel-receiver-dropped',
    severity: 'warn',
    tool: 'edit',
    files: /\.rs$/i,
    when: /let\s*\(\s*(?:mut\s+)?\w+\s*,\s*_\w*\s*\)\s*=\s*(?:[\w:]+::)?(?:channel|unbounded_channel|sync_channel|bounded|unbounded)\s*(?:::<[^>]*>)?\s*\(/,
    message:
      'チャネルの受信側を `_` / `_rx` で受けています。誰も読まないチャネルへの送信は黙って捨てられ、「UI に何も届かない」という原因から遠い症状になります。' +
      '受信タスクを spawn して消費してください（意図的なら `trap-ok:rust-channel-receiver-dropped`）。',
    ref: 'rules/traps/rust.md#受け手のいない-channel',
    examples: {
      hit: [['src/a.rs', 'let (tx, _frame_rx) = mpsc::channel(100);'], ['src/a.rs', 'let (tx, _) = tokio::sync::mpsc::unbounded_channel::<Frame>();']],
      miss: [['src/a.rs', 'let (tx, rx) = mpsc::channel(100);'], ['src/a.rs', 'let (_tx, rx) = std::sync::mpsc::channel::<u8>();']],
    },
  },
  {
    id: 'rust-try-recv-drain',
    severity: 'warn',
    tool: 'edit',
    files: /\.rs$/i,
    when: /while\s+(?:let\s+Ok\(\s*_\s*\)\s*=\s*)?[\w.]+\.try_recv\(\)(?:\.is_ok\(\))?\s*\{\s*\}/,
    message:
      '`try_recv` の空ループでチャネルを一括ドレインしています。「開始前の溜まり」だけでなく直後に届いたイベントまで捨てます（競合）。' +
      '到着時刻で選別してください（`arrival < epoch` なら捨てる）。',
    ref: 'rules/traps/rust.md#チャネルの作り直しと一括ドレイン',
    examples: {
      hit: [['src/a.rs', 'while rx.try_recv().is_ok() {}'], ['src/a.rs', 'while let Ok(_) = self.events.try_recv() { }']],
      miss: [['src/a.rs', 'while let Ok(ev) = rx.try_recv() { handle(ev); }'], ['src/a.rs', 'if rx.try_recv().is_ok() {}']],
    },
  },

  // ─── Web / Cloudflare ────────────────────────────────
  {
    id: 'wrangler-d1-write-target-unspecified',
    severity: 'block',
    tool: 'shell',
    when: /\bwrangler\s+d1\s+(?:migrations\s+apply\b|execute\b(?=[^\n]*\b(?:INSERT|UPDATE|DELETE|DROP|ALTER)\b))/i,
    unless: /--(?:remote|local)\b|--help\b|\s-h\b/,
    message:
      '`wrangler d1` の書き込み（migrations apply / execute の INSERT・UPDATE・DELETE・DROP・ALTER）で `--remote` / `--local` が指定されていません。' +
      '既定はローカル（miniflare）で、本番のつもりの変更が本番に入らず「成功」します。どちらに書くのかを `--remote` か `--local` で明示してください' +
      '（本番へ流すなら先に time-travel の復元点を控える）。',
    ref: 'rules/traps/web.md#wrangler-の既定の落とし穴',
    examples: {
      hit: ['npx wrangler d1 migrations apply shifter-db', 'npx wrangler d1 execute shifter-db --command "DELETE FROM sessions WHERE expired = 1"'],
      miss: [
        'npx wrangler d1 migrations apply shifter-db --remote',
        'npx wrangler d1 execute shifter-db --local --command "INSERT INTO t VALUES (1)"',
        'npx wrangler d1 execute shifter-db --command "SELECT updated_at FROM projects"',
      ],
    },
  },
  {
    id: 'wrangler-remote-local-unspecified',
    severity: 'warn',
    tool: 'shell',
    when: /\bwrangler\s+(?:r2\s+object\s+(?:get|put|delete)|d1\s+execute)\b/,
    unless: /--(?:remote|local)\b|--help\b/,
    message:
      '`wrangler r2 object` / `d1 execute` は既定でローカル（miniflare）を見ます。本番のつもりなら、今の結果はローカルのものです' +
      '（r2 object get は 0 バイトのファイルが「取れた」ように見える）。`--remote` か `--local` を明示してやり直してください。',
    ref: 'rules/traps/web.md#wrangler-の既定の落とし穴',
    examples: {
      hit: ['npx wrangler r2 object get shifter-backup/2026-08-15.sql --file out.sql', 'npx wrangler d1 execute shifter-db --command "SELECT count(*) FROM projects"'],
      miss: ['npx wrangler r2 object get shifter-backup/2026-08-15.sql --file out.sql --remote', 'npx wrangler d1 migrations apply shifter-db --local', 'npx wrangler r2 bucket list'],
    },
  },
  {
    id: 'drizzle-current-timestamp-literal',
    severity: 'warn',
    tool: 'edit',
    files: /\.[cm]?[jt]sx?$/i,
    when: /\.default\(\s*(["'`])\(?CURRENT_TIMESTAMP\)?\1\s*\)/,
    message:
      'Drizzle の `.default("CURRENT_TIMESTAMP")` は文字列リテラルとして保存され、列に "CURRENT_TIMESTAMP" という文字が入ります。' +
      '``.default(sql`(CURRENT_TIMESTAMP)`)`` にしてください。',
    ref: 'rules/traps/web.md#drizzle-の-default-に-current_timestamp-を文字列で渡さない',
    examples: {
      hit: [['src/db/schema.ts', '.notNull().default("CURRENT_TIMESTAMP"),'], ['src/db/schema.ts', ".default('(CURRENT_TIMESTAMP)'),"]],
      miss: [['src/db/schema.ts', '.notNull().default(sql`(CURRENT_TIMESTAMP)`),'], ['src/db/schema.ts', '.notNull().default(NOW),']],
    },
  },
  {
    id: 'cloudflare-vite-plugin-caret',
    severity: 'warn',
    tool: 'edit',
    files: /(?:^|\/)package\.json$/i,
    when: /"@cloudflare\/vite-plugin"\s*:\s*"\^/,
    message:
      '`@cloudflare/vite-plugin` を `^` で入れると 1.42 以降が入り、Node 22.15 未満では `npm run build` が `registerHooks` の SyntaxError で落ちます（この PC は 22.13）。' +
      '`1.40.2` に固定するか Node を上げてください。',
    ref: 'rules/traps/web.md#cloudflare-の-vite-plugin-を固定する',
    examples: {
      hit: [['package.json', '"@cloudflare/vite-plugin": "^1.43.0",'], ['package.json', '"@cloudflare/vite-plugin":"^1.40.2"']],
      miss: [['package.json', '"@cloudflare/vite-plugin": "1.40.2",'], ['package.json', '"@cloudflare/vitest-pool-workers": "^0.8.0",']],
    },
  },
  {
    id: 'js-empty-catch',
    severity: 'warn',
    tool: 'edit',
    files: /\.[cm]?[jt]sx?$/i,
    when: /\.catch\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*(?:\{\s*\}|undefined|null|void\s+0)\s*\)/,
    message:
      '失敗を空の `.catch` で捨てています。「押しても何も起きない」しか見えず、真因（権限・スコープ不足など）に辿り着けません。' +
      'トーストかログへ出してください（意図的なら `trap-ok:js-empty-catch`）。',
    ref: 'rules/traps/web.md#空の-catch-で失敗を握り潰さない',
    examples: {
      hit: [['src/App.tsx', 'openPath(p).catch(() => {});'], ['src/App.tsx', 'await save().catch((e) => { });']],
      miss: [['src/App.tsx', 'openPath(p).catch((e) => showToast(String(e)));'], ['src/App.tsx', 'await save().catch((e) => { log.error(e); });']],
    },
  },
  {
    id: 'hono-param-double-decode',
    severity: 'warn',
    tool: 'edit',
    files: /\.[cm]?[jt]sx?$/i,
    when: /decodeURIComponent\(\s*c\.req\.param\(/,
    message:
      'Hono の `c.req.param()` は既にデコード済みです。もう一度 `decodeURIComponent` すると `%` を含む名前で URIError → 500 になります。そのまま使ってください。',
    ref: 'traps-catalog/web.md#hono-の-param-は既にデコード済み二重-decodeuricomponent-で-500',
    examples: {
      hit: [['worker/routes.ts', 'const n = decodeURIComponent(c.req.param("name"));'], ['worker/routes.ts', "decodeURIComponent( c.req.param('id') )"]],
      miss: [['worker/routes.ts', 'const n = c.req.param("name");'], ['worker/routes.ts', 'decodeURIComponent(url.searchParams.get("q") ?? "")']],
    },
  },
  {
    id: 'react-usememo-today',
    severity: 'warn',
    tool: 'edit',
    files: /\.[cm]?[jt]sx?$/i,
    when: /useMemo\(\s*\(\)\s*=>\s*(?:new\s+Date\(\s*\)|\b(?:[a-z]\w*Today|today|now)\w*\([^)]*\)|Date\.now\(\))\s*,\s*\[\s*\]\s*\)/,
    message:
      '空依存の `useMemo` で「今日 / 今」を取ると初回マウント時の値に固定され、開いたまま日付をまたぐと更新されません。' +
      '次の 0 時の setTimeout + visibilitychange / focus で取り直すフックにしてください。',
    ref: 'traps-catalog/web.md#usememo--today--で日付が初回マウント時に固定される',
    examples: {
      hit: [['src/App.tsx', 'const today = useMemo(() => todayJst(), []);'], ['src/App.tsx', 'const now = useMemo(() => new Date(), []);']],
      miss: [['src/App.tsx', 'const today = useMemo(() => todayJst(), [tick]);'], ['src/App.tsx', 'const items = useMemo(() => knownItems(list), []);']],
    },
  },
  {
    id: 'js-showpicker-optional',
    severity: 'warn',
    tool: 'edit',
    files: /\.[cm]?[jt]sx?$/i,
    when: /\.showPicker\?\.\(\s*\)/,
    message:
      '`showPicker?.()` は未対応環境（スマホ）で例外も出さず何も起きません。透明な input を枠全面に重ね、タップの当たり先を input 自体にしてください。',
    ref: 'traps-catalog/web.md#showpicker-だけに頼ると未対応環境で黙って何も起きない',
    examples: {
      hit: [['src/DateField.tsx', 'inputRef.current?.showPicker?.();'], ['src/DateField.tsx', 'el.showPicker?.()']],
      miss: [['src/DateField.tsx', 'el.showPicker();'], ['src/DateField.tsx', 'if ("showPicker" in el) el.showPicker();']],
    },
  },
  {
    id: 'tsconfig-composite-noemit',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /(?:^|\/)tsconfig[^/]*\.json$/i,
    when: /^(?=[\s\S]*"composite"\s*:\s*true)(?=[\s\S]*"noEmit"\s*:\s*true)/,
    message:
      '`composite: true` と `noEmit: true` は同居できず TS6310 になります。noEmit を外し、出力先を `node_modules/.tmp` へ逃がしてください。',
    ref: 'traps-catalog/web.md#tsconfignodejson-に-noemit-を入れると-composite-と衝突するts6310',
    examples: {
      hit: [['tsconfig.node.json', '{ "compilerOptions": { "composite": true, "noEmit": true } }'], ['tsconfig.node.json', '{\n  "compilerOptions": {\n    "noEmit": true,\n    "composite": true\n  }\n}']],
      miss: [['tsconfig.node.json', '{ "compilerOptions": { "composite": true, "outDir": "node_modules/.tmp" } }'], ['tsconfig.json', '{ "compilerOptions": { "noEmit": true, "strict": true } }']],
    },
  },

  // ─── .NET ───────────────────────────────────────────
  {
    id: 'imgui-printf-format',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    // % を含まない文字列リテラルだけを渡す呼び出しは安全なので外す
    when: /\bImGui\.(?:Text|TextColored|TextWrapped|BulletText|SetTooltip|LabelText)\((?![^()\n]*(?<![$@\w])"[^"%\n\\{]*"\s*\)\s*;)/,
    message:
      'ImGui の Text / SetTooltip 系は渡した文字列を printf 書式として解釈し、`%` を含む値（ファイル名の %20 等）で化け、`%n` でプロセスが落ちます。' +
      'TextUnformatted ベースのラッパを通してください。',
    ref: 'rules/traps/dotnet.md#imgui-の-text-や-settooltip-は-printf-書式',
    examples: {
      hit: [['src/Ui.cs', 'ImGui.Text($"{pct}% done");'], ['src/Ui.cs', 'ImGui.SetTooltip(path);'], ['src/Ui.cs', 'ImGui.Text("50%");']],
      miss: [['src/Ui.cs', 'ImGui.TextUnformatted(label);'], ['src/Ui.cs', 'Gui.Text(label);'], ['src/Ui.cs', 'ImGui.Text("Hello");'], ['src/Ui.cs', 'ImGui.TextColored(red, "OK");']],
    },
  },
  {
    id: 'avalonia-subclass-stylekey',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    when: /^(?=[\s\S]*\busing\s+Avalonia\b)[\s\S]*\bclass\s+\w+\s*:\s*(?:TreeView|ListBox|Button|TextBox|ComboBox)\b/,
    unless: /StyleKeyOverride/,
    message:
      'Avalonia の既定テンプレートは型一致でしか当たらないので、TreeView などの派生クラスは何も描かれず、イベントも届きません。' +
      '`protected override Type StyleKeyOverride => typeof(<基底>);` を足してください。',
    ref: 'rules/traps/dotnet.md#avalonia-の派生コントロールは不可視になる',
    examples: {
      hit: [['src/SceneTree.cs', 'using Avalonia.Controls;\npublic class SceneTree : TreeView { }'], ['src/TrackList.cs', 'using Avalonia;\ninternal sealed class TrackList : ListBox { }']],
      miss: [
        ['src/SceneTree.cs', 'using Avalonia.Controls;\npublic class SceneTree : TreeView {\n  protected override Type StyleKeyOverride => typeof(TreeView);\n}'],
        ['src/RoundButton.cs', 'using System.Windows.Controls;\npublic class RoundButton : Button { }'],
      ],
    },
  },

  // ─── 共有（rclone / Drive） ──────────────────────────
  {
    id: 'rclone-link-gdrive',
    severity: 'block',
    tool: 'shell',
    when: /\brclone(?:\.exe)?\s+link\b[^\n]*\bgdrive[\w-]*:/,
    unless: /^\s*(?:grep|rg|Select-String)\b/,
    message:
      '`rclone link` は「リンクを知っている全員」の権限を付け、既定（所有者 + 2 アカウント）より公開範囲が広がります。' +
      '`python ~/.claude/skills/deliver-artifact/scripts/share.py put <file>` を使ってください（付けてしまったら `share.py private <名前>`）。',
    ref: 'traps-catalog/cloud-sync.md#rclone-link-はリンクを知っている全員の権限を付ける',
    examples: {
      hit: ['rclone link gdrive:Share/a.mp4', 'rclone link --expire 1d "gdrive:Share/b.mp4"'],
      miss: ['rclone link "dropbox:Claude/SinkaiFes2026/x.mp4"', 'rclone lsl gdrive:Builds/App', 'python share.py put a.mp4'],
    },
  },
  {
    id: 'rclone-config-reconnect-tty',
    severity: 'block',
    tool: 'shell',
    when: /\brclone(?:\.exe)?\s+config\s+reconnect\b/,
    unless: /\|\s*rclone(?:\.exe)?\s+config\s+reconnect\b/,
    message:
      'Claude Code のシェルは TTY ではないので、`rclone config reconnect` は対話の途中で EOF になり、認証が通っても token が保存されません。' +
      '`printf "y\\ny\\nn\\n" | rclone config reconnect gdrive:` のように答えをパイプで渡してください。',
    ref: 'traps-catalog/cloud-sync.md#rclone-config-は対話式で非-tty-では-eofreconnect-は-3-問答えないと-token-が保存されない',
    examples: {
      hit: ['rclone config reconnect gdrive:', 'cd x && rclone config reconnect gdrive-ro:'],
      miss: ['printf "y\\ny\\nn\\n" | rclone config reconnect gdrive:', 'rclone config create gdrive drive scope=drive.file'],
    },
  },
  {
    id: 'rclone-config-dump',
    severity: 'block',
    tool: 'shell',
    when: /\brclone(?:\.exe)?\s+config\s+(?:dump|show)\b/,
    unless: /\|\s*(?:python[0-9.]*|node)\b|^\s*(?:grep|rg|Select-String)\b/,
    message:
      '`rclone config dump / show` は refresh token や obscure したパスワード（元に戻せる）をそのまま画面とログへ出します。出たものは取り消せません。' +
      'token が要るならスクリプトへパイプで渡して値を表示しないでください。リモートの有無だけなら `rclone listremotes` を使ってください。',
    ref: 'traps-catalog/cloud-sync.md#rclone-の-tokenobscure-したパスワードを画面やログへ出す',
    examples: {
      hit: ['rclone config dump', 'rclone config show gdrive'],
      miss: ['rclone config dump | python extract_token.py', 'rclone config file', 'rclone listremotes'],
    },
  },
  {
    id: 'rclone-copyid-gdrive-drivefile',
    severity: 'warn',
    tool: 'shell',
    when: /\brclone(?:\.exe)?\s+backend\s+copyid\s+gdrive:/,
    message:
      '`gdrive:` は drive.file スコープで、人から共有されたファイルは 404 になります。' +
      '共有ファイルは最初から `rclone backend copyid gdrive-ro: <fileId> <dir>/` で取ってください（別の手段を順に試さない）。',
    ref: 'traps-catalog/cloud-sync.md#rclone-gdrivedrivefile-スコープでは人から共有されたファイルが見えない',
    examples: {
      hit: ['rclone backend copyid gdrive: 1AbCdEf "D:/tmp/"', 'rclone.exe backend copyid gdrive: 1xyz ./dl/'],
      miss: ['rclone backend copyid gdrive-ro: 1AbCdEf "D:/tmp/"', 'rclone copy gdrive:Builds/App ./out'],
    },
  },

  // ─── 映像・OBS / ffmpeg ─────────────────────────────
  {
    id: 'obs-minimize-to-tray',
    severity: 'block',
    tool: 'shell',
    when: /\bobs64(?:\.exe)?\b[^\n]*--minimize-to-tray/i,
    message:
      '`--minimize-to-tray` で起動した OBS は MainWindowHandle が 0 になり、CloseMainWindow も taskkill（/F 無し）も効かず、強制終了しか手が無くなります（次回起動がクラッシュ扱い）。' +
      '付けずに `bin/64bit` から起動してください。',
    ref: 'skills/screen-recording/SKILL.md',
    examples: {
      hit: ['(cd "C:/Program Files/obs-studio/bin/64bit" && ./obs64.exe --minimize-to-tray &)', 'Start-Process obs64.exe -ArgumentList "--minimize-to-tray"'],
      miss: ['(cd "C:/Program Files/obs-studio/bin/64bit" && ./obs64.exe > /dev/null 2>&1 &)', './obs64.exe --startrecording'],
    },
  },
  {
    id: 'obs-crash-request',
    severity: 'block',
    tool: 'shell',
    when: /\bGetInputPropertiesListPropertyItems\b/,
    unless: /^\s*(?:grep|rg|Select-String)\b/,
    message:
      'obs-websocket の GetInputPropertiesListPropertyItems（モニタ一覧など）を投げると OBS 本体が落ち、WebSocket だけ生き残って SaveSourceScreenshot が返らなくなります。' +
      'モニタは Win32 側（gui.ps1 など）で調べてください。',
    ref: 'skills/vortex-timeline-export/SKILL.md',
    examples: {
      hit: [`python "$S/obs.py" call GetInputPropertiesListPropertyItems '{"inputName":"x","propertyName":"monitor"}'`, 'python obs.py call GetInputPropertiesListPropertyItems'],
      miss: [`python obs.py call GetInputSettings '{"inputName":"x"}'`, 'python obs.py call GetSceneItemList'],
    },
  },
  {
    id: 'obs-force-kill-sentinel',
    severity: 'warn',
    tool: 'shell',
    when: /(?:stop-process|taskkill)\b[^\n]*\bobs64\b|\bobs64\b[^\n]*\|\s*stop-process\b/i,
    unless: /\.sentinel/,
    message:
      'OBS を強制終了すると `%APPDATA%\\obs-studio\\.sentinel\\run_*` が残り、次の起動でセーフモード（WebSocket 無効）を聞かれます。' +
      '`rm -f "$APPDATA/obs-studio/.sentinel/"run_*` も実行してください。',
    ref: 'skills/screen-recording/SKILL.md',
    examples: {
      hit: ['powershell -NoProfile -Command "Get-Process obs64 | Stop-Process -Force"', 'taskkill //F //IM obs64.exe'],
      miss: [
        'powershell -NoProfile -Command "Get-Process obs64 | Stop-Process -Force"\nrm -f "$APPDATA/obs-studio/.sentinel/"run_*',
        'powershell -Command "Get-Process obs64 | Select Id,MainWindowTitle"',
        'taskkill //F //IM ffmpeg.exe',
      ],
    },
  },
  {
    id: 'ffmpeg-hap-metadata',
    severity: 'warn',
    tool: 'shell',
    when: /\bffmpeg(?:\.exe)?\b[^\n]*-c:v\s+hap\b/i,
    unless: /-map_metadata\s+-1\b/,
    message:
      'HAP の出力にタイムコードのデータストリームや色空間メタデータが混ざると、プレイヤーで再生できません。' +
      '`-map 0:v:0 -an -dn -map_metadata -1` を付けてください（BtbN のビルドには HAP が無いので gyan.dev の full ビルドを使う）。',
    ref: 'rules/traps/media.md#hap-が作れない再生できない',
    examples: {
      hit: ['ffmpeg -i in.mov -c:v hap out.mov', 'ffmpeg -y -i a.mp4 -c:v hap -format hap_q b.mov'],
      miss: ['ffmpeg -i in.mov -map 0:v:0 -an -dn -map_metadata -1 -c:v hap out.mov', 'ffmpeg -i a.mov -c:v libx264 b.mp4', 'ffmpeg -i a.mov -c:v hapq b.mov'],
    },
  },
  {
    id: 'ffmpeg-ametadata-direct',
    severity: 'warn',
    tool: ['shell', 'edit'],
    files: /\.(?:go|[cm]?[jt]s|py|rs)$/i,
    when: /ametadata=print(?=[^"\s,;\]]*file=)(?![^"\s,;\]]*direct=1)/,
    message:
      'ametadata のファイル/パイプ出力は avio でバッファされ、数 KB 溜まるまで出ません（メーターが数秒に 1 回、kill で消える）。同じフィルタに `:direct=1` を付けてください。',
    ref: 'rules/traps/media.md#ffmpeg-ametadata-の出力が遅れる解析エラーになる',
    examples: {
      hit: [
        "ffmpeg -i in.wav -af astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file='pipe\\:2' -f null -",
        ['src/meter.go', 'args := []string{"-af", "ametadata=print:file=/tmp/m.txt:key=x"}'],
      ],
      miss: [
        "ffmpeg -i in.wav -af ametadata=print:key=lavfi.astats.Overall.RMS_level:file='pipe\\:2':direct=1 -f null -",
        ['src/meter.go', 'args := []string{"-af", "ametadata=print:key=lavfi.astats.Overall.RMS_level"}'],
        ['src/meter.go', 'args := []string{"-af", "ametadata=mode=add:key=x:value=y"}'],
      ],
    },
  },
  {
    id: 'ffmpeg-ametadata-pipe-quote',
    severity: 'warn',
    tool: ['shell', 'edit'],
    files: /\.(?:go|[cm]?[jt]s|py|rs)$/i,
    when: /file=pipe\\{1,2}:2/,
    message: 'filtergraph の中の `file=pipe\\:2` は引用符が無いと解析エラーになります。`file=\'pipe\\:2\'` と書いてください。',
    ref: 'rules/traps/media.md#ffmpeg-ametadata-の出力が遅れる解析エラーになる',
    examples: {
      hit: ['ffmpeg -i a.wav -af ametadata=print:key=k:file=pipe\\:2 -f null -', ['src/meter.ts', '"ametadata=print:key=k:file=pipe\\\\:2:direct=1"']],
      miss: ["ffmpeg -i a.wav -af ametadata=print:key=k:file='pipe\\:2':direct=1 -f null -", ['src/meter.ts', '"ametadata=print:file=/tmp/out.txt"']],
    },
  },
  {
    id: 'btbn-autobuild-url',
    severity: 'warn',
    tool: ['shell', 'edit'],
    exclude: /\.(?:md|txt|log)$/i,
    when: /BtbN\/FFmpeg-Builds\/releases\/download\/autobuild-/,
    message:
      'BtbN/FFmpeg-Builds は新ビルドが出ると旧 autobuild-* タグを消すので、この URL は近いうちに 404 になります。' +
      '`releases/download/latest/ffmpeg-master-latest-win64-gpl.zip` を使ってください（中身が変わるので SHA256 固定はできない）。',
    ref: 'rules/traps/media.md#btbn-の-autobuild-タグは消えて-404-になる',
    examples: {
      hit: [
        'curl -LO https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-07-01-12-50/ffmpeg-n7.1-win64-gpl.zip',
        ['scripts/fetch-tools.py', 'URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2025-12-31-13-02/x.zip"'],
      ],
      miss: [
        'curl -LO https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        ['scripts/fetch-tools.py', 'URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z"'],
        ['log/claudeLog.txt', 'BtbN/FFmpeg-Builds/releases/download/autobuild-2025-12-31 が 404'],
      ],
    },
  },

  // ─── プロトコル ─────────────────────────────────────
  {
    id: 'natnet-request-id-7',
    severity: 'warn',
    tool: 'edit',
    files: /\.(?:rs|cs|py|[cm]?[jt]s|cpp|h)$/i,
    when: /\bNAT_REQUEST\b\s*(?::\s*\w+\s*)?=\s*7\b|\bNAT_REQUEST\s*:\s*7\b/,
    message:
      'NAT_REQUEST=7 は NatNet v1.x の名残で、今の Motive ではコマンドが実行されず空の MESSAGESTRING が返ります。' +
      '正しくは REQUEST=2 / RESPONSE=3 / MESSAGESTRING=8 / UNRECOGNIZED_REQUEST=100。SDK のヘッダで照合してください。',
    ref: 'rules/traps/protocol.md#外部プロトコルの定数は原典で照合する',
    examples: {
      hit: [['src/natnet.cs', '    NAT_REQUEST = 7,'], ['src/natnet.rs', 'const NAT_REQUEST: u16 = 7;'], ['src/natnet.ts', '  NAT_REQUEST: 7,']],
      miss: [['src/natnet.cs', '    NAT_REQUEST = 2,'], ['src/natnet.rs', 'const NAT_REQUEST_MODELDEF: u16 = 4;'], ['src/natnet.py', 'NAT_REQUEST = 70']],
    },
  },
  {
    id: 'cs-udp-receiveasync-result',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /\.ReceiveAsync\(\)\s*\.Result\b/,
    message:
      '専用スレッドで `UdpClient.ReceiveAsync().Result` を回すと、毎パケット Task を確保し、Dispose しても待機を抜けません（Play のたびに受信スレッドが残る）。' +
      '`Socket.ReceiveFrom` + 使い回しバッファ（65507 バイト）にし、停止は `Close()` で抜けてください。',
    ref: 'traps-catalog/protocol.md#udpclientreceiveasyncresult-は毎パケット確保しdispose-で待機を抜けない',
    examples: {
      hit: [['Assets/Net/Rx.cs', 'var r = _udp.ReceiveAsync().Result;'], ['Assets/Net/Rx.cs', 'var bytes = client.ReceiveAsync().Result.Buffer;']],
      miss: [['Assets/Net/Rx.cs', 'var r = await _udp.ReceiveAsync();'], ['Assets/Net/Rx.cs', 'int n = _socket.ReceiveFrom(_buffer, ref _remote);']],
    },
  },

  // ─── Unity 追加 ─────────────────────────────────────
  {
    id: 'cs-runtime-mono-cecil-using',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    exclude: /\/Editor\/|\/Editor[^/]*\//i,
    when: /^\s*using\s+Mono\.Cecil\b/m,
    unless: /#if\s+UNITY_EDITOR/,
    message:
      'Editor フォルダ外の .cs に using Mono.Cecil があります。IDE の自動 using で紛れ込みやすく、エディタでは通っても Player ビルドで落ちます。' +
      '不要なら消し、必要なら Editor 専用アセンブリへ移すか #if UNITY_EDITOR で囲んでください（asmdef が Editor 限定なら無視してよい）。',
    ref: 'rules/traps/unity-build.md#player-ビルドを壊さない',
    examples: {
      hit: [['Assets/Scripts/Recorder.cs', 'using Mono.Cecil.Cil;\npublic class Recorder {}'], ['Packages/x/Runtime/A.cs', 'using Mono.Cecil;\npublic class A {}']],
      miss: [['Assets/Editor/Weaver.cs', 'using Mono.Cecil;'], ['Assets/Scripts/B.cs', '#if UNITY_EDITOR\nusing Mono.Cecil;\n#endif'], ['Assets/Scripts/C.cs', 'using MonoBehaviourExtensions;']],
    },
  },
  {
    id: 'cs-runtime-unityeditor-qualified',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    exclude: /\/Editor\/|\/Editor[^/]*\//i,
    when: /(?<![\w.])UnityEditor\.[A-Z]\w*/,
    unless: /#if\s+UNITY_EDITOR/,
    message:
      'Editor フォルダ外の .cs で UnityEditor.* を完全修飾で使っています（EditorApplication.isPlaying など）。using が無くても Player ビルドで落ちます。' +
      '再生中判定は Application.isPlaying に、それ以外は #if UNITY_EDITOR で囲むか Editor 専用アセンブリへ移してください（asmdef が Editor 限定なら無視してよい）。',
    ref: 'rules/traps/unity-build.md#player-ビルドを壊さない',
    examples: {
      hit: [['Assets/Scripts/Player.cs', 'if (UnityEditor.EditorApplication.isPlaying) {}'], ['Runtime/Loader.cs', 'var a = UnityEditor.AssetDatabase.LoadAssetAtPath<Material>(p);']],
      miss: [
        ['Assets/Editor/Tool.cs', 'if (UnityEditor.EditorApplication.isPlaying) {}'],
        ['Assets/Scripts/Player.cs', '#if UNITY_EDITOR\nif (UnityEditor.EditorApplication.isPlaying) {}\n#endif'],
        ['Assets/Scripts/Bridge.cs', 'vortex.UnityEditorBridge.Run();'],
      ],
    },
  },
  {
    id: 'cs-apply-before-draw',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /ApplyModifiedProperties\(\)\s*;[^{}]{0,300}?DrawProperties(?:Excluding)?\(/,
    message:
      'serializedObject.ApplyModifiedProperties() の後に DrawPropertiesExcluding / DrawProperties で描いています。後から描いた項目の入力は確定されず捨てられます（Inspector に値が入らない）。' +
      'Apply はすべて描画し終えてから 1 回にしてください。',
    ref: 'rules/traps/unity-editor.md#applymodifiedproperties-は描画し終えてから',
    examples: {
      hit: [['Assets/Editor/AEditor.cs', 'serializedObject.ApplyModifiedProperties();\n DrawPropertiesExcluding(serializedObject, "m_Script");'], ['Assets/Editor/AEditor.cs', 'so.ApplyModifiedProperties(); EditorGUILayout.Space(); DrawProperties(so);']],
      miss: [
        ['Assets/Editor/AEditor.cs', 'serializedObject.Update(); DrawPropertiesExcluding(serializedObject, "m_Script"); serializedObject.ApplyModifiedProperties();'],
        ['Assets/Editor/AEditor.cs', 'void A() { so.ApplyModifiedProperties(); }\nvoid B() { DrawPropertiesExcluding(so, "m_Script"); }'],
      ],
    },
  },
  {
    id: 'cs-runtime-shader-find',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    exclude: /\/Editor\/|\/Editor[^/]*\//i,
    when: /\bShader\.Find\s*\(/,
    message:
      'Shader.Find はシーン参照・Resources・Always Included Shaders のどれにも無いシェーダだとビルドで null を返します（Editor では動くのでビルドまで気付かない）。' +
      'シェーダをシリアライズフィールド / マテリアルで参照するか、Always Included Shaders に登録してください。登録済みなら無視してよい。',
    ref: 'rules/traps/unity-build.md#shaderfind-はビルドで-null-になる',
    examples: {
      hit: [['Assets/Scripts/Spout.cs', 'var s = Shader.Find("Hidden/Klak/Spout/Blit");'], ['Runtime/Fx.cs', 'mat = new Material(Shader.Find ("Universal Render Pipeline/Unlit"));']],
      miss: [['Assets/Editor/Setup.cs', 'var s = Shader.Find("Hidden/X");'], ['Assets/Scripts/Fx.cs', 'int id = Shader.PropertyToID("_BaseMap");'], ['Assets/Scripts/Fx.cs', 'MyShader.Find(x);']],
    },
  },
  {
    id: 'grep-japanese-in-unity-yaml',
    severity: 'warn',
    tool: 'shell',
    when: /\b(?:grep|rg|Select-String|findstr)\b[^\n|;]*[^\x00-\x7F][^\n|;]*\.(?:unity|prefab)\b/,
    message:
      'シーン / プレハブの YAML は日本語名を `\\uXXXX` でエスケープして保存するため、日本語で grep すると 0 件になり「どこにも無い」と誤判定します。' +
      'MCP（get_gameobject_info）で引くか、`\\u` 形式に直すか、名前の ASCII 部分で検索してください。',
    ref: 'rules/traps/unity-editor.md#シーン-yaml-の日本語名は-grep-で当たらない',
    examples: {
      hit: ['grep -rn "みなとん" Assets/Scenes/*.unity', 'rg "新衣装" --glob "*.prefab"'],
      miss: ['grep -rn "_setupped" Assets/Scenes/*.unity', 'grep -rn "みなとん" log/claudeLog.txt'],
    },
  },
  {
    id: 'copy-packagecache-to-packages',
    severity: 'warn',
    tool: 'shell',
    when: /\b(?:cp|robocopy|xcopy|Copy-Item)\b[^\n;|]*Library[\\/]PackageCache[\\/][^\n;|]*\sPackages\b/i,
    message:
      'Library/PackageCache から Packages/ へ手でコピーしてローカル化すると、git 参照が有効なまま同じ GUID のアセットが二重になり、Unity が GUID を作り直して参照が一斉に切れます。' +
      'コピーを消し、Package Manager の Embed（右クリック → Embed）を使ってください。',
    ref: 'rules/traps/unity-editor.md#packagecache-から手でコピーしてローカル化しない',
    examples: {
      hit: ['cp -r Library/PackageCache/jp.lilxyzw.liltoon@1.8.0 Packages/jp.lilxyzw.liltoon', 'Copy-Item -Recurse Library\\PackageCache\\com.x@1.0 Packages\\com.x'],
      miss: ['cp Library/PackageCache/com.x@1.0/Runtime/A.cs /tmp/scratch/A.cs', 'cp -r Packages/com.x backup/', 'robocopy Library\\PackageCache D:\\backup\\cache'],
    },
  },
  {
    id: 'cs-threadabort-log',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /catch\s*\(\s*(?:System\.Threading\.)?ThreadAbortException\b[^)]*\)\s*\{[^}]*Debug\.Log/,
    message:
      'ThreadAbortException を捕まえて Debug.Log* を呼んでいます。ドメインリロードで abort された受信スレッドがログのロックをメインスレッドと奪い合い、Play 投入でハングします。' +
      'ThreadAbortException は何もせず抜け、ログは ConcurrentQueue 経由でメインスレッドから出してください。',
    ref: 'rules/traps/unity-runtime.md#受信スレッドから-debuglog-を呼ばない',
    examples: {
      hit: [['Assets/Net/Rx.cs', 'catch (ThreadAbortException e) { Debug.LogException(e); }'], ['Assets/Net/Rx.cs', 'catch (System.Threading.ThreadAbortException) { Debug.Log("abort"); break; }']],
      miss: [['Assets/Net/Rx.cs', 'catch (ThreadAbortException) { break; }'], ['Assets/Net/Rx.cs', 'catch (Exception e) { Debug.LogException(e); }']],
    },
  },
  {
    id: 'cs-uosc-values-cast',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    check: ({ text }) => /\busing\s+uOSC\b|\buOSC\./.test(text) && /\((?:float|int)\)\s*[\w.]*\.values\s*\[/.test(text),
    message:
      'uOSC の Message.values（object[]）を (float) / (int) で直接キャストしています。送信側の型タグが違うと毎メッセージ InvalidCastException になり、' +
      'uOscServer が例外を捕まえないため受信ループが詰まります。int / float の両方を受ける取り出し（`values[0] is float f ? f : values[0] is int i ? i : ...`）にしてください。',
    ref: 'rules/traps/unity-gc.md#uosc-の-values-を-float-でキャストしない',
    examples: {
      hit: [['Assets/Osc/Rx.cs', 'using uOSC;\nvar x = (float)message.values[0];'], ['Assets/Osc/Rx.cs', 'using uOSC;\nint id = (int) msg.values [2];']],
      miss: [['Assets/Data/D.cs', 'var x = (float)data.values[i];'], ['Assets/Osc/Rx.cs', 'using uOSC;\nif (msg.values[0] is float f) {}']],
    },
  },
  {
    id: 'cs-director-resume',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    when: /\b\w*[Dd]irector\w*\s*\.\s*Resume\s*\(\s*\)/,
    unless: /\.IsValid\s*\(\s*\)/,
    message:
      'PlayableDirector.Resume() は PlayableGraph が未生成（一度も再生していない director）だと何もせず、Paused のまま時間が進みません（エラーなし）。' +
      '`director.playableGraph.IsValid()` で分岐し、無ければ Play() してから time を戻してください。',
    ref: 'rules/traps/unity-timeline.md#playabledirectorresume-は-graph-が無いと何もしない',
    examples: {
      hit: [['Assets/Tl/Ctl.cs', '_director.Resume();'], ['Assets/Tl/Ctl.cs', 'playableDirector.Resume();']],
      miss: [['Assets/Tl/Ctl.cs', 'if (!director.playableGraph.IsValid()) director.Play(); else director.Resume();'], ['Assets/Tl/Ctl.cs', 'timer.Resume();']],
    },
  },
  {
    id: 'cs-recorder-activecamera',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /ImageSource\s*\.\s*ActiveCamera\b|new\s+ActiveCameraInputSettings\b/,
    message:
      'Recorder の ActiveCamera 入力は Built-in 専用で、URP では "ActiveCamera is only compatible with the Legacy Render Pipeline" で開始に失敗します。' +
      'TargetCamera か RenderTexture の入力を使ってください（Built-in のプロジェクトなら無視してよい）。',
    ref: 'rules/traps/unity-timeline.md#urp-で-recorder-の入力を選ぶ',
    examples: {
      hit: [['Assets/Editor/Rec.cs', 'settings.imageInputSettings = new ActiveCameraInputSettings { };'], ['Assets/Editor/Rec.cs', 'input.Source = ImageSource.ActiveCamera;']],
      miss: [['Assets/Editor/Rec.cs', 'new CameraInputSettings { Source = ImageSource.TaggedCamera }'], ['Assets/Editor/Rec.cs', 'new RenderTextureInputSettings()']],
    },
  },
  {
    id: 'uss-unity-font',
    severity: 'warn',
    tool: 'edit',
    files: /\.(?:uss|uxml)$/i,
    when: /(?<![\w-])-unity-font\s*:/,
    message:
      'UI Toolkit の -unity-font は、継承された FontAsset（-unity-font-definition）に負けて効かず、アイコンフォントなら別のグリフが出ます（警告なし）。' +
      '`-unity-font-definition: url("...")` を使ってください。',
    ref: 'rules/traps/unity-runtime.md#ui-toolkit-で文字だけ出ないグリフが違う',
    examples: {
      hit: [['Assets/UI/a.uss', '-unity-font: url("Fonts/lucide.ttf");'], ['Assets/UI/a.uss', '.icon{-unity-font:resource("Fonts/icons");}']],
      miss: [['Assets/UI/a.uss', '-unity-font-definition: url("Fonts/lucide.ttf");'], ['Assets/UI/a.uss', '-unity-font-style: bold;']],
    },
  },
  {
    id: 'cs-getopenfilename-cwd',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.cs$/i,
    when: /\bGet(?:Open|Save)FileName[AW]?\s*\(/,
    unless: /OFN_NOCHANGEDIR|0x0*8\b/,
    message:
      'Win32 の GetOpenFileName / GetSaveFileName は既定でカレントディレクトリを変え、Unity がそれを検知してクラッシュします。' +
      'Flags に OFN_NOCHANGEDIR (0x8) を付け、try/finally で CWD を保存・復元してください。',
    ref: 'traps-catalog/unity-runtime.md#win32-getopenfilename-がカレントディレクトリを変えて-unity-が落ちる',
    examples: {
      hit: [['Assets/Win/Dlg.cs', '[DllImport("comdlg32.dll")] static extern bool GetOpenFileName(ref OpenFileName ofn);'], ['Assets/Win/Dlg.cs', 'if (GetSaveFileNameW(ref ofn)) {}']],
      miss: [['Assets/Win/Dlg.cs', 'const int OFN_NOCHANGEDIR = 0x00000008;\nif (GetOpenFileName(ref ofn)) {}'], ['Assets/Editor/Dlg.cs', 'var p = EditorUtility.OpenFilePanel("a", "", "json");']],
    },
  },
  {
    id: 'cs-vf-packet-int-cast',
    severity: 'warn',
    tool: 'edit',
    files: /\.cs$/i,
    when: /\(int\)\s*packet\s*\*\s*255\b/,
    message:
      '`(int)packet * 255` はキャストが先に効き、0〜1 の packet が 0 か 255 の倍数になって色が飽和します（VF_Laser）。' +
      'PacketToChannel(packet) か `(int)(packet * 255)` にしてください。直すと既存プロファイルの見え方が変わる旨を報告すること。',
    ref: 'traps-catalog/vortex.md#vf_laser-の-intpacket--255-で色が飽和virtualfixturewriteprofile-の-i--count',
    examples: {
      hit: [['Assets/VF/VF_Laser.cs', 'color.r = (int)packet * 255;'], ['Assets/VF/VF_Laser.cs', 'var v = (int) packet*255;']],
      miss: [['Assets/VF/VF_Laser.cs', 'var v = (int)(packet * 255);'], ['Assets/VF/VF_Laser.cs', 'var v = PacketToChannel(packet);']],
    },
  },

  // ─── After Effects（ExtendScript / CEP） ──────────────
  {
    id: 'ae-jsx-regex-slash-in-class',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.(?:jsx|jsxinc)$/i,
    check: ({ text, filePath }) => AE_REGEX_SLASH_IN_CLASS.test(text) && (/\.jsxinc$/i.test(filePath) || AE_CONTEXT.test(text)),
    message:
      'ExtendScript の正規表現の文字クラスに素の / があります（例 /[\\\\/]+$/）。ES3 のスキャナがそこでリテラルを打ち切り、' +
      'JSX 全体が無応答になって AE を再起動するまで evalScript が返りません。Node vm のテストでは再現しません。' +
      'パス区切りは charAt で書くか、[\\/] と / をエスケープしてください。',
    ref: 'rules/traps/after-effects.md#extendscript-の正規表現で文字クラスに素のスラッシュを書かない',
    examples: {
      hit: [['jsx/util.jsx', "var p = String(app.project.file).replace(/[\\\\/]+$/, '');"], ['jsx/lib.jsxinc', "s = s.replace(/[/]+$/, '');"]],
      miss: [['jsx/util.jsx', "var p = String(app.project.file).replace(/[\\/]+$/, '');"], ['jsx/util.jsx', 'var a = [x / 2]; app.project.save();'], ['src/components/Path.jsx', 'const parts = p.split(/[\\\\/]/);']],
    },
  },
  {
    id: 'ae-run-script-regex-slash-in-class',
    severity: 'block',
    tool: 'mcp-code',
    files: /^mcp:aemcp\//,
    when: AE_REGEX_SLASH_IN_CLASS,
    message:
      'ae_run_script に渡す ExtendScript の正規表現で、文字クラスに素の / があります（例 /[\\\\/]+$/）。ES3 のスキャナがそこでリテラルを打ち切り、' +
      'evalScript が返らなくなって AE を再起動するまで AEMCP が全ツールで止まります。パス区切りは charAt で書くか、[\\/] と / をエスケープしてください。',
    ref: 'rules/traps/after-effects.md#extendscript-の正規表現で文字クラスに素のスラッシュを書かない',
    examples: {
      hit: [['mcp:aemcp/run_script.jsx', "String(app.project.file).replace(/[\\\\/]+$/, '')"], ['mcp:aemcp/run_script.jsx', "var n = f.fsName.split(/[/\\\\]/).pop(); n"]],
      miss: [['mcp:aemcp/run_script.jsx', "String(app.project.file).replace(/[\\/]+$/, '')"], ['mcp:aemcp/run_script.jsx', 'app.project.activeItem.width / 2']],
    },
  },
  {
    id: 'ae-run-script-renderqueue-render',
    severity: 'block',
    tool: 'mcp-code',
    files: /^mcp:aemcp\//,
    when: /\brenderQueue\.render\s*\(/,
    message:
      'ae_run_script（evalScript）から renderQueue.render() を呼ぶと同期レンダーになり、書き出しが終わるまで AE ごと固まります（AEMCP の他のツールも返らない）。' +
      'ae_render / ae_ame_render を使うか、aerender を別プロセスで走らせてください（出力先フォルダは先に作る）。',
    ref: 'rules/traps/after-effects.md#renderqueuerender-を-evalscript-から呼ばない',
    examples: {
      hit: [['mcp:aemcp/run_script.jsx', 'app.project.renderQueue.render();'], ['mcp:aemcp/run_script.jsx', 'var rq = app.project.renderQueue; rq.item(1).render = true; app.project.renderQueue.render ()']],
      miss: [['mcp:aemcp/run_script.jsx', 'app.project.renderQueue.items.add(comp); app.project.renderQueue.numItems'], ['mcp:aemcp/run_script.jsx', 'app.project.renderQueue.item(1).render = false;']],
    },
  },
  {
    id: 'ae-json-polyfill-conditional',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.(?:jsx|jsxinc)$/i,
    when: /typeof\s+(?:this\.|\$\.global\.)?JSON(?:\.\w+)?\s*[!=]==?\s*['"](?:undefined|function|object)['"]|if\s*\(\s*!\s*(?:this\.|\$\.global\.)?JSON\s*\)/,
    message:
      'JSON のポリフィルを条件付きで入れています。ExtendScript のエンジンはパネルを再読込しても生き続けるため、' +
      '一度入った古い実装が残り「JSX を直したのに直らない」になります。json2 は無条件で先に読み込んでください。',
    ref: 'traps-catalog/after-effects.md#extendscript-に-json-が無いポリフィルを条件付きで入れると古い実装が残る',
    examples: {
      hit: [['jsx/host.jsx', "if (typeof JSON.stringify !== 'function') {"], ['mcp:aemcp/run_script.jsx', "if (typeof JSON !== 'object') { JSON = {}; }"]],
      miss: [['jsx/host.jsx', "#include 'json2.jsx'\nJSON.stringify(x);"], ['mcp:aemcp/run_script.jsx', "if (typeof x !== 'function') {}"]],
    },
  },
  {
    id: 'ae-text-animator-path-without-selectors',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.(?:jsx|jsxinc|[cm]?[jt]s|py)$/i,
    exclude: NOT_AEMCP,
    when: /Animator \d+\/Range Selector/,
    message:
      'テキストアニメーターのパスに Selectors の段がありません。正しくは Animator 1/Selectors/Range Selector 1/... です。' +
      'スクリプトで足したアニメーターは Range Selector を持たないので、無ければ addProperty("ADBE Text Selector") で足してください。',
    ref: 'rules/traps/after-effects.md#テキストアニメーターの-range-selector',
    examples: {
      hit: [['server/src/lyric.ts', "path: 'Text/Animators/Animator 1/Range Selector 1/Offset'"], ['mcp:aemcp/run_script.jsx', 'var p = "Animator 2/Range Selector 1/Start";']],
      miss: [['server/src/lyric.ts', "path: 'Text/Animators/Animator 1/Selectors/Range Selector 1/Offset'"], ['mcp:bmcp/run_python.py', 'p = "Animator 1/Range Selector 1"']],
    },
  },
  {
    id: 'ae-allfonts-flat-access',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.(?:jsx|jsxinc|[cm]?[jt]s)$/i,
    when: /allFonts\[[^\]\n]+\]\.(?:postScriptName|familyName|styleName|name|fontFamily)\b/,
    message:
      'app.fonts.allFonts はファミリーごとの入れ子配列で、allFonts[i] は FontObject ではありません。' +
      'このままだと値が全件 undefined になり、エラーも出ずにフィルタが空振りします。allFonts[i][j] の二重ループにしてください。',
    ref: 'rules/traps/after-effects.md#extendscript-の-api-の小さな癖',
    examples: {
      hit: [['jsx/fonts.jsx', 'var n = app.fonts.allFonts[i].postScriptName;'], ['mcp:aemcp/run_script.jsx', 'app.fonts.allFonts[k].familyName']],
      miss: [['jsx/fonts.jsx', 'var n = app.fonts.allFonts[i][j].postScriptName;'], ['mcp:aemcp/run_script.jsx', 'var fam = app.fonts.allFonts[i]; fam.length']],
    },
  },
  {
    id: 'cep-manifest-scriptpath',
    severity: 'warn',
    tool: 'edit',
    files: /\/CSXS\/manifest\.xml$/i,
    when: /<ScriptPath>/,
    message:
      'CEP マニフェストに <ScriptPath> があります。CEP が JSX を勝手に評価してエンジンを掴み、以後の evalScript が永久に返りません。' +
      'ScriptPath を外し、JSX のソースを連結して 1 回の evalScript で流してください。',
    ref: 'rules/traps/after-effects.md#cep-マニフェストの-scriptpath-と-starton',
    examples: {
      hit: [['extension/CSXS/manifest.xml', '<ScriptPath>./jsx/host.jsx</ScriptPath>'], ['ext/svc/CSXS/manifest.xml', '<ScriptPath>host.jsx</ScriptPath>']],
      miss: [['extension/CSXS/manifest.xml', '<MainPath>./service.html</MainPath>'], ['docs/notes.md', '<ScriptPath> は使わない']],
    },
  },
  {
    id: 'cep-manifest-event-unqualified',
    severity: 'warn',
    tool: 'edit',
    files: /\/CSXS\/manifest\.xml$/i,
    when: /<Event>\s*(?!com\.adobe\.)[A-Za-z][\w.]*\s*<\/Event>/,
    message:
      'StartOn の <Event> が完全修飾名ではありません。マニフェストの解析は通りますが、イベントは黙って発火しません。' +
      'com.adobe.csxs.events.ApplicationActivate のように書いてください。',
    ref: 'rules/traps/after-effects.md#cep-マニフェストの-scriptpath-と-starton',
    examples: {
      hit: [['extension/CSXS/manifest.xml', '<Event>applicationActivate</Event>'], ['extension/CSXS/manifest.xml', '<Event> ApplicationActivate </Event>']],
      miss: [['extension/CSXS/manifest.xml', '<Event>com.adobe.csxs.events.ApplicationActivate</Event>'], ['extension/CSXS/manifest.xml', '<Event>com.adobe.csxs.events.AppOnline</Event>']],
    },
  },
  {
    id: 'kill-aftereffects',
    severity: 'block',
    tool: 'shell',
    when: /\b(?:stop-process\b[^\n]*afterfx|afterfx[^\n]*\|\s*stop-process\b|taskkill\b(?=[^\n]*\s\/{1,2}f\b)[^\n]*afterfx|kill\s+-9\b[^\n]*afterfx)/i,
    message:
      'After Effects を強制終了すると、次の起動が描画されないモーダル（#32770）で止まります（CPU 0・窓もログも出ない）。' +
      '`(Get-Process -Id <pid>).CloseMainWindow()` か /F 無しの taskkill で閉じてください。止まったらその窓へ WM_CLOSE。',
    ref: 'rules/traps/after-effects.md#after-effects-を強制終了しない',
    examples: {
      hit: ['powershell -Command "Stop-Process -Name AfterFX -Force"', 'taskkill //F //IM AfterFX.exe', 'powershell -Command "Get-Process AfterFX | Stop-Process -Force"'],
      miss: ['taskkill //IM AfterFX.exe', 'powershell -Command "(Get-Process AfterFX).CloseMainWindow()"', 'powershell -Command "Get-Process AfterFX | Select Id,StartTime"'],
    },
  },

  // ─── Blender（bpy。BMCP の blender_run_python にも当てる） ───
  {
    id: 'blender-redraw-swap',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.py$/i,
    exclude: NOT_BMCP,
    when: /redraw_timer\([^)\n]*DRAW_(?:WIN_)?SWAP/,
    message:
      'redraw_timer の SWAP 付きの直後に screenshot_area で撮ると 1×1 の画像になります。再描画させるなら DRAW_WIN を使ってください。' +
      'また演算子の実行中に redraw_timer を呼ぶと Blender が落ちます（進捗は window_manager.progress_* で出す）。',
    ref: 'rules/traps/blender.md#op-の途中で-redraw_timer-を呼ぶと落ちる',
    examples: {
      hit: [['addon/cap.py', "bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)"], ['mcp:bmcp/run_python.py', 'bpy.ops.wm.redraw_timer(type="DRAW_SWAP")']],
      miss: [['addon/cap.py', "bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)"], ['mcp:dvcmcp/run_python.py', 'bpy.ops.wm.redraw_timer(type="DRAW_SWAP")']],
    },
  },
  {
    id: 'blender-shape-key-add-no-value',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.py$/i,
    exclude: NOT_BMCP,
    check: ({ text }) => {
      const calls = text.match(/\.shape_key_add\([^)\n]*\)/g) ?? [];
      const nonBasis = calls.filter((c) => !/name\s*=\s*["']Basis["']/.test(c) && !/from_mix\s*=\s*True/.test(c));
      return nonBasis.length > 0 && !/\.value\s*=/.test(text);
    },
    message:
      'shape_key_add の後に value を設定していません。Blender 5.0 から追加時の値が 1.0（4.2 は 0）になり、足した途端に形が変わります。' +
      '`kb.value = 0.0` を明示してください（生成箇所は 1 関数に集約する）。',
    ref: 'rules/traps/blender.md#blender-5x-で黙って変わった-api',
    examples: {
      hit: [['addon/keys.py', 'kb = obj.shape_key_add(name="Smile", from_mix=False)'], ['mcp:bmcp/run_python.py', 'obj.shape_key_add(name="Basis")\nk = obj.shape_key_add(name="A")']],
      miss: [['addon/keys.py', 'kb = obj.shape_key_add(name="Smile", from_mix=False)\nkb.value = 0.0'], ['mcp:bmcp/run_python.py', 'obj.shape_key_add(name="Basis")']],
    },
  },
  {
    id: 'blender-gn-socket-index',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    scope: 'file',
    files: /\.py$/i,
    exclude: NOT_BMCP,
    when: /\[\s*["']Socket_\d+(?:_use_attribute|_attribute_name)?["']\s*\]/,
    unless: /bpy\.app\.version/,
    message:
      'Geometry Nodes の入力を mod["Socket_N"] で書いています。Blender 5.0 で mod.properties.inputs.<識別子>.value へ移り、' +
      '旧経路は 5.x で黙って効きません。bpy.app.version で分岐し、見つからなければエラーにしてください。',
    ref: 'rules/traps/blender.md#blender-5x-で黙って変わった-api',
    examples: {
      hit: [['addon/gn.py', 'mod["Socket_2"] = 0.5'], ['mcp:bmcp/run_python.py', "m['Socket_3_use_attribute'] = True"]],
      miss: [['addon/gn.py', 'if bpy.app.version >= (5, 0):\n    mod.properties.inputs.Socket_2.value = 0.5\nelse:\n    mod["Socket_2"] = 0.5'], ['mcp:bmcp/run_python.py', 'mod.properties.inputs.Socket_2.value = 0.5']],
    },
  },
  {
    id: 'blender-append-reuse',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    scope: 'file',
    files: /\.py$/i,
    exclude: NOT_BMCP,
    when: /['"]APPEND_REUSE['"]/,
    unless: /bpy\.app\.version/,
    message:
      "取り込み方に 'APPEND_REUSE' を使っています。Blender 5.2 では有効値が LINK / APPEND / PACK で、代入するとエラーになります" +
      '（RNA 定義には残っているので紛らわしい）。bpy.app.version で選んでください。',
    ref: 'traps-catalog/blender.md#blender-52-で-linkappend-の取り込み方に-append_reuse-を代入すると弾かれる',
    examples: {
      hit: [['addon/lib.py', "params.import_method = 'APPEND_REUSE'"], ['mcp:bmcp/run_python.py', 'link_method="APPEND_REUSE"']],
      miss: [['addon/lib.py', "m = 'APPEND_REUSE' if bpy.app.version < (5, 2) else 'APPEND'"], ['addon/lib.py', '# APPEND_REUSE は 5.2 で不可']],
    },
  },
  {
    id: 'blender-importer-active-none',
    severity: 'warn',
    tool: ['edit', 'mcp-code'],
    files: /\.py$/i,
    exclude: NOT_BMCP,
    check: ({ text }) => /temp_override\([^)]*\bactive_object\s*=\s*None/.test(text) && /\bimport_scene\.|\bimport_mesh\.|\bvrm\b|\bgltf\b/i.test(text),
    message:
      'temp_override(active_object=None) の中で取り込みを呼んでいます。FBX / glTF / VRM のインポーターは内部で active_object を参照するので落ちます。' +
      'active は上書きせず、選択解除だけにしてください。',
    ref: 'rules/traps/blender.md#インポーターに-active_objectnone-を渡さない',
    examples: {
      hit: [
        ['addon/imp.py', 'with bpy.context.temp_override(active_object=None):\n    bpy.ops.import_scene.fbx(filepath=p)'],
        ['mcp:bmcp/run_python.py', 'with C.temp_override(selected_objects=[], active_object=None):\n    bpy.ops.import_scene.vrm(filepath=p)'],
      ],
      miss: [['addon/imp.py', 'with bpy.context.temp_override(active_object=None):\n    bpy.ops.object.select_all(action="DESELECT")'], ['mcp:bmcp/run_python.py', 'bpy.ops.import_scene.fbx(filepath=p)']],
    },
  },

  // ─── Unreal ─────────────────────────────────────────
  {
    id: 'ue-rotator-positional',
    severity: 'warn',
    tool: 'edit',
    files: /\.py$/i,
    check: ({ text }) =>
      (text.match(/\bunreal\.Rotator\(\s*-?[\d.]+\s*,[^)\n]*\)/g) ?? []).some(
        (c) => !/^unreal\.Rotator\(\s*0(?:\.0*)?\s*,\s*0(?:\.0*)?\s*,\s*0(?:\.0*)?\s*\)$/.test(c),
      ),
    message:
      'unreal.Rotator を位置引数で作っています。Python の位置引数の順は (roll, pitch, yaw) で、取り違えると向きが黙ってずれます。' +
      'Rotator(roll=..., pitch=..., yaw=...) とキーワードで書いてください。',
    ref: 'rules/traps/unreal.md#sequencer-python-の単位と引数順',
    examples: {
      hit: [['Content/Python/seq.py', 'r = unreal.Rotator(0, 90, 0)'], ['Content/Python/seq.py', 'r = unreal.Rotator(-90.0, 0.0, 45.0)']],
      miss: [['Content/Python/seq.py', 'r = unreal.Rotator(roll=0, pitch=90, yaw=0)'], ['Content/Python/seq.py', 'r = unreal.Rotator(0, 0, 0)']],
    },
  },
  {
    id: 'ue-buildconfig-deprecated-maxprocessorcount',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /BuildConfiguration\.xml$/i,
    when: /<ParallelExecutor>[\s\S]*?<MaxProcessorCount>/,
    message:
      'UE 5.6 では ParallelExecutor.MaxProcessorCount は deprecated で無視され、並列度は下がりません（C3859 / 1455 が続く）。' +
      '<BuildConfiguration><MaxParallelActions>4</MaxParallelActions><bAllowUBALocalExecutor>false</bAllowUBALocalExecutor> を使い、' +
      '変えたら Intermediate / Binaries を消してください。',
    ref: 'rules/traps/unreal.md#c-ビルドが-c3859-や-1455-で落ちる',
    examples: {
      hit: [['UnrealBuildTool/BuildConfiguration.xml', '<ParallelExecutor><MaxProcessorCount>8</MaxProcessorCount></ParallelExecutor>'], ['Saved/UnrealBuildTool/BuildConfiguration.xml', '<ParallelExecutor>\n  <MaxProcessorCount>4</MaxProcessorCount>\n</ParallelExecutor>']],
      miss: [['UnrealBuildTool/BuildConfiguration.xml', '<BuildConfiguration><MaxParallelActions>4</MaxParallelActions></BuildConfiguration>'], ['UnrealBuildTool/BuildConfiguration.xml', '<LocalExecutor><MaxProcessorCount>8</MaxProcessorCount></LocalExecutor>']],
    },
  },
  {
    id: 'ue-poseable-bone-by-name',
    severity: 'warn',
    tool: 'edit',
    files: /\.(?:cpp|h)$/i,
    when: /\b(?:Set|Get)BoneTransformByName\s*\(/,
    message:
      'PoseableMeshComponent の Set/GetBoneTransformByName は呼ぶたびに全身のポーズを作り直します。' +
      '毎フレーム全ボーンを動かすなら、RefSkeleton を 1 パスで舐めて BoneSpaceTransforms へ直接書き、最後に MarkRefreshTransformDirty() を 1 回呼んでください。' +
      '一度きりの読み書きならこのままでよい。',
    ref: 'rules/traps/unreal.md#poseablemesh-をボーン名で-1-本ずつ動かさない',
    examples: {
      hit: [['Source/X/Driver.cpp', 'Poseable->SetBoneTransformByName(Name, T, EBoneSpaces::ComponentSpace);'], ['Source/X/Driver.cpp', 'Poseable->GetBoneTransformByName(Name, EBoneSpaces::WorldSpace);']],
      miss: [['Source/X/Driver.cpp', 'Poseable->BoneSpaceTransforms[i] = Local; Poseable->MarkRefreshTransformDirty();'], ['Source/X/Driver.cpp', 'Mesh->GetBoneTransform(Index);']],
    },
  },

  // ─── スクリプトの文字コード（バイト列で判定。テストは test-hooks.mjs に個別） ───
  {
    id: 'unity-json-bom',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /(?:^|\/)Packages\/(?:manifest|packages-lock)\.json$|\.asmdef$|\.asmref$/i,
    check: ({ bytes }) => bytes != null && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf,
    message:
      'Packages/manifest.json・packages-lock.json・asmdef の先頭に UTF-8 BOM があります。Package Manager がパースに失敗し（Editor.log に `Char: 65279`）、' +
      'パッケージが解決されずコンパイルエラーが連鎖します。BOM なし UTF-8 で保存し直してください。',
    ref: 'rules/traps/unity-build.md#manifestjson-を外で書き換えても再解決されない',
  },
  {
    id: 'ps1-non-ascii-without-bom',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.ps1$/i,
    check: ({ bytes }) =>
      bytes != null &&
      !(bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) &&
      bytes.some((b) => b >= 0x80),
    message:
      'ASCII 以外を含む .ps1 が BOM なし UTF-8 です。Windows PowerShell 5.1 は ANSI として読み、構文エラーや文字化けになります。' +
      'UTF-8 BOM 付きで保存し直してください。',
    ref: 'rules/traps/windows-shell.md#powershell-スクリプトは-bom-付き',
  },
  {
    id: 'vbs-non-ascii-without-utf16-bom',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.(?:vbs|wsf)$/i,
    check: ({ bytes }) => bytes != null && !(bytes[0] === 0xff && bytes[1] === 0xfe) && bytes.some((b) => b >= 0x80),
    message:
      'ASCII 以外を含む .vbs が UTF-16LE BOM 付きではありません。WSH は UTF-8 を読めず、文字化け・構文エラーになります。' +
      'UTF-16LE（BOM 付き）で保存し直すか、ASCII だけで書いてください。',
    ref: 'rules/traps/windows-shell.md#powershell-スクリプトは-bom-付き',
  },
  {
    id: 'bat-formfeed',
    severity: 'warn',
    tool: 'edit',
    scope: 'file',
    files: /\.(?:bat|cmd)$/i,
    check: ({ bytes }) => bytes != null && bytes.includes(0x0c),
    message:
      '.bat に改ページ文字（0x0C）が入っています。`scripts\\fetch-...` の `\\f` が書き換えの途中でエスケープとして解釈された跡です。' +
      'パス区切りをスラッシュにして書き直してください（`"%~dp0scripts/fetch-tools.py"`）。',
    ref: 'traps-catalog/windows-shell.md',
  },
];
