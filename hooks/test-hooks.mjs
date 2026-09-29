// hooks のテスト。パターンを足したら必ず回す: node ~/.claude/hooks/test-hooks.mjs
//   - trap-patterns.mjs の examples（当たる例 / 当たらない例）を全件流す（誤検知と見逃しの両方）
//   - 参照先（ref）のファイルと見出しが実在するか
//   - バイト列で判定するパターン、ファイル全体で判定するパターン、trap-guard の振る舞い
//   - daily-reload / project-context

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import patterns, { MCP_CODE_TOOLS } from './trap-patterns.mjs';

const toolsOf = (p) => (Array.isArray(p.tool) ? p.tool : [p.tool]);
// mcp-code の仮のパス → ツール名（examples の [仮のパス, コード] を MCP ツールの呼び出しに戻す）
const mcpToolByPath = Object.fromEntries(Object.entries(MCP_CODE_TOOLS).map(([name, t]) => [t.path, { name, field: t.field }]));

const here = path.dirname(fileURLToPath(import.meta.url));
const claudeDir = path.join(here, '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'trap-test-'));
let failed = 0;
let passed = 0;

function run(script, args, input, env = {}) {
  const r = spawnSync(process.execPath, [path.join(here, script), ...args], {
    input: JSON.stringify(input),
    encoding: 'utf8',
    env: { ...process.env, ...env },
  });
  if (r.status !== 0) throw new Error(`${script} exit ${r.status}: ${r.stderr}`);
  return r.stdout ? JSON.parse(r.stdout) : null;
}

// trap-guard の記録（state/trap-hits.log）をテストで汚さないよう、HOME を一時フォルダへ向ける
const guardEnv = { USERPROFILE: tmp, HOME: tmp };
function guard(phase, toolName, toolInput) {
  const out = run('trap-guard.mjs', [phase], { tool_name: toolName, tool_input: toolInput, cwd: tmp }, guardEnv);
  const text = out?.hookSpecificOutput?.permissionDecisionReason ?? out?.hookSpecificOutput?.additionalContext ?? '';
  return [...text.matchAll(/\[trap:([\w-]+)\]/g)].map((m) => m[1]);
}

function writeFile(rel, content) {
  const p = path.join(tmp, 'ws', rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content);
  return p;
}

function check(label, ok, detail = '') {
  if (ok) { passed++; return; }
  failed++;
  console.log(`FAIL ${label}${detail ? ` — ${detail}` : ''}`);
}
function expectHit(label, got, id, shouldHit) {
  check(`${label}: ${id} ${shouldHit ? 'を検出すべき' : 'を検出してはいけない'}`, got.includes(id) === shouldHit, `got: ${got.join(',') || 'なし'}`);
}

// GitHub 形式の見出しアンカー（記号を落とし、空白を - に）
const slug = (h) => h.trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s/g, '-');

