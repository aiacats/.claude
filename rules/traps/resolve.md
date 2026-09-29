---
paths:
  - "**/*.drp"
  - "**/DvcMCP/**"
---

# resolve の罠

全件は ~/.claude/traps-catalog/resolve.md。ここは再発しやすいものだけ。

### モーダル中の API は例外でなく None を返す
起動直後の更新案内などのダイアログが出ていると、ImportMedia・SetSetting などが全部 None で黙って失敗する。→ 書き込みの戻り値を必ず見て None と False を区別し、`GetCurrentPage()` が None ならダイアログを疑う。（実例: 2026-09-23 DvcMCP）

### フレームの約束が API の説明文と違う
`GetRightOffset()` はソース Out を含まず、`AppendToTimeline` の endFrame は含む。そのまま渡すと区間が 1 フレームずれる。→ 内部は [start, end) で持ち、渡す直前に -1。（実例: 2026-09-23 DvcMCP）

### SetClipsLinked は 1 組 75ms
300 件で 39 秒かかる。→ 同じ区間の V+A は mediaType 無しで 1 件として Append すれば Resolve がリンクして置く（3.5 秒）。（実例: 2026-09-23 DvcMCP）

### 音声だけのクリップに Frames は無い
WAV は "Duration"（プロジェクト fps のタイムコード）しか持たない。→ Duration から数える。（実例: 2026-09-23 DvcMCP）

### メディアの長さは取り込み時点で固定
素材ファイルを作り直してもメディアプールは古い長さのまま。→ 作り直したら入れ直す。（実例: 2026-09-23 DvcMCP）
