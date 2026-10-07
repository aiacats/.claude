"""会場・セット一式の点検と撮影（別プロセスの Blender で、保存した .blend を開いて流す）。

    "<blender.exe>" -b <file.blend> --factory-startup -P venue_check.py -- --root LiveHall --out <出力フォルダ>
        [--allow allow.json] [--bmcp D:\\_Personal\\Project\\BMCP] [--focus x,y,z] [--no-units] [--size 480x300]
    終了コード: 0 = 問題なし / 1 = 階層・浮き・食い込みのどれかが出た / 2 = スクリプトが落ちた

点検（report.json と標準出力の RESULT 行）:
- 階層: 部品（メッシュ）は「区分（ルート直下の Empty）> 単位（区分の直下の Empty）> 部品」に入っているか。
  単位の中の入れ子（回る部品の軸の Empty・部品の子の部品）は認める。単位に入っていない部品、部品の無い単位、
  名前が単位の名前で始まらない部品を出す。
- 浮き: BMCP の mesh_floating_parts（ルート一式を 1 つの組み立て物として）。
- 食い込み: BMCP の mesh_overlaps（まとまり = 単位。unit_depth=2）。allow.json は [a, b, 理由] の並び（a・b は fnmatch のパターン）。
撮影（Workbench。sheet_*.png に名前付きで並べる）:
- 全体: 会場の外形を 0.5m 内側へ縮めた箱の中の割合で置く（壁の外に出て真っ黒にならない）。
  客席の正面・客席の上手と下手・舞台から客席・袖の左右・舞台裏・天井の近く。
- 単位ごとの寄り: 単位の外形の中心から、会場の中心の向きへ斜め上に引いた位置。
  間に別の物があれば、その手前（単位の側）へカメラを寄せる（光線を単位の中心から外へ飛ばして確かめる）。

座標の約束（blender-stage と同じ）: +Z 上、客席は -Y、--focus（既定は原点 = 舞台の床の中央）が舞台の中心。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector

INNER_MARGIN = 0.5      # 会場の外形から内側へ縮める幅（壁の厚み 0.3m 前後 + カメラの near clip の余白）
EYE = 1.6               # 立った人の目の高さ（全体の画のカメラの高さの目安に使う）
CLOSE_LENS = 35.0       # 寄りの画の焦点距離（35mm 判の標準より少し広い。小物でも周りの付き方が写る）
WIDE_LENS = 18.0        # 全体の画の焦点距離（室内を広く入れる）
CLOSE_FILL = 1.8        # 寄りの画で、単位の外接球の直径に対して画角に取る幅（何に付いているかが写る）
OCCLUDER_GAP = 0.15     # 遮る物の手前へカメラを寄せるときの、遮る物からの距離
SHEET_COLS, SHEET_ROWS = 5, 4
# 寄りの向きの候補（基本の向きからの水平の回転。度）。60° ずつ 1 周（6 方向）で、壁際・隅の単位でも
# 遮る物の少ない向きが 1 つは入る。基本の向きに近い順に試す
ALT_TURNS = (0, 60, -60, 120, -120, 180)
# 狙った距離のこの割合まで引ければ、その向きで撮る。CLOSE_FILL 1.8 × 0.7 ≒ 1.26 で、単位の外接球が画角にちょうど収まる距離
CLEAR_ENOUGH = 0.7
CLOSE_TILT = 0.6        # 寄りの画の見下ろし（水平 1 に対して上へ 0.6 = 約 31°。天板の上と正面が両方写る）
MIN_CLEAR = 0.05        # 遮る物がすぐ手前にあっても、カメラを狙う点からこれ以上は離す（near clip 0.05 と同じ）
RAY_HITS = 64           # 光線が通り抜けてよい面の数の上限（自分の部品と、内側から抜ける面。会場の寄りでは十数枚）


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow")
    ap.add_argument("--bmcp", default=r"D:\_Personal\Project\BMCP")
    ap.add_argument("--focus", default="0,0,0")
    ap.add_argument("--no-units", action="store_true")
    ap.add_argument("--size", default="480x300")
    return ap.parse_args(argv)


class Ctx:
    """BMCP の op を HTTP を通さずに呼ぶための最小の文脈（進捗とキャンセル）。"""

    def progress(self, *a):
        pass

    def check_cancel(self):
        pass


# --------------------------------------------------------------------------- 点検

def unit_ancestor(o, root):
    """ルートから 2 段下（区分 > 単位）の祖先。それより浅ければ None。"""
    chain = []
    p = o
    while p is not None and p is not root:
        chain.append(p)
        p = p.parent
    return chain[-2] if len(chain) >= 3 else None


def hierarchy(root):
    """部品は 区分（ルート直下の Empty）> 単位（区分の直下の Empty）> 部品 に入れる。
    単位の中の入れ子（回る部品の軸の Empty、部品の子の部品）は認める（mesh_overlaps の unit_depth=2 と同じまとまり）。"""
    groups = [c for c in root.children if c.type == "EMPTY"]
    units = {u for g in groups for u in g.children if u.type == "EMPTY"}
    issues = []
    has_mesh = set()
    for o in root.children_recursive:
        if o.type != "MESH":
            continue
        p = unit_ancestor(o, root)
        if p not in units:
            issues.append({"kind": "not_in_unit", "name": o.name, "unitLevel": p.name if p else None})
            continue
        has_mesh.add(p)
        if not o.name.startswith(p.name):
            issues.append({"kind": "name", "name": o.name, "unit": p.name})
    for u in sorted(units - has_mesh, key=lambda u: u.name):
        if not any(c.type == "EMPTY" for c in u.children_recursive):
            issues.append({"kind": "empty_unit", "name": u.name})
    return sorted(units, key=lambda u: u.name), issues


def checks(root, allow, bmcp):
    sys.path.insert(0, os.path.join(bmcp, "addon"))
    from bmcp.ops import assembly                                    # 登録せずに import（op は呼べる）
    t = time.time()
    fl = assembly.mesh_floating_parts(Ctx(), objects=[root.name], capture=False)
    t_fl = time.time() - t
    t = time.time()
    ov = assembly.mesh_overlaps(Ctx(), objects=[root.name], unit_depth=2, allow=allow, capture=False)
    t_ov = time.time() - t
    floating = [{"parts": f["parts"], "gap": f["gap"], "nearest": f["nearest"], "center": f["center"]}
                for a in fl["assemblies"] for f in a["floating"]]
    return floating, ov, {"floating": round(t_fl, 1), "overlaps": round(t_ov, 1)}


# --------------------------------------------------------------------------- 撮影

def meshes_of(o):
    return [o] if o.type == "MESH" else [c for c in o.children_recursive if c.type == "MESH"]


def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def look(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def clear_to(dg, target, want, own):
    """target から want へ光線を飛ばし、own 以外の物に当たったら、その手前（target 側）の位置を返す。"""
    sc = bpy.context.scene
    d = want - target
    dist = d.length
    if dist < 1e-6:
        return want
    d.normalize()
    origin, travelled = target.copy(), 0.0
    for _ in range(RAY_HITS):
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, origin, d, distance=dist - travelled)
        if not hit:
            return want
        step = (loc - origin).length
        travelled += step
        # 自分の部品と、内側から抜ける面（狙う点が別の物の中にある: 幕の厚みの中の出入口など）は遮る物に数えない
        if (ob is not None and ob.name in own) or _n.dot(d) > 0:
            origin = loc + d * 1e-3
            travelled += 1e-3
            continue
        return target + d * max(travelled - OCCLUDER_GAP, MIN_CLEAR)
    return want


def render_to(path, w, h):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.resolution_x, sc.render.resolution_y = w, h
    bpy.ops.render.render(write_still=True)


def shots(root, units, focus, out, size, do_units):
    w, h = size
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE"
    sc.render.image_settings.file_format = "PNG"
    cd = bpy.data.cameras.new("_check_cam")
    cam = bpy.data.objects.new("_check_cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.clip_start = 0.05
    lo, hi = bbox(meshes_of(root))
    ilo = lo + Vector((INNER_MARGIN,) * 3)
    ihi = hi - Vector((INNER_MARGIN,) * 3)
    F = Vector(focus)

    def at(fx, fy, z):
        return Vector((ilo.x + (ihi.x - ilo.x) * fx, ilo.y + (ihi.y - ilo.y) * fy, z))

    fy = (F.y - ilo.y) / max(ihi.y - ilo.y, 1e-6)
    floor = F.z
    # 全体の画の位置は内側の箱の割合（客席は -Y = 割合 0 側）と、床からの高さ。立った目の高さ EYE を基準に、
    # 客席の後ろ寄りは +1m（前の人の頭越し）、2 階席の高さの目安は +3m。天井の低い小屋では内側の箱へ収める
    wide = [
        ("front_center", at(0.5, 0.06, lo.z + EYE + 1.0), F + Vector((0, 0, 2.5))),
        ("house_left", at(0.9, 0.2, lo.z + EYE + 3.0), F + Vector((0, 0, 1.5))),
        ("house_right", at(0.1, 0.3, lo.z + EYE), F + Vector((0, 0, 1.5))),
        ("from_stage", F + Vector((0, -1.0, EYE)), at(0.5, 0.0, lo.z + EYE)),
        ("wing_left", at(0.97, fy, floor + EYE), F + Vector((0, 0, 1.0))),
        ("wing_right", at(0.03, fy, floor + EYE), F + Vector((0, 0, 1.0))),
        ("backstage", at(0.5, 0.99, floor + EYE), F + Vector((0, 0, 3.0))),
        ("ceiling", at(0.5, 0.25, ihi.z), F),
    ]
    files = []
    cd.lens = WIDE_LENS
    for name, loc, tgt in wide:
        loc = Vector((min(max(loc.x, ilo.x), ihi.x), min(max(loc.y, ilo.y), ihi.y), min(max(loc.z, ilo.z), ihi.z)))
        look(cam, loc, tgt)
        p = os.path.join(out, f"wide_{name}.png")
        render_to(p, w, h)
        files.append((name, p))
    unit_files = []
    if do_units:
        dg = bpy.context.evaluated_depsgraph_get()
        cd.lens = CLOSE_LENS
        fov = 2 * math.atan(cd.sensor_width / (2 * cd.lens))
        center = (lo + hi) / 2
        for u in units:
            ms = meshes_of(u)
            if not ms:
                continue
            ulo, uhi = bbox(ms)
            c = (ulo + uhi) / 2
            r = max((uhi - ulo).length / 2, 0.05)
            dist = r * CLOSE_FILL / math.tan(fov / 2)
            # 向き: 会場の中心の向きと客席の向き（-Y。機材の顔はほぼ客席を向く）を足す
            d = Vector((center.x - c.x, center.y - c.y, 0))
            if d.length > 1e-3:
                d.normalize()
            d = d + Vector((0, -1, 0))
            if d.length < 1e-3:
                d = Vector((0, -1, 0))
            d.normalize()
            own = {m.name for m in ms}
            # 遮られて寄りすぎる向きは避ける: 基本の向きと、そこから水平に回した向きを試し、いちばん引ける位置を使う
            best = None
            for turn in ALT_TURNS:
                dd = Matrix.Rotation(math.radians(turn), 3, "Z") @ d
                dd = (dd + Vector((0, 0, CLOSE_TILT))).normalized()
                want = c + dd * dist
                want = Vector((min(max(want.x, ilo.x), ihi.x), min(max(want.y, ilo.y), ihi.y),
                               min(max(want.z, ilo.z), ihi.z)))
                cand = clear_to(dg, c, want, own)
                if best is None or (cand - c).length > (best - c).length + 1e-6:
                    best = cand
                if (cand - c).length >= CLEAR_ENOUGH * dist:
                    break
            loc = best
            look(cam, loc, c)
            p = os.path.join(out, f"unit_{u.name}.png")
            render_to(p, w, h)
            unit_files.append((u.name, p))
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(cd)
    return files, unit_files


def sheets(items, out, stem, size):
    from PIL import Image, ImageDraw
    w, h = size
    label = 18
    per = SHEET_COLS * SHEET_ROWS
    paths = []
    for k in range(0, len(items), per):
        page = items[k:k + per]
        rows = math.ceil(len(page) / SHEET_COLS)
        sheet = Image.new("RGB", (SHEET_COLS * w, rows * (h + label)), (20, 20, 22))
        dr = ImageDraw.Draw(sheet)
        for i, (name, p) in enumerate(page):
            x, y = (i % SHEET_COLS) * w, (i // SHEET_COLS) * (h + label)
            with Image.open(p) as im:
                sheet.paste(im.convert("RGB"), (x, y + label))
            dr.text((x + 4, y + 3), name, fill=(220, 220, 220))
        path = os.path.join(out, f"sheet_{stem}_{k // per + 1:02d}.png")
        sheet.save(path)
        paths.append(path)
    return paths


def main():
    a = parse()
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, os.path.join(a.bmcp, f".blender-site-{bpy.app.version[0]}.{bpy.app.version[1]}"))
    root = bpy.data.objects[a.root]
    allow = json.load(open(a.allow, encoding="utf-8")) if a.allow else []
    units, hier = hierarchy(root)
    floating, ov, sec = checks(root, allow, a.bmcp)
    size = tuple(int(v) for v in a.size.split("x"))
    focus = tuple(float(v) for v in a.focus.split(","))
    wide, unit_shots = shots(root, units, focus, a.out, size, not a.no_units)
    report = {
        "root": root.name, "units": len(units), "meshes": sum(1 for o in root.children_recursive if o.type == "MESH"),
        "hierarchy": hier, "floating": floating,
        "overlaps": [{k: p[k] for k in ("a", "b", "unitA", "unitB", "depth", "measured", "center")} for p in ov["pairs"]],
        "allowedPairs": ov["allowedPairs"], "seconds": sec,
        "sheets": sheets(wide, a.out, "wide", size) + sheets(unit_shots, a.out, "units", size),
    }
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("RESULT " + json.dumps({"units": report["units"], "hierarchy": len(hier), "floating": len(floating),
                                  "overlaps": len(report["overlaps"]), "allowed": ov["allowedPairs"],
                                  "sheets": len(report["sheets"]), "seconds": sec}, ensure_ascii=False))
    sys.stdout.flush()
    os._exit(1 if (hier or floating or report["overlaps"]) else 0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(2)                                          # Blender は -P の例外で終了コードを変えないので明示する
