# unity-mcp の罠（カタログ）
自作 Unity MCP（com.aiacats.unity-mcp、ソース D:\_Personal\Project\unity-mcp）のツールの挙動・罠。トラブル時に grep で引く。
「本体で直る」は unity-mcp のソースを直せば消えるもの。embed が古いプロジェクトでは修正済みの罠も再発する。

### 別プロジェクトの Unity を操作している（正常に応答するので気付けない）
- 症状: 無関係なプロジェクトで Refresh・再コンパイル・Play が走る。get_compilation_errors 等の読み取りも別プロジェクトの結果を返す。固定ポートへの curl で force_compilation / invoke_method が ModelChecker へ届いた
- 原因: (1) 固定ポート 8090 へ繋ぐだけで相手を名乗らない旧版 (2) embed の package.json 欠落でサーバーが立たず別の Unity が応答 (3) `.mcp.json` の `MCP_UNITY_HTTP_URL` が endpoint.json の自動解決より優先 (4) ドメインリロードや Recorder 後の再起動でポートが移り（8092→8091、8090→8091）、空いたポートを別の Unity が取る
- 対策: embed を v1.5.0 以降へ（`Library/ClaudeCodeMCP/endpoint.json` + `/mcp/identity` の projectPath 照合）。`.mcp.json` に `MCP_UNITY_HTTP_URL` を書かない。curl で直接叩くなら毎回 endpoint.json からポートを読み `/mcp/identity` で照合。書き込み前に list_windows のタイトルか endpoint.json の processId で確かめる
- 実例: 2026-08-27 Unity_ArtNetRecorder / 2026-09-06 lll-12 / 2026-09-23 vortex_urp / 2026-09-24 Ext_TokinoSora_2026-pia / 2026-06-15 Unity_ArtNetRecorder
- 自動検出: 候補（patterns-unity-core.md `mcp-json-unity-url`）
- 出典: Notion 3c9e4d4b-751b-815c-aa39-e04c83225291, 3e4e4d4b-751b-812d-80bd-f544a6032ca1, 3e4e4d4b-751b-816b-b182-ee243e8cd2de / LLL-LOG:92-139 / TS:40-42 / AC:68 / CLAUDE.md「MCP の接続先は操作前に必ず確認する」/ command setup-unity-mcp / skill vortex-timeline-export（Recorder 後のポート）

### モーダル・開いたポップアップで全ツールがタイムアウトする
- 症状: get_play_state のような軽いものまで timeout。netstat は LISTENING、curl は HTTP 200 を 1.7ms で返す（`/mcp/identity` だけ応答）。build_player が isRunning のまま
- 原因: OpenFolderPanel / OpenFilePanel / DisplayDialog / SettingsPrompt / 「Scene(s) Have Been Modified」/ Inspector の Popup がメインスレッドを塞ぎ、ProcessMainThreadQueue（EditorApplication.update）が進まない。HTTP は別スレッドなので 200 を返す
- 対策: 真っ先にモーダルを疑い、画面全体を screenshot（Unity 窓だけの capture_window では手前のダイアログが写らない）→ find_window で矩形を取り閉じる（ハング中で黒くても × は効く）。UI 自動操作の後は Popup を閉じる。自作ツールのパス入力はテキスト欄を既定にし、MCP からダイアログを叩かない
- 実例: 2026-06-01 LiveMultiRecorder / 2026-09-24 SinkaiFes2026 / 2026-09-24 lll-12
- 自動検出: 候補（patterns-unity-core.md `cs-editor-modal-panel`）
- 出典: Notion 3e5e4d4b-751b-811a-a873-f5e232f2494c / SinkaiFes2026 log/claudeLog.txt:702-704 / LLL-LOG:423-426 / LMR-MEM/settings-prompt-blocks-domain-reload.md:72-74 / skill vortex-timeline-setup にも記載

### ドメインリロード直後の「エラー 0 件」を信用しない／ログが消える
- 症状: domain reload 直後に get_compilation_errors が hasErrors:false（lastCompilationTime 空）。Play 開始や再起動の前のログ・コンパイルエラーが get_console_logs に出ない。Unity Console の件数と合わない
- 原因: MCP のログフック・トラッカーが Play 開始 / ドメインリロードで作り直される
- 対策: force_compilation を挟むか `Library/ScriptAssemblies/*.dll` の更新時刻で実際に再ビルドされたか確かめる。get_console_logs(logType:error) を併用。Editor.log（他 Unity と共有に注意）を読む
- 実例: 2026-08-06 / 2026-08-24 2609SuiseiTour26 / 2026-08-27 Unity_ArtNetRecorder
- 自動検出: 不可
- 出典: rules/unity.md「検証の追加ルール」/ Notion 3c9e4d4b-751b-815c-aa39-e04c83225291 / 2609SuiseiTour26 log/claudeLog.txt:1022-1024, 1453-1455

