"""2 つのシーンの System の塊と配線を比べる（新しく組んだシーンを、基準のシーンと突き合わせる用）。

System の塊は、ルートの名前を「System」に揃えた相対パスで GameObject を突き合わせる（System_GrandStage と System_PrimeStage も比べられる）。
キャラはシーンごとに違うので、構成の比較からは外し、配線ではキャラごとではなく「キャラへの配線 N 本」に丸める。
"""
from vortex_report import DMX_RECEIVER, OPTI_CONN, OPTI_COORD, OPTI_NAMING, UPDATE, _enum, _on


def _norm_path(m, path):
    for g in m.system_roots:
        name = m.sc.go_name(g)
        if path == name or path.startswith(name + "/"):
            return "System" + path[len(name):]
    return path


def _tree(m):
    """System の塊の GameObject: 相対パス → (有効, レイヤー, コンポーネント, プレハブ)。同名の兄弟は #2, #3 を付ける。"""
    sc = m.sc
    out = {}

    def walk(g, path):
        comps = tuple(sorted(sc.label(k) for k in sc.components(g)))
        gf = sc.go_fields.get(g, {})
        out[path] = (gf.get("active", True), gf.get("layer", 0), comps, sc.instance_root.get(g))
        seen = {}
        for ch in sc.child_gos(g):
            n = sc.go_name(ch)
            seen[n] = seen.get(n, 0) + 1
            walk(ch, f"{path}/{n}" + (f"#{seen[n]}" if seen[n] > 1 else ""))
    for i, g in enumerate(m.system_roots):
        walk(g, "System" + (f"#{i + 1}" if i else ""))
    return out


def _roots(m):
    """System とキャラ置き場以外のルート: 名前 → (有効, プレハブ)。"""
    sc = m.sc
    char_roots = {next(iter(reversed(list(sc.ancestors(c["go"]))))) for c in m.chars}
    out = {}
    for t in sc.roots():
        g = sc.go_of.get(t)
        if g is None or g in m.system_roots or g in char_roots:
            continue
        base = n = sc.go_name(g)
        i = 1
        while n in out:
            i += 1
            n = f"{base} #{i}"
        out[n] = (sc.go_fields.get(g, {}).get("active", True), sc.instance_root.get(g))
    return out


def _target_label(m, ref, method):
    """リスナーの先: キャラの中なら「キャラ.<コンポーネント>」に丸める。"""
    sc = m.sc
    g = sc.ref_go(ref)
    if g is None:
        return f"None.{method}"
    lab = sc.label(ref.key) if sc.objs.get(ref.key) is not None and sc.objs[ref.key].cls != "1" else "GameObject"
    if g in m.char_of:
        return f"<キャラ>.{lab}.{method}"
    return f"{_norm_path(m, sc.go_path(g))} ({lab}).{method}"


