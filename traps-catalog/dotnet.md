# dotnet の罠（カタログ）

.NET（WPF / Avalonia / ImGui / OpenGL / P/Invoke / ビルド）で踏んだ罠の全件。Unity の C# は unity-* カタログ。

## ビルド・テスト・配布

### 起動中の exe がロックされてビルドが MSB3027 で失敗する
- 症状: `dotnet build` / `publish` / `test` が MSB3027（MSB3021、being used by another process）で失敗し、リトライで時間を浪費。
- 原因: 前回起動したアプリ（GUI テスト中のアプリ・MCP プロセス）が exe を掴んでいる。
- 対策: ビルド前に対象プロセスを止める（`taskkill /F /T /IM <App>.exe`）。MCP は別フォルダへ publish してから差し替える。
- 実例: 2026-04 MocapSimulator / 2026-04 WinGuiMcp
- 自動検出: 不可（hook はコマンドの出力を見ない）
- 出典: MocapSimulator:344, 387, MocapSimulator/memory/feedback_kill_before_build.md:9, CLAUDE.md（WinGui MCP の更新フロー）

### dotnet test の後でも App の exe が更新されていない / 変異チェックの後は bin に変異入りの exe が残る
- 症状: 直したはずの GUI が古い挙動のまま（stale exe を起動して検証）。「読み込み完了と出るのにキャラクターが空」という存在しない不具合を追った。
- 原因: テストプロジェクトが Core しか参照しておらず App が再ビルドされない。修正を外して `dotnet test` → ソースを戻す、の最後の回の bin がそのまま残る（ソースは戻っても bin は戻らない）。
- 対策: GUI 検証の前に `dotnet build <sln>` を明示実行し、exe の更新時刻を確かめる。辻褄の合わない挙動は、まず「その行が入った exe か」をログで確かめる。
- 実例: 2026-06-10 Handive / 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: Handive:81-82, Handive/memory/architecture-app1-tracking.md:51, MotionForge/memory/rebuild-after-mutation-check.md:10-15

### nuget.config はディレクトリツリー全体に効く（存在しない local ソースで NU1301）
- 症状: Mac で dotnet restore が NU1301 で失敗。
- 原因: ルートの nuget.config に Windows 絶対パスの local ソース。無関係な csproj の restore でも列挙される。
- 対策: local ソースは使うプロジェクトの配下の nuget.config にだけ置く（階層マージ）。
- 実例: 2026-06-13 MocapSimulator
- 自動検出: 候補 nuget.config の `value="[A-Za-z]:\\`（warn）
- 出典: MocapSimulator:806-821

### 自己完結 publish でファイル参照のアセットが読めない
- 症状: publish ビルドでだけ OBJ 読み込みが失敗。
- 原因: 単一ファイル publish で相対パスのファイルが同梱されない。
- 対策: AvaloniaResource（EmbeddedResource）として埋め込む。
- 実例: 2026-04 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:85

### /ALLUSERS インストールで Program Files\log に書けず起動不能 / インストーラが log を消す
- 症状: 起動しない。アンインストールで未復旧の作業とダンプが消える。
- 対策: 書けるか試して %LOCALAPPDATA% へ（画面 / ログに出す）。インストーラは log を消さない。
- 実例: 2026-09-20 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1722, 1731

### Windows MIDI Services の SDK は NuGet.org に無い
- 症状: `Microsoft.Windows.Devices.Midi2` が restore できない。
- 原因: NuGet.org 未公開（2026-05 時点）。
- 対策: microsoft/MIDI の GitHub releases から nupkg を落としてローカル feed に登録する。
- 実例: 2026-05-03 StreamDeckMIDI
- 自動検出: 不可
- 出典: StreamDeckMIDI/memory/winmidi_services_notes.md:11

### 自己署名では SmartScreen の警告は消えない
- tauri カタログ「署名なし・自己署名の配布では SmartScreen の警告は消えない」を参照。

## 実行時・ライブラリの仕様

