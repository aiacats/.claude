# unity-gc の罠（カタログ）

Unity の GC スパイク・毎フレームの割り当て・GC の計測・OSC 受信ハンドラの割り当てに関する罠の全件。

### 文字列比較に Ordinal を付ける
- 症状: OSC 受信などで 1 フレーム 27KB 前後の GC。アドレスが一致しないメッセージでも毎回確保される。
- 原因: `StartsWith` / `EndsWith` / `IndexOf(string)` の既定はカルチャ依存比較で、Unity の Mono では呼ぶたびにヒープを確保する。早期リターン用の判定でも確保する。
- 対策: `StringComparison.Ordinal` を必ず指定する。挙動は変わらず割り当てだけ消える。実測で OSC 由来の GC が 23,585 → 12,524 byte/frame（47% 減。1500 msg/s を 22 秒、300 フレーム平均）。
- 実例: 2026-09-06 vortex_urp
- 自動検出: hook `cs-culture-string-compare`
- 出典: rules/unity.md「OSC 受信の作法」 / Notion 3d3e4d4b-751b-8114-908b-f20e662afb9a / VL:972-1030

### 受信ハンドラや Update の中で文字列を組み立てない（アドレスの補間・連結・Debug.Log）
- 症状: ハンドラ 1 回ごとに文字列が確保され、受信レートぶんの GC になる。
- 原因: ハンドラ内の `$"/cinecam/position/{id}"` や `prefix + "/play/"` が毎メッセージ評価される。`Debug.Log($"...")` はフラグで囲っても引数の文字列補間が先に評価される。
- 対策: 比較用のアドレスは `Awake` / `OnValidate` で組み立ててフィールドに持ち、ハンドラ内は等値比較だけにする。ID やプレフィックスが Inspector で変わりうるなら `_builtFrom` のような組み立て元を持ち、変化したときだけ作り直す。`Debug.Log` はフラグで呼び出しごとガードする。
- 実例: 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「OSC 受信の作法」「GC スパイクを起こさないか確認する」 / rules/app.md:167-172 / Notion 3d3e4d4b-751b-8114-908b-f20e662afb9a

### OSC の受信ハンドラは自分宛でないメッセージでも全部呼ばれる
- 症状: リスナーを増やすほど GC と CPU が比例して増える。
- 原因: uOSC の `onDataReceived` に登録したハンドラは全メッセージで呼ばれ、ハンドラ内の処理がリスナー数 × 受信レートに増幅される。FacialManager は 5 体 × 18 本 = 最大 90 回の文字列比較を全メッセージで回していた。
- 対策: ハンドラの冒頭でプレフィックス判定して早期リターンし、関係ないアドレスで後続の if / else if を回さない。
- 実例: 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「OSC 受信の作法」 / VL:972-1030

### uOSC の Message.values は object[]。(float) キャストは int 受信で例外になり受信ループが詰まる
- 症状: GC 33KB/frame のうち 28.6KB が StackTraceUtility（毎フレーム例外）。受信が 1 フレーム 1 通しか処理されない。
- 原因: uOSC は型タグ i を int で箱詰めする。`(float)values[n]` は int が届くと InvalidCastException。uOscServer は例外を捕まえないのでループが止まる。値の取り出し自体もボクシング解除になる（uOSC の設計上避けられない）。
- 対策: int / float の両方を受ける取り出し（OscArgs.TryGetFloat / TryGetInt）を使う。`values[0]` を何度も触らず一度ローカルへ。SinkaiFes2026 では同パターンが他 6 ファイル 111 箇所残っている（横展開未実施）。
- 実例: 2026-09-14 SinkaiFes2026
- 自動検出: 候補 uOSC を使うファイルで `\((?:float|int)\)\s*[\w.]*\.values\s*\[`（patterns-unity-play.md `cs-uosc-values-cast`）
- 出典: SINKAI-LOG:128-157 / rules/unity.md「OSC 受信の作法」

