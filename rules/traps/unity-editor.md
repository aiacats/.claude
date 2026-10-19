---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
---
# unity-editor の罠
全件は ~/.claude/traps-catalog/unity-editor.md。ここは再発しやすいものだけ。

### Unity を強制終了しない
taskkill / Stop-Process で落とすと次回起動が遅くなる。原因は Library の書き戻しが飛ぶこと。→ `(Get-Process -Id <pid>).CloseMainWindow()` で閉じる。先にタイトルの `*` で未保存を見て、ProcessName と StartTime で同定する。（CLAUDE.md 2026-09-23）

### vortex.EditorTools で Editor を継承する
`namespace vortex.EditorTools` の中の `: Editor` が CS0118 になり Safe Mode まで行く。原因はパッケージ側の `vortex.Editor` 名前空間に解決されること。→ `: UnityEditor.Editor` と完全修飾する。（実例: 2026-09-24 Ext_TokinoSora_2026-pia）

### Editor.log は他の Unity と共有される
`grep "error CS" Editor.log` に別プロジェクトのエラーが混ざり、先頭には旧セッションの残骸も残る。原因は全 Unity が同じファイルへ書き、起動時に切り詰めないこと。→ コンパイル可否は MCP か `Library/ScriptAssemblies/*.dll` の時刻で見る。自分で起動するなら `-logFile <root>/Logs/editor-session.log`。（実例: 2026-09-24 vortex_urp / 2026-08-04 2609SuiseiTour26）

### 背面の Unity は Refresh も delayCall も回さない
外で書き換えたファイルを拾わず（Refresh が 0.001 秒で終わる）、.vrm の Prefab もできない。原因は背面の Editor に更新ティックが来ないこと。→ `AssetDatabase.ImportAsset(<path>)` を個別に呼び dll の時刻で確かめる。自作の delayCall は `EditorApplication.QueuePlayerLoopUpdate()` で起こす。（実例: 2026-09-14 Ext_Palletproject / 2026-06-20 ReLink / 2026-09-24 ModelChecker）

### 非フォーカスの Unity は Update もフレームも進まない
OSC に無反応でフォーカスした瞬間にまとめて処理、キャプチャが古い、Profiler や Play 中の計測が終わらない。原因は Run In Background=false と非フォーカス時の間引き。→ 計測・キャプチャ・受信の検証中は前面に保つ。受信系は `Application.runInBackground=true`。（実例: 2026-08-06 2609SuiseiTour26 / 2026-09-06 vortex_urp / 2026-09-23 SinkaiFes2026）

### モーダルが開いているとリロードもインポートも止まる
`Reloading Domain (Busy)` が伸び続ける、新規 .cs に .meta ができない。原因は SettingsPrompt などのモーダルがメインスレッドを握ること。→ 画面全体を撮って探し、閉じてから Refresh。Play 中に force_compilation しない。（実例: 2026-06-01 LiveMultiRecorder / 2026-06 Submod_RealtimeLiveUtility）

### プレハブオーバーライドは値を戻しても残る
検証で触ったフィールドが m_Modifications に残り、以後プレハブの修正が効かない。原因は同値でも一度書けば記録されること。→ 検証したシーンは保存せず git checkout。保存前に propertyPath の内訳を見る。（実例: 2026-09-23 SinkaiFes2026）

### 起動中の .asset / ProjectSettings を文字で書き換えない
VolumeProfile を書き換えても見た目が変わらない、EditorBuildSettings が戻る。原因はメモリ側が正で保存時に書き戻されること。→ SerializedObject / PlayerSettings などの Editor API で書き SaveAssets。（実例: 2026-08-04, 08-24, 08-31 2609SuiseiTour26）

### OnValidate で代入した値はシーンに残らない
Inspector に出ているのに保存されずビルドで空。原因は直接代入が PropertyModification を作らず、OnValidate は Player で呼ばれないこと。→ SerializedProperty で書き直後に ApplyModifiedProperties。（実例: 2026-08-04/05 2609SuiseiTour26）

