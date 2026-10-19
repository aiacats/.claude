# unity-build の罠（カタログ）
Player ビルド・asmdef・スクリプト定義・IL2CPP/stripping・パッケージ（UPM）・manifest。トラブル時に grep で引く。

### Player ビルドを壊さない（Runtime 側の UnityEditor 依存）
- 症状: エディタのコンパイルはエラー 0 なのに Player ビルドだけ CS0246 / CS0234 / CS0103 で落ちる（errors=28 など）
- 原因: Runtime asmdef（Editor 限定でないアセンブリ）の中の UnityEditor 依存は、エディタ用コンパイルでは UnityEditor.dll が見えるので通ってしまう。紛れ方: CustomEditor / MenuItem / AssetDatabase / EditorApplication を Runtime のファイルに同居、IDE の自動 using（`Codice.CM.Common` = Plastic SCM、`Mono.Cecil.Cil`）、`[ContextMenu]` / OnValidate 内の UnityEditor API。逆向きに `using` を `#if UNITY_EDITOR` の中へ入れ、ガード外で使っていて CS0103 になることもある
- 対策: UnityEditor の型は `Editor/` フォルダか `includePlatforms: ["Editor"]` の asmdef へ。Runtime に書くなら `using UnityEditor;` からクラス末尾まで `#if UNITY_EDITOR`。再生中判定は `Application.isPlaying`。触ったファイルの using を見直し、Runtime 配下を触ったら grep でガードを確認、大きな変更の前に MCP `build_player` で実際に通す
- 実例: 2026-09-13 SinkaiFes2026（サブモジュール Runtime 4 ファイル）/ 2026-08-27 Unity_ArtNetRecorder（Mono.Cecil）/ 2026-09-06 lll-12（RemoteLipSyncClient.cs CS0103）/ 2026-06-01 LiveMultiRecorder（Submod_RealtimeLiveUtility の未ガード 4 ファイル） / 2026-10-19 SinkaiFes2026（Assets の Runtime フォルダの EditorWindow・CustomEditor と、MonoBehaviour のフィールドの UnityEditor.DefaultAsset。`using UnityEditor;` だけの 35 本はビルドが通った（Crest などが Runtime に UnityEditor の名前空間を作っている）。止まるのは型を使ったとき。skill vortex-project-setup の check `editor-api-in-player` で拾える）
- 自動検出: hook `cs-runtime-unityeditor` / `cs-codice-using`。追加案 patterns-unity-core.md `cs-runtime-mono-cecil-using` / `cs-runtime-unityeditor-qualified`
- 出典: rules/unity.md「Player ビルドを壊さない書き方」/ Notion 3dae4d4b-751b-81b4-a407-ca1633c03759 / SinkaiFes2026 log/claudeLog.txt:34-41, 48-55 / AL:15 / LLL-LOG:54-61 / LMR-LOG:324-352

### UnityEditor を参照するプラグイン DLL が Any プラットフォームだとリンカで落ちる
- 症状: スクリプトは全部ガード済みなのに "UnityEditor.dll assembly is referenced by user code, but this is not allowed"（UnityLinker の 'Failed to resolve assembly: UnityEditor' の後）
- 原因: VRMSkirtTool.dll / VRMSpringBoneTool.dll など UnityEditor を参照する DLL の .meta が `Any: enabled 1`
- 対策: .dll.meta を `Any:0 / Editor:1` に。探すのは `Library/Bee/artifacts/rsp/*.rsp` の `--include-unity-root-assembly` 一覧か、`grep -la UnityEditor` で Assets 配下の DLL を走査
- 実例: 2026-06-01 LiveMultiRecorder / 2026-09-13 SinkaiFes2026
- 自動検出: 不可（DLL の中身と .meta の組で判定が要る）
- 出典: Notion 3dae4d4b-751b-81b4-a407-ca1633c03759 / LMR-LOG:340-352 / SinkaiFes2026 log/claudeLog.txt:62-64 / skill vortex-character-setup にも記載

