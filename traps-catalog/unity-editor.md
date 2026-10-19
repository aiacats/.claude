# unity-editor の罠（カタログ）
Editor 拡張・AssetDatabase・ドメインリロード・Editor の起動/終了・Undo・シーン/Prefab 操作・Editor.log・Editor の UI（IMGUI / UI Toolkit）。トラブル時に grep で引く。

### Unity を強制終了しない（taskkill / Stop-Process）
- 症状: 次回起動が遅い。Library の再構築が走る
- 原因: 強制終了で Library の書き戻しが飛ぶ
- 対策: `(Get-Process -Id <pid>).CloseMainWindow()` で正常終了。先にタイトルの `*` で未保存を確認。同定は ProcessName と StartTime（MainWindowTitle だけで決めない）
- 実例: 2026-09-23（CLAUDE.md 記載時）
- 自動検出: hook `kill-unity`
- 出典: ~/.claude/CLAUDE.md「Claude Code / Unity の再起動」

### vortex.EditorTools で Editor を継承する（CS0118 'Editor' is a namespace）
- 症状: CS0118。Safe Mode のダイアログまで出る
- 原因: パッケージ側の `vortex.Editor` 名前空間に解決される
- 対策: `: UnityEditor.Editor` と完全修飾
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia
- 自動検出: hook `cs-editor-namespace-clash`
- 出典: rules/unity.md「命名・導線」

### 管理者ターミナルから起動すると Unity が管理者で動く
- 症状: 「Unity is running as administrator」警告
- 原因: Claude のターミナルが管理者権限のことがあり、そこから `Start-Process Unity.exe` すると昇格が引き継がれる
- 対策: 昇格していない経路から起動する（Hub / 非管理者シェル）
- 実例: 記載なし（rules/unity.md）
- 自動検出: 不可
- 出典: rules/unity.md「Unity 起動時の注意」

### Editor.log は同時起動の Unity で共有される／先頭に旧セッションの残骸が残る
- 症状: `grep "error CS" Editor.log` に別プロジェクトの 150 件が混ざる。存在しない PackageCache のスタックトレースが見える
- 原因: 全 Unity が `%LOCALAPPDATA%\Unity\Editor\Editor.log` に書く。起動時に 0 バイトへ切り詰めず先頭から上書きする
- 対策: コンパイル可否は MCP か `Library/ScriptAssemblies/*.dll` の更新時刻で見る。どの Unity が何を開いているかは `Get-CimInstance Win32_Process -Filter "Name='Unity.exe'"` の CommandLine。自分で起動するなら `-logFile <root>/Logs/editor-session.log`。Editor.log は最新の起動以降（末尾）で判断
- 実例: 2026-09-24 vortex_urp（ModelChecker の 150 件を読み違え）/ 2026-08-04 2609SuiseiTour26 / 2026-09-24 ModelChecker（-logFile 運用）
- 自動検出: 候補 bash `Editor\.log[\s\S]*error CS`（他の Unity 起動中のみ意味がある。精度不足で未採用）
- 出典: rules/unity.md「検証の追加ルール」/ 2609SuiseiTour26 log/claudeLog.txt:38-41 / ModelChecker CLAUDE.md:25-27

### 背面の Unity は Refresh・delayCall・UniVRM の Prefab 生成を回さない
- 症状: 外で書き換えたファイルを拾わない（Assets/Refresh が 0.001 秒）。.vrm がテクスチャだけ展開され Prefab ができない。ドメインリロード後に MCP サーバーが 3 分以上立たない。ジョブが 3.7 倍遅い
- 原因: 背面・別仮想デスクトップの Editor には更新ティックが来ない（delayCall / EditorApplication.update も止まる）
- 対策: 変更ファイルは `AssetDatabase.ImportAsset(<path>)` を個別に呼び、dll の更新時刻で確認。VRM は前面化してから ImportAsset。自作の delayCall は `EditorApplication.QueuePlayerLoopUpdate()` で起こす（unity-mcp v1.5.1 で修正、約 15 秒で応答）
- 実例: 2026-09-14 Ext_Palletproject / unity-mcp、2026-06-20 ReLink（前面化して Ctrl+R で初めてコンパイル）、2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: rules/unity.md / Notion 3dbe4d4b-751b-8114-89c3-eeb2c3801d9f, 3e5e4d4b-751b-81fd-bdcb-e33c057af362 / PL:103 / MC\CLAUDE.md:41-42, MC\log\claudeLog.txt:14

