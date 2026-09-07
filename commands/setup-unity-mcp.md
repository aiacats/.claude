---
description: 現在のUnityプロジェクトに com.aiacats.unity-mcp をセットアップし、Claude Codeから接続できる状態にする
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, AskUserQuestion, mcp__win-gui__find_window, mcp__win-gui__focus_window, mcp__win-gui__key_press, mcp__win-gui__list_windows
---

# setup-unity-mcp

現在の作業ディレクトリにある Unity プロジェクトに `com.aiacats.unity-mcp` をセットアップし、Claude Code から MCP 経由で操作可能な状態にする。冪等。

## 前提チェック（中断条件）

1. CWD が Unity プロジェクトであること（`ProjectSettings/ProjectVersion.txt` と `Packages/manifest.json` の両方が存在）
2. `node` / `npm` が利用可能（`node --version && npm --version`）

どちらか欠けていれば理由と対処を伝えて中断。

## Step 0: 配置方式とスコープの確認（必ず最初に質問）

`AskUserQuestion` で 2 問まとめて尋ね、回答を `$LAYOUT` / `$SCOPE` として後段で参照する。

**Q1. 配置方式**

| 選択肢 | 置き場所 | manifest.json | packages-lock.json |
|---|---|---|---|
| `assets`（既定・推奨） | `Assets/Plugins/ClaudeCodeMCP/` | 汚れない | 汚れない |
| `packages` | `Packages/com.aiacats.unity-mcp/` | 汚れない※ | **汚れる** |

※ Unity は `Packages/` 直下に `package.json` を持つフォルダを **manifest 記載なしでも embedded package として認識する**。
ただし `packages-lock.json` には `source: "embedded"` のエントリを **Unity が自動生成する**ため、
`Packages/` 配下に置く限りこちらは避けられない（実測済み）。

`assets` を選べる条件は **パッケージが v1.4.0 以降**であること（`MCPPackageLocator` によるパス解決が入ったバージョン）。
それ未満は `"Packages/com.aiacats.unity-mcp"` がコードへ直書きされており、Assets 配下では npm 自動インストールと
サーバー起動が黙って失敗する。古い場合は先にパッケージを更新するか `packages` を選ぶ。

**Q2. スコープ**

- `team-shared` → `.mcp.json` も配置したパッケージもコミット対象
- `personal` → git へ出さない（Step 6 参照）

## Step 1: パッケージの取得と配置

配置先は `$LAYOUT` で決まる。以下 `$DEST` と呼ぶ。

- `assets` → `Assets/Plugins/ClaudeCodeMCP`
- `packages` → `Packages/com.aiacats.unity-mcp`

`$DEST` が既に存在すればスキップ。無ければ次の順で取得する。

1. **ローカルソースがあれば直接コピー（最短）**
   `D:\_Personal\Project\unity-mcp\Packages\com.aiacats.unity-mcp` が存在すればそれを `$DEST` へコピーする。
   Git URL 登録 → Unity 起動待ち → PackageCache から再 embed、という往復が不要になる。
   コピー前に `package.json` の `version` を確認し、`assets` を選んでいて 1.4.0 未満なら先にソース側を更新する。
2. **無ければ PackageCache 経由**
   `Packages/manifest.json` の `dependencies` へ一時的に
   `"com.aiacats.unity-mcp": "https://github.com/aiacats/unity-mcp.git?path=Packages/com.aiacats.unity-mcp"` を追加し、
   Unity Editor を起動 or フォーカスして `Library/PackageCache/com.aiacats.unity-mcp@*/` へ展開させる。
   展開後に `$DEST` へコピーし、`$LAYOUT` が `assets` なら **manifest から当該行を削除して元に戻す**
   （`git checkout -- Packages/manifest.json` で改行コードごと戻すのが確実）。

## Step 2: manifest.json の扱い

- `$LAYOUT` = `assets` → **何も書かない**。Step 1-2 で一時追加した場合は必ず元へ戻す。
- `$LAYOUT` = `packages` → `"com.aiacats.unity-mcp": "file:com.aiacats.unity-mcp"` を書いてよい。
  書かなくても Unity は認識するが、Package Manager の UI 上の扱いを明示したい場合は書く。
  どちらにせよ `packages-lock.json` は汚れる。

いずれの場合も、編集後に `node -e "JSON.parse(...)"` で JSON の妥当性を確認する。

**注意**: `sed -i` で JSON を編集すると、CRLF のファイルが LF へ書き換わって `git status` に差分として出ることがある
（内容差分は無いのに `M` が付く）。内容を戻すだけなら `git checkout -- <file>` を使う。

## Step 3: npm install

パッケージ v1.0.1 以降は Editor 起動時に `MCPAutoBootstrap` が自動で `npm install` を実行するため通常は不要。
Unity を触る前に済ませたい場合は `$DEST/Server~/node_modules/@modelcontextprotocol/sdk` の存在を確認し、
無ければ `cd $DEST/Server~ && npm install --no-audit --no-fund` を実行（あればスキップ）。

