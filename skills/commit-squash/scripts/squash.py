"""未 push のコミットを、作業ごとのまとまりへまとめ直す（push 前の整理）。

使い方:
  python squash.py list  [--repo <path>]                  未 push のコミット・触ったファイル・種別を出し、計画の雛形 JSON を書く
  python squash.py apply <plan.json> [--repo <path>]       計画どおりにまとめる（バックアップのタグを打ってから）
  python squash.py undo  <tag> [--repo <path>]             まとめる前（タグ）へ戻す

計画（plan.json）:
  {"groups": [{"commits": ["8accaa6", "a216192"], "message": "1 行目\\n\\n本文"}, ...]}
  - 未 push のコミットを、どれか 1 つのグループにちょうど 1 回ずつ入れる。
  - グループは、元の並びで連続したコミットだけにできる（並べ替えは衝突しうるので扱わない）。
  - message の代わりに "message_file" でファイルを指してもよい。

仕組み:
  各グループの最後のコミットのツリーを、そのまま新しいコミットのツリーにする（git commit-tree）。
  中身を作り直さないので衝突は起きず、最後のツリーは元の HEAD と必ず同じになる（作ったあとに照合する）。
  ブランチは update-ref で付け替えるだけなので、作業ツリー・index の未コミットの変更には触れない。
"""
import datetime
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")  # sys.exit(<文字列>) は stderr へ出る。既定の cp932 だと呼び出し側で化ける


def git(*args, repo, input_text=None, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8",
                       input=input_text)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def category(path: str) -> str:
    """コミットを分ける粒度（コード / README / ドキュメント / claudeLog）。"""
    low = path.lower()
    if low.endswith("claudelog.txt") or low.startswith("log/"):
        return "log"
    if os.path.basename(low).startswith("readme"):
        return "readme"
    if low.startswith("docs/") or low.endswith(".md"):
        return "docs"
    return "code"


def unpushed(repo):
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", repo=repo, check=False)
    if not upstream:
        sys.exit("upstream が設定されていない（git branch -u origin/<branch>）")
    merges = git("rev-list", "--merges", f"{upstream}..HEAD", repo=repo)
    if merges:
        sys.exit(f"未 push の範囲にマージコミットがある: {merges.split()}（このスクリプトでは扱わない）")
    commits = git("rev-list", "--reverse", f"{upstream}..HEAD", repo=repo).split()
    return upstream, commits