// ─── 一覧の整合 ───
{
  const ids = patterns.map((p) => p.id);
  const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
  check('id に重複なし', dup.length === 0, dup.join(','));
  for (const p of patterns) {
    const tools = toolsOf(p);
    check(`${p.id}: 必須項目`, !!(p.message && p.ref && (p.when || p.check) && ['block', 'warn'].includes(p.severity) && tools.length > 0 && tools.every((t) => ['bash', 'shell', 'edit', 'mcp-code'].includes(t))));
    check(`${p.id}: edit の block は判定できない（編集後にしか中身を読めない）`, !(p.severity === 'block' && tools.includes('edit')));
    check(`${p.id}: examples が要る`, !!p.check || (p.examples?.hit?.length > 0 && p.examples?.miss?.length > 0));
    // 例の形がツール種別と合っているか（合っていないと、例が別の経路で流れて素通りする）
    for (const ex of [...(p.examples?.hit ?? []), ...(p.examples?.miss ?? [])]) {
      const kind = !Array.isArray(ex) ? 'command' : ex[0].startsWith('mcp:') ? 'mcp-code' : 'edit';
      const ok =
        kind === 'command' ? tools.includes('bash') || tools.includes('shell')
        : kind === 'mcp-code' ? tools.includes('mcp-code') && !!mcpToolByPath[ex[0]]
        : tools.includes('edit');
      check(`${p.id}: 例の形が tool と合わない（${kind}: ${String(Array.isArray(ex) ? ex[0] : ex).slice(0, 40)}）`, ok);
    }
    const [refFile, anchor] = p.ref.split('#');
    const abs = path.join(claudeDir, refFile);
    if (!fs.existsSync(abs)) { check(`${p.id}: ref 先 ${refFile} が無い`, false); continue; }
    if (anchor) {
      const anchors = fs.readFileSync(abs, 'utf8').split('\n').filter((l) => /^#{1,6}\s/.test(l)).map((l) => slug(l.replace(/^#+\s*/, '')));
      check(`${p.id}: ref の見出し #${anchor} が ${refFile} に無い`, anchors.includes(anchor));
    }
  }
}

// ─── examples を全件流す ───
for (const p of patterns) {
  if (!p.examples) continue;
  const phase = p.severity === 'block' ? 'pre' : 'post';
  for (const [kind, shouldHit] of [['hit', true], ['miss', false]]) {
    for (const ex of p.examples[kind] ?? []) {
      let got;
      if (Array.isArray(ex) && mcpToolByPath[ex[0]]) {
        const { name, field } = mcpToolByPath[ex[0]];
        got = guard(phase, name, { [field]: ex[1] });
      } else if (Array.isArray(ex)) {
        const [rel, text] = ex;
        const fp = writeFile(rel, text);
        got = guard(phase, 'Edit', { file_path: fp, new_string: text });
      } else {
        got = guard(phase, 'Bash', { command: ex });
      }
      expectHit(`${p.id} ${kind} 「${String(Array.isArray(ex) ? ex.join(' | ') : ex).slice(0, 50).replace(/\n/g, '⏎')}」`, got, p.id, shouldHit);
    }
  }
}

// ─── trap-guard の振る舞い ───
expectHit('Git Bash 固有の罠は PowerShell ツールでは出さない', guard('pre', 'PowerShell', { command: 'python osc_send.py 127.0.0.1 9000 /a/b 1' }), 'osc-address-msys', false);
expectHit('shell の罠は PowerShell ツールでも出す', guard('pre', 'PowerShell', { command: 'Stop-Process -Name Unity' }), 'kill-unity', true);
expectHit('trap-ok で素通り', guard('pre', 'Bash', { command: 'taskkill //IM Unity.exe  # trap-ok:kill-unity' }), 'kill-unity', false);
expectHit('block は post で二重に言わない', guard('post', 'Bash', { command: 'taskkill //IM Unity.exe' }), 'kill-unity', false);
expectHit('warn は pre で止めない', guard('pre', 'Bash', { command: 'pip install numpy' }), 'bare-pip-install', false);
{
  const p = writeFile('Assets/Old.cs', 'if (a.StartsWith("x")) {}\nint added = 1;');
  expectHit('既存行の罠は、書き足した部分に無ければ出さない', guard('post', 'Edit', { file_path: p, new_string: 'int added = 1;' }), 'cs-culture-string-compare', false);
  const m = writeFile('Assets/Multi.cs', '');
  expectHit('MultiEdit の各 new_string を見る', guard('post', 'MultiEdit', { file_path: m, edits: [{ new_string: 'int a;' }, { new_string: 'x.StartsWith("y")' }] }), 'cs-culture-string-compare', true);
  const self = path.join(claudeDir, 'hooks', 'trap-patterns.mjs');
  check('検出の定義ファイル自身は照合しない', guard('post', 'Write', { file_path: self, content: 'x.StartsWith("y")' }).length === 0);
}

// ─── mcp-code ───
{
  const renderAll = { source: 'app.project.renderQueue.render();' };
  expectHit('mcp-code の block は実行前に止める', guard('pre', 'mcp__aemcp__ae_run_script', renderAll), 'ae-run-script-renderqueue-render', true);
  expectHit('mcp-code の block は post で二重に言わない', guard('post', 'mcp__aemcp__ae_run_script', renderAll), 'ae-run-script-renderqueue-render', false);
  expectHit('mcp-code の trap-ok で素通り', guard('pre', 'mcp__aemcp__ae_run_script', { source: 'app.project.renderQueue.render(); // trap-ok:ae-run-script-renderqueue-render' }), 'ae-run-script-renderqueue-render', false);
  expectHit('mcp-code の warn は pre で止めない', guard('pre', 'mcp__bmcp__blender_run_python', { source: 'mod["Socket_2"] = 0.5' }), 'blender-gn-socket-index', false);
  expectHit('mcp-code の warn は post で知らせる', guard('post', 'mcp__bmcp__blender_run_python', { source: 'mod["Socket_2"] = 0.5' }), 'blender-gn-socket-index', true);
  expectHit('Blender の罠は Resolve の run_python に当てない', guard('post', 'mcp__dvcmcp__resolve_run_python', { source: 'mod["Socket_2"] = 0.5' }), 'blender-gn-socket-index', false);
  expectHit('AE の罠を AEMCP 以外の MCP に当てない', guard('pre', 'mcp__bmcp__blender_run_python', renderAll), 'ae-run-script-renderqueue-render', false);
  expectHit('edit 専用の罠は mcp-code に当てない', guard('post', 'mcp__bmcp__blender_run_python', { source: 'r = unreal.Rotator(0, 90, 0)' }), 'ue-rotator-positional', false);
  expectHit('mcp-code の罠を Edit で書いた同名ファイルには当てない', guard('pre', 'Edit', { file_path: path.join(tmp, 'ws', 'run_script.jsx'), new_string: renderAll.source }), 'ae-run-script-renderqueue-render', false);
  check('対象外の MCP ツールは何も照合しない', guard('pre', 'mcp__aemcp__ae_set_text', { source: renderAll.source, text: 'x' }).length === 0);
  // settings.json の matcher が MCP_CODE_TOOLS を漏れなく含むか（漏れると hook が呼ばれず、黙って素通りする）
  const hooks = JSON.parse(fs.readFileSync(path.join(claudeDir, 'settings.json'), 'utf8')).hooks ?? {};
  for (const ev of ['PreToolUse', 'PostToolUse']) {
    const matchers = (hooks[ev] ?? []).filter((h) => h.hooks?.some((c) => /trap-guard\.mjs/.test(c.command ?? ''))).map((h) => h.matcher ?? '');
    for (const name of Object.keys(MCP_CODE_TOOLS)) {
      check(`settings.json ${ev} の trap-guard の matcher に ${name}`, matchers.some((m) => m.split('|').includes(name)));
    }
  }
}

// ─── バイト列で判定するもの ───
{
  const bom8 = Buffer.from([0xef, 0xbb, 0xbf]);
  const bom16 = Buffer.from([0xff, 0xfe]);
  const cases = [
    ['ps1-non-ascii-without-bom', 'a.ps1', Buffer.from('Write-Host "こんにちは"'), true],
    ['ps1-non-ascii-without-bom', 'a.ps1', Buffer.concat([bom8, Buffer.from('Write-Host "こんにちは"')]), false],
    ['ps1-non-ascii-without-bom', 'a.ps1', Buffer.from('Write-Host "hello"'), false],
    ['vbs-non-ascii-without-utf16-bom', 'a.vbs', Buffer.from('MsgBox "テスト"'), true],
    ['vbs-non-ascii-without-utf16-bom', 'a.vbs', Buffer.concat([bom16, Buffer.from('MsgBox "テスト"', 'utf16le')]), false],
    ['vbs-non-ascii-without-utf16-bom', 'a.vbs', Buffer.from('MsgBox "test"'), false],
    ['bat-formfeed', 'a.bat', Buffer.from('python "%~dp0scripts\fetch-tools.py"'), true],
    ['bat-formfeed', 'a.bat', Buffer.from('python "%~dp0scripts/fetch-tools.py"'), false],
    ['unity-json-bom', 'Packages/manifest.json', Buffer.concat([bom8, Buffer.from('{ "dependencies": {} }')]), true],
    ['unity-json-bom', 'Assets/Foo/Foo.Runtime.asmdef', Buffer.concat([bom8, Buffer.from('{ "name": "Foo" }')]), true],
    ['unity-json-bom', 'Packages/manifest.json', Buffer.from('{ "dependencies": {} }'), false],
    ['unity-json-bom', 'src/package.json', Buffer.concat([bom8, Buffer.from('{}')]), false],
    ['unity-json-bom', 'Assets/Data/table.json', Buffer.concat([bom8, Buffer.from('{}')]), false],
  ];
  for (const [id, name, bytes, shouldHit] of cases) {
    const p = path.join(tmp, 'ws', name);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, bytes);
    expectHit(`バイト列 ${name} (${bytes.length}B)`, guard('post', 'Write', { file_path: p, content: 'x' }), id, shouldHit);
  }
}

