"""vortex のライブシーンの点検の規則。Model（vortex_model）から指摘（error / warn / info）を作る。

重さの決め方:
  error  そのまま Play すると例外・受信の失敗・参照切れになる
  warn   動くが、ライブで効かない・写らない・取り違えるおそれが高い
  info   今は害が無いが、出し方を変えると効いてくる（無効な System・無効なキャラ・Timeline 用の設定など）
無効の GameObject / コンポーネントで見つけたものは、重さを info に下げて「※無効」を付ける（仕込み用のシーンは System ごと無効のことがある）。
例外: 参照先のアセットが無い物（Missing Script / Missing Prefab / Timeline の GUID 切れ / LFS のポインタ）は、無効でも warn 以上にする
（データが壊れていて、有効にした途端に効く）。
「出うるキャラ」= シーンで有効か、Activation Track が無効なルートを有効にするか、有効な CharacterActivator の枠で出せるキャラ
（CharacterActivator はルートの有効を変えないので、ルートが無効なら、無効なのが Lookat Bone_hip そのものだけのときに限る）。
「開始時に見えるキャラ」は Model.starts_visible（各枠の予備 [0]・Timeline が受け持つ枠は全員消える・hip が空の予備はシーンのまま）。
どの規則も、根拠にしたソースの振る舞いを msg に書く（Unity を開かずに直す所が分かるように）。
"""
import re

from vortex_model import FACIAL_DEVICE, OPTITRACK_DEFAULT_SKELETON, OSC_FACIAL_DEVICES

SEV_ORDER = {"error": 0, "warn": 1, "info": 2}
OFF = "  ※無効"
NOT_SETUP = "  ※仕込み前（NiloToon・表情・口パクが無い。仮置きのモデル）"


class Findings:
    def __init__(self):
        self.groups = {}  # (sev, id, msg) -> [item]

    def add(self, sev, cid, msg, item=None):
        lst = self.groups.setdefault((sev, cid, msg), [])
        if item is not None and item not in lst:
            lst.append(item)

    def sorted(self):
        return sorted(self.groups.items(), key=lambda kv: (SEV_ORDER[kv[0][0]], kv[0][1], kv[0][2]))

    def count(self, sev):
        """(指摘の数, 物の数)。"""
        gs = [items for (s, _, _), items in self.groups.items() if s == sev]
        return len(gs), sum(max(1, len(i)) for i in gs)


def _sev(live, sev):
    return sev if live else "info"


def _off(live):
    return "" if live else OFF


def _cname(c):
    return c["path"]


def _norm(s):
    s = re.sub(r"\(NiloToon\)_setupped$", "", s)
    return re.sub(r"[^0-9a-z]", "", s.lower())


def run(m):
    f = Findings()
    for fn in (_check_scene, _check_osc, _check_activator, _check_lookat, _check_switcher, _check_volume, _check_light,
               _check_chars, _check_ids, _check_mic, _check_dmx, _check_opti, _check_water, _check_director, _check_ext):
        fn(m, f)
    return f


# ---------------------------------------------------------------------------------------------- シーン全体


def _check_scene(m, f):
    counts = {}
    for k, lab in m.missing_scripts:
        key = (m.where(k), lab)
        counts[key] = counts.get(key, 0) + 1
    for (where, lab), n in sorted(counts.items()):
        f.add("warn", "scene.missing-script", "スクリプトが見つからないコンポーネント（Missing Script。GUID がプロジェクトに無い / m_Script が空）",
              f"{where}  [{lab}]" + (f" x{n}" if n > 1 else ""))
    for mp in m.sc.missing_prefabs:
        if mp.get("nested"):
            f.add("warn", "scene.missing-prefab-nested", "プレハブの中に、元のプレハブが見つからない入れ子のインスタンスがある（その部品が出ない。元のプレハブを直す）",
                  f"{mp['name']}  guid {mp['guid']}")
            continue
        parent = m.sc.describe(mp["parent"]) if mp["parent"] else "(ルート)"
        f.add("error", "scene.missing-prefab", "元のプレハブが見つからない PrefabInstance（中身が展開されない。Unity では Missing Prefab。プレハブを消した・GUID が変わった）",
              f"{mp['name'] or '(名前の上書き無し)'}  親 {parent}  PrefabInstance {mp['pi']}  guid {mp['guid']}")
    seen = set()
    for lp in m.lfs:
        key = (lp.get("label"), lp.get("name"))
        if key in seen:
            continue
        seen.add(key)
        f.add("error", "scene.lfs-pointer",
              "git LFS のポインタのまま（実体を取り出していない）で中身を読めない物がある（Unity でも取り込めない。その分の点検は飛ぶ）。git lfs pull で取り出してから点検し直す",
              f"{lp.get('name') or '(名前の上書き無し)'}  {lp.get('label')}")
    if not m.system_roots:
        f.add("info", "scene.no-system", "名前が System で始まるルートが無い（System の塊を置いていないシーン。本番のステージだけのシーンなど）")


# ---------------------------------------------------------------------------------------------- OSC


