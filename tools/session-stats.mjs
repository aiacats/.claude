// Claude Code のセッション記録（~/.claude/projects/*/*.jsonl）から、作業時間が何に使われているかを集計する。
// 使い方: node ~/.claude/tools/session-stats.mjs [--since YYYY-MM-DD] [--project <部分一致>] [--out <report.md>]
//
// 見るもの
//   - Claude が動いていた時間（依頼ごとの turn_duration の合計）の内訳:
//       モデル（考えて書いている時間）/ ツール実行 / ユーザー待ち（AskUserQuestion・許可ダイアログ）
//   - ツールの種類ごとの所要時間・回数・失敗。Bash はコマンドの種類（ビルド・テスト・待ち・探索…）に分ける
//   - 失敗と、その直後のやり直し。hook に止められた回数
//   - 1 回の応答で読ませた量（入力トークン）と、応答にかかった時間の関係
//   - セッション冒頭の「調べ物」（最初の Edit/Write までのツール回数）
//   - 遅かったツール呼び出しの上位
//
// 注意
//   - ツールは並列に呼ばれることがあるので、ツール別の合計は重なりを含む（壁時計の内訳は「フェーズ」の方で見る）
//   - サブエージェントの中の時間は、親の Agent ツールの時間として 1 本で数える（中身は subagents/ に別記録）

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';

const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : undefined;
};
const since = opt('since') ? Date.parse(opt('since')) : 0;
const projectFilter = opt('project');
const outFile = opt('out');
const root = path.join(os.homedir(), '.claude', 'projects');

// ─── 分類 ───────────────────────────────────────────
// Bash / PowerShell のコマンドを、時間の使い道で分ける。先に当たったものを採る
const BASH_KINDS = [
  ['wait', /\b(sleep|timeout\s+\d|Start-Sleep|wait_for|until\b)/i],
  ['claude-cli', /\bclaude(\.exe)?\s+(-p|--print|mcp|agents|respawn)/],
  ['unity', /Unity\.exe|Editor\.log|ScriptAssemblies/i],
  ['build:rust', /\bcargo\s+(build|b\b|run|install|tauri)|tauri\s+build|npm run tauri build/],
  ['check:rust', /\bcargo\s+(check|clippy|test|nextest)/],
  ['build:js', /\b(npm|pnpm|yarn|npx)\s+(run\s+)?(build|bundle)|\bvite\s+build|\btsc\b/],
  ['test:js', /\b(npm|pnpm|yarn|npx)\s+(run\s+)?(test|vitest|typecheck|lint)|\bvitest\b|\bplaywright\b/],
  ['install', /\b(npm|pnpm|yarn)\s+(i|install|ci|add)\b|\bpip\s+install|\buv\s+(add|sync|pip)|\bwinget\b|\bchoco\b/],
  ['dotnet', /\bdotnet\s+/],
  ['python', /\b(python|py|uv\s+run)\b/],
  ['node', /\bnode\s+/],
  ['git', /^\s*(cd\s+[^&;]+&&\s*)?git\s+/],
  ['network', /\b(curl|wget|rclone|gh\s+)/],
  ['process', /\b(taskkill|Stop-Process|Get-Process|Get-CimInstance|tasklist|Start-Process)\b/i],
  ['explore', /^\s*(cd\s+[^&;]+&&\s*)?(ls|cat|head|tail|find|grep|rg|wc|du|sed\s+-n|tree|stat|file|echo|pwd|which)\b/],
];
function toolKind(name, input) {
  if (name === 'Bash' || name === 'PowerShell') {
    const cmd = String(input?.command ?? '');
    for (const [k, re] of BASH_KINDS) if (re.test(cmd)) return `${name}:${k}`;
    return `${name}:other`;
  }
  if (name.startsWith('mcp__')) {
    const [, server, tool] = name.split('__');
    return `mcp:${server}:${tool}`;
  }
  return name;
}
const toolGroup = (kind) => (kind.startsWith('mcp:') ? kind.split(':').slice(0, 2).join(':') : kind);
const isUserWaitTool = (name) => name === 'AskUserQuestion' || name === 'ExitPlanMode';
// 許可待ち以外で、これを超えて返らなかった呼び出しは「停滞」として実行時間から外す。
// CLAUDE.md の「1 回の待機は 5 分以内」に対して 6 倍で、ルールどおりの待ち方なら到達しない長さ。
// 2026-09-29 の実測で 30〜60 分に入ったのは Unity の完了待ちループと、背面の Unity での AssetDatabase.Refresh（どちらも実際の停滞）
const STALL_MS = 30 * 60 * 1000;

