"""Unity のシーン（.unity / .prefab / .playable）を塊（--- !u!）単位で 3 方向マージする。

theirs（取り込む側。ふつうはリモート）の並びを土台に、ours（手元）で変えた・足した・消した塊を載せる。
両方が同じ塊を変えていたら、theirs で足された行がすべて ours にあり、theirs で消された行が無いときだけ ours を採る。
それ以外は本物の衝突として全部を挙げ、何も書かずに止める（どちらかの版で済ませるなら、その塊を手で選ぶ）。

使い方: python merge3.py <base> <ours> <theirs> <出力> [--prefer-ours fileID,...] [--prefer-theirs fileID,...]
  base は merge-base の版。3 つとも scene_diff.py fromgit で取り出せる。
"""
import argparse
import difflib
import sys

from unity_yaml import Index, load, parse, write

sys.stdout.reconfigure(encoding="utf-8")
p = argparse.ArgumentParser()
p.add_argument("base"); p.add_argument("ours"); p.add_argument("theirs"); p.add_argument("out")
p.add_argument("--prefer-ours", default=""); p.add_argument("--prefer-theirs", default="")
a = p.parse_args()
pref_o = {x for x in a.prefer_ours.split(",") if x}
pref_t = {x for x in a.prefer_theirs.split(",") if x}

_, bd = load(a.base)
opre, od = load(a.ours)
tpre, td = load(a.theirs)
B = {d.fid: d.text for d in bd}
O = {d.fid: d.text for d in od}
T = {d.fid: d.text for d in td}
oorder = [d.fid for d in od]
if opre != tpre:
    print("note: header differs; theirs header is used")

result = dict(T)
order = [d.fid for d in td]
taken, added, removed, conflicts = [], [], [], []
for k in oorder:
    if k in B and O[k] == B[k]:
        continue  # ours は変えていない
    if k not in B:
        if k in T and T[k] != O[k]:
            conflicts.append((k, "both added with different content"))
        elif k not in T:
            added.append(k)
        continue
    if k not in T:
        conflicts.append((k, "ours changed it, theirs removed it"))
        continue
    if T[k] == B[k] or T[k] == O[k] or k in pref_o:
        result[k] = O[k]
        taken.append(k)
        continue
    if k in pref_t:
        continue
    diff = list(difflib.ndiff(B[k].splitlines(), T[k].splitlines()))
    t_added = [l[2:] for l in diff if l.startswith("+ ")]
    t_removed = [l[2:] for l in diff if l.startswith("- ")]
    o_lines = set(O[k].splitlines())
    if all(l in o_lines for l in t_added) and not t_removed:
        result[k] = O[k]
        taken.append(k + " (superset)")
    else:
        conflicts.append((k, "both changed"))
for k in B:
    if k in O or k not in T:
        continue
    if T[k] == B[k]:
        result.pop(k)
        order.remove(k)
        removed.append(k)
    else:
        conflicts.append((k, "ours removed it, theirs changed it"))

if conflicts:
    ix = Index(od + [d for d in td if d.fid not in O])
    print(f"{len(conflicts)} conflict(s); nothing written. Decide with --prefer-ours / --prefer-theirs:")
    for k, why in conflicts:
        d = ix.by.get(k)
        label, where = ix.describe(d) if d else ("?", "")
        print(f"  {k} {label} {where}: {why}")
        if k in B and k in O and k in T:
            for side, txt in (("ours", O[k]), ("theirs", T[k])):
                lines = [l for l in difflib.unified_diff(B[k].splitlines(), txt.splitlines(), lineterm="", n=0)
                         if not l.startswith(("---", "+++", "@@"))]
                print(f"    {side}: " + " / ".join(l.strip()[:70] for l in lines[:6]))
    sys.exit(1)

# ours で足した塊は、ours の並びで直前にある塊の後ろへ入れる
for k in added:
    i = oorder.index(k)
    prev = next((oorder[j] for j in range(i - 1, -1, -1) if oorder[j] in result), None)
    order.insert(order.index(prev) + 1 if prev else len(order), k)
    result[k] = O[k]

_, docs = parse(tpre + "".join(result[k] for k in order))
write(a.out, tpre, docs)
print(f"taken from ours {len(taken)}: {taken}")
print(f"added from ours {len(added)}: {added}")
print(f"removed (ours) {len(removed)}: {removed}")
print(f"docs {len(order)} -> {a.out}")
