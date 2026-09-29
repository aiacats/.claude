"""Tauri アプリのリリースビルドを走らせ、Drive へ上がったことまで確かめる。

    python release.py <プロジェクトのパス> [--jobs 4] [--skip-build]

やること:
  1. そのプロジェクトの dev（tauri dev / vite / アプリ本体）を止める
     … 動いたままだとビルドスクリプトが出力ファイルを掴めずに失敗する
  2. `build-win.bat` を走らせる（CARGO_BUILD_JOBS を絞る。既定 4）
  3. 出来た exe の sha256 を取る
  4. SessionControl デーモンが `gdrive:Builds/<アプリ名>` へ上げるのを待ち、
     Drive 側のハッシュと突き合わせる

ビルドは数分かかる。**呼ぶ側は run_in_background で投げて、出力を追うこと。**
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

SESSION_CONTROL = r"D:\_Personal\Project\SessionControl"


def say(text: str) -> None:
    print(f"[release] {text}", flush=True)


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def stop_dev(project: str) -> None:
    """そのプロジェクトの dev を止める。**プロジェクトのパスで絞る**。
    名前だけで止めると、無関係な node や別プロジェクトの dev まで巻き添えにする。"""
    leaf = os.path.basename(project.rstrip("\\/"))
    ps = (
        "Get-CimInstance Win32_Process | Where-Object { "
        f"($_.Name -eq 'node.exe' -or $_.Name -eq 'cargo.exe') -and $_.CommandLine -like '*{leaf}*' "
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"
    ).replace("{leaf}", leaf)
    out = run(["powershell", "-NoProfile", "-Command", ps]).stdout.strip()
    if out:
        say(f"dev を止めました: {out.split()}")


def app_name(project: str) -> str:
    conf = os.path.join(project, "src-tauri", "tauri.conf.json")
    with open(conf, encoding="utf-8") as f:
        return json.load(f)["productName"]


def build(project: str, jobs: int) -> None:
    bat = os.path.join(project, "build-win.bat")
    if not os.path.isfile(bat):
        raise SystemExit(f"build-win.bat がありません: {bat}")
    env = dict(os.environ, CARGO_BUILD_JOBS=str(jobs))
    say(f"ビルド開始（CARGO_BUILD_JOBS={jobs}）: {bat}")
    started = time.time()
    # bat はフルパスで渡す。相対パスだと cmd が見つけられずに黙って終わる。
    done = subprocess.run(["cmd", "/c", bat], cwd=project, env=env, text=True,
                          encoding="utf-8", errors="replace", capture_output=True)
    tail = "\n".join(done.stdout.splitlines()[-12:])
    if done.returncode != 0 or "[OK] Build complete" not in done.stdout:
        raise SystemExit(f"ビルドに失敗しました（終了コード {done.returncode}）:\n{tail}")
    say(f"ビルド完了（{time.time() - started:.0f} 秒）")
    for line in done.stdout.splitlines():
        if re.search(r"Tests |test result|Finished .*bundles", line):
            say(line.strip())


def exe_path(project: str) -> str:
    folder = os.path.join(project, "src-tauri", "target", "release")
    exes = [f for f in os.listdir(folder) if f.endswith(".exe")]
    if not exes:
        raise SystemExit(f"exe が見つかりません: {folder}")
    return os.path.join(folder, exes[0])


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_log() -> str | None:
    folder = os.path.join(SESSION_CONTROL, "log")
    if not os.path.isdir(folder):
        return None
    logs = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".log")]
    return max(logs, key=os.path.getmtime) if logs else None


def wait_for_upload(name: str, want: str, timeout: int = 180) -> int:
    """デーモンが上げるのを待って、Drive 側のハッシュと突き合わせる。"""
    remote = f"gdrive:Builds/{name}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = run(["rclone", "hashsum", "sha256", remote]).stdout
        for line in out.splitlines():
            got, _, fname = line.strip().partition("  ")
            if got.lower() == want.lower():
                say(f"Drive で一致を確認: {fname.strip()} ({got[:16]}…)")
                return 0
        time.sleep(10)
    log = latest_log()
    hint = ""
    if log:
        lines = [l for l in open(log, encoding="utf-8", errors="replace") if name in l]
        hint = "\n".join(lines[-3:])
    say(f"Drive で一致を確認できませんでした（{timeout} 秒）。SessionControl のログ:\n{hint}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    name = app_name(project)
    say(f"対象: {name}（{project}）")

    if not args.skip_build:
        stop_dev(project)
        build(project, args.jobs)

    exe = exe_path(project)
    digest = sha256(exe)
    size = os.path.getsize(exe) / 1048576
    say(f"exe: {os.path.basename(exe)} {size:.1f} MB / sha256={digest[:16]}…")

    bundles = os.path.join(project, "src-tauri", "target", "release", "bundle")
    for root, _, files in os.walk(bundles):
        for f in files:
            if f.endswith((".exe", ".msi", ".dmg")):
                p = os.path.join(root, f)
                say(f"bundle: {f} {os.path.getsize(p) / 1048576:.1f} MB")

    return wait_for_upload(name, digest)


if __name__ == "__main__":
    raise SystemExit(main())
