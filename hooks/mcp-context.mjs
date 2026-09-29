// PostToolUse hook: 外部アプリの MCP を、そのセッションで初めて使ったときに、その MCP の罠を一度だけ差し込む。
// Unity MCP / BMCP / AEMCP / DvcMCP の作業はファイルを開かずに進むことが多く、rules/ の paths では読み込まれないため。
// 出力は 10,000 文字以内に収める（超えると 2,000 文字の preview に切られる。test-hooks.mjs が検査する）。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const home = path.join(os.homedir(), '.claude');

// ツール名の接頭辞 → 差し込む罠。サーバー名は .mcp.json の登録名なので、名前の揺れを許して照合する
const MCP_CONTEXT = [
  { name: 'Unity MCP', match: /^mcp__[^_]*unity[^_]*__/i, file: 'mcp-context/unity-mcp.md' },
  { name: 'BMCP (Blender)', match: /^mcp__bmcp__/i, file: 'rules/traps/blender.md' },
  { name: 'AEMCP (After Effects)', match: /^mcp__aemcp__/i, file: 'rules/traps/after-effects.md' },
  { name: 'DvcMCP (DaVinci Resolve)', match: /^mcp__dvcmcp__/i, file: 'rules/traps/resolve.md' },
];

const stripFrontmatter = (t) => t.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
  const entry = MCP_CONTEXT.find((e) => e.match.test(input.tool_name ?? ''));
  if (!entry || !input.session_id) return;

  const stateDir = path.join(home, 'state', 'mcp-context');
  const stateFile = path.join(stateDir, `${input.session_id}.json`);
  let seen = [];
  try {
    seen = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  } catch {}
  if (seen.includes(entry.file)) return;

  let body;
  try {
    body = stripFrontmatter(fs.readFileSync(path.join(home, entry.file), 'utf8'));
  } catch {
    return;
  }
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify([...seen, entry.file]));

  const msg = `${entry.name} をこのセッションで初めて使いました。この MCP で過去に踏んだ罠です（~/.claude/${entry.file}）。以降の操作で踏まないこと。\n\n${body}`;
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: msg } }));
}

main();
