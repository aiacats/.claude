"""DMX（ArtNet の .dmx）とプレビューから、照明の暗転・明点の時刻とフェードの形を拾う（Unity 不要。luma は ffmpeg を使う）。
DMX の灯体の上から Light Intensity Track・Light Dimmer Track で暗転・明点を重ねるときに、区間とフェードの長さを決める（reference/dmx.md）。

  switch <.dmx>          多くの ch が一斉に 0 から上がる・0 へ落ちる瞬間（--min ch 以上が 0.1 秒の間に）と、冒頭 --head 秒の推移。
                         --exclude の ch（キャラ用ライトなど）の値の幅も出す（MZM はキャラ用ライトが全編 255 だった）。
  ramp   <.dmx> --at T   T 秒（Timeline）の前後で 0 から上がった ch の、その後の上がり方（平均・最大・255 に達した数）を 0.1 秒ごと。
                         最大値の上がり方を直線で当てはめ、上がり始め・上がり終わり（= Ease の長さ）を出す。
  （照明の合計で「暗い区間」を測る方法は使えない。Pan・Tilt・色など調光以外の ch が暗転中も 0 にならず、合計がほとんど変わらない。MZM で確認）
  luma   <映像>          プレビューの帯（既定は下の 1/3 = 床と足元）の明るさが --thr 未満の区間と、明点の前後の推移。DMX が無い組にも使える。

時刻: --dmx-at <DMX のクリップの start,clipIn> で Timeline の T を出す（sync.py と同じ約束。tl_dump.py で読む）。luma は --p2t M（T = 映像 P + M）。
--exclude は "universe:first-last"（ch は 0 始まり。VirtualFixture の並び）をカンマ区切り。例: キャラ用ライト 0:4-7。
"""
import argparse
import re
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync import gray_frames, placement  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
GRID = 10.0  # 解析の刻み（Hz）。記録は 60 Hz（MZM）。switch・luma はフェードの長さを 0.1 秒で決めれば足りる（ramp の当てはめは全パケットで行う）


def load(path):
    """(時刻 秒, universe 番号のリスト, [パケット, universe × 512] の uint8)。形式は reference/dmx.md の表。"""
    data = open(path, "rb").read()
    _, _, nu = struct.unpack_from("<IdI", data, 0)
    rec = 16 + nu * 516
    n = len(data) // rec
    arr = np.frombuffer(data[:n * rec], dtype=np.uint8).reshape(n, rec)
    t = np.frombuffer(arr[:, 4:12].tobytes(), dtype="<f8") / 1000.0
    unis = [struct.unpack_from("<I", data, 16 + i * 516)[0] for i in range(nu)]
    ch = np.concatenate([arr[:, 16 + i * 516 + 4:16 + (i + 1) * 516] for i in range(nu)], axis=1)
    return t - t[0], unis, ch


def excluded(spec, unis):
    """--exclude を、load の列番号のマスクにする。"""
    m = np.zeros(len(unis) * 512, bool)
    for part in filter(None, (spec or "").split(",")):
        mt = re.fullmatch(r"\s*(\d+):(\d+)(?:-(\d+))?\s*", part)
        if not mt:
            sys.exit(f'--exclude "{part}": write universe:first-last (0-based channels), e.g. 0:4-7')
        u, a, b = int(mt[1]), int(mt[2]), int(mt[3] if mt[3] is not None else mt[2])
        if u not in unis:
            sys.exit(f"--exclude: universe {u} is not in the file (has {unis})")
        if not 0 <= a <= b <= 511:
            sys.exit(f'--exclude "{part}": channels must be 0 <= first <= last <= 511')
        base = unis.index(u) * 512
        m[base + a:base + b + 1] = True
    return m


def on_grid(t, ch):
    grid = np.arange(0, t[-1], 1 / GRID)
    return grid, ch[np.searchsorted(t, grid).clip(0, len(t) - 1)].astype(np.int16)


