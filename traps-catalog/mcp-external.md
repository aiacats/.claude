# mcp-external の罠（カタログ）
外部アプリへ繋ぐ MCP の使い方全般（接続先の取り違え・ポートの取り合い・モーダルで止まる・共有）と win-gui（クリック/キャプチャ/OCR/入力）の罠の全件。Unity MCP 固有のツールの罠は unity-mcp、AE/Resolve/Blender 固有は dcc のカタログ。厳選版は ~/.claude/rules/traps/mcp-external.md。

## 接続先・ポート

### 外部アプリ MCP が正常応答のまま別プロジェクトのアプリに繋がっている
- 症状: 無関係なプロジェクトで Refresh・再コンパイル・Play が走る。読み取り系（get_compilation_errors 等）も別プロジェクトの結果を返し、検証結果を誤読する。
- 原因: MCP は固定ポートへ繋ぐだけで、接続先を名乗らない（旧版）。目的のアプリが閉じている、または先に起動した別プロジェクトがポートを保持していると、そちらに繋がる。vortex_urp では (1) embed パッケージの package.json 欠落で MCP サーバー自体が立っておらず (2) 古い Server~/index.js が照合機能を持たず `.mcp.json` の `MCP_UNITY_HTTP_URL=http://localhost:8090` 固定のまま別プロジェクトへ繋いだ、が重なっていた。
- 対策: 状態を変える操作の前に接続先を確かめる（ウィンドウタイトル。Unity は `<プロジェクト> - <シーン> - ... - Unity <ver>`）。Unity MCP は v1.5.0 以降へ更新（`Library/ClaudeCodeMCP/endpoint.json` + `/mcp/identity` の projectPath 照合）し、`.mcp.json` から `MCP_UNITY_HTTP_URL` の固定を外す。目的のアプリが起動していなければ勝手に起動しない。長時間の作業では節目ごとに確認し直す。
- 旧説: 「`.mcp.json` の `MCP_UNITY_HTTP_URL` を見て netstat でポートの持ち主を特定する」「接続先を返すツールを MCP 本体へ足すのが望ましい」（CLAUDE.md:502-515）。v1.5.0 で endpoint.json + verifyIdentity として実装済みで、URL の固定はむしろ取り違えの原因。
- 実例: 2026-08-27 Unity_ArtNetRecorder（別プロジェクトを Play Mode に入れた）/ 2026-09-23 vortex_urp（ShinkaiFes2026 で Refresh と force_compilation）
- 自動検出: 候補 `mcp-unity-url-fixed`（patterns-claude.md）
- 出典: CLAUDE.md:488-521 / Notion 3c9e4d4b-751b-815c-aa39-e04c83225291, 3e4e4d4b-751b-812d-80bd-f544a6032ca1, 3e4e4d4b-751b-816b-b182-ee243e8cd2de

### `.mcp.json` に `MCP_UNITY_HTTP_URL` を書くと自動検出より優先されて別プロジェクトを掴む
- 症状: 応答は正常なのに別プロジェクトの Unity を操作している。
- 原因: 環境変数が endpoint.json による解決より優先される。
- 対策: unity-mcp v1.5.0 以降では書かない（endpoint.json + `/mcp/identity` 照合に任せる）。
- 実例: 2026-09-06 lll-12 / 2026-09-23 vortex_urp
- 自動検出: 候補 `mcp-unity-url-fixed`（patterns-claude.md）
- 出典: LLL-LOG:92-139 / Notion 3e4e4d4b-751b-816b-b182-ee243e8cd2de

### ドメインリロード・再起動でポートが移り、空いたポートを別プロジェクトが取る
- 症状: 固定ポートへの curl で force_compilation や invoke_method が別プロジェクト（ModelChecker）へ届いた。Recorder の後に Unity を起動し直すとポートが入れ替わる。
- 原因: 8092 → 8091 のようにポートが移り、空いたポートを別の Unity が取る。
- 対策: 毎回 endpoint.json からポートを読み、`/mcp/identity` で照合してから叩く（processId が今のアプリか見る）。
- 実例: 2026-06-15 Unity_ArtNetRecorder（8090 → 8091）/ 2026-09-24 Ext_TokinoSora_2026-pia / skill vortex-timeline-export（Recorder 後）
- 自動検出: 不可（curl 先のポートだけでは照合済みか判定できない）
- 出典: TS:40-42 / AC:68 / skills/vortex-timeline-export/SKILL.md:176

