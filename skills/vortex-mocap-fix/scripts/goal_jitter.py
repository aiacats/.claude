"""ClipCurveTools.GoalCsv の CSV（足の IK の目標 = RootT + RootQ × FootT）を、基準（圧縮 Off で取り込んだ元の FBX）と比べる。Unity 不要。

使い方:
  python goal_jitter.py <scale> <基準.csv> <比べる.csv> [...]        基準とのずれ（mm）と、接地中の急な動き（2 階差分 2 mm 超）の回数
  python goal_jitter.py <scale> <基準.csv> <比べる.csv> --windows    急な動きが多い 10 秒の区間（録画して見せる場面を選ぶ）

scale は Avatar の humanScale（Humanoid の正規化した長さ → m）。GoalCsv の値に掛ける。分からなければ 1（≒ m）で比べ合わせには足りる。
接地は基準の足の目標の速さが 0.15 m/s 未満のコマ（どれも同じコマで測る）。
Foot IK On のキャラは、舞台の足がこの目標に置かれる。ここが元から mm 単位でずれて揺れていれば、間引き（許容）が粗い。
"""
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
FPS = 60.0


def load(p):
    return np.genfromtxt(p, delimiter=",", names=True, deletechars="")


def pos(a, s, scale):
    return np.stack([a[s + "x"], a[s + "y"], a[s + "z"]], 1) * scale


def jolts(p):
    x = np.linalg.norm(p[2:] - 2 * p[1:-1] + p[:-2], axis=1) * 1000
    return np.concatenate([[0], x, [0]])


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(args) < 3:
        sys.exit(__doc__)
    scale = float(args[0])
    ref = load(args[1])
    masks = {}
    for s in ("l", "r"):
        v = np.linalg.norm(np.diff(pos(ref, s, scale), axis=0), axis=1) * FPS
        masks[s] = np.concatenate([[v[0]], v]) < 0.15
    if "--windows" in sys.argv:
        old = load(args[2])
        w = int(10 * FPS)
        score = sum(((jolts(pos(old, s, scale)) > 2) & masks[s]).astype(float) for s in ("l", "r"))
        cs = np.convolve(score, np.ones(w), mode="valid")
        picked = []
        for i in np.argsort(-cs):
            if all(abs(i - j) > w for j in picked):
                picked.append(i)
            if len(picked) >= 6:
                break
        for i in picked:
            print(f"{i / FPS:8.1f}s – {(i + w) / FPS:8.1f}s : {int(cs[i])} jolts")
        return
    for path in args[1:]:
        a = load(path)
        n = min(len(a), len(ref))
        print(f"== {path}")
        for s in ("l", "r"):
            p, m = pos(a, s, scale)[:n], masks[s][:n]
            err = np.linalg.norm(p - pos(ref, s, scale)[:n], axis=1) * 1000
            j = jolts(p)[m]
            print(f"  {'left ' if s == 'l' else 'right'}: off from ref mean {err.mean():6.2f} max {err.max():7.2f} mm | "
                  f"contact {m.mean() * 100:3.0f}% jolts >2mm {int((j > 2).sum()):5d} (p99 {np.percentile(j, 99):.2f} max {j.max():.2f} mm)")


if __name__ == "__main__":
    main()
