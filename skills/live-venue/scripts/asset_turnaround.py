"""アセット単体の撮影（別プロセスの Blender で、保存した .blend を開いて流す）。

    "<blender.exe>" -b <file.blend> -P asset_turnaround.py -- --unit Audience_CamPlatform_Center --out <出力フォルダ>
        [--refs <資料の写真のフォルダ or ファイル>...] [--size 640x640] [--name <出力名>] [--scene AssetBench] [--focus x,y,z,r]

指定した単位（Empty か メッシュ）の子孫だけを残して、ほかを撮らない（hide_render）。グレーの背景とスタジオの 3 灯
（キー・フィル・リム）を撮る間だけ足し、正面・斜め前・横・後ろ・斜め上の 5 方向を EEVEE で撮る。
資料の写真（--refs）を 1 行目に、撮った画を 2 行目に並べた一覧（<名前>_sheet.png）を作る。
正面は単位の局所 -Y（このプロジェクトの約束: 機材の顔は -Y）。.blend は保存しない（開いたファイルは変えない）。
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

BG = (0.18, 0.18, 0.19)          # 背景のグレー（黒い機材の輪郭が読める明るさ）
KEY_FILL_RIM = ((1.0, 300.0), (0.45, 180.0), (0.8, 260.0))   # 3 灯の明るさの比と強さ（W。半径 1m の物で、黒い樹脂がつぶれず白が飛ばない値を見て決めた）
FILL = 0.9                       # 画角に対して物が占める割合
VIEWS = {                        # 名前: (局所の向きの方位角（度。正面 = 0 = -Y から見る）, 仰角（度）)
    "front": (0, 8), "front34": (35, 18), "side": (90, 8), "back": (180, 8), "top34": (-35, 45),
}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--refs", nargs="*", default=[])
    ap.add_argument("--size", default="640x640")
    ap.add_argument("--name")
    ap.add_argument("--scene", help="撮るシーン（既定は開いたときのシーン。作業台は AssetBench）")
    ap.add_argument("--focus", help="寄る点 x,y,z と半径 r（m）: 'x,y,z,r'。大きな物（クレーン）の細部を 5 方向から撮る")
    ap.add_argument("--bmcp", default=r"D:\_Personal\Project\BMCP")
    return ap.parse_args(argv)


def subtree(o):
    return [o] + list(o.children_recursive)


def main():
    a = parse()
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, os.path.join(a.bmcp, f".blender-site-{bpy.app.version[0]}.{bpy.app.version[1]}"))
    sc = bpy.data.scenes[a.scene] if a.scene else bpy.context.scene
    units = [bpy.data.objects[n] for n in a.unit]
    keep = {o.name for u in units for o in subtree(u)}
    for o in bpy.data.objects:
        if o.name not in keep:
            o.hide_render = True
    meshes = [bpy.data.objects[n] for n in keep if bpy.data.objects[n].type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center, radius = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    if a.focus:
        fx, fy, fz, fr = (float(v) for v in a.focus.split(","))
        center, radius = Vector((fx, fy, fz)), fr
    yaw0 = units[0].matrix_world.to_euler().z                                 # 単位の向き（局所 -Y が正面）
    w, h = (int(v) for v in a.size.split("x"))
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("_turn_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*BG, 1.0)
    sc.world = world
    cd = bpy.data.cameras.new("_turn_cam")
    cam = bpy.data.objects.new("_turn_cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.lens = 50
    fov = 2 * math.atan(cd.sensor_width / (2 * cd.lens))
    dist = radius / math.sin(fov / 2) / FILL
    cd.clip_start, cd.clip_end = dist * 0.01, dist * 10
    lights = []
    for k, (rel, power) in enumerate(KEY_FILL_RIM):
        ld = bpy.data.lights.new(f"_turn_l{k}", "AREA")
        ld.energy, ld.size = power * rel * radius ** 2, radius * 1.5            # 灯までの距離は radius に比例するので、明るさを揃えるには radius² に比例
        lo_ = bpy.data.objects.new(ld.name, ld)
        sc.collection.objects.link(lo_)
        lights.append(lo_)
    paths = []
    stem = a.name or a.unit[0]
    for name, (az, el) in VIEWS.items():
        th = yaw0 + math.radians(az)
        d = Vector((math.sin(th) * math.cos(math.radians(el)), -math.cos(th) * math.cos(math.radians(el)), math.sin(math.radians(el))))
        cam.location = center + d * dist
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        for k, lo_ in enumerate(lights):                                          # キーは右前上、フィルは左前、リムは後ろ上
            off = ((1.0, 0.6, 0.8), (-1.0, 0.3, 0.2), (0.0, -1.0, 1.0))[k]
            right = Vector((math.cos(th), math.sin(th), 0))
            lo_.location = center + (right * off[0] + d.normalized() * off[1] + Vector((0, 0, off[2]))) * dist * 0.8
            lo_.rotation_euler = (center - lo_.location).to_track_quat("-Z", "Y").to_euler()
        p = os.path.join(a.out, f"{stem}_{name}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True, scene=sc.name)
        paths.append((name, p))
    sheet(paths, a.refs, os.path.join(a.out, f"{stem}_sheet.png"), (w, h))
    print("RESULT", os.path.join(a.out, f"{stem}_sheet.png"))
    sys.stdout.flush()
    os._exit(0)


def sheet(shots, refs, path, size):
    from PIL import Image, ImageDraw
    w, h = size
    files = []
    for r in refs:
        if os.path.isdir(r):
            files += sorted(os.path.join(r, f) for f in os.listdir(r) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
        elif os.path.exists(r):
            files.append(r)
    cols = max(len(shots), len(files[:len(shots)]) if files else 0)
    rows = 2 if files else 1
    label = 18
    img = Image.new("RGB", (cols * w, rows * (h + label)), (20, 20, 22))
    dr = ImageDraw.Draw(img)

    def put(i, row, im, text):
        im = im.convert("RGB")
        im.thumbnail((w, h))
        x, y = i * w + (w - im.width) // 2, row * (h + label) + label + (h - im.height) // 2
        img.paste(im, (x, y))
        dr.text((i * w + 4, row * (h + label) + 3), text, fill=(220, 220, 220))

    if files:
        for i, f in enumerate(files[:cols]):
            with Image.open(f) as im:
                put(i, 0, im, "ref: " + os.path.basename(f))
    for i, (name, p) in enumerate(shots):
        with Image.open(p) as im:
            put(i, rows - 1, im, name)
    img.save(path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(2)
