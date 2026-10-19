# System の塊の構成と配線（vortex 共通）

Submod_RealtimeLiveUtility（`jp.pjblue.realtime-live-utility`、namespace `vortex`）でライブを回すシーンの、System の塊の中身と、
シーンの Inspector で結ぶ配線。2026-10-19 に SinkaiFes2026（System_GrandStage / System_PrimeStage）と vortex_urp（System）のシーンの YAML と、
サブモジュールのソースで確かめた。今のシーンの値は `scene_audit.py dump --root System --depth 2` と `wiring` で読む。

## 塊の形

| 置き場（System の下） | コンポーネント | 役目 |
|---|---|---|
| `Controller` | ExternalControlManager | MIDI などの機器 → ExternalControl（CharacterActivator・EffectControllerMIDI・MeshActivator）。`_controlDevices` の Target Script が空だと黙って効かない |
| `Controller/LookatController` | LookatManager・CameraLookatController | カメラの注視先の一覧（`_lookatTargets`）と、OSC `/cameraswitcher/lookat` |
| `Controller/ObjectActivator` | CharacterActivator | キャラの出し入れ（枠 `_characters[]` × 予備 `_reserveCharacters[]`） |
| `Controller/MeshActivator` | MeshActivator | メッシュの出し入れ（OSC `/meshactivator`）。無いシーンもある |
| `Controller/Between`・`Center`・`Center_up` | BetweenPosition / Transform だけ | 固定の注視先（LookatManager の先頭 3 つ） |
| `Controller/OSC` | uOscServer（8001） | OSC の受信。受け手はすべて `onDataReceived` の永続リスナー |
| `Controller/Mic Controller` | MicController（vortex_urp の古いシーンは MicOffsetControl） | マイクを持つ腕・握り。OSC `/mic/...` |
| `Controller/Facial` | OscServerEx（9100）→ OscReceiverEx → vortex_GamepadOscReceiver | パッドの入力（vortex_FacialController が読む）。AZKi 系だけ |
| `Camera/VirtualCamera` | VirtualCameraSwitcher・CameraSwitcherController | スイッチャー。子が入力カメラ（VirtualCameraChief、その子に vcamRail・vcam_N = VirtualCameraGenerator） |
| `Camera/RenderCamera/Camera_PGM`・`Camera_PRV` | Camera・CinemachineBrain | 番組（PGM）と予備（PRV）。出力は RT（RT_CameraA / RT_CameraB） |
| `Camera/Canvas/SwitcherUI-Canvas` | Canvas（Overlay） | 操作画面。ProgramOut・PreviewOut・ボタン |
| `Camera/Canvas/Output-Canvas` | Canvas（Overlay） | 番組の出力画面 |
| `Camera/RemoteCamera` | プリセットのカメラ群 | 多くのシーンで無効 |
| `Effect` | EffectControllerMIDI ほか | 演出 |
| `Client - OptiTrack` | OptitrackStreamingClient | モーキャプの受信（ServerAddress / LocalAddress / Unicast） |
| `LightControler` | MetaDmxReceiver・FixtureController | Art-Net → 灯体（VF_*） |

System の外（ルート）に置く部品: `DofMidiControl`（プレハブ。番組の被写界深度）、全体の `volume`（Global Volume）、照明（`Lighting`）、
ステージ（`BG_*`）、VJ、水（Crest の `Water`）、LED などの出力カメラ（`Main Camera (n)` + Canvas）、キャラ置き場 `Character`、Timeline の Director。

SinkaiFes2026 の System は vortex_urp の System と同じ構成で、プレハブではなくシーンの物（`VirtualCamera`・`RemoteCamera` も展開済み）。
vortex_urp は `VirtualCamera`・`RemoteCamera` がプレハブのインスタンス。どちらも `scene_audit.py` は同じに読める（プレハブの上書きも当てて読む）。

## 配線（シーンの Inspector で結ぶ物）

