"""vortex 系 Unity プロジェクトの設定を読み出す・比べる・点検する（Unity は起動しない。ファイルを読むだけ）。

使い方:
  python project_audit.py snapshot <Unity プロジェクト | git ルート> [-o <json>]
  python project_audit.py compare  <A> <B> [--json]        A・B はプロジェクトか snapshot の json
  python project_audit.py check    <Unity プロジェクト | git ルート> [--json] [--no-scan]

- snapshot: 設定の要点を JSON にする。templates/Editor/ProjectSetupApply.cs が同じ形を読んで当てる。
- compare : 違う所を「vortex で揃える / 取り込み物しだい / 案件ごと」に分けて出す。分け方は CATEGORY_RULES。
- check   : 基準が無くても分かる問題を出す（ERROR = ビルドや動作が壊れる / WARN = 罠の元 / INFO = 気付き）。
            --no-scan はファイル全体を読む点検（define の使われ方・DLL・大きいファイル）を飛ばす。
            ERROR があれば終了コード 1。

読み方の前提:
- Unity の YAML は unity-scene-merge の unity_yaml.parse で塊に分け、各塊を PyYAML の BaseLoader（値は全部文字列）で読む。
  m_APIs: 0200000012000000 のような値を数値に化けさせないため。
- GUID → パスは、Assets・Packages の埋め込み・file: 参照の先・Library/PackageCache（packages-lock.json に載っている版だけ）の .meta から引く。
  Unity が読まないフォルダ（名前が . で始まる・~ で終わる）は見ない。
"""
import argparse
import collections
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8")

_MERGE_SCRIPTS = Path(__file__).resolve().parents[2] / "unity-scene-merge" / "scripts"
if not (_MERGE_SCRIPTS / "unity_yaml.py").exists():
    sys.exit(f"unity_yaml.py が見つからない: {_MERGE_SCRIPTS}（skill unity-scene-merge の scripts を使う）")
sys.path.insert(0, str(_MERGE_SCRIPTS))
import unity_yaml  # noqa: E402

import yaml  # noqa: E402

SCHEMA = 1
LOADER = getattr(yaml, "CBaseLoader", yaml.BaseLoader)

# ---- 列挙値 ---------------------------------------------------------------------------------------
# Unity 6000.3.5f2 の UnityEngine.CoreModule.dll / UnityEditor.CoreModule.dll を参照してコンパイルした小さなプログラムで
# 値を出して確かめた（2026-10-19。GraphicsDeviceType・ColorSpace・FullScreenMode・ApiCompatibilityLevel・ScriptingImplementation・
# EnterPlayModeOptions・BuildTargetGroup）。ここに無い値は "unknown(N)" と出す。
GRAPHICS_DEVICE = {2: "Direct3D11", 4: "Null", 11: "OpenGLES3", 16: "Metal", 17: "OpenGLCore", 18: "Direct3D12", 21: "Vulkan", 28: "WebGPU"}
COLOR_SPACE = {0: "Gamma", 1: "Linear"}
FULLSCREEN_MODE = {0: "ExclusiveFullScreen", 1: "FullScreenWindow", 2: "MaximizedWindow", 3: "Windowed"}
API_COMPAT = {3: "NET_Unity_4_8", 6: "NET_Standard"}  # 6 は Player Settings の表示で .NET Standard 2.1
SCRIPTING_BACKEND = {0: "Mono2x", 1: "IL2CPP"}
ENTER_PLAY_MODE_FLAGS = {1: "DisableDomainReload", 2: "DisableSceneReload", 4: "DisableSceneBackupUnlessDirty"}
# com.unity.inputsystem の EditorPlayerSettingHelpers.InputHandler（OldInputManager = 0 / NewInputSystem = 1 / InputBoth = 2）
INPUT_HANDLER = {0: "InputManager", 1: "InputSystem", 2: "Both"}
# URP 17.3 の UniversalRenderer.cs / IntermediateTextureMode.cs
URP_RENDERING_MODE = {0: "Forward", 1: "Deferred", 2: "ForwardPlus", 3: "DeferredPlus"}
URP_DEPTH_PRIMING = {0: "Disabled", 1: "Auto", 2: "Forced"}
URP_INTERMEDIATE = {0: "Auto", 1: "Always"}
# BuildTargetGroup の数値（古い ProjectSettings は define を数値のキーで持つ）
BUILD_TARGET_GROUP = {"1": "Standalone", "7": "Android", "4": "iPhone", "13": "WebGL"}

# git の版の指定（# の後ろ）が「固定」かどうか。コミットのハッシュ（7〜40 桁の 16 進）とタグらしい版番号だけを固定とみなす。
# master・main・upm・develop のような名前はブランチで、取り込み直すたびに中身が変わる。
PINNED_REV = re.compile(r"^(?:[0-9a-f]{7,40}|v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.\-]+)?)$")

# GitHub の制限（https://docs.github.com/repositories/working-with-files/managing-large-files/about-large-files-on-github）:
# 50 MiB を超えると警告、100 MiB を超えると push を断る。LFS に入っていないファイルにだけ当てはまる。
GITHUB_WARN_BYTES = 50 * 1024 * 1024
GITHUB_BLOCK_BYTES = 100 * 1024 * 1024

URP_ASSET_KEYS = [
    "m_DefaultRendererIndex", "m_RequireDepthTexture", "m_RequireOpaqueTexture", "m_OpaqueDownsampling", "m_SupportsHDR",
    "m_HDRColorBufferPrecision", "m_MSAA", "m_RenderScale", "m_UpscalingFilter", "m_MainLightRenderingMode",
    "m_MainLightShadowsSupported", "m_MainLightShadowmapResolution", "m_AdditionalLightsRenderingMode",
    "m_AdditionalLightsPerObjectLimit", "m_AdditionalLightShadowsSupported", "m_ShadowDistance", "m_ShadowCascadeCount",
    "m_SoftShadowsSupported", "m_UseSRPBatcher", "m_SupportsDynamicBatching", "m_SupportsLightLayers", "m_ColorGradingMode",
    "m_ColorGradingLutSize", "m_GPUResidentDrawerMode", "m_StoreActionsOptimization", "m_ReflectionProbeBlending",
    "m_ReflectionProbeBoxProjection",
]
URP_GLOBAL_KEYS = ["m_StripDebugVariants", "m_StripUnusedPostProcessingVariants", "m_StripUnusedVariants", "m_StripScreenCoordOverrideVariants"]
DEFINE_SOURCE_EXT = (".cs", ".shader", ".hlsl", ".cginc", ".compute", ".asmdef", ".asmref", ".rsp")
# 旧 Input の代表的な呼び出し（UnityEngine.Input のメンバー）。InputSystem の Keyboard.current などには当たらない
# Editor にしか無い型・属性の使い方（`using UnityEditor;` だけなら Player でも通る。Crest などが Runtime に UnityEditor の名前空間を作っているため）
EDITOR_API = re.compile(
    r"\bEditorWindow\b|\bScriptableWizard\b|:\s*(?:UnityEditor\.)?Editor\b|\[\s*(?:UnityEditor\.)?(?:CustomEditor|MenuItem|InitializeOnLoad|InitializeOnLoadMethod|"
    r"CustomPropertyDrawer|CanEditMultipleObjects|DidReloadScripts)\b|"
    r"\b(?:AssetDatabase|EditorUtility|EditorGUILayout|EditorGUI|EditorGUIUtility|EditorApplication|EditorPrefs|EditorSceneManager|PrefabUtility|"
    r"Undo|Handles|SceneView|EditorStyles|BuildPipeline|AssetImporter|ModelImporter|TextureImporter)\s*\.|"
    r"\b(?:SerializedObject|SerializedProperty|DefaultAsset|PropertyDrawer|MonoScript)\b|"
    r"\bUnityEditor\.\w")
PP_LINE = re.compile(r"^\s*#\s*(if|elif|else|endif)\b(.*)$")
STRING_LIT = re.compile(r'@"(?:""|[^"])*"|\$?"(?:\\.|[^"\\])*"')


# Unity が場合によって定義するシンボルの頭（これで始まる 1 語の #if は、有効かもしれないので中も見る）
BUILTIN_DEFINE_PREFIXES = ("UNITY_", "ENABLE_", "PLATFORM_", "NET_", "NETSTANDARD", "CSHARP_", "DEVELOPMENT_BUILD", "DEBUG", "TRACE", "CINEMACHINE", "USING_")


