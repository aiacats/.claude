"""Player のビルドでだけコンパイルが止まる、Editor の API の使い方を .cs のソースから見つける（project_audit.py の check の editor-api-in-player）。

Editor のコンパイルでは UnityEditor.dll が見えるので通り、Player のビルドだけ CS0246 / CS0234 で止まる（SinkaiFes2026 2026-10-19:
Runtime フォルダの EditorWindow・CustomEditor、MonoBehaviour のフィールドの UnityEditor.DefaultAsset）。
`using UnityEditor;` だけなら Player でも通る（UnityEngine.dll に UnityEditor.Experimental・UnityEditor.Analytics の型があり、親の名前空間ができる）。

見る物:
- Player に入るファイルか（compile_target）: asmdef / asmref の行き先、asmdef の無い Assets は Editor フォルダの規則、パッケージで asmdef の無い .cs は読まれない。
- その行が Player でコンパイルされうるか: #if / #elif / #else を 3 値（真・偽・不明）で評価する。UNITY_EDITOR は偽、案件の define は真、
  Unity が場合によって定義するシンボルと asmdef の versionDefines は不明（中も見る）、それ以外の定義の無いシンボルは偽。ファイルの #define / #undef も効かせる。
- 使い方: Player に無い名前空間の using（UnityEditorInternal・UnityEditor.SceneManagement など）・using static / 別名、UnityEditor. で修飾した型、
  `using UnityEditor;` が効いているファイルでの Editor の型（EditorWindow・AssetDatabase. など）。コメントと文字列の中は見ない（$"{…}" の中は見る）。
"""
import json
import os
import re
from pathlib import Path

# Unity 6000.3.5f2 の Player のコンパイルの参照（SinkaiFes2026 の Player の Assembly-CSharp.rsp の -r: の DLL 301 本）を走査して見つかった、
# UnityEditor で始まる名前空間（2026-10-19）。ほかはソースで宣言されていれば足す（Crest は Runtime に namespace UnityEditor.SceneManagement { } を置く）
PLAYER_EDITOR_NAMESPACES = frozenset({"UnityEditor", "UnityEditor.Experimental", "UnityEditor.Analytics"})

# Unity・パッケージが場合によって定義するシンボルの頭（不明として扱い、#if の中も見る）
BUILTIN_UNKNOWN_PREFIXES = ("UNITY_", "ENABLE_", "PLATFORM_", "NET_", "NETSTANDARD", "NET4", "NET2", "CSHARP_", "DEVELOPMENT_BUILD",
                            "DEBUG", "TRACE", "CINEMACHINE", "USING_", "MOBILE_INPUT", "UNITY")

# `using UnityEditor;` が効いているときだけ見る、Editor にしか無い型（ほかの名前と紛れにくい物。型のあとに . を要る物は呼び出しの形で見る）
EDITOR_TYPE_BARE = re.compile(
    r"\bEditorWindow\b|\bScriptableWizard\b|\bShaderGUI\b|\bMaterialEditor\b|\bAssetPostprocessor\b|\bScriptableSingleton\b|"
    r"\bSerializedObject\b|\bSerializedProperty\b|\bDefaultAsset\b|\bPropertyDrawer\b|\bDecoratorDrawer\b|\bMonoScript\b|\bSceneAsset\b|"
    r"\bGenericMenu\b|\bBuildTarget\b|\bBuildTargetGroup\b|\bReorderableList\b|"
    r"\bclass\s+\w+(?:<[^>]*>)?\s*:\s*Editor\b|\[\s*(?:CustomEditor|MenuItem|InitializeOnLoad|InitializeOnLoadMethod|CustomPropertyDrawer|"
    r"CanEditMultipleObjects|DidReloadScripts|DrawGizmo|CustomPreview)\b|"
    r"\b(?:AssetDatabase|EditorUtility|EditorGUILayout|EditorGUI|EditorGUIUtility|EditorApplication|EditorPrefs|EditorSceneManager|PrefabUtility|"
    r"Undo|Handles|HandleUtility|SceneView|EditorStyles|BuildPipeline|AssetImporter|ModelImporter|TextureImporter|Selection|AnimationUtility|"
    r"EditorJsonUtility|EditorBuildSettings|PlayerSettings|EditorSettings|EditorUserBuildSettings|ShaderUtil|CompilationPipeline|"
    r"SceneVisibilityManager|EditorCurveBinding|ObjectFactory|PrefabStageUtility|SessionState)\s*\.")