### 非フォーカスの Unity は Update・再描画・Play のフレームが進まない
- 症状: OSC に無反応でフォーカスした瞬間にまとめて処理。win-gui キャプチャが古いフレーム。ProfilerRecorder が 24〜30 フレームしか取れない。MIDI 入力が反映されない。Play 中の自動計測が終わらない
- 原因: Application.runInBackground=false。非フォーカスの Editor は Play ループを間引く
- 対策: 受信系ブリッジで `Application.runInBackground=true`。計測・キャプチャ中は前面に保つ（Bash の polling 中にフォーカスが外れる）。フレーム数は小さく取り、Play 直後のシーンロード GC（8.9MB/frame 級）を warmup で除く
- 実例: 2026-08-06 / 2026-09-02 2609SuiseiTour26、2026-09-14 / 09-15 / 09-23 SinkaiFes2026、2026-09-06 vortex_urp
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:991-1005, 3322-3327 / SinkaiFes2026 log/claudeLog.txt:144, 317, 631-632 / VL:1141-1149

### モーダルが開いているとドメインリロード・インポートが止まる
- 症状: `Reloading Domain (Busy NN:NN)` が伸び続け 23 分後に落ちた。新規 .cs のメニューが出ず .meta も生成されない。MCP は fetch failed / timeout
- 原因: SettingsPrompt（ColorSpace 等の推奨設定、IL.ranch DemoScene）などのモーダルがメインスレッドを握る。Play 中の force_compilation で誘発しやすい
- 対策: 画面全体を screenshot してモーダルを探す（capture_window では写らない）。閉じてから Assets/Refresh。force_compilation は Play を抜けてから。SettingsPrompt は "Close Prompt" で恒久停止
- 実例: 2026-06-01 LiveMultiRecorder / 2026-06 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: LMR-MEM/settings-prompt-blocks-domain-reload.md, LMR-LOG:385-395 / SL:1203-1205

### Play と force_compilation を往復するとリロードがデッドロックする
- 症状: モーダルが無くても Reloading Domain の busy が数分伸び続ける
- 原因: Play ごとに残るネイティブスレッド（OptiTrack NatNet 等）が推定原因
- 対策: 往復を最小にする。固まったら Unity を再起動（Recovering Scene Backups は No）
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-MEM/settings-prompt-blocks-domain-reload.md:85-95, LMR-LOG:436-445

### Unity 6000.3.21f1: ドメインリロード直後のツールチップでネイティブクラッシュ
- 症状: "Resolve of invalid GC handle. The handle is from a previous domain" の後に落ちる
- 原因: Unity 本体（TooltipView）
- 対策: リロード直後にホバーしない。落ちたらログを退避して再起動
- 実例: 2026-09-24 ModelChecker（2 回）
- 自動検出: 不可
- 出典: MC\CLAUDE.md:48-50

### プレハブオーバーライドは値を元に戻しても残る
- 症状: 保存したシーンに m_Intensity × 52 / m_Color × 34 等の不要なオーバーライド。以後プレハブ側の変更が効かない
- 原因: 一度書けば同値でも m_Modifications に記録される
- 対策: 検証で触ったシーンは保存せず git checkout（または RevertPropertyOverride）。保存前に propertyPath の内訳を集計（LFS は `git show HEAD:<path> | git lfs smudge` で取り出して diff）。[ExecuteAlways] が生成する値は開いただけで差分に出るので区別する
- 実例: 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: Notion 3e4e4d4b-751b-81f7-bdec-e666fb986055 / SinkaiFes2026 log/claudeLog.txt:638-648 / skill vortex-timeline-setup にも記載

