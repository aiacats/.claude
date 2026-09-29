"""ステージ（部屋・セット・小物）を組むための形づくりの補助。

BMCP の blender_run_python から読み込んで使う。寸法は全てメートル、UV は「1m = 1UV」で統一する。

    import importlib, os, sys
    sys.path.insert(0, os.path.expanduser("~/.claude/skills/blender-stage/scripts"))
    import stagelib as S
    importlib.reload(S)
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

UV_SCALE = 1.0  # 1m あたりの UV 長さ。全オブジェクトで揃えるとテクセル密度が揃う


# --- コレクションとオブジェクト ---

def collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    """コレクションを作る（既にあればそれを返す）。parent 省略時はシーン直下。"""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    target = parent or bpy.context.scene.collection
    if col.name not in target.children:
        target.children.link(col)
    return col


def new_object(name: str, mesh: bpy.types.Mesh, col: bpy.types.Collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    return obj


def empty(name: str, col: bpy.types.Collection, display: str = "PLAIN_AXES",
          size: float = 0.25) -> bpy.types.Object:
    """階層用の Empty（FBX ではこれが Unity 側の親になる）。"""
    o = bpy.data.objects.get(name)
    if o is None:
        o = bpy.data.objects.new(name, None)
        col.objects.link(o)
    o.empty_display_type = display
    o.empty_display_size = size
    return o


def parent_to(child: bpy.types.Object, parent: bpy.types.Object, *, world_authored: bool) -> None:
    """親子付け。

    world_authored=True … 子をワールド座標で作った場合。親の変換を打ち消して、今の位置を保つ。
    world_authored=False … 子を親のローカル座標で作った場合。親にそのまま追従させる。

    作った直後のオブジェクトは matrix_world が未更新（単位行列）なので、
    必ず view_layer.update() を挟んでから逆行列を取る。ここを間違えると子が二重に移動する。
    """
    bpy.context.view_layer.update()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted() if world_authored else Matrix.Identity(4)
    bpy.context.view_layer.update()


# --- 形 ---

def box_mesh(name: str, size, center=(0.0, 0.0, 0.0)) -> bpy.types.Mesh:
    """軸に沿った直方体のメッシュ。size と center はローカル座標。"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0] + center[0], v.co.y * size[1] + center[1], v.co.z * size[2] + center[2]))
    bm.to_mesh(me)
    bm.free()
    return me


def box(name: str, size, center, col: bpy.types.Collection, material=None, origin=None) -> bpy.types.Object:
    """直方体。origin を渡すと、そこをオブジェクトの原点にする（壁なら床側、扉なら蝶番）。"""
    o = Vector(origin) if origin is not None else Vector(center)
    obj = new_object(name, box_mesh(name, size, Vector(center) - o), col)
    obj.location = o
    if material is not None:
        obj.data.materials.append(material)
    return obj


def frame_mesh(name: str, outer, inner, thickness: float) -> bpy.types.Mesh:
    """額縁状（中抜きの板）。outer/inner は (幅, 高さ)、厚みは Y 方向。窓枠・鏡の枠に使う。"""
    ow, oh = outer
    iw, ih = inner
    pieces = [
        ((ow, thickness, (oh - ih) / 2), (0.0, 0.0, (ih + oh) / 4)),
        ((ow, thickness, (oh - ih) / 2), (0.0, 0.0, -(ih + oh) / 4)),
        (((ow - iw) / 2, thickness, ih), (-(iw + ow) / 4, 0.0, 0.0)),
        (((ow - iw) / 2, thickness, ih), ((iw + ow) / 4, 0.0, 0.0)),
    ]
    return _merged_boxes(name, pieces)


