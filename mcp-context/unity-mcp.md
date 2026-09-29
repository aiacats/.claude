# unity-mcp の罠
全件は ~/.claude/traps-catalog/unity-mcp.md。ここは再発しやすいものだけ。

### 別プロジェクトの Unity を操作している
正常に応答するので気付けない。無関係なプロジェクトで Refresh や Play が走る。原因は旧版の固定ポート、`.mcp.json` の `MCP_UNITY_HTTP_URL`（自動解決より優先）、ドメインリロードでポートが移り空きを別の Unity が取ること。→ embed を v1.5.0 以降にし `MCP_UNITY_HTTP_URL` を書かない。curl で叩くなら毎回 `Library/ClaudeCodeMCP/endpoint.json` のポートを読み `/mcp/identity` で照合。（実例: 2026-09-23 vortex_urp / 2026-09-24 Ext_TokinoSora_2026-pia / 2026-09-06 lll-12）

### 全ツールがタイムアウトしたらまずモーダルを疑う
curl は HTTP 200 を返すのに処理が返らない。原因は OpenFolderPanel・DisplayDialog・SettingsPrompt・未保存シーンの確認・開いた Popup がメインスレッドを塞ぐこと。→ 画面全体を screenshot（Unity 窓だけの capture_window では写らない）して閉じる。Editor 拡張のパス入力はテキスト欄を既定にする。（実例: 2026-06-01 LiveMultiRecorder / 2026-09-24 SinkaiFes2026 / 2026-09-24 lll-12）

### リロード直後の「エラー 0 件」とログを信用しない
get_compilation_errors が hasErrors:false、Play 前のログが get_console_logs から消える。ワーカースレッド発のログはそもそも拾わない。原因はフックが Play 開始 / ドメインリロードで作り直され、`logMessageReceived` だけを購読していること。→ `Library/ScriptAssemblies/*.dll` の時刻で再ビルドを確かめ、Editor.log も読む。fetch failed はリロード中なので数秒待つ。（実例: 2026-08-06, 08-24 2609SuiseiTour26 / 2026-08-27 Unity_ArtNetRecorder）

### force_compilation は追加・削除を拾わず、既定で全再インポートする
新規 .cs が dll に入らない。一時スクリプトを消した直後は CS2001 で MCP が古いコードのまま応答する。一方 `forceUpdate` の既定は true で、大規模プロジェクトは 10 分固まり無関係なアセットに差分が出る。→ 新規は `Assets/Refresh` か `ImportAsset`、削除後だけ forceUpdate=true、通常は `hot_reload(optimized:true)`。（実例: 2026-06-20 ReLink / 2026-09-22 SinkaiFes2026 / 2026-08-16 vortex_urp）

### update_component は成功と返っても書けていないことがある
参照を objectPath 文字列で渡すと null、nested struct は全フィールド 0。旧版は未知キーを黙って無視し、非アクティブを objectPath で指すと空の GameObject を作る。→ 参照は `{"instanceId"}` / `{"guid"}`（Play で instanceId は変わる）。書いたら get で読み返す。（実例: 2026-09-08 lll-12 / 2026-05-29 vortex_urp / 2026-09-02 2609SuiseiTour26）

### invoke_method のインスタンス target は解決に失敗する
instanceId でも objectPath でも target_not_found。→ 内部で FindFirstObjectByType する static メソッドを用意して target 無しで呼ぶ。（実例: 2026-06-21 ReLink / 2026-08-05, 08-12 2609SuiseiTour26）

### MCP で触った .mat やシーンは差分を確かめる
set_material_property を通すと .mat の `disabledShaderPasses` が落ちる。Play 中に作ったオブジェクトや足したコンポーネントはランタイムに効かない。→ 調査で触ったら git status と checkout。検証用の物は Edit モードで Play 前に作る。（実例: 2026-09-02, 09-01 2609SuiseiTour26）

### build_player の errors=0 は成功ではない
コンパイルエラーで即失敗しても result=Unknown, errors=0 を返す。→ result が Succeeded 以外は失敗。Editor.log の error CS を併読。（実例: 2026-09-13 SinkaiFes2026）

### embed を差し替えたら Server~ で npm ci
再起動後に CONNECTION_CLOSED（`ERR_MODULE_NOT_FOUND: @modelcontextprotocol/sdk`）。原因は node_modules が git 管理外でソースにも無いこと。→ `npm ci` して `node index.js` が待ち受けるのを確かめる。（実例: 2026-09-23 vortex_urp）
