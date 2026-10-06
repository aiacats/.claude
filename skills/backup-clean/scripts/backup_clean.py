"""バックアップ用の git タグ（backup/*・backup-*）を一覧にし、中身が origin に残っているものだけを消す。

使い方:
  python backup_clean.py list    [--repo <path> ... | --root <dir> ...]       一覧（サブモジュールも含む）
  python backup_clean.py delete  --repo <path> <tag> ... [--force]           指定したタグを消す
  python backup_clean.py delete  --repo <path> --covered                      origin に中身が残っているものを全部消す
  python backup_clean.py restore --repo <path> <tag>                          消したタグを記録から戻す

状態:
  pushed     … タグのコミット自体が origin のどれかのブランチから辿れる
  same-tree  … タグと同じツリー（中身）のコミットが origin のどれかのブランチにある（まとめ直し後に push 済み）
  local-only … 中身が手元にしか無い。消すと失われうるので --force のときだけ消す
消したタグは <repo>/.git/backup-clean.log に「日時 タグ ハッシュ」で残し、restore で戻せる。
"""
import datetime
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PATTERN = re.compile(r"^backup[/-]")
# same-tree の照合で origin の各ブランチを遡る数。まとめ直しのバックアップは push 先の先頭近くにあるので、
# 直近の範囲だけ見れば足りる（全履歴のツリーを読むと大きいリポジトリで遅い）
TREE_SEARCH_DEPTH = 300


class GitError(Exception):
    pass


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise GitError(f"[{repo}] git {' '.join(args)} failed: {r.stderr.strip().splitlines()[0] if r.stderr.strip() else r.returncode}")
    return r.stdout.strip()


def submodules(repo):
    out = git(repo, "submodule", "foreach", "--quiet", "--recursive", "echo $toplevel/$sm_path", check=False)
    return [os.path.normpath(p) for p in out.splitlines() if p]


def find_repos(root):
    repos = []
    if os.path.exists(os.path.join(root, ".git")):
        return [root]
    for d1 in sorted(os.listdir(root)):
        p1 = os.path.join(root, d1)
        if not os.path.isdir(p1):
            continue
        if os.path.exists(os.path.join(p1, ".git")):
            repos.append(p1)
            continue
        for d2 in sorted(os.listdir(p1)):
            p2 = os.path.join(p1, d2)
            if os.path.isdir(p2) and os.path.exists(os.path.join(p2, ".git")):
                repos.append(p2)
    return repos


def backup_tags(repo):
    out = git(repo, "for-each-ref", "refs/tags", "--format=%(refname:short)%00%(*objectname)%(objectname)%00%(creatordate:iso8601)")
    tags = []
    for line in out.splitlines():
        name, obj, date = line.split("\x00")
        if PATTERN.match(name):
            commit = git(repo, "rev-parse", f"{name}^{{commit}}")
            tags.append((name, commit, date))
    return tags


def status(repo, commit, remote_trees):
    if git(repo, "branch", "-r", "--contains", commit, check=False):
        return "pushed"
    if git(repo, "rev-parse", f"{commit}^{{tree}}") in remote_trees:
        return "same-tree"
    return "local-only"


def remote_tree_set(repo):
    refs = git(repo, "for-each-ref", "refs/remotes", "--format=%(refname)").split()
    if not refs:
        return set()
    out = git(repo, "log", f"--max-count={TREE_SEARCH_DEPTH}", "--format=%T", *refs, check=False)
    return set(out.split())


def rows_for(repo):
    tags = backup_tags(repo)
    if not tags:
        return []
    trees = remote_tree_set(repo)
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for name, commit, date in tags:
        age = (now - datetime.datetime.fromisoformat(date.replace(" ", "T", 1).replace(" ", ""))).days
        rows.append((name, commit[:9], age, status(repo, commit, trees)))
    return rows


def cmd_list(repos):
    total = 0
    for repo in repos:
        for r in [repo] + submodules(repo):
            try:
                rows = rows_for(r)
            except GitError as e:
                # 開けないリポジトリ（所有者違いの dubious ownership など）は飛ばし、飛ばしたことを出す
                print(f"skip: {e}")
                continue
            if not rows:
                continue
            print(f"== {r}")
            for name, commit, age, st in rows:
                print(f"  {st:10} {age:4}d  {commit}  {name}")
                total += 1
    print(f"backup tags: {total}")


def log_path(repo):
    return os.path.join(git(repo, "rev-parse", "--absolute-git-dir"), "backup-clean.log")


def cmd_delete(repo, names, covered, force):
    rows = {name: (commit, st) for name, commit, _, st in rows_for(repo)}
    if covered:
        names = [n for n, (_, st) in rows.items() if st != "local-only"]
    if not names:
        print("nothing to delete")
        return
    with open(log_path(repo), "a", encoding="utf-8") as log:
        for n in names:
            if n not in rows:
                sys.exit(f"not a backup tag: {n}")
            commit, st = rows[n]
            if st == "local-only" and not force:
                print(f"skip (local-only, use --force): {n}")
                continue
            full = git(repo, "rev-parse", f"{n}^{{commit}}")
            git(repo, "tag", "-d", n)
            log.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {n} {full}\n")
            print(f"deleted {n} ({st}, {full[:9]})")


def cmd_restore(repo, name):
    path = log_path(repo)
    entries = [l.split() for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
    hits = [e for e in entries if e[2] == name]
    if not hits:
        sys.exit(f"no record for {name} in {path}")
    commit = hits[-1][3]
    if git(repo, "cat-file", "-t", commit, check=False) != "commit":
        sys.exit(f"commit {commit} is gone (gc で消えた)")
    git(repo, "tag", name, commit)
    print(f"restored {name} -> {commit[:9]}")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args.pop(0)
    repos, roots, rest = [], [], []
    force = "--force" in args
    covered = "--covered" in args
    args = [a for a in args if a not in ("--force", "--covered")]
    while args:
        a = args.pop(0)
        if a == "--repo":
            repos.append(os.path.normpath(args.pop(0)))
        elif a == "--root":
            roots.append(args.pop(0))
        else:
            rest.append(a)
    for r in roots:
        repos.extend(find_repos(r))
    if not repos:
        repos = [os.getcwd()]
    try:
        if cmd == "list":
            cmd_list(repos)
        elif cmd == "delete" and len(repos) == 1 and (rest or covered):
            cmd_delete(repos[0], rest, covered, force)
        elif cmd == "restore" and len(repos) == 1 and len(rest) == 1:
            cmd_restore(repos[0], rest[0])
        else:
            sys.exit(__doc__)
    except GitError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
