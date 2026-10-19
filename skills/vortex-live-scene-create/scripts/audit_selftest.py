"""scene_audit の check が、入れた問題を拾うか（見逃し）と、入れていない所で増えないか（誤検出）を確かめる変異の試験。

  python audit_selftest.py <scene>... [--project <Unity プロジェクト>]

シーンの写しを %TEMP%/vortex-scene-audit/selftest/ に作り、問題を 1 つずつ入れて check を流す。
「検出」の条件は 3 つとも満たすこと: 期待した規則で、期待した重さで、変えた物（anchor の文字列）を含む項目が増えた（または消えた）。
同じ規則の別の物の文言が変わっただけでは検出にしない。期待外の規則で増えた・消えた物は「巻き添え」として並べる。
変異はシーンの塊の書き換え（シーンの中の物）と、PrefabInstance の m_Modifications への追記（プレハブの上書き・配列の上書き）。
当てはまる物が無い変異は「対象なし」と出す（試していない規則が分かるように）。最後に LFS のポインタを読ませて止まるかも見る。
規則を足したり変えたりしたら、構成の違う 2 シーン以上（test・test_Azuki・vortex_urp のシーンなど）に流す。見逃しが 1 つでもあれば終了コード 1。
"""
import argparse
import json
import os
import re
import sys
import tempfile

from vortex_checks import run as run_checks
from vortex_model import Model
from vortex_scene import LFS_HEAD, MASK, Project, open_scene, setup_stdio

FAKE_GUID = "0123456789abcdef0123456789abcdef"  # 「無いアセット」を指す GUID。プロジェクトに無いことは main で GUID 表を引いて確かめる


def _nl(text):
    return "\r\n" if "\r\n" in text[:2000] else "\n"


def _block(text, fid):
    """塊 --- !u!N &fid の (先頭, 末尾)。"""
    m = re.search(r"(?m)^--- !u!\d+ &" + re.escape(str(fid)) + r"( stripped)?\r?$", text)
    if not m:
        return None
    nxt = re.compile(r"(?m)^--- !u!").search(text, m.end())
    return m.start(), nxt.start() if nxt else len(text)


def _sub_in_block(text, fid, pattern, repl, start_at=None, nth=0):
    """塊の中で当たる nth 番目（0 始まり）の 1 か所だけを置き換える（start_at があれば、その文字列より後から探す）。"""
    b = _block(text, fid)
    if b is None:
        return None
    s, e = b
    body = text[s:e]
    off = 0
    if start_at:
        i = body.find(start_at)
        if i < 0:
            return None
        off = i
    ms = list(re.compile(pattern, re.M).finditer(body, off))
    if len(ms) <= nth:
        return None
    m = ms[nth]
    new = body[:m.start()] + m.expand(repl) + body[m.end():]
    return text[:s] + new + text[e:]


def _native(m, k):
    """シーンの中の塊（プレハブ由来でない）なら、その fileID。"""
    sc = m.sc
    d = sc.objs.get(k)
    if d is None or sc.from_prefab.get(k) is not None or not d.text:
        return None
    return int(d.fid) if int(d.fid) == k else None


def _instance_of(m, k):
    """プレハブから来た物 k の、シーンの PrefabInstance の fileID・元のプレハブの GUID・元の fileID（1 段目のプレハブの物だけ）。"""
    sc = m.sc
    d = sc.objs.get(k)
    if d is None or not d.text or sc.from_prefab.get(k) is None:
        return None
    q = int(d.fid)
    for pd in sc.docs:
        if pd.cls != "1001":
            continue
        pi = int(pd.fid)
        if (q ^ pi) & MASK == k:
            g = re.search(r"m_SourcePrefab: \{fileID: \d+, guid: ([0-9a-f]{32})", pd.text)
            if g:
                return pi, g.group(1), q
    return None


def _add_mod(text, pi, target, guid, path, value="", objref="{fileID: 0}"):
    """PrefabInstance の m_Modifications に 1 件足す（後に書いた物が勝つので、末尾に足す）。"""
    b = _block(text, pi)
    if b is None:
        return None
    nl = _nl(text)
    s, e = b
    body = text[s:e]
    entry = (f"    - target: {{fileID: {target}, guid: {guid}, type: 3}}{nl}      propertyPath: {path}{nl}"
             f"      value: {value}{nl}      objectReference: {objref}{nl}")
    if f"    m_Modifications: []{nl}" in body:
        body = body.replace(f"    m_Modifications: []{nl}", f"    m_Modifications:{nl}" + entry, 1)
    else:
        mm = re.search(r"(?m)^    m_Modifications:\r?\n((?:    - .*\r?\n|      .*\r?\n)*)", body)
        if not mm:
            return None
        body = body[:mm.end()] + entry + body[mm.end():]
    return text[:s] + body + text[e:]


