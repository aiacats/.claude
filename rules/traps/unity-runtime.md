---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
---
# unity-runtime の罠

全件は ~/.claude/traps-catalog/unity-runtime.md。ここは再発しやすいものだけ。

### GetComponent に ?? を使わない
null を避けたはずが後で `MissingComponentException`。原因は Unity の偽 null が C# の `??` / `?.` を素通りすること。→ `TryGetComponent(out var c)` か `if (c == null)`。UnityEngine.Object 全般に `?.` を使わない。（実例: 2026-09-24 ModelChecker で 2 回）

### 受信スレッドから Debug.Log を呼ばない
Play 投入やドメインリロードでハングし、"Access version should be odd when acquiring lock" で Editor.log が 3.7GB になる。原因は abort された受信スレッドが ThreadAbortException を捕まえて `Debug.LogException` し、ログのロックを奪い合うこと。→ ログは ConcurrentQueue 経由でメインで出す。ThreadAbortException は黙って抜ける。OnDisable でスレッドを止める。（実例: 2026-08-04, 08-05 2609SuiseiTour26）

### ビルドでだけ動かない（OnValidate・Start の順序）
Editor の Play では動くのにビルドで無反応。原因は OnValidate が Player で呼ばれないこと、Start 同士の順序が Editor と Player で違うこと。→ 初期化を OnValidate に頼らない。依存は使う時点で解決するか `[DefaultExecutionOrder]` で明示。（実例: 2026-08-05 2609SuiseiTour26 / 2026-02-05 MARQ-Studio）

### Find 系 API の仕様差
並びが毎回変わり ID が別物を指す／非アクティブが黙って登録漏れ。原因は `FindObjectsSortMode.None` が順序不定、`FindObjectOfType` が非アクティブを拾わない（`Resources.FindObjectsOfTypeAll` は逆にプレハブ資産まで拾う）こと。→ ヒエラルキー順でソートしてから ID を振る。`FindObjectsInactive.Include` を使い、見つからなければ警告。（実例: 2026-08-30 2609SuiseiTour26 / 2026-09-16 SinkaiFes2026）

### eulerAngles は書いた値を返さない
(100,0,0) を書くと (80,180,180) が返り、読み直して表示すると触っていない軸が飛ぶ。原因は実体が Quaternion であること。→ 四元数のなす角で同一判定し、書いた向きは自分で保持する。（実例: 2026-09-08 2609SuiseiTour26）

### Input System の入力の罠
スキャンコード無しの `keybd_event` や win-gui の key_press は届かず「実装が動いていない」ように見える（Alt+F4 だけ効く）。Value アクションは 0 や Disable で canceled になり、MIDI が黒へ跳ぶ。→ `KEYEVENTF_SCANCODE` で送る。PassThrough にして performed だけ購読する。（実例: 2026-08-25 2609SuiseiTour26 / 2026-09-25, 09-15 SinkaiFes2026）

### ランタイム IMGUI は Editor と別物
ビルドでラベルが折り返して欠け、Display 2 以降には何も出ない。原因は `GUI.skin.label` の wordWrap 既定 ON と CalcSize の数 px 不足、OnGUI が Display 1 固定であること。→ wordWrap=false + TextClipping.Overflow。他ディスプレイは UI Toolkit か Canvas。（実例: 2026-08-25 2609SuiseiTour26 / 2026-09-15 SinkaiFes2026）

### UI Toolkit で文字だけ出ない・グリフが違う
ランタイムの PanelSettings にテーマ（.tss）が無いと Label の文字だけ出ない。`-unity-font` は継承された FontAsset に負けて別グリフになる（警告なし）。→ `@import url("unity-theme://default");` の .tss を割り当てる。フォントは `-unity-font-definition`。（実例: 2026-06-21 ReLink / 2026-06-01 LiveMultiRecorder）

### Edit モードの PlayableGraph は Humanoid の骨に書かない
`SetTime` + `Evaluate` しても骨が動かない（差 0°）が、GUI 再生では動いて見える。→ Edit モードでは `AnimationClip.SampleAnimation`。当てた直後に動いたかをテストで測る。（実例: 2026-09-24 ModelChecker）

### UniTask を WhenAny の後に再び await しない
`Not yet completed, UniTask only allow to use await.` で状態ループが死に、以降入力が効かない。原因は UniTask が 1 回しか await できず WhenAny が消費すること。→ 2 回以上待つなら `.AsTask()` + `Task.WhenAny`。（実例: 2026-05 vortex_urp）