// 許可を求められたコマンドを、何が引っかかったかで束ねる
function permFeature(c) {
  const hits = [];
  if (/\brm\s+-[a-z]*r/i.test(c)) hits.push('rm -r');
  if (/\bgit\s+push\b/.test(c)) hits.push('git push');
  if (/\.claude[\\/]/.test(c) && /(>|tee|\bcp\b|\bmv\b|sed -i)/.test(c)) hits.push('.claude への書き込み');
  if (/\b(curl|wget)\b/.test(c)) hits.push('curl');
  if (/Start-Process|taskkill|Stop-Process|\bkill\b/i.test(c)) hits.push('プロセス操作');
  if (/\bgit\s+(reset|checkout|clean|rebase|restore)\b/.test(c)) hits.push('git の書き戻し');
  if (/^(Read|Edit|Write|MultiEdit|Grep|Glob|NotebookEdit) /.test(c)) hits.push(`${c.split(' ')[0]}${/[\\/]\.claude[\\/]/.test(c) ? '（.claude 配下）' : ''}`);
  return hits.length ? hits.join(' + ') : 'その他';
}

// ─── 集計の器 ───────────────────────────────────────
const S = {
  sessions: 0,
  turns: 0,
  turnMs: 0,
  phases: { model: 0, tool: 0, userWait: 0, permWait: 0, stall: 0 },
  perm: [], // 許可ダイアログで止まっていた Bash {ms, cmd, project}
  stalls: [], // 30 分を超えて返らなかったツール（許可待ち以外）
  byTool: new Map(), // kind -> {n, ms, err}
  byProject: new Map(), // project -> {turnMs, turns, sessions, toolMs, modelMs}
  slow: [], // {ms, kind, detail, project, ts}
  errors: { n: 0, retried: 0, hookBlocked: 0, denied: 0, timeout: 0, msWasted: 0 },
  requests: [], // {inTok, outTok, ms}
  compactions: 0,
  queued: 0,
  warmup: [], // 最初の Edit/Write までのツール回数
  errSamples: new Map(), // kind -> [sample]
};
const bump = (map, key, init) => {
  if (!map.has(key)) map.set(key, init());
  return map.get(key);
};

