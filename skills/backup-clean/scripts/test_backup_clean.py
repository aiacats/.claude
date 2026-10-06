"""backup_clean.py を使い捨てのリポジトリで試す（3 つの状態の判定・--covered は local-only を残す・--force・restore）。"""
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_clean.py")


def run(*args, cwd, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed: {r.stdout}{r.stderr}")
    return r.stdout


def git(*args, cwd):
    return run("git", *args, cwd=cwd).strip()


def commit(work, name, text):
    with open(os.path.join(work, name), "a") as f:
        f.write(text)
    git("add", ".", cwd=work)
    git("commit", "-qm", text.strip(), cwd=work)


def tool(*args, cwd, check=True):
    return run(sys.executable, SCRIPT, *args, cwd=cwd, check=check)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        remote = os.path.join(tmp, "remote.git")
        work = os.path.join(tmp, "work")
        run("git", "init", "--bare", "-q", remote, cwd=tmp)
        run("git", "clone", "-q", remote, work, cwd=tmp)
        git("config", "user.name", "t", cwd=work)
        git("config", "user.email", "t@example.com", cwd=work)
        commit(work, "a.txt", "0\n")
        git("tag", "backup/pushed", cwd=work)              # このコミットは push する -> pushed
        git("push", "-q", "-u", "origin", "HEAD", cwd=work)
        commit(work, "a.txt", "1\n")
        commit(work, "a.txt", "2\n")
        git("tag", "backup-squash", cwd=work)              # まとめ直す前 -> 同じツリーを push -> same-tree
        tree = git("rev-parse", "HEAD^{tree}", cwd=work)
        squashed = git("commit-tree", tree, "-p", "HEAD~2", "-m", "squashed", cwd=work)
        git("reset", "-q", "--hard", squashed, cwd=work)
        git("push", "-q", "origin", "HEAD", cwd=work)
        commit(work, "b.txt", "local\n")
        git("tag", "backup/local", cwd=work)               # push していない -> local-only
        git("tag", "release-1", cwd=work)                  # バックアップではない -> 対象外

        out = tool("list", "--repo", work, cwd=work)
        st = {l.split()[-1]: l.split()[0] for l in out.splitlines() if l.startswith("  ")}
        assert st == {"backup/pushed": "pushed", "backup-squash": "same-tree", "backup/local": "local-only"}, st

        tool("delete", "--repo", work, "--covered", cwd=work)
        tags = set(git("tag", "-l", cwd=work).split())
        assert tags == {"backup/local", "release-1"}, tags

        out = tool("delete", "--repo", work, "backup/local", cwd=work)
        assert "skip" in out and "backup/local" in git("tag", "-l", cwd=work)
        r = subprocess.run([sys.executable, SCRIPT, "delete", "--repo", work, "release-1"], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0 and "release-1" in git("tag", "-l", cwd=work)

        tool("delete", "--repo", work, "backup/local", "--force", cwd=work)
        assert "backup/local" not in git("tag", "-l", cwd=work)
        tool("restore", "--repo", work, "backup/local", cwd=work)
        assert git("rev-parse", "backup/local", cwd=work) == git("rev-parse", "HEAD", cwd=work)
        print("all tests passed")


if __name__ == "__main__":
    main()
