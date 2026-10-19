"""FHD 2 画面の録画（3840x1080）から左半分の Display を切り出し、尺を合わせて点検する。

    python cut_and_check.py <録画.mp4> <出力.mp4> --duration 44 [--head 0.5] [--check-dir <dir>]

- --head: 録画開始から Timeline 再生までのずれ（秒）。MCP の応答は秒単位なので 1 秒未満のずれは測れない。
  テストモーションの冒頭は T ポーズなので 0.5 秒落として構わない。
- 点検: vortex-timeline-export の check.py（解像度・尺・無地でないか + 中間フレーム PNG）と、3 秒以上の静止区間。
  静止区間はモーション終端の T ポーズのこともある（揺れ物が少ないキャラほど出やすい）。その時刻の絵を抜いて確かめる。
"""
import argparse
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
FFMPEG = os.path.expanduser(r"~/tools/ffmpeg-7.1-full_build/bin/ffmpeg.exe")
CHECK = os.path.expanduser(r"~/.claude/skills/vortex-timeline-export/scripts/check.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--head", type=float, default=0.5)
    ap.add_argument("--check-dir", default=None)
    a = ap.parse_args()

    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(a.head), "-i", a.src,
                    "-filter_complex", "[0:v]crop=1920:1080:0:0[v]", "-map", "[v]", "-t", str(a.duration),
                    "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-an", a.out], check=True)

    check_dir = a.check_dir or os.path.join(os.path.dirname(os.path.abspath(a.out)), "check")
    r = subprocess.run([sys.executable, CHECK, a.out, "--out", check_dir], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip())
    ok = r.returncode == 0

    f = subprocess.run([FFMPEG, "-hide_banner", "-hwaccel", "cuda", "-i", a.out, "-vf", "fps=10,freezedetect=n=0.001:d=3",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = re.findall(r"freeze_start: ([\d.]+)", f.stderr)
    durs = re.findall(r"freeze_duration: ([\d.]+)", f.stderr)
    if starts:
        for s, d in zip(starts, durs + ["(to end)"] * len(starts)):
            print(f"  freeze: from {s}s for {d}s  <- 絵を抜いて正当な静止かを見る")
    else:
        print("  freeze: none")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
