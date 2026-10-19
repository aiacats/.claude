"""収録データどうし・参考映像との時刻のずれを、相互相関で測る（Unity 不要。ffmpeg を使う）。

  audio  <a> <b>        a の P 秒の音が b の何秒にあるか（b = a + offset）。窓ごとに測り、伸び（ppm）も出す。
                        a = OBS プレビュー・番組映像（URL 可）、b = 2Mix など。L/R の別ファイルは "L.wav+R.wav"。
                        --b-at start[,clipIn] で b の Timeline 上の置き方を渡すと、Timeline 時刻 T と T − P も出す。
  mouth  <表情> <音>    表情の記録（VRMBlendShapeRecordData の .asset）の口（A・I・U・E・O の合計）と音の包絡を突き合わせる。
                        口の f 秒 = 音の s = f + lag 秒。2 人で 1 本の 2Mix なら表情を "a.asset+b.asset"。
                        --audio-at / --facial-at（start,clipIn）を渡すと、今の置き方のずれと、表情のクリップの start − clipIn を出す。
  motion <a> <b>        音の無い映像どうしを、人物の動きの量（隣のコマとの差）で合わせる（b = a + offset）。--at・--dur・--guess・--range。
  dmx    <.dmx> <映像>  DMX の全チャンネル合計の変化と、映像の明るさの変化を突き合わせる（DMX の d 秒 = 映像の P = d + lag）。
                        --crop で灯体が写る範囲に絞る（画面全体は LED・VJ に引っ張られて相関が出ない）。
                        --p2t M（Timeline T = 映像 P + M）を渡すと、DMX クリップの start − clipIn を出す。

時刻の約束: クリップの中の時刻 x は Timeline の T = start + (x − clipIn) / timeScale。
"""
import argparse
import json
import re
import shutil
import struct
import subprocess
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffprobe.exe"


def duration(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def read_audio(spec, sr, start=None, dur=None, stream=None):
    """spec = "a.wav" か "L.wav+R.wav"（足し合わせる）。モノラル float32。"""
    paths = spec.split("+")
    cmd = [FFMPEG, "-v", "error"]
    for p in paths:
        if start is not None:
            cmd += ["-ss", f"{max(start, 0):.3f}"]
        if dur is not None:
            cmd += ["-t", f"{dur:.3f}"]
        cmd += ["-i", p]
    if len(paths) > 1:
        cmd += ["-filter_complex", "".join(f"[{i}:a]" for i in range(len(paths))) + f"amix=inputs={len(paths)}:normalize=0"]
    elif stream is not None:
        cmd += ["-map", f"0:a:{stream}"]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32).astype(np.float64)


class Ref:
    """長い参照（b）の FFT を 1 回だけ取り、短い窓（seg）がどこに一致するかを探す。"""

    def __init__(self, ref, max_seg):
        self.ref = ref
        self.n = 1 << int(np.ceil(np.log2(len(ref) + max_seg)))
        self.R = np.fft.rfft(ref, self.n)
        self.e = np.concatenate([[0.0], np.cumsum(ref * ref)])  # 区間のエネルギー

    def find(self, seg):
        seg = seg - seg.mean()
        c = np.fft.irfft(self.R * np.conj(np.fft.rfft(seg, self.n)), self.n)[:len(self.ref) - len(seg) + 1]
        en = np.sqrt(np.maximum(self.e[len(seg):] - self.e[:-len(seg)], 1e-12) * (seg * seg).sum())
        norm = c / en
        k = int(np.argmax(norm))
        far = np.abs(np.arange(len(norm)) - k) > len(seg) // 4
        second = float(norm[far].max()) if far.any() else 0.0
        return k, float(norm[k]), second


def cmd_audio(a):
    sr = a.sr
    b = read_audio(a.b, sr)
    b = b - b.mean()
    dur_a = duration(a.a.split("+")[0])
    starts = [float(x) for x in a.at.split(",")] if a.at else [dur_a * f for f in (0.08, 0.27, 0.46, 0.65, 0.84)]
    ref = Ref(b, int(a.win * sr) + 1)
    bs, bc = (list(map(float, a.b_at.split(","))) + [0.0])[:2] if a.b_at else (None, None)
    rows = []
    for p in starts:
        seg = read_audio(a.a, sr, p, a.win, a.stream)
        if len(seg) < sr:
            print(f"P {p:9.2f}: too short")
            continue
        k, c, c2 = ref.find(seg)
        s = k / sr
        rows.append((p, s - p, c))
        line = f"P {p:9.2f} → b {s:9.3f}  offset {s - p:+9.4f}  corr {c:.3f} (next peak {c2:.3f})"
        if bs is not None:
            t = bs + s - bc
            line += f"  T {t:9.3f}  T−P {t - p:+8.4f}"
        print(line)
    if len(rows) >= 2:
        pm = np.array([(p, o) for p, o, c in rows if c >= a.min_corr])
        if len(pm) >= 2:
            slope, icpt = np.polyfit(pm[:, 0], pm[:, 1], 1)
            res = np.abs(pm[:, 1] - (icpt + slope * pm[:, 0])).max() * 1000
            print(f"offset = {icpt:+.4f} + {slope * 1e6:+.1f} ppm × P   (max residual {res:.1f} ms, {len(pm)} windows with corr ≥ {a.min_corr})")
        print(f"median offset {np.median([o for _, o, _ in rows]):+.4f} s")


