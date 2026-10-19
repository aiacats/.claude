"""表情の記録の口を、歌声（Demucs で 2Mix から分けた vocals.wav）と突き合わせる（Unity 不要。ffmpeg を使う）。

  scan <表情> <歌声>   歌声が閾値未満なのに口が開いている区間を並べる（間奏で口がパクパクする所を探す）。
                       --th（歌声の dB）・--mouth（口の平均）・--step（秒）。--show a-b でその区間を 1 行ずつ出す。
  gate <表情> <歌声>   歌声が無い間の口（A・I・U・E・O）を 0 にした複製を作る（元の記録は残す。GUID は新しく振る）。
                       --th・--pad（前後の余白 秒）・--fade（境目のフェード 秒）・--out（既定 <元>_VoGate.asset）。

表情 = VRMBlendShapeRecordData の .asset。口は presetName が A・I・U・E・O のクリップ。
置き方は Timeline 上の start,clipIn で渡す（sync.py と同じ約束）: --facial-at <表情のクリップ> --audio-at <2Mix のクリップ>。
歌声は 2Mix と同じ置き方で読む（Demucs は時刻を保つ。htdemucs の出力は 44.1 kHz に変わるが、周波数はファイルから読む）。
歌声の作り方は reference/facial.md「歌声が無い間の口を閉じる」。
"""
import argparse
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffprobe.exe"
WIN = 0.05  # 歌声の大きさを測る窓（秒）。口の記録（60 fps）より粗く、子音 1 つ（約 50 ms）を拾える細かさ
MOUTH = ("A", "I", "U", "E", "O")


def placement(s):
    v = (list(map(float, s.split(","))) + [0.0])[:2]
    return v[0] - v[1]  # start − clipIn（timeScale 1）


def vocal_rms(path):
    """WIN 秒ごとの RMS（L/R の平均のモノラル）。大きいファイルをメモリに載せないよう、ffmpeg から窓ずつ読む。"""
    sr = int(subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                             "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip())
    hop = int(round(WIN * sr))
    cmd = [FFMPEG, "-v", "error", "-i", path, "-af", "pan=mono|c0=0.5*c0+0.5*c1", "-f", "f32le", "-"]
    out = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as p:
        block = hop * 4 * 2000  # 2000 窓（100 秒）ずつ
        rest = b""
        while True:
            b = p.stdout.read(block)
            if not b:
                break
            b = rest + b
            n = len(b) // (hop * 4)
            x = np.frombuffer(b[:n * hop * 4], dtype=np.float32).reshape(n, hop)
            out.append(np.sqrt((x.astype(np.float64) ** 2).mean(axis=1)))
            rest = b[n * hop * 4:]
    return np.concatenate(out), sr


def read_record(path):
    """(行のリスト, 改行, 口の値の行番号の配列 [frame][k], 各フレームの時刻)。"""
    raw = open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    keys = []
    i = 0
    while i < len(lines) and not lines[i].startswith("  _blendShapeKeys:"):
        i += 1
    i += 1
    while i < len(lines) and lines[i].startswith("  - presetName:"):
        keys.append(lines[i].split(":", 1)[1].strip())
        i += 1
        while i < len(lines) and lines[i].startswith("    "):
            i += 1
    idx = [k for k, p in enumerate(keys) if p in MOUTH]
    if len(idx) == 0:
        sys.exit(f"{path}: no A/I/U/E/O clips")
    while i < len(lines) and not lines[i].startswith("  _frames:"):
        i += 1
    times, rows = [], []
    i += 1
    while i < len(lines) and not lines[i].startswith("  _"):
        if lines[i].startswith("  - time:"):
            times.append(float(lines[i][9:]))
            v0 = i + 2  # "    values:" の次から keys の数だけ "    - v"
            rows.append([v0 + k for k in idx])
            i = v0 + len(keys)
            continue
        i += 1
    return lines, nl, np.array(rows), np.array(times)


def mouth_values(lines, rows):
    return np.array([[float(lines[j][6:]) for j in r] for r in rows])


def wav_time(a, tau):
    """表情の記録の時刻 τ → 歌声の時刻（Timeline T = τ + facial(start − clipIn) = w + audio(start − clipIn)）。"""
    return tau + placement(a.facial_at) - placement(a.audio_at)


def cmd_scan(a):
    lines, _, rows, times = read_record(a.facial)
    mouth = mouth_values(lines, rows).sum(axis=1)
    rms, sr = vocal_rms(a.vocals)
    t_of_tau = times + placement(a.facial_at)
    T0, T1 = max(t_of_tau[0], 0.0), t_of_tau[-1]
    per = int(round(a.step / WIN))
    out = []
    T = T0
    while T < T1:
        m = (t_of_tau >= T) & (t_of_tau < T + a.step)
        mm = mouth[m].mean() if m.any() else 0.0
        w0 = int((T - placement(a.audio_at)) / WIN)
        seg = rms[max(w0, 0):max(w0 + per, 0)]
        db = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-9) if len(seg) else -120.0
        out.append((T, mm, db))
        T += a.step
    if a.show:
        lo, hi = map(float, a.show.split("-"))
        for T, mm, db in out:
            if lo <= T <= hi:
                print(f"T {T:7.1f}  mouth {mm:.2f}  vocal {db:6.1f} dB  " + "#" * int(mm * 30))
        return
    segs = []
    for T, mm, db in out:
        if db < a.th and mm > a.mouth:
            if segs and T - segs[-1][1] <= a.step + 1e-6:
                segs[-1][1] = T
                segs[-1][2].append(mm)
            else:
                segs.append([T, T, [mm]])
    print(f"vocals {sr} Hz. Timeline の区間で、歌声 < {a.th} dB なのに口の平均 > {a.mouth} が {a.min_len} 秒以上続く所:")
    n = 0
    for s, e, ms in segs:
        if e - s + a.step >= a.min_len:
            n += 1
            print(f"  T {s:7.1f}–{e + a.step:7.1f}s ({e - s + a.step:4.1f}s)  {int(s // 60)}:{s % 60:04.1f}  口の平均 {np.mean(ms):.2f}")
    print(f"{n} segments")