def _check_osc(m, f):
    sc = m.sc
    by_port = {}
    for s in m.osc_servers:
        by_port.setdefault(s["port"], []).append(s)
    for port, ss in sorted(by_port.items()):
        live = [s for s in ss if s["live"]]
        if len(live) >= 2:
            msg = (f"OSC の受信ポート {port} を開くサーバーが {len(live)} 個ある（uOscServer も OscServerEx も uOSC の Udp で ReuseAddress を付けずに bind するので、"
                   "2 つ目以降は bind に失敗して LogError を出し、何も受けない。どちらが先に開くかは起動順で決まる）")
            for s in live:
                f.add("error", "osc.port-dup", msg, f"{m.where(s['key'])}  [{s['kind']}, リスナー {len(s['listeners'])}]")
        elif len(ss) >= 2:
            f.add("info", "osc.port-dup-inactive",
                  f"OSC の受信ポート {port} のサーバーが {len(ss)} 個（今開くのは {len(live)} 個。無効な方も有効にすると bind が衝突する）",
                  ", ".join(f"{m.where(s['key'])}{'' if s['live'] else ' (無効)'}" for s in ss))
    for s in m.osc_servers:
        seen = {}
        where = m.where(s["key"])
        for c in s["listeners"]:
            t = c["target"]
            if t.kind != "local" or sc.objs.get(t.key) is None:
                f.add(_sev(s["live"], "warn"), "osc.listener-broken",
                      "uOscServer の onDataReceived に、参照が切れた（None の）リスナーがある（消したキャラ・部品の配線の残り。置き換えた先へ付け替えたかを確かめる）",
                      f"{where} → {c['type'] or '?'}.{c['method'] or '?'}{_off(s['live'])}")
                continue
            if c["state"] == "0":
                f.add(_sev(s["live"], "warn"), "osc.listener-off", "uOscServer のリスナーが Off（m_CallState 0）で呼ばれない",
                      f"{where} → {m.ref_label(t)}.{c['method']}{_off(s['live'])}")
            key = (t.key, c["method"])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 2:
                f.add(_sev(s["live"], "warn"), "osc.listener-dup", "同じリスナーが同じサーバーに 2 回以上登録されている（1 通の OSC で 2 回動く）",
                      f"{where} → {m.ref_label(t)}.{c['method']}{_off(s['live'])}")
    wired_targets = {k for (k, _meth) in m.osc_wired(live_only=True)}
    wired_any = {k for (k, _meth) in m.osc_wired(live_only=False)}
    consumers = [(a["key"], "CharacterActivator", a["is_osc"], a["live"]) for a in m.activators]
    consumers += [(mc["key"], "MicController", mc["is_osc"], mc["live"]) for mc in m.mics]
    consumers += [(c["key"], c["kind"], c["is_osc"], c["live"]) for c in m.switch_controllers]
    for k, lab, is_osc, live in consumers:
        if is_osc and k not in wired_targets:
            if k in wired_any:
                f.add(_sev(live, "warn"), "osc.server-off",
                      "_isOsc が On で配線もあるが、配線先の uOscServer が開かない（無効か autoStart が Off）ので OSC が届かない",
                      f"{m.where(k)}  [{lab}]{_off(live)}")
            else:
                f.add(_sev(live, "warn"), "osc.isosc-unwired",
                      "_isOsc が On なのに、どの uOscServer のリスナーにも入っていない（OSC が届かない。リスナーはシーンの Inspector で足す）",
                      f"{m.where(k)}  [{lab}]{_off(live)}")
        elif not is_osc and k in wired_any:
            f.add("info", "osc.wired-not-isosc", "uOscServer に配線されているが _isOsc が Off（受けた OSC を捨てる）", f"{m.where(k)}  [{lab}]{_off(live)}")
    if not any(s["kind"] == "uOscServer" for s in m.osc_servers) and any(is_osc and live for _, _, is_osc, live in consumers):
        f.add("warn", "osc.no-server", "OSC を受ける設定のコンポーネントがあるのに uOscServer が無い")


# ---------------------------------------------------------------------------------------------- CharacterActivator


