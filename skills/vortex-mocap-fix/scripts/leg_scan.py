"""MotionScan.ScanLegs の出力（t + 脚の 9 骨 × 位置 3・回転 4 の float32、列の並びは <bin>.json）を集計する。

  stats  <bin> [<bin> ...]          膝の跳ねと、接地中の足首・つま先の急な動きを数える（直す前・後を並べて渡す）
  events <IK On の bin> <IK Off の bin> [--thr 10]
                                    膝の跳ねを 1 件ずつ、同じ時刻の Foot IK Off（FK）の値と並べる（跳ねが IK 由来か元データ由来か）

指標（2026-10-14〜15 SinkaiFes2026 で決めたもの）:
  膝の跳ね = 膝の加速度（位置の 2 階差分、mm/コマ²）のうち、股関節・足首のどちらよりも大きい分。
             脚が振られるなら膝は足首以下、足を着いて体が動くなら股関節以下なので、両端より膝だけが動いたコマが残る。
             8 mm 以上が候補、Foot IK が反った側の解を選んだ跳ねは 70〜135 mm（2〜4 コマで戻る）。
  接地    = 足首の速さが 0.15 m/s 未満のコマ。接地中に足首・つま先の 2 階差分が 2 mm を超えたコマを「ガタつき」として数える
             （元の FBX をそのまま流すと数十件、間引きで崩れた .anim は数千件）。
"""
import argparse
import json
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def load(path):
    meta = json.load(open(path + ".json", encoding="utf-8"))
    bones = meta["bones"]
    a = np.fromfile(path, dtype=np.float32).reshape(-1, 1 + 7 * len(bones))
    pos = {b: a[:, 1 + 7 * i:4 + 7 * i].astype(np.float64) for i, b in enumerate(bones)}
    return a[:, 0].astype(np.float64), pos, float(meta.get("fps", 60.0))


def acc(p):
    x = np.linalg.norm(p[2:] - 2 * p[1:-1] + p[:-2], axis=1) * 1000
    return np.concatenate([[0], x, [0]])


def knee_jump(pos, side):
    hip, knee, foot = (pos[side + n] for n in ("UpperLeg", "LowerLeg", "Foot"))
    return acc(knee) - np.maximum(acc(hip), acc(foot))


def contact(p, fps):
    v = np.linalg.norm(np.diff(p, axis=0), axis=1) * fps
    return np.concatenate([[v[0]], v]) < 0.15


def cmd_stats(a):
    for path in a.bins:
        t, pos, fps = load(path)
        print(f"== {path}  frames {len(t)} ({t[0]:.1f}–{t[-1]:.1f}s)")
        for side in ("Left", "Right"):
            kj = knee_jump(pos, side)
            foot, toe = pos[side + "Foot"], pos[side + "Toes"]
            m = contact(foot, fps)
            fa, ta = acc(foot)[m], acc(toe)[m]
            print(f"  {side:5s} knee jump >=8mm {int((kj >= 8).sum()):4d} >=15mm {int((kj >= 15).sum()):4d} max {kj.max():6.1f} | "
                  f"contact {m.mean() * 100:3.0f}% ankle >2mm {int((fa > 2).sum()):5d} (p99 {np.percentile(fa, 99):.2f}) | "
                  f"toe >2mm {int((ta > 2).sum()):5d} (p99 {np.percentile(ta, 99):.2f})")
            big = np.nonzero(kj >= 15)[0]
            if len(big):
                print("        knee jumps at", ", ".join(f"{t[i]:.2f}s({kj[i]:.0f})" for i in big[:15]))


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def leg(pos, side):
    hip, knee, ankle, toe = (pos[f"{side}{b}"] for b in ("UpperLeg", "LowerLeg", "Foot", "Toes"))
    ext = np.linalg.norm(ankle - hip, axis=1) / (np.linalg.norm(knee - hip, axis=1) + np.linalg.norm(ankle - knee, axis=1))
    bend = np.degrees(np.arccos(np.clip(np.sum(unit(knee - hip) * unit(ankle - knee), axis=1), -1, 1)))
    axis = unit(ankle - hip)

    def perp(v):
        return v - np.sum(v * axis, axis=1, keepdims=True) * axis
    off, ref = unit(perp(knee - hip)), unit(perp(toe - ankle))
    swivel = np.degrees(np.arctan2(np.sum(np.cross(ref, off) * axis, axis=1), np.sum(ref * off, axis=1)))
    return dict(excess=knee_jump(pos, side), ext=ext, bend=bend, sw=-swivel if side == "Right" else swivel, knee=knee)


def cmd_events(a):
    t, on, _ = load(a.on)
    _, off, _ = load(a.off)
    rows = []
    for side in ("Left", "Right"):
        x, y = leg(on, side), leg(off, side)
        idx = np.where(x["excess"] >= a.thr)[0]
        groups = []
        for i in idx:
            if groups and t[i] - t[groups[-1][-1]] <= 0.5:
                groups[-1].append(i)
            else:
                groups.append([i])
        for g in groups:
            pk = max(g, key=lambda i: x["excess"][i])
            lo, hi = max(pk - 6, 0), min(pk + 7, len(t))
            rows.append(dict(side=side, t=t[pk], on=x["excess"][pk], off=y["excess"][lo:hi].max(), ext=x["ext"][pk],
                             bend_on=x["bend"][pk], bend_off=y["bend"][pk],
                             dsw=np.ptp(np.unwrap(np.radians(x["sw"][lo:hi]))) * 180 / np.pi,
                             dsw_off=np.ptp(np.unwrap(np.radians(y["sw"][lo:hi]))) * 180 / np.pi,
                             dknee=np.linalg.norm(x["knee"][pk] - y["knee"][pk]) * 1000))
    rows.sort(key=lambda r: -r["on"])
    print(f"knee jumps with IK On >= {a.thr} mm: {len(rows)}  (Off_ex = the same ±0.1 s with IK Off; if it also jumps, the source data jumps)")
    print("side    t(s)   On_ex Off_ex | ext  bend On/Off | knee swivel range On/Off (deg) | IK−FK knee (mm)")
    for r in rows:
        print(f"{r['side']:5s} {r['t']:8.2f} {r['on']:6.1f} {r['off']:6.1f} | {r['ext']:.3f} {r['bend_on']:5.1f}/{r['bend_off']:5.1f} | "
              f"{r['dsw']:6.1f} / {r['dsw_off']:6.1f} | {r['dknee']:5.0f}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats"); s.add_argument("bins", nargs="+")
    s = sub.add_parser("events"); s.add_argument("on"); s.add_argument("off"); s.add_argument("--thr", type=float, default=10.0)
    a = p.parse_args()
    {"stats": cmd_stats, "events": cmd_events}[a.cmd](a)


if __name__ == "__main__":
    main()