def facts(m):
    """比べる事実: (節, 項目) → 値の文字列。"""
    sc, p = m.sc, m.p
    F = {}
    for s in m.osc_servers:
        key = _norm_path(m, m.where(s["key"]))
        F[("OSC", f"{key} [{s['kind']}]")] = f"port {s['port']} autoStart {_on(s['auto'])}{'' if s['active'] else ' (無効)'}"
        counts = {}
        for c in s["listeners"]:
            t = _target_label(m, c["target"], c["method"])
            counts[t] = counts.get(t, 0) + 1
        for t, n in counts.items():
            F[("OSC のリスナー", f"{key} → {t}")] = f"{n} 本"
    for a in m.activators:
        key = _norm_path(m, m.where(a["key"]))
        F[("CharacterActivator", key)] = f"isOsc {_on(a['is_osc'])}{'' if a['live'] else ' (無効)'}"
        for nm in ("lookat", "switcher", "between", "state_client"):
            F[("CharacterActivator", f"{key} _{nm}")] = _norm_path(m, m.ref_label(a[nm]))
        F[("CharacterActivator", f"{key} 枠の数")] = str(len(a["slots"]))
        effs = sorted({m.asset_label(r[e]).split("/")[-1] for rs in a["slots"] for r in rs for e in ("in_effect", "out_effect")})
        F[("CharacterActivator", f"{key} エフェクト")] = ", ".join(effs)
    for la in m.lookats:
        key = _norm_path(m, m.where(la["key"]))
        fixed = [t["name"] for t in la["targets"] if m.char_of.get(sc.ref_go(t["hip"])) is None]
        F[("LookatManager", key)] = f"固定の注視先 [{', '.join(fixed)}] キャラ {len(la['targets']) - len(fixed)} 体{'' if la['live'] else ' (無効)'}"
    for s in m.switchers:
        key = _norm_path(m, m.where(s["key"]))
        F[("スイッチャー", f"{key} 有効")] = _on(s["live"])
        F[("スイッチャー", f"{key} 入力の並び")] = " | ".join(f"{i}:{n}" for i, n in enumerate(s["input_names"]))
        for nm in ("rt_a", "rt_b", "material", "output"):
            F[("スイッチャー", f"{key} {nm}")] = m.asset_label(s[nm])
        for role, bref in (("PGM", s["active"]), ("PRV", s["reserve"])):
            cam = m.brain_camera(bref)
            if cam is None:
                F[("スイッチャー", f"{key} {role}")] = "Camera 無し"
                continue
            F[("スイッチャー", f"{key} {role} RT")] = m.asset_label(cam["rt"])
            F[("スイッチャー", f"{key} {role} Culling")] = p.mask_names(cam["cull"])
            F[("スイッチャー", f"{key} {role} VolumeMask")] = p.mask_names(cam["vol_mask"]) if cam["vol_mask"] is not None else "-"
            F[("スイッチャー", f"{key} {role} Post")] = _on(cam["post"])
    for c in m.switch_controllers:
        F[("スイッチャー", f"{_norm_path(m, m.where(c['key']))} [{c['kind']}] isOsc")] = _on(c["is_osc"])
    for d in m.dofs:
        for role, v in (("PGM", d["pgm_volume"]), ("PRV", d["prv_volume"])):
            vg = sc.ref_go(v)
            F[("DoF", f"{role} Volume のレイヤー")] = p.layer_name(sc.go_fields.get(vg, {}).get("layer", 0)) if vg is not None else "None"
    for mc in m.mics:
        key = _norm_path(m, m.where(mc["key"]))
        F[("MicController", key)] = f"isOsc {_on(mc['is_osc'])} {_enum(UPDATE, mc['update'])} 枠 {len(mc['targets'])}{'' if mc['live'] else ' (無効)'}"
    for d in m.dmx:
        key = _norm_path(m, m.where(d["key"]))
        F[("DMX", key)] = f"{_enum(DMX_RECEIVER, d['receiver_type'])} Use Timeline {_on(d['use_timeline'])}{'' if d['live'] else ' (無効)'}"
        F[("DMX", f"{key} OnMetaDmx")] = ", ".join(_target_label(m, c["target"], c["method"]) for c in d["calls"]) or "(無し)"
    for c in m.opti_clients:
        key = _norm_path(m, m.where(c["key"]))
        F[("OptiTrack", key)] = (f"server {c['server']} local {c['local']} {_enum(OPTI_CONN, c['conn'])} {_enum(OPTI_COORD, c['coords'])}"
                                 f" {_enum(OPTI_NAMING, c['naming'])}{'' if c['live'] else ' (無効)'}")
    for c in m.cameras:
        if not c["live"] or m.char_of.get(c["go"]) is not None:
            continue
        key = _norm_path(m, m.where(c["key"]))
        dest = f"RT {m.asset_label(c['rt'])}" if c["rt"] else f"Display {c['display'] + 1}"
        F[("カメラ（有効）", key)] = f"{dest} Culling {p.mask_names(c['cull'])}"
    for cv in m.canvases:
        if not cv["live"] or not cv["raws"]:
            continue
        key = _norm_path(m, m.where(cv["key"]))
        tex = ", ".join(sorted(m.asset_label(r["texture"]).split("/")[-1] for r in cv["raws"] if r["live"]))
        F[("出力（Canvas）", key)] = f"Display {cv['display'] + 1} [{tex}]"
    for v in m.volumes:
        key = _norm_path(m, m.where(v["key"]))
        F[("Volume", key)] = f"レイヤー {p.layer_name(v['layer'])} {m.asset_label(v['profile'])}{'' if v['live'] else ' (無効)'}"
    for w in m.waters:
        F[("水", _norm_path(m, m.where(w["key"])))] = _norm_path(m, m.ref_label(w["camera"]))
    crl = sum(1 << i for i in p.chara_rendering_layers())
    F[("キャラ用ライト", "有効な数")] = str(sum(1 for l in m.lights if l["live"] and l["rl"] is not None and l["rl"] & crl))
    for e in m.ext_controls:
        F[("ExternalControlManager", _norm_path(m, m.where(e["key"])))] = ", ".join(d["name"] for d in e["devices"]) or "(無し)"
    F[("キャラ", "数（有効 / 全部）")] = f"{sum(1 for c in m.chars if c['active'])} / {len(m.chars)}"
    F[("キャラ", "OSC の配線があるキャラ")] = str(sum(1 for c in m.chars if c["osc"]))
    F[("Timeline", "PlayableDirector の数（有効）")] = str(sum(1 for d in m.directors if d["live"]))
    return F


