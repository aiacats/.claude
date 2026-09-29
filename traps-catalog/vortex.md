# vortex の罠（カタログ）

vortex 系ライブ案件（Submod_RealtimeLiveUtility / Submod_RealtimeLighting、VF_* 灯体、OscRx_*、ArtNetReceiver、CharacterActivator 等）に共通する罠の全件。vortex-* skill に書いてある罠は skill が正で、ここには「skill に記載」とだけ置く。

## 灯体（VF_* / VirtualFixture）

### VirtualFixtureValueProfile は名前ではなく添字で _fixtureAttributes に対応する
- 症状: 並びが AddModeList とずれた Profile で、値域が別チャンネルに入る（VFVP_DRGB は同値のため顕在化せず）。
- 原因: ReadProfile が `_values[i]` → `_fixtureAttributes[i]` で対応づける。
- 対策: Profile は AddModeList と同じ順にする。チャンネル追加時は Profile も同位置に挿入する。「Generate Values from Script」で作り直す。
- 実例: 2026-08-25 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1984-1988

### Profile 未設定・isLerp OFF の灯体は Pan / Tilt / Zoom 等が一切効かない
- 症状: VF_MovingGobo 13 台が動かない。
- 原因: 基底は isLerp OFF のとき lerpPacket に 0 を渡す。Profile 無しは min=max=0。
- 対策: 正規化値で駆動する ch は isLerp ON の Profile を割り当てる。
- 実例: 2026-08-25 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1976-1982

### AddModeList のモード名重複で TryAdd が黙ってチャンネルを落とす（VF_Aura）
- 症状: 26ch のはずが 16ch。後半（Shutter / Dimmer / Color）が欠落。
- 原因: "Fx1Select" が 11 重複し、`_funcList.TryAdd` が false で未登録。
- 対策: 新灯体はモード名の一意性を確認する。VF_Aura は未修正のまま（使う前に要修正）。
- 実例: 2026-08-12 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1384-1387, 1716

### VF_DRGB 等: materialIndex 範囲外・色プロパティ不在（既定 _EmissionColor）で無言スキップ
- 症状: 色が変わらない。TargetMaterial 欄に何も入らない（移植時の設計変更）。
- 原因: HasProperty=false や範囲外を警告なしで飛ばしていた。
- 対策: 警告を出す実装に修正済み。`_BaseColor` を使うシェーダでは Inspector で設定する。VF_RGB の Material Index 既定は 1 → 0 に変わった点に注意。
- 実例: 2026-08-12 / 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1322-1328, 1923-1926

### VF_MobingPar の TargetType は未使用（Light と Material の両方が駆動される）
- 症状: TargetType で片方を選んだつもりが両方効く。
- 原因: どこからも読まれていないフィールドだった（削除済み）。
- 対策: 片方だけ動かしたいなら、動かしたくない側を未設定にする。
- 実例: 2026-08-26 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:2215-2238

### VF_Laser の `(int)packet * 255` で色が飽和、VirtualFixture.WriteProfile の `i > Count`
- 症状: レーザーの色が 0-255 → 0-65025 相当に飽和。WriteProfile で IndexOutOfRange。
- 原因: キャストの位置と境界条件の誤り。Kamitsubaki のコピーでだけ修正済みで、他案件の submodule に残っている可能性がある。
- 対策: `PacketToChannel(packet)` を使う／`i >= Count`。直すと既存プロファイルの見え方が変わる旨を報告する。
- 実例: 2026-03-05 EXT_Kamitsubaki_Composite
- 自動検出: 候補 `\(int\)\s*packet\s*\*\s*255\b`（patterns-unity-play.md `cs-vf-packet-int-cast`）
- 出典: KMT-LOG:583-590