## Step 4: .mcp.json

プロジェクトルートに無ければ次の内容で作成。args のパスは `$DEST` に合わせる。

```json
{
    "mcpServers": {
        "claude-code-mcp-unity": {
            "command": "node",
            "args": ["Assets/Plugins/ClaudeCodeMCP/Server~/index.js"]
        }
    }
}
```

**`MCP_UNITY_HTTP_URL` は書かない**（v1.5.0 以降）。書くと自動検出より優先され、
複数の Unity を同時に開いたときに別プロジェクトの Unity を掴む。
ブリッジは `index.js` の位置から Unity プロジェクトルートを辿り、
`Library/ClaudeCodeMCP/endpoint.json` から実際のポートを解決する。

既に存在する場合は中身を読み、`claude-code-mcp-unity` キーが無ければ **マージで追加**（他サーバーの定義を消さない）。
あればスキップ。既存内容の上書きは事前にユーザー確認。

**`index.js` は自分が置かれている Unity プロジェクトに紐づく**（v1.5.0 以降）。
自分の位置から上方向に `ProjectSettings/ProjectVersion.txt` を探してプロジェクトルートを決め、
そのプロジェクトの `endpoint.json` を読む。したがって **`claude mcp add --scope user` で
1 つの絶対パスをユーザースコープへ登録し、全プロジェクトで使い回すことはできない**
（登録した index.js が属するプロジェクトに固定されるため）。
プロジェクトごとに `.mcp.json` を置く。

なお `.mcp.json` が既に git 追跡されているプロジェクトでは、この追記がコミット差分として出る。
避けたい場合は Step 6 の「追跡済み」の項を参照。

## Step 5: `enabledMcpjsonServers` への登録

`$SCOPE` に応じて対象ファイルへ `enabledMcpjsonServers` を追記する（重複追加しない。他キーは保持してマージ）。

- `team-shared` → `.claude/settings.json`
- `personal` → `.claude/settings.local.json`

`enableAllProjectMcpServers: true` が既にあれば実質不要だが、明示登録しておくと意図が読み取れる。

## Step 6: git へ出さない設定（`$SCOPE` = personal の場合）

**先に `git ls-files --error-unmatch <path>` で追跡済みかを確認する。**

- **未追跡** → `.git/info/exclude` へ書く。`.gitignore` はそれ自体がコミット対象なので、
  そこへ書くと「汚したくない」という目的と矛盾する。`.git/info/exclude` はローカル限定で git に出ない。
  ```
  # Unity MCP bridge (Claude Code 用・個人環境限定)
  /Assets/Plugins/ClaudeCodeMCP/
  /Assets/Plugins/ClaudeCodeMCP.meta
  ```
  **Assets 配下へ置いた場合、フォルダ用の `.meta` を必ず併記する。** Unity が生成する
  `ClaudeCodeMCP.meta` はフォルダの「外」に置かれるため、`/…/ClaudeCodeMCP/` だけでは
  マッチせず未追跡ファイルとして残る（実測で踏んだ）。書いたあとは
  `git status --short | grep -i claudecodemcp` が空になることを確認する。
- **追跡済み**（`.mcp.json` や `.claude/settings.local.json` が既にコミットされている等）
  → ignore は**効かない**。`git rm --cached` が必要だが、それは他の人の設定も外すことになるため
  **勝手に実行せず、事実と選択肢を報告する**。

`$LAYOUT` = `packages` の場合、`Server~/node_modules` が ignore されるかを
`git check-ignore -v <path>` で**実際に確認する**。Unity 標準の `*~` パターンを持たない `.gitignore` の
プロジェクトでは ignore されない（実測あり）。効いていなければ明示的に追加する。

## Step 7: Unity Editor への反映

`mcp__win-gui__find_window` で CWD basename を含むウィンドウを探す。

- **見つかった**: `focus_window` → `key_press` で `Ctrl+R`
- **見つからない**: `ProjectSettings/ProjectVersion.txt` のバージョンを伝え、Unity Hub から開くよう依頼。
  起動完了の signal は Step 8 の polling が兼ねる

## Step 8: HTTP サーバー起動確認

`curl -sS -m 3 http://localhost:8090/mcp/tools/get_compilation_errors -X POST -H "Content-Type: application/json" -d '{}' -o /dev/null -w "HTTP_CODE=%{http_code}\n"`
を最大 6 回・各 15 秒待機で polling し 200 を待つ。タイムアウトしたら警告し、Unity Console の確認を案内。

**`/`（ルート）は `unknown_endpoint` を返すが HTTP 200 なので疎通確認には使える。**

`$LAYOUT` = `assets` の場合、ここで併せて確認する（これが Assets 配下で動いている証拠になる）。

