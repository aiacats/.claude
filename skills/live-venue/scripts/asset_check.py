"""アセット単体の破綻の点検（別プロセスの Blender で、保存した .blend を開いて流す）。

    "<blender.exe>" -b <file.blend> --factory-startup -P asset_check.py -- --unit Bench_StudioCameraRig
        [--out <report.json>] [--bmcp D:\\_Personal\\Project\\BMCP] [--min-depth 0.002]
    終了コード: 0 = 問題なし / 1 = 形の破綻か浮いた部品がある / 2 = スクリプトが落ちた

見るもの（単位の子孫のメッシュ全部）:
- 形: 閉じていない辺（穴・面の継ぎ目の割れ）、3 枚以上の面が付く辺、面積ほぼ 0 の面、どの面にも使われない頂点と辺、
  隣の面と向きが逆の辺（法線の不揃い）、裏返った閉じた塊（体積が負 = 法線が内向き）
- 浮き: BMCP の mesh_floating_parts（単位を 1 つの組み立て物として。どこにも触れていない部品）
- 食い込み: BMCP の mesh_overlaps（部品 = メッシュどうし）。作りとして差し込んだ所（管の端・留め具）も出るので、数には入れず、
  深さの大きい順に一覧を出す。--min-depth 未満は出さない
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import bmesh
import bpy

AREA_EPS = 1e-10        # 面積ほぼ 0 の面（0.01mm 角。これ以下は描画で縮退して影が乱れる）


class Ctx:
    def progress(self, *a):
        pass

    def check_cancel(self):
        pass


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True)
    ap.add_argument("--scene")
    ap.add_argument("--out")
    ap.add_argument("--bmcp", default=r"D:\_Personal\Project\BMCP")
    ap.add_argument("--min-depth", type=float, default=0.0005)
    ap.add_argument("--no-overlaps", action="store_true", help="食い込みを調べない（大きな組み物で時間がかかるとき）")
    return ap.parse_args(argv)


def geometry(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.normal_update()
    r = {
        "open_edges": sum(1 for e in bm.edges if len(e.link_faces) == 1),
        "multi_face_edges": sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "zero_faces": sum(1 for f in bm.faces if f.calc_area() < AREA_EPS),
        "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
        "loose_edges": sum(1 for e in bm.edges if not e.link_faces),
        "flipped_edges": sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous),
    }
    # 閉じた塊ごとの体積の符号（負 = 法線が内向き）
    seen, inverted = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        if all(len(e.link_faces) == 2 for g in comp for e in g.edges):
            vol = 0.0
            o0 = comp[0].verts[0].co.copy()                      # 塊の中の点を原点に測る（遠い座標で小さな塊の体積が桁落ちしない）
            for g in comp:
                vs = [v.co - o0 for v in g.verts]
                for i in range(1, len(vs) - 1):
                    vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
            if vol < 0:
                inverted += 1
    r["inverted_shells"] = inverted
    bm.free()
    return {k: v for k, v in r.items() if v}


def split_loose(unit, meshes, sc):
    """メッシュを、つながった塊（部品 1 つずつ）の一時オブジェクトに分けて、1 つの Empty の下へ並べる（ワールド座標で）。

    キットは部品をマテリアルごとに 1 つのメッシュへまとめるので、そのままでは浮きも食い込みも「メッシュ全体」の単位でしか
    分からない（つまみ 1 個が浮いていても、同じマテリアルの別の部品に触れていれば見つからない）。名前は「<メッシュ>#<番号>」。
    """
    probe = bpy.data.objects.new("_probe", None)
    sc.collection.objects.link(probe)
    for o in meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        seen = set()
        k = 0
        for f in bm.faces:
            if f.index in seen:
                continue
            stack, comp = [f], set()
            seen.add(f.index)
            while stack:
                g = stack.pop()
                comp.add(g)
                for v in g.verts:
                    for h in v.link_faces:
                        if h.index not in seen:
                            seen.add(h.index)
                            stack.append(h)
            part = bm.copy()
            keep = {c.index for c in comp}
            part.faces.ensure_lookup_table()
            drop = [g for g in part.faces if g.index not in keep]
            bmesh.ops.delete(part, geom=drop, context="FACES")
            me = bpy.data.meshes.new(f"{o.name}#{k}")
            part.to_mesh(me)
            part.free()
            ob = bpy.data.objects.new(me.name, me)
            sc.collection.objects.link(ob)
            ob.parent = probe
            k += 1
        bm.free()
    bpy.context.view_layer.update()
    return probe


def main():
    a = parse()
    unit = bpy.data.objects[a.unit]
    sc = bpy.context.scene
    if unit.name not in bpy.context.view_layer.objects:
        # 別のシーン（作業台）の単位: BMCP の op は今のビューレイヤーに見える物だけを調べるので、単位のコレクションを
        # 今のシーンへ一時的につなぐ（.blend は保存しないので元のファイルは変わらない）
        for c in unit.users_collection:
            if c.name not in sc.collection.children and c is not sc.collection:
                sc.collection.children.link(c)
        bpy.context.view_layer.update()
    meshes = [o for o in [unit] + list(unit.children_recursive) if o.type == "MESH"]
    geo = {o.name: g for o in meshes if (g := geometry(o))}
    sys.path.insert(0, os.path.join(a.bmcp, "addon"))
    from bmcp.ops import assembly
    probe = split_loose(unit, meshes, sc)
    fl = assembly.mesh_floating_parts(Ctx(), objects=[probe.name], capture=False)
    floating = [{"parts": f["parts"], "gap": f["gap"], "nearest": f["nearest"], "center": f["center"]}
                for x in fl["assemblies"] for f in x["floating"]]
    # 食い込みは塊の数の 2 乗で重くなる（カメラ 2 台と幕を載せたカメラ台で 25 分を超えた）。--no-overlaps で飛ばし、会場の点検に任せる
    # 下限は op の既定（全体の対角の 1/1000 など）ではなく --min-depth を渡す。薄い板（幅木・帯）の中に入った物は、深さが
    # 板の厚みの半分で頭打ちになるので、既定の下限では見逃す（2026-10-08 のレビュー: ケーブルが幅木を貫いていた）
    ov = {"pairs": []} if a.no_overlaps else assembly.mesh_overlaps(Ctx(), objects=[probe.name], unit="object",
                                                                    min_depth=a.min_depth, capture=False)
    # 深さが測れない組（閉じていない形が絡む）は None のまま先頭に出す（測れない = 中まで入り込んでいるかもしれない）
    pairs = sorted(({"a": p["a"], "b": p["b"], "depth": p["depth"], "center": p["center"]} for p in ov["pairs"]
                    if p["depth"] is None or p["depth"] >= a.min_depth),
                   key=lambda p: -(p["depth"] if p["depth"] is not None else 1e9))
    tris = sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)
    report = {"unit": unit.name, "meshes": len(meshes), "triangles": tris, "geometry": geo, "floating": floating, "overlaps": pairs}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print("RESULT " + json.dumps({"unit": unit.name, "meshes": len(meshes), "triangles": tris, "geometry": geo,
                                  "floating": floating, "overlaps": len(pairs), "overlap_top": pairs[:12]}, ensure_ascii=False))
    sys.stdout.flush()
    os._exit(1 if (geo or floating) else 0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(2)