// ─── daily-reload ───
{
  const home = path.join(tmp, 'home');
  const claude = path.join(home, '.claude');
  fs.mkdirSync(path.join(claude, 'rules', 'traps'), { recursive: true });
  fs.mkdirSync(path.join(claude, 'project-types'), { recursive: true });
  fs.writeFileSync(path.join(claude, 'CLAUDE.md'), '# g');
  fs.writeFileSync(path.join(claude, 'rules', 'traps', 'unity.md'), '---\npaths:\n  - "**/*.cs"\n---\n# u');
  fs.writeFileSync(path.join(claude, 'project-types', 'app.md'), '# a');
  const oldRule = path.join(claude, 'rules', 'traps', 'old.md');
  fs.writeFileSync(oldRule, '# 読み込みより前から変わっていない');
  const env = { USERPROFILE: home, HOME: home };
  const dr = (mode, extra = {}) => run('daily-reload.mjs', [mode], { session_id: 's1', ...extra }, env);
  const stateFile = path.join(claude, 'state', 'rule-sessions', 's1.json');
  const DAY = 24 * 3600 * 1000;
  const ctxOf = (out) => out?.hookSpecificOutput?.additionalContext ?? '';
  // 読み込みを「昨日」にし、old.md だけ読み込みより前の更新時刻にする
  const setLoadedYesterday = (extra = {}) => {
    const loadedAt = Date.now() - DAY - 3600 * 1000;
    fs.utimesSync(oldRule, new Date(loadedAt - 3600 * 1000), new Date(loadedAt - 3600 * 1000));
    const st = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    fs.writeFileSync(stateFile, JSON.stringify({ ...st, date: '2000-01-01', loadedAt, ...extra }));
  };

  dr('session-start');
  check('同じ日は何も出さない', dr('prompt') === null);
  check('session-start は読み込んだファイル一覧を持つ', JSON.parse(fs.readFileSync(stateFile, 'utf8')).files?.length === 4);

  setLoadedYesterday();
  let ctx = ctxOf(dr('prompt'));
  check('日付が変わり更新あり → 常時読むものは「必ず」側', /必ず読み直す:\n[^\n]*CLAUDE\.md/.test(ctx), ctx);
  check('paths 付きと project-types は「関係するなら」側', /関係する分野・種別なら[^\n]*\n(- [^\n]*\n?)*- [^\n]*(unity|app)\.md/.test(ctx) && ctx.includes('unity.md') && ctx.includes('app.md'), ctx);
  check('読み込みより前から変わっていないファイルは挙げない', !ctx.includes('old.md'), ctx);
  check('同じ日の 2 回目は出さない', dr('prompt') === null);

  // 日付は変わったが、どれも読み込みより前の更新
  dr('session-start');
  for (const f of JSON.parse(fs.readFileSync(stateFile, 'utf8')).files) fs.utimesSync(f, new Date(Date.now() - 3 * DAY), new Date(Date.now() - 3 * DAY));
  setLoadedYesterday();
  check('日付が変わっても更新が無ければ出さない', dr('prompt') === null);

  // 読み込んだ後にルールが消された
  dr('session-start');
  for (const f of JSON.parse(fs.readFileSync(stateFile, 'utf8')).files) fs.utimesSync(f, new Date(Date.now() - 3 * DAY), new Date(Date.now() - 3 * DAY));
  setLoadedYesterday();
  fs.rmSync(oldRule);
  ctx = ctxOf(dr('prompt'));
  check('消されたルールを「削除された」として挙げる', /削除されたルール[^\n]*\n- [^\n]*old\.md/.test(ctx), ctx);

  // hook 導入前からのセッション（記録なし）: transcript の最初の timestamp を読み込み時刻とみなす
  fs.rmSync(stateFile);
  const transcript = path.join(tmp, 'old-session.jsonl');
  fs.writeFileSync(path.join(claude, 'CLAUDE.md'), '# g2'); // 今更新された
  fs.writeFileSync(transcript, JSON.stringify({ type: 'user', timestamp: new Date(Date.now() - 2 * DAY).toISOString() }) + '\n');
  ctx = ctxOf(dr('prompt', { transcript_path: transcript }));
  check('記録なし・一昨日に始まったセッション → 知らせる', ctx.includes('CLAUDE.md'), ctx);
  fs.rmSync(stateFile);
  fs.writeFileSync(transcript, JSON.stringify({ type: 'user', timestamp: new Date().toISOString() }) + '\n');
  check('記録なし・今日始まったセッション → 出さない', dr('prompt', { transcript_path: transcript }) === null);
}

