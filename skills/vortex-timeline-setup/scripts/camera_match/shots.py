"""記録（activeId・reserveId・fade）から、番組に出ているカメラのショット一覧を Timeline 時刻で作る。
番組に出ているのは fade < 0.5 なら activeId（PGM 側）、0.5 以上なら reserveId（PRV 側）とする。
カメラ記録の時刻 c と Timeline 時刻 T の関係: c = CLIP_IN + SPEED * T（Azuki-Timeline のカメラのクリップ）。
"""
import json

import numpy as np

CLIP_IN, SPEED = 1.6157, 1.0000356
d = json.load(open('cam_curves.json'))
act = d['activeId'][0]['keys']
res = d['reserveId'][0]['keys']
fad = d['fade'][0]['keys']
t = np.array([k[0] for k in act])
a = np.array([k[1] for k in act])
r = np.interp(t, [k[0] for k in res], [k[1] for k in res])
f = np.interp(t, [k[0] for k in fad], [k[1] for k in fad])
onair = np.where(f < 0.5, a, np.round(r)).astype(int)
shots = []
start = 0
for i in range(1, len(t) + 1):
    if i == len(t) or onair[i] != onair[start]:
        c0, c1 = t[start], t[i - 1] if i < len(t) else t[-1]
        shots.append({'index': int(onair[start]), 'start': (c0 - CLIP_IN) / SPEED, 'end': (c1 - CLIP_IN) / SPEED})
        start = i
shots = [s for s in shots if s['end'] > 0]
json.dump(shots, open('shots.json', 'w'), indent=1)
print('shots', len(shots))
from collections import defaultdict
by = defaultdict(list)
for s in shots:
    by[s['index']].append(s)
for k in sorted(by):
    L = sorted(by[k], key=lambda s: s['end'] - s['start'], reverse=True)
    print(k, 'shots', len(by[k]), 'longest', [(round(s['start'], 2), round(s['end'] - s['start'], 2)) for s in L[:4]])
