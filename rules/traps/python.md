---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# python の罠

全件は ~/.claude/traps-catalog/python.md。ここは再発しやすいものだけ。pip と python の食い違い・cp932 は windows-shell、uv → venv のプロセス残りは process の罠にある。

### uv → venv の多段起動では stdin の EOF が本体に届かない
クライアントがサーバーを閉じるたびに Python ワーカが残る。原因は node → uv → venv の python.exe（ランチャー）→ 本体の多段で EOF が届かず、`proc.kill()` は uv しか止めないこと。→ ワーカ自身が親 PID の終了を `WaitForSingleObject` で待って終わる。（実例: 2026-09-23 DvcMCP）

### PyInstaller onefile で __file__ の隣に書かない
exe で設定が保存できない・同梱ファイルが見つからない。原因は onefile が `_MEIPASS` の一時展開先で動き、Program Files が書き込み不可なこと。→ `sys.frozen` で分岐する `paths.py` を 1 つ持ち、保存先は `%APPDATA%\<App>`。同梱物は `datas` で入れる。（実例: 2026 KachinkoShot）

### pandas の from_dict(orient='index') は時系列順にならない
「最新」として古い行が表示される。原因は行順が時系列を保証しないこと。→ 生成後に `sort_index()` を必ず掛け、回帰テストを置く。（実例: 2026-07-03 Traddist）
