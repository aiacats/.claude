"""カメラ記録の再生で、番組に出ているカメラがキャラをどう追っているかを測る（Unity 不要）。
入力の CSV は templates/Editor/CamFollowProbe.cs の Measure（Timeline を 1/fps ずつ進め、番組カメラ A/B の位置・向き・画角と、キャラの頭・腰を書く）。

  lag      <csv>                     カメラごとに、追従の遅れ（カメラの向きの速さと、キャラへの方位の速さの相互相関）・画面の横の揺れ・パンの速さ。
                                     + = カメラが遅れて追う、− = カメラがキャラより先に動く。遅れ 0・揺れが小さい = キャラに張り付いて回る
                                     （シーンの Aim Damping 0 のカメラ。「リニア感」）。
  fit      <csv> --cams 5,9          カメラの向き ≈「Δ 秒前のキャラへの方位を、時定数 τ の 1 次遅れでならしたもの」の Δ・τ を区間ごとに当てはめる。
                                     Δ > 0 = カメラが Δ 秒遅れて追う（ライブの追従ならこちら）。Δ < 0 = カメラがキャラより先に動く
                                     （追従では起きないので、記録とモーションの時刻がずれている疑い）。
  offframe <csv> [--until T]         ショットごとに、キャラの頭も腰も画面の外のコマの割合と、その間のカメラの向き・位置の変化。
                                     外の割合が大きく向きの変化が 0° のショットは「記録が止まっている」（注視先の番号のキャラがいない等）。
  aim      <csv> --from T0 --to T1   視線がキャラの頭の奥行きでどこを通るか（頭からの横・縦のずれ m と、画面の半幅）。Override の回転量を決める
  keys     <カメラ記録.anim>         記録のキーの密度（キー/秒・間隔）と、値が動くのにタンジェント 0 のキーの割合。

番組に出ている側は fade（≥ 0.5 で B = PRV 側）で選ぶ。カメラの番号は CSV の pgm / prv（スイッチャーの _inputCameras の番号）。
"""
import argparse
import csv
import math
import re
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def rot(q, v):
    """四元数 q = (x, y, z, w) で v を回す。"""
    u = np.array(q[:3])
    v = np.asarray(v, float)
    return v + 2 * np.cross(u, np.cross(u, v) + q[3] * v)


def yaw_of(q):
    x, y, z, w = q
    return math.degrees(math.atan2(2 * (x * z + w * y), 1 - 2 * (x * x + y * y)))


def load(path, until=None):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        t = float(r["t"])
        if until is not None and t > until:
            break
        side = "b" if float(r["fade"]) >= 0.5 else "a"
        rows.append(dict(
            t=t, idx=int(r["prv"] if side == "b" else r["pgm"]),
            p=np.array([float(r[side + k]) for k in "xyz"]),
            q=tuple(float(r[side + k]) for k in ("qx", "qy", "qz", "qw")),
            fov=float(r[side + "fov"]),
            head=np.array([float(r["h" + k]) for k in "xyz"]),
            hip=np.array([float(r["p" + k]) for k in "xyz"])))
    if len(rows) < 2 or rows[-1]["t"] <= rows[0]["t"]:
        sys.exit("CSV needs 2+ rows with increasing t (CamFollowProbe.Measure)")
    fps = round((len(rows) - 1) / (rows[-1]["t"] - rows[0]["t"]), 3)  # Measure は t0 + i/fps を 4 桁で書く。全体で割ると丸めが消える
    return rows, fps


def shots(rows, fps, min_len):
    """同じカメラが続く区間 [s, e)（min_len 秒以上）。番号が −1（記録が無い・番組に出ていない）のコマはショットにしない。"""
    out, s = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]["idx"] != rows[s]["idx"]:
            if rows[s]["idx"] >= 0 and (i - s) / fps >= min_len:
                out.append((s, i))
            s = i
    return out


def unwrap(deg):
    return np.degrees(np.unwrap(np.radians(np.asarray(deg, float))))