QUALIFIED = re.compile(r"\b(UnityEditor(?:Internal)?(?:\.[A-Za-z_]\w*)+)")
USING = re.compile(r"^\s*(?:global\s+)?using\s+(static\s+)?(?:([A-Za-z_]\w*)\s*=\s*)?([A-Za-z_][\w.]*)\s*;")
NAMESPACE_DECL = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)")
DIRECTIVE = re.compile(r"^\s*#\s*(if|elif|else|endif|define|undef)\b(.*)$")
TYPE_DECL = re.compile(r"\b(?:class|struct|interface|enum|record)\s+([A-Za-z_]\w*)")


# ---- コメントと文字列を外す ----

def code_lines(text):
    """行ごとの「コードだけ」の文字列（コメントと文字列の中身を外す。$"…{式}…" の式は残す）。行の数は元と同じ。"""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    out, cur = [], []
    i, n = 0, len(text)
    state = "code"      # code / block / str / vstr / char
    interp = False      # 今の文字列が $"…" か
    depth = 0           # $"…{ … }…" の { の深さ（> 0 の間はコード）
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "\n":
            out.append("".join(cur))
            cur = []
            if state in ("str", "char"):   # 普通の文字列は行をまたがない（壊れたソースでも先へ進める）
                state, depth = "code", 0
            i += 1
            continue
        if state == "code":
            if c == "/" and nxt == "/":
                j = text.find("\n", i)
                i = n if j < 0 else j
                continue
            if c == "/" and nxt == "*":
                state = "block"
                i += 2
                continue
            if c in "$@" and nxt in "$@" and text[i + 2:i + 3] == '"':   # $@"…" / @$"…"
                state, interp, depth = "vstr", True, 0
                cur.append('""')
                i += 3
                continue
            if c == "@" and nxt == '"':
                state, interp, depth = "vstr", False, 0
                cur.append('""')
                i += 2
                continue
            if c == "$" and nxt == '"':
                state, interp, depth = "str", True, 0
                cur.append('""')
                i += 2
                continue
            if c == '"':
                state, interp, depth = "str", False, 0
                cur.append('""')
                i += 1
                continue
            if c == "'":
                state = "char"
                i += 1
                continue
            cur.append(c)
            i += 1
            continue
        if state == "block":
            if c == "*" and nxt == "/":
                state = "code"
                cur.append(" ")
                i += 2
            else:
                i += 1
            continue
        if state == "char":
            if c == "\\":
                i += 2
            else:
                if c == "'":
                    state = "code"
                i += 1
            continue
        # 文字列（str / vstr）
        if interp and depth > 0:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    cur.append(" ")
                    i += 1
                    continue
            cur.append(c)
            i += 1
            continue
        if interp and c == "{":
            if nxt == "{":
                i += 2
                continue
            depth = 1
            cur.append(" ")
            i += 1
            continue
        if state == "str":
            if c == "\\":
                i += 2
                continue
            if c == '"':
                state = "code"
            i += 1
            continue
        # vstr: "" は引用符そのもの
        if c == '"':
            if nxt == '"':
                i += 2
                continue
            state = "code"
        i += 1
    out.append("".join(cur))
    return out


# ---- #if の式を 3 値で ----

TOKEN = re.compile(r"\s*(\|\||&&|==|!=|!|\(|\)|[A-Za-z_]\w*)")