def load_mouth(spec, rate):
    total = None
    for path in spec.split("+"):
        text = open(path, encoding="utf-8").read()
        keys = re.findall(r"(?m)^  - presetName: (\S+)\r?\n    name: (\S+)", text)
        idx = [i for i, (p, _) in enumerate(keys) if p in ("A", "I", "U", "E", "O")]
        if not idx:
            sys.exit(f"{path}: no A/I/U/E/O clips")
        body = text.split("\n  _frames:", 1)[1]
        end = re.search(r"(?m)^  _\w+:", body)
        if end:
            body = body[:end.start()]
        times, vals = [], []
        for fr in re.split(r"(?m)^  - time: ", body)[1:]:
            lines = fr.splitlines()
            v = [float(x.strip()[2:]) for x in lines[2:2 + len(keys)]]
            times.append(float(lines[0]))
            vals.append(sum(v[i] for i in idx))
        grid = np.arange(0, times[-1], 1 / rate)
        m = np.interp(grid, np.array(times), np.array(vals))
        total = m if total is None else total[:min(len(total), len(m))] + m[:min(len(total), len(m))]
    return total


def envelope(x, sr, rate):
    n = int(sr / rate)
    m = len(x) // n
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(axis=1))


def z(x):
    return (x - x.mean()) / (x.std() + 1e-9)


def lag_search(x, y, rate, lo, hi, min_overlap):
    """y(t) が x(t + lag) に最も似る lag（秒）と相関、0.5 秒以上離れた 2 番目の山。"""
    zx, zy = z(x), z(y)
    best = []
    for k in range(int(lo * rate), int(hi * rate) + 1):
        a0, b0 = (k, 0) if k >= 0 else (0, -k)
        m = min(len(zx) - a0, len(zy) - b0)
        if m < min_overlap * rate:
            continue
        best.append((float(np.dot(zx[a0:a0 + m], zy[b0:b0 + m]) / m), k / rate))
    if not best:
        sys.exit("no overlap in the search range")
    best.sort(reverse=True)
    second = next((b for b in best[1:] if abs(b[1] - best[0][1]) > 0.5), (0.0, 0.0))
    return best[0], second


def placement(s):
    v = (list(map(float, s.split(","))) + [0.0])[:2]
    return v[0] - v[1]  # start − clipIn（timeScale 1）


def cmd_mouth(a):
    rate = a.rate
    mouth = load_mouth(a.facial, rate)
    env = envelope(read_audio(a.audio, 4000), 4000, rate)
    lo, hi = map(float, a.search.split(","))
    now = None
    if a.audio_at and a.facial_at:
        now = placement(a.facial_at) - placement(a.audio_at)  # 今の置き方での s = f + now
        lo, hi = now + lo, now + hi
    (c, lag), (c2, lag2) = lag_search(env, mouth, rate, lo, hi, a.min_overlap)
    print(f"mouth f ↔ audio s = f {lag:+.3f} s   corr {c:.3f}  (next peak {c2:.3f} at {lag2:+.2f})")
    if now is not None:
        print(f"now: s = f {now:+.3f} → the mouth is {now - lag:+.3f} s {'late' if now - lag > 0 else 'early'} against the sound")
    if a.audio_at:
        print(f"facial clip: start − clipIn = {placement(a.audio_at) + lag:+.4f}  (e.g. start 0, clipIn {-(placement(a.audio_at) + lag):.4f})")


