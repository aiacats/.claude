"""カメラ記録（Recorder_camera の .anim、YAML で数 GB）を読む・番組映像と照合する（Unity 不要）。

  names    <anim>                  記録が持つカメラのノード（「番号_カメラ名」）の一覧
  order    <anim> <scene>          記録の並びと、シーンのスイッチャー（_inputCameras）の並びを番号ごとに比べる。
                                   再生はカーブを「Cameras/<番号>_<今のシーンのカメラ名>」で当てるので、違う番号は番組カメラが原点・画角 0（真っ黒）になる
  segments <anim> [--ids 13,14] [--clip start,clipIn,ts]
                                   PGM（activeId）・PRV（reserveId）がその番号の区間と合計秒。--clip で Timeline 時刻も出す
  match    <anim> <番組映像> --audio <2Mix> --audio-at start[,clipIn] --clip start,clipIn,ts [--at S1,S2,...] [--dur 40]
                                   番組映像の窓ごとに、音で映像 → Timeline の対応を測り、映像のカットと記録の切り替え（fade）を突き合わせる。
                                   今の置き方でのずれ（カットが記録より何秒遅い/早い）と、合わせ直すなら clipIn・timeScale を出す

記録の中身: 全カメラの位置・回転・FoV のカーブ（Cameras/<番号>_<名前>）と、activeId（PGM の番号）・reserveId（PRV）・fade（0→1 で PGM と PRV が入れ替わる）。
番組の切り替えは activeId ではなく fade に出る（瞬時のカットは 1 キーで 0↔1 に跳ぶ。ディゾルブは約 1 秒かけて動く）。
読み取りは 1 回目に数十秒〜数分かかる（2GB で約 1 分）。結果は %TEMP%/camrec_cache に置き、ファイルの大きさと時刻が同じなら使い回す。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or r"C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffprobe.exe"
WANT = ("activeId", "reserveId", "fade")


def scan(anim):
    """{'names': {番号: 名前}, 'curves': {attr: [[t, v], ...]}}（m_FloatCurves の activeId・reserveId・fade）。"""
    st = os.stat(anim)
    key = hashlib.sha1(f"{os.path.abspath(anim)}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    cache = os.path.join(tempfile.gettempdir(), "camrec_cache", key + ".json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    names, curves, keys = {}, {}, []
    t, section = None, None
    re_path = re.compile(r"^\s+path: Cameras/(\d+)_(.*?)\s*$")
    with open(anim, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("  m_") and line.rstrip().endswith(":"):
                section = line.strip()[:-1]
                continue
            s = line.lstrip()
            if s.startswith("- curve:"):
                keys = []
            elif s.startswith("time: "):
                t = float(s[6:])
            elif s.startswith("value: ") and t is not None:
                try:
                    keys.append((t, float(s[7:])))
                except ValueError:
                    pass
                t = None
            elif s.startswith("attribute: "):
                attr = s[11:].strip()
                if section == "m_FloatCurves" and attr in WANT and attr not in curves:
                    curves[attr] = keys
                keys = []
            elif s.startswith("path: Cameras/"):
                m = re_path.match(line)
                if m:
                    names[int(m.group(1))] = m.group(2)
    out = {"names": {str(k): v for k, v in sorted(names.items())}, "curves": curves}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def cmd_names(a):
    for k, v in scan(a.anim)["names"].items():
        print(f"{int(k):3d}  {v}")


def switcher_order(scene):
    """シーンの _inputCameras（VirtualCameraSwitcher）の並びを GameObject 名で返す。"""
    text = open(scene, encoding="utf-8").read()
    docs = {}
    for m in re.finditer(r"(?m)^--- !u!(\d+) &(-?\d+)[^\n]*\n", text):
        docs[m.group(2)] = m.end()
    order = list(docs)
    bodies = {}
    for i, k in enumerate(order):
        end = docs[order[i + 1]] if i + 1 < len(order) else len(text)
        bodies[k] = text[docs[k]:end]

    def go_of(fid):
        m = re.search(r"m_GameObject: \{fileID: (-?\d+)\}", bodies.get(fid, ""))
        return m.group(1) if m else fid

    def name(go):
        m = re.search(r"(?m)^  m_Name: (.*)$", bodies.get(go, ""))
        return m.group(1).strip() if m else "?"
    out = []
    for k, b in bodies.items():
        if "  _inputCameras:" in b:
            lst = b.split("  _inputCameras:", 1)[1]
            lst = re.match(r"\r?\n((?:  - \{fileID: -?\d+\}\r?\n)*)", lst)
            ids = re.findall(r"fileID: (-?\d+)", lst.group(1)) if lst else []
            out.append((k, [name(go_of(x)) for x in ids]))
    return out


def cmd_order(a):
    rec = {int(k): v for k, v in scan(a.anim)["names"].items()}
    sw = switcher_order(a.scene)
    if not sw:
        sys.exit("no _inputCameras in the scene")
    for comp, names in sw:
        print(f"switcher {comp}: {len(names)} cameras / record {len(rec)} cameras")
        bad = 0
        for i in range(max(len(names), max(rec) + 1 if rec else 0)):
            r, s = rec.get(i, "-"), names[i] if i < len(names) else "-"
            ok = r == s
            bad += not ok
            print(f"  {i:3d}  {'OK ' if ok else 'NG '} record {r:32s} scene {s}")
        print(f"  mismatches: {bad} (those numbers go black when they are on air)")


def segments(keys):
    out, cur, start = [], None, None
    for t, v in keys:
        iv = int(round(v))
        if iv != cur:
            if cur is not None:
                out.append((cur, start, t))
            cur, start = iv, t
    if keys:
        out.append((cur, start, keys[-1][0]))
    return out


def clip_map(clip):
    st, ci, ts = (list(map(float, clip.split(","))) + [0.0, 1.0])[:3]
    return lambda c: st + (np.asarray(c) - ci) / ts


def cmd_segments(a):
    cv = scan(a.anim)["curves"]
    ids = {int(x) for x in a.ids.split(",")} if a.ids else None
    to_t = clip_map(a.clip) if a.clip else None
    for attr, label in (("activeId", "PGM"), ("reserveId", "PRV")):
        segs = segments(cv[attr])
        used = sorted({s[0] for s in segs})
        print(f"{label}: numbers used {used}")
        total = {}
        for idx, s0, s1 in segs:
            total[idx] = total.get(idx, 0.0) + s1 - s0
            if ids and idx in ids and label == "PGM":
                tl = f"  Timeline {float(to_t(s0)):9.2f}–{float(to_t(s1)):9.2f}" if to_t else ""
                print(f"  {label} {idx:2d}: record {s0:9.2f}–{s1:9.2f} ({s1 - s0:5.1f}s){tl}")
        if ids:
            print(f"  {label} total for {sorted(ids)}: {sum(v for k, v in total.items() if k in ids):.1f}s in {sum(1 for x in segs if x[0] in ids)} segments")


def fade_cuts(keys):
    """瞬時のカット（前後のキーで 0↔1 に跳ぶ）の時刻 = 跳ぶ前後のキーの中点。ディゾルブは数えない（映像の差分で拾えない）。"""
    ev, dis = [], 0
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        lo0, hi0, lo1, hi1 = v0 <= 0.02, v0 >= 0.98, v1 <= 0.02, v1 >= 0.98
        if (lo0 and hi1) or (hi0 and lo1):
            ev.append((t0 + t1) / 2)
        elif (lo0 or hi0) and not (lo1 or hi1):
            dis += 1
    return np.array(ev), dis


def read_window(url, s0, dur, sr, w=64, h=36):
    tmp = os.path.join(tempfile.gettempdir(), f"camrec_audio_{os.getpid()}.raw")
    cmd = [FFMPEG, "-v", "error", "-ss", f"{s0:.3f}", "-t", f"{dur:.3f}", "-i", url,
           "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-y", tmp,
           "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h * w).astype(np.float32)
    aud = np.fromfile(tmp, dtype=np.float32).astype(np.float64)
    os.remove(tmp)
    return fr, aud


def video_fps(url):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate", "-of", "csv=p=0", url], capture_output=True, text=True).stdout.strip()
    n, d = (out.split("/") + ["1"])[:2]
    return float(n) / float(d) if out else 60.0


def cuts_of(fr, s0, fps):
    """カット = 隣のコマとの絵柄の相関（明るさに依らない）が、前後に比べて 1 コマだけ大きく落ちる所。"""
    x = fr - fr.mean(axis=1, keepdims=True)
    x /= np.linalg.norm(x, axis=1, keepdims=True) + 1e-6
    d = 1 - (x[1:] * x[:-1]).sum(axis=1)
    out = []
    for i in range(len(d)):
        nb = np.concatenate([d[max(0, i - 4):i], d[i + 1:i + 5]])
        if d[i] > 0.15 and d[i] > 4 * (np.sort(nb)[-2] if len(nb) > 1 else 0) + 0.02:
            t = s0 + (i + 1) / fps  # カット後の最初のコマ
            if not out or t - out[-1] > 0.3:
                out.append(t)
    return out


def cmd_match(a):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sync import Ref, read_audio
    sr = 8000
    src = read_audio(a.audio, sr)
    src = src - src.mean()
    ref = Ref(src, int(a.dur * sr) + 1)
    ast, aci = (list(map(float, a.audio_at.split(","))) + [0.0])[:2]
    fps = video_fps(a.video)
    starts = [float(x) for x in a.at.split(",")]
    pm, cuts_p = [], []
    for s0 in starts:
        fr, aud = read_window(a.video, s0, a.dur, sr)
        k, c, _ = ref.find(aud)
        m = (ast + k / sr - aci) - s0  # T = P + M
        c_list = cuts_of(fr, s0, fps)
        pm.append((s0, m, c))
        cuts_p += c_list
        print(f"window P={s0:.1f}: T = P {m:+.4f} (corr {c:.3f}), cuts {len(c_list)}", flush=True)
    good = np.array([(p, m) for p, m, c in pm if c >= 0.3])
    if len(good) == 0:
        sys.exit("audio did not match in any window")
    slope, icpt = np.polyfit(good[:, 0], good[:, 1], 1) if len(good) > 1 else (0.0, good[0, 1])
    cuts_t = np.array(sorted(p + icpt + slope * p for p in cuts_p))
    ev, dis = fade_cuts(scan(a.anim)["curves"]["fade"])
    st, ci, ts = (list(map(float, a.clip.split(","))) + [0.0, 1.0])[:3]
    pos = st + (ev - ci) / ts
    order = np.argsort(pos)
    pos, evs = pos[order], ev[order]
    j = np.clip(np.searchsorted(pos, cuts_t), 1, len(pos) - 1)
    near = np.where(np.abs(cuts_t - pos[j - 1]) < np.abs(cuts_t - pos[j]), j - 1, j)
    err = cuts_t - pos[near]  # + = 映像のカットが記録の切り替えより遅い
    ok = np.abs(err) < 2.0
    print(f"record: {len(ev)} cuts ({dis} dissolves not counted); video: {len(cuts_t)} cuts in {len(starts)} windows")
    if not ok.any():
        sys.exit("no video cut within 2 s of a recorded cut; check --clip and --audio-at")
    hist, edges = np.histogram(err[ok], bins=np.arange(-2, 2.01, 0.01))
    mode = edges[np.argmax(hist)] + 0.005
    close = np.abs(err - mode) < 0.05
    print(f"now: video cuts are {mode:+.3f} s from the recorded cuts (mode); {int(close.sum())}/{len(cuts_t)} within ±50 ms of it:"
          f" mean {err[close].mean() * 1000:+.1f} ms sd {err[close].std() * 1000:.1f} ms max |{np.abs(err[close] - err[close].mean()).max() * 1000:.1f}| ms")
    if close.sum() >= 3:
        c, t = evs[near[close]], cuts_t[close]
        b, a0 = np.polyfit(c, t, 1)
        new_ts = 1 / b
        print(f"fit T = {a0:+.4f} + {b:.7f} × c  (resid max {np.abs(t - (a0 + b * c)).max() * 1000:.1f} ms)")
        print(f"to match with start {st}: clipIn {(st - a0) * new_ts:.4f}, timeScale {new_ts:.7f}"
              f"   (only shifting: clipIn {ci + err[close].mean() * -ts:.4f} keeping timeScale {ts})")
    print("cuts (T, err s):", " ".join(f"{float(x):.2f}/{float(e):+.3f}" for x, e in zip(cuts_t, err)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("names"); s.add_argument("anim")
    s = sub.add_parser("order"); s.add_argument("anim"); s.add_argument("scene")
    s = sub.add_parser("segments"); s.add_argument("anim"); s.add_argument("--ids"); s.add_argument("--clip")
    s = sub.add_parser("match"); s.add_argument("anim"); s.add_argument("video")
    s.add_argument("--audio", required=True); s.add_argument("--audio-at", required=True); s.add_argument("--clip", required=True)
    s.add_argument("--at", required=True, help="番組映像の窓の開始秒（カンマ区切り）"); s.add_argument("--dur", type=float, default=40.0)
    a = p.parse_args()
    {"names": cmd_names, "order": cmd_order, "segments": cmd_segments, "match": cmd_match}[a.cmd](a)


if __name__ == "__main__":
    main()