### ビルド失敗の真因は Editor.log の "scripts had compiler errors"。Missing Prefab は目くらまし
- 症状: build_player が十数秒で Failed。コンソールは Missing Prefab で埋まる
- 原因: Player 向けコンパイルの CS エラー。Missing Prefab はビルドを止めない。Rewired_Core.dll の GUID 不一致警告も止めない
- 対策: Editor.log の `Error building Player because scripts had compiler errors` の直前の `error CS` を見る（Editor.log は他の Unity と共有に注意）
- 実例: 2026-09-06 lll-12 / 2026-06-01 LiveMultiRecorder（Rewired_Core）
- 自動検出: 不可
- 出典: LLL-LOG:54-61 / LMR-LOG:300-313

### 同じパッケージ・同名 asmdef が二重になるとコンパイルが止まり「エラー 0」に見える
- 症状: ある時刻以降 ScriptAssemblies が更新されていない。Unity が asmdef.meta の GUID を振り直す
- 原因: サブモジュールのブランチ切替で Rewired がパッケージ内と Assets の両方に入る、など同名 asmdef の重複
- 対策: サブモジュール切替・取り込みの後は `Library/ScriptAssemblies/*.dll` の更新時刻とコンパイル結果を確認。二重はどちらかを消す。新依存は manifest へ
- 実例: 2026-09-13 SinkaiFes2026（vortex）/ 2026-09-23 SinkaiFes2026（unity-mcp の二重配置。traps-catalog/unity-mcp.md）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:56-61 / Notion 3dae4d4b-751b-81b4-a407-ca1633c03759

### Runtime だけ検証して Editor アセンブリの参照漏れを見逃す
- 症状: 取り込んだコミットの Editor スクリプトで CS0234 / CS0246、Editor アセンブリ全体がコンパイル不可
- 原因: URP の型を使う Editor スクリプトが足されたのに vortexUtility.Editor.asmdef に参照が無い。検証は Runtime の csproj しかビルドしていなかった
- 対策: Submodule / パッケージを変えたら Runtime と Editor の両アセンブリを検証
- 実例: 2026-08-18 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「検証の追加ルール」/ VL:505-521

### Build が Succeeded でもシェーダエラーは残る
- 症状: Succeeded だがシェーダエラー 43 件。Player ログに VLB の LogError
- 原因: Unity はシェーダエラーでビルドを失敗させない
- 対策: exe を起動して -logFile の Player ログを確認、キャプチャで見るまで「通った」と言わない
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:1731-1736, 1800-1817

### Shader.Find はビルドで null（参照されていないシェーダは外れる）
- 症状: Editor では動くがビルドで null / マゼンタ。マテリアルが作れない、Spout 送信が初期化失敗
- 原因: シーン参照・Resources・Always Included Shaders のどれにも無いシェーダはビルドから除外。`Hidden/Klak/Spout/Blit` のようなパッケージ内シェーダも同じ
- 対策: シェーダを持つ ScriptableObject を Resources に置いて Resources.Load（IPreprocessBuildWithReport で自動生成）、Always Included Shaders、またはマテリアルアセット参照
- 実例: 2026-02-05 / 2026-02-26 MARQ-Studio / 2026-06-21 ReLink（懸念）
- 自動検出: 候補（patterns-unity-core.md `cs-runtime-shader-find`）
- 出典: MARQ-CAU:7-30, MARQ-LOG:1617, 2299-2320 / RL\.claude\claudeLog.txt:277-279

### Resources 配下のシェーダは参照が無くても同梱され、壊れた Built-in シェーダでビルドが落ちる
- 症状: URP のビルドで `'GetCameraPositionWS' undeclared` / `FragCopyExact`・`VertBlit` 欠落。使っていないシェーダで落ちる
- 原因: `Resources/` 配下は参照有無に関係なく含まれる。Built-in RP 用入口が URP 前提の HLSL を include
- 対策: 未使用と確認し承認を得て削除か Resources 外へ（submodule なら非破壊の案も出す）
- 実例: 2026-06-01 LiveMultiRecorder / 2026-09-13 lll-12（VolumetricLightsBundle/Builtin）
- 自動検出: 不可
- 出典: LMR-LOG:324-338 / LLL-LOG:330