### VF_MobingBeam_E3: Dimmer 未使用・lerpPacket がマスター / ブラックアウトを素通り・Profile max 0.07
- 症状: E3 の Dimmer が効かない。直すと今度はマスター / ブラックアウトが効かない（ライブで危険）。
- 原因: `SetFixtureIntensity` が `_dimmerIntensity` を見ていない。FixtureController の multiply は `packet` にだけ掛かり `lerpPacket` には掛からない。VFP_E3_Hall の Dimmer が max 0.07。
- 対策: Dimmer は `Mathf.Clamp01(packet)`（lerpPacket を使わない）。Profile の max を確認する。
- 実例: 2026-09-08 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:268-310

### VF_* の同じ packet を「シェーダー値（0〜0.5）」と「度数」の二用途に使うとスケールが合わない
- 症状: Zoom の packet は変化するのに spotAngle が 1 のまま動かない。
- 原因: VFP の Zoom は min -0.05 / max 0.5 / isLerp=1 で `_ConeWidth` 用のレンジ。それを spotAngle へ流用して 1 にクランプされていた。
- 対策: 0〜1 の lerpPacket と専用の角度レンジ（`_zoomMinAngle` / `_zoomMaxAngle`）で度数を作る。
- 実例: 2026-06-17 Submod_RealtimeLiveUtility（VF_MobingBeam_E3）
- 自動検出: 不可
- 出典: SL:1356-1366

### Universe 繰り上げ判定の off-by-one（> 511 と > 512）
- 症状: Universe の末尾にちょうど収まる灯体まで次の Universe に送られ、末尾の ch が無駄になる。
- 原因: 収まる条件は s+count<=512。`nextChannel + count > 511` だと ==512 でも繰り上げる。AutoCountUp は満杯のとき ch だけ 1 に戻し、Universe を据え置いていた。
- 対策: `> 512` にする。満杯のときは Universe を繰り上げる。
- 実例: 2026-06-17 Submod_RealtimeLiveUtility（VirtualFixtureListWindow / LightingRepachChannel）
- 自動検出: 不可（`> 511` は他の意味でも使われる）
- 出典: SL:1298-1309

### MeshCombiner に includeChildren=true で渡すと非アクティブも統合される
- 症状: 意図的に隠してあったメッシュが統合後に表示される。
- 原因: `GetComponentsInChildren<MeshFilter>(true)`。
- 対策: アクティブかつ Renderer 有効かつ灯体でないものを選び、includeChildren=false。
- 実例: 2026-09-24 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:779-783

### Gobo をぼかすと画像四隅の白が円の内側へ滲む
- 症状: Frost 時に黒かった内縁が白く浮く（平均 3 → 147）。
- 原因: gobo 素材は黒円の外側が白。
- 対策: 円の外を黒でマスクしてからぼかす（半径 0.47 が「白が消えて模様無傷」の境目、実測）。
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1573-1650

## 受信（Art-Net / OSC / MIDI）

### ArtNetReceiver の UDP バインド失敗を高速ループして Editor がロックする
- 症状: Play 中に Editor 全体が固まる。
- 原因: 6454 のバインド失敗（別プロセス／前回 Play の残留ソケット）で例外 → 即再試行を無限に回す。
- 対策: ReuseAddress、失敗は 1 回ログして停止、再試行は間隔を置く、Dispose でソケットを閉じる。
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:180-182

### ArtNetReceiver の受信スレッドが Debug.LogException でドメインリロード時にデッドロックする
- 症状: Play に入ると Unity がハングする。
- 原因: 受信スレッドがドメインリロード中の ThreadAbortException を catch して `Debug.LogException` を呼び、ログのロックでデッドロックした。
- 対策: 一般則は traps-catalog/unity-runtime.md「受信スレッドから Debug.Log* を呼ぶとドメインリロードでデッドロックする」。
- 実例: 2026-08-05 2609SuiseiTour26
- 自動検出: 候補（patterns-unity-play.md `cs-threadabort-log`）
- 出典: M:D---ProjectBLUE-Project-2609SuiseiTour26/play-mode-allowed.md

