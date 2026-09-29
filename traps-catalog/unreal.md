# unreal の罠（カタログ）

Unreal Engine 5.6（C++ ビルド・Python・Sequencer・Niagara・アニメーション）で踏んだ罠の全件。

### UE 5.6 の C++ ビルドが C3859 / C1076 / 1455 で落ちる（並列度で仮想メモリを使い果たす）
- 症状: "could not be compiled"。UBT ログに `C3859 Failed to create virtual memory for PCH`、1455（ページングファイル不足）、`C1076 internal heap limit`。
- 原因: cl.exe 1 プロセス 4〜6GB × 物理コア数（24）並列の同時 commit バースト。UBT の見積り（1.5GB/action）が実態より低い。RAM 64GB・ページファイル 156GB でも起きる。
- 対策: `%APPDATA%\Unreal Engine\UnrealBuildTool\BuildConfiguration.xml` に `<BuildConfiguration><MaxParallelActions>4</MaxParallelActions><bAllowUBALocalExecutor>false</bAllowUBALocalExecutor>`。変更後は Intermediate / Binaries を消してクリーンビルド。
- 旧説: `ParallelExecutor.MaxProcessorCount=8` で抑える（誤り。5.6 で deprecated になり無視される）
- 実例: 2026-06 totolive_202511
- 自動検出: 候補 `ue-buildconfig-deprecated-maxprocessorcount`（patterns-dcc.md。設定ファイル側のみ）
- 出典: totolive_202511\.claude\claudeLog.txt:50-75 / MEM(totolive-202511)\ue56_build_oom.md:18-47

### 新しい UCLASS は Live Coding で入らない
- 症状: 追加したクラスが出ない。
- 原因: Live Coding は新規 UCLASS 非対応。
- 対策: エディタを終了（事前に `save_dirty_packages(True, True)`）→ `Build.bat ... -WaitMutex` → 再起動。
- 実例: 2026-06-06 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\dmx_fluorescent_arch.md:13, editor_lifecycle_pref.md:11

### UE 5.6 で廃止された API（旧プラグインの移植）
- 症状: 旧プラグイン（OVR LipSync）が 5.6 でビルドできない。
- 原因: 旧 include パス、`FAssetData::ObjectPath` / `AssetClass`、`CreatePackage(NULL, ...)`、SoundWave の PCM 展開（DTYPE_Native / GetRuntimeFormat / FAsyncAudioDecompress）の廃止。
- 対策: `CoreMinimal.h`・`Components/...` 形式の include、`GetObjectPathString()` / `AssetClassPath`、`CreatePackage(*p)`、PCM は `GetImportedSoundWaveData(bytes, rate, ch)`。`create_asset` の衝突は `collect_garbage`。
- 実例: 2026-06 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\ovrlipsync_ue56.md:10-15, 23

### Interchange の非同期インポートは remote exec の文脈で完了しない
- 症状: "start importing source" の後にアセットが生成されない。override_pipelines に transient を渡すと TypeError。
- 原因: remote exec 文脈で非同期インポートが完了しない。
- 対策: `AssetToolsHelpers.import_asset_tasks`（同期）を使う。パイプラインは保存したアセットを SoftObjectPath で参照する。レガシーへ戻すなら CVar `Interchange.FeatureFlags.Import.FBX 0`。
- 実例: 2026-06-02 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:166-180

### アニメーションのみの FBX は一致するスケルトンが無いと取り込めない
- 症状: "Mesh contains ... bone as root but animation doesn't contain the root track"。
- 原因: 取り込み先に一致するスケルトンが無い。
- 対策: 一致するスケルトンを先に用意して指定する。
- 実例: 2026-06-02 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:182-196

### Blender 由来（Y-up バインド）のソースを Z-up へリターゲットすると 90° 倒れる
- 症状: 結果が剛体的に 90° 倒れる。import_rotation をアニメへ適用・リターゲットポーズ回転・rotation_offset はいずれもモーションを壊す。
- 原因: ソースのバインドが Y-up（Unity 側の「Blender FBX のルート -90°」と同根）。
- 対策: 補正なしでリターゲットし、再生側（アクターの回転）で補正する。5.6 の Retargeter は新規だと ops=0 なので `add_default_ops()` が必須。
- 実例: 2026-06-02 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:233-270

### Remote Execution の MODE_EXEC_FILE は相対パスをエディタ側の CWD で解決する
- 症状: success:False・出力空。
- 原因: 相対パスはエディタの CWD で解決される。
- 対策: 絶対パスを渡す（MODE_EXEC_STATEMENT は問題なし）。
- 実例: 2026-06 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:425-427 / MEM(totolive-202511)\toto_editor_bridge.md:48

### Sequencer を Python で編集するときの API の罠（クラッシュ・400 倍ずれ・Rotator の引数順）
- 症状: エディタのクラッシュ・接続断／画面が真っ黒／オブジェクトが消える／配置が 400 倍ずれる。
- 原因: (1) spawnable binding への `add_track(MovieScene3DTransformTrack)` はクラッシュ (2) `MovieSceneBindingProxy.get_binding_id()` は無い (3) `unreal.Rotator()` の位置引数は (roll, pitch, yaw) (4) キーを打たないチャンネルは既定 0（Scale=0 で不可視） (5) section の `get_start_frame()` / `set_range()` は display rate 単位、channel の `add_key` は tick（24000）単位。
- 対策: (1) possessable の CineCameraActor を置いてカメラカットを差し替える (2) `MovieSceneSequenceExtensions.get_binding_id(seq, binding)` (3) キーワード引数 `Rotator(roll=, pitch=, yaw=)` (4) 動かさない軸も `set_default()` (5) `set_range_seconds` / `get_start_frame_seconds` の秒 API を使う。
- 実例: 2026-06-04〜07 totolive_202511
- 自動検出: 候補 `ue-rotator-positional`（patterns-dcc.md。(3) のみ）
- 出典: totolive_202511\.claude\claudeLog.txt:470-480, 663-667, 681-690, 750-765 / MEM(totolive-202511)\sequencer_python_pitfalls.md:12-17