### uOSC のパーサ自体が 1 メッセージごとに確保する（リスナーを直しても残る分）
- 症状: リスナーを直しても 12,524 byte/frame が残る（1500 msg/s）。
- 原因: `udpClient_.Receive()` の byte[]、ParseString と Substring、`new object[n]`、int / float のボクシング。
- 対策: 取り込みパッケージは改造しない方針のため未対応。削るなら embed して改造するか、受信部を自前実装してアドレスの byte 列 → string をキャッシュする。
- 実例: 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: VL:1017-1030

### 毎フレームの例外・警告ログが GC の最大要因になる
- 症状: GC 内訳の大半が StackTraceUtility.ExtractStringFromExceptionInternal や警告ログ（AudioListener 複数、DofMidiControl の NRE 10KB/frame）。
- 原因: 例外とログの文字列生成。
- 対策: Profiler の GC 内訳で、まず例外とログを潰す。
- 実例: 2026-09-14 / 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:139-143, 156-157, 213-218

### GetComponent の失敗が常態だと、Editor ではエラーメッセージ文字列を毎回確保する
- 症状: 7,536 byte/frame の GC（1 フレームの約 17%）。12 回/frame でカメラ台数 + SceneView と一致。
- 原因: 描画パスで `camera.GetComponent<MassiveClouds>()` が大半のカメラで null を返す設計。GetComponent は失敗すると GetComponentNullErrorMessage の文字列を作る（Editor）。
- 対策: `TryGetComponent(out var c) ? c : null`。
- 実例: 2026-09-06 vortex_urp（MassiveCloudsUniversalRPScriptableRenderPass.cs:31）
- 自動検出: 不可（GetComponent 自体は正当な用途が多い）
- 出典: VL:1064-1080, 1098-1150

### 毎フレーム経路でヒープを確保する書き方（一覧）
- 症状: Update / 受信ハンドラ / 入力量に比例するループで GC スパイク。フレーム落ちは原因から遠い場所に出る。
- 原因: 文字列の補間・連結・`ToString()`・`string.Format`、LINQ、インターフェース越しの `foreach`、`params` 配列、毎回 `new` する配列 / List / Dictionary / `WaitForSeconds` / `Vector3[]`、ローカル変数を捕捉するラムダ、`object[]` への値型の出し入れや enum を `Equals`・辞書キーに使うボクシング、確保版 API（`GetComponents<T>()`、`Physics.RaycastAll`、`mesh.vertices`、`Texture2D.GetPixels`、`Camera.main` は内部で毎回タグ検索）。
- 対策: バッファ・リストをフィールドに持って `Clear()` で再利用、非確保版 API（`GetComponents(list)`、`RaycastNonAlloc`、`GetPixelData`）か事前キャッシュ、大きな一時確保（readback・メッシュ操作）は頻度を落とすか非同期に。影響は「頻度 × 割り当て」で見る。
- 実例: （rules/unity.md の一般則。個別の実例は他項目）
- 自動検出: 不可
- 出典: rules/unity.md「GC スパイクを起こさないか確認する」

### OnGUI / Editor の毎リペイントで new GUIStyle・シーン全走査
- 症状: 行数 × リペイント回数の確保。RequiresConstantRepaint の Inspector が Play 中ずっと FindObjectsByType する。
- 原因: OnGUI 内での生成と走査。
- 対策: GUIStyle は静的キャッシュ。走査結果は hierarchyChanged か保持時間で無効化する。
- 実例: 2026-08-24 / 2026-08-25 / 2026-08-27 2609SuiseiTour26
- 自動検出: 不可（OnGUI の中かを正規表現で判定できない）
- 出典: 2609-LOG:1696-1710, 1949-1950, 2256-2257

### RenderTexture.Release() だけではオブジェクトが残ってリークする
- 症状: 定期的に GC.Collect のスパイク（336ms）。
- 原因: 参照を差し替えるたびに Release だけ呼び、Destroy を呼んでいなかった。Release は GPU 側を解放するだけ。
- 対策: `Release()` と `Destroy()` をセットで呼ぶ（Edit モードでは DestroyImmediate）。
- 実例: 2026-08-16 vortex_urp（MassiveCloudsAtmos DynamicRenderTexture）
- 自動検出: 不可（`.Release()` は他の型にもあり誤検知が多い）
- 出典: VL:420-437

