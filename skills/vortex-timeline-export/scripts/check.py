# 書き出した動画が「中身のある映像か」を確かめる。
#
#   python check.py <mp4> [<mp4> ...] [--out <フレーム画像の保存先ディレクトリ>]
#
# 解像度・フレーム数・尺と、途中の 1 フレームの平均輝度を出し、確認用の縮小画像を保存する。
# 真っ黒（録画元の RenderTexture に何も描かれていない）は平均輝度でまず弾き、
# 残りは保存した画像を自分で開いて、余計なキャラが映っていないかを見る。
import argparse
import json
import os
import re
import subprocess
import sys

# フレーム内の輝度の最大と最小の差がこれ以下なら「無地」（何も描かれていない）とみなす。
# 明るさでは判定しない。H.264 は多くの場合 16〜235 の範囲で記録されるため、真っ黒でも平均は 16 になる。
# 実測: 無地の黒 = 差 0（YMIN=YMAX=16）、中身のあるテスト映像 = 差 241。
# 1 は丸めの ±1 を吸収するためだけの余裕。
FLAT_SPREAD = 1

ap = argparse.ArgumentParser()
ap.add_argument("videos", nargs="+")
ap.add_argument("--out", default=".")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

bad = 0
for v in a.videos:
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_frames:format=duration,size",
         "-of", "json", v], capture_output=True, text=True).stdout or "{}")
    if not info.get("streams"):
        print(f"NG(read) {v}: cannot read (still writing, or broken)")
        bad += 1
        continue
    s, f = info["streams"][0], info["format"]
    dur = float(f.get("duration", 0))
    mid = dur / 2

    png = os.path.join(a.out, os.path.splitext(os.path.basename(v))[0] + "_mid.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", v,
                    "-frames:v", "1", "-vf", "scale=960:-1", png], check=False)

    stats = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", v, "-frames:v", "1",
         "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-"],
        capture_output=True, text=True).stdout
    def stat(key):
        m = re.search(r"lavfi\.signalstats\.%s=([\d.]+)" % key, stats)
        return float(m.group(1)) if m else -1.0

    ymin, yavg, ymax = stat("YMIN"), stat("YAVG"), stat("YMAX")
    spread = ymax - ymin

    verdict = "OK" if spread > FLAT_SPREAD else "NG(flat)"
    if verdict != "OK":
        bad += 1
    print(f"{verdict:8} {os.path.basename(v)}: {s['width']}x{s['height']} "
          f"{s.get('nb_frames', '?')}f {dur:.2f}s {int(f.get('size', 0)) / 1024 / 1024:.0f}MB "
          f"mid@{mid:.1f}s Y={ymin:.0f}-{ymax:.0f} (avg {yavg:.0f}) -> {png}")

sys.exit(1 if bad else 0)
