# シーン YAML を読み、「実際に描いているカメラ」と、その出力先（画面 or RenderTexture）を出す。
# Unity を止めていても使える（書き出し前の当たり付け用）。
#
#   python active_cameras.py <scene.unity> [--project <Unity プロジェクトのルート>]
#
# 描いているカメラ = Camera コンポーネントが有効 かつ GameObject が祖先まで全部アクティブ。
# 書き出しの録画元には、ここに出た RenderTexture を使う。名前で選ばない
# （このプロジェクトでは "GeandMainLED" が本線、"RT_Output" は誰も書かない RT だった）。
# 画面に出す UI（RawImage）がどの RT を表示しているかも併せて出す。
import argparse
import glob
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("scene")
ap.add_argument("--project", help="guid を RT のパスへ引くためのルート（Assets と、file: 参照のパッケージ）")
a = ap.parse_args()

text = open(a.scene, encoding="utf-8", errors="replace").read()
docs = {m.group(2): (m.group(1), m.group(3))
        for m in re.finditer(r"^--- !u!(\d+) &(\d+)(?: stripped)?\n(.*?)(?=^--- !u!|\Z)", text, re.S | re.M)}

go = {}
for fid, (cid, body) in docs.items():
    if cid == "1":
        n = re.search(r"^  m_Name: (.*)$", body, re.M)
        act = re.search(r"^  m_IsActive: (\d)$", body, re.M)
        tag = re.search(r"^  m_TagString: (.*)$", body, re.M)
        go[fid] = (n.group(1) if n else "?", act.group(1) if act else "1", tag.group(1) if tag else "")

tr = {}
for fid, (cid, body) in docs.items():
    if cid in ("4", "224"):
        g = re.search(r"m_GameObject: \{fileID: (\d+)\}", body)
        fa = re.search(r"m_Father: \{fileID: (\d+)\}", body)
        if g:
            tr[g.group(1)] = (fid, fa.group(1) if fa else "0")
t2g = {v[0]: k for k, v in tr.items()}


def chain(g):
    names, ok, seen = [], True, set()
    while g in tr and g not in seen:
        seen.add(g)
        n, act, _ = go.get(g, ("?", "1", ""))
        names.append(n + ("" if act == "1" else "[OFF]"))
        ok = ok and act == "1"
        g = t2g.get(tr[g][1])
    return ok, "/".join(reversed(names))


# guid -> アセットのパス（--project があれば）
guid_path = {}
if a.project:
    roots = [os.path.join(a.project, "Assets")]
    pk = os.path.join(a.project, "Packages", "manifest.json")
    if os.path.exists(pk):
        for m in re.finditer(r'"file:([^"]+)"', open(pk, encoding="utf-8").read()):
            roots.append(os.path.normpath(os.path.join(a.project, "Packages", m.group(1))))
    for r in roots:
        for meta in glob.glob(os.path.join(r, "**", "*.renderTexture.meta"), recursive=True):
            m = re.search(r"^guid: (\w+)", open(meta, encoding="utf-8").read(), re.M)
            if m:
                guid_path[m.group(1)] = os.path.relpath(meta[:-5], a.project)


def rt_label(ref):
    m = re.search(r"guid: (\w+)", ref)
    if not m:
        return "screen"
    return guid_path.get(m.group(1), "RT guid " + m.group(1))


print("== rendering cameras ==")
for fid, (cid, body) in docs.items():
    if cid != "20":
        continue
    g = re.search(r"m_GameObject: \{fileID: (\d+)\}", body).group(1)
    en = re.search(r"^  m_Enabled: (\d)$", body, re.M)
    ok, path = chain(g)
    if not (ok and en and en.group(1) == "1"):
        continue
    td = int(re.search(r"^  m_TargetDisplay: (\d+)", body, re.M).group(1))
    tex = re.search(r"^  m_TargetTexture: \{(.*)\}$", body, re.M).group(1)
    out = rt_label(tex) if "guid" in tex else f"screen (Display {td + 1})"
    print(f"  {path}  tag={go[g][2]}  -> {out}")

print("== UI showing a texture (active only) ==")
for fid, (cid, body) in docs.items():
    if cid != "114":
        continue
    tex = re.search(r"^  m_Texture: \{(.*)\}$", body, re.M)
    g = re.search(r"m_GameObject: \{fileID: (\d+)\}", body)
    if not tex or not g or "guid" not in tex.group(1):
        continue
    ok, path = chain(g.group(1))
    if ok:
        print(f"  {path}  shows {rt_label(tex.group(1))}")