def _mut(name, rule, sev, anchor, text, expect="add"):
    return dict(name=name, rule=rule, sev=sev, anchor=anchor, text=text, expect=expect)


def mutations(m, text):
    """変異を順に返す（当てはまらない物は text=None）。"""
    sc = m.sc
    p = m.p

    def sev_of(live, base):
        return base if live else "info"

    # 1. CharacterActivator の予備キャラ（シーンの中の物）
    a = next((a for a in m.activators if _native(m, a["key"]) and any(r["target"] for rs in a["slots"] for r in rs)), None)
    if a:
        fid, w, sv = _native(m, a["key"]), m.where(a["key"]), sev_of(a["live"], "warn")
        yield _mut("予備キャラを None に", "act.target-none", sv, w, _sub_in_block(text, fid, r"_targetCharacter: \{fileID: [1-9-]\d*\}", "_targetCharacter: {fileID: 0}"))
        yield _mut("Lookat Bone_hip を None に", "act.hip-none", sv, w, _sub_in_block(text, fid, r"_lookatBone_hip: \{fileID: [1-9-]\d*\}", "_lookatBone_hip: {fileID: 0}"))
        yield _mut("登場のエフェクトを None に", "act.effect-none", sv, w,
                   _sub_in_block(text, fid, r"_in_effect: \{fileID: \d+, guid: [0-9a-f]{32}, type: \d\}", "_in_effect: {fileID: 0}"))
    else:
        for n, r in (("予備キャラを None に", "act.target-none"), ("Lookat Bone_hip を None に", "act.hip-none"), ("登場のエフェクトを None に", "act.effect-none")):
            yield _mut(n, r, None, None, None)
    # 2. uOscServer のリスナー
    s = next((s for s in m.osc_servers if _native(m, s["key"]) and s["kind"] == "uOscServer" and s["listeners"]), None)
    if s:
        fid, w = _native(m, s["key"]), m.where(s["key"])
        yield _mut("OSC のリスナーの先を None に", "osc.listener-broken", sev_of(s["live"], "warn"), w,
                   _sub_in_block(text, fid, r"- m_Target: \{fileID: [1-9-]\d*\}", "- m_Target: {fileID: 0}"))
        target = None
        if s["live"]:
            for c in m.chars:
                e = next((e for e in c["lipsync"] if _native(m, e["key"]) and e["wired"] and e["enabled"]), None)
                if e and m.showable(c) and c["setup"]:
                    target = (c, e)
                    break
        if target:
            c, e = target
            pat = r"      - m_Target: \{fileID: " + str(e["key"]) + r"\}\r?\n(?:        .*\r?\n)*?        m_CallState: \d\r?\n"
            yield _mut(f"{c['name']} の口パクのリスナーを消す", "osc.unwired", "warn", c["path"], _sub_in_block(text, fid, pat, ""))
        else:
            yield _mut("キャラの口パクのリスナーを消す", "osc.unwired", None, None, None)
    else:
        yield _mut("OSC のリスナーの先を None に", "osc.listener-broken", None, None, None)
        yield _mut("キャラの口パクのリスナーを消す", "osc.unwired", None, None, None)
    # 3. OscServerEx のポートを uOscServer と同じに（両方が開く）
    us = [s for s in m.osc_servers if s["kind"] == "uOscServer" and s["live"]]
    ex = next((s for s in m.osc_servers if _native(m, s["key"]) and s["kind"] == "OscServerEx" and s["live"]), None)
    yield _mut("OscServerEx のポートを uOscServer と同じに", "osc.port-dup", "error", m.where(ex["key"]) if ex else None,
               _sub_in_block(text, _native(m, ex["key"]), r"^  port: \d+", f"  port: {us[0]['port']}") if ex and us else None)
    # 4. スイッチャー（シーンの中の物）: PGM の Culling・入力の None・入力カメラを無効に
    sw = m.switchers[0] if m.switchers else None
    cam = m.brain_camera(sw["active"]) if sw else None
    layers = {l for c in m.chars if m.showable(c, any_slot=True) for l in c["go_layers"]}
    if cam and _native(m, cam["key"]) and layers and cam["cull"] & sum(1 << l for l in layers):
        new_bits = cam["cull"] & ~sum(1 << l for l in layers)
        yield _mut("PGM の Culling Mask からキャラのレイヤーを外す", "sw.cull-chara", sev_of(sw["live"], "warn"), m.where(cam["key"]),
                   _sub_in_block(text, _native(m, cam["key"]), r"(m_CullingMask:\r?\n    serializedVersion: \d+\r?\n    m_Bits: )\d+", r"\g<1>" + str(new_bits)))
    else:
        yield _mut("PGM の Culling Mask からキャラのレイヤーを外す", "sw.cull-chara", None, None, None)
    if sw and _native(m, sw["key"]) and sw["inputs"]:
        yield _mut("スイッチャーの入力の 1 番目を None に", "sw.input-none", sev_of(sw["live"], "error"), m.where(sw["key"]),
                   _sub_in_block(text, _native(m, sw["key"]), r"(_inputCameras:\r?\n  - )\{fileID: [1-9-]\d*\}", r"\g<1>{fileID: 0}"))
    else:
        yield _mut("スイッチャーの入力の 1 番目を None に", "sw.input-none", None, None, None)
    live_act = next((a for a in m.activators if a["live"] and sw and a["switcher"].kind == "local" and a["switcher"].key == sw["key"]), None)
    ch = next((c for c in (sw["chiefs"] if sw and sw["live"] else []) if c["go"] is not None and c["active"] and _native(m, c["go"])), None)
    if live_act and ch:
        yield _mut(f"入力カメラ {sc.go_name(ch['go'])} を無効に", "act.vcam-inactive", "warn", m.where(live_act["key"]),
                   _sub_in_block(text, ch["go"], r"^  m_IsActive: 1", "  m_IsActive: 0"))
    else:
        yield _mut("入力カメラを無効に", "act.vcam-inactive", None, None, None)
    # 5. プレハブ由来のスイッチャー: 配列の要素と大きさを m_Modifications で上書き
    psw = next((s for s in m.switchers if _instance_of(m, s["key"])), None)
    if psw:
        pi, guid, q = _instance_of(m, psw["key"])
        w, sv = m.where(psw["key"]), sev_of(psw["live"], "error")
        yield _mut("プレハブの上書きでスイッチャーの入力 [0] を None に", "sw.input-none", sv, w, _add_mod(text, pi, q, guid, "_inputCameras.Array.data[0]"))
        yield _mut("プレハブの上書きでスイッチャーの入力を 5 個に", "sw.input-few", sv, w, _add_mod(text, pi, q, guid, "_inputCameras.Array.size", "5"))
    else:
        yield _mut("プレハブの上書きでスイッチャーの入力 [0] を None に", "sw.input-none", None, None, None)
        yield _mut("プレハブの上書きでスイッチャーの入力を 5 個に", "sw.input-few", None, None, None)
    # 6. プレハブ由来の DofMidiControl: 参照とレイヤーを上書き
    dof = next((d for d in m.dofs if _instance_of(m, d["key"])), None)
    if dof and dof["switcher"]:
        pi, guid, q = _instance_of(m, dof["key"])
        yield _mut("プレハブの上書きで DofMidiControl の _switcher を None に", "dof.switcher-none", sev_of(dof["live"], "error"), m.where(dof["key"]),
                   _add_mod(text, pi, q, guid, "_switcher"))
    else:
        yield _mut("プレハブの上書きで DofMidiControl の _switcher を None に", "dof.switcher-none", None, None, None)
    vg = sc.ref_go(dof["pgm_volume"]) if dof else None
    pcam = m.brain_camera(dof["pgm_brain"]) if dof else None
    inst = _instance_of(m, vg) if vg is not None else None
    if dof and dof["live"] and pcam and pcam["vol_mask"] is not None and inst:
        pi, guid, q = inst
        cur = sc.go_fields[vg]["layer"]
        if pcam["vol_mask"] >> cur & 1:
            bad = next((i for i in range(31, -1, -1) if not pcam["vol_mask"] >> i & 1), None)
            yield _mut(f"プレハブの上書きで PGM_Volume のレイヤーを {bad} に", "dof.vol-mask", "warn", m.where(vg), _add_mod(text, pi, q, guid, "m_Layer", str(bad)))
        else:
            good = next((i for i in range(32) if pcam["vol_mask"] >> i & 1), None)
            yield _mut(f"プレハブの上書きで PGM_Volume のレイヤーを {good} に（DoF の指摘が消える）", "dof.vol-mask", "warn", m.where(vg),
                       _add_mod(text, pi, q, guid, "m_Layer", str(good)), expect="remove")
    else:
        yield _mut("プレハブの上書きで PGM_Volume のレイヤーを変える", "dof.vol-mask", None, None, None)
    # 7. MetaDmxReceiver の Use Timeline を On に（Timeline に結び付いていれば info の dmx.use-timeline-tl）
    bound = {sc.ref_go(b["value"]) for d in m.directors for b in d["binds"]} - {None}
    d = next((d for d in m.dmx if _native(m, d["key"]) and not d["use_timeline"]), None)
    if d:
        tl = sc.go_of.get(d["key"]) in bound
        yield _mut("Use Timeline を On に", "dmx.use-timeline-tl" if tl else "dmx.use-timeline", "info" if tl else sev_of(d["live"], "warn"), m.where(d["key"]),
                   _sub_in_block(text, _native(m, d["key"]), r"^  _useTimeline: 0", "  _useTimeline: 1"))
    else:
        yield _mut("Use Timeline を On に", "dmx.use-timeline", None, None, None)
    # 8. キャラの体の Renderer の GameObject を Default レイヤーに
    c = next((c for c in m.chars if c["setup"] and m.showable(c)
              and any(not r["prop"] and r["layer"] != 0 and _native(m, r["go"]) for r in c["renderers"])), None) if p.chara_layers() else None
    if c:
        r = next(r for r in c["renderers"] if not r["prop"] and r["layer"] != 0 and _native(m, r["go"]))
        yield _mut(f"{c['name']} の Renderer を Default レイヤーに", "char.layer", "warn", c["path"], _sub_in_block(text, r["go"], r"^  m_Layer: \d+", "  m_Layer: 0"))
    else:
        yield _mut("キャラの Renderer を Default レイヤーに", "char.layer", None, None, None)
    # 9. OptiTrack の Skeleton 名を別のキャラの名前に（名前は YAML の文字列として引用して書く）
    named = [x for x in m.chars if len(re.sub(r"[^0-9a-z]", "", x["name"].lower())) >= 3]
    done = False
    for c in m.chars:
        o = next((o for o in c["opti"] if _native(m, o["key"]) and o["enabled"]), None)
        other = next((x for x in named if x is not c), None)
        if o and other:
            nm = re.sub(r"\(NiloToon\)_setupped$", "", other["name"])
            nn = re.sub(r"[^0-9a-z]", "", nm.lower())
            if nn and nn not in re.sub(r"[^0-9a-z]", "", c["name"].lower()):
                yield _mut(f"{c['name']} の Skeleton 名を {nm} に", "char.skeleton-other", "warn" if m.showable(c) else "info", c["path"],
                           _sub_in_block(text, o["key"], r"^  SkeletonAssetName: .*$", "  SkeletonAssetName: " + json.dumps(nm, ensure_ascii=False)))
                done = True
                break
    if not done:
        yield _mut("Skeleton 名を別のキャラの名前に", "char.skeleton-other", None, None, None)
    # 10. LookatManager の注視先の hip を None に（_lookatTargets の中だけ。_activeTargets は実行時の一覧）
    la = next((la for la in m.lookats if _native(m, la["key"]) and any(t["hip"] for t in la["targets"])), None)
    yield _mut("注視先の hip を None に", "lookat.none", sev_of(la["live"], "warn") if la else None, m.where(la["key"]) if la else None,
               _sub_in_block(text, _native(m, la["key"]), r"_hip: \{fileID: [1-9-]\d*\}", "_hip: {fileID: 0}", start_at="_lookatTargets:") if la else None)
    # 11. Timeline の GUID を無い物に
    d = next((d for d in m.directors if _native(m, d["key"]) and d["asset"]), None)
    yield _mut("Timeline の GUID を無い物に", "tl.asset-missing", ("error" if d["live"] else "warn") if d else None, m.where(d["key"]) if d else None,
               _sub_in_block(text, _native(m, d["key"]), r"(m_PlayableAsset: \{fileID: \d+, guid: )[0-9a-f]{32}", r"\g<1>" + FAKE_GUID) if d else None)
    # 12. スクリプトの GUID を無い物に
    a = next((a for a in m.activators if _native(m, a["key"])), None)
    yield _mut("CharacterActivator のスクリプトの GUID を無い物に", "scene.missing-script", "warn", m.where(a["key"]) if a else None,
               _sub_in_block(text, _native(m, a["key"]), r"(m_Script: \{fileID: 11500000, guid: )[0-9a-f]{32}", r"\g<1>" + FAKE_GUID) if a else None)
    # 13. 握りのプリセットを持つマイクの枠の、持つ手を逆に
    hit = None
    for mc in m.mics:
        fid = _native(m, mc["key"])
        if fid:
            for ti, t in enumerate(mc["targets"]):
                hand = m.preset_hand(t["grip"])
                if hand in ("L", "R") and hand == t["hand"]:
                    hit = (mc, ti, fid)
                    break
        if hit:
            break
    if hit:
        mc, ti, fid = hit
        yield _mut(f"マイクの枠 [{ti}] の持つ手を逆に", "mic.grip-hand", sev_of(mc["live"], "warn"), f"[{ti}]",
                   _sub_in_block(text, fid, r"^    _handOption: (\d)", "    _handOption: " + ("0" if mc["targets"][ti]["hand"] == "L" else "1"), nth=ti))
    else:
        yield _mut("マイクの持つ手を逆に", "mic.grip-hand", None, None, None)
    # 14. 開始時に見える 2 体の characterID を同じに
    vis = [c for c in m.chars if m.starts_visible(c) and c["lipsync"] and _native(m, c["lipsync"][0]["key"])]
    pair = next(((x, y) for i, x in enumerate(vis) for y in vis[i + 1:]
                 if x["lipsync"][0]["id"] != y["lipsync"][0]["id"] and not m.exclusive(x, y)), None)
    if pair:
        x, y = pair
        yield _mut(f"{y['name']} の characterID を {x['name']} と同じに", "char.id-dup", "warn", y["name"],
                   _sub_in_block(text, y["lipsync"][0]["key"], r"^  characterID: \d+", f"  characterID: {x['lipsync'][0]['id']}"))
    else:
        yield _mut("開始時に見える 2 体の characterID を同じに", "char.id-dup", None, None, None)


