"""scene_audit.py の wiring / chars の書き出し（Model を人が読む形に）。"""
from vortex_model import FACIAL_DEVICE

DMX_RECEIVER = ["DontReceive", "ArtNet", "sACN", "RDMNet", "MSSP"]  # MetaDmxReceiver.ReceiverType の並び
OPTI_CONN = ["Multicast", "Unicast"]  # OptitrackStreamingClient.ClientConnectionType
OPTI_COORD = ["Local", "Global"]  # StreamingCoordinatesValues
OPTI_NAMING = ["Motive", "FBX", "BVH"]  # OptitrackBoneNameConvention
CALL_STATE = {"0": "Off", "1": "Editor+Runtime", "2": "RuntimeOnly"}
MIC_AXIS = ["+Y", "-Y", "+X", "-X", "+Z", "-Z"]  # MicAutoCorrectionMath.MicAimAxis（PositiveY = 0 から）
MIC_PLACE = ["MicTransform", "Hand"]  # MicAutoCorrectionMath.MicPlacementReference
UPDATE = ["Update", "FixedUpdate", "LateUpdate"]  # mUtility.UpdateMethod


def _enum(lst, i):
    return lst[i] if 0 <= i < len(lst) else str(i)


def _on(b):
    return "On" if b else "Off"


def _live(x):
    return "" if x else "  (無効)"