### 起動中の Unity の .asset / ProjectSettings をテキストで書き換えても効かない
- 症状: VolumeProfile(.asset) を書き換えても見た目が変わらない（Refresh / ImportAsset(ForceUpdate) でも）。EditorBuildSettings / PlayerSettings が戻る
- 原因: 読み込み済み ScriptableObject はメモリ側が正。保存時にメモリの値で書き戻される
- 対策: SerializedObject / VolumeComponent のパラメータ / EditorBuildSettings.scenes / PlayerSettings setter など Editor API で書いて AssetDatabase.SaveAssets。どうしてもファイルなら Editor 再起動。対照実験（背景を赤にする等）で描画更新を切り分ける
- 実例: 2026-08-04 / 2026-08-24 / 2026-08-31 2609SuiseiTour26
- 自動検出: 候補 edit `ProjectSettings[\\/].*\.asset$`（Unity 未起動なら正しい操作なので未採用）
- 出典: 2609SuiseiTour26 log/claudeLog.txt:165-177, 1753-1755, 2744-2746

### OnValidate で直接代入した値はシーンに保存されない
- 症状: Inspector には出ているのにシーンには Array.size しか保存されない。ビルドでは空
- 原因: 直接代入は PropertyModification を作らない。OnValidate は Player ビルドで呼ばれない
- 対策: Editor 側で SerializedProperty 経由で書き、補正直後に ApplyModifiedProperties（遅らせると記録されないことがある）
- 実例: 2026-08-04 / 2026-08-05 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:363-376, 572-578

### OnValidate から DestroyImmediate を呼ばない
- 症状: エラー／不定動作
- 原因: OnValidate 中のオブジェクト破棄は禁止
- 対策: EditorApplication.delayCall で遅延するか、共有キャッシュ化で不要にする
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:1547-1548

### Inspector リストの「+」で足した要素にフィールド初期化子が走らない
- 症状: 空文字・false の「何にも一致しない行」ができる
- 原因: 配列拡張は直前要素の複製か既定値で、C# の初期化子を実行しない
- 対策: Editor 側で空の新規要素を検出し SerializedProperty で既定値を入れる
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:320-325

### 継承すると基底の OnValidate / OnEnable / CustomEditor が呼ばれない
- 症状: 基底の OnValidate の再計算が止まる。基底 Editor の hierarchyChanged 購読が効かない。基底 Inspector に足した UI が一部の派生型でだけ出ない
- 原因: Unity メッセージは最派生の 1 つだけ呼ばれ、基底の private は拾われない。派生専用 Editor が UnityEditor.Editor を直接継承し DrawDefaultInspector だけ呼んでいた
- 対策: 基底から protected virtual の OnXxxValidate() フックを呼ぶ。継承前提の Editor の OnEnable/OnDisable は protected virtual。派生 Editor は基底 Editor を継承して base.OnInspectorGUI()
- 実例: 2026-08-05 / 2026-08-12 / 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:400-409, 1342-1343, 1905-1910

### ApplyModifiedProperties を DrawPropertiesExcluding より先に呼ぶと入力が捨てられる
- 症状: Inspector に値を入れても入らない（Switcher や Dof Control が全滅）
- 原因: Apply の後に描いた項目は確定されない。基底 Editor を継承した時点で顕在化
- 対策: 確定はすべて描画し終えてから。`[CustomEditor(typeof(X), true)]` は派生全体に効くので実際に入力して確かめる
- 実例: 2026-09-06 vortex_urp（Recorder_coreEditor）
- 自動検出: 候補（patterns-unity-core.md `cs-apply-before-draw`）
- 出典: VL:931-966

