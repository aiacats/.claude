"""vortex のライブシーンの中身（System の塊・配線・キャラ）を、点検しやすい形に集める。

vortex_scene.Scene（プレハブを展開したシーン）から、次を dict / list に起こす:
  OSC の受信（uOscServer / OscServerEx とそのリスナー）、CharacterActivator の枠、LookatManager の注視先、
  VirtualCameraSwitcher（Brain・RT・入力カメラの並び）、DofMidiControl、MicController の枠、DMX、OptiTrack、
  カメラ・Volume・ライト・Canvas、PlayableDirector、Crest の WaterRenderer、ExternalControlManager、キャラ。
フィールド名は Submod_RealtimeLiveUtility（jp.pjblue.realtime-live-utility）のソースで確かめたもの。
"""
import os
import re

import yaml

from vortex_scene import as_ref, is_lfs_pointer, mono_label, parse_body
from unity_yaml import load  # noqa: E402（vortex_scene が unity-scene-merge の scripts を sys.path に足す）

# キャラのルートとみなすコンポーネント（どれかを持つ最上位の GameObject）
CHAR_MARKS = ("VRMBlendShapeProxy", "OscRx_LipSync", "FacialManager", "vortex_FacialController", "OptitrackSkeletonAnimator")
# マイクなど、キャラの子に付けた小物の名前。「mic」は前後が英字でないときだけ（Dynamic・Comic・Michiru に当てない）。
# 名前のほかに、MicController の _microphoneObjects / _micTransform に入っている物と、子に付いた NiloToon の controller も小物とみなす
PROP_NAME = re.compile(r"(?i)(^|[^a-z])mic([^a-z]|$|rophone)|handmic|skm\d|dpa|propanchor|guitar|earmonitor")
FACIAL_DEVICE = {"0": "XBox", "1": "StreamDeck", "2": "Joycon", "3": "AnyDevice", "4": "Osc_XBox", "5": "Osc_StreamDeck"}
OSC_FACIAL_DEVICES = ("4", "5")  # FacialManager がこの機器のときだけ OSC を読む（それ以外は Rewired）
# HumanBodyBones の指（Unity の列挙の値）: 24〜38 が左手、39〜53 が右手
LEFT_FINGERS, RIGHT_FINGERS = range(24, 39), range(39, 54)
OPTITRACK_DEFAULT_SKELETON = "Skeleton1"  # OptitrackSkeletonAnimator.SkeletonAssetName の既定値（ソースの初期値）


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _bits(v):
    """LayerMask（{serializedVersion, m_Bits}）か整数の文字列。"""
    if isinstance(v, dict):
        v = v.get("m_Bits")
    return _int(v) & 0xFFFFFFFF


def _calls(event):
    """UnityEvent の永続リスナー。"""
    if not isinstance(event, dict):
        return []
    calls = (event.get("m_PersistentCalls") or {}).get("m_Calls") or []
    out = []
    for c in calls:
        if isinstance(c, dict):
            out.append(dict(target=as_ref(c.get("m_Target")), method=c.get("m_MethodName", ""),
                            state=str(c.get("m_CallState", "2")), type=c.get("m_TargetAssemblyTypeName", "")))
    return out