def wiring(m, out):
    sc, p = m.sc, m.p
    out.append(f"== System の塊: {', '.join(sc.go_path(g) for g in m.system_roots) or '(System で始まるルートが無い)'}")

    out.append("== OSC")
    for s in m.osc_servers:
        out.append(f"  [{s['kind']}] {m.where(s['key'])}  port {s['port']}  autoStart {_on(s['auto'])}{_live(s['active'])}")
        for c in s["listeners"]:
            st = "" if c["state"] == "2" else f"  ({CALL_STATE.get(c['state'], c['state'])})"
            out.append(f"     → {m.ref_label(c['target'])} . {c['method']}{st}")
    for r in m.osc_receivers:
        out.append(f"  [OscReceiverEx] {m.where(r['key'])}  server {m.ref_label(r['server'])}{_live(r['live'])}")
        for pr in r["pairs"]:
            calls = ", ".join(f"{m.ref_label(c['target']).split(' (')[-1].rstrip(')')}.{c['method']}" for c in pr["calls"]) or "(リスナー無し)"
            out.append(f"     {pr['address']} → {calls}")
    flags = [f"{m.where(a['key']).split('/')[-1]}(CharacterActivator) {_on(a['is_osc'])}" for a in m.activators]
    flags += [f"MicController {_on(mc['is_osc'])}" for mc in m.mics]
    flags += [f"{c['kind']} {_on(c['is_osc'])}" for c in m.switch_controllers]
    if flags:
        out.append("  _isOsc: " + " / ".join(flags))

    for a in m.activators:
        out.append(f"== CharacterActivator  {m.where(a['key'])}  isOsc {_on(a['is_osc'])}{_live(a['live'])}")
        out.append(f"  lookat {m.ref_label(a['lookat'])} / switcher {m.ref_label(a['switcher'])} / between {m.ref_label(a['between'])}"
                   f" / stateClient {m.ref_label(a['state_client'])}")
        for si, reserves in enumerate(a["slots"]):
            if not reserves:
                out.append(f"  [{si}] (予備キャラ無し)")
            for ri, r in enumerate(reserves):
                tg = sc.ref_go(r["target"])
                hip = m.ref_label(r["hip"])
                name = sc.go_name(tg) if tg is not None else "None"
                base = sc.go_path(tg) if tg is not None else ""
                hip_rel = hip[len(base) + 1:] if base and hip.startswith(base + "/") else hip
                eff = f"in {m.asset_label(r['in_effect']).split('/')[-1]} {r['in_delay']:g}s / out {m.asset_label(r['out_effect']).split('/')[-1]} {r['out_delay']:g}s"
                sec = f" secondary {m.ref_label(r['secondary'])}" if r["secondary"] else ""
                out.append(f"  [{si}]{'.' + str(ri) if len(reserves) > 1 else ''} {name}  hip {hip_rel}  {eff}{sec}")

    for la in m.lookats:
        out.append(f"== LookatManager  {m.where(la['key'])}{_live(la['live'])}")
        for ti, t in enumerate(la["targets"]):
            out.append(f"  [{ti}] {t['name']}  hip {m.ref_label(t['hip'])}  head {m.ref_label(t['head']).split('/')[-1]}")

    for s in m.switchers:
        out.append(f"== スイッチャー  {m.where(s['key'])}{_live(s['live'])}")
        for role, bref in (("PGM", s["active"]), ("PRV", s["reserve"])):
            cam = m.brain_camera(bref)
            if cam is None:
                out.append(f"  {role}: Brain {m.ref_label(bref)}（Camera が無い）")
                continue
            out.append(f"  {role}: {m.where(cam['key'])}  RT {m.asset_label(cam['rt'])}  Culling {p.mask_names(cam['cull'])}"
                       f"  VolumeMask {p.mask_names(cam['vol_mask']) if cam['vol_mask'] is not None else '-'}  Post {_on(cam['post'])}{_live(cam['live'])}")
        out.append(f"  RT A {m.asset_label(s['rt_a'])} / B {m.asset_label(s['rt_b'])} / material {m.asset_label(s['material'])}"
                   f" / output {m.asset_label(s['output'])} / preview {m.ref_label(s['preview'])}")
        out.append(f"  入力 {len(s['inputs'])}: " + "  ".join(f"[{i}] {n}" for i, n in enumerate(s["input_names"])))
    for c in m.switch_controllers:
        out.append(f"  [{c['kind']}] {m.where(c['key'])}  switcher {m.ref_label(c['switcher'])}  isOsc {_on(c['is_osc'])}{_live(c['live'])}")

    for d in m.dofs:
        out.append(f"== DoF  {m.where(d['key'])}{_live(d['live'])}")
        for role, b, v in (("PGM", d["pgm_brain"], d["pgm_volume"]), ("PRV", d["prv_brain"], d["prv_volume"])):
            vg = sc.ref_go(v)
            lay = p.layer_name(sc.go_fields.get(vg, {}).get("layer", 0)) if vg is not None else "-"
            out.append(f"  {role}: Brain {m.ref_label(b)}  Volume {m.ref_label(v)}（レイヤー {lay}）")

    for mc in m.mics:
        out.append(f"== MicController  {m.where(mc['key'])}  isOsc {_on(mc['is_osc'])}  {_enum(UPDATE, mc['update'])}{_live(mc['live'])}")
        for ti, t in enumerate(mc["targets"]):
            mics = ", ".join(m.ref_label(r).split("/")[-1] for r in t["mics"]) or "-"
            out.append(f"  [{ti}] {t['name']}  animator {m.ref_label(t['animator'])}  手 {t['hand']}  {t['correction']}  enable {_on(t['enable'])}")
            out.append(f"       mics [{mics}]  grip {m.asset_label(t['grip']).split('/')[-1]}（{m.preset_hand(t['grip']) or '-'}）"
                       f"  micT {m.ref_label(t['mic_t']).split('/')[-1]}  mouth {m.ref_label(t['mouth']).split('/')[-1]}"
                       f"  axis {_enum(MIC_AXIS, t['axis'])}  place {_enum(MIC_PLACE, t['place_ref'])}  mouthDist {t['mouth_dist']}  handAim {_on(t['hand_aim'])}")

    for d in m.dmx:
        calls = ", ".join(f"{m.ref_label(c['target'])}.{c['method']}" for c in d["calls"]) or "(無し)"
        out.append(f"== DMX  {m.where(d['key'])}  {_enum(DMX_RECEIVER, d['receiver_type'])}  Use Timeline {_on(d['use_timeline'])}{_live(d['live'])}")
        out.append(f"  OnMetaDmx → {calls}")
    if m.fixtures:
        by_u = {}
        for fx in m.fixtures:
            by_u.setdefault(fx["universe"], []).append(fx)
        out.append("  灯体（VF_*）: " + "  ".join(f"U{u} {len(fs)} 台" for u, fs in sorted(by_u.items())))

    for c in m.opti_clients:
        out.append(f"== OptiTrack  {m.where(c['key'])}  server {c['server']}  local {c['local']}  {_enum(OPTI_CONN, c['conn'])}"
                   f"  coords {_enum(OPTI_COORD, c['coords'])}  naming {_enum(OPTI_NAMING, c['naming'])}{_live(c['live'])}")

    out.append("== カメラ（有効なもの。Display は 1 始まり）")
    for c in sorted(m.cameras, key=lambda c: m.where(c["key"])):
        if not c["live"]:
            continue
        dest = f"RT {m.asset_label(c['rt'])}" if c["rt"] else f"Display {c['display'] + 1}"
        vm = p.mask_names(c["vol_mask"]) if c["vol_mask"] is not None else "-"
        out.append(f"  {m.where(c['key'])}  {dest}  Culling {p.mask_names(c['cull'])}  VolumeMask {vm}  Post {_on(c['post'])}"
                   f"{'  tag MainCamera' if c['tag'] == 'MainCamera' else ''}")
    out.append("== Volume")
    for v in m.volumes:
        out.append(f"  {m.where(v['key'])}  レイヤー {p.layer_name(v['layer'])}  {'Global' if v['is_global'] else 'Local'}"
                   f"  priority {v['priority']}  weight {v['weight']}  {m.asset_label(v['profile'])}{_live(v['live'])}")
    crl = p.chara_rendering_layers()
    cbits = sum(1 << i for i in crl)
    lights = [l for l in m.lights if l["rl"] is not None and l["rl"] & cbits]
    # Everything（全ビット）は灯体のライトに多く、キャラ用に置いたライトではないので数だけ出す
    only = [l for l in lights if l["rl"] & 0xFFFFFFFF != 0xFFFFFFFF]
    rest = [l for l in lights if l["rl"] & 0xFFFFFFFF == 0xFFFFFFFF]
    out.append(f"== キャラ用ライト（Rendering Layer に {', '.join(p.rendering_layers[i] for i in crl) or '-'} を含む。Everything は数だけ）")
    for l in sorted(only, key=lambda l: m.where(l["key"])):
        out.append(f"  {m.where(l['key'])}  Rendering Layer {p.rl_names(l['rl'])}  強さ {l['intensity']}{_live(l['live'])}")
    if rest:
        out.append(f"  ほかに Rendering Layer が Everything など広いライト {len(rest)} 個（有効 {sum(1 for l in rest if l['live'])}）")
    out.append("== 出力（Canvas。Display は 1 始まり）")
    for cv in m.canvases:
        if not cv["live"] or not cv["raws"]:
            continue
        mode = ["Overlay", "Camera", "World"][cv["mode"]] if 0 <= cv["mode"] < 3 else str(cv["mode"])
        raws = ", ".join(f"{m.where(r['key']).split('/')[-1]}={m.asset_label(r['texture']).split('/')[-1]}"
                         + (f"+{m.asset_label(r['material']).split('/')[-1]}" if r["material"] else "") for r in cv["raws"] if r["live"])
        out.append(f"  {m.where(cv['key'])}  {mode}  Display {cv['display'] + 1}  [{raws}]")
    out.append("== Timeline（PlayableDirector）")
    for d in m.directors:
        nb = sum(1 for b in d["binds"] if b["value"])
        out.append(f"  {m.where(d['key'])}  {m.asset_label(d['asset'])}  PlayOnAwake {_on(d['play_on_awake'])}"
                   f"  結び付け {nb}/{len(d['binds'])}{_live(d['live'])}")
    for w in m.waters:
        out.append(f"== 水  {m.where(w['key'])}  Camera {m.ref_label(w['camera'])}{_live(w['live'])}")
    for e in m.ext_controls:
        devs = ", ".join(f"{d['name']}→{m.ref_label(d['target'])}" for d in e["devices"]) or "(Control Devices 無し)"
        out.append(f"== ExternalControlManager  {m.where(e['key'])}  {devs}{_live(e['live'])}")