| 結ぶ物 | 場所（フィールド） | 結ばないと |
|---|---|---|
| OSC の受け手 | uOscServer `onDataReceived` の永続リスナー: CharacterActivator.OnOscDataReceived・MicController.OscOnDataReceived・CameraSwitcherController.OnOscDataReceived・CameraLookatController.OnOscDataReceived・DofMidiControl.OnReceived・キャラごとに OscRx_LipSync.OscOnDataReceived と FacialManager.OscOnDataReceived | 届かない（エラーは出ない）。各コンポーネントの `_isOsc` が Off なら届いても捨てる |
| 出し入れ | CharacterActivator `_characters[i]._reserveCharacters[j]` の `_targetCharacter`・`_lookatBone_hip`・`_secondary`・`_in_effect`・`_out_effect` | hip が空だと On/Off しない（ControlActive が何もしない）。エフェクトが空だと開始時と切り替えのたびに "Activate Effect is Null" |
| 出し入れの後始末 | CharacterActivator `_lookatManager`・`_cameraSwitcher`・`_betweenPosition` | 出し入れの後に注視先を数え直さない。`_cameraSwitcher` が無効の GameObject か、入力カメラ・vcam（`_vCams`）に無効・None があると、開始時と出し入れで VirtualCameraGenerator.ApplyValues が NullReferenceException（`_vcamOffset` は Awake で作る） |
| 注視先 | LookatManager `_lookatTargets[]` の `_hip`・`_head` | どちらかが空の注視先は飛ばされる。CharacterActivator が On/Off する hip の下に入っていないと、消しても注視先から外れない |
| スイッチャー | VirtualCameraSwitcher `_activeCamera`（PGM の Brain）・`_reserveCamera`（PRV）・`_renderTexA`・`_renderTexB`・`_previewImage`・`_inputCameras[]` | `_inputCameras` に None があるか 9 個未満だと Start で例外（[8] をハンディに使う）。`_renderTexA` / `_renderTexB` は操作画面のプレビュー（`_previewImage`）に映すだけ。並びはカメラ記録の番号と名前で当たる（vortex-timeline-setup の `camrec.py order`） |
| 番組の被写界深度 | DofMidiControl `_switcher`・`_pgmBrain`・`_prvBrain`・`_pgmVolume`・`_prvVolume` | `_switcher` が空だと LateUpdate が毎フレーム例外。Volume は 2 つとも揃ったときだけ Start が DoF を取る（片方が空なら両方とも動かさない）。Brain が空ならその側のピントの距離が 0。Volume のレイヤーはプレハブでは PGM 24・PRV 25 で、カメラの Volume Mask（PGM Default + 24 / PRV Default + 25）と対 |
| マイク | MicController `_targets[]`: `_targetAnimator`・`_handOption`・`_microphoneObjects`・`_gripPosePreset`・`_micTransform`・`_mouthTransform`・`_correctionMode` | Auto で口・マイクが空だと Auto が効かない。握りのプリセットは HumanBodyBones 24〜38 が左手・39〜53 が右手で、手を問わずそのまま当たる |
| 照明 | MetaDmxReceiver `OnMetaDmx` → FixtureController.OnMetaDmx、`_useTimeline` | Use Timeline が On だとライブの Art-Net を流さない（Timeline の DMX 用。ライブは Off）。MetaDmxReceiver を 2 つ置くと 2 つ目は 6454 の bind に失敗する |
| マイクの Animator | MicController `_targets[]._targetAnimator` が空でも `_additionalTargetAnimators` があればそちらを使う（GetReferenceAnimator） | 両方とも空だと腕も握りも動かない |
| モーキャプ | キャラの OptitrackSkeletonAnimator `StreamingClient`・`SkeletonAssetName`・`DestinationAvatar` | StreamingClient が空なら有効な OptitrackStreamingClient を探す。無ければ Error を出して自分を無効にする |
| パッドの表情 | vortex_FacialController `_controllerLabel`・`_proxy` と、シーンの vortex_GamepadOscReceiver | 受信側が無い・ラベルが空だと入力が届かない |
| 水 | Crest WaterRenderer `_Camera` | 空なら Camera.main（MainCamera タグ）を基準にする |
| 出力 | Output-Canvas / SwitcherUI-Canvas の RawImage（マテリアル SwitchTexture.mat が RT A / B を混ぜる）、LED カメラの RT と Canvas | RT_Output（`_outputRenderTexture`）には誰も書かない（VirtualCameraSwitcher の Blit はコメントアウト）。RT_Output をマテリアル無しで映すと黒い |

## OSC のアドレス（ソースで確かめたもの）