def cmd_gate(a):
    lines, nl, rows, times = read_record(a.facial)
    rms, sr = vocal_rms(a.vocals)
    voiced = 20 * np.log10(rms + 1e-9) >= a.th
    k = int(round(a.pad / WIN))
    voiced = np.convolve(voiced.astype(float), np.ones(2 * k + 1), mode="same") > 0  # 口の開き始め・閉じ終わりを切らない余白
    f = max(1, int(round(a.fade / WIN)))
    gate = np.convolve(voiced.astype(float), np.ones(f) / f, mode="same")  # 0/1 の境目をなめらかに

    outside = 0

    def gate_at(tau):
        nonlocal outside
        i = wav_time(a, tau) / WIN
        if i < 0 or i >= len(gate) - 1:
            outside += 1
            return 0.0  # 歌声の外（音が始まる前・終わった後）は歌声なし
        i0 = int(i)
        r = i - i0
        g = float(gate[i0] * (1 - r) + gate[i0 + 1] * r)
        return 1.0 if g > 1.0 - 1e-6 else g  # 移動平均の丸めで 0.9999999 になった所を、歌っている間として扱う

    total = removed = 0.0
    changed = 0
    for tau, r in zip(times, rows):
        g = gate_at(tau)
        for j in r:
            v = float(lines[j][6:])
            total += v
            if g < 1.0 and v != 0.0:
                nv = v * g
                removed += v - nv
                changed += 1
                lines[j] = "    - " + (repr(round(nv, 6)) if nv != 0 else "0")
    src = Path(a.facial)
    dst = Path(a.out) if a.out else src.with_name(src.stem + "_VoGate.asset")
    text = nl.join(lines)
    text = re.sub(r"(?m)^  m_Name: [^\r\n]*", "  m_Name: " + dst.stem, text, count=1)
    dst.write_text(text, encoding="utf-8", newline="")
    dst_meta = Path(str(dst) + ".meta")
    if dst_meta.exists():
        # 作り直し: 既にある複製の GUID を引き継ぐ（Timeline のクリップが指しているので、変えると参照が切れる）
        note = "kept the GUID of the existing copy"
    else:
        with open(str(src) + ".meta", encoding="utf-8", newline="") as f:  # 改行（CRLF / LF）を元のまま写す
            meta = f.read()
        dst_meta.write_text(re.sub(r"guid: [0-9a-f]{32}", "guid: " + uuid.uuid4().hex, meta, count=1), encoding="utf-8", newline="")
        note = "new GUID; swap the Timeline clip to this asset"
    print(f"vocals {sr} Hz, voiced {voiced.mean() * 100:.1f}% of the vocal file")
    print(f"frames {len(times)}, mouth values changed {changed}, removed {removed / max(total, 1e-9) * 100:.2f}% of the mouth total")
    if outside:
        print(f"{outside} frames are outside the vocal file (before the 2Mix starts or after it ends) -> their mouth was set to 0")
    print(f"-> {dst} ({note})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "gate"):
        s = sub.add_parser(name)
        s.add_argument("facial")
        s.add_argument("vocals")
        s.add_argument("--facial-at", required=True, help="表情のクリップの start,clipIn（Timeline）")
        s.add_argument("--audio-at", required=True, help="2Mix のクリップの start,clipIn（Timeline）")
        s.add_argument("--th", type=float, default=-50.0, help="歌声ありとみなす大きさ（dB）。AZKi の歌の無い間は -60〜-80 dB")
    s = sub.choices["scan"]
    s.add_argument("--mouth", type=float, default=0.05,
                   help="口が開いているとみなす A〜O の合計の平均（0〜1）。AZKi の間奏のパクパクは 0.06〜0.28 だった")
    s.add_argument("--step", type=float, default=0.5)
    s.add_argument("--min-len", type=float, default=1.0)
    s.add_argument("--show", help="a-b（Timeline 秒）を 1 行ずつ")
    s = sub.choices["gate"]
    s.add_argument("--pad", type=float, default=0.15)
    s.add_argument("--fade", type=float, default=0.1)
    s.add_argument("--out")
    a = p.parse_args()
    {"scan": cmd_scan, "gate": cmd_gate}[a.cmd](a)


if __name__ == "__main__":
    main()