def findings(path, project):
    m = Model(open_scene(path, quiet=True, project=project))
    f = run_checks(m)
    return m, {(sev, cid, it) for (sev, cid, msg), items in f.groups.items() for it in (items or [""])}


def lfs_test(out_dir, project):
    """LFS のポインタのシーンを読ませると、黙って空の結果にせず止まるか。"""
    p = os.path.join(out_dir, "lfs_pointer.unity")
    with open(p, "wb") as fh:
        fh.write(LFS_HEAD + b"\noid sha256:0\nsize 1\n")
    try:
        findings(p, project)
        ok = False
    except SystemExit as e:
        ok = "LFS" in str(e)
    os.remove(p)
    return ok


def main():
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", nargs="+")
    ap.add_argument("--project")
    a = ap.parse_args()
    out_dir = os.path.join(tempfile.gettempdir(), "vortex-scene-audit", "selftest")
    os.makedirs(out_dir, exist_ok=True)
    total = ok = na = 0
    project = None
    for scene in a.scene:
        project = a.project or Project.find(scene).root
        m, base = findings(scene, project)
        if m.sc.guids.label(FAKE_GUID) is not None:
            raise SystemExit(f"試験用の GUID {FAKE_GUID} がプロジェクトにある: {m.sc.guids.label(FAKE_GUID)}")
        with open(scene, encoding="utf-8", newline="") as fh:
            text = fh.read()
        print(f"== {scene}（基準の指摘 {len(base)} 箇所）")
        tmp = os.path.join(out_dir, os.path.basename(scene))
        for mu in mutations(m, text):
            if mu["text"] is None or mu["text"] == text:
                na += 1
                print(f"  対象なし  {mu['name']}（{mu['rule']}）")
                continue
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(mu["text"])
            _, got = findings(tmp, project)
            added, removed = got - base, base - got
            pool = added if mu["expect"] == "add" else removed
            hit = [it for sev, cid, it in pool if cid == mu["rule"] and sev == mu["sev"] and mu["anchor"] in it]
            near = [f"{sev}:{it}" for sev, cid, it in pool if cid == mu["rule"] and not (sev == mu["sev"] and mu["anchor"] in it)]
            side = sorted({f"+{cid}" for sev, cid, it in added if cid != mu["rule"]} | {f"-{cid}" for sev, cid, it in removed if cid != mu["rule"]})
            total += 1
            ok += bool(hit)
            verb = "増えた" if mu["expect"] == "add" else "消えた"
            print(f"  {'検出' if hit else '見逃し'}  {mu['name']} → {mu['rule']}（{mu['sev']}・{verb}）" + (f"  巻き添え: {', '.join(side)}" if side else ""))
            for it in hit[:1]:
                print(f"         {it}")
            if not hit and near:
                print(f"         期待と違う形で出た: {near[:2]}")
        if os.path.exists(tmp):
            os.remove(tmp)
    lfs_ok = lfs_test(out_dir, project)
    print(f"\n検出 {ok} / {total}（対象なし {na}）  LFS のポインタで止まる: {'OK' if lfs_ok else 'NG'}")
    return 0 if ok == total and lfs_ok else 1


if __name__ == "__main__":
    sys.exit(main())