def _check_activator(m, f):
    sc = m.sc
    seen_targets = {}
    for a in m.activators:
        live = a["live"]
        where = m.where(a["key"])
        if not a["lookat"]:
            f.add(_sev(live, "warn"), "act.ref-none", "CharacterActivator の参照が空（_lookatManager が空だと、出し入れの後に注視先を数え直さない）",
                  f"{where}  _lookatManager{_off(live)}")
        if not a["switcher"]:
            f.add(_sev(live, "warn"), "act.ref-none", "CharacterActivator の参照が空（_cameraSwitcher が空だと、出し入れの後に vcam の注視先を付け直さない）",
                  f"{where}  _cameraSwitcher{_off(live)}")
        if a["switcher"].kind == "local" and live:
            sw_go = sc.go_of.get(a["switcher"].key)
            sw = next((s for s in m.switchers if s["key"] == a["switcher"].key), None)
            if sw_go is not None and not sc.active_in_hierarchy(sw_go):
                f.add("warn", "act.switcher-inactive",
                      "CharacterActivator の _cameraSwitcher が無効の GameObject にある（InitializeLookat が Awake 前の vcam の Initialize を呼び、"
                      "開始時とキャラの出し入れで VirtualCameraGenerator.ApplyValues が NullReferenceException。_vcamOffset は Awake で作る）",
                      f"{where} → {m.ref_label(a['switcher'])}")
            elif sw is not None:
                # スイッチャーは有効でも、入力カメラ（VirtualCameraChief）や vcam が無効・None なら同じ NRE
                bad = []
                for ch in sw["chiefs"]:
                    if ch["go"] is None:
                        bad.append(f"[{ch['index']}] None")
                    elif not ch["active"]:
                        bad.append(f"[{ch['index']}] {sc.go_name(ch['go'])}（無効）")
                    else:
                        nv = sum(1 for v in ch["vcams"] if v["go"] is None)
                        off = sum(1 for v in ch["vcams"] if v["go"] is not None and not v["active"])
                        if nv or off:
                            bad.append(f"[{ch['index']}] {sc.go_name(ch['go'])}（vcam None {nv}・無効 {off}）")
                if bad:
                    f.add("warn", "act.vcam-inactive",
                          "スイッチャーの入力カメラか vcam（_vCams）に、無効・None の物がある（CharacterActivator.InitializeLookat が全部の Initialize を呼ぶので、"
                          "開始時とキャラの出し入れで NullReferenceException）",
                          f"{where}: {', '.join(bad[:6])}{' ...' if len(bad) > 6 else ''}")
        for si, reserves in enumerate(a["slots"]):
            if not reserves:
                f.add(_sev(live, "warn"), "act.slot-empty", "CharacterActivator の枠に予備キャラが 1 体も無い（/ModelActivate で ChangeCharacter が範囲外を引く）",
                      f"{where}  枠 [{si}]{_off(live)}")
            for ri, r in enumerate(reserves):
                slot = f"枠 [{si}]" + (f" 予備 [{ri}]" if len(reserves) > 1 else "")
                tg = sc.ref_go(r["target"])
                if tg is None:
                    f.add(_sev(live, "warn"), "act.target-none", "CharacterActivator の予備キャラ（_targetCharacter）が None の枠", f"{where}  {slot}{_off(live)}")
                    continue
                tname = sc.go_name(tg)
                hg = sc.ref_go(r["hip"])
                if hg is None:
                    f.add(_sev(live, "warn"), "act.hip-none",
                          "Lookat Bone_hip が空の予備キャラ（ControlActive / SetActiveImmediate が何もせず戻り、On/Off が効かない）",
                          f"{where}  {slot} {tname}{_off(live)}")
                    continue
                c = m.char_of.get(tg)
                if c is not None and hg not in c["gos"]:
                    f.add(_sev(live, "warn"), "act.hip-outside", "Lookat Bone_hip が予備キャラの中に無い（別の物を出し入れしている。複製のときの付け替え漏れ）",
                          f"{where}  {slot} {tname}: hip = {sc.go_path(hg)}{_off(live)}")
                for eff, nm in ((r["in_effect"], "_in_effect"), (r["out_effect"], "_out_effect")):
                    if not eff:
                        f.add(_sev(live, "warn"), "act.effect-none",
                              "登場・退場のエフェクトが空の予備キャラ（開始時と切り替えのたびに PlayEffect が \"Activate Effect is Null\" を Error で出す）",
                              f"{where}  {slot} {tname}  {nm}{_off(live)}")
                seen_targets.setdefault(tg, []).append((f"{where} {slot}", live))
    for tg, places in seen_targets.items():
        if len(places) >= 2:
            live = any(lv for _, lv in places)
            f.add(_sev(live, "warn"), "act.target-dup", "同じキャラが CharacterActivator の 2 か所以上に入っている（片方の出し入れがもう片方の状態とずれる）",
                  f"{sc.go_name(tg)}: " + " / ".join(p for p, _ in places) + _off(live))
    if any(a["live"] for a in m.activators):
        for c in m.chars:
            if c["slots"]:
                continue
            if c["bound"]:
                f.add("info", "act.unregistered-timeline", "CharacterActivator の枠に入っていないキャラ（Timeline に結び付いているので Timeline が出す想定）", _cname(c))
            elif c["active"]:
                f.add("warn" if c["setup"] else "info", "act.unregistered",
                      "CharacterActivator のどの枠にも入っていない、有効なキャラ（出しっぱなしで、OSC / MIDI で出し入れできない）",
                      _cname(c) + ("" if c["setup"] else NOT_SETUP))
            else:
                f.add("info", "act.unregistered-off", "CharacterActivator の枠に入っていない、無効なキャラ（置いてあるだけ。出すなら枠に足す）", _cname(c))


# ---------------------------------------------------------------------------------------------- LookatManager


