// PreToolUse hook（Bash）: 再帰削除（rm -r / -rf / -fr / -R / --recursive）の対象を確かめ、
// 一時フォルダ（%TEMP% 配下）の中だと断定できないものだけ、確認ダイアログを出す（permissionDecision: ask）。
//
// なぜ: 以前は settings.json の permissions.ask に `rm -r` を入れていたため、scratchpad の一時ファイルを消すだけでも
// 毎回確認が出て、席を外している間は何時間も止まっていた（2026-09-29 の集計で 47 件・46 時間。tools/session-stats.mjs）。
//
// allow は返さない。allow はコマンド全体の許可判定（auto mode の安全判定を含む）を飛ばすので、
// `rm -rf "$S/x" && <危険なもの>` の後半まで素通りさせてしまう。ここは「確認を足す」側にだけ働く。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
if (input.tool_name !== 'Bash') process.exit(0);
const command = String(input.tool_input?.command ?? '');
if (!/\brm\b/.test(command)) process.exit(0);

const norm = (p) => p.replace(/\\/g, '/').replace(/\/+$/, '');
const home = norm(os.homedir());
// 一時フォルダ。Claude の scratchpad（%TEMP%/claude/...）もここに入る
const SAFE_ROOTS = [norm(process.env.TEMP || process.env.TMP || os.tmpdir())].map((r) => r.toLowerCase());

// ─── シェルの字句解析（引用符・エスケープ・区切り） ───
// 戻り値: サブコマンドの配列。各サブコマンドはトークン配列 [{text, quoted, raw}]
function splitCommands(src) {
  const cmds = [];
  let tokens = [];
  let cur = '';
  let raw = '';
  let quoted = false;
  let started = false;
  const pushTok = () => {
    if (started) tokens.push({ text: cur, quoted, raw });
    cur = '';
    raw = '';
    quoted = false;
    started = false;
  };
  const pushCmd = () => {
    pushTok();
    if (tokens.length) cmds.push(tokens);
    tokens = [];
  };
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === "'") {
      const j = src.indexOf("'", i + 1);
      const end = j < 0 ? src.length : j;
      cur += src.slice(i + 1, end);
      raw += src.slice(i, end + 1);
      quoted = started = true;
      i = end;
    } else if (c === '"') {
      let j = i + 1;
      let s = '';
      while (j < src.length && src[j] !== '"') {
        if (src[j] === '\\' && j + 1 < src.length && '"\\$`'.includes(src[j + 1])) {
          s += src[j + 1];
          j += 2;
        } else s += src[j++];
      }
      cur += s;
      raw += src.slice(i, j + 1);
      quoted = started = true;
      i = j;
    } else if (c === '\\' && i + 1 < src.length) {
      cur += src[i + 1];
      raw += src.slice(i, i + 2);
      started = true;
      i++;
    } else if (c === ' ' || c === '\t') {
      pushTok();
    } else if (c === '\n' || c === ';' || c === '|' || c === '&' || c === '(' || c === ')') {
      pushCmd();
    } else {
      cur += c;
      raw += c;
      started = true;
    }
  }
  pushCmd();
  return cmds;
}