### UXML/USS を Resources 外に置くとビルドで読めない
- 症状: ランタイムの UI Toolkit 画面がビルドで出ない。`Resources.Load<VisualTreeAsset>()` が null
- 原因: 文字列パスでロードするアセットが Resources 外でビルドに含まれない
- 対策: `Resources/UI/` へ置くかシーン/SO から直接参照。UXML の `<Style src>` は相対パス
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU:34-55, MARQ-LOG:1520-1545

### ビルドを実行すると設定ファイルが書き換わる
- 症状: ProjectSettings（StaticBatching・Scripting Define）、PC_RPAsset の m_PrefilteringMode*、URP GlobalSettings の m_RuntimeSettings、lilToonSetting.json に差分
- 原因: ビルド時に URP / lilToon / VLB が再計算して書き戻す
- 対策: 意図した変更と分けてコミット。副産物の扱いはユーザー判断
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:1767-1772, 1855-1862

### Player 設定の解像度は 4 項目セットでないと効かない
- 症状: 1920x1080 を指定してもウィンドウで出ない、枠を掴めない
- 原因: defaultIsNativeResolution=1 でディスプレイ解像度優先、FullScreenWindow、resizableWindow=0
- 対策: 4 項目をまとめて PlayerSettings setter + SaveAssets
- 実例: 2026-08-28 / 2026-08-31 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:2412-2419, 2735-2746

### 初回ビルドのシェーダバリアント生成が 40〜70 分かかる
- 症状: "Compiling shader variants" のまま 1 時間近く進まない（止まって見える）
- 原因: バリアント爆発（URP + MToon + RealtimeLiveUtility 同梱シェーダ）。2 回目以降はキャッシュで速い
- 対策: 初回は background 実行 + 5 分ごとに Editor.log を確認。短縮は Shader Stripping
- 実例: 2026-06-01 LiveMultiRecorder（約 69 分）
- 自動検出: 不可
- 出典: LMR-LOG:315-322

### ビルド開始時の「Scene(s) Have Been Modified」モーダルで build_player が止まる
- 症状: build_player が isRunning のまま進まない
- 原因: 未保存シーンの確認モーダル。win-gui `click_text "Save"` が本文の "save..." を押していた
- 対策: ビルド前に save_scene。押すなら occurrence 指定でボタン行を狙う
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:253-256

### Editor が同じプロジェクトを開いたままだと CLI のバッチビルドは exit 21
- 症状: `another Unity instance is running` で中断。コンパイルエラーと取り違えやすい
- 原因: プロジェクトのロックを Editor が持つ
- 対策: Editor を閉じてから。開いたまま確かめるなら MCP か Roslyn 単体コンパイル
- 実例: 2026-06 Unity_ArtNetRecorder
- 自動検出: 不可（実行中プロセスとの照合が要る）
- 出典: AC:60-61

### 同梱 Roslyn の単体コンパイルは偽陰性があり、参照の組み方にも罠がある
- 症状: Roslyn は通ったのに Unity で CS0246。参照を足すと CS0433（型の重複）が大量、CS0012 で enum の基底型が引けない
- 原因: asmdef の参照条件までは再現しない。UnityEditor.dll と UnityEditor.CoreModule.dll は型が重複。netstandard.dll だけでは mscorlib 由来の型を引けない
- 対策: `Editor/Data/NetCoreRuntime/dotnet.exe` + `DotNetSdkRoslyn/csc.dll`、参照は `Managed/UnityEngine/*.dll` + `NetStandard/ref/2.1.0/netstandard.dll` + `NetStandard/compat/2.1.0/shims/netfx/mscorlib.dll`（UnityEditor.dll は入れない）。空白入りパスは `@rsp`。csproj か `Library/Bee` の .rsp を流用すると早い。Unity を開いたら force_compilation で確かめ直す
- 実例: 2026-08-27 Unity_ArtNetRecorder / 2026-09-14 Ext_Palletproject / 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: rules/unity.md「検証の追加ルール」/ Notion 3c9e4d4b-751b-815c-aa39-e04c83225291 / VL:1495-1497 / PL:47