// ─── 1 セッション分を読む ───────────────────────────
async function readSession(file, project) {
  const rl = readline.createInterface({ input: fs.createReadStream(file, { encoding: 'utf8' }), crlfDelay: Infinity });
  const recs = [];
  for await (const line of rl) {
    if (!line) continue;
    let o;
    try {
      o = JSON.parse(line);
    } catch {
      continue;
    }
    if (o.isSidechain) continue;
    const ts = o.timestamp ? Date.parse(o.timestamp) : NaN;
    if (o.type === 'queue-operation' && o.operation === 'enqueue') S.queued++;
    if (o.type === 'system' && o.subtype === 'compact_boundary') S.compactions++;
    if (Number.isNaN(ts)) continue;
    recs.push({ o, ts });
  }
  if (!recs.length) return;
  if (recs[recs.length - 1].ts < since) return;
  recs.sort((a, b) => a.ts - b.ts);

  const proj = bump(S.byProject, project, () => ({ turnMs: 0, turns: 0, sessions: 0, toolMs: 0, modelMs: 0, userWaitMs: 0, permWaitMs: 0 }));
  proj.sessions++;
  S.sessions++;

  const pending = new Map(); // tool_use id -> {ts, kind, name, input}
  let lastInputTs = null; // モデルに渡した直近の入力（依頼・ツール結果）の時刻
  const reqSeen = new Map(); // requestId -> {start, end, inTok, outTok}
  let prevErr = null; // 直前に失敗したツール {kind, key}
  let toolCalls = 0;
  let warmupDone = false;

  for (const { o, ts } of recs) {
    if (ts < since) continue;
    if (o.type === 'system' && o.subtype === 'turn_duration') {
      S.turns++;
      S.turnMs += o.durationMs;
      proj.turns++;
      proj.turnMs += o.durationMs;
      continue;
    }
    if (o.type === 'user') {
      const content = o.message?.content;
      if (typeof content === 'string' || (Array.isArray(content) && content.some((c) => c.type === 'text'))) {
        lastInputTs = ts;
        continue;
      }
      if (!Array.isArray(content)) continue;
      for (const c of content) {
        if (c.type !== 'tool_result') continue;
        lastInputTs = ts;
        const p = pending.get(c.tool_use_id);
        if (!p) continue;
        pending.delete(c.tool_use_id);
        const ms = Math.max(0, ts - p.ts);
        const t = bump(S.byTool, p.kind, () => ({ n: 0, ms: 0, err: 0 }));
        t.n++;
        const isShell = p.name === 'Bash' || p.name === 'PowerShell';
        // 実行時間に上限があるツールで、上限を超えて返ってきたものは、実行前に許可ダイアログで止まっていた。
        //   Bash / PowerShell: タイムアウト（既定 2 分）を超えられない。余裕の 30 秒はタイムアウト後の後始末と記録の書き込みの遅れ分
        //   ファイル操作（Read/Edit/Write/Grep/Glob）: 実行は 1 秒未満（この集計の平均 0.1〜0.2 秒）。60 秒を超えたら確認待ち
        //   （.claude/ 配下の編集など、許可ルールで確認が出るもの）
        const FAST_TOOLS = ['Read', 'Edit', 'Write', 'MultiEdit', 'Grep', 'Glob', 'NotebookEdit'];
        const limit = isShell ? (p.input?.timeout ?? 120000) + 30000 : FAST_TOOLS.includes(p.name) ? 60000 : Infinity;
        if (isUserWaitTool(p.name)) {
          t.ms += ms;
          S.phases.userWait += ms;
          proj.userWaitMs += ms;
        } else if (!p.input?.run_in_background && ms > limit) {
          S.phases.permWait += ms;
          proj.permWaitMs += ms;
          const cmd = isShell ? String(p.input?.command ?? '') : `${p.name} ${p.input?.file_path ?? p.input?.pattern ?? ''}`;
          S.perm.push({ ms, over: ms - limit, cmd: cmd.replace(/\s+/g, ' '), project });
        } else if (ms > STALL_MS) {
          S.phases.stall += ms;
          S.stalls.push({ ms, kind: p.kind, detail: JSON.stringify(p.input).slice(0, 110), project });
        } else {
          t.ms += ms;
        }
        const text = typeof c.content === 'string' ? c.content : JSON.stringify(c.content ?? '');
        const key = `${p.name}:${JSON.stringify(p.input).slice(0, 200)}`;
        if (c.is_error) {
          t.err++;
          S.errors.n++;
          S.errors.msWasted += ms;
          if (/hook/i.test(text) && /(deny|denied|blocked|error)/i.test(text)) S.errors.hookBlocked++;
          if (/doesn't want to proceed|was rejected|permission.*denied|user denied/i.test(text)) S.errors.denied++;
          if (/timed? ?out|exit code 124|ETIMEDOUT/i.test(text)) S.errors.timeout++;
          const samples = bump(S.errSamples, toolGroup(p.kind), () => []);
          if (samples.length < 3) samples.push(text.replace(/\s+/g, ' ').slice(0, 140));
          prevErr = { kind: p.kind, key };
        } else if (prevErr && prevErr.kind === p.kind) {
          S.errors.retried++; // 失敗の直後に同じ種類のツールで成功 = やり直し
          prevErr = null;
        } else {
          prevErr = null;
        }
        const detail = p.name === 'Bash' || p.name === 'PowerShell' ? p.input?.command : p.name === 'Agent' ? p.input?.description : JSON.stringify(p.input).slice(0, 120);
        S.slow.push({ ms, kind: p.kind, detail: String(detail ?? '').replace(/\s+/g, ' ').slice(0, 110), project, ts, file, id: c.tool_use_id, startTs: p.ts });
      }
      continue;
    }
    if (o.type === 'assistant') {
      const rid = o.requestId ?? o.message?.id;
      const u = o.message?.usage ?? {};
      if (!reqSeen.has(rid)) {
        const inTok = (u.input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0);
        reqSeen.set(rid, { start: lastInputTs ?? ts, end: ts, inTok, outTok: u.output_tokens ?? 0 });
      } else {
        const r = reqSeen.get(rid);
        r.end = ts;
        r.outTok = Math.max(r.outTok, u.output_tokens ?? 0);
      }
      for (const c of o.message?.content ?? []) {
        if (c.type !== 'tool_use') continue;
        const kind = toolKind(c.name, c.input);
        pending.set(c.id, { ts, kind, name: c.name, input: c.input });
        toolCalls++;
        if (!warmupDone && ['Edit', 'Write', 'MultiEdit', 'NotebookEdit'].includes(c.name)) {
          S.warmup.push(toolCalls - 1);
          warmupDone = true;
        }
      }
    }
  }

  // モデルの時間: 応答ごとに「入力が揃ってから、最後のブロックを書き終えるまで」
  for (const r of reqSeen.values()) {
    const ms = Math.max(0, r.end - r.start);
    if (ms > 30 * 60 * 1000) continue; // 30 分超は、入力の後にユーザーが離席していたもの（応答時間ではない）
    S.phases.model += ms;
    proj.modelMs += ms;
    S.requests.push({ inTok: r.inTok, outTok: r.outTok, ms });
  }
}

// ─── 走査 ───────────────────────────────────────────
const files = [];
for (const p of fs.readdirSync(root)) {
  if (projectFilter && !p.toLowerCase().includes(projectFilter.toLowerCase())) continue;
  const d = path.join(root, p);
  let entries;
  try {
    entries = fs.readdirSync(d);
  } catch {
    continue;
  }
  for (const f of entries) if (f.endsWith('.jsonl')) files.push({ file: path.join(d, f), project: p.replace(/^[A-Z]---/, '').replace(/^(Personal|ProjectBLUE)-Project-+/, '') });
}
const t0 = Date.now();
for (const { file, project } of files) {
  try {
    if (fs.statSync(file).mtimeMs < since) continue;
    await readSession(file, project);
  } catch (e) {
    console.error(`skip ${file}: ${e.message}`);
  }
}
for (const [kind, t] of S.byTool) if (!isUserWaitTool(kind)) S.phases.tool += t.ms;

// ─── 出力 ───────────────────────────────────────────
const h = (ms) => (ms >= 3600e3 ? `${(ms / 3600e3).toFixed(1)}h` : ms >= 60e3 ? `${(ms / 60e3).toFixed(1)}m` : `${(ms / 1e3).toFixed(1)}s`);
const pct = (a, b) => (b ? `${((a / b) * 100).toFixed(0)}%` : '-');
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
};
const out = [];
const w = (s = '') => out.push(s);

