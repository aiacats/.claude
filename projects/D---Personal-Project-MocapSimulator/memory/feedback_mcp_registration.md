---
name: MCP server registration
description: Claude Code に MCP サーバーを登録する正しい方法。`~/.claude/.mcp.json` は無効
type: feedback
originSessionId: 8ef2e761-a8af-4aea-a2c6-76fca81e526b
---
Claude Code に MCP サーバーを登録するには `claude mcp add -s user <name> <command>` を使う。

**Why:** `~/.claude/.mcp.json` を手書きしても Claude Code は読み込まない。実際の登録先は `C:\Users\komao\.claude.json`（ホーム直下、`.claude/` フォルダ内ではない）で、CLI 経由で更新する必要がある。`.mcp.json` はプロジェクトルート専用の別フォーマット。

**How to apply:** 新しい MCP を追加する時は必ず `claude mcp add` を使う。ユーザー全プロジェクトで使うなら `-s user`、特定プロジェクトのみなら `-s project`。登録後は `claude mcp list` で接続確認。新規MCPは現在のセッションでは使えず、Claude Code 再起動が必要。