### get_console_logs がワーカースレッド発のログを拾わない（本体で直る）
- 症状: send_console_log で送ったログが get_console_logs に出ない。Editor.log には出ている
- 原因: MCPHttpServer が `Application.logMessageReceived`（メインスレッド発のみ）だけを購読。2026-09-29 時点のソース（MCPHttpServer.cs:141）も同じ
- 対策: `logMessageReceivedThreaded` を購読する。それまでは Editor.log を直接読む
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:23-36

### ドメインリロード中は fetch failed／サーバーが二重に立つ
- 症状: 一時的な fetch failed。wait_for_compilation_done も接続が切れて fetch failed。reload 起因の二重起動でエンドポイントが不安定
- 原因: ドメインリロードで HTTP サーバーが張り直される
- 対策: 数秒待って再試行（失敗と判定しない）。不安定が続くなら Unity 再起動。背面の Unity で立たない件は v1.5.1 で修正（traps-catalog/unity-editor.md）
- 実例: 2026-06-20 ReLink / 2026-08-27 Unity_ArtNetRecorder
- 自動検出: 不可
- 出典: MEM(ReLink)\unity-mcp-new-file-reimport.md / RL\.claude\claudeLog.txt:121-123 / Notion 3c9e4d4b-751b-815c-aa39-e04c83225291

### 追加・削除したファイルを force_compilation が拾わない
- 症状: 新規 .cs が ScriptAssemblies に入らず、そのテストだけ出ない（touch も無効）。一時スクリプトを消した直後に forceUpdate=false でコンパイルすると CS2001 で Editor アセンブリだけ失敗し、MCP が古いコードのまま応答する
- 原因: 新規・削除の AssetDatabase 再インポートが起きない（内容ハッシュ判定）
- 対策: 新規は `execute_menu_item "Assets/Refresh"` か `AssetDatabase.ImportAsset(<path>)`。削除後は forceUpdate=true。確認は dll の更新時刻と `strings <dll> | grep 型名`
- 実例: 2026-06-20 ReLink / 2026-09-22 / 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: MEM(ReLink)\unity-mcp-new-file-reimport.md:10-14 / RL\.claude\claudeLog.txt:39-42 / SinkaiFes2026 log/claudeLog.txt:477, 498

### force_compilation は既定で全アセットを再インポートする（本体で直る）
- 症状: 大規模プロジェクトで 10 分・222 秒固まる。.renderTexture や prefab に意図しない再シリアライズ差分
- 原因: `forceUpdate` の既定が true で `AssetDatabase.Refresh(ForceUpdate)`（CompilationHandler.cs:162、2026-09-29 確認）
- 対策: 通常は `hot_reload(optimized:true)` か `execute_menu_item "Assets/Refresh"`。forceUpdate は削除後など必要なときだけ。出た再シリアライズ差分は破棄
- 実例: 2026-07-11 / 2026-08-16 vortex_urp / 2026-09-14 Ext_Palletproject
- 自動検出: 不可（MCP 引数は hook の対象外）
- 出典: VL:27, 412-413 / M:D---ProjectBLUE-Project-Ext-Palletproject/unity-mcp-http-fallback.md

### update_component / update_gameobject は成功と返っても書けていないことがある（本体で直る）
- 症状: (1) 参照を objectPath 文字列で渡すと null が入る（applied は成功） (2) nested struct（ColorBlock 等）を渡すと全フィールドが 0 (3) 旧版は未知キー（isActive 等）や properties を黙って無視して success (4) 旧版は非アクティブを objectPath で指すと同名の空 GameObject を新規作成（"Created"）
- 原因: 参照解決・struct のシリアライズの不具合。(3)(4) は e159209（2026-09-02）で修正済み（未知キーはエラー、applied/failed を返す、createIfMissing=true のときだけ作成）
- 対策: 参照はシーン内なら `{"instanceId"}`、アセットなら `{"guid"}`。Play に入ると instanceId が変わるので割り当て直す。書いたら get で読み返す。nested struct は一時 Editor スクリプトか YAML。古い embed なら更新する
- 実例: 2026-05-29 vortex_urp / 2026-08-04（×2）/ 2026-09-02 2609SuiseiTour26 / 2026-09-08 lll-12
- 自動検出: 不可
- 出典: M:D---ProjectBLUE-Project--vortex-vortex-urp/unity_mcp_component_reference.md / 2609SuiseiTour26 log/claudeLog.txt:178-180, 386-390, 3382-3418 / LLL-LOG:238-242

