"""Unity のシーン / プレハブを読み、プレハブのインスタンスを展開したヒエラルキーを作る（読むだけ。Unity 不要）。

塊（--- !u!）への分割は unity-scene-merge の unity_yaml を使う。ここで足すのは:
  - Project: シーンのパスから Unity プロジェクトを見つけ、レイヤー名・Rendering Layer 名・パッケージの置き場を読む
  - GuidMap: GUID → アセットのパス。%TEMP%/vortex-scene-audit/ に表を持ち、変わった .meta だけ読み直す
  - Scene: プレハブのインスタンス（入れ子・上書き・stripped・消したコンポーネント）を展開し、
           外から見た id（key）で GameObject・Transform・コンポーネントを引けるようにする

展開した物の key は Unity と同じ式: インスタンスの中の物 q は (q ^ PrefabInstance の fileID) & 0x7FFF_FFFF_FFFF_FFFF。
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time

import yaml

_SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_SKILLS, "unity-scene-merge", "scripts"))
from unity_yaml import CLASS_NAMES, load  # noqa: E402

MASK = 0x7FFFFFFFFFFFFFFF
# unity_yaml の表に無いクラス ID（https://docs.unity3d.com/Manual/ClassIDReference.html）
CLASS_NAMES = dict(CLASS_NAMES)
CLASS_NAMES.update({"81": "AudioListener", "96": "TrailRenderer", "111": "Animation", "135": "SphereCollider", "136": "CapsuleCollider",
                    "153": "ConfigurableJoint", "205": "LODGroup", "215": "ReflectionProbe", "220": "LightProbeGroup", "225": "CanvasGroup"})
# FBX などのモデルのプレハブは中身が YAML に無い。ルートの GameObject / Transform の fileID は
# ModelImporter が全モデルで同じ値を振る（どのモデルの .unity でも同じ値で参照されている）
MODEL_ROOT_GO = 919132149155446097
MODEL_ROOT_TR = -8679921383154817045
TRANSFORM_CLASSES = ("4", "224")
# Unity が読まないフォルダ（末尾 ~・先頭 .）。同じ GUID の写しが入っていることがある（_GamepadOsc~ など）
_SKIP_DIR = re.compile(r"(~$|^\.)")

RE_NAME = re.compile(r"(?m)^  m_Name: (.*?)\r?$")
RE_ACTIVE = re.compile(r"(?m)^  m_IsActive: (\d)")
RE_LAYER = re.compile(r"(?m)^  m_Layer: (\d+)")
RE_TAG = re.compile(r"(?m)^  m_TagString: (.*?)\r?$")
RE_COMP = re.compile(r"(?m)^  - component: \{fileID: (-?\d+)\}")
RE_GO = re.compile(r"(?m)^  m_GameObject: \{fileID: (-?\d+)\}")
RE_FATHER = re.compile(r"(?m)^  m_Father: \{fileID: (-?\d+)\}")
RE_CHILDREN = re.compile(r"(?ms)^  m_Children:\s*\r?\n((?:  - \{fileID: -?\d+\}\r?\n)*)")
RE_FID = re.compile(r"\{fileID: (-?\d+)\}")
RE_SCRIPT = re.compile(r"(?m)^  m_Script: \{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}))?")
RE_PI = re.compile(r"(?m)^  m_PrefabInstance: \{fileID: (-?\d+)\}")
RE_CSO = re.compile(r"(?m)^  m_CorrespondingSourceObject: \{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}))?")
RE_ROOTS = re.compile(r"(?ms)^  m_Roots:\s*\r?\n((?:  - \{fileID: -?\d+\}\r?\n)*)")
RE_REF = re.compile(r"^\{fileID: (-?\d+)(?:, guid: ([0-9a-f]{32}), type: \d+)?\}$")
RE_CLASS_ID = re.compile(r"(?m)^  m_EditorClassIdentifier: ?(.*?)\r?$")
# Unity 本体の組み込みの GUID（0000000000000000e000000000000000 = 組み込みの型・f... = 組み込みのリソース）。.meta が無いのが正常
BUILTIN_GUID = re.compile(r"^0{16}[0-9a-f]0{15}$")


LFS_HEAD = b"version https://git-lfs.github.com/spec/"
# 値をすべて文字列のまま読む Loader。libyaml 付きの PyYAML なら C 版（速い）、無ければ Python 版（同じ結果で遅い）。
# どちらで動いているかは、Python 版のときだけ最初に 1 回 stderr へ出す
YAML_LOADER = getattr(yaml, "CBaseLoader", None) or yaml.BaseLoader
_LOADER_NOTICE = [YAML_LOADER is yaml.BaseLoader]


def setup_stdio():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def is_lfs_pointer(path):
    """git LFS のポインタ（実体を取り出していないファイル）か。"""
    try:
        with open(path, "rb") as f:
            return f.read(len(LFS_HEAD)) == LFS_HEAD
    except OSError:
        return False


def _yaml_load(text):
    if _LOADER_NOTICE[0]:
        _LOADER_NOTICE[0] = False
        print("[yaml] libyaml が無いので Python 版の Loader で読む（大きいシーンでは遅い）", file=sys.stderr)
    return yaml.load(text, Loader=YAML_LOADER)


def scalar(raw):
    """YAML の 1 行の値（引用符・エスケープ付きのことがある）を文字列に。"""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        try:
            return _yaml_load("v: " + raw)["v"]
        except yaml.YAMLError:
            return raw
    return raw


def mono_label(text, guids):
    """MonoBehaviour の塊の本文から、スクリプトのクラス名。
    Unity 6 は m_EditorClassIdentifier に「アセンブリ::名前空間.クラス」を書く（古いシーンは空）。DLL のクラス名と、消えたスクリプトの元の名前が分かる。"""
    m = RE_SCRIPT.search(text)
    ci = RE_CLASS_ID.search(text)
    cname = ci.group(1).split("::")[-1].split(".")[-1].strip() if ci and ci.group(1).strip() else ""
    if not m or m.group(1) == "0":
        return f"MissingScript({cname})" if cname else "MissingScript"
    if not m.group(2):
        return cname or "MonoBehaviour"
    if BUILTIN_GUID.match(m.group(2)):
        return cname or f"Builtin:{m.group(1)}"
    p = guids.label(m.group(2))
    if p is None:
        return f"MissingScript({cname or m.group(2)[:8]})"
    b = os.path.basename(p)
    return b[:-3] if b.endswith(".cs") else (cname or f"{b}:{m.group(1)}")


def parse_body(text):
    """塊の本文（見出し行を除く）を、値をすべて文字列のままの dict に（型の推測で On / 1e3 などが化けないように）。"""
    nl = text.find("\n")
    if nl < 0:
        return {}
    data = _yaml_load(text[nl + 1:])
    if isinstance(data, dict) and len(data) == 1:
        data = next(iter(data.values()))
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------------------------- Project


class Project:
    """Unity プロジェクト（Assets と ProjectSettings を持つフォルダ）。"""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.layers = [""] * 32
        self.rendering_layers = [""] * 32
        self._read_tags()
        self.package_roots = self._package_roots()

    @staticmethod
    def find(path):
        cur = os.path.dirname(os.path.abspath(path))
        while True:
            if os.path.isdir(os.path.join(cur, "Assets")) and os.path.isdir(os.path.join(cur, "ProjectSettings")):
                return Project(cur)
            nxt = os.path.dirname(cur)
            if nxt == cur:
                raise SystemExit(f"Unity のプロジェクト（Assets と ProjectSettings のあるフォルダ）が見つからない: {path}")
            cur = nxt

    def _read_tags(self):
        p = os.path.join(self.root, "ProjectSettings", "TagManager.asset")
        if is_lfs_pointer(p):
            # レイヤー名が読めないと、キャラ用レイヤー・Rendering Layer の点検が黙って飛ぶので止める
            raise SystemExit(f"TagManager.asset が git LFS のポインタのまま（実体が無い）: {p}\n  git lfs pull（または git lfs checkout）で取り出してから流す")
        with open(p, encoding="utf-8") as f:
            text = f.read()
        i = text.find("--- !u!")
        data = parse_body(text[i:]) if i >= 0 else {}
        for i, n in enumerate(data.get("layers") or []):
            if i < 32:
                self.layers[i] = n or ""
        for i, n in enumerate(data.get("m_RenderingLayers") or []):
            if i < 32:
                self.rendering_layers[i] = n or ""

    def layer_name(self, i):
        i = int(i)
        return self.layers[i] if 0 <= i < 32 and self.layers[i] else f"L{i}"

    def mask_names(self, bits, names=None):
        names = names or self.layers
        bits = int(bits) & 0xFFFFFFFF
        if bits == 0xFFFFFFFF:
            return "Everything"
        if bits == 0:
            return "Nothing"
        return "|".join((names[i] or f"L{i}") for i in range(32) if bits >> i & 1)

    def rl_names(self, bits):
        return self.mask_names(bits, self.rendering_layers)

    def chara_layers(self):
        """キャラ用のレイヤー（名前が chara で始まる。SinkaiFes2026 は Chara、vortex_urp は Character）。"""
        return [i for i, n in enumerate(self.layers) if re.match(r"(?i)^chara", n or "")]

    def chara_rendering_layers(self):
        """キャラ用の Rendering Layer（SinkaiFes2026 は Character、vortex_urp は Charactor）。"""
        return [i for i, n in enumerate(self.rendering_layers) if re.match(r"(?i)^chara", n or "")]

    def _package_roots(self):
        """(フォルダ, 表示の頭) の並び。先にあるほど GUID の重複で優先する（Assets > 埋め込み・file: > PackageCache）。"""
        roots = [(os.path.join(self.root, "Assets"), "Assets")]
        pk = os.path.join(self.root, "Packages")
        if os.path.isdir(pk):
            for e in sorted(os.scandir(pk), key=lambda e: e.name):
                if e.is_dir() and not _SKIP_DIR.search(e.name):
                    roots.append((e.path, "Packages/" + e.name))
            man = os.path.join(pk, "manifest.json")
            if os.path.exists(man):
                with open(man, encoding="utf-8") as f:
                    deps = json.load(f).get("dependencies", {})
                for name, ver in sorted(deps.items()):
                    if isinstance(ver, str) and ver.startswith("file:"):
                        p = os.path.normpath(os.path.join(pk, ver[5:]))
                        if os.path.isdir(p) and not any(os.path.normcase(p) == os.path.normcase(r) for r, _ in roots):
                            roots.append((p, "Packages/" + name))
        cache = os.path.join(self.root, "Library", "PackageCache")
        if os.path.isdir(cache):
            for e in sorted(os.scandir(cache), key=lambda e: e.name):
                if e.is_dir():
                    roots.append((e.path, "Packages/" + e.name.split("@")[0]))
        return roots


# ---------------------------------------------------------------------------------------------- GuidMap


class GuidMap:
    """GUID → アセットのパス。表は %TEMP%/vortex-scene-audit/guids-<プロジェクトの hash>.json。

    毎回フォルダをたどって .meta の大きさと更新時刻を比べ、変わった物・増えた物だけ読み直す（消えた物は表から落とす）。
    初回は .meta を全部読む（SinkaiFes2026 の 3.5 万件で、OS のファイルキャッシュが冷えているとき 104 秒。2 回目からは 0.6 秒）。
    本体の無い .meta（アセットを消して .meta だけ残った物）は表に入れない（Unity もその GUID を持つアセットを読めない）。
    """

    VERSION = 1

    def __init__(self, project, quiet=False):
        self.project = project
        key = hashlib.sha1(os.path.normcase(project.root).encode("utf-8")).hexdigest()[:12]
        self.cache_path = os.path.join(tempfile.gettempdir(), "vortex-scene-audit", f"guids-{key}.json")
        t0 = time.time()
        old = self._load_cache()
        metas, reread = {}, 0
        self.by_guid = {}  # guid -> (表示のパス, ファイルのパス)
        self.orphan_metas = 0
        for root, label in project.package_roots:
            for meta, st, has_asset in self._walk(root):
                prev = old.get(meta)
                if prev and prev[0] == st.st_mtime_ns and prev[1] == st.st_size:
                    guid = prev[2]
                else:
                    guid = self._read_guid(meta)
                    reread += 1
                metas[meta] = [st.st_mtime_ns, st.st_size, guid]
                if not has_asset:
                    self.orphan_metas += 1
                    continue
                if guid and guid not in self.by_guid:
                    asset = meta[:-5]
                    rel = os.path.relpath(asset, root).replace("\\", "/")
                    self.by_guid[guid] = (label + "/" + rel, asset)
        if reread or len(metas) != len(old):
            self._save_cache(metas)
        if not quiet:
            print(f"[guid] {len(self.by_guid)} 件（読み直し {reread} 件, {time.time() - t0:.1f}s, 表 {self.cache_path}）", file=sys.stderr)

    def _load_cache(self):
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") == self.VERSION and data.get("project") == self.project.root:
                return data.get("metas", {})
        except (OSError, ValueError):
            pass
        return {}

    def _save_cache(self, metas):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        tmp = self.cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": self.VERSION, "project": self.project.root, "metas": metas}, f, ensure_ascii=False)
        os.replace(tmp, self.cache_path)

    @staticmethod
    def _walk(root):
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                entries = list(it)
            names = {e.name for e in entries}
            for e in entries:
                if e.is_dir(follow_symlinks=False):
                    if not _SKIP_DIR.search(e.name):
                        stack.append(e.path)
                elif e.name.endswith(".meta"):
                    try:
                        yield e.path, e.stat(), e.name[:-5] in names
                    except OSError:
                        pass

    @staticmethod
    def _read_guid(meta):
        try:
            with open(meta, encoding="utf-8", errors="ignore") as f:
                head = f.read(400)
        except OSError:
            return None
        m = re.search(r"(?m)^guid: ([0-9a-f]{32})", head)
        return m.group(1) if m else None

    def label(self, guid):
        v = self.by_guid.get(guid)
        return v[0] if v else None

    def fs_path(self, guid):
        v = self.by_guid.get(guid)
        return v[1] if v else None

    def short(self, guid):
        """表示用: Assets/ や Packages/<名前>/ の頭を落とした、ファイル名寄りの短いパス。"""
        p = self.label(guid)
        if not p:
            return f"(missing guid {guid[:8]})"
        return re.sub(r"^(Assets|Packages/[^/]+)/", "", p)


# ---------------------------------------------------------------------------------------------- Ref


class Ref:
    """シーンの中の参照。kind: none（{fileID: 0}）/ local（展開後の key）/ asset（guid と fileID）。"""
    __slots__ = ("kind", "key", "guid", "fid")

    def __init__(self, kind, key=None, guid=None, fid=None):
        self.kind, self.key, self.guid, self.fid = kind, key, guid, fid

    def __bool__(self):
        return self.kind != "none"

    def __repr__(self):
        return f"Ref({self.kind}, {self.key if self.kind == 'local' else (self.guid, self.fid)})"


NONE_REF = Ref("none")


def as_ref(v):
    return v if isinstance(v, Ref) else NONE_REF


# ---------------------------------------------------------------------------------------------- Scene


class FakeDoc:
    __slots__ = ("fid", "cls", "stripped", "text")

    def __init__(self, fid, cls):
        self.fid, self.cls, self.stripped, self.text = str(fid), cls, False, ""


def _is_yaml(path):
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%YAML"
    except OSError:
        return False


def _is_yaml_name(path):
    """拡張子から、Unity が YAML で書くアセットか（LFS のポインタで中身が見られないとき用）。"""
    return os.path.splitext(path)[1].lower() in (".prefab", ".unity", ".asset", ".playable", ".mat", ".controller")


def _set_path(root, path, value):
    """プレハブの上書き（propertyPath: a.b.Array.data[2].c / a.Array.size）を dict / list へ当てる。"""
    toks = path.split(".")
    parent, key, cur = None, None, root
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "Array" and i + 1 < len(toks):
            if not isinstance(cur, list):
                cur = []
                if parent is not None:
                    parent[key] = cur
            n = toks[i + 1]
            if n == "size":
                try:
                    size = int(value) if not isinstance(value, Ref) else len(cur)
                except ValueError:
                    return
                del cur[size:]
                while len(cur) < size:
                    cur.append(None)
                return
            m = re.match(r"data\[(\d+)\]$", n)
            if not m:
                return
            idx = int(m.group(1))
            while len(cur) <= idx:
                cur.append(None)
            if i + 2 >= len(toks):
                cur[idx] = value
                return
            if not isinstance(cur[idx], (dict, list)):
                cur[idx] = [] if toks[i + 2] == "Array" else {}
            parent, key, cur = cur, idx, cur[idx]
            i += 2
            continue
        if not isinstance(cur, dict):
            new = {}
            if parent is not None:
                parent[key] = new
            cur = new
        if i == len(toks) - 1:
            cur[t] = value
            return
        nxt = cur.get(t)
        if not isinstance(nxt, (dict, list)):
            nxt = [] if toks[i + 1] == "Array" else {}
            cur[t] = nxt
        parent, key, cur = cur, t, nxt
        i += 1


def _get_path(data, path):
    cur = data
    for t in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(t)
        elif isinstance(cur, list) and re.fullmatch(r"\d+", t):
            i = int(t)
            cur = cur[i] if i < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


class Scene:
    """シーンかプレハブを 1 つ展開したもの。key はこのファイルから見た id。

    objs[key]       塊（Doc / FakeDoc）。cls はクラス ID の文字列（"1" GameObject、"114" MonoBehaviour ...）
    ctx[key]        その塊の中の {fileID: n} を key へ直すための (stripped の対応表, XOR)
    go_fields[key]  GameObject の name / active / layer / tag（上書きを当てた後）
    parent / children / go_of / comps_of / removed / overrides / instance_root / instance_mods / from_prefab
    """

    def __init__(self, path, project=None, guids=None, depth=0, _subs=None, _files=None):
        self.path = os.path.abspath(path)
        self.project = project or Project.find(self.path)
        self.guids = guids or GuidMap(self.project)
        self.depth = depth
        self._subs = {} if _subs is None else _subs  # プレハブのパス -> 展開済みの Scene（同じプレハブの 2 つ目からは使い回す）
        self._files = {} if _files is None else _files
        if depth == 0 and is_lfs_pointer(self.path):
            raise SystemExit(f"シーンが git LFS のポインタのまま（実体が無い）: {self.path}\n"
                             "  git lfs pull で取り出すか、unity-scene-merge の scene_diff.py fromgit で版を取り出して --project を付けて流す")
        if self.path not in self._files:
            self._files[self.path] = load(self.path)[1]
        self.docs = self._files[self.path]
        self.by = {int(d.fid): d for d in self.docs}
        self.objs, self.ctx, self.go_fields = {}, {}, {}
        self.parent, self.children, self.go_of, self.comps_of = {}, {}, {}, {}
        self.instance_root, self.instance_mods, self.instance_pi = {}, {}, {}
        self.from_prefab, self.removed, self.overrides = {}, set(), {}
        self.pi_root_tr = {}
        self.missing_prefabs = []  # dict(pi, guid, name, parent[, nested])
        self.lfs_pointers = []  # dict(label, name[, nested]) 元のプレハブ・モデルが LFS のポインタのまま（中身を読めない）
        self._body_cache = {}
        self._label_cache = {}
        self._build()

    # ------------------------------------------------------------------ 組み立て

    def A(self, x):
        """このファイルの fileID（stripped なら展開後の key へ）。"""
        return self.alias.get(x, x)

    def _ref_from(self, d, alias, xor):
        """{fileID, guid} の dict / 文字列を Ref に（local は key へ直す）。"""
        if isinstance(d, str):
            m = RE_REF.match(d.strip())
            if not m:
                return NONE_REF
            fid, guid = m.group(1), m.group(2)
        elif isinstance(d, dict):
            fid, guid = d.get("fileID", "0"), d.get("guid")
        else:
            return NONE_REF
        if guid:
            return Ref("asset", guid=guid, fid=fid)
        try:
            v = int(fid)
        except (TypeError, ValueError):
            return NONE_REF
        if v == 0:
            return NONE_REF
        v = alias.get(v, v)
        return Ref("local", key=(v ^ xor) & MASK if xor else v)

    def _build(self):
        self.alias = {}
        for d in self.docs:
            if d.stripped:
                cso, pim = RE_CSO.search(d.text), RE_PI.search(d.text)
                if cso and pim:
                    self.alias[int(d.fid)] = (int(cso.group(1)) ^ int(pim.group(1))) & MASK
        for d in self.docs:
            if d.stripped or d.cls == "1001":
                continue
            k = int(d.fid)
            self.objs[k] = d
            self.ctx[k] = (self.alias, 0)
            self.from_prefab[k] = None
        for d in self.docs:
            if d.cls == "1001":
                self._expand_instance(d)
        # 自前の GameObject・Transform・コンポーネント
        for k, d in list(self.objs.items()):
            if self.from_prefab.get(k) is not None:
                continue
            if d.cls == "1":
                m, a, l, t = RE_NAME.search(d.text), RE_ACTIVE.search(d.text), RE_LAYER.search(d.text), RE_TAG.search(d.text)
                self.go_fields[k] = dict(name=scalar(m.group(1)) if m else "?", active=(a.group(1) == "1") if a else True,
                                         layer=int(l.group(1)) if l else 0, tag=scalar(t.group(1)) if t else "")
                self.comps_of[k] = [self.A(int(c)) for c in RE_COMP.findall(d.text)]
            else:
                g = RE_GO.search(d.text)
                if g and g.group(1) != "0":
                    self.go_of[k] = self.A(int(g.group(1)))
                if d.cls in TRANSFORM_CLASSES:
                    f = RE_FATHER.search(d.text)
                    self.parent[k] = self.A(int(f.group(1))) if f else 0
                    ch = RE_CHILDREN.search(d.text)
                    self.children[k] = [self.A(int(x)) for x in RE_FID.findall(ch.group(1))] if ch else []
        # プレハブ由来の GameObject に、このファイルで足したコンポーネント（m_GameObject が stripped の GO）
        for k, g in list(self.go_of.items()):
            if self.from_prefab.get(k) is None and g in self.go_fields and k not in self.comps_of.get(g, []):
                self.comps_of[g] = self.comps_of.get(g, []) + [k]
        # このファイルで足した Transform の親がプレハブの中の物なら、その子に足す
        for k, f in list(self.parent.items()):
            if f and f in self.children and k not in self.children[f]:
                self.children[f] = self.children[f] + [k]

    def _instance_data(self, d):
        body = parse_body(d.text)
        mod = body.get("m_Modification") or {}
        return body, mod

    def _expand_instance(self, d):
        pi = int(d.fid)
        body, mod = self._instance_data(d)
        src_ref = body.get("m_SourcePrefab") or {}
        guid = src_ref.get("guid") if isinstance(src_ref, dict) else None
        src_path = self.guids.fs_path(guid) if guid else None
        src_label = self.guids.label(guid) if guid else None
        name = next((m.get("value", "") for m in mod.get("m_Modifications") or [] if isinstance(m, dict) and m.get("propertyPath") == "m_Name"), "")
        if not src_path or not os.path.exists(src_path) or self.depth > 8:
            tp = self._ref_from(mod.get("m_TransformParent"), self.alias, 0)
            self.missing_prefabs.append(dict(pi=pi, guid=guid, name=name, parent=tp))
            return
        pointer = is_lfs_pointer(src_path)
        if pointer:
            self.lfs_pointers.append(dict(label=src_label, name=name))
            if _is_yaml_name(src_path):
                return  # プレハブの中身を読めないので展開しない（Unity でも取り込めていない）
        mods = []
        for m in mod.get("m_Modifications") or []:
            tgt = m.get("target") or {}
            try:
                tfid = int(tgt.get("fileID", "0"))
            except ValueError:
                continue
            mods.append(dict(target=tfid, path=m.get("propertyPath", ""), value=m.get("value", ""),
                             ref=self._ref_from(m.get("objectReference"), self.alias, 0)))
        tparent = self._ref_from(mod.get("m_TransformParent"), self.alias, 0)

        def mapk(q):
            return (q ^ pi) & MASK

        if pointer or not _is_yaml(src_path):
            self._expand_model(d, pi, src_label, mods, tparent)
            return
        sub = self._subs.get(src_path)
        if sub is None:
            sub = Scene(src_path, self.project, self.guids, self.depth + 1, self._subs, self._files)
            self._subs[src_path] = sub
        for mp in sub.missing_prefabs:
            # 入れ子のプレハブの中の Missing Prefab（親は入れ子の中の物なので、どのプレハブの中かだけを残す）
            self.missing_prefabs.append(dict(mp, name=f"{mp['name'] or '(名前の上書き無し)'}（{src_label} の中）", parent=NONE_REF, nested=True))
        for lp in sub.lfs_pointers:
            self.lfs_pointers.append(dict(lp, name=f"{lp['name'] or '(名前の上書き無し)'}（{src_label} の中）", nested=True))
        for q, sd in sub.objs.items():
            k = mapk(q)
            self.objs[k] = sd
            al, x = sub.ctx[q]
            self.ctx[k] = (al, x ^ pi)
            self.from_prefab[k] = sub.from_prefab.get(q) or src_label
        for q, f in sub.go_fields.items():
            self.go_fields[mapk(q)] = dict(f)
        for q, f in sub.parent.items():
            self.parent[mapk(q)] = mapk(f) if f else 0
        for q, ch in sub.children.items():
            self.children[mapk(q)] = [mapk(c) for c in ch]
        for q, g in sub.go_of.items():
            self.go_of[mapk(q)] = mapk(g)
        for q, cs in sub.comps_of.items():
            self.comps_of[mapk(q)] = [mapk(c) for c in cs]
        for q, p in sub.instance_root.items():
            self.instance_root[mapk(q)] = p
        for q, ms in sub.instance_mods.items():
            self.instance_mods[mapk(q)] = ms
        for q, p in sub.instance_pi.items():
            self.instance_pi[mapk(q)] = mapk(p)
        self.removed |= {mapk(q) for q in sub.removed}
        for q, ov in sub.overrides.items():
            dst = self.overrides.setdefault(mapk(q), {})
            for path, (val, ref) in ov.items():
                dst[path] = (val, Ref("local", key=mapk(ref.key)) if ref.kind == "local" else ref)
        rg = sub.root_go()
        rt = sub.root_transform()
        if rg is not None:
            self.instance_root[mapk(rg)] = src_label
            self.instance_mods[mapk(rg)] = mods
            self.instance_pi[mapk(rg)] = pi
        if rt is not None:
            self.parent[mapk(rt)] = tparent.key if tparent.kind == "local" else 0
            self.pi_root_tr[pi] = mapk(rt)
        self._apply_mods(mods, mapk)
        for lst in ("m_RemovedComponents", "m_RemovedGameObjects"):
            for r in mod.get(lst) or []:
                try:
                    self.removed.add(mapk(int(r.get("fileID", "0"))))
                except (AttributeError, ValueError):
                    pass

    def _apply_mods(self, mods, mapk):
        for md in mods:
            tk = mapk(md["target"])
            self.overrides.setdefault(tk, {})[md["path"]] = (md["value"], md["ref"])
            f = self.go_fields.get(tk)
            if f is None:
                continue
            if md["path"] == "m_Name":
                f["name"] = md["value"]
            elif md["path"] == "m_IsActive":
                f["active"] = md["value"].strip() == "1"
            elif md["path"] == "m_Layer":
                try:
                    f["layer"] = int(md["value"] or 0)
                except ValueError:
                    pass
            elif md["path"] == "m_TagString":
                f["tag"] = md["value"]

    def _expand_model(self, d, pi, src_label, mods, tparent):
        """FBX などのモデルのプレハブ。中身は YAML に無いので、ルートと、このファイルで触った物（stripped）だけ作る。

        ルートの fileID は ModelImporter なら固定値。ScriptedImporter（VRM・glTF など）は違う値なので、
        上書きの対象から拾う（シーンに置いたモデルは、ルートの Transform の m_LocalPosition と GameObject の m_Name を必ず上書きする）。"""
        def mapk(q):
            return (q ^ pi) & MASK

        targets = {}
        for md in mods:
            targets.setdefault(md["path"], []).append(md["target"])
        tr_t = targets.get("m_LocalPosition.x", [])
        go_t = targets.get("m_Name", [])
        root_tr = MODEL_ROOT_TR if MODEL_ROOT_TR in tr_t or not tr_t else tr_t[0]
        root_go = MODEL_ROOT_GO if MODEL_ROOT_GO in go_t or not go_t else go_t[0]
        go, tr = mapk(root_go), mapk(root_tr)
        base = os.path.splitext(os.path.basename(src_label or "model"))[0]
        self.go_fields[go] = dict(name=base, active=True, layer=0, tag="")
        for k, cls in ((go, "1"), (tr, "4")):
            self.objs[k] = FakeDoc(k, cls)
            self.ctx[k] = (self.alias, 0)
            self.from_prefab[k] = src_label
        self.comps_of[go] = [tr]
        self.go_of[tr] = go
        self.parent[tr] = tparent.key if tparent.kind == "local" else 0
        self.pi_root_tr[pi] = tr
        self.children.setdefault(tr, [])
        self.instance_root[go] = src_label
        self.instance_mods[go] = mods
        self.instance_pi[go] = pi
        for sd in self.docs:
            if not sd.stripped:
                continue
            m = RE_PI.search(sd.text)
            if not m or int(m.group(1)) != pi:
                continue
            k = self.A(int(sd.fid))
            if k in (go, tr):
                continue
            self.from_prefab[k] = src_label
            self.ctx[k] = (self.alias, 0)
            if sd.cls == "1":
                # モデルの中の GameObject（コンポーネントを足した骨など）。どの Transform の物かは YAML に無いので、
                # 仮の Transform を作ってモデルのルートの子に置く（キャラの中の物として数えられるように）
                self.go_fields.setdefault(k, dict(name=f"(モデルの中の GameObject {k})", active=True, layer=0, tag=""))
                self.objs[k] = FakeDoc(k, "1")
                ftr = k ^ 3
                self.objs[ftr] = FakeDoc(ftr, "4")
                self.ctx[ftr] = (self.alias, 0)
                self.from_prefab[ftr] = src_label
                self.parent[ftr] = tr
                self.children.setdefault(ftr, [])
                self.children[tr].append(ftr)
                self.go_of[ftr] = k
                self.comps_of[k] = [ftr] + [c for c in self.comps_of.get(k, []) if c != ftr]
            elif sd.cls in TRANSFORM_CLASSES:
                # モデルの中の Transform（骨など）。親子は YAML に無いので、モデルのルートの子として扱う
                self.objs[k] = FakeDoc(k, "4")
                self.parent[k] = tr
                self.children.setdefault(k, [])
                self.children[tr].append(k)
                gk = k ^ 1
                self.go_fields[gk] = dict(name=f"(モデルの中の物 {k})", active=True, layer=0, tag="")
                self.objs[gk] = FakeDoc(gk, "1")
                self.ctx[gk] = (self.alias, 0)
                self.comps_of[gk] = [k]
                self.go_of[k] = gk
        self._apply_mods(mods, mapk)

    # ------------------------------------------------------------------ 読む

    def root_transform(self):
        for k, f in self.parent.items():
            if not f and self.go_of.get(k) is not None and k not in self.removed:
                d = self.objs.get(k)
                if d is not None and d.cls in TRANSFORM_CLASSES:
                    return k
        return None

    def root_go(self):
        t = self.root_transform()
        return self.go_of.get(t) if t is not None else None

    def roots(self):
        """シーンのルート Transform（SceneRoots の順。無ければ親の無い Transform）。"""
        order = []
        for d in self.docs:
            if d.cls == "1660057539":
                m = RE_ROOTS.search(d.text)
                if m:
                    for x in RE_FID.findall(m.group(1)):
                        x = int(x)
                        if x in self.by and self.by[x].cls == "1001":
                            x = self.pi_root_tr.get(x, x)
                        order.append(self.A(x))
        seen = set(order)
        for k, f in self.parent.items():
            if not f and k not in seen and self.go_of.get(k) is not None and k not in self.removed:
                order.append(k)
        return [k for k in order if k in self.objs]

    def transform_of_go(self, gk):
        for c in self.comps_of.get(gk, []):
            d = self.objs.get(c)
            if d is not None and d.cls in TRANSFORM_CLASSES:
                return c
        return None

    def parent_go(self, gk):
        t = self.transform_of_go(gk)
        if t is None:
            return None
        p = self.parent.get(t, 0)
        return self.go_of.get(p) if p else None

    def child_gos(self, gk):
        t = self.transform_of_go(gk)
        out = []
        for c in self.children.get(t, []) if t is not None else []:
            g = self.go_of.get(c)
            if g is not None and c not in self.removed and g not in self.removed:
                out.append(g)
        return out

    def descendants(self, gk):
        stack = [gk]
        while stack:
            g = stack.pop()
            yield g
            stack.extend(reversed(self.child_gos(g)))

    def ancestors(self, gk):
        """自分を含めて上へ。"""
        seen = set()
        cur = gk
        while cur is not None and cur not in seen:
            seen.add(cur)
            yield cur
            cur = self.parent_go(cur)

    def go_name(self, gk):
        return self.go_fields.get(gk, {}).get("name", "?")

    def go_path(self, gk):
        return "/".join(reversed([self.go_name(g) for g in self.ancestors(gk)]))

    def active_in_hierarchy(self, gk):
        return all(self.go_fields.get(g, {}).get("active", True) for g in self.ancestors(gk))

    def is_removed(self, k):
        if k in self.removed:
            return True
        g = self.go_of.get(k, k)
        return any(a in self.removed for a in self.ancestors(g)) if g in self.go_fields else False

    def label(self, k):
        """コンポーネントの名前（MonoBehaviour はスクリプトのクラス名）。"""
        if k in self._label_cache:
            return self._label_cache[k]
        d = self.objs.get(k)
        if d is None:
            lab = "?"
        elif d.cls == "114":
            lab = mono_label(d.text, self.guids)
        else:
            lab = CLASS_NAMES.get(d.cls, "class" + d.cls)
        self._label_cache[k] = lab
        return lab

    def components(self, gk):
        """GameObject のコンポーネントの key（Transform を除く・消した物を除く）。"""
        out = []
        for c in self.comps_of.get(gk, []):
            d = self.objs.get(c)
            if d is None or c in self.removed or d.cls in TRANSFORM_CLASSES:
                continue
            out.append(c)
        return out

    def all_components(self):
        """(key, label) の全部（消した物・GameObject の無い物を除く）。"""
        out = []
        for gk in self.go_fields:
            # m_RemovedGameObjects で消した GameObject とその子孫は数えない
            if self.removed and any(a in self.removed for a in self.ancestors(gk)):
                continue
            for c in self.components(gk):
                out.append((c, self.label(c)))
        return out

    def body(self, k):
        """上書きを当てた後の塊の中身（dict、値は文字列、参照は Ref）。"""
        if k in self._body_cache:
            return self._body_cache[k]
        d = self.objs.get(k)
        data = parse_body(d.text) if d is not None and d.text else {}
        alias, xor = self.ctx.get(k, (self.alias, 0))

        def conv(v):
            if isinstance(v, dict):
                if "fileID" in v and len(v) <= 3 and set(v) <= {"fileID", "guid", "type"}:
                    return self._ref_from(v, alias, xor)
                return {kk: conv(vv) for kk, vv in v.items()}
            if isinstance(v, list):
                return [conv(x) for x in v]
            return v
        data = conv(data)
        ov = self.overrides.get(k)
        if ov:
            items = sorted(ov.items(), key=lambda it: (0 if it[0].endswith(".Array.size") else 1, it[0].count(".")))
            for path, (val, ref) in items:
                cur = _get_path(data, path.replace(".Array.data[", ".").replace("]", "")) if "Array.data" in path else _get_path(data, path)
                use_ref = ref.kind != "none" or isinstance(cur, Ref)
                _set_path(data, path, ref if use_ref else val)
        self._body_cache[k] = data
        return data

    def get(self, k, path, default=None):
        """body の中のドット区切りのパス（配列は数字）。"""
        v = _get_path(self.body(k), path)
        return default if v is None else v

    def val(self, k, key):
        """トップレベルの 1 行の値だけを速く読む（YAML を全部読まない。上書きがあればそれ）。"""
        ov = self.overrides.get(k)
        if ov and key in ov:
            return ov[key][0]
        d = self.objs.get(k)
        if d is None or not d.text:
            return None
        m = re.search(r"(?m)^  " + re.escape(key) + r": ?(.*?)\r?$", d.text)
        return scalar(m.group(1)) if m else None

    def enabled(self, k):
        v = self.get(k, "m_Enabled")
        return v is None or str(v) == "1"

    def comp_active(self, k):
        """GameObject が activeInHierarchy で、コンポーネントが有効。"""
        g = self.go_of.get(k)
        return g is not None and self.active_in_hierarchy(g) and self.enabled(k)

    def describe(self, ref_or_key):
        """参照を「GO のパス (コンポーネント)」や「アセットのパス」の文字列に。"""
        r = ref_or_key if isinstance(ref_or_key, Ref) else Ref("local", key=ref_or_key)
        if r.kind == "none":
            return "None"
        if r.kind == "asset":
            return self.guids.short(r.guid) if r.guid else "?"
        d = self.objs.get(r.key)
        if d is None:
            return f"(切れた参照 {r.key})"
        if d.cls == "1":
            return self.go_path(r.key)
        g = self.go_of.get(r.key)
        if g is not None:
            lab = self.label(r.key)
            return self.go_path(g) + ("" if lab in ("Transform", "RectTransform") else f" ({lab})")
        return f"{CLASS_NAMES.get(d.cls, d.cls)}"

    def ref_go(self, r):
        """参照の先の GameObject の key（GO ならそのもの、コンポーネントならその GO）。"""
        if not isinstance(r, Ref) or r.kind != "local":
            return None
        d = self.objs.get(r.key)
        if d is None:
            return None
        return r.key if d.cls == "1" else self.go_of.get(r.key)

    def by_label(self):
        out = {}
        for k, lab in self.all_components():
            out.setdefault(lab, []).append(k)
        return out


def open_scene(path, quiet=False, project=None):
    """project を渡すと、シーンがプロジェクトの外にあっても（git から取り出した版など）そのプロジェクトの GUID で読む。"""
    proj = Project(project) if project else Project.find(path)
    return Scene(path, proj, GuidMap(proj, quiet=quiet))
