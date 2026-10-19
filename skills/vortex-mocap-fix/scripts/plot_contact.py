# 着いている足の足首の位置（区間の平均からのずれ、mm）を、直す前・直した後・元の FBX で重ねて描く（MotionScan.ScanLegs の出力）。
# 区間は、指定した時刻の範囲で、その足がいちばん長く止まっている所（速さ 0.15 m/s 未満）。最後に渡したデータで区間を決める。
# 使い方: python plot_contact.py <title> <out.png> <t0> <t1> <Left|Right> <label=bin> [<label=bin> ...]
#   ラベル Before / After / Source FBX は色が決まっている（赤 / 緑 / 灰）。報告の画像に使う。
import json
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
if len(sys.argv) < 7 or sys.argv[5] not in ("Left", "Right"):
    sys.exit("使い方: python plot_contact.py <title> <out.png> <t0> <t1> <Left|Right> <label=bin> [<label=bin> ...]")
title, out, t0, t1, side = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
runs = [a.split("=", 1) for a in sys.argv[6:]]


def load(p):
    m = json.load(open(p + ".json"))
    a = np.fromfile(p, dtype=np.float32).reshape(m["frames"], 1 + 7 * len(m["bones"]))
    return a[:, 0], {b: a[:, 1 + 7 * i:4 + 7 * i].astype(float) for i, b in enumerate(m["bones"])}


# 区間は最初の（基準の）データで決める
t, pos = load(runs[-1][1])
f = pos[side + "Foot"]
v = np.concatenate([[0], np.linalg.norm(np.diff(f, axis=0), axis=1) * 60])
ok = (v < 0.15) & (t >= t0) & (t < t1)
best, cur, start = (0, 0), 0, 0
for i, o in enumerate(ok):
    if o:
        if cur == 0:
            start = i
        cur += 1
        if cur > best[1] - best[0]:
            best = (start, i + 1)
    else:
        cur = 0
a0, a1 = best
fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
fig.patch.set_facecolor("#1e1e1e")
colors = {"Before": "#e05050", "After": "#40c070", "Source FBX": "#9a9a9a"}
for label, path in runs:
    tt, pp = load(path)
    p = pp[side + "Foot"][a0:a1]
    d = (p - p.mean(axis=0)) * 1000
    for k, ax in enumerate(axes):
        ax.plot(tt[a0:a1], d[:, k], color=colors.get(label, "#5080e0"), lw=1.4 if label != "Source FBX" else 1.0, label=label)
for k, ax in enumerate(axes):
    ax.set_facecolor("#262626")
    ax.set_ylabel(f"{'XYZ'[k]} (mm)", color="#d0d0d0")
    ax.tick_params(colors="#c0c0c0")
    ax.grid(color="#3a3a3a")
    for s in ax.spines.values():
        s.set_color("#555555")
axes[0].legend(facecolor="#2a2a2a", edgecolor="#555555", labelcolor="#d0d0d0", loc="upper right")
axes[-1].set_xlabel("Timeline time (s)", color="#d0d0d0")
fig.suptitle(f"{title}: {side} ankle while planted ({t[a0]:.2f}-{t[a1 - 1]:.2f} s), offset from its mean", color="#e0e0e0")
fig.tight_layout()
fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
print(out, t[a0], t[a1 - 1])
