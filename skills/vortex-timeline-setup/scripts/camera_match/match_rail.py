"""ショットごとに、参考 mov の絵へ合う railOffset と FoV（と残りのずれを埋めるパン・ティルト）を探す。

1 ショットの流れ:
  1. 参考 mov の、ショットの中ほどの時刻（Timeline + 0.132 秒）のコマを読み、YOLOv8 の人物セグメンテーションでキャラのマスクを取る。
  2. Unity（CamProbe.Capture）で同じ時刻を、railOffset × ズームの候補ごとに撮る（キャラだけのマスクも）。
  3. 点数 = キャラの重なり（IoU） + BG_WEIGHT × キャラ以外の輪郭の一致（正規化相互相関）。
     キャラの大きさだけではドリーで寄ったのかズームで寄ったのかが分からないため、トラスや床などの線の位置で見分ける
     （LED の中身は参考映像と違うが、トラスや床の位置は同じ）。最も高い組を選ぶ。点の差が TIE 以内なら、ずらしの小さい方を選ぶ。
     粗く（rail 0.05 刻み × ズーム 6 段）探してから、その近くを細かく探す。
  4. 選んだ絵のマスクと mov のマスクの外接矩形の中心のずれを、パン・ティルト（カメラ基準の回転）に直す。
     キャラが画面の端で切れているときは直さない。IoU が MIN_IOU 未満のショットは「合わせられず」にする。

使い方: <segenv の python> match_rail.py <mov の直リンク> <shots.json> <出力 json> [index をカンマ区切り] [最初の n ショット]
"""
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request

import cv2
import numpy as np
from ultralytics import YOLO

B = 'http://localhost:%d/mcp/tools/' % json.load(open(r'D:/_ProjectBLUE/Project/SinkaiFes2026/ShinkaiFes2026/Library/ClaudeCodeMCP/endpoint.json'))['port']
FFMPEG = r'C:\Users\komao\tools\ffmpeg-7.1-full_build\bin\ffmpeg.exe'
# mov（SW）の秒 = Timeline の秒 + TL_TO_MOV。組ごとに sw_sync.py の結果から渡す:
#   音で測った T = S + M と、カットが記録の切り替えより err 秒ずれていること（カメラの絵を記録どおりの時点で比べるため）から
#   TL_TO_MOV = -M + err
TL_TO_MOV = float(os.environ['TL_TO_MOV'])
W, H = 640, 360
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'match_work_' + os.environ['KEY'])
MIN_MASK = int(W * H * 0.001)  # キャラが写っているとみなす最小面積（640x360 の 0.1%）
MIN_SHIFT = W * 0.02  # 位置のずれをパン・ティルトに回す下限（幅の 2%）
EDGE = 3  # 外接矩形が画面の端からこれ以内なら「切れている」
BG_WEIGHT = 0.5  # キャラ以外の線の一致の重み（IoU と同じ 0〜1 の尺度で、キャラを主にする）
TIE = 0.01  # 点の差がこれ以内なら、ずらしの小さい方を選ぶ
MIN_IOU = 0.4  # これ未満は合わせられなかったとみなす
# 止まったのは 1.7GB 前後（2026-10-12/13）。ただしこの数値は日によって土台が違う（2026-10-14 はタグ合計 1.24GB でも 1.8GB を示し、
# lockcheck は 1024MB まで通った）。本当の判定は lockcheck なので、しきい値は env で今の土台 + 余裕にする
POOL_LIMIT_MB = int(os.environ.get('POOL_LIMIT_MB', '1620'))
COARSE_RAILS = [float(x) for x in os.environ['RAILS'].split(',')] if os.environ.get('RAILS') else [round(x, 3) for x in np.arange(-0.5, 0.5001, 0.1)]
COARSE_ZOOMS = [float(x) for x in os.environ['ZOOMS'].split(',')] if os.environ.get('ZOOMS') else [0.35, 0.5, 0.7, 1.0, 1.4, 2.0, 2.8]

