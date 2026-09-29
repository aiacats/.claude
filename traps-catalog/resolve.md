# resolve の罠（カタログ）

DaVinci Resolve のスクリプト API と DvcMCP で踏んだ罠の全件。実測は Resolve Studio 18.6.6。

### Resolve がモーダルダイアログを出していると API は例外でなく None を返す
- 症状: ImportMedia・SetSetting などが全部 None で黙って失敗する。起動直後の Software Update（21.1 の案内）ダイアログで踏んだ。
- 原因: ダイアログ表示中はスクリプト API が機能しない。
- 対策: 書き込みの戻り値を必ず検査し、None と False を区別する（None → ダイアログで停止）。GetCurrentPage() が None なら警告する。ダイアログは Skip で閉じる。DvcMCP は RESOLVE_BLOCKED と resolve_status の warnings で対処済み。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:56-58 / MEM(DvcMCP)\resolve-environment.md:11-12 / Notion 3e4e4d4b-751b-81ef-8e90-d2c359f3261b

### Resolve のフレームの約束は API の説明文と違う（1 フレームずれる）
- 症状: 区間が 1 フレームずれる。
- 原因: `GetLeftOffset()` = ソース In、`GetRightOffset()` = ソース Out（含まない）。`AppendToTimeline` の endFrame は含む。
- 対策: 内部は [start, end) で持ち、渡す直前に -1 する。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:59-61

### SetClipsLinked は 1 組 75ms と遅い
- 症状: 300 件で 39 秒。
- 原因: API 1 回のコスト。
- 対策: 同じ区間の V+A は mediaType 無しで 1 件として Append する（Resolve がリンクして置く）。3.5 秒になった。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可（リンクが要る場面の正しい使い方と区別できない）
- 出典: DvcMCP\CLAUDE.md:62-63

### 音声だけのクリップ（WAV）には "Frames" が無い
- 症状: フレーム数の取得が失敗する。
- 原因: WAV は "Duration"（プロジェクト fps のタイムコード）しか持たない。
- 対策: Duration から数える。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:78-79

### 字幕トラックのアイテムは AppendToTimeline で置き直せない
- 症状: 詰めたタイムラインで字幕だけ取り残される。
- 原因: API の制約。
- 対策: 位置が変わる字幕があれば編集を止める。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:80 / DvcMCP\log\claudeLog.txt:37

### Resolve はメディアの長さを取り込み時点で覚えている
- 症状: 試験素材を作り直しても古い長さのまま。
- 原因: メディアプールのキャッシュ。
- 対策: 素材を作り直したらメディアプールへ入れ直す。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:83-84

### トリム・移動・Undo の API が無い
- 症状: 既存タイムラインのアイテムを動かせない。書き換えを戻せない。
- 原因: API に無い。
- 対策: 元を変えずに新しいタイムラインを作って置き直す（グレード・エフェクト・トランジションは引き継がれない）。DvcMCP の編集系ツールはこの方式。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:62-64, 78-85 / DvcMCP の server instructions

### 無償版 Resolve は外部スクリプトから繋がらない
- 症状: scriptapp が None。
- 原因: 外部スクリプトは Studio 限定。
- 対策: Studio を使う。アンインストール一覧の表示名はどちらも "DaVinci Resolve" なので、`GetProductName` で確かめる。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP\CLAUDE.md:85 / MEM(DvcMCP)\resolve-environment.md