### NiloToon Bloom の RenderGraph が毎フレーム TextureHandle[] と文字列を確保する（URP Bloom と二重）
- 症状: RenderGraph 2.1KB/frame。ブルームのピラミッドを 2 回作る。
- 原因: NiloToonUberPostProcessPass.SetupBloomRenderGraph の実装。Volume で URP Bloom と NiloToonBloom が両方有効。
- 対策: Bloom を一本化する（パッケージ改造は要判断）。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:325-330

### GC の測り方
- 症状: 「割り当て 0 バイト」「Editor では 36KB/f」など、測り方次第で誤った結論が出る。
- 原因: `GC.GetTotalMemory()` の差分は分解能が足りず小さい割り当てを取りこぼす。`GC.GetAllocatedBytesForCurrentThread()` は Unity の Mono では常に 0 を返すスタブ。Editor の Play にはエディタ由来の割り当てが乗る（Editor Play 36KB/f に対しキャプチャ解析 4.1KB/f）。
- 対策: Play 中に `ProfilerRecorder(ProfilerCategory.Memory, "GC Allocated In Frame")` を読み、実負荷をかけて前後比較する。本番相当の値は Development Build で測る。回収頻度は `GC.CollectionCount(0)` の差分で見る（スパイクの正体は回収 1 回 13ms でフレームが 40ms に跳ねる、だった）。
- 実例: 2026-09-06 vortex_urp / 2026-09-16 SinkaiFes2026
- 自動検出: hook `cs-gc-alloc-thread-stub`
- 出典: rules/unity.md「Unity で GC を測るとき」 / Notion 3d3e4d4b-751b-8114-908b-f20e662afb9a / SINKAI-LOG:431-437

### Deep Profile でないと、リスナーの割り当ては呼び出し元のサンプルに合算される
- 症状: `uOscServer.Update()` が全体の 60% に見える。
- 原因: Deep Profile でないとリスナーのメソッドは個別サンプルにならない。uOSC のパースは別スレッドなので Update() の中身ですらなく、実体は登録済みリスナー 15 個の割り当てだった。
- 対策: サンプル名を額面どおりに読まない。Deep Profile か、下記の Scripts マーカーで原因を直接見る。
- 実例: 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「Unity で GC を測るとき」 / rules/app.md:173-175 / Notion 3d3e4d4b-751b-8114-908b-f20e662afb9a

### ProfilerRecorder は Scripts カテゴリのマーカーも読める（単位は ns）／HierarchyFrameDataView に GetItemParent が無い
- 症状: GC Allocated In Frame 以外で特定の原因を追えない。親をたどる API が無く走査が組めない。
- 原因: API の仕様。
- 対策: `ProfilerRecorder(ProfilerCategory.Scripts, "GetComponentNullErrorMessage")` のようにマーカーの有無で原因を直接見る（値はバイトではなく時間）。階層は走査しながら親名を持ち回る。巨大な `.data` で Profiler ウィンドウが固まるときは `ProfilerDriver.LoadProfile` + `GetHierarchyFrameDataView` で `HierarchyFrameDataView.columnGcMemory` を集計する Editor スクリプトを書く。
- 実例: 2026-08-16 / 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: VL:411, 1141-1143 / rules/unity.md「Unity で GC を測るとき」

### uOSC の GameObject を Inspector で選択していると計測が狂う
- 症状: 計測中の GC が実際より多い。
- 原因: 選択中は `uOscServerEditor` が全メッセージを Queue に貯める。
- 対策: 計測時は選択を外す。
- 実例: 2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「Unity で GC を測るとき」

### 他分野・skill に置いたもの
- Recorder_VRMBlendShapeProxy / Recorder_camera の毎フレーム new float[] → traps-catalog/vortex.md

---
出典の略記: 2609-LOG = D:\_ProjectBLUE\Project\2609SuiseiTour26\log\claudeLog.txt / SINKAI-LOG = D:\_ProjectBLUE\Project\SinkaiFes2026\log\claudeLog.txt / VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt
