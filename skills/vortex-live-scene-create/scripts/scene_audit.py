"""vortex のライブシーンを YAML のまま読んで、構成・配線・キャラを出し、問題を点検する（Unity 不要・読むだけ）。

  python scene_audit.py dump   <scene> [--root 名前] [--depth N] [--chars] [--full]   ヒエラルキー（有効/無効・レイヤー・コンポーネント・プレハブ）
  python scene_audit.py wiring <scene>                                               配線（OSC・枠・注視先・スイッチャー・マイク・DMX・OptiTrack・カメラ・出力・Timeline）
  python scene_audit.py chars  <scene> [--tsv]                                       キャラの表
  python scene_audit.py check  <scene>... [--min warn]                               問題を error / warn / info で
  python scene_audit.py summary <scene>...                                           1 シーン 1 行の表（System・カメラ・キャラ・OSC・DMX・DoF・OptiTrack・件数）
  python scene_audit.py diff   <scene> --ref <基準のシーン>                           System の塊・配線を基準と比べる
  python scene_audit.py show   <scene> <コンポーネント名,...> [--path 部分一致] [--lines N]   コンポーネントの中身（参照を名前に、プレハブの上書き込み）

GUID → パスの表は %TEMP%/vortex-scene-audit/ に持つ（初回は .meta を全部読むので 1〜2 分、以降は変わった .meta だけ）。
"""
import argparse
import os
import sys
import time

from vortex_checks import run as run_checks
from vortex_diff import diff as run_diff
from vortex_model import Model
from vortex_report import CHAR_HEAD, char_rows, wiring
from vortex_scene import Ref, open_scene, setup_stdio

# メッシュを描くだけの物（dump で枝ごとまとめる）
BORING = {"MeshFilter", "MeshRenderer", "SkinnedMeshRenderer", "MeshCollider", "BoxCollider", "SphereCollider", "CapsuleCollider",
          "ParticleSystem", "ParticleSystemRenderer", "LineRenderer", "SpriteRenderer", "Rigidbody", "TrailRenderer", "LODGroup"}


PROJECT = None  # --project（シーンがプロジェクトの外にあるとき）


def _load(path):
    t0 = time.time()
    sc = open_scene(path, project=PROJECT)
    m = Model(sc)
    return m, time.time() - t0


def cmd_dump(a):
    m, dt = _load(a.scene)
    sc, p = m.sc, m.p
    char_gos = {c["go"]: c for c in m.chars}
    out = []

    def interesting(g):
        return (g in sc.instance_root or not sc.go_fields.get(g, {}).get("active", True) or g in char_gos
                or any(sc.label(k) not in BORING for k in sc.components(g)))

    memo = {}

    def sub_interesting(g):
        if g not in memo:
            memo[g] = interesting(g) or any(sub_interesting(c) for c in sc.child_gos(g))
        return memo[g]

    def line(g, ind):
        gf = sc.go_fields.get(g, dict(name="?", active=True, layer=0))
        comps = ", ".join(sc.label(k) + ("" if sc.enabled(k) else "(off)") for k in sc.components(g))
        pf = f"  <{sc.instance_root[g]} 上書き {len(sc.instance_mods.get(g, []))}>" if g in sc.instance_root else ""
        lay = f" L:{p.layer_name(gf['layer'])}" if gf["layer"] else ""
        out.append("  " * ind + f"{gf['name']}{'' if gf['active'] else ' [OFF]'}{lay} [{comps}]{pf}")

    def emit(g, ind):
        line(g, ind)
        if g in char_gos and not a.chars:
            c = char_gos[g]
            out.append("  " * (ind + 1) + f"(キャラ: GameObject {len(c['gos'])} 個・SkinnedMeshRenderer {c['smr']}・揺れもの {c['spring']}/{c['magica']}。--chars で展開)")
            return
        if a.depth is not None and ind >= a.depth:
            n = sum(1 for _ in sc.descendants(g)) - 1
            if n:
                out.append("  " * (ind + 1) + f"(子 {n} 個)")
            return
        kids = sc.child_gos(g)
        boring = [] if a.full else [c for c in kids if not sub_interesting(c)]
        for c in kids:
            if c not in boring:
                emit(c, ind + 1)
        if boring:
            total = sum(sum(1 for _ in sc.descendants(c)) for c in boring)
            names = ", ".join(sc.go_name(c) for c in boring[:6]) + (" ..." if len(boring) > 6 else "")
            out.append("  " * (ind + 1) + f"(メッシュだけの枝 {len(boring)} 本 / {total} 個: {names})")

    for t in sc.roots():
        g = sc.go_of.get(t)
        if g is None:
            continue
        if a.root and a.root not in sc.go_name(g):
            continue
        emit(g, 0)
    print("\n".join(out))
    print(f"\n({len(out)} 行, {dt:.1f}s)", file=sys.stderr)


