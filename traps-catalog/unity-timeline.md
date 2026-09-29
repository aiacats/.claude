# unity-timeline の罠（カタログ）

Timeline・PlayableDirector・PlayableGraph・Recorder・Cinemachine の罠の全件。

### PlayableDirector.Resume() は PlayableGraph が未生成だと効かない
- 症状: 再生を指示しても state=Paused のまま時間が進まない。エラーなし。
- 原因: playOnAwake=false で一度も再生していない director には graph が無い。Resume は既存 graph の再開なので何もしない。
- 対策: `director.playableGraph.IsValid()` で分岐し、無ければ `director.Play()` で作る。頭出しは initialTime に入れてから／頭出しした time を戻す。
- 実例: 2026-09-05 / 2026-09-06 vortex_urp（TimelineManipulator）
- 自動検出: 候補 `\w*[Dd]irector\w*\.Resume\(\)` かつファイルに `IsValid\(` が無い（patterns-unity-play.md `cs-director-resume`）
- 出典: VL:826-829, 857 / Notion 3d2e4d4b-751b-8114-b02c-e1a7d40d6dd2

### Timeline のトラックバインドはクリップではなく、ミキサーの playerData に渡る
- 症状: Timeline で再生すると画角が 1 つしか出ない（スイッチングもフェードも再現されない）。
- 原因: クリップ側の ProcessFrame で playerData を受けていたが、そこでは null になる。
- 対策: `TrackAsset.CreateTrackMixer` をオーバーライドし、ミキサー側で playerData を受けて駆動する。
- 実例: 2026-06-18 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:1469-1476

### clipCaps = None のクリップは Split すると右側が頭から再生し直される
- 症状: Split やトリムをしても正しく分割されない。
- 原因: ClipIn を宣言しないと Timeline は clip-in を 0 に固定する。
- 対策: `clipCaps => ClipCaps.ClipIn | ClipCaps.SpeedMultiplier`。サンプリングは `input.GetTime()` で行う。
- 実例: 2026-06-18 Submod_RealtimeLiveUtility
- 自動検出: 不可（時刻を使わない状態クリップでは None が正当）
- 出典: SL:1528-1534

### ClipBackgroundRegion.startTime / endTime は「クリップ相対」ではなく「ソースローカル時刻」
- 症状: トリムや速度変更をしたクリップで、マーカーの位置がずれる。
- 原因: ドキュメントには「relative to the clip」とあるが、実装は `clip.ToLocalTimeUnbound()` を通した値を渡している。
- 対策: clipIn と timeScale を適用済みの時刻として扱う。
- 実例: 2026-08-20 vortex_urp
- 自動検出: 不可
- 出典: VL:598-601

### オブジェクトを置き換えると Timeline のバインドが黙って外れる
- 症状: ステージを差し替えた後、演出の一部が動かない（エラーなし）。
- 原因: Activation / Animation トラックのバインドがシーンオブジェクトを直接指している（1 本の Timeline に 52 本など）。
- 対策: 親を残してメッシュ・マテリアルだけ入れ替える。差し替え後に各 Timeline のバインド欠けを確認する。Timeline を複製したら参照側と Director の両方を同じアセットに向ける。
- 実例: 2026-09-16 PRBL_Gacha
- 自動検出: 不可
- 出典: GACHA-MEM/gacha-cg-asset-swap.md:167, 180-181

### 毎フレーム記録した AnimationCurve がゼロタンジェントと四元数の符号反転でカクつく
- 症状: 記録した .anim を再生するとカクつく（時々ひどい）。収録中のライブは滑らか。
- 原因: `new Keyframe(t, v)` は in / out タンジェントが 0 なので、キーごとに速度が 0 になる。rotation は q と -q の間で符号が反転し、その瞬間だけ大きく振れる。
- 対策: 直前のキーとの Dot が負なら符号を反転して連続させる。タンジェントは隣のキーへの傾き（線形）。離散値は ∞ タンジェントのステップにする。
- 実例: 2026-06-18 Submod_RealtimeLiveUtility
- 自動検出: 不可（2 引数の Keyframe は静的カーブでは正当）
- 出典: SL:1539-1551

### Recorder の入力 ActiveCamera は Built-in 専用。URP では開始に失敗する
- 症状: `Recording failed. ActiveCamera is only compatible with the Legacy Render Pipeline.`
- 原因: 入力の種類の制約。
- 対策: MainCamera / TargetCamera / RenderTexture の入力を使う。点検で「ActiveCamera かつ currentRenderPipeline != null」をエラーにする。vortex のシーンは MainCamera タグが 0 台のことがあるので RT 入力が素直。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 候補 `ImageSource\.ActiveCamera|ActiveCameraInputSettings`（patterns-unity-play.md `cs-recorder-activecamera`）
- 出典: VL:1643-1661

