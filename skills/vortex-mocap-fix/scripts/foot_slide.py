# MotionScan の bin 2 本（例: Foot IK Off / On、直す前 / 後）で、着いている足の「滑り」と膝の様子を比べる。
# 接地 = つま先の高さが低く（各足の下位 30% 以内 + 2 cm）、つま先の水平の速さが 0.3 m/s 未満のコマが 0.2 秒以上続く区間。
# 滑り = 接地区間の中で、つま先が水平に動いた道のり（mm）。膝 = 膝の曲がり（股関節→膝→足首の角度）と、膝の内向き（左右の膝の間隔 − 左右の足首の間隔）。
# 使い方: python foot_slide.py <A の bin> <B の bin> [A の名前,B の名前（既定 Off,On）]
# 目安（エルセ 1312〜1550 秒、2026-10-16）: Foot IK Off 毎秒 60〜63 mm → On 13〜15 mm。膝の内向き 平均 4 → 13 mm・曲がり 15° → 26°。
# 接地の判定は緩い（すり足や踏み替えも「1 回の接地」に入り、1 回で 1 m の「滑り」になることがある）。同じ区間の 2 本を比べるためにだけ使う。
import json, sys
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def load(path):
    meta = json.load(open(path + '.json', encoding='utf-8'))
    b = meta['bones']
    a = np.fromfile(path, dtype=np.float32).reshape(-1, 1 + 7 * len(b))
    return a[:, 0].astype(float), {n: a[:, 1 + 7 * i:4 + 7 * i].astype(float) for i, n in enumerate(b)}, float(meta.get('fps', 60))

def contacts(toe, fps):
    h = toe[:, 1]
    v = np.r_[0, np.linalg.norm(np.diff(toe[:, [0, 2]], axis=0), axis=1) * fps]
    low = h < np.percentile(h, 30) + 0.02
    m = low & (v < 0.3)
    segs = []
    s = None
    for i, x in enumerate(np.r_[m, False]):
        if x and s is None: s = i
        if not x and s is not None:
            if i - s >= int(0.2 * fps): segs.append((s, i))
            s = None
    return segs

def unit(v): return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

def analyze(path):
    t, P, fps = load(path)
    out = {'t': t}
    for side in ('Left', 'Right'):
        toe = P[side + 'Toes']
        segs = contacts(toe, fps)
        slides = []
        for s, e in segs:
            d = np.linalg.norm(np.diff(toe[s:e][:, [0, 2]], axis=0), axis=1).sum() * 1000
            slides.append((t[s], t[e - 1], d))
        h, k, f = P[side + 'UpperLeg'], P[side + 'LowerLeg'], P[side + 'Foot']
        bend = np.degrees(np.arccos(np.clip(np.sum(unit(k - h) * unit(f - k), axis=1), -1, 1)))
        out[side] = dict(slides=slides, bend=bend)
    ksep = np.linalg.norm((P['LeftLowerLeg'] - P['RightLowerLeg'])[:, [0, 2]], axis=1)
    asep = np.linalg.norm((P['LeftFoot'] - P['RightFoot'])[:, [0, 2]], axis=1)
    out['inward'] = (asep - ksep) * 1000  # 正 = 膝が足首より内側に寄っている（mm）
    return out

if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
    sys.exit('使い方: python foot_slide.py <A の bin> <B の bin> [A の名前,B の名前（既定 Off,On）]（bin は MotionScan.ScanLegs の出力。同じ区間・同じ fps で撮る）')
A, B = analyze(sys.argv[1]), analyze(sys.argv[2])
if len(A['t']) != len(B['t']) or abs(A['t'][0] - B['t'][0]) > 1e-3:
    sys.exit(f'2 本の区間が違う（A {A["t"][0]:.2f}s・{len(A["t"])} コマ / B {B["t"][0]:.2f}s・{len(B["t"])} コマ）。同じ区間で撮り直す')
NA, NB = (sys.argv[3].split(',') if len(sys.argv) > 3 else ['Off', 'On'])
W = max(len(NA), len(NB))
print(f'区間 {A["t"][0]:.0f}〜{A["t"][-1]:.0f} 秒')
for side in ('Left', 'Right'):
    for name, X in ((NA.ljust(W), A), (NB.ljust(W), B)):
        s = np.array([x[2] for x in X[side]['slides']]) if X[side]['slides'] else np.zeros(1)
        dur = sum(x[1] - x[0] for x in X[side]['slides'])
        print(f'{side:5s} {name}: 接地 {len(X[side]["slides"]):3d} 回・{dur:6.1f} 秒  滑り 合計 {s.sum():7.0f} mm  1 回の中央値 {np.median(s):5.1f} mm  最大 {s.max():6.1f} mm  '
              f'(1 秒あたり {s.sum() / max(dur, 1e-6):5.1f} mm)')
for name, X in ((NA.ljust(W), A), (NB.ljust(W), B)):
    inw = X['inward']
    print(f'膝の内向き {name}: 平均 {inw.mean():6.1f} mm  p95 {np.percentile(inw, 95):6.1f} mm  最大 {inw.max():6.1f} mm | '
          f'膝の曲がり 左 平均 {X["Left"]["bend"].mean():.1f}° 右 {X["Right"]["bend"].mean():.1f}°')
# 差が大きい時刻（B と A の膝の内向きの差、A で滑りの大きい接地）
d = B['inward'] - A['inward']
pick = []
for k in np.argsort(-np.abs(d)):  # 大きい順に、互いに 1 秒以上離れた 5 つ（同じ動きの続くコマを並べない）
    if all(abs(A['t'][k] - A['t'][j]) >= 1.0 for j in pick):
        pick.append(k)
    if len(pick) == 5:
        break
print(f'{NB} と {NA} で膝の内向きの差が大きい時刻:', ', '.join(f'{A["t"][k]:.1f}s ({d[k]:+.0f} mm)' for k in sorted(pick)))
for side in ('Left', 'Right'):
    big = sorted(A[side]['slides'], key=lambda x: -x[2])[:4]
    print(f'{side} の {NA} で滑りの大きい接地:', ', '.join(f'{s:.1f}-{e:.1f}s {v:.0f}mm' for s, e, v in big))