url, shots_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
only = set(int(x) for x in sys.argv[4].split(',')) if len(sys.argv) > 4 and sys.argv[4] else None
limit = int(sys.argv[5]) if len(sys.argv) > 5 else None
model = YOLO(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yolov8m-seg.pt'))


def inv(m, args):
    req = urllib.request.Request(B + 'invoke_method', json.dumps({'typeName': 'CamProbe', 'methodName': m, 'args': args}).encode(),
                                 {'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=300))['data']['result']


GUI = os.path.expanduser(r'~\.claude\skills\windows-gui-testing\scripts\gui.ps1')
UNITY_HWND = os.environ.get('UNITY_HWND', '')


def capture(t, idx, rails, zooms, tag):
    # 背面の Unity はフレームが進まず撮影が終わらないため、毎回前面に出す
    if UNITY_HWND:
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', GUI, 'focus', UNITY_HWND],
                       capture_output=True)
    inv('Clear', [])
    # Timeline が終端まで再生されると止まり、記録の再生が無くなる（no playback frame）。毎回再生し直す
    if os.environ.get('DIRECTOR'):
        inv('SetDirector', [os.environ['DIRECTOR']])
    inv('SetZooms', [','.join(f'{z:.3f}' for z in zooms)])
    inv('Capture', [t, idx, ','.join(f'{r:.3f}' for r in rails), WORK, tag])
    for _ in range(600):
        st = inv('State', [])
        if ('done ' + tag) in st:
            return st
        time.sleep(0.5)
    raise RuntimeError('capture timeout ' + tag)


def fname(tag, r, z, mask=False):
    s = f'{r:+.3f}'
    s = '0.000' if s in ('+0.000', '-0.000') else s
    suffix = '' if abs(z - 1) < 1e-6 else f'_z{z:.3f}'
    return os.path.join(WORK, f'{tag}_r{s}{suffix}{"_mask" if mask else ""}.png')


def unity_mask(tag, r, z):
    m = cv2.imread(fname(tag, r, z, True))
    if m is None:
        return None
    m = (m.max(axis=2) > 1).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0


def mov_masks(img):
    r = model.predict(img, classes=[0], conf=0.1, verbose=False, imgsz=640)[0]
    if r.masks is None:
        return []
    return [cv2.resize((m > 0.5).astype(np.uint8), (W, H)) > 0 for m in r.masks.data.cpu().numpy()]


def grad_small(img):
    g = cv2.cvtColor(cv2.resize(img, (W // 2, H // 2)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def ncc(a, b, m):
    a = a[m]; b = b[m]
    if a.size < 100:
        return 0.0
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / (math.sqrt(float((a * a).sum() * (b * b).sum())) + 1e-6))


def iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def evaluate(tag, combos, mms, gm_small, mov_union_small):
    out = {}
    for r, z in combos:
        um = unity_mask(tag, r, z)
        img = cv2.imread(fname(tag, r, z))
        if um is None or img is None:
            continue
        if um.sum() < MIN_MASK:
            continue
        best = (0.0, -1)
        for i, mm in enumerate(mms):
            v = iou(um, mm)
            if v > best[0]:
                best = (v, i)
        um_small = cv2.resize(um.astype(np.uint8), (W // 2, H // 2)) > 0
        bgm = ~cv2.dilate((um_small | mov_union_small).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        bg = ncc(grad_small(img), gm_small, bgm)
        out[(r, z)] = {'iou': best[0], 'mi': best[1], 'bg': bg, 'score': best[0] + BG_WEIGHT * max(bg, 0.0)}
    return out


def pick(res):
    top = max(v['score'] for v in res.values())
    near = [k for k, v in res.items() if v['score'] >= top - TIE]
    return min(near, key=lambda k: (abs(k[0]) + abs(math.log(k[1])), k))


def bbox(m):
    ys, xs = np.where(m)
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1


def clipped(b):
    return b[0] <= EDGE or b[2] <= EDGE or b[1] >= W - EDGE or b[3] >= H - EDGE


shots = json.load(open(shots_path))  # 並びはファイルの順のまま（percam_order.py で優先順にしてある）
if only is not None:
    shots = [s for s in shots if s['index'] in only]
os.makedirs(WORK, exist_ok=True)
results = json.load(open(out_path)) if os.path.exists(out_path) else []
done = {(r['index'], round(r['start'], 3)) for r in results}
n = 0
for sh in shots:
    if limit is not None and n >= limit:
        break
    if (sh['index'], round(sh['start'], 3)) in done:
        continue
    # 非ページプールが 1.7GB 前後で GPU を失う（この PC、2026-10-12 に 3 回）。手前の POOL_LIMIT_MB で止めて、結果を壊さずに抜ける
    pool = subprocess.run(['powershell', '-NoProfile', '-Command',
                           '[int]((Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).PoolNonpagedBytes/1MB)'],
                          capture_output=True, text=True).stdout.strip()
    if pool.isdigit() and int(pool) >= POOL_LIMIT_MB:
        print(f'STOP: nonpaged pool {pool} MB >= {POOL_LIMIT_MB} MB', flush=True)
        break
    n += 1
    t = (sh['start'] + sh['end']) / 2
    tag = f"s{sh['index']:02d}_{sh['start']:.2f}"
    rec = {'index': sh['index'], 'start': sh['start'], 'end': sh['end'], 't': t}
    movp = os.path.join(WORK, f'{tag}_mov.png')
    if not os.path.exists(movp):
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', f'{t + TL_TO_MOV:.3f}', '-i', url, '-frames:v', '1',
                        '-vf', f'scale={W}:{H}', movp], check=True)
    mov = cv2.imread(movp)
    mms = mov_masks(mov)
    gm_small = grad_small(mov)
    mov_union_small = cv2.resize(np.any(mms, axis=0).astype(np.uint8), (W // 2, H // 2)) > 0 if mms else np.zeros((H // 2, W // 2), bool)
    log = capture(t, sh['index'], COARSE_RAILS, COARSE_ZOOMS, tag)
    rec['probe'] = log.strip().splitlines()[-1][:300]
    fov = float(re.search(r'fov=([\d.]+)', log).group(1))
    rec['fov'] = fov
    if 'no rail' in log:
        rec['status'] = 'no rail'
    elif not mms:
        rec['status'] = 'no person in mov'
    else:
        res = evaluate(tag, [(r, z) for r in COARSE_RAILS for z in COARSE_ZOOMS], mms, gm_small, mov_union_small)
        if not res:
            rec['status'] = 'no character in unity'
        else:
            rb, zb = pick(res)
            fr = [] if os.environ.get('NOFINE') else sorted({round(min(1.0, max(-1.0, rb + d)), 3) for d in np.arange(-0.08, 0.0801, 0.02)})
            fz = sorted({round(zb * f, 3) for f in (0.84, 0.92, 1.0, 1.09, 1.19)})
            if fr:
                capture(t, sh['index'], fr, fz, tag)
            res.update(evaluate(tag, [(r, z) for r in fr for z in fz], mms, gm_small, mov_union_small))
            rb, zb = pick(res)
            v = res[(rb, zb)]
            base0 = res.get((0.0, 1.0))
            rec.update({'rail': rb, 'zoom': zb, 'iou': v['iou'], 'bg': v['bg'], 'score': v['score'],
                        'score_base': base0['score'] if base0 else None, 'iou_base': base0['iou'] if base0 else None})
            rec['fov_offset'] = math.degrees(2 * math.atan(math.tan(math.radians(fov) / 2) / zb)) - fov
            rec['pan'] = rec['tilt'] = 0.0
            if v['mi'] >= 0:
                um, mm = unity_mask(tag, rb, zb), mms[v['mi']]
                bu, bm = bbox(um), bbox(mm)
                if clipped(bu) or clipped(bm):
                    rec['residual'] = 'clipped'
                else:
                    dx = (bm[0] + bm[1]) / 2 - (bu[0] + bu[1]) / 2
                    dy = (bm[2] + bm[3]) / 2 - (bu[2] + bu[3]) / 2
                    rec['dx'], rec['dy'] = float(dx), float(dy)
                    fov2 = fov + rec['fov_offset']
                    vt = math.tan(math.radians(fov2) / 2)
                    if abs(dx) > MIN_SHIFT:
                        rec['pan'] = -math.degrees(math.atan(dx / (W / 2) * vt * W / H))
                    if abs(dy) > MIN_SHIFT:
                        rec['tilt'] = -math.degrees(math.atan(dy / (H / 2) * vt))
            rec['status'] = 'ok' if v['iou'] >= MIN_IOU else 'low'
    results.append(rec)
    json.dump(results, open(out_path, 'w'), indent=1)
    print(json.dumps({k: (round(x, 3) if isinstance(x, float) else x) for k, x in rec.items() if k != 'probe'}, ensure_ascii=False), flush=True)
