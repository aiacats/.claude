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

### Foot IK On の収録モーションで、膝が 2〜4 フレームだけ反った側へ跳ねる（Foot IK を切ると常に反る）
- 症状: Timeline の Humanoid クリップを Foot IK On で流すと、膝が 1 コマで 7〜13 cm 動き、2〜4 フレーム後に戻る（膝の向きが反対へ入れ替わる）。Foot IK Off にすると跳ねは消えるが、膝が常に 5〜14° 反る（逆折れ）。股関節・足首は滑らかで、膝だけが動く。
- 原因: クリップの膝のマッスル（`Left/Right Lower Leg Stretch`）が正規の範囲 −1〜1 を超えている（1.1〜1.26）。マッスル 1 がほぼ伸び切り（春猿火のアバターで 0.9°、膝の角度 = −80 × マッスル + 80.9°）で、超えた分だけ FK の膝が反る。Foot IK は普段は前へ曲げ直すが、FK が反っているフレームの一部で反った側の解を選ぶ。「伸び切りで向きが決まらない」だけではない（IK が選ぶ膝の曲がりは 13〜22° ある）。
- 対策: Foot IK を切らずに、クリップの膝のマッスルを 1 以下に抑える（複製のカーブを `AnimationUtility.SetEditorCurve`）。春猿火で跳ね 135 mm → 17 mm、逆折れ 0、足首・つま先の位置の差 0.1 mm 以下、膝も跳ねたコマ以外は p99 で 2 mm 以内。確かめ方は、Timeline を 1/60 秒ずつ Evaluate して膝の加速度（2 階差分）のうち股関節・足首のどちらよりも大きい分を数える（8 mm 以上を候補）。マッスルの値は `AnimationUtility.GetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), "Left Lower Leg Stretch"))`。
- 実例: 2026-10-14 SinkaiFes2026（春猿火 左 34%・右 9% が 1 超え、MZM の Anjo 右 65%・Kosaka 右 最大 1.26。どれも先に Foot IK Off で凌いでいた）
- 自動検出: 不可（クリップのマッスルの最大値を読めば分かる）
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-14 16:00 の節

### 2 人以上の収録モーションで Remove Start Offset が On だと、2 人が舞台の中央で重なる
- 症状: 同じ収録の 2 人の Animation Track を並べると、番組では左右に分かれて立っているのに、Timeline では 2 人とも中央に重なる。
- 原因: AnimationPlayableAsset の Remove Start Offset（既定 On）が、クリップの最初のルートの位置・向きを打ち消して原点から始める。
- 対策: 複数人のクリップは Remove Start Offset を Off（収録の座標のまま）。FBX の取り込みでも keepOriginalOrientation / PositionXZ / PositionY を On にする（traps-catalog/unity-import.md「複数人の収録モーション…」）。`tl_dump.py`（skill vortex-timeline-setup）で RemoveStartOffset を一覧できる。
- 実例: 2026-10-14 SinkaiFes2026（MZM の Anjo・Kosaka）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-14 01:40・04:35

### .playable.meta の GUID が変わり、シーンから Timeline の参照が切れる
- 症状: シーンの PlayableDirector の Playable が空（Missing）になり、Timeline ウィンドウでも組の Timeline が出ない。.playable 自体は残っている。
- 原因: 作業ツリーで .playable.meta（とシーンの .meta）の GUID が作り直されていた。いつ・何が作り直したかは未特定（.meta を消した状態で Unity が開いた、ファイルを外から置き直した等が考えられる）。
- 対策: `git diff` で .meta の guid の行を見て、コミット時の GUID に戻す（`git checkout -- <.meta>`）。戻す前の差分は控える。Timeline・シーンを他の PC で開いたら、まず `git status` で .meta が変わっていないかを見る。
- 実例: 2026-10-14 SinkaiFes2026（4 組の Timeline と ShinkaiFes2026_Timeline.unity.meta）
- 自動検出: 候補（.meta の guid 行の変更を warn）
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-14 00:10

### Edit モードの Director では、Pause / Stop の通知（OnBehaviourPause・OnPlayableDestroy）がミキサーに届かない
- 症状: 自作トラックのミキサーで「一時停止・停止で元の値に戻す」を EditMode テストで確かめると、何度やっても戻らない（Play では戻る）。
- 原因: Edit モードで PlayableDirector を Evaluate しても、Play（Manual の時間）してから Pause / Stop しても、ScriptPlayable のミキサーに OnBehaviourPause・OnPlayableDestroy・OnGraphStop が呼ばれなかった（ProcessFrame だけ）。手で組んだ PlayableGraph でも同じ。
- 対策: 区間・Ease・入り直しなどは EditMode テストで Director を Evaluate して確かめ、一時停止・停止の戻りは Play で確かめる（PlayMode テストにするか、手で確かめて記録を残す）。手で組んだグラフより Director で評価する方が、クリップの区間と Ease の重みの曲線が実際どおりになる。
- 実例: 2026-10-15 SinkaiFes2026（LightIntensityTrack。Play では区間の中の Pause で 0 → 1 に戻った）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-15 22:55

### Timeline を動かした直後に Render すると、キャラだけ前の時刻のポーズで写る
- 症状: `director.time = t; Evaluate(); camera.Render()` を時刻を変えながら続けて撮ると、カメラの位置と向きはその時刻なのに、キャラの腕・脚が 1 枚前の時刻の形。番組映像と並べると「めちゃくちゃずれている」。
- 原因: スキンメッシュの形は次のコマのプレイヤーループで更新される（Evaluate では骨だけ動く）。カメラの値は書いた時点で効くので、画の中で食い違う。
- 対策: 時刻を合わせたら、その時刻のまま数コマ回して（毎コマ time を戻して Evaluate）`WaitForEndOfFrame` で撮る。撮った画のポーズが参照映像と一致するかを最初の 1 枚で確かめる。
  雛形は skill vortex-timeline-setup の `templates/ShotRunner.cs`（3 コマ回してから撮る）。
- 実例: 2026-10-16 SinkaiFes2026（AZKi の Cam14 の構図合わせで補正量を 2 回誤った。ユーザーに指摘された）。CLAUDE.md の「LateUpdate 中に Render するとスキンメッシュが前フレーム」と同根。
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-16 00:30

### 他分野・skill に置いたもの
- Edit モードの PlayableGraph は Humanoid の骨に書かない → traps-catalog/unity-runtime.md
- DmxClip は Looping を持たない（ループは wrapMode=Loop）／キャラ別 Timeline の Play On Awake が DMX を取り合う／DmxMixerBehaviour.OnGraphStart で実受信が止まる／RT_Output を誰も書かない → skill vortex-timeline-setup・vortex-timeline-export に記載（コード修正の経緯は traps-catalog/vortex.md）
- Override 系トラックの順序、vcam.State の記録に平滑化が乗らない → traps-catalog/vortex.md
- PlayableDirector などシーン参照が Play で切れる → unity-editor の担当

---
出典の略記: VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt / SL = D:\_ProjectBLUE\Project\_vortex\Submod_RealtimeLiveUtility\Submod_RealtimeLiveUtility\.claude\claudeLog.txt / GACHA-MEM = C:\Users\komao\.claude\projects\D---ProjectBLUE-Project-PRBL-Gacha\memory