def cmd_list(repo):
    upstream, commits = unpushed(repo)
    branch = git("rev-parse", "--abbrev-ref", "HEAD", repo=repo)
    behind = git("rev-list", "--count", f"HEAD..{upstream}", repo=repo)
    print(f"branch {branch} / upstream {upstream} / ahead {len(commits)} / behind {behind}")
    groups = []
    for c in commits:
        short = git("rev-parse", "--short", c, repo=repo)
        subject = git("log", "-1", "--format=%s", c, repo=repo)
        files = [f for f in git("show", "--name-only", "--format=", c, repo=repo).splitlines() if f]
        cats = sorted({category(f) for f in files})
        print(f"{short} [{','.join(cats)}] {subject}")
        for f in files[:8]:
            print(f"    {f}")
        if len(files) > 8:
            print(f"    ... {len(files) - 8} more")
        groups.append({"commits": [short], "message": git("log", "-1", "--format=%B", c, repo=repo)})
    status = git("status", "--porcelain", repo=repo)
    if status:
        print(f"未コミットの変更 {len(status.splitlines())} 件（まとめ直しでは触らない）")
    plan_path = os.path.join(repo, ".git", "squash-plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump({"groups": groups}, f, ensure_ascii=False, indent=2)
    print(f"plan template: {plan_path}")


def cmd_apply(repo, plan_path):
    upstream, commits = unpushed(repo)
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    full = {git("rev-parse", c, repo=repo): i for i, c in enumerate(commits)}
    order = []
    for g in plan["groups"]:
        ids = [git("rev-parse", c, repo=repo) for c in g["commits"]]
        idx = [full.get(i) for i in ids]
        if None in idx:
            sys.exit(f"未 push の範囲に無いコミット: {g['commits']}")
        if idx != list(range(idx[0], idx[0] + len(idx))):
            sys.exit(f"グループが連続していない（元の並びで隣り合うコミットだけまとめられる）: {g['commits']}")
        order.extend(idx)
        if "message_file" in g:
            with open(g["message_file"], encoding="utf-8") as mf:
                g["message"] = mf.read()
        if not g.get("message", "").strip():
            sys.exit(f"メッセージが空: {g['commits']}")
        cats = {category(p) for c in ids for p in git("show", "--name-only", "--format=", c, repo=repo).splitlines() if p}
        if len(cats) > 1:
            print(f"warning: 種別が混ざっている {sorted(cats)}: {g['commits']}（コード / README / ドキュメント / claudeLog は分ける）")
    if order != list(range(len(commits))):
        sys.exit("未 push のコミットを、どれか 1 つのグループにちょうど 1 回ずつ、元の順で入れる")

    head = git("rev-parse", "HEAD", repo=repo)
    branch = git("symbolic-ref", "HEAD", repo=repo)
    tag = "backup/squash-" + datetime.datetime.now().strftime("%y%m%d-%H%M%S")
    git("tag", tag, head, repo=repo)

    parent = git("rev-parse", upstream, repo=repo)
    for g in plan["groups"]:
        last = git("rev-parse", g["commits"][-1], repo=repo)
        tree = git("rev-parse", f"{last}^{{tree}}", repo=repo)
        # 作者・日時は、グループの最後のコミットのものを引き継ぐ
        env_fmt = git("log", "-1", "--format=%an%x00%ae%x00%aI", last, repo=repo).split("\x00")
        env = dict(os.environ, GIT_AUTHOR_NAME=env_fmt[0], GIT_AUTHOR_EMAIL=env_fmt[1], GIT_AUTHOR_DATE=env_fmt[2])
        r = subprocess.run(["git", "-C", repo, "commit-tree", tree, "-p", parent, "-F", "-"], capture_output=True,
                           text=True, encoding="utf-8", input=g["message"].rstrip() + "\n", env=env)
        if r.returncode != 0:
            sys.exit(f"commit-tree failed: {r.stderr}")
        parent = r.stdout.strip()

    if git("rev-parse", f"{parent}^{{tree}}", repo=repo) != git("rev-parse", f"{head}^{{tree}}", repo=repo):
        sys.exit(f"まとめた結果のツリーが元の HEAD と違う。ブランチは変えていない（バックアップ {tag}）")
    git("update-ref", "-m", f"squash ({tag})", branch, parent, head, repo=repo)
    print(f"backup tag: {tag}")
    print(git("log", "--format=%h %s", f"{upstream}..HEAD", repo=repo))
    diff = git("diff", "--stat", tag, "HEAD", repo=repo)
    print("tree diff vs backup:", "none" if not diff else diff)


def cmd_undo(repo, tag):
    head = git("rev-parse", "HEAD", repo=repo)
    target = git("rev-parse", tag, repo=repo)
    if git("rev-parse", f"{head}^{{tree}}", repo=repo) != git("rev-parse", f"{target}^{{tree}}", repo=repo):
        sys.exit("HEAD のツリーがタグと違う（まとめた後にコミットを足した）。手で戻す")
    git("update-ref", "-m", f"undo squash ({tag})", git("symbolic-ref", "HEAD", repo=repo), target, head, repo=repo)
    print(f"restored to {tag}")


def main():
    args = sys.argv[1:]
    repo = "."
    if "--repo" in args:
        i = args.index("--repo")
        repo = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    if args[0] == "list":
        cmd_list(repo)
    elif args[0] == "apply" and len(args) == 2:
        cmd_apply(repo, args[1])
    elif args[0] == "undo" and len(args) == 2:
        cmd_undo(repo, args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