### possessable の binding 操作は対象アクターのレベルを開いて行う
- 症状: 本番アニメの binding が空（EMPTY）になり壊れる。誤ったワールドでの生死判定を信じて二次破壊した。
- 原因: 別レベルを開いた状態で `add_possessable` すると重複 binding ができて元の binding の参照を奪う。`locate_bound_objects` の解決可否・binding の表示名はワールド依存。
- 対策: 対象が属するレベルを開いてから操作する。binding は表示名ではなく中身（保持セクション）で特定する。修復は正しいレベルで add_possessable → `move_binding_contents(旧, 新)` → 旧を remove。
- 実例: 2026-06-07 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\morph_pose_component.md:19-22, toto_animbp_additive_lip.md:21

### Sequencer のスケルタルトラックは additive にできない（AnimBP 側で直す）
- 症状: ボーン 0 本のリップ用 additive アニメがボディを ref pose で上書きする。
- 原因: `set_blend_type(ADDITIVE)` は非サポートで、別トラック・上位 row でも additive にならない。加算になるかは AnimBP の DefaultSlot 構成次第。
- 対策: 正しい AnimBP へ差し替えるか、スロット構成を合わせる。検証はセクションの on/off で同フレームのボーン world 位置が変わるかで見る。
- 実例: 2026-06-07 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\toto_animbp_additive_lip.md:15-24 / totolive_202511\.claude\claudeLog.txt:745-760

### get_morph_target はアニメカーブ駆動のモーフで 0 を返す
- 症状: 効いているのに 0 と出て判定を誤る。
- 原因: SetMorphTarget 由来の値しか読まない。
- 対策: 判定は目視かボーン位置で行う。
- 実例: 2026-06-07 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\toto_animbp_additive_lip.md:22

### 大きなアニメや大量データを Python の反射で触ると激遅・ハング
- 症状: 434 秒の mocap に `add_float_curve_keys` で 1 本 8 分超ハング。24 万フレームの frame_sequence 展開が 7〜11 分 + クラッシュ。
- 原因: 呼ぶたびの全体再圧縮／Python 反射のオーバーヘッド。
- 対策: C++ の関数ライブラリ（BlueprintFunctionLibrary）で一括処理して Python から呼ぶ。
- 実例: 2026-06-07 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\toto_animbp_additive_lip.md:23, ovrlipsync_ue56.md:23

### Niagara: エクスポートされていないエディタ API／rapid iteration で値が効かない／FLIP に汎用 Force は効かない
- 症状: LNK2019（FindOutputNode / GetOrderedModuleNodes / RelayoutGraph）。モジュール入力値を書いても効かない。FLIP ソルバの粒子に Force を足しても動かない。
- 原因: `NIAGARAEDITOR_API` が付いていない関数はリンクできない。rapid iteration パラメータが有効だと override pin への直書きが反映されない。FLIP ソルバはグリッド速度で毎ステップ速度を上書きする。
- 対策: ヘッダを grep して `NIAGARAEDITOR_API` を確認し、エクスポート済みの代替（FindEquivalentOutputNode）を使う。`SetBakeOutRapidIterationOnCook(true)` で rapid iteration を切ってから pin を書く。FLIP は User Param（Water Height 等）で駆動する。
- 実例: 2026-06-05 totolive_202511
- 自動検出: 不可
- 出典: MEM(totolive-202511)\toto_editor_bridge.md:17-20, 25-28, 41-44 / totolive_202511\.claude\claudeLog.txt:428-429

### PoseableMeshComponent の Set/GetBoneTransformByName は毎回全身ポーズを再構築する
- 症状: ヒューマノイド 1 体（約 50 ボーン）を 60fps で駆動すると毎秒 6,000 回の全身再構築 + アロケーション。
- 原因: Set も Get も内部で FA2CSPose を確保して全身のコンポーネント空間ポーズを作り直す。SetBoneTransformByName(ComponentSpace) は親の現在の変換で割ってローカルに格納するので、親→子の順で書かないと子がずれる。
- 対策: RefSkeleton を 1 パスで前から舐めてコンポーネント空間ポーズを自前で合成し、`BoneSpaceTransforms` にローカル変換を直接書き、最後に 1 回だけ `MarkRefreshTransformDirty()`。
- 実例: 2026-08-24 MotionForge
- 自動検出: 候補 `ue-poseable-bone-by-name`（patterns-dcc.md）
- 出典: Notion 3c6e4d4b-751b-8135-982a-ebb9055218ea

### ビューポートのカメラ制御は分割ビューの非アクティブ側に当たることがある
- 症状: `set_level_viewport_camera_info` で動かしたのに見ているビューが変わらない。
- 原因: 分割ビューの非アクティブ側に当たる。
- 対策: 記録なし（操作後に実際に見ているビューが変わったかを確かめる）。
- 実例: 2026-06 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:321-323

### DMX Library は Python から編集できない
- 症状: Python で DMX Library を組めない。
- 原因: API が公開されていない。
- 対策: 記録なし（Python での自動化を前提にしない）。
- 実例: 2026-06 totolive_202511
- 自動検出: 不可
- 出典: totolive_202511\.claude\claudeLog.txt:325