w(`# Claude Code 作業時間の内訳`);
w(`対象: ${files.length} 記録中 ${S.sessions} セッション / ${S.turns} 依頼${opt('since') ? `（${opt('since')} 以降）` : ''}。集計 ${h(Date.now() - t0)}`);
w();
w(`## 全体`);
const phaseSum = S.phases.model + S.phases.tool + S.phases.userWait + S.phases.permWait + S.phases.stall;
w(`| 項目 | 時間 | 割合 |`);
w(`|---|---|---|`);
w(`| Claude が動いていた時間（依頼の合計） | ${h(S.turnMs)} | |`);
w(`| モデル（考えて書いている） | ${h(S.phases.model)} | ${pct(S.phases.model, phaseSum)} |`);
w(`| ツール実行（並列の重なりを含む） | ${h(S.phases.tool)} | ${pct(S.phases.tool, phaseSum)} |`);
w(`| ユーザー待ち（質問・計画の承認） | ${h(S.phases.userWait)} | ${pct(S.phases.userWait, phaseSum)} |`);
w(`| 許可ダイアログ待ち（Bash がタイムアウトを超えて返ったもの） | ${h(S.phases.permWait)} | ${pct(S.phases.permWait, phaseSum)} |`);
w(`| 停滞（許可待ち以外で 30 分超） | ${h(S.phases.stall)} | ${pct(S.phases.stall, phaseSum)} |`);
w(`| 1 依頼あたり（中央値ではなく平均） | ${h(S.turnMs / Math.max(1, S.turns))} | |`);
w(`| 作業中に積まれた追加の依頼 | ${S.queued} 件 | |`);
w(`| context の圧縮（compact） | ${S.compactions} 回 | |`);
w();

