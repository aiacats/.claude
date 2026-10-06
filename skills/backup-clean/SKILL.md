---
name: backup-clean
description: まとめ直し・マージ・リセットの前に打ったバックアップの git タグ（backup/*・backup-*）を一覧にし、中身が origin に残っているものだけを消す。消したタグは記録して戻せる。「バックアップを消して」「バックアップのタグを掃除して」「古い backup タグを整理して」と言われたとき、commit-squash でまとめて push し終えたあと、全プロジェクトのバックアップを棚卸しするときに使う。
---

# バックアップのタグを掃除する

バックアップのタグは `commit-squash` skill（`backup/squash-<日時>`）や、マージ・リセットの前に手で打ったもの
（`backup/master-before-...`、`backup-before-...`）。push が済めば役目を終えるが、手元にしか無い中身を指していることもある。
**中身が origin に残っているものだけを消す**。手元にしか無いものは、ユーザーが明示したときだけ消す。

## 先に読む（踏んだ罠）

- **タグの名前だけで消さない**。「before-squash」でも、まとめた結果を push していなければ中身は手元にしか無い。
  → `scripts/backup_clean.py` が origin との関係で判定する（下の 3 状態）。
- **所有者が Administrators のリポジトリは git が開けない**（`detected dubious ownership`。2026-10-06 に FlowBot・Traddist）。
  → 一覧はそのリポジトリを `skip:` と出して続ける。`safe.directory` を勝手に足さない（設定の変更になる）。報告に飛ばした件数を書く。
- **サブモジュールにもタグがある**（vortex_urp の Submod_RealtimeLiveUtility に `backup/mao-dev2-local-...`）。一覧はサブモジュールも辿る。
- 判定は origin の**取得済み**の状態で行う。古いと push 済みでも `local-only` と出るので、消す前に `git fetch` する。

## 状態

| 状態 | 意味 | 消してよいか |
|---|---|---|
| `pushed` | タグのコミット自体が origin のどれかのブランチから辿れる | よい |
| `same-tree` | タグと同じ中身（ツリー）のコミットが origin にある（まとめ直して push 済み） | よい |
| `local-only` | 中身が手元にしか無い | ユーザーが明示したときだけ（`--force`） |

`same-tree` は origin の各ブランチの直近 300 コミットと照合する（全履歴は大きいリポジトリで遅い。まとめ直しのバックアップは push 先の先頭近くにある）。

## 手順

1. **取得して一覧を出す**
   ```bash
   BC=~/.claude/skills/backup-clean/scripts/backup_clean.py
   git -C <リポジトリ> fetch --quiet          # 判定を最新にする（各リポジトリ。サブモジュールも）
   python "$BC" list --repo <リポジトリ>       # 1 つ
   python "$BC" list --root 'D:\_ProjectBLUE\Project' --root 'D:\_Personal\Project' --repo ~/.claude   # 全プロジェクト
   ```
   出力は「状態・経過日数・コミット・タグ名」。`skip:` は開けなかったリポジトリ。

2. **一覧を見せる**（消す前に必ず。CLAUDE.md「まとめて消す前に一覧を見せる」）。
   `pushed` / `same-tree` と `local-only` を分けて表にし、`local-only` は「消すと戻せなくなりうる」と添える。
   依頼が「消して」で、対象が `pushed` / `same-tree` だけなら、確認を待たずに消してよい。`local-only` を含めるかは選択肢で聞く。

3. **消す**
   ```bash
   python "$BC" delete --repo <リポジトリ> --covered            # pushed と same-tree を全部
   python "$BC" delete --repo <リポジトリ> <タグ> ...            # 指定したものだけ（local-only は skip される）
   python "$BC" delete --repo <リポジトリ> <タグ> --force       # local-only も消す（ユーザーが明示したとき）
   ```
   - バックアップの形（`backup/` か `backup-` で始まる）でないタグは消さない（止まる）。
   - 消したタグは `<.git>/backup-clean.log` に「日時 タグ ハッシュ」で残る。
   - リモートのタグには触れない（バックアップのタグは push しない運用。`commit-squash` 参照）。

4. **戻すとき**: `python "$BC" restore --repo <リポジトリ> <タグ>`。
   コミットが gc で消えていたら戻せない（`local-only` を消したあと、参照が無いまま約 2 週間でありうる）。

5. **報告**: 消したタグ（状態・ハッシュ）、残したタグと理由、飛ばしたリポジトリ。claudeLog に追記する。

## スクリプトのテスト

```bash
python ~/.claude/skills/backup-clean/scripts/test_backup_clean.py
```
使い捨てのリポジトリで、3 状態の判定・`--covered` が local-only を残す・バックアップでないタグは消さない・`--force`・restore を確かめる。
2026-10-06 に、local-only の歯止め・same-tree の判定・名前の形の判定を外すとテストが落ちることを確認済み
（`--covered` の絞り込みを外しても、削除直前の local-only の歯止めが同じものを止めるため動きは変わらない）。
