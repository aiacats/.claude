---
name: Unity MCP デバッグフロー
description: 実装後にclaude-code-mcp-unityツールを使ってコンパイル確認・デバッグを行う手順
type: feedback
---

実装完了後、claude-code-mcp-unity MCPツールを使ってデバッグ・検証を行うこと。

手順:
1. `check_compilation_status` / `get_compilation_errors` でコンパイルエラー確認
2. エラーがあれば修正し、`force_compilation` / `hot_reload` で再コンパイル
3. `get_console_logs` でランタイムエラーやログを確認
4. `run_tests` でテスト実行
5. 必要に応じて `screenshot` でシーン状態を視覚確認

**Why:** CLAUDE.mdの「実装後の原則」にあるコンパイルエラー確認を、MCP経由でUnity Editorと直接連携して行うことで、手動確認に頼らず正確に検証できる。ユーザーからの明示的な指示。

**How to apply:** 実装作業が完了したら、必ずこのフローを実行してからユーザーに報告する。エラーが見つかった場合は根本原因を解決してから再度確認する。