### RegisterCreatedObjectUndo の直後に素で代入すると参照が保存時に null へ戻る
- 症状: 生成した rail や LookAt の m_Target がディスク上で fileID:0。位置は残る
- 原因: Undo の flush/collapse で生成直後のスナップショットへ巻き戻る
- 対策: 代入前に `Undo.RecordObject(obj, ...)`
- 実例: 2026-07-23 Ext_Palletproject（ServiceCamVirtualCameraBuilder）
- 自動検出: 不可（同ファイルの RecordObject 有無では精度が出ない）
- 出典: PL:1-15

### EditorSceneManager.NewScene は未参照アセットを解放する
- 症状: 直前に作ったアセットを objectReferenceValue に入れても fileID 0
- 原因: NewScene で未参照アセットがアンロードされ、変数の参照が無効になる
- 対策: NewScene の後は `AssetDatabase.LoadAssetAtPath` で引き直す
- 実例: 2026-09-24 vortex_urp
- 自動検出: 不可
- 出典: VL:1870-1872

### AssetDatabase.StartAssetEditing 中は CreateFolder / CreateAsset が作られない
- 症状: 保存フォルダもアセットも生成されない
- 原因: インポートパイプライン停止中
- 対策: 使わないか、フォルダを事前に作る
- 実例: 2026-08-05 2609SuiseiTour26
- 自動検出: 候補 edit `StartAssetEditing\(`（正しく使う場合もあり未採用）
- 出典: 2609SuiseiTour26 log/claudeLog.txt:475-478

### ドメインリロードを越える状態と越えない状態が混ざる
- 症状: (1) Play しても Editor 拡張のジョブが始まらない (2) 点検していないのに「問題なし」で書き出しボタンが押せる (3) EditorWindow の入力がコンパイルで消える (4) Play 中のリロードでジョブが黙って飛ばされ、Recorder は DontDestroyOnLoad で生き残り前のファイルが未完結
- 原因: ScriptableSingleton（HideAndDontSave）とシリアライズ済みフィールドは残るが、static の EditorApplication.update 購読と非シリアライズのコレクションは消える
- 対策: 購読は `update -= Tick; update += Tick;`（フラグで覚えない）。結果とフラグは同じ寿命で持ち OnEnable でリセット。残したい状態は [SerializeField] か EditorPrefs。開始済みフラグをシリアライズし、復帰時に不整合なら失敗として中断
- 実例: 2026-09-23 vortex_urp（×3）/ 2026-09-24 SinkaiFes2026
- 自動検出: 不可
- 出典: VL:1627-1639, 1731-1733, 1461-1464 / SinkaiFes2026 log/claudeLog.txt:708-709 / skill vortex-timeline-setup（EditorWindow の状態）

### EditorApplication.delayCall を [InitializeOnLoadMethod] の中で登録すると呼ばれない
- 症状: OnEditorLoad は走るのに delayCall の Flush が一度も呼ばれない
- 原因: 初期化処理の途中で delayCall のキューが捨てられる
- 対策: EditorApplication.update に 1 回限りのハンドラで登録し、OnEditorLoad のたびに登録し直す
- 実例: 2026-09-24 vortex_urp（Discord 通知の保留キュー）
- 自動検出: 不可（実例 1 件で一般化できない）
- 出典: VL:1866-1869

### 自作の Editor 常駐サーバーでドメインリロードがループする
- 症状: 2 回目以降のコンパイルで Reloading Domain から戻らない
- 原因: 静的コンストラクタで delayCall を重複登録、受信スレッドを終了待ちしない、リロード中に Unity API を呼ぶ
- 対策: `beforeAssemblyReload` でサーバーとスレッドを止める。delayCall は一度だけ。リロード中フラグで API 呼び出しを止める
- 実例: 2026-02-03 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:270-295, MARQ-CAU 11 節

