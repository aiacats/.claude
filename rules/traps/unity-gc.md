---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
---
# unity-gc の罠

全件は ~/.claude/traps-catalog/unity-gc.md。ここは再発しやすいものだけ。

### 文字列比較に Ordinal を付ける
一致しないメッセージでも毎回 GC が出る。原因は `StartsWith` / `EndsWith` / `IndexOf(string)` の既定がカルチャ依存比較で、Unity の Mono では呼ぶたびにヒープを確保すること。→ `StringComparison.Ordinal` を必ず付ける。OSC 由来の GC が 47% 減った。（実例: 2026-09-06 vortex_urp）

### 受信ハンドラの中で文字列を組み立てない
受信レートぶん GC が積み上がる。原因は uOSC のハンドラが自分宛でないメッセージでも全部呼ばれ、`$"/cinecam/position/{id}"` や連結が毎回評価されること。`Debug.Log($"...")` はフラグで囲っても補間が先に走る。→ アドレスは `Awake` / `OnValidate` で組んでフィールドに持ち、冒頭でプレフィックス判定して早期リターン。（実例: 2026-09-06 vortex_urp）

### uOSC の values を (float) でキャストしない
GC の大半が StackTraceUtility で、受信が 1 フレーム 1 通しか進まない。原因は int タグの値を `(float)values[n]` して毎回 InvalidCastException、uOscServer が例外を捕まえずループが止まること。→ int / float 両方を受ける取り出し（TryGetFloat 等）を使う。（実例: 2026-09-14 SinkaiFes2026）

### 毎フレームの例外・失敗が GC の最大要因になる
GC 内訳の大半が例外・警告ログの文字列生成。GetComponent が失敗し続けるだけでも Editor ではエラーメッセージを確保する（カメラ台数ぶん 7.5KB/frame）。→ 内訳でまず例外とログを潰す。失敗が常態の取得は `TryGetComponent`。（実例: 2026-09-15 SinkaiFes2026 / 2026-09-06 vortex_urp）

### RenderTexture は Release だけでなく Destroy する
定期的に 336ms の GC スパイク。原因は Release が GPU 側しか解放せず、差し替えのたびにオブジェクトが残ること。→ `Release()` と `Destroy()` を対で呼ぶ。（実例: 2026-08-16 vortex_urp）

### GC の測り方
「0 バイト」や桁違いの値で誤判断する。原因は `GC.GetTotalMemory` の分解能不足、`GC.GetAllocatedBytesForCurrentThread` が Mono では常に 0 のスタブ、Editor Play にはエディタ分が乗ること（36KB/f 対 4.1KB/f）。Deep Profile でないとリスナーの割り当ては呼び出し元（`uOscServer.Update()` 等）に合算される。→ Play 中に `ProfilerRecorder(ProfilerCategory.Memory, "GC Allocated In Frame")` を読んで前後比較、本番相当は Development Build で。uOSC の GameObject は選択を外して測る。（実例: 2026-09-06 vortex_urp / 2026-09-16 SinkaiFes2026）
