"""選んだショットのうち、指定カメラの先頭 n 本を試し用の json に書き出す。usage: python pick_test.py <key> <cams csv> <n> <out.json>"""
import json
import sys

key, cams, n, out = sys.argv[1], [int(x) for x in sys.argv[2].split(',')], int(sys.argv[3]), sys.argv[4]
p = json.load(open(f'shots_{key}_pick.json'))
sel = []
for c in cams:
    sel += [s for s in p if s['index'] == c][:n]
json.dump(sel, open(out, 'w'), indent=1)
print(out, len(sel))