def char_rows(m):
    """キャラ 1 体 1 行の表（列は chars の見出しと同じ順）。"""
    sc, p = m.sc, m.p
    rows = []
    for c in m.chars:
        face = []
        for e in c["facial"]:
            face.append(f"FM:{FACIAL_DEVICE.get(e['device'], e['device'])}" + ("" if e["enabled"] else "(off)"))
        for e in c["lipsync"]:
            face.append("OscLip" + ("" if e["enabled"] else "(off)"))
        for e in c["vfc"]:
            face.append("vFC" + (f":{e['label']}" if e["label"] else "") + ("" if e["enabled"] else "(off)"))
        if c["ulipsync"]:
            face.append("uLipSync")
        ids = "/".join(str(e["id"]) for e in c["lipsync"]) or "-"
        fids = "/".join(str(e["id"]) for e in c["facial"]) or "-"
        osc = "ok" if c["osc"] else ("-" if not (c["lipsync"] or c["facial"]) else "無し")
        sk = ", ".join(o["skeleton"] for o in c["opti"]) or "-"
        layers = ", ".join(f"{p.layer_name(l)}x{n}" for l, n in sorted(c["go_layers"].items())) or "-"
        rls = ", ".join(f"{p.rl_names(rl)}x{n}" for rl, n in sorted(c["rls"].items())) or "-"
        slots = ", ".join(f"{si}" + (f".{ri}" if ri else "") for (_, si, ri) in c["slots"]) or "-"
        mic = ", ".join(m.mics[mi]["targets"][ti]["name"] for mi, ti in c["mic"]) or "-"
        props = ", ".join(sorted({sc.go_name(g) for g in c["props"]}))[:60] or "-"
        scale = "-"
        if c["scale"]:
            # 表示だけ小数 4 桁に丸める（0.97999996 のような float の表し方の端数を見せない）
            vals = []
            for v in c["scale"]:
                try:
                    vals.append(f"{float(v):.4f}".rstrip("0").rstrip("."))
                except (TypeError, ValueError):
                    vals.append(str(v))
            scale = vals[0] if len(set(vals)) == 1 else "/".join(vals)
        origin = c["origin"].replace("instance ", "PI ").split("/")[-1] if c["origin"] != "scene" else "scene"
        rows.append([c["name"].replace("(NiloToon)_setupped", ""), "on" if c["active"] else ("off" if not c["active_self"] else "off(親)"),
                     p.layer_name(c["layer"]), layers, rls, origin, "+".join(face) or "-", f"{ids} / {fids}", osc, sk, slots,
                     "yes" if c["lookat"] else "-", mic, str(scale), f"{c['spring']}/{c['magica']}", props])
    return rows


CHAR_HEAD = ["キャラ", "有効", "Layer(root)", "Renderer の Layer", "Rendering Layer", "由来", "表情・口", "ID(Lip / Facial)", "OSC",
             "Skeleton", "枠", "注視", "マイク枠", "scale", "揺れ(VRM/Magica)", "小物"]