### MS Hosting の既定ログが stdout に出て stdio MCP を壊す
- 症状: MCP サーバーが応答不能・プロトコルエラー。
- 原因: Microsoft.Extensions.Hosting のコンソールログが stdout に出る（stdio MCP は stdout が JSON-RPC 専用）。
- 対策: `LogToStandardErrorThreshold = LogLevel.Trace` で全ログを stderr へ。どの言語でも stdio MCP は stdout に何も書かない。
- 実例: 2026-04 WinGuiMcp
- 自動検出: 候補 stdio MCP サーバーの `Console\.WriteLine`（warn。MCP サーバーかどうかをパスで絞る必要あり）
- 出典: MocapSimulator:321-322

### ソケットを Dispose すると Poll 中のスレッドに WSAEINTR が上がりプロセスが落ちる
- 症状: ソース停止・アプリ終了で毎回クラッシュ。
- 原因: バックグラウンドスレッドの未処理例外でプロセスが終了する。
- 対策: Interrupted / OperationAborted / NotSocket / Shutdown / ObjectDisposed を正常終了扱いにし、スレッド本体を try/catch で包む。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:63

### System.Text.Json は System.Numerics.Vector3 を {} と書く
- 症状: 保存・読み戻しでゼロになる（例外なし）。
- 原因: X / Y / Z はフィールドで、既定ではシリアライズされない。
- 対策: 専用 JsonConverter。往復テストは 1 プロパティずつ動かす。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: Notion 3c6e4d4b-751b-8116-9329-f3e99b981dc5

### MemoryMappedFile.CreateFromFile(leaveOpen:false) と using の併用で二重 close
- 症状: Windows では出ない。POSIX で無関係な fd を閉じうる。
- 原因: leaveOpen:false は所有権の移譲。
- 対策: using を外し、例外経路だけ Dispose する。
- 実例: 2026-08-24 MotionForge
- 自動検出: 候補（multiline）`using\s+(var\s+)?\w+\s*=\s*new\s+FileStream[\s\S]{0,300}CreateFromFile\([^)]*leaveOpen:\s*false`（warn）
- 出典: Notion 3c6e4d4b-751b-813d-86ff-c03e10b1d13b

### 割り当て計測: GC.GetTotalAllocatedBytes は全スレッド合計 / IReadOnlyList<T> の foreach は列挙子をボックス化
- 症状: 割り当てテストが 5448B で失敗（テストホストの裏方を拾う）。48B/回の割り当て。
- 対策: .NET 本体では `GC.GetAllocatedBytesForCurrentThread` を使う（Unity の Mono では 0 を返すので不可）。ホットパスは配列 + for。計測するテストは非並列コレクションに入れる。
- 実例: 2026-08-24, 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:57, 1246

### 遅延評価のための Func<T> は毎回クロージャを確保する
- 症状: 健全な状態でこそ毎フレーム割り当てが出る。
- 原因: キャプチャしたラムダ。
- 対策: 分岐内で文字列を作り `string?` を渡す。計測は表示状態を固定して比較する。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: Notion 3c6e4d4b-751b-81c4-b52d-e228245d2b3d

### キャッシュキーが新規オブジェクトの既定値と衝突する（Version=0）
- 症状: 閉じた前のドキュメントを描き続ける。
- 原因: 値だけのキー。
- 対策: 所有者参照（ReferenceEquals）をキーにする。テストは同じ長さの別データで。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: Notion 3c6e4d4b-751b-8128-9d81-fc44a9d33467

### 未初期化の四元数どうしの角度は 180°
- 症状: 全ボーン 179.94°。
- 原因: `default(Quaternion)` は (0,0,0,0)。
- 対策: Identity で初期化するか、有効ビットを別に持つ。
- 実例: 2026-08-24 MotionForge
- 自動検出: 候補 `new\s+Quaternion\[|default\(Quaternion\)`（warn。Unity でも同じ）
- 出典: Notion 3c6e4d4b-751b-8145-9f78-e95f91bf9c57

### x64 の INPUT 構造体は union のオフセットが 8
- 症状: SendInput が効かない。
- 原因: x64 ではアラインメントで union が offset 8。
- 対策: `[FieldOffset(8)]`。
- 実例: 2026-04 MocapSimulator
- 自動検出: 候補 `struct INPUT` 内の `FieldOffset(4)`（warn）
- 出典: MocapSimulator:87