// ─── mcp-context ───
{
  const home = path.join(tmp, 'mc-home');
  fs.cpSync(path.join(claudeDir, 'mcp-context'), path.join(home, '.claude', 'mcp-context'), { recursive: true });
  fs.cpSync(path.join(claudeDir, 'rules', 'traps'), path.join(home, '.claude', 'rules', 'traps'), { recursive: true });
  const env = { USERPROFILE: home, HOME: home };
  const mc = (tool, session = 'm1') => {
    const out = run('mcp-context.mjs', [], { session_id: session, tool_name: tool }, env);
    return out?.hookSpecificOutput?.additionalContext ?? '';
  };
  const u = mc('mcp__claude-code-mcp-unity__force_compilation');
  check('Unity MCP の初回で unity-mcp の罠を出す', u.includes('# unity-mcp の罠'), u.slice(0, 80));
  check('frontmatter は外して出す', !/^---/m.test(u.split('\n\n').slice(1).join('\n\n')));
  check('同じセッションの 2 回目は出さない', mc('mcp__claude-code-mcp-unity__get_console_logs') === '');
  check('別のセッションではまた出す', mc('mcp__claude-code-mcp-unity__get_console_logs', 'm2').includes('unity-mcp'));
  check('BMCP は blender の罠', mc('mcp__bmcp__blender_status').includes('# blender の罠'));
  check('AEMCP は after-effects の罠', mc('mcp__aemcp__ae_status').includes('after-effects'));
  check('DvcMCP は resolve の罠', mc('mcp__dvcmcp__resolve_status').includes('resolve'));
  check('関係ない MCP では出さない', mc('mcp__win-gui__capture_window', 'm3') === '');
  for (const f of ['mcp-context/unity-mcp.md', 'rules/traps/blender.md', 'rules/traps/after-effects.md', 'rules/traps/resolve.md']) {
    const n = [...fs.readFileSync(path.join(claudeDir, f), 'utf8')].length;
    check(`${f} は hook の上限内（${n} 文字）`, n < 9500); // 10,000 から前置きの 1 文ぶんを引いた値
  }
  const settings = JSON.parse(fs.readFileSync(path.join(claudeDir, 'settings.json'), 'utf8'));
  const post = (settings.hooks?.PostToolUse ?? []).filter((h) => h.hooks.some((x) => x.command.includes('mcp-context.mjs')));
  for (const t of ['mcp__claude-code-mcp-unity__x', 'mcp__bmcp__x', 'mcp__aemcp__x', 'mcp__dvcmcp__x']) {
    check(`settings.json の mcp-context の matcher が ${t} に当たる`, post.some((h) => new RegExp(`^(?:${h.matcher})$`).test(t)));
  }
}