### Camera を足しても UniversalAdditionalCameraData は付かない
- 症状: URP のカメラ設定が効かない
- 原因: MCP の add は URP の追加コンポーネントを自動付与しない
- 対策: UniversalAdditionalCameraData を明示的に追加
- 実例: 2026-05-29 vortex_urp
- 自動検出: 不可
- 出典: M:D---ProjectBLUE-Project--vortex-vortex-urp/unity_mcp_component_reference.md

### invoke_method でインスタンスメソッドの target 解決・配列引数の解決が失敗する（本体で直る）
- 症状: instanceId / {objectPath, componentName} どちらでも target_not_found。`IEnumerable<GameObject>` 引数に {objectPath} を渡すと解決に失敗し空 GameObject を作る
- 原因: 引数・target 解決の不備（479f918 2026-06-03 で declaring type による解決を入れた後も 06-21 / 08-05 / 08-12 に再発）
- 対策: 内部で FindFirstObjectByType する static メソッドを用意して target 無しで叩く。internal クラスなら同じ asmdef 配下に一時ラッパ（Selection を参照）を置く
- 実例: 2026-06-21 ReLink / 2026-08-05 / 2026-08-12 2609SuiseiTour26
- 自動検出: 不可
- 出典: RL\.claude\claudeLog.txt:253-255 / 2609SuiseiTour26 log/claudeLog.txt:492-498, 1357-1360

### invoke_method で EditorBuildSettings.set_scenes に {path, enabled} だけ渡すと空配列（本体で直る）
- 症状: ビルド対象シーンが空になる
- 原因: EditorBuildSettingsScene のシリアライズ名は m_path / m_enabled
- 対策: m_path / m_enabled も併記
- 実例: 2026-09-13 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:33

### set_object_properties はネストした VolumeParameter を設定できない（本体で直る）
- 症状: "Unable to find a constructor to use for type UnityEngine.Rendering.ColorParameter"
- 原因: VolumeParameter<T> のデシリアライズ未対応
- 対策: invoke_method か一時 Editor スクリプトで VolumeComponent のパラメータを直接操作
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:169-171

### UnityEvent の永続コールは MCP で編集できない（本体で直る）
- 症状: get_component_properties で "(Generic)"、update_component で編集不可
- 原因: MCP が UnityEvent を扱わない
- 対策: 一時 Editor スクリプトで `UnityEventTools.AddPersistentListener` → SetDirty / MarkSceneDirty。作業後にスクリプトを消す
- 実例: 2026-09-05 vortex_urp
- 自動検出: 不可
- 出典: Notion 3d2e4d4b-751b-810b-92de-ea5f3050156f

### set_material_property を通すと .mat の disabledShaderPasses が落ちる（本体で直る）
- 症状: 調査後に .mat から `- MOTIONVECTORS` が消える差分
- 原因: MCP 経由の書き換えがシリアライズ全体を書き直す
- 対策: 調査で使ったら git checkout で戻し、git status で確認
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:3329-3331

### build_player がコンパイルエラーで即失敗しても result=Unknown, errors=0（本体で直る）
- 症状: 失敗なのに errors=0 で成功と誤読しうる
- 原因: 結果判定の不備
- 対策: result が Succeeded 以外は失敗扱い。Editor.log の error CS を併読
- 実例: 2026-09-13 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:76

### restart_editor が失敗する
- 症状: restart_editor が失敗
- 原因: SetSceneRepaintDirty をメインスレッド外で呼んでいた。2026-09-29 時点のソースは EnqueueOnMainThread 経由で OpenProject を呼んでいる（古い embed で再発しうる）
- 対策: invoke_method で `EditorApplication.OpenProject` を呼ぶか embed を更新
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:195, 205

### Play 中に MCP で作ったオブジェクト・足したコンポーネントは検証に使えない
- 症状: Play 中に update_gameobject で作ったオブジェクトがランタイムに無い。足したコンポーネントは Update が回らない
- 原因: Edit 側のシーンに作られる／実行時追加の経路が通常と違う
- 対策: 検証用オブジェクトは Play 前に作る。コンポーネントは Edit モードで付ける
- 実例: 2026-08-06 / 2026-09-01 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26 log/claudeLog.txt:1025-1026, 2947-2951

### Game ビューが Display 2 だと UI が映らない／Ctrl+P はフォーカス依存
- 症状: Play しても UI が見えない。キー送信で Play に入れない
- 原因: Game ビューの Display 設定。Ctrl+P はウィンドウフォーカス依存
- 対策: `set_game_view_display(0)`、Play は `enter_play_mode`
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:183-185, 400-405