### 三重バッファを複数の読み手が AcquireLatest すると別の瞬間を映す
- 症状: 4 ビューで同じ人が別フレーム。
- 原因: 読み手 1 つ前提の設計。
- 対策: フレーム頭に 1 回取って配る。
- 実例: 2026-09-20 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1716

### 未保存判定の指紋に UI が初フレームで書く値が含まれる
- 症状: 起動しただけでタイトルに「•」、終了時に毎回「未保存」。
- 対策: 表示用の状態を指紋から外す。
- 実例: 2026-09-20 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1718

### 自動退避を同じ名前に書き続けると、復旧案内の直後の操作で消える
- 症状: 「ここに保存してあります」と案内した復旧コピーが最初の編集で上書き。
- 対策: 起動時に前回分を日時付きの名前へ退避してから書き始める。
- 実例: 2026-09-20 MotionForge
- 自動検出: 不可
- 出典: MotionForge/README.md:1583

### 3D ピッキングを「投影中心からの px 距離」で判定するとズーム時に選べない
- 症状: 部屋の内側（ズームイン）で何をクリックしても反応しない。
- 原因: 対象の画面上サイズが大きくなると投影中心がクリック点から 30px 以上離れる。
- 対策: 3D レイ × AABB（最近傍）で判定し、遠景の小アイコン用にだけスクリーン距離を併用する。
- 実例: 2026-06 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:693-701

## ImGui（Hexa.NET.ImGui / Silk.NET）

### ImGui の Text / SetTooltip は文字列を printf 書式として扱う
- 症状: 「100% such」が化ける。`%n` でプロセスが落ちる（ファイル名の %20 で起こりうる）。
- 原因: 渡した文字列が fmt として解釈される（Text / TextColored / TextWrapped / BulletText / SetTooltip / LabelText）。
- 対策: TextUnformatted ベースのラッパに統一し、直接呼び出しを走査して禁止するテストを置く。
- 実例: 2026-09-17 MotionForge
- 自動検出: 候補（patterns-app.md の `imgui-printf-format`）
- 出典: Notion 3dee4d4b-751b-819c-8b1a-fa1f6cef5db8, MotionForge/log/claudeLog.txt:1482

### ImGui 内蔵 + BIZ UDGothic のアトラスで U+2014 / U+2015 が描かれない
- 症状: em ダッシュが空白になる。
- 対策: 描画時にハイフンへ置換する（または glyph range に含める）。
- 実例: 2026-09-20 MotionForge
- 自動検出: 不可
- 出典: MotionForge/README.md:1570

### Silk.NET の Dispose が別例外を投げて元の例外を隠す
- 症状: 描画ループ外の例外がログに残らない。
- 対策: AppHost.Run で先に記録してから Dispose する。
- 実例: 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1232

### Hexa.NET.ImGui: ImGuiDockNodeFlags.DockSpace が公開 enum に無い
- 症状: コンパイルできない。
- 対策: ImGuiDockNodeFlagsPrivate をキャストする。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:40

## OpenGL / ANGLE

### 同一深度の 2 パス描画は GL_LESS で後者が消える
- 症状: 補正後スケルトンが描かれない。オニオンスキンで本体が虫食い。
- 対策: DepthFunc を LEqual にするか、深度を書かない独立パスにする。
- 実例: 2026-08-24 MotionForge / 2026-09-20 MotionForge（2 回）
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:44, 1716

### GLSL #version 300 es は macOS の Desktop GL 4.1 Core で拒否される（固定 330 core にすると ANGLE が壊れる）
- 症状: Mac でシェーダーコンパイル失敗「version '300' is not supported」→ 全レンダラ null で真っ黒。
- 原因: Windows の NVIDIA ドライバは GLES シェーダーを Desktop GL でも通すので表面化しない。Apple GL 4.1 は GLSL 410 まで。Windows 側は ANGLE（D3D11）で GLSL ES が要る。
- 対策: `#version` を実行時にコンテキスト種別（GL_SHADING_LANGUAGE_VERSION に "ES"）で出し分ける。ES 側は `precision highp float;`、整数頂点属性は float 属性 + `int()` 変換。
- 実例: 2026-04 MocapSimulator / 2026-06-13 MocapSimulator
- 自動検出: 不可（300 es は ANGLE 経路では正しい）
- 出典: MocapSimulator:841-858, MocapSimulator/memory/project_architecture.md:22-28, project_bvh_motion.md:20