### Art-Net は送るチャンネル数ぶんしか載せない（512 固定コピーは範囲外読み）
- 症状: 一部チャンネルだけ送る卓で、隣の領域や前のパケットの残骸を読む（unsafe なので例外にならない）。
- 原因: ArtNetPacketUtillity.GetDmx が受信長を見ず dst.Length ぶん MemCpy していた。
- 対策: srcLength を渡し、届いた分だけ写す（修正済み 273d8be。他案件の submodule は要確認）。
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1677-1683

### ArtNetReceiver が送信元 IP を捨てて universe ごとに後着勝ち
- 症状: 複数卓が同一ユニバースを送ると混ざる。全 FixtureController が全灯体を駆動する。
- 原因: `metaDmxArray[universe]` へ上書きし、LightDeviceAssembly が全灯体を無条件に収集する。
- 対策: `[sourceIndex][universe]` 化と DmxSource 許可リスト（2609 で実装済み）。電飾バッファ（DmxEmissiveBuffer）は先頭ソース固定だった点にも注意。
- 実例: 2026-08-04 / 2026-08-12 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:236-240, 1404-1405

### ArtNetReceiver は IPAddress.Any 固定で、Bind IP の設定がどこにも効いていない
- 症状: 設定 UI で Art-Net の受信 IP を選べるのに挙動が変わらない。
- 原因: 受信器側に外部からバインド先を渡す口が無い（submodule 版）。lll-12 で `_bindAddress` を追加済み。他案件の submodule は未対応の可能性。
- 対策: 設定を足す前に、受信器まで値が届くかを確認する。NIC 指定を使うなら lll-12 版の MetaDmxReceiver / ArtNetReceiver を移植する。
- 実例: 2026-06-02 LiveMultiRecorder / 2026-09-24 lll-12
- 自動検出: 不可
- 出典: LMR-LOG:466-477 / LLL-LOG:402-420

### MetaDmx には seq / timestamp が無く、パケット到着は検出できない
- 症状: 受信メーターで値が固定のルックだと「途切れ」扱いになる。
- 原因: MetaDmx は Universe + byte[512] のみ。鮮度は変化検出でしか取れない。
- 対策: 到着検出が要るなら受信器側に到着時刻を持たせる（submodule の変更）。現状は仕様として表示に明記する。
- 実例: 2026-06-02 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:483-499

### 差分送信の ArtNet 再生はループ時にバッファを戻さないと、2 周目が前周の最終値から始まる
- 症状: ループ後の最初の値がおかしい。
- 原因: ReadAndSend は差分だけ更新する。部分的な Universe しか含まない収録では、受信側に前周の値が残る。
- 対策: 巻き戻すときに `ResetBuffers()` を呼ぶ。必要なら blackout を送る。
- 実例: 2026-08-27 Unity_ArtNetRecorder
- 自動検出: 不可
- 出典: AL:33-35, 49-51

### シーンの UnityEvent の永続リスナー（uOscServer.onDataReceived 等）がリファクタ後の保存で消える
- 症状: OSC を送っても CameraSwitcher が動かない。Cut / Fade ボタンも無反応。
- 原因: Submodule のリファクタで、実行時の AddListener 配線が削除された。旧 uGUI UI のシーンで無配線になっていた。OSC のハンドラは各シーンで Inspector から配線する規約。
- 対策: 欠けているシーンに Inspector で配線を足す。コードで購読すると他シーンで二重に発火する。リファクタの後は各シーンの onDataReceived の登録数を突き合わせる。Unity MCP からは永続コールを編集できない。
- 実例: 2026-07-11 vortex_urp（260711_ShoreLine）
- 自動検出: 不可
- 出典: VL:1-9, 41-47

### Minis（MIDI）は入力ポートが無いと InputDevice を作らず、MIDI 系が黙って反応しない
- 症状: CharacterActivator / MicController / EffectControllerMIDI が MIDI に反応しない。
- 原因: loopMIDI が起動しておらず、MIDI 入力ポートが 0 だった（Editor.log に `MidiInWinMM::initialize: no MIDI input devices`）。
- 対策: 先に loopMIDI を起動してポートを作る（`midiInGetNumDevs>0` で確かめる）。Minis が再スキャンするので Unity の再起動は不要。
- 実例: 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: PL:21-30

