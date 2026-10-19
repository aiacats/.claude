# Unity のテキストシリアライズ（.unity / .prefab / .asset / .playable）を「--- !u!<class> &<fileID>」の塊に分ける共通部品。
# 塊の本文は見出し行を含み、改行コードはファイルのまま（newline="" で読み書きする）。
import re
import subprocess

HEADER = re.compile(r"^--- !u!(\d+) &(-?\d+)( stripped)?[ \t]*\r?\n?$")
LOCAL_REF = re.compile(r"\{fileID: (-?\d+)\}")  # guid の無い参照 = 同じファイルの塊
NAME = re.compile(r"(?m)^  m_Name: (.*?)\r?$")
GAMEOBJECT = re.compile(r"(?m)^  m_GameObject: \{fileID: (-?\d+)\}")
FATHER = re.compile(r"(?m)^  m_Father: \{fileID: (-?\d+)\}")
PREFAB_INSTANCE = re.compile(r"(?m)^  m_PrefabInstance: \{fileID: (-?\d+)\}")
SCRIPT_GUID = re.compile(r"(?m)^  m_Script: \{fileID: -?\d+, guid: ([0-9a-f]{32})")

# よく出るクラス ID（https://docs.unity3d.com/Manual/ClassIDReference.html）
CLASS_NAMES = {
    "1": "GameObject", "4": "Transform", "20": "Camera", "21": "Material", "23": "MeshRenderer", "28": "Texture2D",
    "33": "MeshFilter", "43": "Mesh", "54": "Rigidbody", "64": "MeshCollider", "65": "BoxCollider", "82": "AudioSource",
    "84": "RenderTexture", "95": "Animator", "108": "Light", "114": "MonoBehaviour", "120": "LineRenderer",
    "137": "SkinnedMeshRenderer", "198": "ParticleSystem", "199": "ParticleSystemRenderer", "212": "SpriteRenderer",
    "222": "CanvasRenderer", "223": "Canvas", "224": "RectTransform", "320": "PlayableDirector", "1001": "PrefabInstance",
    "29": "OcclusionCullingSettings", "104": "RenderSettings", "157": "LightmapSettings", "196": "NavMeshSettings",
    "1660057539": "SceneRoots",
}
TRANSFORM_CLASSES = ("4", "224")


class Doc:
    __slots__ = ("fid", "cls", "stripped", "text")

    def __init__(self, fid, cls, stripped, text):
        self.fid, self.cls, self.stripped, self.text = fid, cls, stripped, text

    @property
    def class_name(self):
        return CLASS_NAMES.get(self.cls, "class " + self.cls)


def parse(text):
    """(前置き, [Doc]) を返す。"""
    pre, docs, cur = [], [], None
    for line in text.splitlines(keepends=True):
        m = HEADER.match(line)
        if m:
            if cur:
                docs.append(cur)
            cur = [m.group(2), m.group(1), bool(m.group(3)), [line]]
        elif cur:
            cur[3].append(line)
        else:
            pre.append(line)
    if cur:
        docs.append(cur)
    return "".join(pre), [Doc(d[0], d[1], d[2], "".join(d[3])) for d in docs]


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        return parse(f.read())


def write(path, pre, docs):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(pre)
        for d in docs:
            f.write(d.text)


def from_git(rev, path, cwd=None):
    """git の rev の版を返す（LFS のポインタなら実体へ戻す）。"""
    raw = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=cwd, capture_output=True, check=True).stdout
    if raw.startswith(b"version https://git-lfs.github.com/spec/"):
        raw = subprocess.run(["git", "lfs", "smudge"], cwd=cwd, input=raw, capture_output=True, check=True).stdout
    return raw.decode("utf-8")


def local_refs(text):
    return {r for r in LOCAL_REF.findall(text) if r != "0"}


class Index:
    """fileID → 塊と、名前・ヒエラルキーパスの解決。"""

    def __init__(self, docs, script_names=None):
        self.docs = docs
        self.by = {d.fid: d for d in docs}
        self.script_names = script_names or {}

    def go_name(self, fid):
        d = self.by.get(fid)
        if d is None:
            return "?"
        m = NAME.search(d.text)
        return m.group(1) if m else "?"

    def owner_go(self, d):
        m = GAMEOBJECT.search(d.text)
        return m.group(1) if m else None

    def transform_of(self, go_fid):
        for d in self.docs:
            if d.cls in TRANSFORM_CLASSES and self.owner_go(d) == go_fid:
                return d
        return None

    def path(self, go_fid, limit=12):
        """GameObject のヒエラルキーパス（親を Transform の m_Father でたどる）。"""
        names, cur = [], go_fid
        for _ in range(limit):
            names.append(self.go_name(cur))
            tr = self.transform_of(cur)
            if tr is None:
                break
            father = FATHER.search(tr.text)
            if not father or father.group(1) == "0" or father.group(1) not in self.by:
                break
            cur = self.owner_go(self.by[father.group(1)])
            if cur is None:
                break
        return "/".join(reversed(names))

    def describe(self, d, with_path=True):
        """「クラス 名前 @ パス」の短い説明。"""
        label = d.class_name
        if d.cls == "114":
            g = SCRIPT_GUID.search(d.text)
            if g and g.group(1) in self.script_names:
                label = self.script_names[g.group(1)]
        if d.stripped:
            # プレハブのインスタンスの中の物。名前は持たないので、どのインスタンスの物かを出す
            pi = PREFAB_INSTANCE.search(d.text)
            return label + " (stripped)", f"in PrefabInstance {pi.group(1) if pi else '?'}"
        if d.cls == "1":
            where = self.path(d.fid) if with_path else self.go_name(d.fid)
        else:
            go = self.owner_go(d)
            if go:
                where = self.path(go) if with_path else self.go_name(go)
            else:
                m = NAME.search(d.text)
                where = m.group(1) if m else ""
        return label, where


def script_names(assets_dir):
    """Assets（と Packages）以下の .cs.meta から guid → スクリプト名。"""
    import os
    out = {}
    for root in assets_dir:
        for dp, _, files in os.walk(root):
            for f in files:
                if f.endswith(".cs.meta"):
                    try:
                        with open(os.path.join(dp, f), encoding="utf-8", errors="ignore") as fh:
                            for line in fh:
                                if line.startswith("guid:"):
                                    out[line.split()[1]] = f[:-8]
                                    break
                    except OSError:
                        pass
    return out