def _check_lookat(m, f):
    sc = m.sc
    live = [la for la in m.lookats if la["live"]]
    if len(live) >= 2:
        f.add("error", "lookat.dup", "有効な LookatManager が 2 つ以上（シングルトンで、2 つ目は Awake で Destroy される）",
              ", ".join(m.where(la["key"]) for la in live))
    if any(s["live"] for s in m.switchers) and not live:
        f.add("warn", "lookat.inactive",
              "スイッチャーが有効なのに、有効な LookatManager が無い（VirtualCameraGenerator は FindObjectOfType で探すので、無効だと vcam の注視先が付かない）",
              ", ".join(m.where(la["key"]) + " (無効)" for la in m.lookats) or "LookatManager がシーンに無い")
    for la in m.lookats:
        where = m.where(la["key"])
        for ti, t in enumerate(la["targets"]):
            if not t["hip"] or not t["head"]:
                miss = " と ".join(n for n, r in (("hip", t["hip"]), ("head", t["head"])) if not r)
                f.add(_sev(la["live"], "warn"), "lookat.none",
                      "LookatManager の注視先で hip / head が空（ResetLookAt が飛ばし、どのカメラもこの注視先を向かない）",
                      f"{where}  [{ti}] {t['name']}: {miss} が None{_off(la['live'])}")
    if not live:
        return
    for c in m.chars:
        if not m.showable(c):
            continue
        if not c["lookat"]:
            f.add("warn", "lookat.unregistered", "出うるキャラが LookatManager に登録されていない（カメラの注視先にならない）", _cname(c))
            continue
        # CharacterActivator が On/Off する hip の枝に、LookatManager の hip / head が入っているか
        for (ai, si, ri) in c["slots"]:
            r = m.activators[ai]["slots"][si][ri]
            hg = sc.ref_go(r["hip"])
            if hg is None:
                continue
            ok = False
            for (li, ti) in c["lookat"]:
                t = m.lookats[li]["targets"][ti]
                th, td = sc.ref_go(t["hip"]), sc.ref_go(t["head"])
                if th is not None and td is not None and hg in set(sc.ancestors(th)) and hg in set(sc.ancestors(td)):
                    ok = True
            if not ok:
                f.add("warn", "lookat.hip-mismatch",
                      "CharacterActivator が On/Off する Lookat Bone_hip の下に、LookatManager の hip / head が無い（キャラを消してもカメラの注視先から外れない）",
                      f"{_cname(c)}: Bone_hip = {sc.go_path(hg)}")


# ---------------------------------------------------------------------------------------------- スイッチャー


def _check_switcher(m, f):
    sc = m.sc
    for s in m.switchers:
        live = s["live"]
        where = m.where(s["key"])
        nones = [i for i, r in enumerate(s["inputs"]) if sc.ref_go(r) is None]
        if nones:
            f.add(_sev(live, "error"), "sw.input-none", "スイッチャーの _inputCameras に None がある（Start の焦点距離の登録で NullReferenceException）",
                  f"{where}  {nones}{_off(live)}")
        if len(s["inputs"]) < 9:
            f.add(_sev(live, "error"), "sw.input-few", "スイッチャーの _inputCameras が 9 個未満（Start が _inputCameras[8] をハンディの位置に使う）",
                  f"{where}  {len(s['inputs'])} 個{_off(live)}")
        names = s["input_names"]
        dups = sorted({n for n in names if names.count(n) >= 2 and n != "None"})
        if dups:
            f.add("info", "sw.input-dup", "スイッチャーの _inputCameras に同じカメラが 2 回以上（カメラ記録は番号と名前で当たるので、記録と並びを照合する）",
                  f"{where}  {dups}")
        for nm, r in (("_activeCamera", s["active"]), ("_reserveCamera", s["reserve"])):
            if not r:
                f.add(_sev(live, "error"), "sw.brain-none", "スイッチャーの Brain（PGM / PRV）が空", f"{where}  {nm}{_off(live)}")
        if not s["preview"]:
            f.add(_sev(live, "error"), "sw.preview-none", "スイッチャーの _previewImage が空（Start で NullReferenceException）", where + _off(live))
        for nm, r in (("_renderTexA", s["rt_a"]), ("_renderTexB", s["rt_b"])):
            if not r:
                f.add(_sev(live, "warn"), "sw.rt-none",
                      "スイッチャーの _renderTexA / _renderTexB が未割り当て（VirtualCameraSwitcher はこの 2 つを操作画面のプレビュー _previewImage に映すだけなので、プレビューが出ない）",
                      f"{where}  {nm}{_off(live)}")
        pgm, prv = m.brain_camera(s["active"]), m.brain_camera(s["reserve"])
        if pgm and prv and s["rt_a"] and s["rt_b"]:
            want = {s["rt_a"].guid, s["rt_b"].guid}
            have = {pgm["rt"].guid if pgm["rt"] else None, prv["rt"].guid if prv["rt"] else None}
            if want != have:
                f.add(_sev(live, "warn"), "sw.rt-mismatch", "PGM / PRV のカメラの出力先 RT が、スイッチャーの _renderTexA / _renderTexB と合わない",
                      f"{where}  PGM→{m.asset_label(pgm['rt'])} PRV→{m.asset_label(prv['rt'])} / A={m.asset_label(s['rt_a'])} B={m.asset_label(s['rt_b'])}{_off(live)}")
        for role, cam in (("PGM", pgm), ("PRV", prv)):
            if cam is None:
                continue
            who = {}
            for c in m.chars:
                if not m.showable(c, any_slot=not live):
                    continue
                miss = sorted(l for l in c["go_layers"] if not cam["cull"] >> l & 1)
                if miss:
                    who[c["name"]] = miss
            if who:
                layers = sorted({l for ls in who.values() for l in ls})
                names = sorted(who)
                f.add(_sev(live, "warn"), "sw.cull-chara",
                      "番組カメラの Culling Mask に、出うるキャラの Renderer のレイヤーが無い（そのキャラが番組に写らない）",
                      f"{role} {m.where(cam['key'])}: 無いレイヤー {', '.join(m.p.layer_name(l) for l in layers)}（{len(names)} 体: "
                      f"{', '.join(names[:6])}{' ...' if len(names) > 6 else ''}）{_off(live)}")
    for c in m.switch_controllers:
        if not c["switcher"]:
            f.add(_sev(c["live"], "warn"), "sw.ctrl-ref-none", "スイッチャーを操作するコンポーネントの _cameraSwitcher が空",
                  f"{m.where(c['key'])}  [{c['kind']}]{_off(c['live'])}")
    # RT_Output（_outputRenderTexture）に書くのは旧 CameraSwitcher の Blit だけ。VirtualCameraSwitcher は Blit がコメントアウト
    outs = {s["output"].guid for s in m.switchers if s["output"]}
    writers = any(m.live(k) for k in m.comps("CameraSwitcher"))
    cam_rts = {c["rt"].guid for c in m.cameras if c["live"] and c["rt"]}
    for cv in m.canvases:
        for r in cv["raws"]:
            g = r["texture"].guid if r["texture"] else None
            if g in outs and not r["material"] and not writers and g not in cam_rts and cv["live"] and r["live"]:
                f.add("warn", "sw.output-unwritten",
                      "RawImage が RT_Output（スイッチャーの _outputRenderTexture）をそのまま映しているが、誰も書いていない"
                      "（VirtualCameraSwitcher は Blit がコメントアウト。PGM / PRV を混ぜるのは RawImage のマテリアル SwitchTexture.mat）",
                      f"{m.where(r['key'])}  Display {cv['display'] + 1}  {m.asset_label(r['texture'])}")