def unguarded_editor_api(text, defines=()):
    """#if UNITY_EDITOR（と !UNITY_EDITOR の #else 側）の外で、Editor にしか無い型を使っている最初の行番号。無ければ None。
    using / namespace の行・コメント・文字列は見ない。条件の式は UNITY_EDITOR を含むかだけで見る（肯定で含めば囲まれているとみなす）。"""
    defined = set(defines)
    stack = []  # 各段: editor = その枝の中が Editor だけで有効か / off = その枝はコンパイルされない（定義の無いシンボル 1 つの #if）
    in_block_comment = False
    for no, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):  # 先頭の BOM があると 1 行目の #if を見落とす
        line = raw
        if in_block_comment:
            if "*/" not in line:
                continue
            line = line.split("*/", 1)[1]
            in_block_comment = False
        line = re.sub(r"/\*.*?\*/", "", line)
        if "/*" in line:
            line, in_block_comment = line.split("/*", 1)[0], True
        line = STRING_LIT.sub('""', line.split("//", 1)[0] if '"' not in line else line)
        line = line.split("//", 1)[0]
        m = PP_LINE.match(line)
        if m:
            kw, cond = m.group(1), m.group(2)
            neg = bool(re.search(r"!\s*UNITY_EDITOR", cond))
            pos = "UNITY_EDITOR" in cond and not neg
            one = re.fullmatch(r"\s*\(?\s*([A-Za-z_]\w*)\s*\)?\s*", cond)
            undefined = bool(one) and one.group(1) not in defined and not one.group(1).startswith(BUILTIN_DEFINE_PREFIXES)
            if kw == "if":
                stack.append({"editor": pos, "neg": neg, "off": undefined, "undef_if": undefined})
            elif kw == "elif" and stack:
                stack[-1]["editor"] = pos
                stack[-1]["off"] = undefined
            elif kw == "else" and stack:
                stack[-1]["editor"] = stack[-1]["neg"]
                stack[-1]["off"] = False  # 定義の無いシンボルの #if の #else 側はコンパイルされる
            elif kw == "endif" and stack:
                stack.pop()
            continue
        if re.match(r"\s*(?:using|namespace)\b", line):
            continue
        if EDITOR_API.search(line) and not any(f["editor"] or f["off"] for f in stack):
            return no
    return None


def compile_target(path, cache):
    """path の .cs がどこへコンパイルされるか。"editor" = Editor 専用の asmdef / "player" = Player にも入る / "none" = コンパイルされない
    （パッケージの中で asmdef にも asmref にも入っていない .cs。Unity はパッケージの asmdef の外のスクリプトを読まない）。"""
    for d in path.parents:
        key = os.path.normcase(str(d))
        if key in cache:
            return cache[key]
        if d.is_dir():
            defs = list(d.glob("*.asmdef"))
            if defs:
                try:
                    plats = json.loads(defs[0].read_text(encoding="utf-8-sig")).get("includePlatforms") or []
                except (OSError, json.JSONDecodeError):
                    plats = []
                cache[key] = "editor" if plats == ["Editor"] else "player"
                return cache[key]
            if list(d.glob("*.asmref")):
                cache[key] = "player"  # 参照先の asmdef までは追わない（Player にも入るとみなす）
                return cache[key]
        if (d / "package.json").exists():
            cache[key] = "none"
            return "none"
        if d.name == "Assets":
            cache[key] = "player"  # Assembly-CSharp
            return "player"
    return "player"


LEGACY_INPUT = re.compile(r"(?<![\w.])(?:UnityEngine\.)?Input\.(?:GetKey|GetKeyDown|GetKeyUp|GetAxis|GetAxisRaw|GetButton|GetButtonDown|"
                          r"GetButtonUp|GetMouseButton|GetMouseButtonDown|GetMouseButtonUp|mousePosition|mouseScrollDelta|anyKey|"
                          r"anyKeyDown|inputString|touchCount|GetTouch)\b")
GITATTR_SAMPLES = ["x.unity", "x.prefab", "x.asset", "x.mat", "x.meta", "x.anim", "x.controller", "x.playable", "x.cs",
                   "x.fbx", "x.vrm", "x.png", "x.psd", "x.wav", "x.mp4", "x.dll", "x.dmx", "x.sh"]


# ---- 読み込みの部品 --------------------------------------------------------------------------------
class ReadError(Exception):
    pass


def read_text(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"version https://git-lfs.github.com/spec/"):
        raise ReadError(f"LFS のポインタのまま（git lfs pull が要る）: {path}")
    return raw.decode("utf-8", errors="replace")


def load_docs(path):
    """Unity の YAML を [(class id, fileID, dict)] にする。"""
    _, docs = unity_yaml.parse(read_text(path))
    out = []
    for d in docs:
        body = d.text.split("\n", 1)[1] if "\n" in d.text else ""
        try:
            data = yaml.load(body, Loader=LOADER) or {}
        except yaml.YAMLError as e:
            raise ReadError(f"YAML を読めない: {path} の &{d.fid}: {e}") from e
        out.append((d.cls, d.fid, data))
    return out


def main_body(path):
    """設定ファイル（塊が 1 つ）の中身の dict。"""
    docs = load_docs(path)
    if not docs:
        raise ReadError(f"中身が無い: {path}")
    data = docs[0][2]
    return next(iter(data.values())) if isinstance(data, dict) and len(data) == 1 else data


def as_int(v, default=None):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def as_bool(v):
    i = as_int(v)
    return None if i is None else bool(i)


def label(table, v):
    i = as_int(v)
    return table.get(i, f"unknown({v})") if i is not None else None


def ref_guid(v):
    if isinstance(v, dict):
        g = v.get("guid")
        if g and g != "0" * 32 and as_int(v.get("fileID"), 0) != 0:
            return g
    return None


def run_git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    return r.stdout if r.returncode == 0 else None


# ---- プロジェクトの場所 ----------------------------------------------------------------------------
def find_unity_root(p):
    p = Path(p).resolve()
    if (p / "ProjectSettings" / "ProjectVersion.txt").exists():
        return p
    found = [c for c in sorted(p.iterdir()) if c.is_dir() and (c / "ProjectSettings" / "ProjectVersion.txt").exists()]
    if len(found) == 1:
        return found[0]
    if not found:
        sys.exit(f"Unity プロジェクトが見つからない（ProjectSettings/ProjectVersion.txt が無い）: {p}")
    sys.exit("Unity プロジェクトが複数ある。どれかを直接指定する: " + ", ".join(str(f) for f in found))


def find_git_root(p):
    for c in [p, *p.parents]:
        if (c / ".git").exists():
            return c
    return None


class Project:
    def __init__(self, path):
        self._pkg_dirs = None
        self.root = find_unity_root(path)
        self.git_root = find_git_root(self.root)
        self.ps = self.root / "ProjectSettings"
        self.errors = []  # 読めなかったもの（snapshot に残す）
        self.manifest = self._json(self.root / "Packages" / "manifest.json")
        self.lock = self._json(self.root / "Packages" / "packages-lock.json")
        self._index = None

    def _json(self, path):
        if not path.exists():
            self.errors.append(f"無い: {self.rel(path)}")
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.errors.append(f"JSON を読めない: {self.rel(path)}: {e}")
            return {}

    def rel(self, path):
        """Unity から見たパス（Assets/... か Packages/<パッケージ名>/...）。どちらでもなければ git ルートからのパス。"""
        path = Path(path).resolve()
        for _kind, name, d in self._pkg_dirs or []:
            try:
                rest = path.relative_to(d).as_posix()
                return "Packages/" + name + ("" if rest == "." else "/" + rest)
            except ValueError:
                pass
        for base in (self.root, self.git_root):
            if base:
                try:
                    return path.relative_to(base).as_posix()
                except ValueError:
                    pass
        return path.as_posix()

    def settings(self, name):
        try:
            return main_body(self.ps / name)
        except (ReadError, OSError) as e:
            self.errors.append(str(e))
            return {}

    # file: 参照・埋め込み・PackageCache の、Unity が今読んでいる場所（同じフォルダは 1 回だけ）
    def package_dirs(self):
        if self._pkg_dirs is None:
            self._pkg_dirs = self._find_package_dirs()
        return self._pkg_dirs

    def _find_package_dirs(self):
        out, seen = [], set()  # (kind, name, dir)

        def add(kind, name, d):
            key = os.path.normcase(str(d))
            if key not in seen:
                seen.add(key)
                out.append((kind, name, d))

        pk = self.root / "Packages"
        if pk.is_dir():
            for d in sorted(pk.iterdir()):
                if d.is_dir() and (d / "package.json").exists():
                    try:
                        name = json.loads((d / "package.json").read_text(encoding="utf-8-sig")).get("name") or d.name
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        name = d.name
                    add("embedded", name, d.resolve())
        for name, spec in (self.manifest.get("dependencies") or {}).items():
            if isinstance(spec, str) and spec.startswith("file:"):
                d = (pk / spec[5:]).resolve()
                if d.is_dir():
                    add("file", name, d)
        cache = self.root / "Library" / "PackageCache"
        if cache.is_dir():
            lock = self.lock.get("dependencies") or {}
            by_name = collections.defaultdict(list)
            for d in cache.iterdir():
                if d.is_dir():
                    by_name[d.name.split("@")[0]].append(d)
            for name, dirs in by_name.items():
                info = lock.get(name)
                if not info or info.get("source") in ("embedded", "local"):
                    continue
                pick = None
                for d in dirs:
                    if "@" in d.name and info.get("hash") and info["hash"].startswith(d.name.split("@", 1)[1]):
                        pick = d
                    elif len(dirs) == 1 or self._pkg_version(d) == info.get("version"):
                        pick = pick or d
                if pick:
                    add("cache", name, pick)
        return out

    @staticmethod
    def _pkg_version(d):
        try:
            return json.loads((d / "package.json").read_text(encoding="utf-8-sig")).get("version")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def roots(self):
        out = [("assets", "Assets", self.root / "Assets")]
        out += self.package_dirs()
        return out

    def index(self):
        if self._index is None:
            self._index = FileIndex(self)
        return self._index