def eval_condition(expr, value_of):
    """#if の式を、True / False / None（不明）で評価する。value_of(シンボル) が 3 値を返す。読めない式は None。"""
    toks, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m:
            return None
        toks.append(m.group(1))
        pos = m.end()
    k = [0]

    def peek():
        return toks[k[0]] if k[0] < len(toks) else None

    def take():
        k[0] += 1
        return toks[k[0] - 1]

    def p_or():
        v = p_and()
        while peek() == "||":
            take()
            r = p_and()
            v = True if (v is True or r is True) else (False if (v is False and r is False) else None)
        return v

    def p_and():
        v = p_eq()
        while peek() == "&&":
            take()
            r = p_eq()
            v = False if (v is False or r is False) else (True if (v is True and r is True) else None)
        return v

    def p_eq():
        v = p_not()
        while peek() in ("==", "!="):
            op = take()
            r = p_not()
            v = None if (v is None or r is None) else ((v == r) if op == "==" else (v != r))
        return v

    def p_not():
        if peek() == "!":
            take()
            v = p_not()
            return None if v is None else (not v)
        return p_atom()

    def p_atom():
        t = take() if peek() is not None else None
        if t == "(":
            v = p_or()
            if peek() == ")":
                take()
            return v
        if t == "true":
            return True
        if t == "false":
            return False
        if t is None or not re.match(r"[A-Za-z_]", t):
            raise ValueError(t)
        return value_of(t)

    try:
        v = p_or()
    except (ValueError, IndexError):
        return None
    return v if peek() is None else None


def player_symbol(defines, unknown):
    """Player のビルドでのシンボルの値（3 値）。"""
    def value_of(name, local=None):
        if local is not None and name in local:
            return local[name]
        if name.startswith("UNITY_EDITOR"):
            return False
        if name in defines:
            return True
        if name in unknown or name.startswith(BUILTIN_UNKNOWN_PREFIXES):
            return None
        return False
    return value_of


# ---- ファイル 1 本を見る ----

def declared_types(text):
    """ソースで宣言している型の名前（class / struct / interface / enum / record）。"""
    return {m.group(1) for line in code_lines(text) for m in TYPE_DECL.finditer(line)}


def scan(text, defines=(), unknown=(), extra_namespaces=(), own_types=()):
    """Player でコンパイルされうる所で、Editor の API を使っている最初の (行番号, 理由)。無ければ None。
    own_types: 案件が自分で宣言している型の名前（同じ名前の Editor の型とはみなさない。Crest の ScriptableSingleton<T> など）。"""
    own = set(own_types) | declared_types(text)
    allowed = set(PLAYER_EDITOR_NAMESPACES) | set(extra_namespaces)
    base = player_symbol(set(defines), set(unknown))
    local = {}                      # ファイルの #define / #undef
    stack = []                      # 各段: {"cur": この枝の値, "any": それまでの枝のどれかが真か（3 値）}
    editor_using = False            # 効いている `using UnityEditor;` があるか

    def value_of(name):
        return base(name, local)

    def active():
        v = True
        for f in stack:
            if f["cur"] is False:
                return False
            if f["cur"] is None:
                v = None
        return v

    for no, line in enumerate(code_lines(text), 1):
        m = DIRECTIVE.match(line)
        if m:
            kw, rest = m.group(1), m.group(2).strip()
            if kw in ("define", "undef"):
                if active() is not False and rest:
                    local[rest.split()[0]] = (kw == "define")
                continue
            if kw == "if":
                c = eval_condition(rest, value_of)
                parent_off = active() is False
                stack.append({"cur": False if parent_off else c, "any": c, "off": parent_off})
            elif kw == "elif" and stack:
                f = stack[-1]
                c = eval_condition(rest, value_of)
                prev = f["any"]
                cur = False if prev is True else (c if prev is False else (False if c is False else None))
                f["cur"] = False if f["off"] else cur
                f["any"] = True if (prev is True or c is True) else (False if (prev is False and c is False) else None)
            elif kw == "else" and stack:
                f = stack[-1]
                prev = f["any"]
                cur = False if prev is True else (True if prev is False else None)
                f["cur"] = False if f["off"] else cur
                f["any"] = True
            elif kw == "endif" and stack:
                stack.pop()
            continue
        if active() is False or not line.strip():
            continue
        um = USING.match(line)
        if um:
            is_static, alias, target = um.group(1), um.group(2), um.group(3)
            if target.startswith(("UnityEditor", "UnityEditorInternal")):
                if is_static or alias:
                    # 型か名前空間を指す: 有る名前空間そのもの（別名だけ）か、Player に型がある名前空間の下なら通る
                    has_type = any(target.startswith(ns + ".") for ns in PLAYER_EDITOR_NAMESPACES if ns != "UnityEditor")
                    if not (has_type or (alias and target in allowed)):
                        return no, f"using {'static ' if is_static else alias + ' = '}{target}"
                elif target not in allowed:
                    return no, f"using {target}（Player に無い名前空間）"
                elif target == "UnityEditor":
                    editor_using = True
            continue
        if NAMESPACE_DECL.match(line):
            continue
        for q in QUALIFIED.finditer(line):
            # 修飾した型は、Player の DLL に型がある名前空間の下だけ通る（ソースで宣言しただけの名前空間には型が無い）
            name = q.group(1)
            if not any(name.startswith(ns + ".") for ns in PLAYER_EDITOR_NAMESPACES if ns != "UnityEditor"):
                return no, name
        if editor_using:
            for b in EDITOR_TYPE_BARE.finditer(line):
                ids = re.findall(r"[A-Za-z_]\w*", b.group(0))
                name = ids[-1] if ids[0] == "class" else ids[0]
                if name not in own:
                    return no, name
    return None


