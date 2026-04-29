---
description: 現在のUnityプロジェクトに com.aiacats.unity-mcp をセットアップし、Claude Codeから接続できる状態にする
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, mcp__win-gui__find_window, mcp__win-gui__focus_window, mcp__win-gui__key_press, mcp__win-gui__list_windows
---

# setup-unity-mcp

現在の作業ディレクトリにある Unity プロジェクトに `com.aiacats.unity-mcp` をセットアップし、Claude Code から MCP 経由で操作可能な状態にする。冪等。

## 前提チェック（中断条件）

1. CWD が Unity プロジェクトであること（`ProjectSettings/ProjectVersion.txt` と `Packages/manifest.json` の両方が存在）
2. `node` / `npm` が利用可能（`node --version && npm --version`）

どちらか欠けていれば理由と対処を伝えて中断。

## Step 0: スコープの確認（必ず最初に質問）

ユーザーに「**この MCP セットアップを `team-shared`（チーム全員にコミット） / `personal`（個人設定として gitignore） のどちらにしますか？**」と尋ねる。回答を `$SCOPE` として後段で参照する。

- `team-shared` → `.mcp.json` も embed パッケージもコミット対象
- `personal` → `.mcp.json` を `.gitignore` に追加（embed パッケージは Unity 側の都合でコミット必須なので対象外）

## Step 1: manifest.json への登録

`Packages/manifest.json` の `dependencies` に `com.aiacats.unity-mcp` が無ければ次を追加：

```json
"com.aiacats.unity-mcp": "https://github.com/aiacats/unity-mcp.git?path=Packages/com.aiacats.unity-mcp"
```

既に Git URL 形式で登録済みかつ `Packages/com.aiacats.unity-mcp/` が未存在なら、Step 2 の前に Unity Editor を起動 or フォーカスして PackageCache に展開させる。

## Step 2: パッケージの embed

`Packages/com.aiacats.unity-mcp/` が存在しなければ `Library/PackageCache/com.aiacats.unity-mcp@*/` を Glob で探して最新を `Packages/com.aiacats.unity-mcp/` にコピー。PackageCache が無ければ Unity 起動 → 数十秒待機 → 再 Glob。

## Step 3: manifest.json を file: 参照に切替

`com.aiacats.unity-mcp` の値が Git URL のままなら `"file:com.aiacats.unity-mcp"` に書き換え。既に file: 参照ならスキップ。

## Step 4: npm install（自動 or フォールバック）

パッケージ v1.0.1 以降は Editor 起動時に `MCPAutoBootstrap` が自動で `npm install` を実行するため、通常は不要。

ただし Step 6 で Unity を起動・フォーカスする前に Claude 側でも進めたい場合は、`Packages/com.aiacats.unity-mcp/Server~/node_modules/@modelcontextprotocol/sdk` の存在を確認し、無ければ `cd Packages/com.aiacats.unity-mcp/Server~ && npm install --no-audit --no-fund` を実行（既にあればスキップ）。

## Step 5: .mcp.json 作成

プロジェクトルートに `.mcp.json` が無ければ次の内容で作成：

```json
{
    "mcpServers": {
        "claude-code-mcp-unity": {
            "command": "node",
            "args": ["Packages/com.aiacats.unity-mcp/Server~/index.js"],
            "env": {
                "MCP_UNITY_HTTP_URL": "http://localhost:8090"
            }
        }
    }
}
```

既に存在する場合は中身を読み、`claude-code-mcp-unity` キーが無ければマージで追加。あればスキップ。**既存内容の上書きは事前にユーザー確認**。

## Step 5b: gitignore 反映（`$SCOPE` = personal の場合のみ）

`.gitignore` に以下を追加（既存パターンと重複しなければ）：

```
# Claude Code MCP local config
/.mcp.json
```

`Server~/node_modules` は Unity 標準の `*~` パターンで既に ignore されるため対象外。

## Step 6: Unity Editor の起動 or フォーカス

`mcp__win-gui__find_window` で CWD basename を含むウィンドウを探す。

- **見つかった場合**: `mcp__win-gui__focus_window` でフォーカス → `mcp__win-gui__key_press` で `Ctrl+R` 送信
- **見つからなかった場合**: `ProjectSettings/ProjectVersion.txt` から Unity バージョンを読み、ユーザーに「Unity Hub から開いてください」と依頼。Unity 起動完了の signal は Step 7 の polling で兼ねる

## Step 7: HTTP サーバー起動確認

`curl -sS -m 3 http://localhost:8090/ -o /dev/null -w "HTTP_CODE=%{http_code}\n"` を最大 6 回・各 15 秒待機で polling し 200 を待つ。タイムアウトしたら警告表示し、Unity Console を確認するよう案内。

## Step 8: 完了報告

```
| Step | 状態 |
|---|---|
| スコープ | team-shared / personal |
| manifest.json 登録 | ✅ / (skip) |
| パッケージ embed | ✅ / (skip) |
| file: 参照化 | ✅ / (skip) |
| npm install | ✅ auto / ✅ manual / (skip) |
| .mcp.json 作成 | ✅ / (skip) |
| .gitignore 反映 | ✅ / N/A |
| Unity 再インポート | ✅ Ctrl+R / 手動依頼 |
| HTTP サーバー応答 | ✅ HTTP 200 / ❌ 未応答 |
```

最後に: **「Claude Code を `/exit` → 再起動してください。`.mcp.json` の承認ダイアログが出たら許可。再起動後 `/mcp` で `claude-code-mcp-unity: connected` を確認してください」**

アンインストールは `/uninstall-unity-mcp` で対称的に行えることも案内。

## 注意事項

- Submodule への書き込みは絶対にしない
- 既存ファイルの上書きは事前にユーザーに確認する
- Unity Editor の自動起動は Hub のパスや version 整合性が環境依存なので避ける