### Packages/manifest.json の先頭に BOM があると Package Manager がパースに失敗する
- 症状: パッケージが解決されずコンパイルエラーが連鎖。Editor.log に `Non-whitespace before {[. Char: 65279`
- 原因: BOM 付き UTF-8 で保存
- 対策: BOM を外し LF に
- 実例: 2026-05-12 Submod_RealtimeLiveUtility
- 自動検出: 候補（patterns-unity-core.md `unity-json-bom`）
- 出典: SL:27-28

### manifest.json を外で編集しても Unity が再解決しない／削除が反映されない
- 症状: 追加したパッケージが PackageCache に来ない。消したパッケージのアセンブリのエラーが残る
- 原因: フォーカスだけでは再解決されない。削除は in-memory のパッケージリストが更新されない
- 対策: 追加は `packages-lock.json` を消して force_compilation。削除は lock 削除 + Editor 再起動
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可（編集自体は正しい操作）
- 出典: LMR-MD:24-38, LMR-LOG:30-36, 80-85

### R3.Unity はコアの R3（NuGet）が別途要る
- 症状: `Observable<>` / `Subject<>` / `Unit` が見つからない CS0246 が 411〜414 件
- 原因: git の com.cysharp.r3 は Unity 用ラッパーのみ。コア R3 と依存（Microsoft.Bcl.TimeProvider 等）は NuGetForUnity
- 対策: NuGetForUnity でコア R3。R3.Unity のタグを固定
- 実例: 2026-03-04 EXT_Kamitsubaki_Composite / 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:71-80, KMT-LOG:121-140

### パッケージ内のテストは manifest の testables に載せないと 0 件
- 症状: Test Runner がパッケージ内のテストを見つけない
- 原因: `testables` 未登録
- 対策: `"testables": ["<package名>"]`
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:66-68

### asmdef から Assembly-CSharp（asmdef 無しのプラグイン）は参照できない
- 症状: FinalIK の型が asmdef 配下から見えない
- 原因: Assembly-CSharp は asmdef の参照先にできない
- 対策: 使う層を Assembly-CSharp に置き、自前 asmdef は autoReferenced:true
- 実例: 2026-06-20 ReLink
- 自動検出: 不可
- 出典: RL\.claude\claudeLog.txt:36-38, MEM(ReLink)\conduit-architecture.md

### UniVRM の LoadAsync は autoReferenced:false の UniGLTF.Utils に依存
- 症状: Assembly-CSharp から `VrmUtility.LoadAsync` で CS0012 / CS0246（IAwaitCaller）
- 原因: IAwaitCaller が autoReferenced:false のアセンブリにある
- 対策: asmdef から明示参照、または同期の `GlbFileParser.Parse → VRMData → VRMImporterContext.Load()`
- 実例: 2026-06-20 ReLink（UniVRM 0.131.1）
- 自動検出: 不可
- 出典: RL\.claude\claudeLog.txt:110-113

### asmdef の無いプラグインを Packages へ移すと参照が切れる／asmdef 名がネイティブ DLL と同名だと衝突
- 症状: CS0246 / CS0118 が 19 件。asmdef を足すと「hard to diagnose...crashes」の同名衝突警告
- 原因: パッケージ内では既定アセンブリ（Assembly-CSharp / -Editor）が効かない。asmdef 名 `AVProDeckLink` が Plugins/x86_64/AVProDeckLink.dll と同名
- 対策: Runtime / Editor の asmdef を足す。名前は `*.Runtime` などネイティブ DLL と変える
- 実例: 2026-06-03 Submod_RealtimeLiveUtility（AVProDeckLink / AVProLiveCamera）
- 自動検出: 不可
- 出典: SL:805-818

### 自前の namespace や型に Math / Editor / HumanBone を使うと標準の型と衝突する
- 症状: `Math.Sin` が CS0234、HumanBone が CS0104
- 原因: 自前 `X.Core.Math` が優先解決、同名型の二重 import
- 対策: System.Math を完全修飾 / using エイリアス。予約的な名前を namespace・型名に使わない（vortex.Editor の CS0118 は traps-catalog/unity-editor.md）
- 実例: 2026-06-20 ReLink
- 自動検出: 候補 edit `namespace\s+[\w.]+\.(Math|Editor)\b`（既存 vortex.Editor など変えられない名前に当たるため未採用）
- 出典: RL\.claude\claudeLog.txt:34-35