w(`## ツール別（時間の多い順、上位 30）`);
w(`| ツール | 回数 | 合計 | 平均 | 失敗 |`);
w(`|---|---|---|---|---|`);
const groups = new Map();
for (const [kind, t] of S.byTool) {
  const g = bump(groups, toolGroup(kind), () => ({ n: 0, ms: 0, err: 0 }));
  g.n += t.n;
  g.ms += t.ms;
  g.err += t.err;
}
for (const [k, t] of [...groups].sort((a, b) => b[1].ms - a[1].ms).slice(0, 30)) {
  w(`| ${k} | ${t.n} | ${h(t.ms)} | ${h(t.ms / t.n)} | ${t.err ? `${t.err}（${pct(t.err, t.n)}）` : ''} |`);
}
w();

w(`## MCP のツール別（上位 15）`);
w(`| ツール | 回数 | 合計 | 平均 | 失敗 |`);
w(`|---|---|---|---|---|`);
for (const [k, t] of [...S.byTool].filter(([k]) => k.startsWith('mcp:')).sort((a, b) => b[1].ms - a[1].ms).slice(0, 15)) {
  w(`| ${k.replace(/^mcp:/, '')} | ${t.n} | ${h(t.ms)} | ${h(t.ms / t.n)} | ${t.err || ''} |`);
}
w();

w(`## 許可ダイアログで止まっていたコマンド（${S.perm.length} 件）`);
if (S.perm.length) {
  const overs = S.perm.map((r) => r.over).sort((a, b) => a - b);
  w(`判定の境界（上限）からの超過: 最小 ${h(overs[0])} / 中央値 ${h(overs[Math.floor(overs.length / 2)])}（境界付近に集まっていれば、判定が実行の遅いものを拾っている疑い）`);
}
w(`| 引っかかったもの | 件数 | 止まっていた時間 | 例 |`);
w(`|---|---|---|---|`);
const permBy = new Map();
for (const r of S.perm) {
  const b = bump(permBy, permFeature(r.cmd), () => ({ n: 0, ms: 0, ex: '' }));
  b.n++;
  b.ms += r.ms;
  if (!b.ex) b.ex = `${r.project}: ${r.cmd.slice(0, 80)}`;
}
for (const [k, b] of [...permBy].sort((a, b) => b[1].ms - a[1].ms)) w(`| ${k} | ${b.n} | ${h(b.ms)} | ${b.ex.replace(/\|/g, '\\|')} |`);
w();
if (S.stalls.length) {
  w(`## 停滞（許可待ち以外で 30 分を超えて返らなかった呼び出し）`);
  for (const s of S.stalls.sort((a, b) => b.ms - a.ms).slice(0, 10)) w(`- ${h(s.ms)} ${s.kind}（${s.project}）${s.detail}`);
  w();
}