// ─── 変数の展開 ───
// 同じコマンドの中で前に代入された VAR=値 と、既知の環境変数だけを展開する。それ以外（$(...)、未知の変数）は展開できない = null
const vars = {
  HOME: home,
  USERPROFILE: home,
  TEMP: SAFE_ROOTS[0],
  TMP: SAFE_ROOTS[0],
  TMPDIR: SAFE_ROOTS[0],
  LOCALAPPDATA: norm(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')),
};
function expand(tok) {
  let t = tok.text;
  if (/\$\(|`/.test(tok.raw)) return null;
  if (!tok.quoted && t.startsWith('~')) t = home + t.slice(1);
  let failed = false;
  t = t.replace(/\$\{(\w+)\}|\$(\w+)/g, (_, a, b) => {
    const v = vars[a || b];
    if (v === undefined) failed = true;
    return v ?? '';
  });
  return failed ? null : t;
}

// Git Bash の /c/... と /tmp を Windows のパスへ
function toWin(p) {
  p = norm(p);
  const m = p.match(/^\/([a-zA-Z])(\/.*)?$/);
  if (m) return `${m[1].toUpperCase()}:${m[2] ?? '/'}`;
  if (p === '/tmp' || p.startsWith('/tmp/')) return SAFE_ROOTS[0] + p.slice(4);
  return p;
}

// ─── 判定 ───
function isRecursiveRm(tokens) {
  if (!tokens.length || tokens[0].text !== 'rm') return false;
  return tokens.slice(1).some((t) => !t.quoted && (/^-[a-zA-Z]*[rR]/.test(t.text) || t.text === '--recursive'));
}

// 対象が一時フォルダの「中」（ルートそのものや、ルート直下の全消しではない）と断定できれば null、できなければ理由
function unsafeReason(target, cwd) {
  if (target === null) return '対象に展開できない変数・コマンド置換がある';
  let p = toWin(target);
  if (!/^[a-zA-Z]:\//.test(p)) {
    if (!cwd) return `相対パス（${target}）で、作業フォルダが分からない`;
    p = `${cwd}/${p}`;
  }
  // グロブは最初のワイルドカードより前の部分で判定する（その部分がルートより深くないと、ルート配下を丸ごと消しうる）
  const globAt = p.search(/[*?[]/);
  const fixed = globAt >= 0 ? p.slice(0, p.lastIndexOf('/', globAt)) : p;
  const resolved = norm(path.posix.normalize(fixed.replace(/^([a-zA-Z]):/, '/$1:')).replace(/^\/([a-zA-Z]:)/, '$1')).toLowerCase();
  if (resolved.split('/').includes('..')) return `親ディレクトリ参照を含む（${target}）`;
  const root = SAFE_ROOTS.find((r) => resolved === r || resolved.startsWith(r + '/'));
  if (!root) return `一時フォルダの外（${target}）`;
  if (resolved === root) return `一時フォルダそのもの（${target}）`;
  return null;
}

const reasons = [];
let cwd = input.cwd ? toWin(input.cwd) : null;
for (const tokens of splitCommands(command)) {
  // 先頭の VAR=値 を記録（`S="..." rm -rf "$S/x"` も `S=...; rm ...` も拾う）
  let i = 0;
  while (i < tokens.length && /^[A-Za-z_]\w*=/.test(tokens[i].raw)) {
    const eq = tokens[i].text.indexOf('=');
    const v = expand({ ...tokens[i], text: tokens[i].text.slice(eq + 1), raw: tokens[i].raw.slice(tokens[i].raw.indexOf('=') + 1) });
    vars[tokens[i].text.slice(0, eq)] = v === null ? undefined : norm(toWin(v));
    i++;
  }
  const rest = tokens.slice(i);
  if (rest[0]?.text === 'export') continue;
  if (rest[0]?.text === 'cd') {
    const d = rest[1] ? expand(rest[1]) : home;
    const w = d === null ? null : toWin(d);
    cwd = w === null ? null : /^[a-zA-Z]:\//.test(w) ? w : cwd ? `${cwd}/${w}` : null;
    continue;
  }
  // find -exec rm / xargs rm は対象を静的に決められない
  if ((rest[0]?.text === 'find' || rest[0]?.text === 'xargs') && rest.some((t) => t.text === 'rm')) {
    if (rest.some((t) => /^-[a-zA-Z]*[rR]/.test(t.text))) reasons.push(`${rest[0].text} 経由の再帰削除は対象を確かめられない`);
    continue;
  }
  if (!isRecursiveRm(rest)) continue;
  let endOfOpts = false;
  const targets = [];
  for (const t of rest.slice(1)) {
    if (!endOfOpts && !t.quoted && t.text === '--') {
      endOfOpts = true;
      continue;
    }
    if (!endOfOpts && !t.quoted && t.text.startsWith('-')) continue;
    if (/^[0-9]*[<>]/.test(t.raw) || t.raw === '/dev/null') continue; // リダイレクト
    targets.push(expand(t));
  }
  for (const t of targets) {
    const r = unsafeReason(t, cwd);
    if (r) reasons.push(r);
  }
}

if (reasons.length === 0) process.exit(0);
process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'ask',
      permissionDecisionReason: `再帰削除の確認: ${[...new Set(reasons)].join(' / ')}`,
    },
  }),
);
