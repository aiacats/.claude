---
description: 現在のUnityプロジェクトから com.aiacats.unity-mcp をアンインストール（setup-unity-mcp の対称操作）
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# uninstall-unity-mcp

`/setup-unity-mcp` で導入した `com.aiacats.unity-mcp` 関連の構成を、現在の Unity プロジェクトからアンインストールする。

## 前提チェック

CWD が Unity プロジェクトであること（`Packages/manifest.json` 存在）。無ければ中断。

## Step 0: 影響範囲の事前提示と確認

以下を**箇条書きで提示してユーザーに最終確認**を取る（破壊的操作のため必須）：

```
これからアンインストールする対象:
  1. Packages/com.aiacats.unity-mcp/  （embed されたパッケージ一式 — 削除）
  2. Packages/manifest.json  から com.aiacats.unity-mcp エントリを削除
  3. .mcp.json  （claude-code-mcp-unity サーバー定義のみ削除、他サーバーがあればファイル残置）
  4. .gitignore  に setup 時に追加した /.mcp.json 行があれば削除（任意）

実行してよろしいですか？ [yes / no]
```

`no` または応答なしなら中断。

## Step 1: Unity Editor が起動中なら一度終了するよう促す

`mcp__win-gui__find_window` で CWD basename を含むウィンドウを探し、見つかった場合は「ロックがかかる可能性があるので Unity Editor を一度閉じてから続行してください」と案内し、ユーザー応答を待つ。

## Step 2: .mcp.json から `claude-code-mcp-unity` を削除

プロジェクトルートに `.mcp.json` があれば JSON として読み、`mcpServers.claude-code-mcp-unity` キーのみ削除。

- 削除後 `mcpServers` が空オブジェクトになる場合は **`.mcp.json` 自体を削除**
- 他のサーバー定義が残る場合は **ファイルを書き戻して保持**

## Step 3: manifest.json から `com.aiacats.unity-mcp` を削除

`Packages/manifest.json` を読み、`dependencies.com.aiacats.unity-mcp` 行を削除。JSON 構造は維持（trailing comma に注意）。

## Step 4: embed パッケージを削除

`Packages/com.aiacats.unity-mcp/` ディレクトリを再帰削除。

実行前に `git ls-files Packages/com.aiacats.unity-mcp/ | wc -l` で git 追跡ファイル数を確認し、`> 0` ならユーザーに「git 追跡されたファイルが N 件あります。削除を続けますか？」と再確認。

## Step 5: .gitignore のクリーンアップ（オプション）

`.gitignore` に setup-unity-mcp が追加した以下の行があれば削除：

```
# Claude Code MCP local config
/.mcp.json
```

直前のコメント行も含めて削除。他用途で同じ行を手動追加している可能性があるので、削除前に diff を提示してユーザー確認。

## Step 6: 完了報告

```
| Step | 状態 |
|---|---|
| .mcp.json から claude-code-mcp-unity 削除 | ✅ / (なし) |
| .mcp.json 自体の削除 | ✅ / 他サーバー残存のため保持 |
| manifest.json からエントリ削除 | ✅ / (なし) |
| Packages/com.aiacats.unity-mcp/ 削除 | ✅ / (なし) |
| .gitignore クリーンアップ | ✅ / (なし) |
```

最後に: **「Claude Code を `/exit` → 再起動すると `claude-code-mcp-unity` MCP サーバーが切断されます。Unity Editor を起動すれば `Tools > Claude Code MCP` メニューが消えていることを確認できます」**

git 追跡ファイルを削除した場合は「変更を確認したうえで `git status` → `git commit` で履歴に反映してください」と案内。

## 注意事項

- Submodule への書き込みは絶対にしない
- このコマンドは破壊的操作を含むため、Step 0 の確認は省略しない
- `Library/PackageCache/com.aiacats.unity-mcp@*/` は Unity が再生成する可能性があるので明示削除はしない（manifest.json から消えれば次回 Unity 起動時に GC される）
