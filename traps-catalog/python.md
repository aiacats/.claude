# python の罠（カタログ）

Python（uv・venv・パッケージ・配布・ライブラリ）で踏んだ罠の全件。Blender の Python は blender カタログ、シェルに Python を埋め込む罠は windows-shell カタログ。

### python と pip が別の Python を指す（pip install したのに import できない）
- windows-shell カタログ「pip と python が別の Python を指す」に記載（`python -m pip` / `uv add`・`uv run`）。
- 実例: 2026-03-31 ClaudeVideoReader / 2026-05-23 KachinkoShot

### Windows の子プロセスで Python の標準入出力が cp932 になる
- windows-shell カタログ「子プロセスの出力が cp932 で化ける」に記載（`sys.stdout.reconfigure(encoding="utf-8")`）。
- 補足（DvcMCP）: stdout を JSON 専用にするなら、fd 1 を JSON 用に複製し、fd 1 自体は stderr へ向け直してネイティブ出力の混入を防ぐ。
- 実例: 2026-07 Traddist / 2026-09-23 DvcMCP
- 出典: DvcMCP/CLAUDE.md:71-73

### node → uv → venv の python.exe（ランチャー）→ 本体 python の多段起動で終了が伝わらない
- process カタログ「kill してもツリーの本体が残る」に記載。
- 補足（Python 側の対策）: ワーカに親 PID を渡し `WaitForSingleObject` で親の終了を待って自分も終わる。stdin の EOF は 4 段目まで届かない。残骸確認は元 Python のパスの python.exe を `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` の親子で見る。
- 実例: 2026-09-23 DvcMCP
- 出典: DvcMCP/CLAUDE.md:74-77

### PyInstaller onefile ではデータファイルとユーザーデータの置き場が変わる
- 症状: （予防）exe で設定が保存できない・同梱ファイルが見つからない。
- 原因: onefile は `_MEIPASS` の一時展開先で動く。`Path(__file__).parent` は frozen 時に意味が変わる。Program Files 配下は書き込み不可のことがある。
- 対策: `sys.frozen` で分岐する `paths.py` を 1 つ持ち、exe 時の保存先は `%APPDATA%\<App>`。新規データは Analysis の `datas=[(..., '.')]` で同梱し、初回起動で `_MEIPASS` から APPDATA へコピーする。
- 実例: 2026 KachinkoShot
- 自動検出: 不可
- 出典: KachinkoShot/memory/path_conventions.md:11-17

### PyInstaller onefile は初回起動に 1〜2 秒かかり、Qt は ICU で重い
- 症状: 起動ラグ、配布サイズ 46MB。
- 原因: _MEI への展開、icudt74.dll（28MB）。
- 対策: 許容するか onedir にする。excludes は効果が小さい。
- 実例: 2026-05-23 KachinkoShot
- 自動検出: 不可
- 出典: KachinkoShot:110-112

### pandas の DataFrame.from_dict(orient='index') は行順が時系列にならない
- 症状: 最新ポジションとして古い銘柄（VWO）が表示された。
- 原因: 行順が挿入順・時系列を保証しない。
- 対策: 時系列 DataFrame は生成後に `sort_index()` を必ず掛ける。回帰テストを置く。
- 実例: 2026-07-03 Traddist
- 自動検出: 候補 `from_dict\([^)]*orient\s*=\s*['"]index['"]`（warn。sort_index が後続にあるかは見られない）
- 出典: Traddist/log/claudeLog.txt:29

### 自己署名では SmartScreen の警告は消えない（PyInstaller 配布）
- tauri カタログ「署名なし・自己署名の配布では SmartScreen の警告は消えない」に記載。
- 実例: 2026-05-23 KachinkoShot