def screen_x(r, point, aspect):
    """画面上の横位置（-1〜1）。後ろなら nan。"""
    loc = np.array([np.dot(point - r["p"], rot(r["q"], a)) for a in ([1, 0, 0], [0, 1, 0], [0, 0, 1])])
    if loc[2] <= 0.1:
        return float("nan")
    return (loc[0] / loc[2]) / (math.tan(math.radians(r["fov"]) / 2) * aspect)


def cmd_lag(a):
    rows, fps = load(a.csv)
    stats = {}
    for s, e in shots(rows, fps, 3.0):
        seg = rows[s:e]
        idx = seg[0]["idx"]
        cy = unwrap([yaw_of(r["q"]) for r in seg])
        br = unwrap([math.degrees(math.atan2(*(r["hip"] - r["p"])[[0, 2]])) for r in seg])
        sx = np.array([screen_x(r, r["hip"], a.aspect) for r in seg])
        vc, vb = np.diff(cy) * fps, np.diff(br) * fps
        st = stats.setdefault(idx, dict(dur=0.0, lags=[], sx=[], pan=[], k=[]))
        st["dur"] += (e - s) / fps
        st["sx"].append(np.nanstd(sx))
        st["pan"].append(np.mean(np.abs(vc)))
        best = None
        if np.std(vb) >= 1.0 and np.std(vc) >= 0.5:  # キャラもカメラも動いていないショットは相関が測れない
            for L in range(int(-0.5 * fps), int(1.0 * fps) + 1):  # 探索: カメラが 0.5 秒先〜1 秒遅れ
                x = vc[max(0, L):len(vc) + min(0, L)]
                y = vb[max(0, -L):len(vb) - max(0, L)]
                n = min(len(x), len(y))
                if n < fps:
                    continue
                c = np.corrcoef(x[:n], y[:n])[0, 1]
                if best is None or c > best[1]:
                    best = (L / fps, c)
            if best and best[1] > 0.5:
                st["lags"].append((best[0], best[1], (e - s) / fps))
        if np.std(vb) > 1.0:  # キャラが横へ動くショットだけ
            # 実効の遅れ: 注視のずれ（方位 − 向き）を方位の速さに回帰した傾き（秒）。張り付いて追うと 0、減衰で遅れて追うと正
            err = (br - cy)[:-1]
            err = err - err.mean()
            vbc = vb - vb.mean()
            st["k"].append((float(np.dot(err, vbc) / np.dot(vbc, vbc)), (e - s) / fps))
            if a.show:
                print(f"  cam{idx:2d} {seg[0]['t']:7.1f}-{seg[-1]['t']:7.1f}s  lag {best[0] if best else float('nan'):+.3f} "
                      f"corr {best[1] if best else float('nan'):.2f}  eff_lag {st['k'][-1][0]:+.3f}s  pan {np.mean(np.abs(vc)):.1f}°/s")
    print(f"{fps:.0f} fps. cam  on-air(s)  shots  lag(s, corr>0.5 の区間の時間重み)  eff_lag(s)  画面の横の揺れ(std)  パン(°/s)")
    for idx in sorted(stats):
        st = stats[idx]
        w = lambda xs, j: sum(x[j] * x[-1] for x in xs) / sum(x[-1] for x in xs)  # noqa: E731
        lag = f"{w(st['lags'], 0):+.3f} ({len(st['lags'])})" if st["lags"] else "-"
        k = f"{w(st['k'], 0):+.3f} ({len(st['k'])})" if st["k"] else "-"
        print(f"  {idx:3d} {st['dur']:9.1f} {len(st['sx']):6d}  {lag:18s} {k:14s} {np.nanmean(st['sx']):.3f}  {np.mean(st['pan']):.2f}")