def segments(mask, min_len):
    out, s = [], None
    for i, v in enumerate(np.r_[mask, False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if (i - s) / GRID >= min_len:
                out.append((s, i))
            s = None
    return out


def cmd_switch(a):
    t, unis, ch = load(a.dmx)
    off = placement(a.dmx_at)
    ex = excluded(a.exclude, unis)
    grid, g = on_grid(t, ch)
    print(f"universes {unis}, packets {len(t)}, {t[-1]:.1f} s ({len(t) / t[-1]:.1f} Hz)")
    if ex.any():
        print(f"excluded ch: min {g[:, ex].min(0).tolist()} max {g[:, ex].max(0).tolist()}")
    g = g[:, ~ex]
    vary = g.max(axis=0) != g.min(axis=0)
    gv = g[:, vary]
    nonzero = (gv > 0).sum(axis=1)
    level = gv.sum(axis=1) / 255.0
    print(f"channels that vary: {vary.sum()} / {g.shape[1]}. Timeline T = DMX + {off:+.4f}")
    print(f"--- first {a.head:.0f} s")
    for i in range(0, min(int(a.head * GRID), len(grid)), int(GRID // 2)):
        print(f"  T {grid[i] + off:7.1f}  non-zero {nonzero[i]:4d}  level {level[i]:8.1f}")
    rise = ((gv[1:] > 0) & (gv[:-1] == 0)).sum(axis=1)
    fall = ((gv[1:] == 0) & (gv[:-1] > 0)).sum(axis=1)
    hits = np.nonzero((rise >= a.min) | (fall >= a.min))[0]
    print(f"--- {a.min}+ channels switch on / off within {1 / GRID:.1f} s: {len(hits)} moments"
          + (f" (showing the {a.top} largest in time order; raise --min or --top)" if len(hits) > a.top else ""))
    if len(hits) > a.top:
        hits = np.sort(hits[np.argsort(-np.maximum(rise[hits], fall[hits]), kind="stable")[:a.top]])
    for i in hits:
        print(f"  T {grid[i + 1] + off:8.2f}  on {rise[i]:4d}  off {fall[i]:4d}  non-zero after {nonzero[i + 1]:4d}  level {level[i + 1]:8.1f}")


def cmd_ramp(a):
    t, unis, ch = load(a.dmx)
    off = placement(a.dmx_at)
    ex = excluded(a.exclude, unis)
    T = t + off
    if not (T[0] <= a.at - a.win and a.at + a.win <= T[-1]):
        sys.exit(f"--at {a.at}: outside the DMX on the Timeline ({T[0]:.2f}–{T[-1]:.2f} s)")
    i0, i1 = np.searchsorted(T, a.at - a.win), np.searchsorted(T, a.at + a.win)
    on = (ch[i0] == 0) & (ch[min(i1, len(T) - 1)] > 0) & ~ex
    print(f"channels that switch on within ±{a.win} s of T {a.at}: {on.sum()}")
    if not on.any():
        return
    for x in np.arange(a.at - 0.5, a.at + a.after + 1e-6, 1 / GRID):
        v = ch[min(np.searchsorted(T, x), len(T) - 1), on].astype(float)
        print(f"  T {x:7.2f}  mean {v.mean():6.1f}  max {v.max():5.0f}  at full {int((v >= 250).sum()):4d}")
    # 最大値の上がり方（記録の全パケット）を、終わりの値の 10〜90% の間で直線に当てはめ、0 と終わりの値に届く時刻を出す
    k = (T >= a.at - 0.5) & (T <= a.at + a.after)
    tt, mx = T[k], ch[k][:, on].max(axis=1).astype(float)
    final = mx[-1]
    mid = (mx > 0.1 * final) & (mx < 0.9 * final)
    if mid.sum() < 3:
        print("the rise is too short to fit a line (a cut, not a fade)")
        return
    slope, icpt = np.polyfit(tt[mid], mx[mid], 1)
    t0, t1 = -icpt / slope, (final - icpt) / slope
    res = np.abs(mx[mid] - (icpt + slope * tt[mid])).max()
    print(f"max rises linearly from T {t0:.2f} to T {t1:.2f} (fade {t1 - t0:.2f} s, {slope:.0f}/s, max residual {res:.1f})")
    if (mx[tt >= tt[-1] - 0.2] < final).any() or t1 > tt[-1] - 0.1:
        print(f"warning: still rising near the end of the window (T {tt[-1]:.2f}); the fade may be longer -> raise --after")


def cmd_luma(a):
    fr = gray_frames(a.video, None, None, GRID, 64, 36, a.crop)
    y = fr.mean(axis=(1, 2))
    print(f"frames {len(fr)} ({len(fr) / GRID:.1f} s), band luma p5 {np.percentile(y, 5):.1f} p50 {np.percentile(y, 50):.1f} p95 {np.percentile(y, 95):.1f}")
    for s, e in segments(y < a.thr, a.min_len):
        print(f"dark: T {s / GRID + a.p2t:8.1f}–{e / GRID + a.p2t:8.1f}  ({(e - s) / GRID:5.1f}s)  min {y[s:e].min():.1f}")
        lo, hi = max(e - 10, 0), min(e + 40, len(y))
        print("   rise: " + " ".join(f"{i / GRID + a.p2t:.2f}:{y[i]:.0f}" for i in range(lo, hi)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("switch", "ramp"):
        s = sub.add_parser(name)
        s.add_argument("dmx")
        s.add_argument("--dmx-at", default="0,0", help="DMX のクリップの start,clipIn（Timeline）")
        s.add_argument("--exclude", help='除く ch "universe:first-last"（0 始まり）。例 0:4-7')
    s = sub.choices["switch"]
    s.add_argument("--min", type=int, default=30, help="一斉とみなす ch 数（MZM の明点は 302 ch、点滅は 30〜45 ch）")
    s.add_argument("--top", type=int, default=20, help="多いときは ch 数の大きい順にこの数だけ（時刻順で出す）")
    s.add_argument("--head", type=float, default=40.0)
    s = sub.choices["ramp"]
    s.add_argument("--at", type=float, required=True, help="明点の Timeline 秒（switch で拾った値）")
    s.add_argument("--win", type=float, default=0.3)
    s.add_argument("--after", type=float, default=4.0)
    s = sub.add_parser("luma")
    s.add_argument("video")
    s.add_argument("--p2t", type=float, default=0.0, help="Timeline T = 映像 P + この値")
    s.add_argument("--crop", default="0,0.667,1,0.333", help="帯 x,y,w,h（画面に対する割合）。既定は下の 1/3")
    s.add_argument("--thr", type=float, required=True, help="暗いとみなす帯の明るさ（0〜255）。p5・p50 を見て決める")
    s.add_argument("--min-len", type=float, default=1.0)
    a = p.parse_args()
    {"switch": cmd_switch, "ramp": cmd_ramp, "luma": cmd_luma}[a.cmd](a)


if __name__ == "__main__":
    main()