### MonoBehaviour / ScriptableObject は同名ファイルに 1 クラスずつ
- 症状: 「The script class couldn't be found」「No script asset for CameraRecordTrack」。`AnimationClip.SetCurve(typeof(X), ...)` のカーブが丸ごと落ちる
- 原因: MonoScript はクラス名と同名の .cs でしか解決されない
- 対策: MonoBehaviour / ScriptableObject（TrackAsset・PlayableAsset 含む）の派生は同名ファイルへ分ける（PlayableBehaviour や static は同居可）。壊れた .anim / Timeline は再記録か再バインド
- 実例: 2026-06-18/19 Submod_RealtimeLiveUtility
- 自動検出: 候補（1 ファイル内の該当クラス数を数える hook スクリプト。正規表現単体では不可）
- 出典: SL:1489-1497, 1589-1599

### 名前で引くと同名の別物を掴む
- 症状: マテリアルや Renderer を変えても画面が変わらず長時間誤診。Play 後に別の Timeline を書き出す
- 原因: GameObject.Find や名前だけのパスは同名の先頭を返す。シーン参照は Play で切れる
- 対策: 同名の数を数え instanceId / 完全パスで特定。画面の 1 箇所を変えて当たりを確かめてから本題。永続化はシーンパス + ルートからの兄弟インデックス列で持ち、名前は照合に使う。ロード済み全シーンを探す
- 実例: 2026-09-02 2609SuiseiTour26 / 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:3341-3354 / VL:1472-1474

### GameObject と Transform の GetInstanceID は別の値
- 症状: ツリーの行が描画されない
- 原因: 作る側 GameObject、引く側 Transform の ID を辞書キーにしていた
- 対策: キーの型を統一
- 実例: 2026-06-13 Submod_RealtimeLiveUtility（PlayEditPersistWindow）
- 自動検出: 不可
- 出典: SL:1285-1293

### Edit モードではスキニング・BlendShape・Humanoid がすぐには反映されない
- 症状: 表情を当てて撮るとニュートラルや前の表情が写る（ラベルと顔がずれる）。PlayableGraph を SetTime + Evaluate しても Hips の差 0°（GUI 再生では動いて見える）
- 原因: スキニングはフレーム単位で Render より後。Edit モードの手動評価は Humanoid の骨に書かない
- 対策: 当てて次のフレームで撮る／`SkinnedMeshRenderer.BakeMesh` を一時 MeshRenderer で描く。撮影中は FacialController / OscRx_LipSync を止める。クリップは `AnimationClip.SampleAnimation`（Humanoid でも効く、16.4°）。テストで「当てた直後に動いたか」を測る
- 実例: 2026-06-21 Ext_Haruluna（FacialDetector）/ 2026-09-24 ModelChecker（×2）/ 2026-09-28 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: rules/unity.md / Notion 3e5e4d4b-751b-8129-9554-dfe2df9574c0, 3e5e4d4b-751b-8116-974e-dcea9c8a34d1 / SL:1640-1643 / TS:273 / MC\log\claudeLog.txt:10

### SkinnedMeshRenderer の Transform を動かしても描画は動かない
- 症状: 「画面のどれがこれか」を位置移動で確かめて誤判定
- 原因: 描画はボーン駆動
- 対策: Renderer の有効/無効や _AsUnlit で確かめる
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:3356-3358

### スクリプトで変えた直後の Game ビューは描き直されない
- 症状: 値を変えたのにキャプチャに出ない
- 原因: Edit モードの Game ビューは再描画要求が無いと更新されない
- 対策: Repaint を要求するかタブをクリックしてから撮る
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:29

### スクリプトで Prefab を変換しても開いているシーンのインスタンスにすぐ反映されない
- 症状: Play すると古い構成のまま動く
- 原因: 開いているシーンのインスタンスが古い状態で残る
- 対策: シーンを読み直すか再起動してから検証
- 実例: 2026-06-03 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:1077

### ScreenCapture.CaptureScreenshot は非同期で Edit モードでは撮れない
- 症状: 戻った時点でファイルが無い。非再生時は撮れない。Editor UI は写らない
- 原因: 次フレームの描画時に撮る仕様。Edit モードでは Game ビューが描画されない
- 対策: Win32 PrintWindow(PW_RENDERFULLCONTENT) で同期キャプチャ
- 実例: 2026-03-22 unity-mcp
- 自動検出: 候補（patterns-unity-core.md `cs-editor-screencapture`）
- 出典: UM\.claude\claudeLog.txt:103-106

