"""書き出した FBX を空のシーンへ読み込み、Unity へ持っていける形かを点検する。

**共有中の Blender（BMCP の接続先）では実行しない**。別セッションの作業を read_homefile で消しかねない。
別プロセスの Blender で走らせる:

    "<blender.exe>" -b --factory-startup -P check_fbx.py -- <FBX のパス>

標準出力の `RESULT {...}` を見る。
- textured_by_image: Base Color に画像が直接つながったマテリアル。FBX は Mix 経由の画像を運ばないので、
  色テクスチャを使っているはずのマテリアルがここに無ければ、Unity では白くなる。
- normal_mapped: ノーマルマップの画像がつながったマテリアルの数（Normal の入口がつながっているだけでは数えない）。
- dup_mesh_names: `.001` 付きのメッシュ名。モディファイア付きのメッシュは取り込み時に必ず `.001` になる
  （無害。band_studio で 88 件）。作り直しで古いメッシュデータが残っているとさらに増えるので、前回との差で見る。
"""
import json
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not args:
    raise SystemExit("使い方: blender -b --factory-startup -P check_fbx.py -- <FBX のパス>")
path = args[0]

bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)

objs = list(bpy.data.objects)
meshes = [o for o in objs if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))

textured, flat, normal_mapped = [], [], []
for m in bpy.data.materials:
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes else None
    if b is None:
        continue
    links = b.inputs["Base Color"].links
    (textured if links and links[0].from_node.type == "TEX_IMAGE" else flat).append(m.name)
    # ノーマルマップ: 読み込み側は画像が無くても Normal Map ノードを作ることがあるので、画像がつながっているかで見る
    if any(n.type == "NORMAL_MAP" and n.inputs["Color"].is_linked
           and n.inputs["Color"].links[0].from_node.type == "TEX_IMAGE"
           and n.inputs["Color"].links[0].from_node.image is not None for n in m.node_tree.nodes):
        normal_mapped.append(m.name)

roots = [o.name for o in objs if o.parent is None]
print("RESULT " + json.dumps({
    "objects": len(objs), "meshes": len(meshes), "materials": len(bpy.data.materials),
    "images": len(bpy.data.images), "roots": roots[:5],
    "root_rot": [round(a, 4) for a in objs[0].rotation_euler] if objs else None,
    "size_m": [round(v, 3) for v in (hi - lo)],
    "non_uniform_scale": [o.name for o in meshes
                          if max(abs(o.scale.x - o.scale.y), abs(o.scale.y - o.scale.z)) > 1e-5][:5],
    "no_uv": [o.name for o in meshes if not o.data.uv_layers][:5],
    "textured_by_image": sorted(textured),
    "flat_color": len(flat),
    "normal_mapped": len(normal_mapped),
    "dup_mesh_names": sum(1 for me in bpy.data.meshes if me.name[-4:-3] == "." and me.name[-3:].isdigit()),
}, ensure_ascii=False))