### ANGLE（D3D11）では glLineWidth が効かない / GlConsts に GL_LINES 等が無い
- 症状: 線幅が常に 1px。定数が見つからない。
- 原因: ANGLE / D3D11 は太線非対応。
- 対策: ネイティブ WGL の GL 4.x を使うか線をポリゴンで描く。独自の GL 定数クラスを持つ。
- 実例: 2026-04 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:84, MocapSimulator/memory/project_architecture.md:22-28

## Avalonia / WPF

### Avalonia: コントロールをサブクラス化するとテンプレートが当たらず不可視
- 症状: TreeView 派生が何も描画されず、イベントも届かない。
- 原因: 既定テンプレートは `Selector="TreeView"` で型一致し、派生型には適用されない。
- 対策: `protected override Type StyleKeyOverride => typeof(TreeView);`
- 実例: 2026-04 MocapSimulator
- 自動検出: 候補（patterns-app.md の `avalonia-subclass-stylekey`）
- 出典: MocapSimulator:359-364, 384

### Avalonia: TreeViewItem が PointerPressed を Handled にしてバブルが止まる
- 症状: 派生 TreeView の OnPointerPressed が呼ばれない。
- 原因: 選択可能なコントロールの class handler が `e.Handled = true` にする。
- 対策: `AddHandler(PointerPressedEvent, h, RoutingStrategies.Tunnel, handledEventsToo: true)`。
- 実例: 2026-04 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:366-369, 385

### Avalonia 12 の macOS は Metal 合成で OpenGlControlBase に GL が来ない
- 症状: Mac でビルド・起動は成功するが Viewport が真っ黒・FPS=0、OnOpenGlInit が呼ばれない。
- 原因: AvaloniaNative の既定レンダリングが Metal。
- 対策: `AvaloniaNativePlatformOptions { RenderingMode = [OpenGl, Software] }`。
- 実例: 2026-06-13 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:824-836

### Dock.Avalonia 12 の設定（namespace・テーマ別パッケージ・ActiveDockable）
- 症状: IRootDock が見つからない / DockControl が描画されない / ToolDock のパネルが出ない。`[ObservableProperty]` が Dock.Model 型に使えない。
- 原因: namespace が Dock.Model.Controls へ移動、テンプレートは Dock.Avalonia.Themes.Fluent 別パッケージ、ToolDock は ActiveDockable と GripMode が必須。
- 対策: 3 点をセットで設定する（`DockFluentTheme` を Application.Styles に追加、DockControl に Factory をバインド）。Dock.Model 型は手動でプロパティを実装する。
- 実例: 2026-04 MocapSimulator / 2026-06-12 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:25-33, MocapSimulator/memory/project_architecture.md:22-28

### Avalonia 12 で DataObject 非推奨 / RelayCommand の CanExecute が更新されない
- 症状: DnD が実装できない / ボタンがグレーアウトのまま。
- 対策: ポインターベースの DnD。状態変化時に `NotifyCanExecuteChanged()`。
- 実例: 2026-04 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:249-250

### 絵文字アイコンは Foreground で色が変わらない
- 症状: ON / OFF の状態色が付かない。
- 原因: カラー絵文字はフォント側の色。
- 対策: モノクロのアイコンライブラリ（Material.Icons.Avalonia 等）を使う。
- 実例: 2026-06-13 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:691, 716-722

### HelixToolkit.Wpf 3.x で WPF 版 MeshBuilder が廃止
- 症状: MeshBuilder の結果を WPF の GeometryModel3D に渡せない。
- 原因: 3.x で MeshBuilder が `HelixToolkit.Geometry`（System.Numerics 版）へ移った。
- 対策: SphereVisual3D / PipeVisual3D の永続プールを毎フレーム座標更新する（低分割なら 90Hz 維持）。
- 実例: 2026-06-10 Handive
- 自動検出: 不可
- 出典: Handive:103-107, Handive/memory/architecture-app1-tracking.md:41