def diff(ref, tgt, out, ref_name, tgt_name):
    p = tgt.p
    out.append(f"基準: {ref_name}")
    out.append(f"対象: {tgt_name}")
    # 構成
    a, b = _tree(ref), _tree(tgt)
    only_a = [k for k in a if k not in b]
    only_b = [k for k in b if k not in a]

    def top_only(keys, other):
        keys = sorted(keys)
        res = []
        for k in keys:
            if any(k.startswith(r + "/") for r in res):
                continue
            res.append(k)
        return [(k, sum(1 for x in keys if x.startswith(k + "/"))) for k in res]
    out.append("== System の塊の構成")
    if not ref.system_roots or not tgt.system_roots:
        out.append(f"  System の塊: 基準 {len(ref.system_roots)} / 対象 {len(tgt.system_roots)}")
    n = 0
    for k, sub in top_only(only_a, b):
        out.append(f"  基準だけ: {k}  [{', '.join(a[k][2])}]" + (f"  (+子 {sub})" if sub else ""))
        n += 1
    for k, sub in top_only(only_b, a):
        out.append(f"  対象だけ: {k}  [{', '.join(b[k][2])}]" + (f"  (+子 {sub})" if sub else ""))
        n += 1
    layer_diff = {}
    for k in sorted(set(a) & set(b)):
        (aa, al, ac, ap), (ba, bl, bc, bp) = a[k], b[k]
        if ac != bc:
            ra = sorted(set(ac) - set(bc))
            rb = sorted(set(bc) - set(ac))
            out.append(f"  コンポーネント: {k}  基準だけ {ra or '-'} / 対象だけ {rb or '-'}")
            n += 1
        if aa != ba:
            out.append(f"  有効: {k}  基準 {_on(aa)} / 対象 {_on(ba)}")
            n += 1
        if al != bl:
            layer_diff[k] = (al, bl)
        if (ap or "") != (bp or ""):
            out.append(f"  プレハブ: {k}  基準 {ap or '-'} / 対象 {bp or '-'}")
            n += 1
    # レイヤーの違いは、親と同じ違いの子をまとめて 1 行に（Camera 以下が丸ごと違う、など）
    for k, (al, bl) in sorted(layer_diff.items()):
        parent = k.rsplit("/", 1)[0] if "/" in k else None
        if parent is not None and layer_diff.get(parent) == (al, bl):
            continue
        sub = sum(1 for x, v in layer_diff.items() if x.startswith(k + "/") and v == (al, bl))
        out.append(f"  レイヤー: {k}" + (f"（と子 {sub} 個）" if sub else "") + f"  基準 {p.layer_name(al)} / 対象 {p.layer_name(bl)}")
        n += 1
    if not n:
        out.append("  差なし")
    # ルートの部品
    ra, rb = _roots(ref), _roots(tgt)
    out.append("== ルートの部品（System・キャラ置き場以外）")
    n = 0
    for k in sorted(set(ra) - set(rb)):
        out.append(f"  基準だけ: {k}{'' if ra[k][0] else ' (無効)'}{'  <' + ra[k][1] + '>' if ra[k][1] else ''}")
        n += 1
    for k in sorted(set(rb) - set(ra)):
        out.append(f"  対象だけ: {k}{'' if rb[k][0] else ' (無効)'}{'  <' + rb[k][1] + '>' if rb[k][1] else ''}")
        n += 1
    for k in sorted(set(ra) & set(rb)):
        if ra[k] != rb[k]:
            out.append(f"  違う: {k}  基準 {_on(ra[k][0])} {ra[k][1] or ''} / 対象 {_on(rb[k][0])} {rb[k][1] or ''}")
            n += 1
    if not n:
        out.append("  差なし")
    # 配線
    fa, fb = facts(ref), facts(tgt)
    sections = []
    for sec, _ in list(fa) + list(fb):
        if sec not in sections:
            sections.append(sec)
    out.append("== 配線・設定")
    total = 0
    for sec in sections:
        keys = sorted({k for s, k in fa if s == sec} | {k for s, k in fb if s == sec})
        lines = []
        for k in keys:
            va, vb = fa.get((sec, k)), fb.get((sec, k))
            if va == vb:
                continue
            if va is None:
                lines.append(f"    対象だけ: {k} = {vb}")
            elif vb is None:
                lines.append(f"    基準だけ: {k} = {va}")
            else:
                lines.append(f"    違う: {k}\n      基準 {va}\n      対象 {vb}")
        if lines:
            out.append(f"  [{sec}]")
            out.extend(lines)
            total += len(lines)
    if not total:
        out.append("  差なし")
    return out