def cmd_wiring(a):
    m, dt = _load(a.scene)
    out = [f"シーン: {a.scene}"]
    wiring(m, out)
    print("\n".join(out))
    print(f"({dt:.1f}s)", file=sys.stderr)


def cmd_chars(a):
    m, dt = _load(a.scene)
    rows = char_rows(m)
    if a.tsv:
        print("\t".join(CHAR_HEAD))
        for r in rows:
            print("\t".join(r))
    else:
        print("| " + " | ".join(CHAR_HEAD) + " |")
        print("|" + "---|" * len(CHAR_HEAD))
        for r in rows:
            print("| " + " | ".join(x.replace("|", "/") for x in r) + " |")
    print(f"({len(rows)} 体, {dt:.1f}s)", file=sys.stderr)


def cmd_check(a):
    order = {"error": 0, "warn": 1, "info": 2}
    for path in a.scene:
        m, dt = _load(path)
        f = run_checks(m)
        print(f"シーン: {path}")
        print(f"System の塊: {', '.join(m.sc.go_path(g) for g in m.system_roots) or '-'} / キャラ {len(m.chars)} 体（有効 {sum(1 for c in m.chars if c['active'])}）")
        cnt = {s: f.count(s) for s in ("error", "warn", "info")}
        print("  ".join(f"{s} {g} 件（{n} 箇所）" for s, (g, n) in cnt.items()) + f"  （読み込み {dt:.1f}s）")
        for (sev, cid, msg), items in f.sorted():
            if order[sev] > order[a.min]:
                continue
            print(f"\n[{sev}] {cid}  {msg}")
            for it in items[:a.max_items]:
                print(f"    - {it}")
            if len(items) > a.max_items:
                print(f"    ... ほか {len(items) - a.max_items} 件（--max-items で増やす）")
        print()


SUMMARY_HEAD = ["シーン", "System", "カメラ系", "キャラ（開始時に見える / 出うる / 全部）", "OSC（開くポート）", "枠（isOsc・数）",
                "Use Timeline", "DoF", "PGM にキャラのレイヤー", "OptiTrack（local → server）", "Director", "check（E / W / I）"]


def summary_row(path, m, f):
    sc, p = m.sc, m.p
    on = lambda b: "On" if b else "Off"  # noqa: E731
    sys_state = ", ".join(f"{sc.go_name(g)} {on(sc.active_in_hierarchy(g))}" for g in m.system_roots) or "-"
    cam = ", ".join(on(s["live"]) for s in m.switchers) or "-"
    chars = f"{sum(1 for c in m.chars if m.starts_visible(c))} / {sum(1 for c in m.chars if m.showable(c))} / {len(m.chars)}"
    ports = {}
    for s in m.osc_servers:
        if s["live"]:
            ports[s["port"]] = ports.get(s["port"], 0) + 1
    osc = ", ".join(f"{pt}" + (f"×{n}" if n > 1 else "") for pt, n in sorted(ports.items())) or "-"
    act = ", ".join(f"{on(a['is_osc'])}・{len(a['slots'])}" + ("" if a["live"] else "（無効）") for a in m.activators) or "-"
    tl = ", ".join(on(d["use_timeline"]) + ("" if d["live"] else "（無効）") for d in m.dmx) or "-"
    dof = []
    for d in m.dofs:
        state = on(d["live"])
        for bref, vref in ((d["pgm_brain"], d["pgm_volume"]), (d["prv_brain"], d["prv_volume"])):
            cam_ = m.brain_camera(bref)
            vg = sc.ref_go(vref)
            if cam_ is not None and vg is not None and cam_["vol_mask"] is not None and not cam_["vol_mask"] >> sc.go_fields.get(vg, {}).get("layer", 0) & 1:
                state += "・Mask 外"
                break
        dof.append(state)
    pgm = []
    for s in m.switchers:
        cam_ = m.brain_camera(s["active"])
        if cam_ is not None:
            cl = p.chara_layers()
            pgm.append(("あり" if all(cam_["cull"] >> l & 1 for l in cl) else "なし") if cl else "-")
    opti = ", ".join(f"{c['local']} → {c['server']}" + ("" if c["live"] else "（無効）") for c in m.opti_clients) or "-"
    dirs = f"{sum(1 for d in m.directors if d['live'])} / {len(m.directors)}"
    e, w, i = (f.count(s)[0] for s in ("error", "warn", "info"))
    return [os.path.splitext(os.path.basename(path))[0], sys_state, cam, chars, osc, act, tl, ", ".join(dof) or "-", ", ".join(pgm) or "-",
            opti, dirs, f"{e} / {w} / {i}"]


