// 罠の検出 hook。trap-patterns.mjs の一覧と、ツールに渡されたコマンド / 書いた文字列 / MCP に渡したコードを照合する。
//   PreToolUse  … severity=block を実行前に止める（permissionDecision: deny）
//   PostToolUse … severity=warn を編集後・実行後に知らせる（additionalContext）
// 使い方: node trap-guard.mjs pre | post   （stdin に hook の JSON）
// 引っかかった記録は ~/.claude/state/trap-hits.log へ残す（効き目と誤検知を後で見るため）。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import patterns, { MCP_CODE_TOOLS } from './trap-patterns.mjs';

const phase = process.argv[2];
const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
const toolName = input.tool_name ?? '';
const toolInput = input.tool_input ?? {};

const isBash = toolName === 'Bash';
const isShell = isBash || toolName === 'PowerShell';
const isEdit = ['Edit', 'Write', 'MultiEdit'].includes(toolName);
const mcpCode = Object.hasOwn(MCP_CODE_TOOLS, toolName) ? MCP_CODE_TOOLS[toolName] : null;

const normalizePath = (p) => (p ?? '').replace(/\\/g, '/');
// mcp-code はファイルを持たないので、ツールごとの仮のパスで files / exclude を照合する
const filePath = mcpCode ? mcpCode.path : normalizePath(toolInput.file_path);

// 検出の定義とそのテストは、罠の文字列を例として持つのが仕事なので照合しない
if (/\/\.claude\/hooks\/(?:trap-patterns|test-hooks)\.mjs$/i.test(filePath)) process.exit(0);

// 書き足した文字列（scope=new の照合対象）
function newText() {
  if (toolName === 'Write') return toolInput.content ?? '';
  if (toolName === 'Edit') return toolInput.new_string ?? '';
  if (toolName === 'MultiEdit') return (toolInput.edits ?? []).map((e) => e.new_string ?? '').join('\n');
  return '';
}

// 編集後のファイル全体（scope=file の照合対象）。PostToolUse でだけ読める
let fileCache;
function fileState() {
  if (fileCache !== undefined) return fileCache;
  try {
    const bytes = fs.readFileSync(toolInput.file_path);
    fileCache = { bytes, text: bytes.toString('utf8') };
  } catch {
    fileCache = { bytes: null, text: '' };
  }
  return fileCache;
}

const toolsOf = (p) => (Array.isArray(p.tool) ? p.tool : [p.tool]);

function pathAllowed(p) {
  if (p.files && !p.files.test(filePath)) return false;
  if (p.exclude && p.exclude.test(filePath)) return false;
  return true;
}

function applies(p) {
  const tools = toolsOf(p);
  if (isBash && (tools.includes('bash') || tools.includes('shell'))) return true;
  if (isShell && tools.includes('shell')) return true;
  if (isEdit && tools.includes('edit')) return pathAllowed(p);
  if (mcpCode && tools.includes('mcp-code')) return pathAllowed(p);
  return false;
}

function matches(p) {
  let text;
  let bytes = null;
  if (mcpCode) {
    // 渡したコードの全体が照合対象（scope は関係ない）
    text = String(toolInput[mcpCode.field] ?? '');
  } else if (isEdit) {
    if (p.scope === 'file' || p.check) {
      ({ text, bytes } = fileState());
    } else {
      text = newText();
    }
  } else {
    text = toolInput.command ?? '';
  }
  if (text.includes(`trap-ok:${p.id}`)) return false;
  if (p.check) return p.check({ text, filePath, bytes });
  if (!p.when.test(text)) return false;
  if (p.unless && p.unless.test(text)) return false;
  return true;
}

// block は実行前にしか意味が無く、warn は編集結果（ファイル全体）を見てからでないと判定できない
const wanted = phase === 'pre' ? 'block' : 'warn';
const hits = patterns.filter((p) => p.severity === wanted && applies(p) && matches(p));
if (hits.length === 0) process.exit(0);

try {
  const stateDir = path.join(os.homedir(), '.claude', 'state');
  fs.mkdirSync(stateDir, { recursive: true });
  const cwd = normalizePath(input.cwd);
  const lines = hits.map((h) => `${new Date().toISOString()}\t${phase}\t${h.id}\t${cwd}\t${filePath || '-'}\n`).join('');
  fs.appendFileSync(path.join(stateDir, 'trap-hits.log'), lines);
} catch {
  // 記録に失敗しても判定は返す（記録は効き目の計測用で、検出の本筋ではない）
}

const body = hits
  .map((h) => `[trap:${h.id}] ${h.message}\n  詳細: ~/.claude/${h.ref}\n  誤検知なら、コマンドかコードに \`trap-ok:${h.id}\` と書けば通ります。`)
  .join('\n');

const out =
  phase === 'pre'
    ? { hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: body } }
    : { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: `過去に踏んだ罠に当たる書き方があります。直してください。\n${body}` } };
process.stdout.write(JSON.stringify(out));