### ExternalControl: MIDI Learn はデバイスだけ割り当て、CC / ノート番号は学習しない。未登録・-1 でも無警告
- 症状: 「MIDI コンでアサインしても動かない」。
- 原因: ExternalControlManager の Control Devices に未登録、番号が -1。
- 対策: Manager への登録と番号設定を確認する。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:340-346

## カメラ・スイッチャー・キャラ

### 高い Script Execution Order のコンポーネント（OscRx_LipSync 24100）が検証用コンポーネントの値を上書きする
- 症状: 検証用に口の値を書く一時コンポーネント（order 100）の値が 0 になる。
- 原因: OscRx_LipSync（Script Execution Order 24100）が後から 0 で上書きした。
- 対策: 検証用の注入は 30000 など、より後の順序にする。本番の付け替えは LateUpdate で行う。
- 実例: 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:259

### VirtualCameraChief._autoDofSettings は実行時プロファイルが組み上がるまで null
- 症状: 起動直後に DofMidiControl.LateUpdate で NRE が大量に出る。
- 原因: ActiveConfig が未構築の間、プロパティが null を返す。消費側にガードが無い。
- 対策: 消費側で null をガードし、既定値を使う。
- 実例: 2026-07-11 vortex_urp（SinkaiFes2026 でも DofMidiControl の NRE が 10KB/frame の GC を出していた。同じ原因かは未確認）
- 自動検出: 不可
- 出典: VL:21-23 / SINKAI-LOG:213-218

### 旧システムで実行時に付与していた CinemachineCameraOffset が、新システムでは Generate 前提で無い
- 症状: Play で VirtualCameraController.ApplyValues が NRE を連発する。
- 原因: 既存の vcam に CinemachineCameraOffset が付いていない。どの `_vCams` にも登録されていない orphan の controller も残っていた。
- 対策: 既存の vcam に付与する。orphan の controller を掃除する。
- 実例: 2026-06-03 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:934-940

### Switcher の _renderTexA / _renderTexB が Prefab で未割り当て（fileID:0）で、PGM / PRV に映像が出ない
- 症状: PGM / PRV にライブ映像が出ない。
- 原因: Prefab 側の割り当てが欠けている。
- 対策: Camera_PGM / PRV の targetTexture（RT_CameraA / RT_CameraB）を割り当てる。
- 実例: 2026-06-03 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:1015-1019

### 出力カメラ 3 台が 4K・同じ cullingMask で三重描画
- 症状: Tris 16〜19M、Batches 8,000。
- 原因: PGM / PRV / LED の 3 台が 3840x2160 でほぼ同じ cullingMask（LED は Everything）。
- 対策: PRV の解像度を下げる。LED の cullingMask を絞る。
- 実例: 2026-09-24 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:785-793

### ライブ用の Volume（charIndirectLightMultiplier=0）とキャラ専用 Rendering Layer のまま新シーンへ持ち込むと、キャラが真っ黒
- 症状: 新しいシーンでキャラがシルエットになる。
- 原因: キャラの Renderer は Rendering Layer=Character のみで、新シーン標準の Directional Light（Default）が当たらない。間接光も 0。
- 対策: Rendering Layer=Character のみのキャラ用ライトを一緒に置く。
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:30-38 / M:D---ProjectBLUE-Project-Ext-TokinoSora-2026-pia/rendering-layers.md

### FacialManager / MorphControl の既存バグ（|| と &&、Stick Right 符号、UniTask のキャンセル無し）
- 症状: 範囲外アクセスでクラッシュ、右スティックで負の BlendShape、GameObject 破棄後もタスクが生存。
- 原因: `|| _proxy != null` の条件誤り、反転漏れ、`while(true)` に CancellationToken 無し。Kamitsubaki のコピーでだけ修正。
- 対策: 他案件で FacialManager を使うなら同じ修正を確認する（新方式 vortex_FacialController へ移行済みなら不要）。
- 実例: 2026-03-04 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:340-366