### win-gui の合成クリックは Editor の Game ビューのランタイム UIDocument に届かない
- 症状: 歯車ボタン等を押しても隠れパネルが開かない
- 原因: 合成クリックが Play 入力として処理されない
- 対策: ビルドした exe で検証するか、表示を切り替える口を MCP 側に用意する
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-MEM/settings-prompt-blocks-domain-reload.md:85-93

### run_tests がリロード中にハングする／queryOnly が 0 件を返す
- 症状: run_tests が返らない。queryOnly の結果が空
- 原因: 直前のドメインリロード中に問い合わせた。queryOnly の 0 件は原因不明（実測）
- 対策: wait_for_compilation_done の後に実行。結果は `-logFile` 専用ログの "Test run finished" で見る
- 実例: 2026-06-01 LiveMultiRecorder / 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: LMR-LOG:160-161 / MC\CLAUDE.md:17

### Unity MCP の screenshot は上下反転した画像を返す
- 症状: キャプチャが上下逆
- 原因: RenderTexture の読み戻しの向き。現行ソースに screenshot ツールは無い（v1.2.0 2026-06-01 で削除、2026-09-29 確認）ので古い embed で起きる
- 対策: win-gui の capture_window を使う
- 実例: 2026-08-20 vortex_urp
- 自動検出: 不可
- 出典: M:D---ProjectBLUE-Project--vortex-vortex-urp/feedback_screenshot_use_wingui.md

### embed を差し替えると Server~/node_modules が消え CONNECTION_CLOSED
- 症状: 再起動後に繋がらない。`ERR_MODULE_NOT_FOUND: @modelcontextprotocol/sdk`
- 原因: node_modules は git 管理外でソースリポジトリにも無い
- 対策: 差し替えたら `Server~` で `npm ci` し、`node index.js` が待ち受けるのを確かめる
- 実例: 2026-09-23 vortex_urp
- 自動検出: 不可（コピー手段が多様で正規表現の精度が出ない）
- 出典: VL:1557-1565

### unity-mcp を Packages と Assets/Plugins に二重配置するとアセンブリ名が衝突してコンパイルが止まる
- 症状: ある時刻以降コンパイルが一切通っていない
- 原因: manifest の com.aiacats.unity-mcp（サブモジュール内）と Assets/Plugins/ClaudeCodeMCP の同名 asmdef
- 対策: どちらか一方に。セットアップ時に既存の配置を確かめる
- 実例: 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt:440-443, 512-513

### upstream の .meta 欠落で git URL のパッケージがエディタ全体のコンパイルを止める
- 症状: CS0246 'BuildState' でエディタ全体がコンパイル不可
- 原因: BuildHandler.cs.meta / ExportPackageHandler.cs.meta のコミット忘れ
- 対策: unity-mcp リポジトリで新規 .cs の .meta がステージされているかコミット前に確かめる
- 実例: 2026-05-12 Submod_RealtimeLiveUtility / 2026-09-14 unity-mcp（e1cc1ef で追加）
- 自動検出: 不可（ステージ内容の照合が要る）
- 出典: SL:43-45, PL:104

### embed した unity-mcp が packages-lock.json 経由でリポジトリへ漏れる
- command setup-unity-mcp に記載（clean フィルタ `~/.claude/tools/strip-unity-mcp-lock.py`）。実例 2026-08-04 / 2026-08-25 2609SuiseiTour26。出典 Notion 3c7e4d4b-751b-8112-bd8f-fe61e64a5e2f

### UPM パッケージの .gitignore の `*~` が Server~ / Samples~ を除外する
- 症状: パッケージのサーバー/サンプルがリポジトリに入らない
- 原因: エディタのバックアップ用 `*~` が末尾 ~ のフォルダにも一致
- 対策: `!Server~/` `!Samples~/` の例外
- 実例: 2026-03-12 unity-mcp
- 自動検出: 不可
- 出典: UM\.claude\claudeLog.txt:37-38

### open_scene で今開いているシーンを開き直しても、未保存の変更が捨てられない
- 症状: 検証で変えたシーンを `open_scene`（同じパス）で開き直したのに、足したキャラが残ったまま次の検証が走り、数え方が狂った（成功が返る）。
- 原因: 今開いているシーンと同じパスを開くと、読み直しをしない（実測）。
- 対策: 変更を捨てたいときは、別のシーンを開いてから開き直す。検証用の写しなら、DeleteAsset → CopyAsset で作り直す。開き直した後は、足した物が消えたかを 1 つ確かめる。
- 実例: 2026-10-19 SinkaiFes2026（_ClaudeVerify_Grand で SetupCharacterEx を 2 回）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-19
