---
paths:
  - "**/*.{aep,jsx,jsxbin,jsxinc}"
  - "**/CSXS/**"
  - "**/AEMCP/**"
---

# after-effects の罠

全件は ~/.claude/traps-catalog/after-effects.md。ここは再発しやすいものだけ。

### ExtendScript の正規表現で文字クラスに素のスラッシュを書かない
`/[\\/]+$/` のように `[...]` の中に素の `/` があると JSX 全体が無応答になり、AE を再起動するまで `1+1` も返らない。ES3 のスキャナがそこでリテラルを打ち切るためで、Node vm の契約テストは通ってしまう。→ パス区切りは charAt で書く（書くなら `[\/]`）。実機の往復テストを回す。（実例: 2026-09-16 AEMCP）

### setValueAtTime を 1 キーずつ呼ばない
1000 キーで 10 秒、5000 キーは返らない（キー数の二乗）。nearestKeyIndex の逐次呼び出しも二乗。→ 数値系は `setValuesAtTimes` で一括（1000 キー 30ms）。キー時刻は置き終わってから 1 回読んで二分探索。（実例: 2026-09-17 AEMCP）

### キーのあるプロパティに setValue しない
Source Text などキーがあると、値が同じでも "Can not call setValue() on a property with keyframes." になる。`.value` も再生ヘッド時刻の値を返す。→ `numKeys > 0` を先に見て `setValueAtTime` / `valueAtTime` で時刻を固定する。（実例: 2026-09-16 / 09-17 AEMCP）

### テキストアニメーターの Range Selector
スクリプトで足したアニメーターは Range Selector 無しで生まれ "The range has no values" になる。パスは `Animator 1/Selectors/Range Selector 1`。Shape=`ADBE Text Range Shape` と Mode=`ADBE Text Selector Mode` を取り違えても例外は出ず、範囲が反転するだけ。→ 無ければ `addProperty('ADBE Text Selector')`、matchName は表で持つ。（実例: 2026-09-16 AEMCP）

### ExtendScript の API の小さな癖
省略可能な引数に `undefined` を渡すと拒否される（引数ごと渡さない）。`app.project.save(file)` は別名保存。作成直後の `layer.index` は常に 1（同定は `layer.id`）。`app.fonts.allFonts` は入れ子配列。`saveFrameToPng` は非同期。KeyframeEase の個数は Position=1 / Scale=3。（実例: 2026-09-16 AEMCP）

### renderQueue.render を evalScript から呼ばない
同期レンダーで、書き出しが終わるまで AE ごと固まる。→ aerender を別プロセスで走らせる（出力先フォルダは先に作る）。（実例: 2026-09-17 AEMCP）

### After Effects を強制終了しない
`Stop-Process -Force` の後、次の起動が描画されないモーダル（#32770）で止まる。CPU 0 のまま窓もログも出ない。→ CloseMainWindow で閉じる。止まったらその窓へ WM_CLOSE。（実例: 2026-09-16 AEMCP）

### CEP マニフェストの ScriptPath と StartOn
`<ScriptPath>` を指定すると CEP が JSX を勝手に評価してエンジンを掴み、以後 evalScript が永久に返らない。StartOn の `<Event>` は `com.adobe.csxs.events.ApplicationActivate` と完全修飾にしないと黙って発火しない。→ ScriptPath は使わず、ソースを連結して 1 回の evalScript で流す。（実例: 2026-09-16 AEMCP）