### com.autodesk.fbx（FBX SDK）は Player で解決できない
- 症状: Player ビルドで `CS0246 Autodesk / FbxAnimCurve / FbxTime`
- 原因: asmdef の includePlatforms に Standalone があっても FBX SDK は実質 Editor 専用
- 対策: FBX 変換の asmdef を Editor 専用化
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:255-262, 164

### IL2CPP へ切り替えるとリフレクション頼みの項目が黙って消える
- 症状: （想定）命名規則で自動収集している項目が Player で拾えない
- 原因: managed stripping。現状は Mono + stripping 無効（実測）なので問題が出ていない
- 対策: 切り替えるなら `link.xml` か `[Preserve]`
- 実例: なし（rules/unity.md の注意）
- 自動検出: 不可
- 出典: rules/unity.md「設計の癖」

### 未コミットのビルド必須修正が checkout で消える
- 症状: 前に直した CS0103 で再びビルド失敗
- 原因: 未コミットのまま作業ツリーを別コミット（detached HEAD）へ切り替えた
- 対策: ビルド必須の修正はその場でコミット。submodule で出来ないなら claudeLog とプロジェクト CLAUDE.md に「未コミット」を残す
- 実例: 2026-09-23 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:351-356

## vortex 案件

### 分離パッケージの依存宣言漏れ（一度もコンパイル検証されていない）
- 症状: 移植直後に CS0246（ReadOnlyAttribute / uOSC / Animation.Rigging）。main にマージ後も manifest 欠落
- 原因: 分離時に属性クラス・uOSC・Rigging 依存を package.json / asmdef / manifest に書いていない
- 対策: 取り込み時に asmdef の references と manifest を突き合わせる。uOSC は `upm@2.2.0` 等に固定
- 実例: 2026-08-04 / 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:67-76, 1447-1471

### Submod_RealtimeLiveUtility はそのままではスタンドアロンビルド不可
- 症状: 4 エラーで失敗
- 原因: Runtime 約 20 ファイルに裸の `using UnityEditor;`（未ガード 4）、Resources 配下の Built-in シェーダ、VRMTools DLL の .meta
- 対策: ガード・未使用シェーダ除去・DLL .meta を Editor 限定。submodule はコミットしない、削除は説明と承認の後
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:324-352

### realtime-live-utility を別プロジェクトへ入れると Cinemachine 2/3・PPv2・Rewired・dynamic で大量エラー
- 症状: PostProcessAdjuster / DivideController / FacialManager / PusherData でエラー
- 原因: Cinemachine 2.8.6 前提（Unity 6 は 3.x）、PPv2 型、有料 Rewired、`dynamic`（Microsoft.CSharp）
- 対策: versionDefine で `USE_URP`、Rewired 依存を `#if REWIRED`、`dynamic`→object。file: パスは Packages/ からの相対
- 実例: 2026-03-04 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:119-170

### uLipSyncBlendShapeVRM ↔ vortexUtility.Runtime の循環参照
- 症状: CS0246 `vortex` / `IBlendShapeProvider`
- 原因: vortexUtility.Runtime が uLipSync.Samples.VRM.Runtime を参照済みで、逆向きを足すと循環
- 対策: サンプル側の vortex 依存を外し、リセットは呼び出し元（FacialMorphController）で
- 実例: 2026-03-05 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:655-668

### 同名の型がサブモジュールと Assets の両方にあると Editor asmdef で CS0433
- 症状: Inspector 拡張を Editor 用 asmdef に置くと CS0433
- 原因: MidiEffectEmitter などがサブモジュールと Assets/SubModuleRefScripts の両方に同名で存在
- 対策: Inspector は SubmoduleRef 側に `#if UNITY_EDITOR` で置く（CS0436 警告は意図どおり）
- 実例: 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: PL:44-46, 57