### vortex_FacialController の口の重みの合計が 1 を超え、母音が最大 2 倍になる
- 症状: Smile / Close のトリガーを重ねると口が大きく開く。
- 原因: ApplyLipSync のベース母音 = 入力 × Σ重み で、ボタン表情とトリガー表情が同時に効く。
- 対策: 合計が 1 を超えたら 1/合計 で正規化する（Submod mao/dev2 ba40ab5a）。
- 実例: 2026-09-28 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:309-315

### uLipSync は話し声で較正したプロファイルでは歌を判定できない。正規化が A〜O だけなので口が閉じない
- 症状: 歌うと「あ」に偏る（82%）。ま行・な行で口が閉じない。
- 原因: 較正の母音は 222〜276Hz、歌は 571Hz で MFCC が別物になる。正規化が A〜O の 5 つだけなので、「ん」や無音と判定されても合計が 1 に戻る。ミックス済みのボーカルは RMS が上限を超えて張り付く。
- 対策: 歌のボーカルを強制アラインメントして区間を切り出し、較正する（Sora-Sing）。送り側の正規化と音量レンジを見直す。
- 実例: 2026-09-27 / 2026-09-28 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:217-243, 277-284

## Timeline・収録

### DmxMixerBehaviour.OnGraphStart が無条件に Timeline モードへ入り、ライブの Art-Net が止まる
- 症状: 再生すると MetaDmxReceiver の UseTimeline が勝手に ON。DMX クリップが鳴っていなくても、ビルドが Art-Net に無反応。
- 原因: `OnGraphStart` で `IsTimeline(true)` を呼び、false へ戻す経路が無い。Timeline のグラフが走っている限り MetaDmxReceiver.cs:179 で return する。
- 対策: 症状と切り分けは skill vortex-timeline-setup に記載。コードで直すなら ProcessFrame で `_totalWeight > 0` の間だけ Acquire、抜けたら Release（複数トラック用に参照カウント）。OnGraphStop / OnPlayableDestroy でも解除（lll-12 で実装）。
- 実例: 2026-09-24 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:392-400, 436-440 / skills/vortex-timeline-setup/SKILL.md

### Override 系のトラックは、元のトラックより「下」に置かないと上書きされて効かない
- 症状: CameraRecordOverrideTrack のオフセットが効かない。
- 原因: Timeline はトラックを上から順に評価する。上に置くと下の CameraRecordTrack の記録値で上書きされる。
- 対策: Override トラックは CameraRecordTrack より下に置く。
- 実例: 2026-08-20 vortex_urp
- 自動検出: 不可
- 出典: VL:580-582

### vcam.State を記録すると、CameraUpdatedEvent で後がけする平滑化（mCameraJitterFilter）が記録に乗らない
- 症状: 手振れ中の記録を再生すると大きくカクつく。
- 原因: mCameraJitterFilter は Brain の解決後に OutputCamera.transform を EMA で平滑化しており、vcam.State には乗らない。
- 対策: 表示中の PGM / PRV は OutputCamera の transform と FOV を記録する。
- 実例: 2026-06-19 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:1573-1584

### 録画系（Recorder_VRMBlendShapeProxy / Recorder_camera）は毎フレーム new float[] と List 倍増で周期スパイク
- 症状: 録画中に時間とともに大きくなる周期的スパイク。
- 原因: 毎フレーム `new float[keys.Count]`、`_frames` の容量倍増コピー。
- 対策: バッファを使い回し、想定尺で容量を先に確保する（提案段階・未実施）。
- 実例: 2026-09-16 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:423-430

## サブモジュール・ビルド

### Submodule / パッケージを変更したら Runtime と Editor の両アセンブリを検証する
- 症状: 取り込んだコミットで CharacterShadowMaskRendererFeatureInstaller.cs が CS0234 / CS0246。Editor アセンブリ全体がコンパイル不可。
- 原因: URP の型を使う Editor スクリプトが追加されたが、vortexUtility.Editor.asmdef に URP の参照が無かった。前回の検証は Runtime の csproj しかビルドしていなかった。
- 対策: asmdef に Unity.RenderPipelines.Core.Runtime / Universal.Runtime を足す。サブモジュールの検証は Runtime と Editor の両方で行う。
- 実例: 2026-08-18 vortex_urp
- 自動検出: 不可
- 出典: VL:505-521 / rules/unity.md「検証の追加ルール」