### PreviewRenderUtility の書き出しで背景色がリニア変換され、NPOT が 2048² に拡縮される
- 症状: 一覧画像の背景色が違う。取り込むと引き伸ばされる
- 原因: リニア色空間の変換、テクスチャの NPOT 既定
- 対策: 色を変換して指定、NPOT を None に
- 実例: 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: MC\log\claudeLog.txt:10

### Unity の表面の向きは Cross(b-a, c-a) 側
- 症状: 裏返り判定が全部逆
- 原因: 巻き順と外積の符号の取り違え
- 対策: Cube でテストして符号を固定
- 実例: 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: MC\log\claudeLog.txt:7

### 別シーンへ複製するときは選択を外してから Paste
- 症状: 貼ったはずのオブジェクトが無い（成功したのに何も無い）。名前に ` (1)` が付く
- 原因: 選択が残っていると貼り付けは選択オブジェクトの隣＝元シーン側に入り、元シーンを閉じると消える
- 対策: `Unsupported.CopyGameObjectsToPasteboard` → `SetActiveScene(新シーン)` → `Selection.activeGameObject = null` → `PasteGameObjectsFromPasteboard`。`pasted.scene == 新シーン` を確かめ、付いた連番を戻す。シーンをまたぐ参照は保存時に外れる。複製元の非アクティブ状態も引き継ぐ
- 実例: 2026-09-26（rules/unity.md）
- 自動検出: 不可
- 出典: rules/unity.md「FBX をスクリプトで取り込む・置くとき」

### シーン YAML の日本語名は grep で当たらない
- 症状: `grep "みなとん" *.unity` が 0 件で「どのシーンにも無い」と誤判定
- 原因: 日本語名は `\uXXXX` でエスケープされて保存される
- 対策: MCP（get_gameobject_info）で引くか、`\u` 形式に直すか、ASCII 部分（`_setupped` 等）で grep
- 実例: 2026-09-26（rules/unity.md）
- 自動検出: 候補（patterns-unity-core.md `grep-japanese-in-unity-yaml`）
- 出典: rules/unity.md

### 階層を複製するとき自前で作った中間親の activeSelf を引き継ぎ忘れる
- 症状: 元は非アクティブ親の下の灯体が複製側で点灯（アクティブ 1347 / 非アクティブ 0）
- 原因: Instantiate は対象自身の activeSelf は引き継ぐが、自前の中間親は既定 active
- 対策: 中間親に activeSelf・tag・layer をコピー。複製前後のアクティブ内訳をレポートして食い違いを警告
- 実例: 2026-09-08 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:175-185

### 起動中のファイル削除・git の巻き戻しで Safe Mode / CS2001
- 症状: 再起動で Safe Mode。消したはずのファイルで CS2001
- 原因: 親リポジトリの reset + pull で削除コミットが消えファイルが復活／起動中の削除を AssetDatabase が拾わない
- 対策: git 操作後は差分を確認。起動中に消したら Refresh（forceUpdate）か再起動
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:196-197

### Unity の外で作ったファイルには .meta が無く、配布先で GUID が振り直される
- 症状: .unitypackage や Submodule 取り込み後に参照が切れる
- 原因: .meta が無いと取り込み側で新規採番
- 対策: 外で作ったファイル・フォルダは .meta を作ってからコミット／梱包
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:3297-3298

### コミット済みの .meta にコンフリクトマーカーが残っている
- 症状: GUID が解決できない／インポートエラー
- 原因: 過去のマージで未解消のままコミット
- 対策: マージ後に .meta を grep で検査してからコミット
- 実例: 2026-09-23 SinkaiFes2026（サブモジュール 4 件）
- 自動検出: 候補（patterns-unity-core.md `unity-yaml-conflict-marker`）
- 出典: SinkaiFes2026 log/claudeLog.txt:509-511

