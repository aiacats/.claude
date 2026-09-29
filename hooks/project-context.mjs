// SessionStart hook: プロジェクトの種別を見分けて、その種別の作業方針（project-types/*.md）を差し込む。
// rules/ に置くと全セッションで読まれてしまうため、種別で絞るものはここから入れる。
// hook の出力は 10,000 文字を超えると先頭 2,000 文字の preview に切られる（公式仕様）。
// 各ファイルはその上限に収める（test-hooks.mjs が検査する）。

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
const cwd = input.cwd || process.cwd();
const typesDir = path.join(os.homedir(), '.claude', 'project-types');

const exists = (...p) => fs.existsSync(path.join(cwd, ...p));

// Unity はルートか 1 階層下に ProjectSettings を持つ（リポジトリ直下に Unity プロジェクトを置く構成があるため）
function isUnity() {
  if (exists('ProjectSettings', 'ProjectVersion.txt')) return true;
  try {
    return fs
      .readdirSync(cwd, { withFileTypes: true })
      .some((d) => d.isDirectory() && exists(d.name, 'ProjectSettings', 'ProjectVersion.txt'));
  } catch {
    return false;
  }
}
const isApp = () => exists('package.json') || exists('src-tauri');

const types = [];
if (isUnity()) types.push('unity');
if (isApp()) types.push('app');

// 2 つ同時（Unity と Node を同居させたリポジトリ）でも、それぞれ別の出力にはできないので 1 つにまとめる。
// その場合に上限を超えないよう、片方だけの時より短い案内に切り替える。
const bodies = types.map((t) => fs.readFileSync(path.join(typesDir, `${t}.md`), 'utf8'));
const joined = bodies.join('\n\n---\n\n');
const LIMIT = 10000;
if (joined.length <= LIMIT) {
  process.stdout.write(joined);
} else if (types.length) {
  process.stdout.write(
    `このプロジェクトは ${types.join(' と ')} の両方に当たる。作業方針が上限を超えるため全文を差し込めない。` +
      `作業の前に次を Read で読むこと:\n${types.map((t) => `- ${path.join(typesDir, `${t}.md`)}`).join('\n')}`,
  );
}