def cmd_summary(a):
    print("| " + " | ".join(SUMMARY_HEAD) + " |")
    print("|" + "---|" * len(SUMMARY_HEAD))
    for path in a.scene:
        m, _ = _load(path)
        print("| " + " | ".join(x.replace("|", "/") for x in summary_row(path, m, run_checks(m))) + " |")


def cmd_diff(a):
    ref, _ = _load(a.ref)
    tgt, _ = _load(a.scene)
    out = []
    run_diff(ref, tgt, out, a.ref, a.scene)
    print("\n".join(out))


def _fmt(sc, v, ind, out, key=None):
    pad = "  " * ind
    head = f"{pad}{key}: " if key is not None else f"{pad}- "
    if isinstance(v, Ref):
        out.append(head + "{" + sc.describe(v) + "}")
    elif isinstance(v, dict):
        if not v:
            out.append(head + "{}")
            return
        out.append(head.rstrip())
        for k, x in v.items():
            _fmt(sc, x, ind + 1, out, k)
    elif isinstance(v, list):
        if not v:
            out.append(head + "[]")
            return
        out.append(head.rstrip())
        for x in v:
            _fmt(sc, x, ind + 1, out)
    else:
        out.append(head + ("" if v is None else str(v)))


def cmd_show(a):
    m, _ = _load(a.scene)
    sc = m.sc
    names = set(a.names.split(","))
    skip = {"m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance", "m_PrefabAsset", "m_GameObject",
            "m_EditorHideFlags", "m_EditorClassIdentifier", "m_Script", "m_Name"}
    for k, lab in sc.all_components():
        if lab not in names:
            continue
        g = sc.go_of.get(k)
        path = sc.go_path(g) if g is not None else "?"
        if a.path and a.path not in path:
            continue
        src = sc.from_prefab.get(k)
        ov = len(sc.overrides.get(k, {}))
        print(f"##### {lab} @ {path}  （有効 {'On' if sc.comp_active(k) else 'Off'}{', プレハブ ' + src if src else ''}{f', 上書き {ov}' if ov else ''}）")
        out = []
        for key, v in sc.body(k).items():
            if key not in skip:
                _fmt(sc, v, 1, out, key)
        print("\n".join(out[:a.lines]))
        if len(out) > a.lines:
            print(f"  ... ほか {len(out) - a.lines} 行（--lines で増やす）")


def main():
    global PROJECT
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="Unity プロジェクトのフォルダ（シーンがプロジェクトの外にあるとき。省略時はシーンの上をたどって探す）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("dump")
    s.add_argument("scene")
    s.add_argument("--root", help="名前にこの文字を含むルートだけ")
    s.add_argument("--depth", type=int, help="この深さまで（それより下は数だけ）")
    s.add_argument("--chars", action="store_true", help="キャラの中も展開する")
    s.add_argument("--full", action="store_true", help="メッシュだけの枝もまとめずに出す")
    s.set_defaults(fn=cmd_dump)
    s = sub.add_parser("wiring")
    s.add_argument("scene")
    s.set_defaults(fn=cmd_wiring)
    s = sub.add_parser("chars")
    s.add_argument("scene")
    s.add_argument("--tsv", action="store_true")
    s.set_defaults(fn=cmd_chars)
    s = sub.add_parser("check")
    s.add_argument("scene", nargs="+")
    s.add_argument("--min", choices=("error", "warn", "info"), default="info", help="この重さ以上だけ出す")
    s.add_argument("--max-items", type=int, default=12, help="1 つの指摘に並べる物の数")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("summary")
    s.add_argument("scene", nargs="+")
    s.set_defaults(fn=cmd_summary)
    s = sub.add_parser("diff")
    s.add_argument("scene")
    s.add_argument("--ref", required=True, help="基準のシーン")
    s.set_defaults(fn=cmd_diff)
    s = sub.add_parser("show")
    s.add_argument("scene")
    s.add_argument("names", help="コンポーネント名（カンマ区切り。MonoBehaviour はクラス名）")
    s.add_argument("--path", help="GameObject のパスにこの文字を含むものだけ")
    s.add_argument("--lines", type=int, default=80)
    s.set_defaults(fn=cmd_show)
    a = ap.parse_args()
    PROJECT = a.project
    for attr in ("scene", "ref"):
        v = getattr(a, attr, None)
        for pth in (v if isinstance(v, list) else [v]):
            if pth and not os.path.exists(pth):
                raise SystemExit(f"シーンが無い: {pth}")
    a.fn(a)


if __name__ == "__main__":
    main()