# ---------------------------------------------------------------------------------------------- Volume / DoF


def _check_volume(m, f):
    sc = m.sc
    vol_by_go = {sc.go_of.get(v["key"]): v for v in m.volumes}
    dof_vols = set()
    for d in m.dofs:
        where = m.where(d["key"])
        live = d["live"]
        if not d["switcher"]:
            f.add(_sev(live, "error"), "dof.switcher-none", "DofMidiControl の _switcher が空（LateUpdate が毎フレーム NullReferenceException）",
                  where + _off(live))
        for nm, fld in (("pgm_volume", "_pgmVolume"), ("prv_volume", "_prvVolume")):
            if not d[nm]:
                f.add(_sev(live, "warn"), "dof.volume-none",
                      "DofMidiControl の Volume が空（Start は 2 つとも揃ったときだけ DoF を取るので、片方が空でも PGM・PRV の両方とも被写界深度を動かさない）",
                      f"{where}  {fld}{_off(live)}")
        for nm, fld in (("pgm_brain", "_pgmBrain"), ("prv_brain", "_prvBrain")):
            if not d[nm]:
                f.add(_sev(live, "warn"), "dof.brain-none", "DofMidiControl の Brain が空（その側のピントの距離が 0 になる。CalcFocusDistance が 0 を返す）",
                      f"{where}  {fld}{_off(live)}")
        unseen = []
        for role, bref, vref in (("PGM", d["pgm_brain"], d["pgm_volume"]), ("PRV", d["prv_brain"], d["prv_volume"])):
            cam = m.brain_camera(bref)
            v = vol_by_go.get(sc.ref_go(vref))
            if v is not None:
                dof_vols.add(v["key"])
            if cam is None or v is None or cam["vol_mask"] is None:
                continue
            if not cam["vol_mask"] >> v["layer"] & 1:
                unseen.append(f"{role}: {m.where(v['key'])} のレイヤー {m.p.layer_name(v['layer'])} / {m.where(cam['key'])} の Volume Mask {m.p.mask_names(cam['vol_mask'])}")
        if live:
            for u in unseen:
                f.add("warn", "dof.vol-mask",
                      "番組の被写界深度の Volume のレイヤーが、そのカメラの Volume Mask に無い（DofMidiControl が値を書いても、そのカメラに DoF が掛からない）", u)
        else:
            f.add("info", "dof.off", "DofMidiControl が無効（番組の被写界深度を動かさない）"
                  + ("。DoF の Volume のレイヤーもカメラの Volume Mask に無いので、DoF は掛からない" if unseen else ""),
                  where + (f"  {' / '.join(unseen)}" if unseen else ""))
    masks = [c["vol_mask"] for c in m.cameras if c["live"] and c["vol_mask"] is not None]
    for v in m.volumes:
        if not v["live"] or v["key"] in dof_vols or not v["is_global"]:
            continue
        if masks and not any(mk >> v["layer"] & 1 for mk in masks):
            f.add("info", "vol.unseen", "有効なカメラのどの Volume Mask にも入っていないレイヤーの Global Volume（どのカメラにも効かない）",
                  f"{m.where(v['key'])}  レイヤー {m.p.layer_name(v['layer'])}  {m.asset_label(v['profile'])}")


# ---------------------------------------------------------------------------------------------- ライト


def _check_light(m, f):
    crl = m.p.chara_rendering_layers()
    if not crl:
        return
    cbits = sum(1 << i for i in crl)
    showable = [c for c in m.chars if m.showable(c) and c["rls"]]
    only_chara = [c for c in showable if all((rl & cbits) and not (rl & ~cbits) for rl in c["rls"])]
    if only_chara and not any(l["live"] and l["rl"] is not None and l["rl"] & cbits for l in m.lights):
        f.add("warn", "light.chara-none",
              "キャラの Renderer は Rendering Layer がキャラ用だけなのに、キャラ用の Rendering Layer を含む有効なライトが無い（キャラが真っ黒になる）",
              ", ".join(c["name"] for c in only_chara[:8]) + (" ..." if len(only_chara) > 8 else ""))