ROOT_ORDER = ("assets", "embedded", "file", "cache")
# 読み込みはスレッドで重ねる（ThreadPoolExecutor の既定の本数）。ただし 2026-10-19 の実測では、初めて開く .cs は
# 32 本で重ねても 1 本 4.8 ms のままでほとんど縮まなかった（待ちの元はディスクの外。ウイルス対策の検査の疑い、未確認）。
# 効くのは 2 回目以降のキャッシュに載った読み込み。読む本数そのものを減らすのが本筋なので、lookup は拡張子で絞る


def _read_head(p):
    try:
        with open(p, "rb") as fh:
            return fh.read(4096)
    except OSError:
        return None


class FileIndex:
    """ファイルの名前だけを 1 回で集め、中身は要る物だけ読む（初めて開くファイルが遅い環境があるため）。

    GUID → パスは lookup のたびに、拡張子が合う .meta を Assets → 埋め込み → file: → PackageCache の順に読んで探す。
    """

    def __init__(self, proj):
        t = time.time()
        self.proj = proj
        self.metas = collections.defaultdict(list)  # kind -> [.meta]
        self.asmdef_files, self.dlls, self.sources, self.avpro = [], [], [], []
        for kind, _name, root in proj.roots():
            if not root.is_dir():
                continue
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if not d.startswith(".") and not d.endswith("~")]
                if kind != "cache":
                    self.avpro += [(kind, Path(dp) / d) for d in dns if d.lower().startswith("avpro")]
                for f in fns:
                    low = f.lower()
                    if low.endswith(".meta"):
                        self.metas[kind].append(os.path.join(dp, f))
                    elif low.endswith(".asmdef"):
                        self.asmdef_files.append(Path(dp) / f)
                    elif low.endswith(".dll") and kind != "cache":
                        self.dlls.append((kind, Path(dp) / f))
                        if low.startswith("avpro"):
                            self.avpro.append((kind, Path(dp) / f))
                    if low.endswith(DEFINE_SOURCE_EXT):
                        self.sources.append((kind, Path(dp) / f))
        self.guid = {}  # guid -> 実体のパス（.meta を外したもの）。読んだ .meta の分だけ
        self.guid_all = collections.defaultdict(list)  # 重なりを見るため、読んだ .meta を全部
        self.exec_order = {}
        self._read = set()
        self.walk_seconds = round(time.time() - t, 2)
        self.read_seconds = 0.0

    def _ingest(self, paths, kind):
        paths = [p for p in paths if p not in self._read]
        if not paths:
            return
        t = time.time()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor() as ex:
            heads = list(ex.map(_read_head, paths))
        for p, head in zip(paths, heads):
            self._read.add(p)
            if not head:
                continue
            m = re.search(rb"(?m)^guid: ([0-9a-f]{32})", head)
            if not m:
                continue
            g = m.group(1).decode()
            target = Path(p[:-5])
            self.guid_all[g].append(target)
            self.guid.setdefault(g, target)
            if kind != "cache" and p.endswith(".cs.meta"):
                e = re.search(rb"(?m)^  executionOrder: (-?\d+)", head)
                if e and int(e.group(1)) != 0:
                    self.exec_order[target.name] = int(e.group(1))
        self.read_seconds += time.time() - t

    def read_all(self, kinds, suffix=".meta"):
        for kind in kinds:
            self._ingest([p for p in self.metas[kind] if p.endswith(suffix)], kind)

    def lookup(self, guid, exts):
        """guid の実体のパス（無ければ None）。exts は実体の拡張子（".cs" など）で、読む .meta を絞る。"""
        if not guid:
            return None
        if guid in self.guid:
            return self.guid[guid]
        suffixes = tuple(e + ".meta" for e in exts)
        # 見つかった場所より後ろ（PackageCache など）は読まない。読んだ .meta は覚えておき、次の lookup では読み直さない
        for kind in ROOT_ORDER:
            self._ingest([p for p in self.metas[kind] if p.endswith(suffixes)], kind)
            if guid in self.guid:
                return self.guid[guid]
        return None

    def path_of(self, guid, exts):
        p = self.lookup(guid, exts)
        return self.proj.rel(p) if p else None

    def guid_dups(self):
        """読んだ .meta のうち、同じ GUID を持つ別のファイル（Assets・埋め込み・file: は read_all で全部読んでから呼ぶ）。"""
        return {g: ps for g, ps in self.guid_all.items() if len(set(ps)) > 1}

    def asmdefs(self):
        out = collections.defaultdict(list)
        for p in self.asmdef_files:
            try:
                name = json.loads(p.read_text(encoding="utf-8-sig")).get("name")
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if name:
                out[name].append(p)
        return out


def script_exts(ref):
    """m_Script の参照の先の拡張子。fileID 11500000 は .cs の MonoScript、それ以外は DLL の中の型。"""
    return (".cs",) if isinstance(ref, dict) and str(ref.get("fileID")) == "11500000" else (".dll",)


# ---- snapshot -------------------------------------------------------------------------------------
def git_ref_info(spec):
    if not isinstance(spec, str):
        return None
    if not (spec.startswith(("https://", "http://", "git@", "git+", "ssh://")) or spec.endswith(".git") or ".git?" in spec or ".git#" in spec):
        return None
    rev = spec.split("#", 1)[1] if "#" in spec else None
    return {"rev": rev, "pinned": bool(rev and PINNED_REV.match(rev))}


