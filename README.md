# ~/.claude（Claude Code のグローバル設定）

全プロジェクト共通の方針・好み・過去に踏んだ罠と、それを効かせる hook を置くリポジトリ。

## 何がどこにあるか

| 置き場所 | 中身 | いつ読まれるか |
|---|---|---|
| `CLAUDE.md` | 方針（どう進めるか） | 常時 |
| `rules/taste/general.md` | ユーザーの好み・こだわり（見た目・文言・操作感・作り方・進め方） | 常時 |
| `rules/taste/rendering.md` | 演出・シェーダー・3D の美意識 | シェーダー等を開いたとき（`paths:`） |
| `rules/traps/<分野>.md` | 罠の厳選版（再発しやすく、注意では防げないもの） | windows-shell・process・git・claude-code・mcp-external は常時。他は該当ファイルを開いたとき |
| `traps-catalog/<分野>.md` | 罠の全件（症状・原因・対策・実例・出典） | 自動では読まれない。トラブル時に grep |
| `traps-catalog/_mcp-fixes.md` | 自作 MCP 本体で直すべき罠の一覧 | 手動 |
| `project-types/{unity,app}.md` | プロジェクト種別ごとの作業方針 | 該当プロジェクトの開始時（`hooks/project-context.mjs`） |
| `mcp-context/unity-mcp.md` | Unity MCP の罠 | Unity MCP を初めて使ったとき（`hooks/mcp-context.mjs`。BMCP / AEMCP / DvcMCP は `rules/traps/` の該当ファイルを出す） |
| `hooks/trap-patterns.mjs` | 機械的に見つけられる罠 100 件（block 18 / warn 82） | コマンド実行前・実行後・編集後（`hooks/trap-guard.mjs`） |
| `hooks/daily-reload.mjs` | 日付をまたいだセッションで、更新・削除されたルールを読み直させる | 開始時に記録、日付が変わって最初の依頼で通知 |
| `hooks/rm-guard.mjs` | 再帰削除（`rm -r` 系）の対象が一時フォルダ（`%TEMP%` 配下）の中と断定できないときだけ確認を出す。以前の `permissions.ask` の `rm -r` の代わり（scratchpad の掃除で何時間も止まっていたため） | Bash の実行前 |
| `tools/session-stats.mjs` | セッション記録から作業時間の内訳（モデル・ツール・ユーザー待ち・許可待ち・停滞）を集計する | 手動 |
| `skills/` | 手順（順番・コマンド・補助スクリプト） | 呼んだとき |

`rules/` 配下は Claude Code が再帰的に自動で読む（frontmatter の `paths:` があれば、一致するファイルを Read したときだけ）。
種別で絞りたいものを `rules/` に置くと全セッションで読まれるので、`project-types/` に置いて hook から差し込む。
hook の出力は 10,000 文字を超えると先頭 2,000 文字の preview に切られるため、差し込むファイルはその上限に収める（テストが検査する）。

## 罠・好みを足すとき

1. `traps-catalog/<分野>.md` に全件の形式で足す（同じ罠があれば実例を追記）。
2. 今後も普通に踏み、注意では防げないなら `rules/traps/<分野>.md` にも 2〜4 行で足す。
3. コマンドや書いたコードの正規表現で確実に見つけられるなら、`hooks/trap-patterns.mjs` に `examples`（当たる例・当たらない例）付きで足す。
4. `node hooks/test-hooks.mjs` を通す。

好みは、同じ種類の手直しを 2 回させたら `rules/taste/general.md` へ足す。

誤検知で止められたときは、コマンドかコードに `trap-ok:<id>` と書けば通る。引っかかった記録は `state/trap-hits.log`（追跡対象外）。

## 検証

```bash
node hooks/test-hooks.mjs   # パターンの例・参照先の見出し・hook の振る舞い・出力の上限
```
