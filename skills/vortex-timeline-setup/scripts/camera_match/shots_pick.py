"""ショット一覧から、カメラごとに長い順に N 本（MIN_DUR 秒以上）を選び、カメラを巡る順に並べる（途中で止めても全カメラに数が揃う）。
usage: python shots_pick.py <key> <N>   → shots_<key>_pick.json
"""
import json
import sys
from collections import defaultdict

MIN_DUR = 1.5  # 撮る時刻はショットの中ほど。前後 0.75 秒あれば、記録とカットのずれ（~0.1 秒）や 4 コマの待ちでも隣のショットに掛からない
key, n = sys.argv[1], int(sys.argv[2])
shots = json.load(open(f'shots_{key}.json'))
by = defaultdict(list)
for s in shots:
    if s['end'] - s['start'] >= MIN_DUR and s['start'] > 0:
        by[s['index']].append(s)
for k in by:
    by[k].sort(key=lambda s: s['end'] - s['start'], reverse=True)
    by[k] = by[k][:n]
out = []
for i in range(n):
    for k in sorted(by):
        if i < len(by[k]):
            out.append(by[k][i])
json.dump(out, open(f'shots_{key}_pick.json', 'w'), indent=1)
print(key, 'picked', len(out), {k: len(v) for k, v in sorted(by.items())})