### 継承すると基底の OnValidate・OnEnable・Inspector が呼ばれない
原因は Unity メッセージが最派生の 1 つだけ呼ばれ、基底の private は拾われないこと。→ 基底から protected virtual のフックを呼ぶ。派生 Editor は基底 Editor を継承して base.OnInspectorGUI()。（実例: 2026-08-05, 08-12, 08-24 2609SuiseiTour26）

### ApplyModifiedProperties は描画し終えてから
Inspector に入れた値が入らない。原因は Apply の後に DrawPropertiesExcluding で描いた項目が確定されないこと。→ Apply は全描画の後。（実例: 2026-09-06 vortex_urp）

### RegisterCreatedObjectUndo の直後の代入は RecordObject を挟む
生成物の参照が保存時に fileID:0 へ戻る。原因は Undo の flush で生成直後のスナップショットに巻き戻ること。→ 代入前に `Undo.RecordObject`。（実例: 2026-07-23 Ext_Palletproject）

### MonoBehaviour / ScriptableObject は同名ファイルに 1 クラス
「The script class couldn't be found」、SetCurve のカーブや Timeline のトラックが黙って落ちる。原因は MonoScript をクラス名と同名の .cs でしか解決しないこと。→ 派生クラスごとにファイルを分ける。（実例: 2026-06-18/19 Submod_RealtimeLiveUtility）

### PackageCache から手でコピーしてローカル化しない
GUID が衝突し全アセットの GUID が作り直され、参照が一斉に切れる。原因は git 参照が有効なままコピーを読ませたこと。→ Package Manager の Embed を使う。（実例: 2026-05-31 vortex_urp）

### ドメインリロードで残る状態と消える状態を混ぜない
Editor 拡張のジョブが Play で始まらない、点検していないのに「問題なし」。原因は ScriptableSingleton やシリアライズ済み bool は残り、update 購読や非シリアライズのコレクションは消えること。→ 購読は `-=` してから `+=`。結果とフラグは同じ寿命で持つ。（実例: 2026-09-23 vortex_urp ×3）

### 名前で引くと同名の別物を掴む
変更しても画面が変わらない、別の Timeline を書き出す。原因は GameObject.Find や名前パスが同名の先頭を返すこと。→ 同名の数を数え、instanceId かシーンパス + 兄弟インデックスで特定。（実例: 2026-09-02 2609SuiseiTour26 / 2026-09-23 vortex_urp）

### Edit モードで表情を当てて同じフレームで撮らない
前の表情やニュートラルが写り、ラベルと顔がずれる。原因はスキニングがフレーム単位で Render より後なこと。→ 当てて次のフレームで撮るか `SkinnedMeshRenderer.BakeMesh`。撮影中は FacialController / OscRx_LipSync を止める（Humanoid の件は unity-runtime.md）。（実例: 2026-06-21 Ext_Haruluna / 2026-09-24 ModelChecker / 2026-09-28 Ext_TokinoSora_2026-pia）

### 別シーンへの Paste は選択を外してから
貼ったはずのオブジェクトが無い。原因は選択が残ると元シーン側に ` (1)` 付きで入り、元シーンを閉じると消えること。→ `Selection.activeGameObject = null` → Paste → `pasted.scene` を確かめる。（実例: 2026-09-26）

### シーン YAML の日本語名は grep で当たらない
`grep "みなとん" *.unity` が 0 件。原因は日本語名が `\uXXXX` で保存されること。→ MCP で引くか、`\u` 形式か ASCII 部分で grep。（実例: 2026-09-26）

### 非同期のシェーダーコンパイルでも Play 中に止まる
Timeline の途中でときどき Shader Compile が走って止まる。原因は Blit で描くポスト（URP の UberPost・NiloToon の Uber Post・Crest の水中）と `editor_sync_compilation` のシェーダーが同期でコンパイルされること。→ 使う組み合わせを ShaderVariantCollection に集め、Play の開始時に WarmUp する（skill vortex-project-setup 6.5）。（実例: 2026-10-19 SinkaiFes2026、止まり 2 回 → 0 回）
