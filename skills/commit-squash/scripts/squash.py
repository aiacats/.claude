"""未 push のコミットを、作業ごとのまとまりへまとめ直す（push 前の整理）。

使い方:
  python squash.py list  [--repo <path>]                  未 push のコミット・触ったファイル・種別を出し、計画の雛形 JSON を書く
  python squash.py apply <plan.json> [--repo <path>]       計画どおりにまとめる（バックアップのタグを打ってから）
  python squash.py undo  <tag> [--repo <path>]             まとめる前（タグ）へ戻す
  list / apply に --base <rev> を付けると、<rev>..HEAD だけを扱う（未 push の範囲にマージがあるとき、その後ろだけをまとめる）

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


def git(*args, repo, input_text=None, check=True, env=None):
    # 標準入力はバイト列で渡す。text=True のままだと Windows では \n が \r\n に化け、
    # mktree の名前・commit-tree のメッセージの行末に \r が入る（2026-10-26 にツリーが壊れた）
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, env=env,
                       input=input_text.encode("utf-8") if input_text is not None else None)
    out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{err.strip()}")
    return out.replace("\r\n", "\n").strip()


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


BASE = None  # --base <rev>: まとめる範囲の起点（未 push の範囲にマージがあるとき、その後ろだけを扱う）


def unpushed(repo):
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", repo=repo, check=False)
    if not upstream:
        sys.exit("upstream が設定されていない（git branch -u origin/<branch>）")
    base = upstream
    if BASE:
        base = git("rev-parse", BASE, repo=repo)
        if subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", base, "HEAD"]).returncode != 0:
            sys.exit(f"--base {BASE} が HEAD の祖先でない")
        if git("rev-list", "--count", f"{base}..{upstream}", repo=repo) != "0":
            sys.exit(f"--base {BASE} が push 済みの範囲（{upstream}）より前にある")
    merges = git("rev-list", "--merges", f"{base}..HEAD", repo=repo)
    if merges:
        sys.exit(f"範囲にマージコミットがある: {merges.split()}（--base でマージより後ろを指す）")
    commits = git("rev-list", "--reverse", f"{base}..HEAD", repo=repo).split()
    return base, commits


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
    # サブモジュールでは .git がファイル（gitdir: の参照）なので、git に本当の置き場を聞く
    plan_path = os.path.join(git("rev-parse", "--absolute-git-dir", repo=repo), "squash-plan.json")
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

    # "gitlinks": {"旧ハッシュ": "新ハッシュ"} … サブモジュールのコミットを作り直したとき、途中のコミットが指す旧ハッシュを付け替える
    # 短いハッシュはサブモジュールのリポジトリで 40 桁にする（mktree は 40 桁しか受けない）
    gitlinks = {}
    for k, v in plan.get("gitlinks", {}).items():
        for p in submodule_paths(repo):
            fk = git("rev-parse", "--verify", "--quiet", f"{k}^{{commit}}", repo=os.path.join(repo, p), check=False)
            fv = git("rev-parse", "--verify", "--quiet", f"{v}^{{commit}}", repo=os.path.join(repo, p), check=False)
            if fk and fv:
                gitlinks[fk] = fv
        if not any(x == k or x.startswith(k) for x in gitlinks):
            sys.exit(f"gitlinks: {k} → {v} をどのサブモジュールでも引けない")
    parent = git("rev-parse", upstream, repo=repo)
    for g in plan["groups"]:
        last = git("rev-parse", g["commits"][-1], repo=repo)
        tree = git("rev-parse", f"{last}^{{tree}}", repo=repo)
        if gitlinks:
            tree = relink(repo, tree, gitlinks)
        # 作者・日時は、グループの最後のコミットのものを引き継ぐ
        env_fmt = git("log", "-1", "--format=%an%x00%ae%x00%aI", last, repo=repo).split("\x00")
        env = dict(os.environ, GIT_AUTHOR_NAME=env_fmt[0], GIT_AUTHOR_EMAIL=env_fmt[1], GIT_AUTHOR_DATE=env_fmt[2])
        message = g["message"].replace("\r\n", "\n").rstrip() + "\n"
        parent = git("commit-tree", tree, "-p", parent, "-F", "-", repo=repo, input_text=message, env=env)
        # 作り直したコミットは、元の最後のコミットとサブモジュールの参照以外が同じこと・メッセージに \r が無いこと
        changed = [p for p in git("diff", "--name-only", last, parent, repo=repo).splitlines() if p]
        extra = [p for p in changed if p not in submodule_paths(repo)]
        if extra:
            git("tag", "-d", tag, repo=repo)
            sys.exit(f"{g['commits']} の作り直しで中身が変わった（{extra[:5]}）。ブランチは変えていない")
        if "\r" in git("cat-file", "commit", parent, repo=repo):
            git("tag", "-d", tag, repo=repo)
            sys.exit(f"{g['commits']} のコミットに \\r が入った。ブランチは変えていない")

    if git("rev-parse", f"{parent}^{{tree}}", repo=repo) != git("rev-parse", f"{head}^{{tree}}", repo=repo):
        sys.exit(f"まとめた結果のツリーが元の HEAD と違う。ブランチは変えていない（バックアップ {tag}）")
    git("update-ref", "-m", f"squash ({tag})", branch, parent, head, repo=repo)
    print(f"backup tag: {tag}")
    print(git("log", "--format=%h %s", f"{upstream}..HEAD", repo=repo))
    diff = git("diff", "--stat", tag, "HEAD", repo=repo)
    print("tree diff vs backup:", "none" if not diff else diff)


def submodule_paths(repo):
    out = git("config", "-f", os.path.join(repo, ".gitmodules"), "--get-regexp", r"submodule\..*\.path", repo=repo, check=False)
    return [line.split(" ", 1)[1] for line in out.splitlines() if " " in line]


def relink(repo, tree, gitlinks):
    """tree の中のサブモジュール（.gitmodules の path）が gitlinks の旧ハッシュを指していれば新ハッシュへ替えたツリーを返す。
    替えるのはその 1 行と、そこまでの親ディレクトリのツリーだけ（他の中身は同じオブジェクトのまま）。"""
    for path in submodule_paths(repo):
        entry = git("ls-tree", tree, path, repo=repo)
        if not entry:
            continue
        sha = entry.split()[2]
        if sha in gitlinks:
            tree = replace_entry(repo, tree, path.split("/"), gitlinks[sha])
    return tree


def replace_entry(repo, tree, parts, new_sha):
    lines = git("ls-tree", tree, repo=repo).splitlines()
    out = []
    for line in lines:
        meta, name = line.split("\t", 1)
        mode, typ, sha = meta.split()
        if name == parts[0]:
            sha = new_sha if len(parts) == 1 else replace_entry(repo, sha, parts[1:], new_sha)
        out.append(f"{mode} {typ} {sha}\t{name}")
    return git("mktree", repo=repo, input_text="\n".join(out) + "\n")


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
    if "--base" in args:
        global BASE
        i = args.index("--base")
        BASE = args[i + 1]
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