def gray_frames(path, start, dur, fps, w, h, crop=None):
    """crop = "x,y,w,h"（画面に対する割合 0〜1）なら、その範囲だけを縮めて読む。"""
    cmd = [FFMPEG, "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    vf = f"fps={fps},"
    if crop:
        x, y, cw, ch = crop.split(",")
        vf += f"crop=iw*{cw}:ih*{ch}:iw*{x}:ih*{y},"
    cmd += ["-i", path, "-vf", vf + f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w).astype(np.float32)


def cmd_motion(a):
    fps, w, h = 30, 192, 108
    y0, y1 = (int(v) * h // 1080 for v in a.band.split(",")) if a.band else (h * 25 // 100, h * 80 // 100)

    def energy(fr):
        d = np.abs(np.diff(fr[:, y0:y1, :], axis=0))
        med = np.median(d, axis=(1, 2), keepdims=True) + 1.0  # 画面全体の明滅（照明）を弱める
        return (d / med).mean(axis=1)
    ea = energy(gray_frames(a.a, a.at, a.dur, fps, w, h))
    eb = energy(gray_frames(a.b, a.at + a.guess - a.range, a.dur + 2 * a.range, fps, w, h))
    best = None
    for s in range(0, int(2 * a.range * fps) + 1):
        seg = eb[s:s + len(ea)]
        if len(seg) < len(ea):
            break
        c = np.corrcoef(ea.ravel(), seg.ravel())[0, 1]
        if best is None or c > best[0]:
            best = (c, s)
    c, s = best
    print(f"offset {a.guess - a.range + s / fps:+.3f} s (b = a + offset)  corr {c:.3f}")


def dmx_series(path, rate):
    data = open(path, "rb").read()
    _, _, nu = struct.unpack_from("<IdI", data, 0)
    rec = 16 + nu * 516
    n = len(data) // rec
    arr = np.frombuffer(data[:n * rec], dtype=np.uint8).reshape(n, rec)
    t = np.frombuffer(arr[:, 4:12].tobytes(), dtype="<f8") / 1000.0
    t = t - t[0]
    ch = np.concatenate([arr[:, 16 + i * 516 + 4:16 + (i + 1) * 516] for i in range(nu)], axis=1).astype(np.float32)
    grid = np.arange(0, t[-1], 1 / rate)
    return np.interp(grid, t, ch.sum(axis=1))


def cmd_dmx(a):
    rate = 30.0
    d = dmx_series(a.dmx, rate)
    # 画面全体の平均は LED・VJ の映像に引っ張られて相関が出ない（AZKi で 0.04）。灯体が写る帯を --crop で選ぶ
    luma = gray_frames(a.video, None, None, rate, 16, 64, a.crop).mean(axis=(1, 2))
    dd, dl = np.diff(d, prepend=d[0]), np.diff(luma, prepend=luma[0])
    lo, hi = map(float, a.search.split(","))
    (c, lag), (c2, lag2) = lag_search(dl, dd, rate, a.guess + lo, a.guess + hi, a.min_overlap)
    print(f"DMX d ↔ video P = d {lag:+.3f} s   corr {c:.3f}  (next peak {c2:.3f} at {lag2:+.2f})")
    if a.p2t is not None:
        print(f"DMX clip: start − clipIn = {lag + a.p2t:+.4f}  (T = P {a.p2t:+.4f})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("audio"); s.add_argument("a"); s.add_argument("b")
    s.add_argument("--at", help="a の窓の開始秒（カンマ区切り）。省くと全体に 5 か所"); s.add_argument("--win", type=float, default=20.0)
    s.add_argument("--sr", type=int, default=8000); s.add_argument("--stream", type=int, help="a の音声ストリーム番号")
    s.add_argument("--b-at", help="b の Timeline 上の start[,clipIn]"); s.add_argument("--min-corr", type=float, default=0.3)
    s = sub.add_parser("mouth"); s.add_argument("facial"); s.add_argument("audio")
    s.add_argument("--rate", type=float, default=50.0); s.add_argument("--search", default="-60,60", help="lag の探索範囲（秒）。置き方を渡したときは今の値からの幅")
    s.add_argument("--audio-at"); s.add_argument("--facial-at"); s.add_argument("--min-overlap", type=float, default=60.0)
    s = sub.add_parser("motion"); s.add_argument("a"); s.add_argument("b")
    s.add_argument("--at", type=float, required=True); s.add_argument("--dur", type=float, default=60.0)
    s.add_argument("--guess", type=float, default=0.0); s.add_argument("--range", type=float, default=5.0)
    s.add_argument("--band", help="人物の居る帯 y0,y1（FHD の画素）")
    s = sub.add_parser("dmx"); s.add_argument("dmx"); s.add_argument("video")
    s.add_argument("--guess", type=float, default=0.0); s.add_argument("--search", default="-30,30")
    s.add_argument("--p2t", type=float, help="Timeline T = 映像 P + この値"); s.add_argument("--min-overlap", type=float, default=60.0)
    s.add_argument("--crop", help="灯体の写る範囲 x,y,w,h（画面に対する割合）。例 0,0,0.05,0.75 = 左端 5%%・上 75%%")
    a = p.parse_args()
    {"audio": cmd_audio, "mouth": cmd_mouth, "motion": cmd_motion, "dmx": cmd_dmx}[a.cmd](a)


if __name__ == "__main__":
    main()