### 分離パッケージの依存宣言漏れ（一度もコンパイル検証されていない）
- 症状: 移植直後に CS0246（ReadOnlyAttribute / uOSC / Animation.Rigging）。main にマージ後も manifest 欠落のまま。
- 原因: 分離時に RLU 側の属性クラス・uOSC・Rigging の依存を package.json / asmdef / manifest に書いていない。
- 対策: 移植・取り込み時に asmdef の references と manifest を突き合わせる。uOSC は #upm 追従でなく upm@2.2.0 等に固定する。
- 実例: 2026-08-04 / 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:67-76, 1447-1471

### サブモジュールのブランチ切替で Rewired が二重化 → asmdef 名・GUID 衝突でコンパイルが止まる
- 症状: 8/31 以降 ScriptAssemblies が更新されていなかった（「エラー 0」に見える）。Unity が asmdef.meta 8 件の GUID を振り直す。
- 原因: mao/dev2 は Rewired をパッケージ内へ移動済みで、案件側 Assets/Rewired と衝突。同時に新依存 com.oscjackexpansion も manifest に無かった。
- 対策: サブモジュール切替後は ScriptAssemblies の更新時刻とコンパイル結果を確認する。二重はどちらかを削除。新依存を manifest へ。
- 実例: 2026-09-13 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:56-61

### Rewired_Core.dll の GUID 不一致警告はビルドを止めない
- 症状: Rewired_Core.dll が "expected GUID で見つからない" と出て、ビルドブロッカーに見える。
- 原因: submodule 内に RewiredBackup が併存し GUID 衝突。ただし実行時 LogException でコンパイルは通る。vortexUtility.Runtime が Rewired に実依存しており削除不可。
- 対策: ビルド失敗の原因と決めつけず Editor.log の CS エラーを見る。Rewired は消さない。
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:300-313

### Submod_RealtimeLiveUtility はそのままではスタンドアロンビルド不可
- 症状: ビルドが 4 エラーで失敗（VolumetricLights の Builtin シェーダ／UnityEditor 参照）。
- 原因: runtime 約 20 ファイルに裸の `using UnityEditor;`（うち未ガード 4: Recorder_VRMBlendShapeProxy / DivideController / InputPatchMaster 等）、Resources 配下の Built-in シェーダ、VRMTools DLL の .meta。
- 対策: ガード・未使用シェーダの除去・DLL .meta を Editor 限定、の 3 点。submodule はコミットしない。削除は説明と承認の後。
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: hook `cs-runtime-unityeditor`（ガード漏れ）
- 出典: LMR-LOG:324-352

### realtime-live-utility を別プロジェクトへ入れると Cinemachine 2/3・PostProcessing v2・Rewired・dynamic で大量エラー
- 症状: パッケージ読み込み後に PostProcessAdjuster / DivideController / FacialManager / PusherData でコンパイルエラー。
- 原因: パッケージが Cinemachine 2.8.6 前提（Unity 6 は 3.x 必須）、PPv2 の型、有料 Rewired、`dynamic`（Microsoft.CSharp 依存）。
- 対策: asmdef の versionDefine で `USE_URP`、Rewired 依存を `#if REWIRED`、`dynamic` → object。file: パスは Packages/ からの相対。
- 実例: 2026-03-04 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:119-170

### uLipSyncBlendShapeVRM ↔ vortexUtility.Runtime の循環参照
- 症状: CS0246 `vortex` / `IBlendShapeProvider` が見つからない。
- 原因: vortexUtility.Runtime が uLipSync.Samples.VRM.Runtime を参照済みで、逆向き参照を足すと循環する。
- 対策: サンプル側から vortex への依存を外し、リセット処理は呼び出し元（FacialMorphController）で行う。
- 実例: 2026-03-05 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:655-668

