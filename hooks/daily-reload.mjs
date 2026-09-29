// 日付をまたいだセッションで、グローバルのルールを読み直させる hook。
// CLAUDE.md と rules/ はセッション開始時にしか読まれない。長く開いたままのセッション
// （Remote Control で数日生かすなど）は、その間の更新を知らないまま動き続けるため。
//
//   session-start … 読み込んだ時刻と日付をセッションごとに記録する（startup / resume / clear / compact のすべて）
//   prompt        … 日付が変わって最初の依頼で、記録した時刻より後に更新されたファイルを挙げて Read させる
//
// 全文を hook から差し込まないのは、hook の出力が 10,000 文字を超えると
// 先頭 2,000 文字の preview に切られるため（公式仕様。rules/unity.md で実際に切れていた）。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const mode = process.argv[2];
const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
const sessionId = input.session_id;
if (!sessionId) process.exit(0);

const home = path.join(os.homedir(), '.claude');
const stateDir = path.join(home, 'state', 'rule-sessions');
const stateFile = path.join(stateDir, `${sessionId}.json`);

// 日付は手元の暦で見る（「日をまたいだ」はユーザーの暮らしの時間で判断するため）
const localDate = (ms) => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const now = Date.now();

// 読み込んだ時点のファイル一覧も持つ（後で消されたルールを知らせるため。消えたファイルは mtime では検知できない）
function save(loadedAt) {
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify({ date: localDate(loadedAt), loadedAt, files: globalRuleFiles() }));
}

// 読み直しの対象: グローバルの CLAUDE.md、rules/ 配下の .md すべて、種別ごとの作業方針 project-types/、MCP 用の mcp-context/
function globalRuleFiles() {
  const files = [path.join(home, 'CLAUDE.md')];
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.md')) files.push(p);
    }
  };
  walk(path.join(home, 'rules'));
  walk(path.join(home, 'project-types'));
  walk(path.join(home, 'mcp-context'));
  return files;
}

// paths: 付きのルールは該当ファイルを開くまで、project-types/ は該当する種別のプロジェクトでしか、
// mcp-context/ はその MCP を使うまで読まれていない。どれも読み直しは「今の作業に関係するなら」でよい
function isPathScoped(file) {
  if (['project-types', 'mcp-context'].includes(path.basename(path.dirname(file)))) return true;
  try {
    const head = fs.readFileSync(file, 'utf8').slice(0, 600);
    return /^---\r?\n[\s\S]*?^paths:/m.test(head);
  } catch {
    return false;
  }
}

if (mode === 'session-start') {
  save(now);
  // 古い記録の掃除。30 日 = 1 セッションが生き続ける長さとして十分な上限（月をまたいで開き続けることは無い運用）
  try {
    for (const f of fs.readdirSync(stateDir)) {
      const p = path.join(stateDir, f);
      if (now - fs.statSync(p).mtimeMs > 30 * 24 * 3600 * 1000) fs.unlinkSync(p);
    }
  } catch {}
  process.exit(0);
}

if (mode !== 'prompt') process.exit(0);

let state;
try {
  state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
} catch {
  // この hook を入れる前から続いているセッション。セッション記録（transcript）の最初の timestamp を読み込み時刻とみなす
  // （ファイルの作成時刻はコピーや移動で変わるので使わない）。取れなければ今を読み込み時刻とし、次の日付変更から働く
  let loadedAt = now;
  try {
    const fd = fs.openSync(input.transcript_path, 'r');
    const buf = Buffer.alloc(8192);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    const m = buf.toString('utf8', 0, n).match(/"timestamp"\s*:\s*"([^"]+)"/);
    const t = m ? Date.parse(m[1]) : NaN;
    if (!Number.isNaN(t)) loadedAt = t;
  } catch {}
  state = { date: localDate(loadedAt), loadedAt };
}

if (state.date === localDate(now)) process.exit(0);

const current = globalRuleFiles();
const changed = current.filter((f) => {
  try {
    return fs.statSync(f).mtimeMs > state.loadedAt;
  } catch {
    return false;
  }
});
// 一覧を持たない記録（hook 導入前からのセッション）では、消えたものは分からない
const removed = (state.files ?? []).filter((f) => !current.includes(f));
save(now);
if (changed.length === 0 && removed.length === 0) process.exit(0);

const always = changed.filter((f) => !isPathScoped(f));
const scoped = changed.filter((f) => isPathScoped(f));
const list = (fs_) => fs_.map((f) => `- ${f}`).join('\n');
let msg =
  `日付が変わりました（前回の読み込み: ${new Date(state.loadedAt).toLocaleString('ja-JP')}）。` +
  'その後にグローバルのルールが更新されています。依頼に取りかかる前に、次のファイルを Read で読み直し、' +
  'セッション開始時に読んだ内容と食い違う箇所は新しい方に従ってください。';
if (always.length) msg += `\n\n必ず読み直す:\n${list(always)}`;
if (scoped.length) msg += `\n\n今の作業に関係する分野・種別なら読み直す（paths で絞ったルール、種別ごとの作業方針、MCP 用の罠）:\n${list(scoped)}`;
if (removed.length) msg += `\n\n削除されたルール（セッション開始時に読んだ内容でも、以後は従わない。内容は移動済みのことが多いので CLAUDE.md の置き場所の表を見る）:\n${list(removed)}`;

process.stdout.write(
  JSON.stringify({ hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: msg } }),
);