### URP の RT 入力から Recorder で PNG 連番を書き出すと全面透明になる
- 症状: RGB には絵があるのに、アルファが 0 の連番になる。
- 原因: Recorder は PNG / EXR を必ず RGBA32 で読み戻す。RenderTextureInput は RecordTransparency を見ずに RT をそのまま渡す。URP の不透明描画は RT のアルファを 0 のままにする。
- 対策: JPEG・動画・カメラ入力に切り替える。点検で警告する。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: VL:1723-1728

### Recorder API の罠（OutputFile の setter でファイル名が消える／Controller が設定を上書き／DontSave のリーク）
- 症状: 連番画像で全フレームが同じファイルに上書きされる。Recorder 側に設定した FrameRate が効かない。RecorderSettings が溜まっていく。
- 原因: OutputFile の setter は `FromPath()` でファイル名を丸ごと置き換える。`AddRecorderSettings` → `ApplyGlobalSetting` が Controller 側の値で上書きし、DontSave を立てる。
- 対策: 連番では `DefaultWildcard.Frame` を自分で付ける。FrameRate などは Controller 側に設定する。停止時に DestroyImmediate する。検証は `IEncoderSettings.ValidateRecording` で行う（HasErrors は外から呼べない）。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: VL:1434-1445

### 書き出しの終端を時間や Time.frameCount で判定すると、Loop でラップする・フレームが欠ける
- 症状: Loop の Timeline が無限に録り続ける。「完了・失敗 0 件」なのに 2626 フレームのはずが 1440 枚しかない。
- 原因: captureDeltaTime が 1/FrameRate 刻みなので、余裕を持たせた時間判定では終端を跨ぐ。Game View が無いか裏にあると描画されないのに Update だけ回って frameCount が進む。
- 対策: `SetRecordModeToFrameInterval(0, n-1)` にし、Recorder が実際に録ったフレームを数えて止めるのに任せる。実行前に Game View を開いて前に出す。`Time.renderedFrameCount` が進まなければ打ち切る。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: VL:1453-1460, 1712-1722

### Recorder の音声はスピーカー構成が Mono / Stereo 以外だとエラー
- 症状: 音声付きの書き出しが失敗する。
- 原因: `AudioRecorderSettings.kSupportedSpeakerModes = {Mono, Stereo}`。
- 対策: 点検で AudioSettings のスピーカー構成を確かめる。有効な AudioListener があるかも確かめる。
- 実例: 2026-09-24 vortex_urp
- 自動検出: 不可
- 出典: VL（2026-09-24 13:50 の節「書き出しに音声を載せる」）

### Play 中のドメインリロードで Editor 側のジョブが黙って飛ばされ、Recorder は止まらない
- 症状: ジョブがスキップされるが、Recorder のセッションは DontDestroyOnLoad で生き残る。前のファイルが未完結のまま残る。
- 原因: Editor 側の状態（参照）はリロードで消えるが、ランタイム側のオブジェクトは残る。
- 対策: `_started` をシリアライズしておき、復帰時に「開始済みなのに controller が無い」状態を検出したら、そのジョブを失敗として全体を中断する。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: VL:1461-1464

### Cinemachine 2 の Brain は、vcam のレイヤーと出力カメラの cullingMask で候補を絞る
- 症状: 新しい vcam を足すと PGM / PRV を奪う、または拾われない。
- 原因: `CinemachineCore.UpdateAllActiveVirtualCameras` の layerMask で絞り込まれる。ライブ用の vcam は Priority 10。
- 対策: 番組外のカメラは Camera_ServiceA〜C のレイヤーにするか、Priority 0 にする。
- 実例: 2026-08 vortex_urp
- 自動検出: 不可
- 出典: VL:657-663

### 他分野・skill に置いたもの
- Edit モードの PlayableGraph は Humanoid の骨に書かない → traps-catalog/unity-runtime.md
- DmxClip は Looping を持たない（ループは wrapMode=Loop）／キャラ別 Timeline の Play On Awake が DMX を取り合う／DmxMixerBehaviour.OnGraphStart で実受信が止まる／RT_Output を誰も書かない → skill vortex-timeline-setup・vortex-timeline-export に記載（コード修正の経緯は traps-catalog/vortex.md）
- Override 系トラックの順序、vcam.State の記録に平滑化が乗らない → traps-catalog/vortex.md
- PlayableDirector などシーン参照が Play で切れる → unity-editor の担当

---
出典の略記: VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt / SL = D:\_ProjectBLUE\Project\_vortex\Submod_RealtimeLiveUtility\Submod_RealtimeLiveUtility\.claude\claudeLog.txt / GACHA-MEM = C:\Users\komao\.claude\projects\D---ProjectBLUE-Project-PRBL-Gacha\memory