# ---------------------------------------------------------------------------------------------- キャラ


def _check_chars(m, f):
    sc = m.sc
    clayers = set(m.p.chara_layers())
    crl = m.p.chara_rendering_layers()
    cbits = sum(1 << i for i in crl)
    live_clients = {c["key"] for c in m.opti_clients if c["live"]}
    live_receivers = [k for k in m.gamepad_receivers if m.live(k)]
    # キャラ用のレイヤー: プロジェクトの chara* と、仕込み済みのキャラが体に使っている Default 以外のレイヤー
    # （vortex_urp はキャラごとにレイヤーを分けている。Default だけを「設定していない」とみなす）
    conv = set(clayers)
    for c in m.chars:
        if c["setup"]:
            conv |= {r["layer"] for r in c["renderers"] if not r["prop"] and r["layer"] != 0}
    conv_names = ", ".join(m.p.layer_name(l) for l in sorted(conv))
    for c in m.chars:
        show = m.showable(c)
        sev = "warn" if show and c["setup"] else "info"
        note = "" if show else "  ※Play で出ないキャラ（ルートが無効で、枠でも Activation Track でも有効にならない）"
        if not c["setup"]:
            note += NOT_SETUP
        body = [r for r in c["renderers"] if not r["prop"]]
        props = [r for r in c["renderers"] if r["prop"]]
        if conv:
            bad = [r for r in body if r["layer"] == 0]
            if bad:
                f.add(sev, "char.layer",
                      f"キャラの Renderer の GameObject が Default レイヤーのまま（ほかのキャラ・プロジェクトのキャラ用は {conv_names}。"
                      "CharacterSetup のウィンドウはレイヤーを設定しないので取り込みのまま残る。VortexCharTool.SetupCharacterEx はレイヤーを渡せる。"
                      "キャラのレイヤーで分けたカメラの Culling Mask・影・ライトの対象から外れる）",
                      f"{_cname(c)}: {len(bad)}/{len(body)} 個{note}")
        if cbits:
            bad = [r for r in body if not r["rl"] & cbits]
            if bad:
                f.add(sev, "char.rl", "キャラの Renderer の Rendering Layer にキャラ用（" + ", ".join(m.p.rendering_layers[i] for i in crl)
                      + "）が無い（キャラ用ライトが当たらない）",
                      f"{_cname(c)}: {len(bad)}/{len(body)} 個（{', '.join(sorted({sc.go_name(r['go']) for r in bad})[:5])}）{note}")
            badp = [r for r in props if not r["rl"] & cbits]
            if badp:
                f.add("info", "char.rl-prop", "キャラの小物（マイクなど）の Rendering Layer にキャラ用が無い（小物はステージのライトで照らす作りもある）",
                      f"{_cname(c)}: {', '.join(sorted({sc.go_name(r['go']) for r in badp})[:5])}")
        for e in c["lipsync"]:
            if e["enabled"] and not e["proxy"]:
                f.add(sev, "char.lipsync-proxy", "OscRx_LipSync の blendShapeProxy が空（Start で警告し、口が動かない）", _cname(c) + note)
        osc_comps = [("OscRx_LipSync", e) for e in c["lipsync"] if e["enabled"]]
        osc_comps += [(f"FacialManager({FACIAL_DEVICE.get(e['device'], e['device'])})", e) for e in c["facial"]
                      if e["enabled"] and e["device"] in OSC_FACIAL_DEVICES]
        unwired = [n for n, e in osc_comps if not e["wired_any"]]
        if unwired:
            f.add(sev, "osc.unwired",
                  "表情・口パクを OSC で受けるコンポーネントがあるのに、uOscServer のリスナーに入っていない（vortex-character-setup の OSC 配線の漏れ）",
                  f"{_cname(c)}: {', '.join(unwired)}{note}")
        server_off = [n for n, e in osc_comps if e["wired_any"] and not e["wired"]]
        if server_off:
            f.add(sev, "osc.unwired-server-off",
                  "表情・口パクの配線はあるが、配線先の uOscServer が開かない（無効か autoStart が Off）ので OSC が届かない",
                  f"{_cname(c)}: {', '.join(server_off)}{note}")
        offs = [n for n, e in osc_comps if e["wired"] and all(st == "0" for st in e["wired"])]
        if offs:
            f.add(sev, "osc.unwired-callstate", "キャラの OSC のリスナーがすべて Off（m_CallState 0）", f"{_cname(c)}: {', '.join(offs)}{note}")
        for v in c["vfc"]:
            if not v["enabled"]:
                continue
            if not v["label"]:
                f.add(sev, "char.vfc-label", "vortex_FacialController の _controllerLabel が空（どのコントローラーの入力も読まない）", _cname(c) + note)
            if show and not live_receivers:
                f.add("warn", "char.vfc-no-receiver", "vortex_FacialController があるのに、有効な vortex_GamepadOscReceiver がシーンに無い（パッドの入力が届かない）", _cname(c))
        for o in c["opti"]:
            if not o["enabled"]:
                continue
            if not o["client"]:
                if not live_clients:
                    f.add(sev, "char.opti-client",
                          "OptitrackSkeletonAnimator の StreamingClient が空で、有効な OptitrackStreamingClient もシーンに無い（Initialize が Error を出して自分を無効にする）",
                          f"{_cname(c)}  @{o['rel']}{note}")
            elif o["client"].kind == "local" and o["client"].key not in live_clients:
                f.add(sev, "char.opti-client-off", "OptitrackSkeletonAnimator の StreamingClient が無効の OptitrackStreamingClient を指している（骨格を受けない）",
                      f"{_cname(c)}  @{o['rel']} → {m.ref_label(o['client'])}{note}")
            if not o["avatar"]:
                f.add(sev, "char.opti-avatar", "OptitrackSkeletonAnimator の DestinationAvatar が空（HumanPoseHandler を作れない）", f"{_cname(c)}  @{o['rel']}{note}")
        if not (c["lipsync"] or c["facial"] or c["vfc"] or c["ulipsync"]):
            f.add("info", "char.no-facial", "表情・口パクの仕組みが付いていないキャラ", _cname(c))
    # OptiTrack の Skeleton 名が別のキャラの名前に見える（複製のときの付け替え漏れ）
    names = [(c, _norm(c["name"])) for c in m.chars]
    for c in m.chars:
        own = _norm(c["name"])
        for o in c["opti"]:
            sk = _norm(o["skeleton"])
            if len(sk) < 3 or sk == _norm(OPTITRACK_DEFAULT_SKELETON) or sk in own:
                continue
            others = [oc["name"] for oc, n in names if oc is not c and sk in n]
            if others:
                f.add("warn" if m.showable(c) else "info", "char.skeleton-other",
                      "OptiTrack の Skeleton 名が、自分ではなく別のキャラの名前を指している（複製のときの付け替え漏れの疑い。受信で別の演者の骨格を拾う）",
                      f"{_cname(c)}: SkeletonAssetName = {o['skeleton']}（{', '.join(others[:3])} の名前）")