// ─── project-context ───
{
  const LIMIT = 10000; // hook 出力の上限（公式仕様。超えると 2,000 文字の preview に切られる）
  const typesDir = path.join(claudeDir, 'project-types');
  for (const f of fs.readdirSync(typesDir)) {
    const n = [...fs.readFileSync(path.join(typesDir, f), 'utf8')].length;
    check(`project-types/${f} が上限内（${n} 文字）`, n <= LIMIT);
  }
  const home = path.join(tmp, 'pc-home');
  fs.mkdirSync(path.join(home, '.claude'), { recursive: true });
  fs.cpSync(typesDir, path.join(home, '.claude', 'project-types'), { recursive: true });
  const pc = (cwd) =>
    spawnSync(process.execPath, [path.join(here, 'project-context.mjs')], {
      input: JSON.stringify({ cwd }),
      encoding: 'utf8',
      env: { ...process.env, USERPROFILE: home, HOME: home },
    }).stdout;
  const mk = (name, files) => {
    const d = path.join(tmp, 'pc', name);
    fs.mkdirSync(d, { recursive: true });
    for (const f of files) { fs.mkdirSync(path.dirname(path.join(d, f)), { recursive: true }); fs.writeFileSync(path.join(d, f), ''); }
    return d;
  };
  const u = pc(mk('unity', ['ProjectSettings/ProjectVersion.txt']));
  check('Unity を見分ける', u.includes('Unity プロジェクトの作業方針'));
  check('Unity にアプリの方針を入れない', !u.includes('アプリ開発'));
  check('1 階層下の Unity も見分ける', pc(mk('unity-sub', ['unity_proj/ProjectSettings/ProjectVersion.txt'])).includes('Unity プロジェクトの作業方針'));
  check('package.json でアプリ', pc(mk('app', ['package.json'])).includes('アプリ開発'));
  check('src-tauri だけでもアプリ', pc(mk('tauri', ['src-tauri/Cargo.toml'])).includes('アプリ開発'));
  check('どちらでもなければ何も出さない', pc(mk('none', ['README.md'])).trim() === '');
  const b = pc(mk('both', ['package.json', 'ProjectSettings/ProjectVersion.txt']));
  check('両方なら両方を上限内で出す', b.length <= LIMIT && b.includes('Unity') && (b.includes('アプリ開発') || b.includes('app.md')));
}

// ─── ルールの置き場の整合 ───
{
  const rulesDir = path.join(claudeDir, 'rules');
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
  for (const f of walk(rulesDir).filter((f) => f.endsWith('.md'))) {
    const rel = path.relative(claudeDir, f).replace(/\\/g, '/');
    const text = fs.readFileSync(f, 'utf8');
    // paths の frontmatter は YAML の配列で書く（壊れていると、黙って常時読み込みになる）
    if (text.startsWith('---')) {
      const fm = text.split(/\r?\n---/)[0];
      check(`${rel}: frontmatter に paths の配列`, /^paths:\s*\r?\n(\s+- "[^"]+"\r?\n?)+/m.test(fm + '\n'), fm.slice(0, 120));
    }
  }
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log(failed ? `\n${passed} 件成功 / ${failed} 件失敗` : `\nすべて成功（${passed} 件）`);
process.exit(failed ? 1 : 0);