w(`## 失敗`);
w(`- 失敗したツール呼び出し: ${S.errors.n} 回（その呼び出しに使った時間 ${h(S.errors.msWasted)}）`);
w(`- 失敗の直後に同じ種類のツールでやり直した: ${S.errors.retried} 回`);
w(`- hook に止められた: ${S.errors.hookBlocked} 回 / 許可で拒否された: ${S.errors.denied} 回 / タイムアウト: ${S.errors.timeout} 回`);
w(`- 失敗の例（ツール別に最大 3 件）:`);
for (const [k, xs] of [...S.errSamples].sort((a, b) => (groups.get(b[0])?.err ?? 0) - (groups.get(a[0])?.err ?? 0)).slice(0, 8)) {
  w(`  - ${k}: ${xs.map((x) => `「${x}」`).join(' / ')}`);
}
w();

w(`## 読ませる量と応答時間`);
const bands = [[0, 30e3], [30e3, 60e3], [60e3, 100e3], [100e3, 200e3], [200e3, 400e3], [400e3, Infinity]];
w(`| 入力トークン | 応答数 | 応答時間の中央値 | 出力トークンの中央値 | 1k 出力あたりの時間 |`);
w(`|---|---|---|---|---|`);
for (const [lo, hi] of bands) {
  const xs = S.requests.filter((r) => r.inTok >= lo && r.inTok < hi);
  if (!xs.length) continue;
  const perK = median(xs.filter((r) => r.outTok > 50).map((r) => r.ms / (r.outTok / 1000)));
  w(`| ${lo / 1000}k〜${hi === Infinity ? '' : `${hi / 1000}k`} | ${xs.length} | ${h(median(xs.map((r) => r.ms)))} | ${median(xs.map((r) => r.outTok))} | ${h(perK)} |`);
}
w(`- 応答 1 回の入力の中央値: ${Math.round(median(S.requests.map((r) => r.inTok)) / 1000)}k トークン`);
w();

w(`## セッション冒頭の調べ物`);
w(`- 最初に編集するまでのツール呼び出し回数: 中央値 ${median(S.warmup)} 回 / 平均 ${(S.warmup.reduce((a, b) => a + b, 0) / Math.max(1, S.warmup.length)).toFixed(1)} 回（${S.warmup.length} セッション）`);
w();

w(`## プロジェクト別（Claude が動いていた時間の多い順、上位 15）`);
w(`| プロジェクト | セッション | 依頼 | 動いていた時間 | モデル | ユーザー待ち | 許可待ち |`);
w(`|---|---|---|---|---|---|---|`);
for (const [k, p] of [...S.byProject].sort((a, b) => b[1].turnMs - a[1].turnMs).slice(0, 15)) {
  w(`| ${k} | ${p.sessions} | ${p.turns} | ${h(p.turnMs)} | ${h(p.modelMs)} | ${h(p.userWaitMs)} | ${h(p.permWaitMs)} |`);
}
w();

w(`## 遅かったツール呼び出し（上位 25。ユーザー待ちを除く）`);
w(`| 時間 | 種類 | 内容 | プロジェクト |`);
w(`|---|---|---|---|`);
for (const s of S.slow.filter((s) => !/AskUserQuestion|ExitPlanMode/.test(s.kind) && s.ms <= STALL_MS && !S.perm.some((r) => r.ms === s.ms)).sort((a, b) => b.ms - a.ms).slice(0, 25)) {
  w(`| ${h(s.ms)} | ${s.kind} | ${s.detail.replace(/\|/g, '\\|')} | ${s.project} |`);
}

const text = out.join('\n');
if (outFile) fs.writeFileSync(outFile, text);
// 掘り下げ用: 遅かった呼び出しを、記録ファイルとツール ID 付きで JSON に出す
if (opt('json')) fs.writeFileSync(opt('json'), JSON.stringify(S.slow.sort((a, b) => b.ms - a.ms).slice(0, 200), null, 1));
process.stdout.write(text + '\n');