def _check_ids(m, f):
    """同時に出うるキャラどうしで、OSC の番号・OptiTrack の Skeleton 名・パッドのラベルが重なっていないか。"""
    keyers = [
        ("char.id-dup", "OscRx_LipSync の characterID",
         lambda c: [str(e["id"]) for e in c["lipsync"] if e["enabled"]]),
        ("char.facial-id-dup", "FacialManager の oscFacialID（OSC の機器）",
         lambda c: [str(e["id"]) for e in c["facial"] if e["enabled"] and e["device"] in OSC_FACIAL_DEVICES]),
        ("char.vfc-label-dup", "vortex_FacialController の _controllerLabel",
         lambda c: [e["label"] for e in c["vfc"] if e["enabled"] and e["label"]]),
        ("char.skeleton-dup", "OptiTrack の SkeletonAssetName",
         lambda c: [o["skeleton"] for o in c["opti"] if o["enabled"]]),
    ]
    show = [c for c in m.chars if m.showable(c)]
    for cid, what, keyf in keyers:
        groups = {}
        for c in show:
            for v in set(keyf(c)):
                groups.setdefault(v, []).append(c)
        for v, cs in sorted(groups.items()):
            # 同じ枠の予備どうしは同時に出ないので除く。数えるのは GameObject（同じ名前の複製も別の 1 体）
            pairs = [(a, b) for i, a in enumerate(cs) for b in cs[i + 1:] if not m.exclusive(a, b)]
            if not pairs:
                continue
            by_go = {}
            for p in pairs:
                for c in p:
                    by_go[c["go"]] = c
            mem = sorted(by_go.values(), key=lambda c: c["path"])
            on_c = [c for c in mem if m.starts_visible(c)]
            members = [c["name"] for c in mem]
            on = [c["name"] for c in on_c]
            sev = "warn" if len(on_c) >= 2 else "info"
            msg = (f"開始時に一緒に見えるキャラで {what} が同じ（同じ入力で一緒に動く。別の枠の予備 [0] どうしと、枠に入っていない有効なキャラは一緒に出る。"
                   "同じ演者の衣装違いなら、同じ枠の予備に入れると同時には出ない）" if sev == "warn"
                   else f"別の枠のキャラで {what} が同じ（今は同時に出ていないが、2 体を同時に出すと同じ入力で動く）")
            f.add(sev, cid, msg, f"{v}: {len(members)} 体（開始時に見えるのは {len(on)} 体{': ' + ', '.join(on[:6]) if on else ''}）: "
                  f"{', '.join(members[:8])}{' ...' if len(members) > 8 else ''}")


# ---------------------------------------------------------------------------------------------- マイク


