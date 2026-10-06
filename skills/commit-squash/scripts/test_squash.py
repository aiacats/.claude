"""squash.py を使い捨てのリポジトリで試す（連続したまとめ・ツリー一致・undo・不正な計画で止まる・未コミットの変更を保つ）。"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SQUASH = os.path.join(HERE, "squash.py")


def run(*args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed: {r.stdout}{r.stderr}")
    return r


def git(*args, cwd):
    return run("git", *args, cwd=cwd).stdout.strip()


def setup(tmp):
    remote = os.path.join(tmp, "remote.git")
    work = os.path.join(tmp, "work")
    run("git", "init", "--bare", "-q", remote, cwd=tmp)
    run("git", "clone", "-q", remote, work, cwd=tmp)
    git("config", "user.name", "t", cwd=work)
    git("config", "user.email", "t@example.com", cwd=work)
    with open(os.path.join(work, "a.txt"), "w") as f:
        f.write("0\n")
    git("add", ".", cwd=work)
    git("commit", "-qm", "base", cwd=work)
    git("push", "-q", "-u", "origin", "HEAD", cwd=work)
    for i, name in enumerate(["a.txt", "a.txt", "b.txt", "b.txt"], 1):
        with open(os.path.join(work, name), "a") as f:
            f.write(f"{i}\n")
        git("add", ".", cwd=work)
        git("commit", "-qm", f"c{i}", cwd=work)
    with open(os.path.join(work, "dirty.txt"), "w") as f:
        f.write("uncommitted\n")
    return work


def plan(work, groups):
    path = os.path.join(work, ".git", "p.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"groups": groups}, f)
    return path


def main():
    with tempfile.TemporaryDirectory() as tmp:
        work = setup(tmp)
        commits = git("rev-list", "--reverse", "@{u}..HEAD", cwd=work).split()
        assert len(commits) == 4, commits
        head_tree = git("rev-parse", "HEAD^{tree}", cwd=work)
        mid_tree = git("rev-parse", f"{commits[1]}^{{tree}}", cwd=work)

        # 不正な計画: 連続していない / 抜けがある -> 止まり、ブランチは変わらない
        bad = plan(work, [{"commits": [commits[0], commits[2]], "message": "x"}, {"commits": [commits[1], commits[3]], "message": "y"}])
        r = run(sys.executable, SQUASH, "apply", bad, "--repo", work, cwd=work, check=False)
        assert r.returncode != 0 and "連続" in (r.stdout + r.stderr), r.stdout + r.stderr
        missing = plan(work, [{"commits": commits[:2], "message": "x"}])
        r = run(sys.executable, SQUASH, "apply", missing, "--repo", work, cwd=work, check=False)
        assert r.returncode != 0, r.stdout
        assert git("rev-parse", "HEAD", cwd=work) == commits[-1]

        # 正しい計画: 2 つにまとめる
        good = plan(work, [{"commits": commits[:2], "message": "A\n\nbody"}, {"commits": commits[2:], "message": "B"}])
        r = run(sys.executable, SQUASH, "apply", good, "--repo", work, cwd=work)
        tag = [l.split(": ")[1] for l in r.stdout.splitlines() if l.startswith("backup tag")][0]
        new = git("rev-list", "--reverse", "@{u}..HEAD", cwd=work).split()
        assert len(new) == 2, new
        assert git("rev-parse", "HEAD^{tree}", cwd=work) == head_tree
        assert git("rev-parse", f"{new[0]}^{{tree}}", cwd=work) == mid_tree
        assert git("log", "-1", "--format=%s", new[0], cwd=work) == "A"
        assert os.path.exists(os.path.join(work, "dirty.txt")), "未コミットのファイルが消えた"

        # undo でタグへ戻る
        run(sys.executable, SQUASH, "undo", tag, "--repo", work, cwd=work)
        assert git("rev-parse", "HEAD", cwd=work) == commits[-1]
        print("all tests passed")


if __name__ == "__main__":
    main()