| 受け手 | アドレス |
|---|---|
| CharacterActivator（`_isOsc` On のとき） | `/ModelActivate n`（トグル）・`/characteractivator/{n} reserve [withEffect]`・`/characteractivator/query`。同じ GameObject の uOscClient へ `/characteractivator/state/{n}` を送り返す |
| OscRx_LipSync | `/lipsync/phoneme/{a,i,u,e,o}/{characterID}` |
| FacialManager（機器が Osc_XBox / Osc_StreamDeck のとき） | `/facial/...`（oscFacialID で分ける）。機器が XBox・StreamDeck・Joycon・AnyDevice なら OSC ではなく Rewired |
| MicController | `/mic/{n}/{enable,toggle,hand,correctionMode,...}`・`/mic/all/enable` |
| CameraSwitcherController | `/cameraswitcher/{cut,fade,camera,direct,fov,handyposY,pantilt,speed,dof}` |
| CameraLookatController | `/cameraswitcher/lookat` |
| DofMidiControl | `/cameraswitcher/autoDof` |
| MeshActivator | `_addressPrefix`（既定 `/meshactivator`） |

uOscServer と OscServerEx はどちらも uOSC の Udp で、ReuseAddress を付けずに bind する。同じポートを 2 つ開くと 2 つ目は bind に失敗して LogError を出し、何も受けない。
MetaDmxReceiver（ArtNetReceiver）も 6454 を同じように bind するので、2 つ目は受けられない（MetaDmxReceiver が SocketException を捕まえて LogError）。

## キャラの出し入れ（出うるキャラ・開始時に見えるキャラ）

- CharacterActivator の ApplyActive が切り替えるのは、キャラの子の Renderer の enabled・Lookat Bone_hip の SetActive・`_secondary` だけ。
  キャラのルートの有効は変えない。ルートが無効のまま枠に入れても出ない（無効なのが hip そのものなら、hip を有効にして出る）。
- Timeline で出すなら Activation Track でルート（か親）を有効にする。Animator などキャラの中の物に結んだトラックは、ルートを有効にしない。
- 開始時（Start の IntializeCharactersState）は各枠の予備 [0] を出し、ほかを消す。別の枠のキャラ、枠に入っていない有効なキャラは一緒に出る。
- Play On Awake の Director の Character Activation トラック（ミュートでない物）が受け持つ枠は、Start で InitializeHidden（全員消える）から始まる
  （CharacterActivationTrack.CreateTrackMixer → ClaimTimelineControl。受け持つ枠はクリップの characterIndex）。
- Lookat Bone_hip が空の予備は ControlActive / SetActiveImmediate が何もしないので、シーンの状態のまま（有効なら出たまま）。
- 開始時に一緒に見えるキャラどうしで、OscRx_LipSync の characterID・FacialManager の oscFacialID・OptiTrack の SkeletonAssetName・
  vortex_FacialController の `_controllerLabel` が重なると、同じ入力で一緒に動く。同じ演者の衣装違いは同じ枠の予備に入れる。

## キャラの描画の作法

- キャラの Renderer は Rendering Layer をキャラ用（SinkaiFes2026 は Character、vortex_urp は Charactor）にし、キャラ用ライトだけを受ける。
  キャラ用の Rendering Layer を含むライトが無いシーンへ持ち込むと真っ黒（traps-catalog/vortex.md）。
- GameObject のレイヤーは案件の決まりに合わせる（SinkaiFes2026 は Chara、vortex_urp はキャラごとのレイヤー）。
  CharacterSetup のウィンドウは GameObject のレイヤーを設定しない（vortex-character-setup の VortexCharTool.SetupCharacterEx は渡せる）。
- 番組カメラ（PGM / PRV）の Culling Mask にキャラのレイヤーが無いと、そのキャラは番組に写らない。

## 読み違えやすい物

- LookatManager の `_activeTargets`・`_activeTargetNames` は実行時の一覧（ReadOnly で保存されるが、Awake の Initialize で作り直す）。
  ここに残った None や消したキャラは害が無い。点検するのは `_lookatTargets`。
- CharacterActivator の `_currentCharacter` も表示用（開始時の表示では更新されない）。
- `Camera/VirtualCamera/RemoteCam/CineRemote` に `m_Script: {fileID: 0}` の Missing Script が 2 つある（SinkaiFes2026 の System を持つどのシーンも同じ。前からある）。