def _check_mic(m, f):
    for mc in m.mics:
        live = mc["live"]
        where = m.where(mc["key"])
        for ti, t in enumerate(mc["targets"]):
            tag = f"{where}  [{ti}] {t['name']}"
            if not t["animator"] and not any(t["extra_animators"]):
                f.add(_sev(live, "warn"), "mic.animator-none",
                      "MicController の枠の _targetAnimator も _additionalTargetAnimators も空（腕も握りも動かない）", tag + _off(live))
            if t["correction"] == "Auto":
                miss = [n for n, r in (("Mic Transform", t["mic_t"]), ("Mouth Transform", t["mouth"])) if not r]
                if miss:
                    f.add(_sev(live, "warn"), "mic.auto-missing", "MicController の枠が Auto なのに口・マイクの位置が空（実行時に警告して Auto が効かない）",
                          f"{tag}: {', '.join(miss)}{_off(live)}")
            if any(not r for r in t["mics"]):
                f.add(_sev(live, "warn"), "mic.mics-none", "MicController の枠の _microphoneObjects に None がある", tag + _off(live))
            hand = m.preset_hand(t["grip"])
            if hand and t["hand"] not in hand:
                f.add(_sev(live, "warn"), "mic.grip-hand",
                      "握りのプリセットの指が、マイクを持つ手と逆（プリセットは手を問わずそのまま当たるので、持つ手は握らず、逆の手が握る）",
                      f"{tag}: 持つ手 {t['hand']} / プリセット {m.asset_label(t['grip'])} は {hand}{_off(live)}")


# ---------------------------------------------------------------------------------------------- DMX


def _check_dmx(m, f):
    sc = m.sc
    bound = set()
    for d in m.directors:
        for b in d["binds"]:
            if b["value"].kind == "local":
                bound.add(b["value"].key)
                g = sc.ref_go(b["value"])
                if g is not None:
                    bound.add(g)
    live = [d for d in m.dmx if d["live"]]
    if len(live) >= 2:
        f.add("warn", "dmx.dup",
              "有効な MetaDmxReceiver が 2 つ以上（ArtNetReceiver は 6454 を ReuseAddress 無しで bind するので、2 つ目は bind に失敗して LogError を出し、何も受けない。"
              "重複を消す仕組みは無い）",
              ", ".join(m.where(d["key"]) for d in live))
    for d in m.dmx:
        where = m.where(d["key"])
        lv = d["live"]
        if d["use_timeline"]:
            if d["key"] in bound or sc.go_of.get(d["key"]) in bound:
                f.add("info", "dmx.use-timeline-tl", "MetaDmxReceiver の Use Timeline が On（Timeline の DMX トラックが結び付いている。ライブで卓を使うときは Off）",
                      where + _off(lv))
            else:
                f.add(_sev(lv, "warn"), "dmx.use-timeline", "MetaDmxReceiver の Use Timeline が On で、Timeline にも結び付いていない（ライブの Art-Net を灯体へ流さない）",
                      where + _off(lv))
        if not any(c["target"].kind == "local" and c["target"].key in sc.objs and sc.label(c["target"].key) == "FixtureController"
                   and c["method"] == "OnMetaDmx" and c["state"] != "0" for c in d["calls"]):
            f.add(_sev(lv, "warn"), "dmx.no-fixture", "MetaDmxReceiver の OnMetaDmx に FixtureController.OnMetaDmx が入っていない（受けた DMX が灯体へ流れない）",
                  where + _off(lv))


# ---------------------------------------------------------------------------------------------- OptiTrack


def _check_opti(m, f):
    live = [c for c in m.opti_clients if c["live"]]
    if len(live) >= 2:
        f.add("warn", "opti.dup", "有効な OptitrackStreamingClient が 2 つ以上（StreamingClient が空のキャラが拾う既定のクライアントが曖昧になる）",
              ", ".join(m.where(c["key"]) for c in live))


# ---------------------------------------------------------------------------------------------- 水


def _check_water(m, f):
    mains = [c for c in m.cameras if c["live"] and c["tag"] == "MainCamera"]
    for w in m.waters:
        if not w["live"] or w["camera"]:
            continue
        if mains:
            f.add("info", "water.camera-main", "Crest の WaterRenderer の Camera が空（Camera.main を基準にする）",
                  f"{m.where(w['key'])} → Camera.main 候補: {', '.join(m.where(c['key']) for c in mains)}")
        else:
            f.add("warn", "water.camera-none", "Crest の WaterRenderer の Camera が空で、MainCamera タグの有効なカメラも無い（水の詳細の中心が決まらない）",
                  m.where(w["key"]))


# ---------------------------------------------------------------------------------------------- Timeline


def _check_director(m, f):
    awake = []
    for d in m.directors:
        where = m.where(d["key"])
        if not d["asset"]:
            f.add(_sev(d["live"], "warn"), "tl.asset-none", "PlayableDirector の Playable が空", where + _off(d["live"]))
        elif not m.asset_exists(d["asset"]):
            f.add("error" if d["live"] else "warn", "tl.asset-missing",
                  "PlayableDirector の Timeline の GUID がプロジェクトに無い（.playable.meta の GUID が作り直された / ファイルが無い）",
                  f"{where}  guid {d['asset'].guid}{_off(d['live'])}")
        if d["live"] and d["play_on_awake"]:
            awake.append(where)
    if len(awake) >= 2:
        f.add("warn", "tl.multi-awake", "Play On Awake の有効な PlayableDirector が 2 つ以上（同じ DMX・カメラ・キャラを取り合う）", ", ".join(awake))


# ---------------------------------------------------------------------------------------------- ExternalControl


def _check_ext(m, f):
    for e in m.ext_controls:
        for d in e["devices"]:
            if not d["target"]:
                f.add(_sev(e["live"], "warn"), "ext.target-none", "ExternalControlManager の Control Devices の Target Script が空（その機器の入力がどこにも行かない）",
                      f"{m.where(e['key'])}  {d['name']}{_off(e['live'])}")
