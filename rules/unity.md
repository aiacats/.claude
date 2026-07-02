# Unity プロジェクト共通ルール

このファイルは `~/.claude/rules/unity.md`。SessionStart hook により、Unity プロジェクト（`ProjectSettings/ProjectVersion.txt` が存在する）でのみ context に自動注入される。グローバル CLAUDE.md の原則に加えて、以下を必ず守ること。

## 実装後のデバッグフロー（claude-code-mcp-unity MCP を使用）

1. `force_compilation` / `hot_reload` で再コンパイルをトリガする。
2. **`wait_for_compilation_done` を1回だけ呼んで完了を待つ**（`check_compilation_status` を polling で連打しない。コンソールがログで詰まり、token も無駄になる）。
3. `get_compilation_errors` でエラー内容を取得する。
4. `get_console_logs` でランタイムエラーやログを確認する。
5. `run_tests` でテストを実行する。
6. 必要に応じて `screenshot` でシーンの状態を視覚確認する。
7. エラーが見つかった場合は根本原因を解決し、再度このフローを実行する。

自主レビュー（グローバル CLAUDE.md「実装後の自主レビュー」）の検証コマンドも同フロー: `force_compilation` → `wait_for_compilation_done` → `get_compilation_errors` → `get_console_logs`。

## シーン保存（恒久・全 Unity プロジェクト共通）

**Unity シーンを自分で変更したら必ず自分で保存する**。MCP の `update_component`／オブジェクト追加・削除、Play 検証のための一時改変を含め、シーンに手を入れたら最後に意図した状態へ戻したうえで `save_scene`（MCP）で保存する。保存し忘れると変更が宙ぶらりんになり、次の操作や domain reload で失われたり、dirty 状態の放置で混乱する。ユーザー指示(2026-06-20)。

## Unity MCP のソース所在と更新フロー（恒久）

- **Unity MCP ソース**: `D:\_Personal\Project\unity-mcp`（Unity 側 embed パッケージ名 `com.aiacats.unity-mcp`、GitHub: aiacats/unity-mcp）
- MCP に機能追加・修正が必要になったら、**使用中プロジェクト内の embed パッケージを直接いじるのではなく、必ず上記ソースリポジトリを更新する**。プロジェクト固有 Editor スクリプトで MCP 的な機能（例: 自動 Play、UI キャプチャ等）を暫定実装した場合も、恒久化のため MCP 本体へ移設する。

更新フロー:
1. `D:\_Personal\Project\unity-mcp` のソースを更新（Node サーバー側 + Unity Editor C# 側）。
2. **このリポジトリに限り、自動でコミット & Push してよい**。
3. その後、使用中プロジェクトの UPM（embed `com.aiacats.unity-mcp`）を更新して取り込む（PackageCache から再 embed、または file: 参照先の同期）。Claude 自身がこの取り込みまで行う。
4. 「自動で Play させる機能」など、これまでプロジェクト側 Editor スクリプトに足してきた MCP 的機能は Unity MCP 本体へ入れる。

## Unity 起動時の注意（恒久）

- Claude のターミナルが管理者権限のことがあり、そこから `Start-Process Unity.exe` すると **Unity が管理者起動**になり「Unity is running as administrator」警告が出る。Unity 起動は **Unity Hub から**行う（またはユーザーに依頼する）のが基本。どうしても CLI 起動する場合も管理者昇格を避ける。
- MCP の新ツール追加後は、Claude Code 再起動まで新ツールは呼べない（既存ツールは動く）。

## MCP 有効化

- Unity プロジェクトでは `.claude/settings.local.json` の `enabledMcpjsonServers` に `claude-code-mcp-unity`, `context7` を列挙する（グローバル CLAUDE.md「MCP サーバーのプロジェクト別有効化方針」参照）。
- セットアップは `/setup-unity-mcp` skill が使える。