### 外部アプリ MCP のポートを固定すると多重起動で壊れる（設計）
- 症状: 固定ポートだと AE を 2 つ起動したときに衝突する。
- 原因: 1 ポート = 1 インスタンス。
- 対策: アプリ側ブリッジが `%APPDATA%\<App>\bridges\<pid>.json` を書き、MCP サーバーが動的に発見する（stdio サーバーを別プロセスにする）。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: D---Personal-Project-AEMCP/memory/aemcp-architecture.md:22-27

### 同じ GUI アプリを別の Claude セッションも MCP で触っている
- 症状: 自分の検証中に別セッションがシーンや FBX を書き換える。報告した FBX を別セッションが修正版で上書きしていた。
- 原因: GUI の Blender 1 つを複数の Claude セッションが BMCP で共有している。
- 対策: 検証やアセットライブラリ登録は別プロセス（`blender -b ... -P`）で行う。共有中のアプリで `read_homefile` / `open_mainfile` をしない（skill blender-stage に記載）。
- 実例: 2026-09-26 BMCP / band_studio
- 自動検出: 不可
- 出典: D---Personal-Project-BMCP/memory/project-status.md:20-21 / skills/blender-stage/SKILL.md:84-87

## モーダル・ダイアログで止まる

### MCP が全部タイムアウト・None を返すときはまずモーダルを疑う
- 症状: Unity: 軽いツールも timeout、HTTP は 200 を 1.7ms で返す。Inspector のプルダウンを開いたままでも全ツールがタイムアウト。build_player が isRunning のまま進まない。Resolve: ImportMedia・SetSetting などが例外なしで None。
- 原因: モーダル（OpenFolderPanel 等のファイル選択・「Scene(s) Have Been Modified」・起動時の更新案内）がアプリのメインスレッドを止める。
- 対策: 真っ先に全画面 `screenshot` でダイアログを探す（`capture_window` は対象窓しか写らず、別窓のモーダルや Hub の前面化が見えない）。find_window でモーダルの矩形を取って閉じる（ハング中で中身が黒くても × は効く）。Editor 拡張のパス入力は OpenFolderPanel ではなくテキスト欄を既定にする。書き込み系の戻り値は None と False を区別する。アプリ固有の詳細は unity-mcp / dcc のカタログ。
- 実例: 2026-06-01 LiveMultiRecorder（Inspector プルダウン・ビルド時モーダル）/ 2026-09-23 DvcMCP（Resolve 更新案内）/ 2026-09-24 SinkaiFes2026（OpenFolderPanel）
- 自動検出: 不可（コード側の OpenFolderPanel 検出は unity-mcp 担当の案）
- 出典: Notion 3e5e4d4b-751b-811a-a873-f5e232f2494c, 3e4e4d4b-751b-81ef-8e90-d2c359f3261b / LMR-MEM/settings-prompt-blocks-domain-reload.md:72-74 / LMR-LOG:253-256 / skills/vortex-timeline-setup/SKILL.md:202-203

## win-gui: 前面・フォーカス

### capture_window が正常に撮れてもクリックは前面の別アプリへ落ちる
- 症状: MotionForge を操作したつもりのクリックが前面の After Effects のツールバーに落ちた。打った文字列（"Actor Main"+Enter）が別アプリや Unity の Game ビューへ入った。Unity を押したつもりで Fork の Checkout Commit ダイアログが開いた。別プロジェクトの Unity 窓に当たった。
- 原因: 常駐の全画面オーバーレイや他セッションの作業ウィンドウが前面にいる。`focus_window` は foreground lock で前面化できないことがある。`capture_window` は PrintWindow なので隠れていても撮れ、見た目上は正常に見える。
- 対策: 操作前に全画面 `screenshot` で本当に前面か確かめる。pin + focus（skill windows-gui-testing）。前面にできなければ画面座標クリックをせず、PostMessage で対象 HWND に直接送る補助ツールを使う（GLFW / Silk.NET はメッセージ入力を受ける）。対象を他の窓と重ならない位置へ動かす。届かなければ描画確認までにとどめ「未検証」と報告する。
- 実例: 2026-06-13 MocapSimulator / 2026-09-02, 2026-09-13, 2026-09-23 Sequence / 2026-09-17 MotionForge / 2026-09-23 SinkaiFes2026 / 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（GUI 検証について）/ Seq/log/claudeLog.txt:1084-1086, 2673-2674, 2834-2836 / D---Personal-Project-MotionForge/memory/gui-verification-by-window-messages.md:10-13 / MotionForge/log/claudeLog.txt:1175 / SinkaiFes2026/log/claudeLog.txt:650-653 / ModelChecker/CLAUDE.md:57 / MS/.claude/claudeLog.txt:757-758