def wall_mesh(name: str, width: float, height: float, thickness: float, opening=None) -> bpy.types.Mesh:
    """壁の板（ローカル: X = 幅、Y = 厚み、Z = 高さ。中心は板の中心）。

    opening = (中心 X, 幅, 高さ) を渡すと、その分を避けて「左・右・上」の板で作る。
    ブーリアンを使わないので面が四角のまま残り、後から編集しやすい。
    腰壁・巾木を扉で切るときにも使える（opening の高さを板の高さ以上にすれば左右に分かれる）。
    """
    if opening is None:
        return _merged_boxes(name, [((width, thickness, height), (0.0, 0.0, 0.0))])
    ox, ow, oh = opening
    left_w = (ox - ow / 2) + width / 2
    right_w = width / 2 - (ox + ow / 2)
    top_h = height - oh
    pieces = []
    if left_w > 1e-6:
        pieces.append(((left_w, thickness, height), (-width / 2 + left_w / 2, 0.0, 0.0)))
    if right_w > 1e-6:
        pieces.append(((right_w, thickness, height), (width / 2 - right_w / 2, 0.0, 0.0)))
    if top_h > 1e-6:
        pieces.append(((ow, thickness, top_h), (ox, 0.0, -height / 2 + oh + top_h / 2)))
    return _merged_boxes(name, pieces)


def wall_with_openings(name: str, width: float, height: float, thickness: float, openings) -> bpy.types.Mesh:
    """開口をいくつも持つ壁（扉 + 窓 + 給排気口など）。

    openings は [(中心 X, 幅, 下端 Z, 上端 Z), ...]。床から始まる扉は下端 0。
    X 方向を開口の縁で切って列に分け、列ごとに「開口の無い高さ」だけ板を置く。
    ブーリアンを使わないので、面が四角のまま残って後から編集しやすい。
    開口どうしが X 方向で重なる場合は、重なった範囲で両方の穴が開く。
    """
    xs = {-width / 2, width / 2}
    for cx, ow, _z0, _z1 in openings:
        xs.add(cx - ow / 2)
        xs.add(cx + ow / 2)
    edges = sorted(x for x in xs if -width / 2 - 1e-9 <= x <= width / 2 + 1e-9)
    pieces = []
    for xa, xb in zip(edges, edges[1:]):
        if xb - xa < 1e-6:
            continue
        mid = (xa + xb) / 2
        # この列にかかる開口の高さ範囲
        gaps = sorted((max(0.0, z0), min(height, z1)) for cx, ow, z0, z1 in openings
                      if cx - ow / 2 <= mid <= cx + ow / 2)
        z = 0.0
        for g0, g1 in gaps:
            if g0 - z > 1e-6:
                pieces.append(((xb - xa, thickness, g0 - z), (mid, 0.0, (z + g0) / 2 - height / 2)))
            z = max(z, g1)
        if height - z > 1e-6:
            pieces.append(((xb - xa, thickness, height - z), (mid, 0.0, (z + height) / 2 - height / 2)))
    return _merged_boxes(name, pieces)


def _merged_boxes(name: str, pieces) -> bpy.types.Mesh:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for size, center in pieces:
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            v.co = Vector((v.co.x * size[0] + center[0], v.co.y * size[1] + center[1], v.co.z * size[2] + center[2]))
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
    bm.to_mesh(me)
    bm.free()
    return me


def lathe(name: str, profile, col: bpy.types.Collection, material=None, segments: int = 20) -> bpy.types.Object:
    """断面を Z 軸まわりに回した形（ろくろ挽き）。脚・ノブ・ボタン・花瓶などに。

    profile は [(半径, 高さ), ...]。半径 0 から始めて 0 で終わると、上下に蓋が付く。
    """
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, angle=2 * math.pi, steps=segments, axis=(0, 0, 1), cent=(0, 0, 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    obj = new_object(name, me, col)
    if material is not None:
        obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def cushion_mesh(name: str, width: float, depth: float, thickness: float, *, dome: float = 0.014,
                 buttons=(), dimple: float = 0.032, radius: float = 0.062,
                 segments=(26, 16)) -> bpy.types.Mesh:
    """中央が膨らんだ座面。buttons に (x, y) を渡すと、そこがボタン留めでくぼむ。

    Bevel → Subdivision のモディファイアを足すと、縁が締まった布の座面になる。
    """
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segments[0], y_segments=segments[1], size=1.0)
    for v in bm.verts:
        u, w = v.co.x, v.co.y
        v.co.x, v.co.y = u * width / 2, w * depth / 2
        v.co.z = (math.cos(u * math.pi / 2) ** 0.7) * (math.cos(w * math.pi / 2) ** 0.7) * dome
    res = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, verts=[e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)],
                        vec=(0, 0, -thickness))
    for bx, by in buttons:
        for v in bm.verts:
            if v.co.z < 0.0:
                continue
            d = math.hypot(v.co.x - bx, v.co.y - by)
            if d < radius:
                v.co.z -= (1.0 - d / radius) ** 2 * dimple
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