- `grep -c aiacats Packages/manifest.json Packages/packages-lock.json` が **両方 0**
- コンソールに `パッケージルートを解決できませんでした` の警告が**出ていない**
- `Library/ScriptAssemblies/ClaudeCodeMCPEditor.dll` の更新時刻がソースより新しい
  （ドメインリロード直後の「エラー 0 件」は信用しない。トラッカーがリセットされるため）

## Step 9: 完了報告

```
| Step | 状態 |
|---|---|
| 配置方式 / スコープ | assets or packages / team-shared or personal |
| パッケージ配置 | ✅ ローカルソース直接 / ✅ PackageCache 経由 / (skip) |
| manifest.json | ✅ 無変更 / ✅ file: 参照追加 |
| packages-lock.json | ✅ 無変更 / ⚠️ embedded エントリが入る |
| npm install | ✅ auto / ✅ manual / (skip) |
| .mcp.json | ✅ 新規 / ✅ マージ追加 / (skip) |
| enabledMcpjsonServers | ✅ / (skip) |
| git ignore | ✅ .git/info/exclude / ⚠️ 追跡済みのため未対応 / N/A |
| Unity 反映 | ✅ Ctrl+R / 手動依頼 |
| HTTP サーバー応答 | ✅ HTTP 200 / ❌ 未応答 |
```

最後に: **「Claude Code を `/exit` → 再起動してください。`enabledMcpjsonServers` を登録済みなので承認ダイアログは出ません。再起動後 `/mcp` で `claude-code-mcp-unity: connected` を確認してください」**

アンインストールは `/uninstall-unity-mcp` で対称的に行えることも案内する。

## セットアップ直後の検証テクニック

**MCP ツール（`mcp__claude-code-mcp-unity__*`）は Claude Code を再起動するまで呼べないが、
HTTP API は curl で直接叩ける。** セットアップ当日の検証はこれで完結する。

```bash
BASE=http://localhost:8090/mcp/tools
curl -sS -X POST $BASE/force_compilation        -H "Content-Type: application/json" -d '{}'
curl -sS -X POST $BASE/wait_for_compilation_done -H "Content-Type: application/json" -d '{}'
curl -sS -X POST $BASE/get_compilation_errors   -H "Content-Type: application/json" -d '{}'
curl -sS -X POST $BASE/get_console_logs         -H "Content-Type: application/json" -d '{"count":60}'
```

- エンドポイント一覧は `$DEST/Editor/Core/MCPHttpServer.cs` の文字列リテラルを grep すれば分かる。
- `force_compilation` はドメインリロードで接続が切れ、**応答が空で返ることがある**。異常ではない。
  完了は `wait_for_compilation_done` の再試行か、`Library/ScriptAssemblies/*.dll` の更新時刻で判定する。
- `get_console_logs` の `data` は配列風オブジェクト（キーが `0,1,2...`）。`Object.values()` で取り出す。

## 複数の Unity プロジェクトを同時に開く場合

**v1.5.0 以降は追加設定なしで共存できる。** 以下がその仕組みなので、動かないときはここを見る。

- Unity は 8090 が埋まっていれば **8091.. へ自動で逃げる**（`MCPHttpServer.TryStartAlternativePort`）
- Unity は実際にバインドしたポートと素性を **`Library/ClaudeCodeMCP/endpoint.json`** へ書き出す
  （`Library/` は Unity 管理下かつ git 管理外なので、成果物を汚さない。サーバー停止時に削除される）
- Node ブリッジは呼び出しのたびに、`index.js` の位置 → Unity プロジェクトルート → `endpoint.json`
  の順に辿ってポートを解決し、**毎回 `/mcp/identity` で接続先のプロジェクトパスを照合する**

v1.5.0 より前は Node ブリッジが 8090 固定だったため、**2 つ目以降の Claude Code が
1 つ目の Unity を操作してしまい、しかも応答が正常に返るので気づけなかった**
（`force_compilation` で別プロジェクトがコンパイルされる、`save_scene` で別プロジェクトの
シーンが保存される、といった形で出る）。パッケージが古いプロジェクトは更新する。

切り分け:

```bash
cat Library/ClaudeCodeMCP/endpoint.json          # このプロジェクトの Unity が使っているポート
curl -sS http://localhost:8090/mcp/identity      # そのポートの相手がどのプロジェクトか
netstat -ano -p UDP | grep 809                   # 8090-8099 の使用状況（Windows）
```

「別プロジェクトのため操作を中止しました」というエラーが出た場合は、
目的のプロジェクトの Unity Editor が起動しているかを確認する（エラーは正しく働いた印であって、不具合ではない）。

## 注意事項

- Submodule への書き込みは絶対にしない
- 既存ファイルの上書きは事前にユーザーに確認する
- Unity Editor の自動起動は Hub のパスや version 整合性が環境依存なので避ける
- パッケージ本体に手を入れたくなったら、使用中プロジェクトの配置物ではなく
  **`D:\_Personal\Project\unity-mcp` のソースを更新**して取り込み直す（グローバル CLAUDE.md の恒久ルール）