### 別の仮想デスクトップの窓は撮れない・操作できない（Win キーも送れない）
- 症状: 対象の窓が win-gui でキャプチャ・操作できない。仮想デスクトップのショートカットを key_press で送れない。
- 原因: win-gui は別デスクトップの窓を扱えない。`key_press` の修飾キーは Ctrl/Shift/Alt のみで Win キーを送れない。
- 対策: 作業前に対象のデスクトップへ切り替える（`~/.claude/tools/virtual-desktop.ps1` の `left` / `right` / `new`）。切り替えたら今どのデスクトップにいるかを報告に書く。起動済みの窓を後から別デスクトップへ移すのは標準機能では自動化できない。
- 実例: 2026-09-23（ユーザー指示と同時に記録）
- 自動検出: 不可（MCP ツールの引数は hook の対象外）
- 出典: CLAUDE.md:275-286

### 最前面固定のアプリがあると SetForegroundWindow / SetWindowPos がタイムアウトする
- 症状: Unity の独立ウィンドウを前面に出せない。PowerShell の Add-Type 呼び出しが 2 回ともタイムアウト。
- 原因: ftpDeck が最前面固定になっていた。
- 対策: 対象を重ならない位置へ移すか、相手を一時的に最小化する。
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可
- 出典: VL（2026-09-23 19:14 の節「Timeline Exporter 実機検証」）

### Unity が長時間ビジーだと focus が返らない
- 症状: フォーカスが 120 秒返らず GUI 確認ができない。
- 原因: AttachThreadInput の相手が固まっている。
- 対策: skill windows-gui-testing に記載（IsHungAppWindow で見て結び付けない）。
- 実例: 2026-09-06, 2026-09-23 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:427, 941 / Notion 3e4e4d4b-751b-81b1-8b9e-cd29bba33a49

### screenshot の後に Claude のターミナルが前面に戻る
- 症状: 続く操作が別ウィンドウに入る。
- 原因: キャプチャ処理でフォーカスが戻る。
- 対策: skill windows-gui-testing に記載（入力の直前に毎回 focus）。
- 実例: 2026-06 MocapSimulator
- 自動検出: 不可
- 出典: MocapSimulator:495

### dev 起動中の WebView2 アプリがマウス入力を受け付けなくなる
- 症状: スナップ操作の繰り返し後、クリックが効かない（キーは通る）。
- 原因: 不明（WebView2 側の可能性）。
- 対策: skill windows-gui-testing に記載（タスクバー等で注入が生きているか確かめてから起動し直す）。
- 実例: 2026-09-23 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:937

## win-gui: 窓の指定・座標

### find_window / capture_window のタイトル指定がターミナルを掴む
- 症状: `capture_window("MotionForge")` がプロジェクトフォルダで開いたターミナルを撮った。端末のタイトル `◐ ftpDeck` を掴んだ。
- 原因: find_window / focus_window はタイトルの部分一致。ターミナルのタイトルもプロジェクト名になる。
- 対策: skill windows-gui-testing に記載（プロセス名からハンドルを取る。`pid:<id>` で指す）。
- 実例: 2026-09-14 unity-mcp / 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: D---Personal-Project-MotionForge/memory/gui-verification-by-window-messages.md:21 / Notion 3dbe4d4b-751b-8114