# --- UV ---

def uv_box_project(obj: bpy.types.Object, scale: float = UV_SCALE, name: str = "UVMap") -> None:
    """面の向きごとに軸へ落とす UV（1m = scale UV）。箱の集まりで出来た形向け。

    UV を 0〜1 に詰めず、ワールドの位置をそのまま使う（同じ壁の中で継ぎ目が出ない）。
    """
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name=name)
    uv = me.uv_layers[0]
    uv.name = name
    mw = obj.matrix_world
    rot = mw.to_3x3()
    for poly in me.polygons:
        n = (rot @ poly.normal).normalized()
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            u, v = (co.y, co.z) if ax == 0 else (co.x, co.z) if ax == 1 else (co.x, co.y)
            uv.data[li].uv = (u * scale, v * scale)


def uv_cylindrical(obj: bpy.types.Object, scale: float = UV_SCALE, name: str = "UVMap") -> None:
    """Z 軸まわりの回転体向けの UV。U は実寸の周長、V は高さ（1m = scale UV）。

    継ぎ目（角度 ±pi）をまたぐ面は、面ごとに近い側へ寄せて U が一周ぶん飛ぶのを防ぐ。
    """
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name=name)
    uv = me.uv_layers[0]
    uv.name = name
    r_ref = max((math.hypot(v.co.x, v.co.y) for v in me.vertices), default=1.0) or 1.0
    for poly in me.polygons:
        loops = list(poly.loop_indices)
        angles = [math.atan2(me.vertices[me.loops[li].vertex_index].co.y,
                             me.vertices[me.loops[li].vertex_index].co.x) for li in loops]
        base = angles[0]
        for li, a in zip(loops, angles):
            while a - base > math.pi:
                a -= 2 * math.pi
            while a - base < -math.pi:
                a += 2 * math.pi
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (a * r_ref * scale, co.z * scale)


# --- 仕上げ ---

def bevel(obj: bpy.types.Object, width: float = 0.004, segments: int = 2, angle_deg: float = 40.0):
    """角を少し落とす（光が当たって面が見分けられる）。適用はせず残す。"""
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle_deg)
    return m


def shade_smooth(obj: bpy.types.Object) -> None:
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.update()


def sync_viewport_colors() -> None:
    """ノードのベースカラーを material.diffuse_color へ写す。

    blender_capture（Workbench）のプレビューはノードを見ないので、これをやると色が分かる。
    """
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if b is None:
            continue
        c = b.inputs["Base Color"].default_value
        m.diffuse_color = (c[0], c[1], c[2], 1.0)
        m.roughness = b.inputs["Roughness"].default_value
        m.metallic = b.inputs["Metallic"].default_value


def look_at(obj: bpy.types.Object, target) -> None:
    """カメラなどを target へ向ける。カメラは部屋の内側に置くこと（外だと真っ黒に写る）。"""
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def audit(objects=None) -> dict:
    """終わる前の点検。スケール・UV・マテリアル・孤立頂点・n-gon を数える。"""
    objs = objects or [o for o in bpy.data.objects if o.type == "MESH"]
    out = {"meshes": len(objs), "unapplied_scale": [], "no_uv": [], "no_material": [],
           "ngons": [], "loose_verts": [], "triangles": 0}
    for o in objs:
        if tuple(round(v, 4) for v in o.scale) != (1.0, 1.0, 1.0):
            out["unapplied_scale"].append(o.name)
        if not o.data.uv_layers:
            out["no_uv"].append(o.name)
        if not o.data.materials:
            out["no_material"].append(o.name)
        if any(len(p.vertices) > 4 for p in o.data.polygons):
            out["ngons"].append(o.name)
        used = {i for p in o.data.polygons for i in p.vertices}
        if len(used) != len(o.data.vertices):
            out["loose_verts"].append(o.name)
        out["triangles"] += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return out