def snap_packages(proj):
    deps = {}
    lock = proj.lock.get("dependencies") or {}
    for name, spec in (proj.manifest.get("dependencies") or {}).items():
        e = {"spec": spec}
        g = git_ref_info(spec)
        if g:
            e["kind"] = "git"
            e.update(g)
            if lock.get(name, {}).get("source") == "embedded":
                e["overriddenByEmbedded"] = True
            if lock.get(name, {}).get("hash"):
                e["lockHash"] = lock[name]["hash"]
        elif isinstance(spec, str) and spec.startswith("file:"):
            e["kind"] = "file"
            d = (proj.root / "Packages" / spec[5:]).resolve()
            e["resolved"] = d.as_posix()
            e["exists"] = (d / "package.json").exists()
            if e["exists"]:
                try:
                    e["packageName"] = json.loads((d / "package.json").read_text(encoding="utf-8-sig")).get("name")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    e["packageName"] = None
        else:
            e["kind"] = "registry"
        deps[name] = e
    embedded = {}
    pk = proj.root / "Packages"
    if pk.is_dir():
        for d in sorted(pk.iterdir()):
            if d.is_dir() and (d / "package.json").exists():
                try:
                    pj = json.loads((d / "package.json").read_text(encoding="utf-8-sig"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pj = {}
                embedded[d.name] = {"name": pj.get("name"), "version": pj.get("version")}
    indirect = {n: {"version": v.get("version"), "source": v.get("source"), "depth": v.get("depth")}
                for n, v in lock.items() if v.get("depth", 0) > 0 and not n.startswith("com.unity.modules.")}
    return {
        "dependencies": deps,
        "scopedRegistries": proj.manifest.get("scopedRegistries") or [],
        "testables": proj.manifest.get("testables") or [],
        "embedded": embedded,
        "indirect": indirect,
    }


def decode_apis(hexstr):
    names = []
    hexstr = (hexstr or "").strip()
    for i in range(0, len(hexstr) - len(hexstr) % 8, 8):
        v = struct.unpack("<i", bytes.fromhex(hexstr[i:i + 8]))[0]
        names.append(GRAPHICS_DEVICE.get(v, f"unknown({v})"))
    return names


def snap_player(proj):
    ps = proj.settings("ProjectSettings.asset")
    apis = {}
    for e in ps.get("m_BuildTargetGraphicsAPIs") or []:
        apis[e.get("m_BuildTarget")] = {"apis": decode_apis(e.get("m_APIs")), "automatic": as_bool(e.get("m_Automatic"))}
    defines = {}
    for k, v in (ps.get("scriptingDefineSymbols") or {}).items():
        defines[BUILD_TARGET_GROUP.get(k, k)] = [s for s in (v or "").split(";") if s.strip()]
    backend = {BUILD_TARGET_GROUP.get(k, k): label(SCRIPTING_BACKEND, v) for k, v in (ps.get("scriptingBackend") or {}).items()}
    # 値が無い対象は Mono（ScriptingImplementation の既定 0）
    backend.setdefault("Standalone", "Mono2x")
    api_per = {BUILD_TARGET_GROUP.get(k, k): label(API_COMPAT, v) for k, v in (ps.get("apiCompatibilityLevelPerPlatform") or {}).items()}
    api_default = label(API_COMPAT, ps.get("apiCompatibilityLevel"))
    return {
        "productName": ps.get("productName"),
        "companyName": ps.get("companyName"),
        "bundleVersion": ps.get("bundleVersion"),
        "graphicsApis": apis,
        "colorSpace": label(COLOR_SPACE, ps.get("m_ActiveColorSpace")),
        "runInBackground": as_bool(ps.get("runInBackground")),
        "visibleInBackground": as_bool(ps.get("visibleInBackground")),
        "fullscreenMode": label(FULLSCREEN_MODE, ps.get("fullscreenMode")),
        "defaultScreen": f"{ps.get('defaultScreenWidth')}x{ps.get('defaultScreenHeight')}",
        "resizableWindow": as_bool(ps.get("resizableWindow")),
        "forceSingleInstance": as_bool(ps.get("forceSingleInstance")),
        "usePlayerLog": as_bool(ps.get("usePlayerLog")),
        "gpuSkinning": as_bool(ps.get("gpuSkinning")),
        "activeInputHandler": as_int(ps.get("activeInputHandler")),
        "activeInputHandlerLabel": label(INPUT_HANDLER, ps.get("activeInputHandler")),
        "apiCompatibility": {"Standalone": api_per.get("Standalone", api_default)},
        "scriptingBackend": backend,
        "defines": defines,
        "allowUnsafeCode": as_bool(ps.get("allowUnsafeCode")),
        "gcIncremental": as_bool(ps.get("gcIncremental")),
    }


def snap_editor(proj):
    es = proj.settings("EditorSettings.asset")
    opts = as_int(es.get("m_EnterPlayModeOptions"), 0)
    return {
        "enterPlayModeOptionsEnabled": as_bool(es.get("m_EnterPlayModeOptionsEnabled")),
        "enterPlayModeOptions": opts,
        "enterPlayModeOptionsLabel": "+".join(n for b, n in ENTER_PLAY_MODE_FLAGS.items() if opts & b) or "None",
        # 効き目: Options が無効なら Options の値に関係なくドメインとシーンを読み直す（= None）。案件どうしはこれで比べる
        "enterPlayModeEffective": ("+".join(n for b, n in ENTER_PLAY_MODE_FLAGS.items() if opts & b) or "None")
        if as_bool(es.get("m_EnterPlayModeOptionsEnabled")) else "None",
        "serializationMode": as_int(es.get("m_SerializationMode")),  # 2 = Force Text
        "lineEndingsForNewScripts": as_int(es.get("m_LineEndingsForNewScripts")),
        "asyncShaderCompilation": as_bool(es.get("m_AsyncShaderCompilation")),
    }


def snap_tags(proj):
    tm = proj.settings("TagManager.asset")
    layers = {str(i): n for i, n in enumerate(tm.get("layers") or []) if n}
    rl = {str(i): n for i, n in enumerate(tm.get("m_RenderingLayers") or []) if n}
    return {
        "layers": layers,
        "renderingLayers": rl,
        "tags": tm.get("tags") or [],
        "sortingLayers": [s.get("name") for s in (tm.get("m_SortingLayers") or [])],
    }


def snap_build_scenes(proj):
    eb = proj.settings("EditorBuildSettings.asset")
    idx = proj.index()
    scenes = []
    for s in eb.get("m_Scenes") or []:
        path = s.get("path") or ""
        exists = (proj.root / path).exists()
        g = s.get("guid")
        scenes.append({"path": path, "enabled": as_bool(s.get("enabled")), "exists": exists,
                       "guidPath": idx.path_of(g, (".unity",)) if g else None})
    config = {}
    for k, v in (eb.get("m_configObjects") or {}).items():
        g = ref_guid(v)
        config[k] = {"guid": g, "path": idx.path_of(g, (".asset", ".inputactions")) if g else None}
    return {"scenes": scenes, "configObjects": config}


def renderer_info(proj, path):
    """Renderer（ScriptableRendererData）の Renderer Feature の並び。空の要素は Map から元の塊を引く。"""
    idx = proj.index()
    info = {"path": proj.rel(path)}
    try:
        docs = load_docs(path)
    except (ReadError, OSError) as e:
        info["error"] = str(e)
        return info
    by_fid = {fid: (cls, data) for cls, fid, data in docs}
    main = by_fid.get("11400000")
    body = (main[1].get("MonoBehaviour") if main else None) or {}
    info["type"] = script_name(idx, body.get("m_Script"))
    for key, table, name in (("m_RenderingMode", URP_RENDERING_MODE, "renderingMode"), ("m_DepthPrimingMode", URP_DEPTH_PRIMING, "depthPriming"),
                             ("m_IntermediateTextureMode", URP_INTERMEDIATE, "intermediateTexture")):
        if key in body:
            info[name] = label(table, body.get(key))
    for key in ("m_CopyDepthMode", "m_DepthTextureFormat", "m_UseNativeRenderPass", "m_AccurateGbufferNormals"):
        if key in body:
            info[key[2:3].lower() + key[3:]] = body.get(key)
    for key in ("m_OpaqueLayerMask", "m_TransparentLayerMask"):
        if isinstance(body.get(key), dict):
            info[key[2:3].lower() + key[3:]] = body[key].get("m_Bits")
    feats = body.get("m_RendererFeatures") or []
    fmap_hex = (body.get("m_RendererFeatureMap") or "").strip()
    fmap = [str(struct.unpack("<q", bytes.fromhex(fmap_hex[i:i + 16]))[0]) for i in range(0, len(fmap_hex) - len(fmap_hex) % 16, 16)]
    listed = set()
    features, empty = [], []
    for slot, ref in enumerate(feats):
        fid = str(ref.get("fileID")) if isinstance(ref, dict) else "0"
        if fid == "0":
            e = {"slot": slot}
            if slot < len(fmap) and fmap[slot] in by_fid:
                e["mapPointsTo"] = feature_desc(idx, by_fid[fmap[slot]][1], fmap[slot])
            empty.append(e)
            continue
        listed.add(fid)
        if fid not in by_fid:
            features.append({"slot": slot, "fileID": fid, "missingBlock": True})
            continue
        d = feature_desc(idx, by_fid[fid][1], fid)
        d["slot"] = slot
        features.append(d)
    orphans = [feature_desc(idx, data, fid) for cls, fid, data in docs
               if cls == "114" and fid != "11400000" and fid not in listed]
    info["features"] = features
    info["emptySlots"] = empty
    info["orphanBlocks"] = orphans
    info["featureMapCount"] = len(fmap)
    info["featureListCount"] = len(feats)
    return info


def feature_desc(idx, data, fid):
    mb = (data or {}).get("MonoBehaviour") or {}
    g = ref_guid(mb.get("m_Script"))
    return {"fileID": fid, "name": mb.get("m_Name"), "active": as_bool(mb.get("m_Active")),
            "script": script_name(idx, mb.get("m_Script")), "scriptGuid": g,
            "scriptFound": bool(g and idx.lookup(g, script_exts(mb.get("m_Script"))))}


def script_name(idx, ref):
    g = ref_guid(ref)
    if not g:
        return None
    p = idx.lookup(g, script_exts(ref))
    return p.name if p else f"(missing {g})"


def urp_asset_info(proj, path):
    idx = proj.index()
    info = {"path": proj.rel(path)}
    try:
        body = main_body(path)
    except (ReadError, OSError) as e:
        info["error"] = str(e)
        return info
    info["type"] = script_name(idx, body.get("m_Script"))
    info["settings"] = {k[2:]: body[k] for k in URP_ASSET_KEYS if k in body}
    vp = ref_guid(body.get("m_VolumeProfile"))
    info["volumeProfile"] = idx.path_of(vp, (".asset",)) if vp else None
    rends = []
    for i, ref in enumerate(body.get("m_RendererDataList") or []):
        g = ref_guid(ref)
        p = idx.lookup(g, (".asset",)) if g else None
        if not p:
            rends.append({"index": i, "guid": g, "missing": True})
            continue
        r = renderer_info(proj, p)
        r["index"] = i
        rends.append(r)
    info["renderers"] = rends
    return info


def snap_render_pipelines(proj):
    idx = proj.index()
    qs = proj.settings("QualitySettings.asset")
    gs = proj.settings("GraphicsSettings.asset")
    assets = {}

    def asset(g):
        if not g:
            return None
        p = idx.lookup(g, (".asset",))
        if not p:
            return f"(missing {g})"
        key = proj.rel(p)
        if key not in assets:
            assets[key] = urp_asset_info(proj, p)
        return key

    levels = []
    for q in qs.get("m_QualitySettings") or []:
        levels.append({"name": q.get("name"), "renderPipeline": asset(ref_guid(q.get("customRenderPipeline"))),
                       "excludedTargetPlatforms": q.get("excludedTargetPlatforms") or [],
                       "vSyncCount": as_int(q.get("vSyncCount")), "antiAliasing": as_int(q.get("antiAliasing"))})
    per = {k: as_int(v) for k, v in (qs.get("m_PerPlatformDefaultQuality") or {}).items()}
    default_rp = asset(ref_guid(gs.get("m_CustomRenderPipeline")))
    sa = per.get("Standalone")
    standalone_level = levels[sa]["name"] if sa is not None and 0 <= sa < len(levels) else None
    standalone_rp = (levels[sa]["renderPipeline"] if standalone_level else None) or default_rp
    gmap = gs.get("m_RenderPipelineGlobalSettingsMap") or {}
    glob = {}
    for cls, ref in gmap.items():
        g = ref_guid(ref)
        p = idx.lookup(g, (".asset",)) if g else None
        e = {"pipeline": cls, "path": proj.rel(p) if p else (f"(missing {g})" if g else None)}
        if p:
            try:
                text = read_text(p)
                m = re.search(r"m_EnableRenderCompatibilityMode: (\d)", text)
                e["renderCompatibilityMode"] = as_bool(m.group(1)) if m else None
                body = main_body(p)
                for k in URP_GLOBAL_KEYS:
                    if k in body:
                        e[k[2:]] = body[k]
            except (ReadError, OSError) as ex:
                e["error"] = str(ex)
        glob[cls.rsplit(".", 1)[-1]] = e
    return {
        "currentQuality": as_int(qs.get("m_CurrentQuality")),
        "perPlatformDefault": per,
        "qualityLevels": levels,
        "graphicsDefault": default_rp,
        "standaloneLevel": standalone_level,
        "standalone": standalone_rp,
        "preloadedShaders": [idx.path_of(ref_guid(r), (".shadervariants",)) or str(r) for r in gs.get("m_PreloadedShaders") or []],
        "alwaysIncludedShaderCount": len(gs.get("m_AlwaysIncludedShaders") or []),
        "globalSettings": glob,
        "assets": assets,
    }


def snap_git(proj):
    root = proj.git_root
    out = {"root": root.as_posix() if root else None}
    if not root:
        return out
    ga = root / ".gitattributes"
    lines = ga.read_text(encoding="utf-8", errors="replace").splitlines() if ga.exists() else []
    out["lfsPatterns"] = sorted({l.split()[0] for l in lines if "filter=lfs" in l and not l.lstrip().startswith("#")})
    # git ルートから見た Unity プロジェクトの位置（proj.rel は Unity から見たパスを返すので、プロジェクトのフォルダ自身は "." になる）
    unity_prefix = proj.root.resolve().relative_to(root.resolve()).as_posix()
    unity_prefix = "" if unity_prefix in (".", "") else unity_prefix + "/"
    samples = [unity_prefix + "Assets/" + s for s in GITATTR_SAMPLES] + [unity_prefix + "ProjectSettings/ProjectSettings.asset"]
    attrs = run_git(root, "check-attr", "filter", "merge", "text", "eol", "--", *samples)
    eff = collections.defaultdict(dict)
    for line in (attrs or "").splitlines():
        m = re.match(r"^(.*?): (\w+): (.*)$", line)
        if m:
            key = "ProjectSettings/*.asset" if m.group(1).endswith("ProjectSettings/ProjectSettings.asset") else "*" + Path(m.group(1)).suffix
            eff[key][m.group(2)] = m.group(3)
    out["attributes"] = {k: ",".join(f"{a}={v}" for a, v in sorted(d.items()) if v != "unspecified") or "-" for k, d in eff.items()}
    ignores = {}
    for gi in (root / ".gitignore", proj.root / ".gitignore"):
        if gi.exists():
            ignores[gi.relative_to(root).as_posix()] = [
                l.strip() for l in gi.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip() and not l.strip().startswith("#")]
    out["gitignore"] = ignores
    exc = root / ".git" / "info" / "exclude"
    out["infoExclude"] = [l.strip() for l in exc.read_text(encoding="utf-8", errors="replace").splitlines()
                          if l.strip() and not l.strip().startswith("#")] if exc.is_file() else []
    subs = []
    gm = root / ".gitmodules"
    if gm.exists():
        cur = None
        for line in gm.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r'^\s*\[submodule "(.*)"\]', line)
            if m:
                cur = {"name": m.group(1)}
                subs.append(cur)
                continue
            m = re.match(r"^\s*(\w+)\s*=\s*(.*?)\s*$", line)
            if m and cur is not None:
                cur[m.group(1)] = m.group(2)
        status = run_git(root, "submodule", "status") or ""
        for s in subs:
            d = root / s.get("path", "")
            s["checkedOut"] = d.is_dir() and any(d.iterdir())
            st = next((l for l in status.splitlines() if l[1:].split(" ")[1:2] == [s.get("path")]), None)
            s["status"] = {"-": "not-initialized", "+": "commit-differs", "U": "conflict", " ": "ok"}.get(st[0], st[0]) if st else None
            if s["checkedOut"]:
                s["head"] = (run_git(d, "rev-parse", "--short", "HEAD") or "").strip() or None
                s["currentBranch"] = (run_git(d, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None
    out["submodules"] = subs
    out["remote"] = (run_git(root, "remote", "get-url", "origin") or "").strip() or None
    return out


def snap_mcp(proj):
    out = {"assets": None, "packages": None, "mcpJson": {}}
    for key, d in (("assets", proj.root / "Assets" / "Plugins" / "ClaudeCodeMCP"), ("packages", proj.root / "Packages" / "com.aiacats.unity-mcp")):
        if (d / "package.json").exists():
            try:
                out[key] = json.loads((d / "package.json").read_text(encoding="utf-8-sig")).get("version")
            except (json.JSONDecodeError, UnicodeDecodeError):
                out[key] = "?"
            if proj.git_root:
                r = subprocess.run(["git", "-C", str(proj.git_root), "check-ignore", "-q", str(d)], capture_output=True)
                out[key + "Ignored"] = r.returncode == 0
    for base in {proj.root, proj.git_root} - {None}:
        f = base / ".mcp.json"
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                out["mcpJson"][proj.rel(f)] = {"error": str(e)}
                continue
            srv = (data.get("mcpServers") or {}).get("claude-code-mcp-unity") or {}
            out["mcpJson"][proj.rel(f)] = {"args": srv.get("args"), "env": sorted((srv.get("env") or {}).keys())}
    return out


def snapshot(path):
    proj = Project(path)
    proj.package_dirs()
    idx = proj.index()
    idx.read_all(("assets", "embedded", "file"), ".cs.meta")
    pv = proj.ps / "ProjectVersion.txt"
    m = re.search(r"m_EditorVersion: (\S+)", pv.read_text(encoding="utf-8", errors="replace"))
    ver = m.group(1) if m else None
    snap = {
        "schema": SCHEMA,
        "project": {"name": proj.root.name, "path": proj.root.as_posix(), "unityVersion": ver},
        "packages": snap_packages(proj),
        "player": snap_player(proj),
        "editor": snap_editor(proj),
        "tags": snap_tags(proj),
        "buildSettings": snap_build_scenes(proj),
        "renderPipelines": snap_render_pipelines(proj),
        "executionOrder": dict(sorted(idx.exec_order.items())),
        "git": snap_git(proj),
        "unityMcp": snap_mcp(proj),
        "errors": proj.errors,
        "scanSeconds": {"walk": idx.walk_seconds, "read": round(idx.read_seconds, 2)},
    }
    return snap, proj


# ---- compare --------------------------------------------------------------------------------------
# 比べる鍵の分け方（前から順に最初に当たったもの）。reference/settings.md の表と同じ考え方:
#   align   = vortex で揃える（違うと挙動・ビルド・受信が変わる）
#   imports = 取り込み物しだい（入っているアセット・パッケージで変わる）
#   project = 案件ごとに違ってよい
CATEGORY_RULES = [
    ("project.unityVersion", "align"),
    ("project.", "skip"),
    ("player.productName", "project"), ("player.companyName", "project"), ("player.bundleVersion", "project"),
    ("player.defaultScreen", "project"), ("player.defines", "imports"),
    ("player.graphicsApis.WindowsStandaloneSupport", "align"), ("player.graphicsApis", "project"),
    ("player.", "align"),
    ("editor.", "align"),
    ("tags.layers", "align"), ("tags.renderingLayers", "align"), ("tags.", "project"),
    ("packages.dependencies.jp.pjblue.realtime-live-utility", "align"),
    ("packages.dependencies", "imports"), ("packages.embedded", "imports"), ("packages.indirect", "imports"),
    ("packages.scopedRegistries", "imports"), ("packages.testables", "project"),
    ("renderPipelines.standalone.renderers.", "align"), ("renderPipelines.standalone.settings", "align"),
    ("renderPipelines.globalSettings.UniversalRenderPipeline.renderCompatibilityMode", "align"),
    ("renderPipelines.globalSettings", "align"),
    ("renderPipelines.", "project"),
    ("buildSettings.", "project"),
    ("executionOrder.", "imports"),
    ("git.attributes", "align"), ("git.lfsPatterns", "align"), ("git.submodules", "project"), ("git.", "project"),
    ("unityMcp.", "project"),
    ("errors", "project"), ("scanSeconds", "skip"), ("schema", "skip"),
]
CATEGORY_TITLES = {"align": "vortex で揃える所（違うと挙動・ビルド・受信が変わる）", "imports": "取り込み物しだいの所",
                   "project": "案件ごとに違ってよい所（参考）", "other": "その他"}
SKIP_KEYS = re.compile(r"(^git\.root$|\.resolved$|\.lockHash$|\.head$|scanSeconds|\.guid$|\.scriptGuid$|\.fileID$|^unityMcp\.mcpJson)")


def categorize(key):
    for prefix, cat in CATEGORY_RULES:
        if key.startswith(prefix):
            return cat
    return "other"


def comparable(snap):
    """比べやすい平らな dict にする。RP アセットはパスではなく役割（standalone = Windows のビルドで使う物）で並べる。"""
    s = json.loads(json.dumps(snap))
    rp = s.get("renderPipelines") or {}
    assets = rp.pop("assets", {}) or {}
    key = rp.get("standalone")
    if isinstance(key, str) and key in assets:
        a = assets[key]
        rp["standalone"] = {"path": key, "settings": a.get("settings"), "volumeProfile": a.get("volumeProfile"),
                            "renderers": {str(r.get("index")): renderer_summary(r) for r in a.get("renderers") or []}}
    rp["qualityLevels"] = {q.get("name"): q for q in rp.get("qualityLevels") or []}
    # パッケージは 1 つ 1 行（spec。埋め込みに上書きされている git 参照はそう書く）
    pk = s.get("packages") or {}
    pk["dependencies"] = {n: str(d.get("spec")) + (" (embedded)" if d.get("overriddenByEmbedded") else "")
                          for n, d in (pk.get("dependencies") or {}).items()}
    pk["embedded"] = {n: d.get("version") for n, d in (pk.get("embedded") or {}).items()}
    pk["indirect"] = {n: d.get("version") for n, d in (pk.get("indirect") or {}).items()}
    flat = {}

    def walk(prefix, v):
        if isinstance(v, dict):
            if not v:
                flat[prefix] = "{}"
            for k, x in v.items():
                walk(f"{prefix}.{k}" if prefix else str(k), x)
        elif isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
            flat[prefix] = v  # 文字の並びは集合として比べる（graphicsApis.apis だけは順番が意味を持つ → 下で別扱い）
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(f"{prefix}[{i}]", x)
        else:
            flat[prefix] = v

    walk("", s)
    return {k: v for k, v in flat.items() if not SKIP_KEYS.search(k)}


def renderer_summary(r):
    feats = []
    slots = {f.get("slot"): f for f in r.get("features") or []}
    for e in r.get("emptySlots") or []:
        slots[e.get("slot")] = {"name": "<empty>"}
    for slot in sorted(k for k in slots if k is not None):
        f = slots[slot]
        feats.append(f"{f.get('name')}{'' if f.get('active') in (True, None) else '(off)'}")
    return {"path": r.get("path"), "type": r.get("type"), "renderingMode": r.get("renderingMode"), "depthPriming": r.get("depthPriming"),
            "intermediateTexture": r.get("intermediateTexture"), "features": " / ".join(feats)}


def load_side(p):
    p = Path(p)
    if p.suffix.lower() == ".json" and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return snapshot(p)[0]


def compare(a, b):
    fa, fb = comparable(a), comparable(b)
    rows = []
    for k in sorted(set(fa) | set(fb)):
        cat = categorize(k)
        if cat == "skip":
            continue
        va, vb = fa.get(k, "<none>"), fb.get(k, "<none>")
        ordered = k.endswith(".apis")
        if isinstance(va, list) and isinstance(vb, list) and not ordered:
            if set(va) == set(vb):
                continue
            rows.append({"category": cat, "key": k, "onlyA": sorted(set(va) - set(vb)), "onlyB": sorted(set(vb) - set(va))})
        elif va != vb:
            rows.append({"category": cat, "key": k, "a": va, "b": vb})
    return rows


def print_compare(a, b, rows):
    print(f"A: {a['project']['name']}  ({a['project']['path']})")
    print(f"B: {b['project']['name']}  ({b['project']['path']})")
    if not rows:
        print("\n違いは無い")
        return
    for cat in ("align", "imports", "project", "other"):
        sel = [r for r in rows if r["category"] == cat]
        if not sel:
            continue
        print(f"\n== {CATEGORY_TITLES[cat]}  {len(sel)} 件")
        for r in sel:
            if "onlyA" in r:
                parts = []
                if r["onlyA"]:
                    parts.append("A だけ: " + "; ".join(map(str, r["onlyA"])))
                if r["onlyB"]:
                    parts.append("B だけ: " + "; ".join(map(str, r["onlyB"])))
                print(f"  {r['key']}: " + " | ".join(parts))
            else:
                print(f"  {r['key']}: A={fmt(r['a'])}  B={fmt(r['b'])}")


def fmt(v):
    if isinstance(v, list):
        return ",".join(map(str, v)) or "[]"
    return str(v)


# ---- check ----------------------------------------------------------------------------------------
class Findings:
    def __init__(self):
        self.items = []

    def add(self, level, code, msg, fix=None):
        self.items.append({"level": level, "code": code, "message": msg, "fix": fix})


def check(path, scan=True):
    snap, proj = snapshot(path)
    idx = proj.index()
    f = Findings()

    for e in snap["errors"]:
        f.add("ERROR" if "LFS" in e else "WARN", "unreadable", e, "LFS なら git lfs pull。無いファイルは Unity を一度開けば作られるものか確かめる")

    # パッケージ
    for name, d in snap["packages"]["dependencies"].items():
        if d["kind"] == "git" and d.get("overriddenByEmbedded"):
            f.add("INFO", "git-overridden-by-embedded", f"{name}: manifest は git 参照だが Packages/ の埋め込みが使われている（git の版は効いていない）",
                  "埋め込みで使い続けるなら manifest の行は file:<フォルダ> にすると読み違えない")
        elif d["kind"] == "git" and not d.get("pinned"):
            rev = d.get("rev")
            pin = f"#{d['lockHash']}" if d.get("lockHash") else "#<コミット>"
            f.add("WARN", "git-unpinned", f"{name}: 版を固定していない git 参照（{'#' + rev if rev else '版の指定なし'}）",
                  f"今の版で固定するなら spec の末尾を {pin} にする（packages-lock.json の hash）。タグがあればタグ")
        if d["kind"] == "file":
            if not d.get("exists"):
                f.add("ERROR", "file-ref-missing", f"{name}: file: 参照の先に package.json が無い（{d['spec']}）",
                      "サブモジュールが取れていないなら git submodule update --init。パッケージの置き場が変わったなら spec を直す")
            elif d.get("packageName") and d["packageName"] != name:
                f.add("ERROR", "file-ref-name", f"{name}: file: 参照の先の package.json の name が {d['packageName']}", "manifest の名前か参照先を直す")
    for s in snap["git"].get("submodules") or []:
        if not s.get("checkedOut"):
            f.add("ERROR", "submodule-missing", f"サブモジュール {s.get('path')} が空", "git submodule update --init --recursive")

    # 同名の asmdef（二重に入るとコンパイルが止まり「エラー 0」に見える。traps unity-build）
    for name, paths in sorted(idx.asmdefs().items()):
        if len(paths) > 1:
            f.add("ERROR", "asmdef-duplicate", f"asmdef {name} が {len(paths)} か所: " + " / ".join(proj.rel(p) for p in paths),
                  "どちらかを消す（パッケージ化済みの物を Assets にも置いていないか）")
    idx.read_all(("assets", "embedded", "file"))
    dup_cache_free = idx.guid_dups()
    if dup_cache_free:
        sample = list(dup_cache_free.items())[:5]
        f.add("WARN", "guid-duplicate", f"同じ GUID の .meta が {len(dup_cache_free)} 組: " +
              " / ".join(f"{g[:8]}… " + " = ".join(proj.rel(p) for p in ps) for g, ps in sample),
              "Unity は片方の GUID を振り直す（参照が切れる元）。片方を消すか、複製した物の .meta を作り直す")

    # Player
    pl = snap["player"]
    win = pl["graphicsApis"].get("WindowsStandaloneSupport")
    if idx.avpro:
        first = None
        if win is None or win.get("automatic"):
            first = "Automatic"
        elif win.get("apis"):
            first = win["apis"][0]
        if first in ("Automatic", "Direct3D12"):
            # 真っ黒になるのを確かめたのは、案件の Assets に入れた AVPro Live Camera（SinkaiFes2026 738b78dc）。
            # 他の AVPro 製品と、パッケージに同梱されているだけの DLL は未確認なので WARN にする
            live = [p for k, p in idx.avpro if k == "assets" and "livecamera" in p.name.lower()]
            where = ", ".join(proj.rel(p) for _, p in idx.avpro[:3])
            fix = "Automatic を外し Direct3D11 → Direct3D12 の順にする（SinkaiFes2026 738b78dc・Ext_Palletproject 2026-03-23）"
            if live:
                f.add("ERROR", "avpro-dx12", f"AVPro Live Camera があるのに Windows の Graphics API の先頭が {first}（DX12 で映像が真っ黒になる）: {where}", fix)
            else:
                f.add("WARN", "avpro-dx12", f"AVPro があるのに Windows の Graphics API の先頭が {first}（DX12 で黒くなるのを確かめたのは Live Camera だけ。"
                      f"この案件で AVPro の映像を使うか確かめる）: {where}", fix)
    if pl.get("runInBackground") is False:
        f.add("WARN", "run-in-background", "runInBackground が Off（背面で OSC・Art-Net・MoCap の受信と Update が止まる）", "Player > Resolution > Run In Background を On")
    if pl.get("visibleInBackground") is False:
        f.add("INFO", "visible-in-background", "visibleInBackground が Off（全画面の窓が背面に回ると描画されない）", None)
    # Input System だけ（1）のとき、旧 Input の API を呼ぶと実行時に InvalidOperationException
    # （SinkaiFes2026 2026-09-15: QuickDeviceMenu が例外になり消した。claudeLog「AVPro の差分調査」）
    if scan and pl.get("activeInputHandler") == 1:
        hits = []
        for k, p in idx.sources:
            if k == "cache" or p.suffix.lower() != ".cs" or any(part.lower() == "editor" for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if LEGACY_INPUT.search(text) and "ENABLE_LEGACY_INPUT_MANAGER" not in text:
                hits.append(p)
        if hits:
            # デモ・サンプル・テストのフォルダの物は後ろへ（案件のスクリプトを先に見せる）
            hits.sort(key=lambda p: (bool(re.search(r"(?i)/[^/]*(demo|example|sample|test)[^/]*/", p.as_posix())), p.as_posix()))
            f.add("WARN", "input-legacy-api", f"Active Input Handling が Input System だけなのに、旧 Input（UnityEngine.Input）を呼ぶスクリプトが {len(hits)} 本: " +
                  ", ".join(proj.rel(p) for p in hits[:5]) + (" ほか" if len(hits) > 5 else ""),
                  "シーンで使う物なら Both（2）にするか Input System へ書き換える。デモ・サンプルなら使わない限り害は無い")

    # Editor の外で UnityEditor を使う .cs は、Editor ではコンパイルが通り、Player のビルドだけ止まる（traps unity-build「Player ビルドを壊さない」）
    if scan:
        bad, asm_cache = [], {}
        for k, p in idx.sources:
            if k == "cache" or p.suffix.lower() != ".cs" or any(part.lower() == "editor" for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "UnityEditor" not in text:  # Editor の型は using UnityEditor か UnityEditor. の修飾なしには書けない
                continue
            line = unguarded_editor_api(text, pl["defines"].get("Standalone") or [])
            if line is not None and compile_target(p, asm_cache) == "player":
                bad.append((p, line))
        if bad:
            f.add("ERROR", "editor-api-in-player",
                  f"Editor フォルダ・Editor 専用の asmdef の外で、#if UNITY_EDITOR に囲まれずに Editor の型（EditorWindow・AssetDatabase など）を使うスクリプトが {len(bad)} 本"
                  "（Editor ではエラー 0 のまま、Player のビルドだけ CS0246 / CS0234 で止まる）: " +
                  ", ".join(f"{proj.rel(p)}:{n}" for p, n in bad[:5]) + (" ほか" if len(bad) > 5 else ""),
                  "EditorWindow・CustomEditor は Editor フォルダへ（.meta ごと移して GUID を保つ）。MonoBehaviour の中なら使う所を #if UNITY_EDITOR で囲む")

    # define
    defs = pl["defines"].get("Standalone") or []
    if scan and defs:
        used = scan_tokens([p for k, p in idx.sources if k != "cache"], defs)
        rest = [d for d in defs if d not in used]
        if rest:
            used |= scan_tokens([p for k, p in idx.sources if k == "cache"], rest)
        cache_present = any(k == "cache" for k, _, _ in proj.package_dirs())
        for d in defs:
            if d not in used:
                f.add("INFO", "define-unused", f"define {d} はどのソース（.cs・シェーダー・asmdef・rsp）にも出てこない" +
                      ("" if cache_present else "（Library/PackageCache が無いので、パッケージ側は見ていない）"),
                      "消した取り込み物の残りなら Player > Scripting Define Symbols から外す")

    # レンダーパイプライン
    rp = snap["renderPipelines"]
    for lv in rp["qualityLevels"]:
        if isinstance(lv.get("renderPipeline"), str) and lv["renderPipeline"].startswith("(missing"):
            f.add("ERROR", "rp-missing", f"Quality {lv['name']} の Render Pipeline Asset が見つからない {lv['renderPipeline']}", "アセットを入れるか Quality で選び直す")
    if isinstance(rp.get("graphicsDefault"), str) and rp["graphicsDefault"].startswith("(missing"):
        f.add("ERROR", "rp-missing", f"Graphics の既定の Render Pipeline Asset が見つからない {rp['graphicsDefault']}", "Graphics で選び直す")
    if rp.get("standalone") is None:
        f.add("WARN", "rp-none", "Windows のビルドで使う Render Pipeline Asset が無い（Built-in のまま）", None)
    seen_renderers = set()  # 同じ Renderer を複数の RP アセットが使うことがある（vortex_urp は 3 つ）。点検は 1 回
    for apath, a in rp["assets"].items():
        if a.get("error"):
            f.add("ERROR", "rp-unreadable", a["error"], None)
        for r in a.get("renderers") or []:
            where = f"{apath} の Renderer [{r.get('index')}]"
            if r.get("missing"):
                f.add("ERROR", "renderer-missing", f"{where} の参照先が無い（guid {r.get('guid')}）", "Renderer List から外すか、アセットを入れる")
                continue
            if r.get("path") in seen_renderers:
                continue
            seen_renderers.add(r.get("path"))
            if r.get("error"):
                f.add("ERROR", "renderer-unreadable", f"{where}: {r['error']}", None)
                continue
            for e in r.get("emptySlots") or []:
                was = e.get("mapPointsTo")
                extra = ""
                if was:
                    extra = f"。Map ではこの枠は {was.get('name')}（スクリプト {'あり' if was.get('scriptFound') else '無し: ' + str(was.get('scriptGuid'))}）"
                f.add("ERROR", "renderer-empty-feature",
                      f"{r['path']} の m_RendererFeatures[{e['slot']}] が空（{{fileID: 0}}）{extra}。"
                      "ビルド時に URP の GatherShaderFeatures が NRE を出し、バリアントの間引きが止まる",
                      "ProjectSetupApply.RemoveEmptyRendererFeatures で m_RendererFeatures と m_RendererFeatureMap の同じ位置を外す（SinkaiFes2026 cf636af9）")
            for x in r.get("features") or []:
                if x.get("missingBlock"):
                    f.add("ERROR", "renderer-feature-dangling", f"{r['path']} の m_RendererFeatures[{x['slot']}] の塊がファイルに無い", None)
                elif not x.get("scriptFound"):
                    if (proj.root / "Library" / "PackageCache").is_dir():
                        f.add("ERROR", "renderer-feature-missing-script",
                              f"{r['path']} の Renderer Feature {x.get('name')} のスクリプトが無い（{x.get('scriptGuid')}）", "取り込み物を入れるか、Renderer から外す")
                    else:
                        # clone の直後など。URP の SSAO などパッケージ側のスクリプトは PackageCache ができるまで引けない
                        f.add("WARN", "renderer-feature-missing-script",
                              f"{r['path']} の Renderer Feature {x.get('name')} のスクリプトが見つからない（{x.get('scriptGuid')}）。"
                              "Library/PackageCache が無いので、パッケージ側のスクリプトは見ていない",
                              "Unity で一度開いて PackageCache を作ってから check し直す")
            if r.get("orphanBlocks"):
                names = ", ".join(f"{o.get('name')}{'' if o.get('scriptFound') else '（スクリプト無し）'}" for o in r["orphanBlocks"])
                f.add("INFO", "renderer-orphan-block", f"{r['path']} に一覧から外れた Feature の塊が残っている: {names}",
                      "一覧に無いので描画にも間引きにも使われない（SinkaiFes2026 cf636af9 はこの塊を残したまま空要素だけ外してビルドが 6.8 時間 → 9.6 分）")
            if r.get("featureMapCount") != r.get("featureListCount"):
                f.add("WARN", "renderer-map-mismatch", f"{r['path']} の m_RendererFeatures {r.get('featureListCount')} 件と Map {r.get('featureMapCount')} 件が合わない", None)
        # 同じ RP アセットの Renderer で描画方式が混ざると、ビルドで両方の方式のバリアントを作る（traps-catalog unity-build「VolumetricLights が DX11 で…」）
        modes = {r.get("renderingMode") for r in a.get("renderers") or [] if r.get("renderingMode")}
        if len(modes) > 1:
            f.add("WARN", "renderer-mode-mixed", f"{apath} の Renderer の描画方式が混ざっている: " +
                  ", ".join(f"[{r.get('index')}] {r.get('renderingMode')}" for r in a.get("renderers") or [] if r.get("renderingMode")),
                  "深度用など補助の Renderer の Rendering Path を本線と同じにする（VolumetricLightsDepthRenderer は DX11 で Forward のまま足される）")
    g = rp["globalSettings"].get("UniversalRenderPipeline") or {}
    if g.get("path", "").startswith("(missing"):
        f.add("ERROR", "urp-global-missing", f"URP の Global Settings が見つからない {g['path']}", "Graphics > URP Global Settings を作り直す")

    # ビルドのシーン
    bs = snap["buildSettings"]
    for s in bs["scenes"]:
        if not s["exists"]:
            f.add("WARN", "build-scene-missing", f"Build Settings のシーンが存在しない: {s['path']}" + ("" if s["enabled"] else "（無効）"),
                  "Build Profiles のシーン一覧から外すか、ビルドするシーンを入れる（ビルドの手順がシーンを渡すなら影響は無い）")
    if not any(s["exists"] and s["enabled"] for s in bs["scenes"]):
        f.add("INFO", "build-scene-none", "Build Settings に有効で存在するシーンが無い（File > Build で何も入らない）", None)
    for k, c in bs["configObjects"].items():
        if c.get("guid") and not c.get("path"):
            f.add("INFO", "config-object-missing", f"EditorBuildSettings の {k} の参照先が無い（guid {c['guid']}）。"
                  "読む側は null として扱う（Input System の project-wide actions ならビルドに入らないだけ）", "使うなら、その設定のウィンドウで作り直す")

    # Unity MCP
    for p, m in snap["unityMcp"]["mcpJson"].items():
        if "MCP_UNITY_HTTP_URL" in (m.get("env") or []):
            f.add("WARN", "mcp-fixed-url", f"{p} に MCP_UNITY_HTTP_URL がある（自動の接続先解決より優先され、別の Unity を掴む）", "env から消す（/setup-unity-mcp）")

    # git
    gi = snap["git"]
    if gi.get("root"):
        check_gitignore(proj, gi, f)
        if scan:
            check_large_files(proj, gi, f)
        sh_attr = (gi.get("attributes") or {}).get("*.sh", "")
        if "eol=lf" not in sh_attr:
            tracked_sh = [l for l in (run_git(proj.git_root, "ls-files", "*.sh") or "").splitlines() if l]
            if tracked_sh:
                f.add("WARN", "sh-eol", f".sh が {len(tracked_sh)} 本あるのに eol=lf でない（CRLF が混ざると途中の行が黙って飛ぶ）", ".gitattributes に `*.sh text eol=lf`")
        if "filter=lfs" in (gi.get("attributes") or {}).get("ProjectSettings/*.asset", ""):
            f.add("INFO", "projectsettings-lfs", "ProjectSettings の .asset も LFS に入る（git diff で中身が見えない・行単位のマージができない）", None)

    # DLL（UnityEditor を参照するのに Windows のビルドに入る）
    if scan:
        for kind, p in idx.dlls:
            if any(part.lower() == "editor" for part in p.parts):
                continue  # Editor フォルダの DLL は Editor 専用
            if dll_in_windows_player(p) and dll_refs_unityeditor(p):
                f.add("WARN", "dll-editor-in-player", f"{proj.rel(p)} は UnityEditor を参照するのに Windows のビルドに入る設定",
                      ".dll.meta を Any: 0 / Editor: 1 にする（Player ビルドで「UnityEditor.dll assembly is referenced by user code」）")
    return snap, f


def scan_tokens(files, tokens):
    pat = re.compile(rb"\b(" + b"|".join(re.escape(t.encode()) for t in tokens) + rb")\b")
    found = set()
    want = set(tokens)
    for p in files:
        try:
            data = p.read_bytes()
        except OSError:
            continue
        for m in pat.finditer(data):
            found.add(m.group(1).decode())
        if found >= want:
            break
    return found


def check_gitignore(proj, gi, f):
    """先頭 / の無い名前だけのパターンが、意図より深い所まで隠していないか（traps git「.gitignore は先頭 / で固定する」）。"""
    listed = run_git(proj.git_root, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory") or ""
    ignored = [l.rstrip("/") for l in listed.splitlines() if l]
    for src, lines in (gi.get("gitignore") or {}).items():
        base = "" if src == ".gitignore" else src.rsplit("/", 1)[0] + "/"
        for pat in lines:
            name = pat.rstrip("/")
            if pat.startswith(("/", "!")) or "/" in name or any(c in name for c in "*?[") or not name:
                continue
            deep = [p for p in ignored if p.startswith(base) and p.split("/")[-1] == name and p[len(base):].count("/") >= 1]
            if deep:
                f.add("WARN", "gitignore-unanchored", f"{src} の `{pat}` が深い所も隠している: " + ", ".join(deep[:5]),
                      f"直下だけなら `/{pat}` と書く。書いたら git check-ignore -v で確かめる")


def run_git_stdin(root, data, *args):
    r = subprocess.run(["git", "-C", str(root), *args], input=data.encode("utf-8"), capture_output=True)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def lfs_filtered(root, paths):
    """.gitattributes で filter=lfs になるパス（-z で受ける。日本語や空白のパスは -z でないと引用符付きで返る）。"""
    out = run_git_stdin(root, "\0".join(paths) + "\0", "check-attr", "-z", "--stdin", "filter") or ""
    parts = out.split("\0")
    return {parts[i] for i in range(0, len(parts) - 2, 3) if parts[i + 2] == "lfs"}


def check_large_files(proj, gi, f):
    """GitHub の大きさの制限に当たるファイル。追跡中の物は index の blob の大きさ（LFS ならポインタで数百バイト）で見る。"""
    if "github.com" not in (gi.get("remote") or ""):
        return
    root = proj.git_root
    staged = run_git(root, "ls-files", "-z", "-s") or ""
    objs = []
    for rec in staged.split("\0"):
        m = re.match(r"^\d+ ([0-9a-f]{40}) \d+\t(.*)$", rec)
        if m:
            objs.append((m.group(1), m.group(2)))
    sizes = run_git_stdin(root, "\n".join(o for o, _ in objs) + "\n", "cat-file", "--batch-check=%(objectsize)") or ""
    big = [(rel, int(s)) for (_, rel), s in zip(objs, sizes.split("\n")) if s.isdigit() and int(s) > GITHUB_WARN_BYTES]
    for rel, size in big:
        if size > GITHUB_BLOCK_BYTES:
            f.add("ERROR", "large-in-git", f"{rel}（{size / 1048576:.0f} MiB）が LFS でなく git の中身として入っている（GitHub は 100 MiB 超の push を断る）",
                  ".gitattributes に足し、git lfs migrate import --include=<path>（push 済みの履歴を書き換えるので先に聞く。後で git lfs checkout）")
    warn = [(rel, size) for rel, size in big if size <= GITHUB_BLOCK_BYTES]
    if warn:
        warn.sort(key=lambda x: -x[1])
        f.add("WARN", "large-in-git", f"50〜100 MiB のファイルが LFS でなく git の中身として {len(warn)} 本入っている（GitHub は push のたびに警告）: " +
              ", ".join(f"{r}（{s / 1048576:.0f} MiB）" for r, s in warn[:5]) + (" ほか" if len(warn) > 5 else ""),
              "拡張子ごと LFS にするなら .gitattributes に足す（既に入っている物は git lfs migrate で移すまで git のまま）")
    untracked = [l for l in (run_git(root, "ls-files", "-z", "--others", "--exclude-standard") or "").split("\0") if l]
    ubig = []
    for rel in untracked:
        try:
            size = (root / rel).stat().st_size
        except OSError:
            continue
        if size > GITHUB_BLOCK_BYTES:
            ubig.append((rel, size))
    if ubig:
        lfs = lfs_filtered(root, [r for r, _ in ubig])
        for rel, size in ubig:
            if rel not in lfs:
                f.add("WARN", "large-untracked-not-lfs", f"{rel}（{size / 1048576:.0f} MiB）を add すると LFS に入らず push で断られる",
                      ".gitattributes に個別に足してから add する")


def dll_in_windows_player(p):
    """.dll.meta の PluginImporter から、Windows 64bit のビルドに入るか。platformData が無い .meta は判断しない（False）。"""
    meta = Path(str(p) + ".meta")
    try:
        # .meta は塊の見出し（--- !u!）の無い普通の YAML
        data = yaml.load(read_text(meta), Loader=LOADER) if meta.exists() else None
    except (ReadError, OSError, yaml.YAMLError):
        return False
    body = data.get("PluginImporter") if isinstance(data, dict) else None
    if not isinstance(body, dict) or "platformData" not in body:
        return False
    entries = body.get("platformData")
    if not isinstance(entries, list):
        return False  # 古い形式（data: の繰り返し）は YAML として重なった鍵になり読めない
    any_on, any_settings, win_on = False, {}, False
    for e in entries:
        if not isinstance(e, dict):
            continue
        first, second = e.get("first") or {}, e.get("second") or {}
        if "Any" in first:
            any_on = as_bool(second.get("enabled")) or False
            any_settings = second.get("settings") or {}
        if first.get("Standalone") == "Win64":
            win_on = as_bool(second.get("enabled")) or False
    if any_on:
        return str(any_settings.get("Exclude Win64", "0")) != "1"
    return win_on


def dll_refs_unityeditor(p):
    try:
        data = p.read_bytes()
    except OSError:
        return False
    if not data.startswith(b"MZ"):
        return False
    return b"\x00UnityEditor\x00" in data or b"\x00UnityEditor.CoreModule\x00" in data


def print_findings(snap, f):
    print(f"{snap['project']['name']}  ({snap['project']['path']})  Unity {snap['project']['unityVersion']}")
    if not f.items:
        print("問題は見つからない")
        return
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for it in sorted(f.items, key=lambda x: order[x["level"]]):
        print(f"[{it['level']}] {it['code']}: {it['message']}")
        if it.get("fix"):
            print(f"    -> {it['fix']}")
    c = collections.Counter(i["level"] for i in f.items)
    print(f"\nERROR {c['ERROR']} / WARN {c['WARN']} / INFO {c['INFO']}")


# ---- main -----------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="vortex 系 Unity プロジェクトの設定を読み出す・比べる・点検する")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="設定の要点を JSON にする")
    s.add_argument("project")
    s.add_argument("-o", "--out")
    c = sub.add_parser("compare", help="2 つ（プロジェクトか snapshot の json）を比べる")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--json", action="store_true")
    k = sub.add_parser("check", help="基準が無くても分かる問題を出す")
    k.add_argument("project")
    k.add_argument("--json", action="store_true")
    k.add_argument("--no-scan", action="store_true", help="ファイル全体を読む点検（define・DLL・大きいファイル）を飛ばす")
    a = ap.parse_args()

    if a.cmd == "snapshot":
        snap, _ = snapshot(a.project)
        text = json.dumps(snap, ensure_ascii=False, indent=2)
        if a.out:
            Path(a.out).write_text(text + "\n", encoding="utf-8")
            sec = snap['scanSeconds']
            print(f"wrote {a.out}  （名前の走査 {sec['walk']} 秒・.meta の読み込み {sec['read']} 秒、読めなかったもの {len(snap['errors'])} 件）")
        else:
            print(text)
    elif a.cmd == "compare":
        sa, sb = load_side(a.a), load_side(a.b)
        rows = compare(sa, sb)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print_compare(sa, sb, rows)
    elif a.cmd == "check":
        snap, f = check(a.project, scan=not a.no_scan)
        if a.json:
            print(json.dumps(f.items, ensure_ascii=False, indent=2))
        else:
            print_findings(snap, f)
        sys.exit(1 if any(i["level"] == "ERROR" for i in f.items) else 0)


if __name__ == "__main__":
    main()