### キャプチャ画像の座標をそのままクリックに渡すとずれる
- 症状: 座標クリックが外れる。
- 原因: `capture_window` / `screenshot` の画像は 1280px 等へ縮小され、ウィンドウ内座標である。マルチモニタではウィンドウ原点のオフセットも要る。
- 対策: skill windows-gui-testing に記載（倍率 = 実幅 / 画像幅、画面座標 = ウィンドウ左上 + 画像座標 × 倍率。region 指定なら等倍）。
- 実例: 2026-06-11 MocapSimulator / 2026-07 ExtOsc / Sequence
- 自動検出: 不可
- 出典: MocapSimulator:458 / EXTOSC-LOG:92-94 / Seq/CLAUDE.md（GUI 検証について 末尾）

### PostMessage 入力で座標を二重補正する／コモンダイアログのファイル名欄を取り違える
- 症状: (1) 入力欄にクリック・文字が入らない (2) ファイル名を入れたのにアドレスバーに入る／入れた文字が消える。
- 原因: (1) ツールがクライアント原点 (8,31) を引くのに自分でも引いて二重にずれた (2) 最初に見つかる Edit はアドレスバーのことがある。ダイアログ出現直後の入力は初期化で消される。
- 対策: 座標は capture_window 画像の座標をそのまま渡す（補正はツール側だけ）。ファイル名欄は部品 ID で探す（開く 1148 / 保存 1001、コンボなら中の Edit）。欄が出てから 1 秒待って入れる。
- 実例: 2026-09-17 MotionForge（2 回踏んだ）
- 自動検出: 不可
- 出典: D---Personal-Project-MotionForge/memory/gui-verification-by-window-messages.md:18, 29-31

### 「ウィンドウが無い」のか「非表示」なのかを区別しないと切り分けを誤る
- 症状: exe のウィンドウが出ない原因を設定・フォルダの総当たりで探し、全部濡れ衣だった。
- 原因: 窓は作られていたが非表示だった（Wails）。
- 対策: PowerShell + user32 の EnumWindows / IsWindowVisible / GetWindowText で可視状態を確認してから切り分ける。
- 実例: 2026-07 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:538-545

## win-gui: キャプチャ

### Chrome は capture_window で真っ黒／SSE を張るページは headless --screenshot が戻らない
- 症状: キャプチャが真っ黒。`chrome --headless --screenshot` が返らない。
- 原因: PrintWindow は Chrome の GPU 合成を拾えない。SSE を張るページは読み込み完了にならない。
- 対策: Web は playwright か、Chrome を `--remote-debugging-port` 付きで起動して CDP（Page.captureScreenshot / Runtime.evaluate）で撮る（SessionControl の `scripts/uiprobe.mjs`）。
- 実例: 2026-09-05 SessionControl / 2026-09 MemoryObserver
- 自動検出: 不可（headless --screenshot は SSE の無いページでは正常に動く）
- 出典: SessionControl/CLAUDE.md:255 / MemoryObserver/CLAUDE.md:80 / Notion 3d2e4d4b-751b-810e-9edf-ed3189fae9a3

### 重なった窓があるとタイトル指定のキャプチャが手前を拾う
- 症状: capture が手前のウィンドウを写し、focus_window でも前面に来ない。
- 原因: 共有モニタでの重なり。
- 対策: 対象を最大化して前面化する（座標も安定する）。
- 実例: 2026-06-13 MocapSimulator
- 自動検出: 不可
- 出典: MS/.claude/claudeLog.txt:757-758

### 4K ディスプレイでは SetProcessDPIAware が要る
- 症状: （レイアウト調査のチェックリストに記載。症状の記録なし）
- 原因: DPI 仮想化。
- 対策: 4K ディスプレイでは `SetProcessDPIAware` を呼ぶ。
- 実例: 記録なし
- 自動検出: 不可
- 出典: CLAUDE.md:189

## win-gui: 入力

### type_text で同じキーの連打をまとめて送ると取りこぼす
- 症状: `.` を 10 文字一度に送ると 9 回しか届かない。
- 原因: 合成入力側の取りこぼし（アプリの問題ではない）。
- 対策: 回数が意味を持つキー操作は 1 文字ずつ送る。長い文字列の type_text が落ちる件は skill windows-gui-testing に記載。
- 実例: 2026-08-30 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:454-455