def cmd_fit(a):
    rows, fps = load(a.csv)
    cams = {int(x) for x in a.cams.split(",")}
    shifts = list(range(-int(0.6 * fps), int(0.6 * fps) + 1))  # 探索: ±0.6 秒
    taus = [0.0, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]  # 1 次遅れの時定数の候補（秒）
    total = np.zeros((len(shifts), len(taus)))
    count = 0
    for s, e in shots(rows, fps, 3.0):
        if rows[s]["idx"] not in cams:
            continue
        cy = unwrap([yaw_of(rows[i]["q"]) for i in range(s, e)])
        if np.mean(np.abs(np.diff(cy))) * fps < a.min_pan:
            continue
        res = np.zeros((len(shifts), len(taus)))
        for ai, sh in enumerate(shifts):
            br = []
            for i in range(s, e):  # 方位はカメラの今の位置から、キャラの (t − sh) の位置へ。sh > 0 = 前の時刻のキャラを狙う = カメラが遅れて追う
                j = min(max(i - sh, 0), len(rows) - 1)
                d = rows[j]["hip"] - rows[i]["p"]
                br.append(math.degrees(math.atan2(d[0], d[2])))
            br = unwrap(br)
            for bi, tau in enumerate(taus):
                if tau == 0:
                    lp = br
                else:
                    al = 1 - math.exp(-1 / (fps * tau))
                    lp = np.empty_like(br)
                    v = cy[0]
                    for k in range(len(br)):
                        v = v + al * (br[k] - v)
                        lp[k] = v
                d = np.diff(cy) - np.diff(lp)  # 速さで比べる（向きの一定のずれ = 構図は無視）
                res[ai, bi] = np.sqrt(np.mean(d[int(fps / 3):] ** 2)) * fps
        ai, bi = np.unravel_index(np.argmin(res), res.shape)
        print(f"cam{rows[s]['idx']:2d} {rows[s]['t']:7.1f}-{rows[e - 1]['t']:7.1f}s pan {np.mean(np.abs(np.diff(cy))) * fps:5.1f}°/s"
              f"  best Δ {shifts[ai] / fps:+.3f}s τ {taus[bi]:.2f}  rms {res[ai, bi]:.2f} (Δ=0 best {res[shifts.index(0)].min():.2f})")
        total += res / res.min()
        count += 1
    if count:
        ai, bi = np.unravel_index(np.argmin(total), total.shape)
        print(f"ALL {count} shots: best Δ {shifts[ai] / fps:+.3f}s τ {taus[bi]:.2f}")


def cmd_offframe(a):
    rows, fps = load(a.csv, a.until)
    th_n = a.min_len * fps
    print(f"ショット（{a.min_len} 秒以上）のうち、頭も腰も画面の外のコマが {a.min_frac * 100:.0f}% 以上のもの")
    n = 0
    for s, e in shots(rows, fps, 0.0):
        if e - s < th_n:
            continue
        seg = rows[s:e]
        frac = sum(1 for r in seg if not in_frame(r, a.aspect)) / len(seg)
        if frac < a.min_frac:
            continue
        n += 1
        Q = np.array([r["q"] for r in seg])
        P = np.array([r["p"] for r in seg])
        dq = np.degrees(2 * np.arccos(np.clip(np.abs(Q @ Q[0]), 0, 1))).max()
        dp = np.linalg.norm(P - P[0], axis=1).max()
        print(f"  cam {seg[0]['idx']:2d} {seg[0]['t']:8.2f}-{seg[-1]['t']:8.2f}s ({seg[-1]['t'] - seg[0]['t']:4.1f}s) 外 {frac * 100:4.0f}%"
              f"  向きの変化 最大 {dq:5.2f}°  位置の変化 最大 {dp:.2f} m")
    print(f"{n} shots")


def in_frame(r, aspect):
    """頭か腰が画面の中に入っているか。"""
    th = math.tan(math.radians(r["fov"]) / 2)
    for pt in (r["head"], r["hip"]):
        loc = np.array([np.dot(pt - r["p"], rot(r["q"], v)) for v in ([1, 0, 0], [0, 1, 0], [0, 0, 1])])
        if loc[2] > 0 and abs(loc[1] / loc[2]) <= th and abs(loc[0] / loc[2]) <= th * aspect:
            return True
    return False


