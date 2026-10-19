"""カメラごとに、全ショットの点数（キャラの IoU + 0.5 x キャラ以外の輪郭の一致）の合計が最大になる (rail, zoom) を、
撮影済みの格子（全ショット共通に撮った組み合わせ）から探す。記録のまま (0, 1) と、AZKi で入れた値の点も並べる。
usage: <segenv python> joint_key.py <key> [cams csv]   → joint_<key>.json
"""
import collections
import glob
import json
import math
import os
import re
import sys

import cv2
import numpy as np
from ultralytics import YOLO

W, H = 640, 360
HERE = os.path.dirname(os.path.abspath(__file__))
key = sys.argv[1]
WORK = os.path.join(HERE, 'match_work_' + key)
AZKI = {2: (0.14, 1.0), 3: (-0.04, None), 4: (0.21, 1.0), 5: (0.40, 1.0), 9: (-0.07, 1.0), 12: (0.22, 1.0)}  # Cam03 は FoV +0.24（ズーム換算はショットの画角次第）
model = YOLO(os.path.join(HERE, 'yolov8m-seg.pt'))
NAME = re.compile(r'_r([+-]?\d+\.\d+)(?:_z(\d+\.\d+))?\.png$')


def grad_small(img):
    g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(img, (W // 2, H // 2)), cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def ncc(a, b, m):
    a = a[m]; b = b[m]
    if a.size < 100:
        return 0.0
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / (math.sqrt(float((a * a).sum() * (b * b).sum())) + 1e-6))


def shot_scores(tag):
    mov = cv2.imread(os.path.join(WORK, tag + '_mov.png'))
    if mov is None:
        return None
    p = model.predict(mov, classes=[0], conf=0.1, verbose=False, imgsz=640)[0]
    mms = [] if p.masks is None else [cv2.resize((m > 0.5).astype(np.uint8), (W, H)) > 0 for m in p.masks.data.cpu().numpy()]
    gm = grad_small(mov)
    mu = cv2.resize(np.any(mms, axis=0).astype(np.uint8), (W // 2, H // 2)) > 0 if mms else np.zeros((H // 2, W // 2), bool)
    sc = {}
    for f in glob.glob(os.path.join(WORK, tag + '_r*.png')):
        if f.endswith('_mask.png'):
            continue
        m = NAME.search(f)
        r, z = float(m.group(1)), float(m.group(2) or 1.0)
        img = cv2.imread(f)
        um = cv2.imread(f[:-4] + '_mask.png')
        if img is None or um is None:
            continue
        um = cv2.morphologyEx((um.max(axis=2) > 1).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
        iou = max([float(np.logical_and(um, mm).sum() / max(1, np.logical_or(um, mm).sum())) for mm in mms] or [0.0])
        us = cv2.resize(um.astype(np.uint8), (W // 2, H // 2)) > 0
        bgm = ~cv2.dilate((us | mu).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        sc[(round(r, 3), round(z, 3))] = iou + 0.5 * max(ncc(grad_small(img), gm, bgm), 0.0)
    return sc


res = json.load(open(os.path.join(HERE, 'work', f'match_{key}.json')))
cams = sorted({r['index'] for r in res}) if len(sys.argv) < 3 else [int(x) for x in sys.argv[2].split(',')]
out = {}
for k in cams:
    rows = [r for r in res if r['index'] == k and r.get('status') not in ('no rail',)]
    if not rows:
        rr = [r for r in res if r['index'] == k]
        if rr:
            out[k] = {'status': rr[0].get('status')}
            print(k, rr[0].get('status'))
        continue
    per = []
    common = None
    for r in rows:
        sc = shot_scores(f"s{k:02d}_{r['start']:.2f}")
        if not sc:
            continue
        per.append((r, sc))
        common = set(sc) if common is None else common & set(sc)
    if not per or not common:
        continue
    tot = {kk: sum(sc[kk] for _, sc in per) / len(per) for kk in common}
    b = max(tot, key=tot.get)
    base = tot.get((0.0, 1.0))
    rails = sorted({kk[0] for kk in common if kk[1] == 1.0})
    out[k] = {'n': len(per), 'best': b, 'best_mean': tot[b], 'base_mean': base,
              'rail_profile_z1': {rr: round(tot[(rr, 1.0)], 3) for rr in rails},
              'per_shot_best': [(round(r['t'], 1), max(sc, key=sc.get), round(max(sc.values()), 3), round(sc.get((0.0, 1.0), 0), 3)) for r, sc in per]}
    print(f'cam {k}: n={len(per)} best={b} {tot[b]:.3f}  base(0,1)={base if base is None else round(base, 3)}  AZKi={AZKI.get(k)}', flush=True)
    print('   z1 profile', out[k]['rail_profile_z1'])
json.dump({str(k): {kk: (list(v) if isinstance(v, tuple) else v) for kk, v in d.items()} for k, d in out.items()},
          open(os.path.join(HERE, 'work', f'joint_{key}.json'), 'w'), indent=1, default=str)