### SendInput が wScan=0 だとナビゲーションキーがテンキー扱いになる
- 症状: Home/End/PageUp/PageDown が GLFW/SDL アプリに届かない（VK_HOME → テンキー 7）。
- 原因: スキャンコード未設定・KEYEVENTF_EXTENDEDKEY 無し。
- 対策: MapVirtualKey でスキャンコードを埋め、拡張キーに EXTENDEDKEY を付ける。WinGuiMcp のソースは修正済みだが publish が古いことがある（稼働中の exe を確認）。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:690

### key_press("Escape") が mpv に届かない
- 症状: Esc で閉じない（`q` は届く）。
- 原因: win-gui 側の送り方の制約（PowerShell の SendKeys なら届く）。
- 対策: 届かないキーは SendKeys で送る。アプリの実装の問題と誤認しない。
- 実例: 2026-08 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:904-907

### PostMessageA で日本語が化ける
- 症状: WM_CHAR で送った日本語が化ける。
- 原因: ANSI 版 API。
- 対策: PostMessageW を使う。
- 実例: 2026-09-17 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:1353, 1234

### XAML ItemTemplate 製の入れ子 ContextMenu は葉のクリックが効かない
- 症状: SendInput で入れ子メニューの末端をクリックしても実行されない（コードで組んだ MenuItem.Items は動く）。
- 原因: 不明（テンプレート生成メニューのヒットテスト）。
- 対策: GUI 自動テストではコードで構築したメニュー経路を使う、またはキーボード操作。
- 実例: 2026-06-11 MocapSimulator（セッション 10/11/12 で繰り返し）
- 自動検出: 不可
- 出典: MocapSimulator:456-457, 496

### win-gui の合成クリックは Unity エディタの Game ビューのランタイム UIDocument に届かない
- 症状: 歯車ボタン等を押しても隠れパネルが開かない。
- 原因: 合成クリックが Play 入力として処理されない。
- 対策: ビルドした exe 側で検証するか、表示を切り替える口を MCP 側に用意する。
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-MEM/settings-prompt-blocks-domain-reload.md:85-93

### click_text が本文中の同じ語を押す／日本語 OCR が効かない
- 症状: モーダルの「Save」ボタンを押したつもりが本文中の "save..." を押していた。日本語の click_text が効かない。
- 原因: OCR 一致の最初の出現を押す。OCR が日本語非対応。
- 対策: occurrence 指定でボタン行を狙う。日本語は座標クリック（skill windows-gui-testing に記載）。
- 実例: 2026-06-01 LiveMultiRecorder / rules/unity.md:247
- 自動検出: 不可
- 出典: LMR-LOG:253-256 / rules/unity.md:247

### 数値入力欄はトリプルクリックで全選択できない
- 対策: skill windows-gui-testing に記載（Ctrl+A を使う）。
- 出典: skills/windows-gui-testing/SKILL.md

### ダイアログは別ウィンドウ（押したのに進まない）
- 対策: skill windows-gui-testing に記載（窓が増えていないか見る）。
- 出典: skills/windows-gui-testing/SKILL.md

## 他の外部 MCP

### ComfyUI MCP の generate_with_ip_adapter は現行ノードに合わず 400
- 症状: 「Required input is missing: weight_type」で 400 Bad Request。
- 原因: MCP 内蔵ワークフローが古い（IPAdapter の必須入力が増えた）。
- 対策: API ワークフローを自前で組んで /prompt へ POST（必須: model, ipadapter, image, weight, start_at, end_at, weight_type）。
- 実例: 2026-07-04 Comfy
- 自動検出: 不可
- 出典: Comfy:73-80

### QLC+ Web API は実行時制御専用でオーサリングできない
- 症状: Fixture / Function / VC を API で作れない。
- 原因: webaccess.cpp にオーサリングコマンドが無い。
- 対策: .qxw(XML) を書き出して `-w -p -o` で読み込ませる。isProjectLoaded は -o でも "false"（保留ロード無しの意）なので疎通判定に使わない。
- 実例: 2026-06-03 QLCMCP
- 自動検出: 不可
- 出典: QLCMCP:68-72, 97-98