### UPM パッケージを PackageCache から手でコピーすると GUID が衝突し全アセットの GUID が作り直される
- 症状: `ArgumentException: input asset name cannot be empty` が連鎖。GUID をハードコードした参照が全部切れる
- 原因: git 参照が有効なままコピーを読ませた
- 対策: Package Manager の Embed（右クリック → Embed）で GUID を保ってローカル化
- 実例: 2026-05-31 vortex_urp（lilToon）
- 自動検出: 候補（patterns-unity-core.md `copy-packagecache-to-packages`）
- 出典: VC:250-256

### AssetDatabase.ExportPackage: フォルダ + Recurse だと除外が効かない
- 症状: 除外したファイルが戻る、意図しないアセットが入る。32MB で約 90 秒メインスレッドを塞ぐ
- 原因: Recurse は後段で効く。IncludeDependencies は芋づる
- 対策: ファイルを平坦に列挙して ExportPackageOptions.Default。出力は tar を開いて pathname を全件検証。MCP の export_package（非同期）を使う
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:3174-3185, 3205-3215

### GenericMenu の項目名の '/' はサブメニュー区切り
- 症状: 「univ: 12 / chan: 143」が階層に割れる
- 原因: GenericMenu のパス仕様
- 対策: U+2215 などに置き換える
- 実例: 2026-08-28 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:2477-2479

### IMGUI: hover で style.hover に切り替わり normal だけ塗った色が消える
- 症状: ホバー中だけ警告色や選択色が既定へ戻る。ハイライトが前の行に残る
- 原因: normal しか設定していない。MouseMove が来ない
- 対策: normal/hover/active/focused 全部に色。`wantsMouseMove=true` と MouseMove で Repaint
- 実例: 2026-08-27 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:2248-2255

### IMGUI でクリックをイベント発生時に処理すると描画順依存の情報が半分しか無い
- 症状: 範囲選択・選択数が正しく出ず、メニューが常に無効
- 原因: クリック時点ではクリック行より上の行しか積まれていない
- 対策: クリックを保留し、描画し終えてから捌く
- 実例: 2026-08-28 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:2455-2458

### UI Toolkit のアイコンフォントは -unity-font-definition
- 症状: 別のグリフが出る（□にならないので効いていると誤認）。警告なし
- 原因: 継承された FontAsset(TextCore) が `-unity-font: url(ttf)` に勝つ
- 対策: `-unity-font-definition: url("Fonts/lucide.ttf")`。グリフは C# で `\uXXXX`。コードポイントは fonttools で cmap 確認
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 候補 edit .uss `-unity-font\s*:`（テキスト用フォントでは正しいので未採用）
- 出典: LMR-MEM/uitoolkit-custom-font-definition.md, LMR-LOG:417-419

### UI Toolkit の worldBound は transform の scale を反映しない
- 症状: ズーム時にクリック判定がずれ、中心から離れるほどずれる
- 原因: worldBound で位置を取りつつズームを二重に掛けていた
- 対策: `WorldToLocal` / `LocalToWorld` で変換
- 実例: 2026-02-04 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU 8 節, MARQ-LOG:1010-1060

### UI Toolkit: flex の中央寄せは子が親より大きいと中央にならない
- 症状: キャンバスを 4K にするとビューポート中央に来ない
- 原因: center 寄せは子がはみ出すと片側に寄る
- 対策: `position:absolute; left/top:50%` + transform で -size/2
- 実例: 2026-02-04 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:1040-1055

### UI Toolkit: ルートで TrickleDown の KeyDown を止めると子パネルのキー操作が死ぬ
- 症状: Hierarchy の上下キーで別機能が発動し選択が動かない
- 原因: キャプチャフェーズで先に処理して伝搬を止めている
- 対策: `focusController.focusedElement` がパネル内ならルート処理をスキップ
- 実例: 2026-02-26 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:2368-2385