def cmd_aim(a):
    rows, fps = load(a.csv)
    every = max(1, int(round(a.every * fps)))
    for i, r in enumerate(rows):
        if r["t"] < a.from_ or r["t"] > a.to or i % every:
            continue
        f, up, right = rot(r["q"], [0, 0, 1]), rot(r["q"], [0, 1, 0]), rot(r["q"], [1, 0, 0])
        d = np.dot(r["head"] - r["p"], f)
        off = r["head"] - (r["p"] + f * d)
        half = math.tan(math.radians(r["fov"]) / 2) * a.aspect * d
        print(f"T {r['t']:8.2f} cam {r['idx']:>2} fov {r['fov']:5.1f}  dist {d:5.2f} m  head − aim: right {np.dot(off, right):+.2f} m"
              f"  up {np.dot(off, up):+.2f} m  (half width {half:.2f} m)  yaw to center {math.degrees(math.atan2(np.dot(off, right), d)):+.1f}°")


def cmd_keys(a):
    num = re.compile(r"-?[\d.]+(?:e-?\d+)?")
    curves, section = [], None
    times, vals, slopes = [], [], []
    with open(a.anim, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("m_") and s.endswith("Curves:"):
                section = s[:-1]
            elif s.startswith("m_Curve:"):
                times, vals, slopes = [], [], []
            elif s.startswith("time:"):
                times.append(float(s[5:]))
            elif s.startswith("value:"):
                vals.append([float(x) for x in num.findall(s[6:])])
            elif s.startswith("outSlope:"):
                slopes.append([float(x) for x in num.findall(s[9:])])
            elif s.startswith("path:"):
                curves.append((section, s[5:].strip(), times, vals, slopes))
                if len(curves) >= a.curves:
                    break
    for sec, path, ts, vs, ss in curves:
        if len(ts) < 2:
            print(f"{sec} {path}: {len(ts)} keys")
            continue
        d = np.diff(ts)
        moving = [i for i in range(len(vs) - 1) if max(abs(x - y) for x, y in zip(vs[i], vs[i + 1])) > 1e-5]
        flat = sum(1 for i in moving if i < len(ss) and max(abs(x) for x in ss[i]) == 0)
        print(f"{sec} {path}: keys {len(ts)} {ts[0]:.2f}-{ts[-1]:.2f}s  {len(ts) / (ts[-1] - ts[0]):.1f}/s  "
              f"dt med {np.median(d) * 1000:.1f} ms p99 {np.percentile(d, 99) * 1000:.1f} max {d.max() * 1000:.0f} ms | "
              f"moving keys {len(moving)}, slope 0 among them {flat} ({flat / max(len(moving), 1) * 100:.1f}%)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("lag", "fit", "offframe", "aim"):
        s = sub.add_parser(name)
        s.add_argument("csv")
        s.add_argument("--aspect", type=float, default=16 / 9, help="番組の画の縦横比（出力の RT が 16:9）")
    sub.choices["lag"].add_argument("--show", action="store_true", help="ショットごとにも出す")
    s = sub.choices["fit"]
    s.add_argument("--cams", required=True)
    s.add_argument("--min-pan", type=float, default=3.0, help="これより遅いパンのショットは外す（°/s。止まっているショットは当てはめにならない）")
    s = sub.choices["offframe"]
    s.add_argument("--until", type=float)
    s.add_argument("--min-len", type=float, default=0.5)
    s.add_argument("--min-frac", type=float, default=0.3)
    s = sub.choices["aim"]
    s.add_argument("--from", dest="from_", type=float, required=True)
    s.add_argument("--to", type=float, required=True)
    s.add_argument("--every", type=float, default=0.25)
    s = sub.add_parser("keys")
    s.add_argument("anim")
    s.add_argument("--curves", type=int, default=1)
    a = p.parse_args()
    {"lag": cmd_lag, "fit": cmd_fit, "offframe": cmd_offframe, "aim": cmd_aim, "keys": cmd_keys}[a.cmd](a)


if __name__ == "__main__":
    main()