class Model:
    def __init__(self, sc):
        self.sc = sc
        self.p = sc.project
        self.bl = sc.by_label()
        self._preset_hand = {}
        self._playables = {}
        # LFS のポインタのままで中身を読めなかった物（プレハブ・モデル・Timeline・握りのプリセット）
        self.lfs = list(sc.lfs_pointers)
        self.system_roots = self._system_roots()
        self.osc_servers, self.osc_receivers = self._osc()
        self.activators = self._activators()
        self.lookats = self._lookats()
        self.switchers = self._switchers()
        self.switch_controllers = self._switch_controllers()
        self.dofs = self._dofs()
        self.mics = self._mics()
        self.dmx = self._dmx()
        self.fixtures = self._fixtures()
        self.opti_clients = self._opti_clients()
        self.cameras = self._cameras()
        self.volumes = self._volumes()
        self.lights = self._lights()
        self.canvases = self._canvases()
        self.directors = self._directors()
        self.waters = self._waters()
        self.ext_controls = self._ext_controls()
        self.gamepad_receivers = [k for k in self.bl.get("vortex_GamepadOscReceiver", [])]
        self.chars = self._chars()
        self.missing_scripts = [(k, lab) for lab, ks in self.bl.items() if lab.startswith("MissingScript") for k in ks]

    # ------------------------------------------------------------------ 共通

    def comps(self, label):
        return self.bl.get(label, [])

    def where(self, k):
        g = self.sc.go_of.get(k, k)
        return self.sc.go_path(g) if g in self.sc.go_fields else "?"

    def live(self, k):
        return self.sc.comp_active(k)

    def ref_label(self, r):
        return self.sc.describe(r)

    def asset_label(self, r):
        r = as_ref(r)
        if r.kind == "asset":
            return self.sc.guids.short(r.guid)
        return self.sc.describe(r)

    def asset_exists(self, r):
        r = as_ref(r)
        p = self.sc.guids.fs_path(r.guid) if r.kind == "asset" else None
        return p is not None and os.path.exists(p)

    def _system_roots(self):
        out = []
        for t in self.sc.roots():
            g = self.sc.go_of.get(t)
            if g is not None and re.match(r"(?i)^system", self.sc.go_name(g)):
                out.append(g)
        return out

    def in_system(self, k):
        g = self.sc.go_of.get(k, k)
        return any(a in self.system_roots for a in self.sc.ancestors(g))

    # ------------------------------------------------------------------ OSC

    def _osc(self):
        sc = self.sc
        servers = []
        for lab in ("uOscServer", "OscServerEx"):
            for k in self.comps(lab):
                b = sc.body(k)
                auto = str(b.get("autoStart", "1")) == "1"
                servers.append(dict(key=k, kind=lab, port=_int(b.get("port")), auto=auto,
                                    live=self.live(k) and auto, active=self.live(k),
                                    listeners=_calls(b.get("onDataReceived")) if lab == "uOscServer" else []))
        receivers = []
        for k in self.comps("OscReceiverEx"):
            b = sc.body(k)
            pairs = []
            for p in b.get("_addressEventPairs") or []:
                if not isinstance(p, dict):
                    continue
                calls = []
                for ev in ("stringEvent", "integerEvent", "floatEvent", "booleanEvent", "blobEvent"):
                    calls += _calls(p.get(ev))
                pairs.append(dict(address=p.get("address", ""), calls=calls))
            receivers.append(dict(key=k, server=as_ref(b.get("_server")), pairs=pairs, live=self.live(k)))
        return servers, receivers

    def osc_wired(self, live_only=True):
        """(リスナーの先のコンポーネントの key, メソッド名) → [(サーバーの key, callState)]。
        live_only なら、開くサーバー（有効・autoStart On）のリスナーだけ（無効なサーバーのリスナーは OSC を受けない）。"""
        out = {}
        for s in self.osc_servers:
            if live_only and not s["live"]:
                continue
            for c in s["listeners"]:
                if c["target"].kind == "local":
                    out.setdefault((c["target"].key, c["method"]), []).append((s["key"], c["state"]))
        return out

    # ------------------------------------------------------------------ CharacterActivator / Lookat / Switcher

    def _activators(self):
        out = []
        for k in self.comps("CharacterActivator"):
            b = self.sc.body(k)
            slots = []
            for ch in b.get("_characters") or []:
                reserves = []
                raw = (ch.get("_reserveCharacters") or []) if isinstance(ch, dict) else []
                for r in raw:
                    if not isinstance(r, dict):
                        r = {}
                    reserves.append(dict(target=as_ref(r.get("_targetCharacter")), hip=as_ref(r.get("_lookatBone_hip")),
                                         secondary=as_ref(r.get("_secondary")), in_effect=as_ref(r.get("_in_effect")),
                                         out_effect=as_ref(r.get("_out_effect")),
                                         in_delay=_float(r.get("_in_delaySeconds"), 2.0), out_delay=_float(r.get("_out_delaySeconds"), 2.0)))
                slots.append(reserves)
            out.append(dict(key=k, is_osc=str(b.get("_isOsc", "0")) == "1", live=self.live(k),
                            lookat=as_ref(b.get("_lookatManager")), switcher=as_ref(b.get("_cameraSwitcher")),
                            between=as_ref(b.get("_betweenPosition")), state_client=as_ref(b.get("_stateClient")), slots=slots))
        return out

    def _lookats(self):
        out = []
        for k in self.comps("LookatManager"):
            b = self.sc.body(k)
            targets = []
            for t in b.get("_lookatTargets") or []:
                if isinstance(t, dict):
                    targets.append(dict(name=t.get("_name", ""), hip=as_ref(t.get("_hip")), head=as_ref(t.get("_head"))))
            out.append(dict(key=k, live=self.live(k), targets=targets))
        return out

    def _switchers(self):
        sc = self.sc
        out = []
        for k in self.comps("VirtualCameraSwitcher"):
            b = sc.body(k)
            inputs = [as_ref(x) for x in b.get("_inputCameras") or []]
            # 入力カメラ（VirtualCameraChief）ごとの vcam（_vCams）。CharacterActivator.InitializeLookat が全部の Initialize を呼ぶ
            chiefs = []
            for i, r in enumerate(inputs):
                g = sc.ref_go(r)
                if g is None or r.key not in sc.objs:
                    chiefs.append(dict(index=i, go=None, active=False, vcams=[]))
                    continue
                vcams = []
                for v in sc.get(r.key, "_vCams") or []:
                    vg = sc.ref_go(as_ref(v))
                    vcams.append(dict(go=vg, active=vg is not None and sc.active_in_hierarchy(vg)))
                chiefs.append(dict(index=i, go=g, active=sc.active_in_hierarchy(g), vcams=vcams))
            out.append(dict(key=k, live=self.live(k), active=as_ref(b.get("_activeCamera")), reserve=as_ref(b.get("_reserveCamera")),
                            material=as_ref(b.get("_switchMaterial")), output=as_ref(b.get("_outputRenderTexture")),
                            rt_a=as_ref(b.get("_renderTexA")), rt_b=as_ref(b.get("_renderTexB")), preview=as_ref(b.get("_previewImage")),
                            inputs=inputs, chiefs=chiefs,
                            input_names=[sc.go_name(sc.ref_go(r)) if sc.ref_go(r) is not None else "None" for r in inputs]))
        return out

    def _switch_controllers(self):
        out = []
        for lab in ("CameraSwitcherController", "CameraLookatController"):
            for k in self.comps(lab):
                b = self.sc.body(k)
                out.append(dict(key=k, kind=lab, switcher=as_ref(b.get("_cameraSwitcher")), is_osc=str(b.get("_isOsc", "0")) == "1",
                                live=self.live(k)))
        return out

    def brain_camera(self, brain_ref):
        """CinemachineBrain の参照 → 同じ GameObject の Camera の情報（無ければ None）。"""
        g = self.sc.ref_go(brain_ref)
        if g is None:
            return None
        for c in self.cameras:
            if self.sc.go_of.get(c["key"]) == g:
                return c
        return None

    def _dofs(self):
        out = []
        for k in self.comps("DofMidiControl"):
            b = self.sc.body(k)
            out.append(dict(key=k, live=self.live(k), switcher=as_ref(b.get("_switcher")), pgm_brain=as_ref(b.get("_pgmBrain")),
                            prv_brain=as_ref(b.get("_prvBrain")), pgm_volume=as_ref(b.get("_pgmVolume")), prv_volume=as_ref(b.get("_prvVolume"))))
        return out

    # ------------------------------------------------------------------ Mic

    def preset_hand(self, r):
        """握りのプリセット（PosePreset）の指が左手か右手か: 'L' / 'R' / 'LR' / '' / None（読めない）。"""
        r = as_ref(r)
        if r.kind != "asset":
            return None
        if r.guid in self._preset_hand:
            return self._preset_hand[r.guid]
        path = self.sc.guids.fs_path(r.guid)
        hand = None
        if path and is_lfs_pointer(path):
            self.lfs.append(dict(label=self.sc.guids.label(r.guid), name="(握りのプリセット)"))
        elif path:
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                i = text.find("--- !u!")
                body = parse_body(text[i:]) if i >= 0 else {}
                bones = [_int(b.get("_humanbone"), -1) for b in body.get("_targetBones") or [] if isinstance(b, dict)]
                hand = ("L" if any(x in LEFT_FINGERS for x in bones) else "") + ("R" if any(x in RIGHT_FINGERS for x in bones) else "")
            except (OSError, ValueError, yaml.YAMLError):
                hand = None
        self._preset_hand[r.guid] = hand
        return hand

    def _mics(self):
        out = []
        for k in self.comps("MicController"):
            b = self.sc.body(k)
            targets = []
            for t in b.get("_targets") or []:
                if not isinstance(t, dict):
                    continue
                targets.append(dict(name=t.get("_name", ""), mode=_int(t.get("_activationMode")), animator=as_ref(t.get("_targetAnimator")),
                                    extra_animators=[as_ref(x) for x in t.get("_additionalTargetAnimators") or []],
                                    hand="L" if str(t.get("_handOption", "0")) == "1" else "R",
                                    correction="Auto" if str(t.get("_correctionMode", "0")) == "1" else "Manual",
                                    enable=str(t.get("_isEnable", "0")) == "1",
                                    mics=[as_ref(x) for x in t.get("_microphoneObjects") or []],
                                    grip=as_ref(t.get("_gripPosePreset")), mic_t=as_ref(t.get("_micTransform")),
                                    mouth=as_ref(t.get("_mouthTransform")), hand_aim=str(t.get("_useHandAimOffset", "0")) == "1",
                                    axis=_int(t.get("_micAimAxis")), place_ref=_int(t.get("_autoPlacementReference")),
                                    mouth_dist=t.get("_mouthDistance", "")))
            out.append(dict(key=k, live=self.live(k), is_osc=str(b.get("_isOsc", "1")) == "1",
                            update=_int(b.get("_updateMethod")), targets=targets))
        return out

    # ------------------------------------------------------------------ DMX / OptiTrack

    def _dmx(self):
        out = []
        for k in self.comps("MetaDmxReceiver"):
            b = self.sc.body(k)
            out.append(dict(key=k, live=self.live(k), receiver_type=_int(b.get("receiverType")),
                            use_timeline=str(b.get("_useTimeline", "0")) == "1", calls=_calls(b.get("OnMetaDmx"))))
        return out

    def _fixtures(self):
        """VF_*（VirtualFixture）の universe ごとの台数。"""
        rows = []
        for lab, ks in self.bl.items():
            if not lab.startswith("VF_"):
                continue
            for k in ks:
                rows.append(dict(key=k, kind=lab, universe=_int(self.sc.val(k, "_universe"), -1),
                                 start=_int(self.sc.val(k, "_startChannel"), -1), live=self.live(k)))
        return rows

    def _opti_clients(self):
        out = []
        for k in self.comps("OptitrackStreamingClient"):
            b = self.sc.body(k)
            out.append(dict(key=k, live=self.live(k), server=b.get("ServerAddress", ""), local=b.get("LocalAddress", ""),
                            conn=_int(b.get("ConnectionType")), coords=_int(b.get("SkeletonCoordinates")),
                            naming=_int(b.get("BoneNamingConvention"))))
        return out

    # ------------------------------------------------------------------ カメラ・Volume・ライト・出力

    def _cameras(self):
        sc = self.sc
        urp = {}
        for k in self.comps("UniversalAdditionalCameraData"):
            urp[sc.go_of.get(k)] = k
        out = []
        for k in self.comps("Camera"):
            b = sc.body(k)
            g = sc.go_of.get(k)
            u = urp.get(g)
            ub = sc.body(u) if u is not None else {}
            out.append(dict(key=k, go=g, live=self.live(k), go_active=sc.active_in_hierarchy(g), enabled=sc.enabled(k),
                            tag=sc.go_fields.get(g, {}).get("tag", ""), display=_int(b.get("m_TargetDisplay")),
                            rt=as_ref(b.get("m_TargetTexture")), cull=_bits(b.get("m_CullingMask")), depth=b.get("m_Depth", ""),
                            vol_mask=_bits(ub.get("m_VolumeLayerMask")) if u is not None else None,
                            post=str(ub.get("m_RenderPostProcessing", "0")) == "1" if u is not None else None,
                            renderer=_int(ub.get("m_RendererIndex"), -1) if u is not None else None,
                            cam_type=_int(ub.get("m_CameraType")) if u is not None else 0))
        return out

    def _volumes(self):
        sc = self.sc
        out = []
        for k in self.comps("Volume"):
            b = sc.body(k)
            g = sc.go_of.get(k)
            out.append(dict(key=k, live=self.live(k), layer=sc.go_fields.get(g, {}).get("layer", 0),
                            is_global=str(b.get("m_IsGlobal", "1")) == "1", priority=b.get("priority", ""),
                            weight=b.get("weight", ""), profile=as_ref(b.get("sharedProfile"))))
        return out

    def _lights(self):
        sc = self.sc
        urp = {}
        for k in self.comps("UniversalAdditionalLightData"):
            urp[sc.go_of.get(k)] = k
        out = []
        for k in self.comps("Light"):
            g = sc.go_of.get(k)
            u = urp.get(g)
            rl = None
            if u is not None:
                ub = sc.body(u)
                rl = _bits(ub["m_RenderingLayersMask"]) if "m_RenderingLayersMask" in ub else _bits(ub.get("m_RenderingLayers"))
            out.append(dict(key=k, live=self.live(k), type=_int(sc.val(k, "m_Type")), intensity=sc.val(k, "m_Intensity"), rl=rl))
        return out

    def _canvases(self):
        sc = self.sc
        out = []
        for k in self.comps("Canvas"):
            b = sc.body(k)
            g = sc.go_of.get(k)
            raws = []
            for d in sc.descendants(g):
                for c in sc.components(d):
                    if sc.label(c) == "RawImage":
                        rb = sc.body(c)
                        raws.append(dict(key=c, texture=as_ref(rb.get("m_Texture")), material=as_ref(rb.get("m_Material")), live=self.live(c)))
            out.append(dict(key=k, live=self.live(k), mode=_int(b.get("m_RenderMode")), display=_int(b.get("m_TargetDisplay")),
                            camera=as_ref(b.get("m_Camera")), sort=b.get("m_SortingOrder", ""), raws=raws))
        return out

    def _playable(self, guid):
        """Timeline（.playable）のトラック: fileID → dict(label, muted, parent, clips=[クリップの fileID], text)。読めなければ None。"""
        if guid in self._playables:
            return self._playables[guid]
        path = self.sc.guids.fs_path(guid) if guid else None
        info = None
        if path and os.path.exists(path):
            if is_lfs_pointer(path):
                self.lfs.append(dict(label=self.sc.guids.label(guid), name="(Timeline)"))
            else:
                info = {}
                for d in load(path)[1]:
                    if d.cls != "114":
                        continue
                    mu = re.search(r"(?m)^  m_Muted: (\d)", d.text)
                    pa = re.search(r"(?m)^  m_Parent: \{fileID: (-?\d+)", d.text)
                    clips = re.findall(r"(?m)^    m_Asset: \{fileID: (-?\d+)\}", d.text)
                    info[d.fid] = dict(label=mono_label(d.text, self.sc.guids), muted=bool(mu and mu.group(1) == "1"),
                                       parent=pa.group(1) if pa else None, clips=clips, text=d.text)
        self._playables[guid] = info
        return info

    @staticmethod
    def _track_muted(tracks, fid):
        """トラックか、その親のグループがミュート（グラフに入らない）。"""
        seen = set()
        while fid in tracks and fid not in seen:
            seen.add(fid)
            if tracks[fid]["muted"]:
                return True
            fid = tracks[fid]["parent"]
        return False

    def _directors(self):
        sc = self.sc
        out = []
        for k in self.comps("PlayableDirector"):
            b = sc.body(k)
            asset = as_ref(b.get("m_PlayableAsset"))
            tracks = self._playable(asset.guid) if asset.kind == "asset" else None
            binds = []
            for e in b.get("m_SceneBindings") or []:
                if not isinstance(e, dict):
                    continue
                tr = as_ref(e.get("key"))
                t = tracks.get(tr.fid) if tracks and tr.kind == "asset" else None
                indices = []
                if t and t["label"] == "CharacterActivationTrack":
                    for cf in t["clips"]:
                        cd = tracks.get(cf)
                        m = re.search(r"(?m)^  characterIndex: (\d+)", cd["text"]) if cd else None
                        if m:
                            indices.append(int(m.group(1)))
                binds.append(dict(track=tr, value=as_ref(e.get("value")), track_type=t["label"] if t else None,
                                  muted=self._track_muted(tracks, tr.fid) if t else False, indices=indices))
            out.append(dict(key=k, live=self.live(k), asset=asset, tracks_read=tracks is not None,
                            play_on_awake=str(b.get("m_InitialState", "0")) == "1", wrap=_int(b.get("m_WrapMode")), binds=binds))
        return out

    def timeline_claimed(self):
        """Play On Awake の有効な Director の CharacterActivationTrack が受け持つ枠: CharacterActivator の key → {枠の番号}。
        受け持つ枠は Start で InitializeHidden（全員消える）から始まる（CharacterActivationTrack.CreateTrackMixer → ClaimTimelineControl）。"""
        out = {}
        for d in self.directors:
            if not (d["live"] and d["play_on_awake"]):
                continue
            for b in d["binds"]:
                if b["track_type"] == "CharacterActivationTrack" and not b["muted"] and b["value"].kind == "local":
                    out.setdefault(b["value"].key, set()).update(b["indices"])
        return out

    def _waters(self):
        out = []
        for k in self.comps("WaterRenderer"):
            out.append(dict(key=k, live=self.live(k), camera=as_ref(self.sc.get(k, "_Camera"))))
        return out

    def _ext_controls(self):
        out = []
        for k in self.comps("ExternalControlManager"):
            b = self.sc.body(k)
            devs = []
            for d in b.get("_controlDevices") or []:
                if isinstance(d, dict):
                    devs.append(dict(name=d.get("_name", ""), devices=d.get("_deviceNames") or [], target=as_ref(d.get("_targetScript"))))
            out.append(dict(key=k, live=self.live(k), devices=devs))
        return out

    # ------------------------------------------------------------------ キャラ

    def _chars(self):
        sc = self.sc
        marked = set()
        for lab in CHAR_MARKS:
            for k in self.comps(lab):
                g = sc.go_of.get(k)
                if g is not None:
                    marked.add(g)
        tops = []
        for g in marked:
            if not any(a in marked for a in list(sc.ancestors(g))[1:]):
                tops.append(g)
        tops.sort(key=sc.go_path)
        prop_refs = self._mic_prop_gos()
        chars = []
        for g in tops:
            chars.append(self._char(g, prop_refs))
        self._link_chars(chars)
        return chars

    def _mic_prop_gos(self):
        """MicController の枠のマイク（_microphoneObjects / _micTransform）の GameObject。"""
        out = set()
        for mc in self.mics:
            for t in mc["targets"]:
                for r in t["mics"] + [t["mic_t"]]:
                    g = self.sc.ref_go(r)
                    if g is not None:
                        out.add(g)
        return out

    def _char(self, g, prop_refs):
        sc = self.sc
        gf = sc.go_fields.get(g, {})
        c = dict(go=g, path=sc.go_path(g), name=gf.get("name", "?"), active_self=gf.get("active", True),
                 active=sc.active_in_hierarchy(g), layer=gf.get("layer", 0),
                 origin=("instance " + sc.instance_root[g]) if g in sc.instance_root else ("inside " + sc.from_prefab[g] if sc.from_prefab.get(g) else "scene"),
                 mods=len(sc.instance_mods.get(g, [])), root_comps=[sc.label(k) for k in sc.components(g)],
                 lipsync=[], facial=[], vfc=[], ulipsync=0, opti=[], animators=[], smr=0, mr=0, go_layers={}, rls={},
                 spring=0, magica=0, props=[], scale=None, gos=set(), renderers=[])
        t = sc.transform_of_go(g)
        if t is not None:
            sv = sc.get(t, "m_LocalScale")
            if isinstance(sv, dict):
                c["scale"] = (sv.get("x"), sv.get("y"), sv.get("z"))
        gos = list(sc.descendants(g))
        c["gos"] = set(gos)

        def is_prop(d):
            return (PROP_NAME.search(sc.go_name(d)) is not None or d in prop_refs
                    or any(sc.label(k) == "NiloToonPerCharacterRenderController" for k in sc.components(d)))
        for d in gos:
            if d != g and is_prop(d):
                p = sc.parent_go(d)
                if p is None or p == g or not is_prop(p):
                    c["props"].append(d)
        prop_gos = set()
        for pg in c["props"]:
            prop_gos |= set(sc.descendants(pg))
        for d in gos:
            dl = sc.go_fields.get(d, {}).get("layer", 0)
            for k in sc.components(d):
                lab = sc.label(k)
                if lab in ("SkinnedMeshRenderer", "MeshRenderer"):
                    rl = _int(sc.val(k, "m_RenderingLayerMask"), 1)
                    c["renderers"].append(dict(key=k, go=d, kind=lab, layer=dl, rl=rl, prop=d in prop_gos))
                    if d in prop_gos:
                        continue
                    # 体（小物を除く）の Renderer だけを数える。小物（マイクなど）は renderers に prop として残す
                    c["smr" if lab == "SkinnedMeshRenderer" else "mr"] += 1
                    c["go_layers"][dl] = c["go_layers"].get(dl, 0) + 1
                    c["rls"][rl] = c["rls"].get(rl, 0) + 1
                elif lab == "OscRx_LipSync":
                    c["lipsync"].append(dict(key=k, id=_int(sc.val(k, "characterID")), proxy=as_ref(sc.get(k, "blendShapeProxy")),
                                             enabled=sc.enabled(k)))
                elif lab == "FacialManager":
                    dev = str(sc.val(k, "_deviceType") or "0")
                    c["facial"].append(dict(key=k, device=dev, id=_int(sc.val(k, "oscFacialID")), enabled=sc.enabled(k)))
                elif lab == "vortex_FacialController":
                    c["vfc"].append(dict(key=k, label=sc.val(k, "_controllerLabel") or "", proxy=as_ref(sc.get(k, "_proxy")),
                                         enabled=sc.enabled(k)))
                elif lab.startswith("uLipSync"):
                    c["ulipsync"] += 1
                elif lab == "OptitrackSkeletonAnimator":
                    c["opti"].append(dict(key=k, skeleton=sc.val(k, "SkeletonAssetName") or "", client=as_ref(sc.get(k, "StreamingClient")),
                                          avatar=as_ref(sc.get(k, "DestinationAvatar")), enabled=sc.enabled(k),
                                          rel=sc.go_path(d)[len(c["path"]) + 1:] or "(root)"))
                elif lab == "Animator":
                    c["animators"].append(dict(key=k, avatar=as_ref(sc.get(k, "m_Avatar")), controller=as_ref(sc.get(k, "m_Controller")),
                                               enabled=sc.enabled(k), rel=sc.go_path(d)[len(c["path"]) + 1:] or "(root)"))
                elif lab == "VRMSpringBone":
                    c["spring"] += 1
                elif lab.startswith("MagicaCloth"):
                    c["magica"] += 1
        # 仕込み済み = NiloToon の変換か、表情・口パクの仕組みが付いている（vortex-character-setup を通したキャラ）
        c["setup"] = ("NiloToonPerCharacterRenderController" in c["root_comps"]
                      or bool(c["lipsync"] or c["facial"] or c["vfc"] or c["ulipsync"]))
        return c

    def _link_chars(self, chars):
        """キャラごとに、どの枠・注視先・マイク・OSC・Timeline から指されているか。"""
        sc = self.sc
        owner = {}
        for c in chars:
            for d in c["gos"]:
                owner[d] = c
        for c in chars:
            c.update(slots=[], lookat=[], mic=[], osc=[], bound=False, act_bound=[])
        for ai, a in enumerate(self.activators):
            for si, reserves in enumerate(a["slots"]):
                for ri, r in enumerate(reserves):
                    c = owner.get(sc.ref_go(r["target"]))
                    if c is not None:
                        c["slots"].append((ai, si, ri))
        for li, la in enumerate(self.lookats):
            for ti, t in enumerate(la["targets"]):
                c = owner.get(sc.ref_go(t["hip"])) or owner.get(sc.ref_go(t["head"]))
                if c is not None:
                    c["lookat"].append((li, ti))
        for mi, m in enumerate(self.mics):
            for ti, t in enumerate(m["targets"]):
                c = owner.get(sc.ref_go(t["animator"]))
                if c is not None:
                    c["mic"].append((mi, ti))
        wired = self.osc_wired(live_only=True)
        wired_any = self.osc_wired(live_only=False)
        for c in chars:
            for e in c["lipsync"] + c["facial"]:
                e["wired"] = [st for (k, meth), lst in wired.items() if k == e["key"] for _, st in lst]
                e["wired_any"] = [st for (k, meth), lst in wired_any.items() if k == e["key"] for _, st in lst]
            c["osc"] = [e for e in c["lipsync"] + c["facial"] if e["wired"]]
        for d in self.directors:
            for bnd in d["binds"]:
                g = sc.ref_go(bnd["value"])
                c = owner.get(g)
                if c is not None:
                    c["bound"] = True
                # Activation Track がキャラのルートかその親を有効にする（キャラの中の物を指すのは Animator などで、ルートは有効にならない）
                if bnd["track_type"] == "ActivationTrack" and not bnd["muted"] and g is not None:
                    for c2 in chars:
                        if g in set(sc.ancestors(c2["go"])):
                            c2["act_bound"].append(g)
        self.char_of = owner

    def _inactive_chain(self, c):
        """キャラのルートとその祖先のうち、無効（activeSelf が Off）な GameObject。"""
        return [g for g in self.sc.ancestors(c["go"]) if not self.sc.go_fields.get(g, {}).get("active", True)]

    def _reserve(self, slot):
        ai, si, ri = slot
        return self.activators[ai]["slots"][si][ri]

    def can_show_by_slot(self, c, slot):
        """CharacterActivator がこの枠でキャラを出せるか。ApplyActive が切り替えるのは子の Renderer・Lookat Bone_hip・_secondary だけで、
        ルートの有効は変えない（CharacterActivator.cs ApplyActive）。出せるのは、無効な祖先が無いか、無効なのが hip そのものだけのとき。"""
        r = self._reserve(slot)
        hg = self.sc.ref_go(r["hip"])
        if hg is None:
            return False  # hip が空の予備は ControlActive が何もしない
        return all(g == hg for g in self._inactive_chain(c))

    def showable(self, c, any_slot=False):
        """キャラが Play 中に出うるか:
          シーンで有効（activeInHierarchy）/ Activation Track が無効なルート（か親）を有効にする / 有効な CharacterActivator の枠で出せる。
        any_slot なら、CharacterActivator の枠にいるだけで数える（System ごと無効の仕込み用シーンを info で点検するとき）。"""
        if c["active"]:
            return True
        if c["act_bound"]:
            inactive = self._inactive_chain(c)
            if all(g in c["act_bound"] for g in inactive):
                return True
        if any_slot and c["slots"]:
            return True
        return any(self.activators[s[0]]["live"] and self.can_show_by_slot(c, s) for s in c["slots"])

    def starts_visible(self, c):
        """Play の開始時に見えているか。有効な CharacterActivator の Start（IntializeCharactersState）は各枠の予備 [0] を出し、ほかを消す。
        ただし Play On Awake の Director の CharacterActivationTrack が受け持つ枠は全員消えて始まり（InitializeHidden）、
        Lookat Bone_hip が空の予備は ControlActive / SetActiveImmediate が何もしないので、シーンの状態のまま。枠に入っていない有効なキャラは出たまま。"""
        if not hasattr(self, "_claimed"):
            self._claimed = self.timeline_claimed()
        claimed = self._claimed
        live_slots = [s for s in c["slots"] if self.activators[s[0]]["live"]]
        if not live_slots:
            return c["active"]
        for s in live_slots:
            ai, si, ri = s
            if not self._reserve(s)["hip"]:
                if c["active"]:
                    return True
                continue
            if si in claimed.get(self.activators[ai]["key"], set()):
                continue
            if ri == 0 and self.can_show_by_slot(c, s):
                return True
        return False

    @staticmethod
    def exclusive(a, b):
        """2 体が同時には出ない（同じ CharacterActivator の同じ枠の予備どうし。枠は 1 体ずつしか出さない）。"""
        sa = {(x[0], x[1]) for x in a["slots"]}
        sb = {(x[0], x[1]) for x in b["slots"]}
        return bool(sa & sb)