### UXML に USS をリンクし忘れると未スタイルで崩れて見える
- 症状: UI Toolkit の画面が崩れて見える
- 原因: UXML↔USS 未リンク
- 対策: UXML のリンクとコードの `styleSheets.Add` を確認
- 実例: 2026-06-01（CLAUDE.md の例）/ 2026-06 ReLink
- 自動検出: 不可
- 出典: CLAUDE.md「一時回避策に逃げない」の例 / D---Personal-Project-ReLink/memory/conduit-architecture.md:13

### ドメインリロードのたびに Crest の hlsl と codecoverage の Settings.json に改行だけの差分
- 症状: git に M が出る（内容差分なし）
- 原因: Unity とパッケージが再生成する
- 対策: リロード由来と見分けて報告。コミットに含めない
- 実例: 2026-09-14 Ext_Palletproject / 2026-09 Ext_TokinoSora_2026-pia（vortex）
- 自動検出: 不可
- 出典: PL:66-68, M:D---ProjectBLUE-Project-Ext-Palletproject/unity-mcp-http-fallback.md

### Auto Refresh が無効のプロジェクトがある
- skill vortex-timeline-setup に記載（vortex 案件。dll とソースの更新時刻を比べる）。実例 2026-09-24 SinkaiFes2026

### 非同期のシェーダーコンパイルが On でも、Play 中に初めて使う組み合わせで止まる
- 症状: Asynchronous Shader Compilation は On なのに、Timeline の再生中にときどき Shader Compile が走って止まる。
- 原因: Blit で描くもの（URP の CoreBlit・UberPost、NiloToon の Uber Post、Crest の水中など）は非同期にならない（Unity マニュアル Asynchronous shader compilation）。`#pragma editor_sync_compilation` 付きのシェーダー（URP の CoreBlit・SSAO）も同じ。Recorder は録画中に非同期を切る。
  コンパイル済みは Library/ShaderCache に残るので、止まるのは初めての組み合わせ・シェーダーやパッケージが変わった後・別の PC。
- 対策: 使う組み合わせを ShaderVariantCollection に記録し（ShaderUtil の internal の記録 = Graphics 設定の Save to asset と同じ）、Play の開始時に WarmUp する Editor のフックを置く。
  Editor の WarmUp は未コンパイルの組み合わせを先にコンパイルする（新しいキーワードのシェーダーで IsPassCompiled false → true、何もしないと false のまま。2026-10-19 実測）。
  SinkaiFes2026（キャッシュを一時的に外した状態）: 先読み無し 止まり 2 回・最大 180 ms → 有り 0 回・最大 40 ms。キャッシュがあれば WarmUp は 0.3 秒。
- 実例: 2026-10-19 SinkaiFes2026（Scripts/Editor/ShaderWarmupOnPlay.cs・Shaders/ShinkaiFes2026.shadervariants）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-19

### 生成物を仕上げてから RegisterCreatedObjectUndo すると、Redo で他の物からの参照が壊れる
- 症状: Editor の道具でキャラを生成 → 配線（uOscServer の永続リスナー・CharacterActivator の登録は Undo.RecordObject）→ 最後に RegisterCreatedObjectUndo。Undo は全部戻るが、Redo の後に OSC のリスナーの宛先が「Object @ キャラ名」（型の無い参照）になる。
- 原因: 同じ Undo グループの中で、記録した順に戻される。生成の記録が最後だと、Redo で配線先（サーバー）の値がキャラより先に戻り、まだ無いコンポーネントを指したまま残る。
- 対策: 生成の直後に `RegisterCreatedObjectUndo`、続けて `RegisterFullObjectHierarchyUndo`（以降の素の書き込みが flush で生成直後の姿に戻らないように）。グループは `IncrementCurrentGroup` → 最後に `CollapseUndoOperations`、失敗は `RevertAllDownToGroup`。
  確かめ方: 道具を流す → Inspect（参照の一覧）→ Undo → 前と一致 → Redo → 流した直後と一致 → 保存して開き直し → 一致。
- 実例: 2026-10-19 SinkaiFes2026（vortex-character-setup の SetupCharacterEx）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-19