### 同名の型がサブモジュールと Assets の両方にあると、Editor 専用 asmdef に置いたとき CS0433
- 症状: Inspector 拡張を Editor 用 asmdef に置くと CS0433。
- 原因: MidiEffectEmitter などが、サブモジュール側と Assets/SubModuleRefScripts 側の両方に同名で存在する。
- 対策: Inspector は SubmoduleRef 側に `#if UNITY_EDITOR` で置く（CS0436 の警告は意図どおり）。
- 実例: 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: PL:44-46, 57

### 親リポジトリがサブモジュールの新しい API に依存するときは、サブモジュールを先にコミット・push してからポインタを進める
- 症状: 他の環境でコンパイルが壊れる。解決できない参照が残る。
- 原因: 親だけコミットした、またはポインタだけ先に進めた。
- 対策: サブモジュールをコミットして push した後に、親のポインタを更新する。
- 実例: 2026-09-06 vortex_urp / 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: VL:925-927 / PL:80-82

### ドメインリロードのたびに Crest の hlsl と codecoverage の Settings.json に改行コードだけの差分が出る
- 症状: git に M が出る（内容の差分は無い）。
- 原因: Unity とパッケージが再生成する。
- 対策: リロード由来かどうかを見分けて報告する。コミットには含めない。
- 実例: 2026-09-14 Ext_Palletproject / 2026-09 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: PL:66-68 / M:D---ProjectBLUE-Project-Ext-Palletproject/unity-mcp-http-fallback.md

## skill に記載（ここには書かない）
- DmxClip は Looping を持たない（ループは PlayableDirector.wrapMode=Loop） → skill vortex-timeline-setup
- キャラ別 Timeline を複数 Play On Awake にすると DMX を取り合う → skill vortex-timeline-setup
- RT_Output を誰も書かない（VirtualCameraSwitcher の Blit がコメントアウト）、複製シーンでカメラ系が無効、Canvas の前提解像度より小さい Game View で中央切り出し、Recorder 後の Play 終了で落ちる → skill vortex-timeline-export
- NiloToon 変換で MatCap（_SphereAdd）が入らない、vortexCharacterSetup が旧方式（uLipSync / FacialManager）で仕込む、LookatManager に非アクティブのキャラが登録されない → skill vortex-character-setup
- LED メッシュのマテリアルに RT が繋がっていない、ChartSync の入力が保存されない → skill vortex-led-framing

## 他分野に置いたもの
- Kronnect VolumetricLights・NiloToon・MassiveClouds・VolumetricLightBeam のパッケージ側の罠 → traps-catalog/unity-rendering.md
- uOSC の Ordinal / キャスト例外 / パーサの確保 → traps-catalog/unity-gc.md

---
出典の略記: 2609-LOG = D:\_ProjectBLUE\Project\2609SuiseiTour26\log\claudeLog.txt / SINKAI-LOG = D:\_ProjectBLUE\Project\SinkaiFes2026\log\claudeLog.txt / VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt / SL = D:\_ProjectBLUE\Project\_vortex\Submod_RealtimeLiveUtility\Submod_RealtimeLiveUtility\.claude\claudeLog.txt / TS = D:\_ProjectBLUE\Project\Ext_TokinoSora_2026-pia\log\claudeLog.txt / PL = D:\_ProjectBLUE\Project\Ext_Palletproject\log\claudeLog.txt / AL = D:\_ProjectBLUE\Project\_thirdParty\Unity_ArtNetRecorder\log\claudeLog.txt / LMR-LOG = D:\_ProjectBLUE\Project\LiveMultiRecorder\.claude\claudeLog.txt / LLL-LOG = D:\_ProjectBLUE\Project\lll-12\log\claudeLog.txt / KMT-LOG = D:\_ProjectBLUE\Project\EXT_Kamitsubaki_Composite\EXT_Kamitsubaki_Composite\.claude\claudeLog.txt / M:<name> = C:\Users\komao\.claude\projects\<name>\memory