def declared_namespaces(text):
    """ソースで宣言している UnityEditor で始まる名前空間（Crest の namespace UnityEditor.SceneManagement { } など）。"""
    return {m.group(1) for line in code_lines(text) for m in [NAMESPACE_DECL.match(line)] if m and m.group(1).startswith("UnityEditor")}


# ---- ファイルがどこへコンパイルされるか ----

class AsmIndex:
    """asmdef の名前・GUID → 中身。asmref の行き先を引くのに使う。"""

    def __init__(self, asmdef_files):
        self.by_path, self.by_name, self.by_guid = {}, {}, {}
        for p in asmdef_files:
            try:
                d = json.loads(Path(p).read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            self.by_path[os.path.normcase(str(p))] = d
            if d.get("name"):
                self.by_name[d["name"]] = d
            meta = Path(str(p) + ".meta")
            if meta.exists():
                m = re.search(r"^guid:\s*([0-9a-f]{32})", meta.read_text(encoding="utf-8", errors="replace"), re.M)
                if m:
                    self.by_guid[m.group(1)] = d

    def version_define_names(self):
        return {vd.get("define") for d in self.by_path.values() for vd in (d.get("versionDefines") or []) if vd.get("define")}

    @staticmethod
    def target_of(d):
        """asmdef の中身 → "editor"（Windows の Player に入らない）/ "player"。"""
        if d is None:
            return "player"
        if "UNITY_EDITOR" in (d.get("defineConstraints") or []):
            return "editor"
        inc, exc = d.get("includePlatforms") or [], d.get("excludePlatforms") or []
        if inc and "WindowsStandalone64" not in inc:
            return "editor"
        if "WindowsStandalone64" in exc:
            return "editor"
        return "player"

    def resolve_asmref(self, path):
        try:
            ref = json.loads(Path(path).read_text(encoding="utf-8-sig")).get("reference") or ""
        except (OSError, json.JSONDecodeError):
            return None
        if ref.startswith("GUID:"):
            return self.by_guid.get(ref[5:].lower())
        return self.by_name.get(ref)


def compile_target(path, kind, boundary, asm, cache):
    """.cs の行き先: "editor" / "player" / "none"（パッケージで asmdef の無い .cs は読まれない）。
    boundary: Assets のフォルダ（kind が assets）か、パッケージのフォルダ。Assets の中の package.json は見ない。"""
    path = Path(path)
    boundary = Path(boundary)
    for d in path.parents:
        key = os.path.normcase(str(d))
        if key in cache:
            return cache[key]
        if d.is_dir():
            defs = sorted(d.glob("*.asmdef"))
            if defs:
                cache[key] = asm.target_of(asm.by_path.get(os.path.normcase(str(defs[0]))))
                return cache[key]
            refs = sorted(d.glob("*.asmref"))
            if refs:
                cache[key] = asm.target_of(asm.resolve_asmref(refs[0]))
                return cache[key]
        if os.path.normcase(str(d)) == os.path.normcase(str(boundary)):
            break
    if kind != "assets":
        return "none"
    try:
        rel = path.relative_to(boundary).parts[:-1]
    except ValueError:
        rel = path.parts[:-1]
    # asmdef の無い Assets: Editor という名前のフォルダの下は Assembly-CSharp-Editor（大文字小文字は区別しない: Windows）
    return "editor" if any(part.lower() == "editor" for part in rel) else "player"
