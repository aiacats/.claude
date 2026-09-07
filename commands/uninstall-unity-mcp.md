---
description: 現在のUnityプロジェクトから com.aiacats.unity-mcp をアンインストール（setup-unity-mcp の対称操作）
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, mcp__win-gui__find_window, mcp__win-gui__focus_window, mcp__win-gui__list_windows
---

# uninstall-unity-mcp

`/setup-unity-mcp` で導入した `com.aiacats.unity-mcp` 関連の構成を、現在の Unity プロジェクトからアンインストールする。

## 前提チェック

CWD が Unity プロジェクトであること（`Packages/manifest.json` 存在）。無ければ中断。

## Step 0: 配置先の特定と影響範囲の提示

setup 時の配置方式によりパッケージの置き場所が 2 通りある。**両方を実際に探してから**対象を確定する。

```bash
ls -d Packages/com.aiacats.unity-mcp 2>/dev/null
ls -d Assets/Plugins/ClaudeCodeMCP 2>/dev/null
# 別名で置いている可能性もあるため、取りこぼしを避けるなら package.json の name で探す
grep -rl '"name": *"com.aiacats.unity-mcp"' Assets Packages --include=package.json 2>/dev/null
```

見つかった実パスを `$DEST` とし、以下を**箇条書きで提示してユーザーに最終確認**を取る（破壊的操作のため必須）：

```
これからアンインストールする対象:
  1. $DEST  （パッケージ一式 — 削除）
  2. Packages/manifest.json  から com.aiacats.unity-mcp エントリを削除（記載がある場合のみ）
  3. .mcp.json  （claude-code-mcp-unity サーバー定義のみ削除、他サーバーがあればファイル残置）
  4. .claude/settings.json と .claude/settings.local.json の enabledMcpjsonServers から claude-code-mcp-unity を除去
  5. .gitignore / .git/info/exclude に setup 時に追加した行があれば削除

実行してよろしいですか？ [yes / no]
```

`no` または応答なしなら中断。`$DEST` が 1 つも見つからなければ、設定ファイル側（3〜5）のみを対象にする旨を伝える。

## Step 1: Unity Editor が起動中なら一度終了するよう促す

`mcp__win-gui__find_window` で CWD basename を含むウィンドウを探し、見つかった場合は
「ロックがかかる可能性があるので Unity Editor を一度閉じてから続行してください」と案内し、ユーザー応答を待つ。

## Step 2: .mcp.json から `claude-code-mcp-unity` を削除

プロジェクトルートに `.mcp.json` があれば JSON として読み、`mcpServers.claude-code-mcp-unity` キーのみ削除。

- 削除後 `mcpServers` が空オブジェクトになる場合は **`.mcp.json` 自体を削除**
- 他のサーバー定義が残る場合は **ファイルを書き戻して保持**

ユーザースコープ（`claude mcp add --scope user`）へ登録している構成もありうる。
プロジェクトの `.mcp.json` に定義が無いのに接続されている場合は `claude mcp list` を確認し、
ユーザースコープの解除は `claude mcp remove` をユーザー自身に実行してもらう。

## Step 2b: `enabledMcpjsonServers` から登録解除

`.claude/settings.json` と `.claude/settings.local.json` の双方について、存在すれば JSON として読み込み、
トップレベルの `enabledMcpjsonServers` 配列から `claude-code-mcp-unity` を除去：

- 配列に含まれていなければ何もしない
- 除去後 `enabledMcpjsonServers` が空配列になる場合はキー自体を削除
- ファイルに他のキー（`permissions` など）が残るなら書き戻して保持
- キーが `enabledMcpjsonServers` だけになり本体が `{}` になる場合も **ファイルは削除しない**（他用途で使われ得る）

## Step 3: manifest.json から `com.aiacats.unity-mcp` を削除

`Packages/manifest.json` に `dependencies.com.aiacats.unity-mcp` があれば削除。JSON 構造は維持（trailing comma に注意）。

**Assets 配下へ配置した構成では manifest に記載が無いのが正常**なので、無ければ何もしない（警告も不要）。

編集後は `node -e "JSON.parse(...)"` で妥当性を確認する。`sed -i` を使うと CRLF が LF へ変わって
不要な差分が出ることがある。行削除だけなら内容差分は無いはずなので、`git diff` が空なら
`git checkout -- Packages/manifest.json` ではなく**削除結果を保つ**こと（削除は意図した変更のため）。

## Step 4: パッケージ本体を削除

Step 0 で確定した `$DEST` を再帰削除。

実行前に `git ls-files "$DEST" | wc -l` で git 追跡ファイル数を確認し、
`> 0` ならユーザーに「git 追跡されたファイルが N 件あります。削除を続けますか？」と再確認。

削除後、Unity を起動すると `packages-lock.json` から `com.aiacats.unity-mcp` のエントリが消える
（`Packages/` 配下に置いていた場合）。差分が出るので、コミットするかをユーザーに確認する。

## Step 5: ignore 設定のクリーンアップ

setup 時の書き込み先が 2 通りあるため、両方を確認する。

- `.gitignore` … `/.mcp.json`、`/Packages/com.aiacats.unity-mcp/Server~/node_modules/` などの行
- `.git/info/exclude` … `/Assets/Plugins/ClaudeCodeMCP/`、`/Packages/com.aiacats.unity-mcp/` などの行

直前のコメント行も含めて削除する。他用途で同じ行を手動追加している可能性があるので、
削除前に diff を提示してユーザー確認を取る。

## Step 6: 完了報告

```
| Step | 状態 |
|---|---|
| 配置先の特定 | Packages/... / Assets/Plugins/... / (見つからず) |
| .mcp.json から claude-code-mcp-unity 削除 | ✅ / (なし) |
| .mcp.json 自体の削除 | ✅ / 他サーバー残存のため保持 |
| enabledMcpjsonServers 登録解除 | ✅ settings.json / ✅ settings.local.json / (なし) |
| manifest.json からエントリ削除 | ✅ / (記載なし＝正常) |
| パッケージ本体の削除 | ✅ / (なし) |
| packages-lock.json | ✅ エントリ消滅 / N/A（元から未記載） |
| ignore クリーンアップ | ✅ .gitignore / ✅ .git/info/exclude / (なし) |
```

最後に: **「Claude Code を `/exit` → 再起動すると `claude-code-mcp-unity` MCP サーバーが切断されます。Unity Editor を起動すれば `Tools > Claude Code MCP` メニューが消えていることを確認できます」**

git 追跡ファイルを削除した場合は「変更を確認したうえで `git status` → `git commit` で履歴に反映してください」と案内。

## 注意事項

- Submodule への書き込みは絶対にしない
- このコマンドは破壊的操作を含むため、Step 0 の確認は省略しない
- `Library/PackageCache/com.aiacats.unity-mcp@*/` は明示削除しない（manifest から消えれば次回 Unity 起動時に GC される）
