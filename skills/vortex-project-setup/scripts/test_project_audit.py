"""project_audit.py の確かめ（Unity 不要）。一時フォルダに小さな Unity プロジェクトを 2 つ作って流す。
- clean : 問題の無いプロジェクト。check が ERROR / WARN を 1 件も出さないこと（偽陽性が無いこと）
- broken: clean に問題を 1 つずつ入れたもの。入れた問題の code がすべて出ること（取りこぼしが無いこと）。
          同じ所に「出てはいけない」物（版を固定した git 参照・使われている define など）も混ぜて、出ないことも確かめる
使い方: python test_project_audit.py [--keep]   （--keep で一時フォルダを残す）"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import project_audit as pa  # noqa: E402

HEAD = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
G = {  # 32 桁の GUID（中身に意味は無い。重ならないように振る）
    "rp": "a" * 31 + "1", "renderer": "a" * 31 + "2", "global": "a" * 31 + "3", "scene": "a" * 31 + "4",
    "feature_cs": "a" * 31 + "5", "rp_cs": "bf2edee5c58d82540a51f03df9d42094", "renderer_cs": "de640fe3d0db1804a85f9fc8f5cadab6",
    "volume": "a" * 31 + "6", "missing_cs": "b" * 32, "missing_rp": "c" * 32, "rp2": "a" * 31 + "7", "renderer2": "a" * 31 + "8",
}


def meta(guid, extra=""):
    return f"fileFormatVersion: 2\nguid: {guid}\n{extra}"


def w(root, rel, text, binary=False):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8", newline="\n")


def player(apis="0200000012000000", run_bg=1, defines="BAR_USED"):
    return HEAD + f"""--- !u!129 &1
PlayerSettings:
  productName: Clean
  companyName: aiacats
  defaultScreenWidth: 1920
  defaultScreenHeight: 1080
  m_ActiveColorSpace: 1
  runInBackground: {run_bg}
  visibleInBackground: 1
  fullscreenMode: 1
  m_BuildTargetGraphicsAPIs:
  - m_BuildTarget: WindowsStandaloneSupport
    m_APIs: {apis}
    m_Automatic: 0
  scriptingDefineSymbols:
    Standalone: {defines}
  scriptingBackend: {{}}
  apiCompatibilityLevelPerPlatform: {{}}
  apiCompatibilityLevel: 6
  activeInputHandler: 1
"""


def renderer(features, mode=2):
    """features: [(fileID, name, script guid)]。fileID '0' は空要素（Map にはそのまま書く）。"""
    blocks, refs, fmap = "", "", ""
    for fid, name, sg in features:
        refs += f"  - {{fileID: {fid if name != '<empty>' else 0}}}\n"
        fmap += pa.struct.pack("<q", int(fid)).hex()
        if name != "<empty>":
            blocks += f"""--- !u!114 &{fid}
MonoBehaviour:
  m_Script: {{fileID: 11500000, guid: {sg}, type: 3}}
  m_Name: {name}
  m_Active: 1
"""
    return HEAD + blocks + f"""--- !u!114 &11400000
MonoBehaviour:
  m_Script: {{fileID: 11500000, guid: {G['renderer_cs']}, type: 3}}
  m_Name: Renderer
  m_RendererFeatures:
{refs}  m_RendererFeatureMap: {fmap}
  m_OpaqueLayerMask:
    serializedVersion: 2
    m_Bits: 4294967295
  m_RenderingMode: {mode}
  m_DepthPrimingMode: 0
  m_IntermediateTextureMode: 1
"""


def quality(rp_guid):
    """PC（Windows の既定）と Mobile の 2 段。Mobile の RP2 は PC と同じ Renderer を使う（同じ Renderer を 2 回点検しないこと）。"""
    levels = ""
    for name, g in (("PC", rp_guid), ("Mobile", G["rp2"])):
        levels += f"""  - serializedVersion: 5
    name: {name}
    vSyncCount: 0
    antiAliasing: 0
    customRenderPipeline: {{fileID: 11400000, guid: {g}, type: 2}}
    excludedTargetPlatforms: []
"""
    return HEAD + "--- !u!47 &1\nQualitySettings:\n  m_CurrentQuality: 0\n  m_QualitySettings:\n" + levels + \
        "  m_PerPlatformDefaultQuality:\n    Standalone: 0\n"


def build_settings(extra_scene=False):
    s = HEAD + f"""--- !u!1045 &1
EditorBuildSettings:
  m_Scenes:
  - enabled: 1
    path: Assets/Scenes/Main.unity
    guid: {G['scene']}
"""
    if extra_scene:
        s += "  - enabled: 1\n    path: Assets/Scenes/Gone.unity\n    guid: " + "d" * 32 + "\n"
    return s + "  m_configObjects: {}\n"


def make_clean(root):
    w(root, "Unity/ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.3.5f2\n")
    w(root, "Unity/ProjectSettings/ProjectSettings.asset", player())
    w(root, "Unity/ProjectSettings/EditorSettings.asset", HEAD + "--- !u!159 &1\nEditorSettings:\n  m_SerializationMode: 2\n"
      "  m_EnterPlayModeOptionsEnabled: 1\n  m_EnterPlayModeOptions: 0\n")
    w(root, "Unity/ProjectSettings/TagManager.asset", HEAD + "--- !u!78 &1\nTagManager:\n  tags: []\n  layers:\n  - Default\n"
      "  - TransparentFX\n  - Ignore Raycast\n  - Chara\n  - Water\n  - UI\n  m_SortingLayers:\n  - name: Default\n"
      "  m_RenderingLayers:\n  - Default\n  - Character\n")
    w(root, "Unity/ProjectSettings/EditorBuildSettings.asset", build_settings())
    w(root, "Unity/ProjectSettings/QualitySettings.asset", quality(G["rp"]))
    w(root, "Unity/ProjectSettings/GraphicsSettings.asset", HEAD + f"""--- !u!30 &1
GraphicsSettings:
  m_AlwaysIncludedShaders: []
  m_PreloadedShaders: []
  m_CustomRenderPipeline: {{fileID: 11400000, guid: {G['rp']}, type: 2}}
  m_RenderPipelineGlobalSettingsMap:
    UnityEngine.Rendering.Universal.UniversalRenderPipeline: {{fileID: 11400000, guid: {G['global']}, type: 2}}
""")
    w(root, "Unity/Packages/manifest.json", json.dumps({"dependencies": {
        "com.unity.render-pipelines.universal": "17.3.0",
        "com.example.pinned": "https://github.com/example/pinned.git?path=/Pkg#0123456789abcdef0123456789abcdef01234567",
        "com.example.tagged": "https://github.com/example/tagged.git#v1.2.3",
        "jp.example.local": "file:../../Local/jp.example.local",
        # 埋め込みに上書きされた git 参照（vortex_urp の lilToon・unity-mcp と同じ形）。版の固定を問わず INFO だけ
        "com.example.embedded": "https://github.com/example/embedded.git#master",
        # 埋め込みを file: でも書いた物（同じフォルダを 2 回数えないこと）
        "com.example.embedded2": "file:com.example.embedded2",
    }}, indent=2))
    w(root, "Unity/Packages/packages-lock.json", json.dumps({"dependencies": {
        "com.example.embedded": {"version": "file:com.example.embedded", "depth": 0, "source": "embedded"},
        "com.example.embedded2": {"version": "file:com.example.embedded2", "depth": 0, "source": "embedded"},
    }}))
    for n in ("com.example.embedded", "com.example.embedded2"):
        w(root, f"Unity/Packages/{n}/package.json", json.dumps({"name": n, "version": "1.0.0"}))
        w(root, f"Unity/Packages/{n}/Runtime/{n}.asmdef", json.dumps({"name": n}))
    w(root, "Local/jp.example.local/package.json", json.dumps({"name": "jp.example.local", "version": "1.0.0"}))
    w(root, "Local/jp.example.local/Runtime/Local.asmdef", json.dumps({"name": "Example.Local"}))
    w(root, "Unity/Assets/Settings/RP.asset", HEAD + f"""--- !u!114 &11400000
MonoBehaviour:
  m_Script: {{fileID: 11500000, guid: {G['rp_cs']}, type: 3}}
  m_Name: RP
  m_RendererDataList:
  - {{fileID: 11400000, guid: {G['renderer']}, type: 2}}
  m_DefaultRendererIndex: 0
  m_RequireDepthTexture: 1
  m_RequireOpaqueTexture: 1
  m_VolumeProfile: {{fileID: 11400000, guid: {G['volume']}, type: 2}}
""")
    w(root, "Unity/Assets/Settings/RP.asset.meta", meta(G["rp"]))
    w(root, "Unity/Assets/Settings/RP2.asset", (root / "Unity/Assets/Settings/RP.asset").read_text(encoding="utf-8").replace("m_Name: RP", "m_Name: RP2"))
    w(root, "Unity/Assets/Settings/RP2.asset.meta", meta(G["rp2"]))
    w(root, "Unity/Assets/Settings/Renderer.asset", renderer([("123", "MyFeature", G["feature_cs"])]))
    w(root, "Unity/Assets/Settings/Renderer.asset.meta", meta(G["renderer"]))
    w(root, "Unity/Assets/Settings/Global.asset", HEAD + "--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: Global\n"
      "  m_StripUnusedVariants: 1\n  references:\n    RefIds:\n    - rid: 1\n      type: {class: RenderGraphSettings, ns: UnityEngine.Rendering.Universal, asm: x}\n"
      "      data:\n        m_EnableRenderCompatibilityMode: 0\n")
    w(root, "Unity/Assets/Settings/Global.asset.meta", meta(G["global"]))
    w(root, "Unity/Assets/Settings/Volume.asset", HEAD + "--- !u!114 &11400000\nMonoBehaviour:\n  m_Name: Volume\n")
    w(root, "Unity/Assets/Settings/Volume.asset.meta", meta(G["volume"]))
    w(root, "Unity/Assets/Scripts/MyFeature.cs", "#if BAR_USED\nclass MyFeature {}\n#endif\n")
    w(root, "Unity/Assets/Scripts/MyFeature.cs.meta", meta(G["feature_cs"], "MonoImporter:\n  executionOrder: -5\n"))
    w(root, "Unity/Assets/Scripts/UniversalRenderPipelineAsset.cs", "class UniversalRenderPipelineAsset {}\n")
    w(root, "Unity/Assets/Scripts/UniversalRenderPipelineAsset.cs.meta", meta(G["rp_cs"]))
    w(root, "Unity/Assets/Scripts/UniversalRendererData.cs", "class UniversalRendererData {}\n")
    w(root, "Unity/Assets/Scripts/UniversalRendererData.cs.meta", meta(G["renderer_cs"]))
    w(root, "Unity/Assets/Scripts/Game.asmdef", json.dumps({"name": "Example.Game"}))
    # AVPro Live Camera があっても D3D11 が先頭なら問題ない（avpro-dx12 が出てはいけない）
    w(root, "Unity/Assets/AVProLiveCamera/Runtime/AVProLiveCamera.cs", "class AVProLiveCamera {}\n")
    w(root, "Unity/Assets/Scenes/Main.unity", HEAD)
    w(root, "Unity/Assets/Scenes/Main.unity.meta", meta(G["scene"]))
    # DLL: UnityEditor を参照するが Editor 専用の設定（出てはいけない）
    w(root, "Unity/Assets/Plugins/EdOnly.dll", b"MZ\x00\x00UnityEditor\x00", binary=True)
    w(root, "Unity/Assets/Plugins/EdOnly.dll.meta", meta("e" * 32, "PluginImporter:\n  platformData:\n  - first:\n      Any: \n"
      "    second:\n      enabled: 0\n      settings: {}\n  - first:\n      Editor: Editor\n    second:\n      enabled: 1\n"))
    w(root, ".gitattributes", "*.sh text eol=lf\n*.png filter=lfs diff=lfs merge=lfs -text\n")
    w(root, ".gitignore", "/log/\n/Unity/[Ll]ibrary/\n")
    w(root, "tools/run.sh", "echo ok\n")
    w(root, ".mcp.json", json.dumps({"mcpServers": {"claude-code-mcp-unity": {"command": "node", "args": ["x/index.js"]}}}))
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", "https://github.com/example/clean.git")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "clean")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_broken(root):
    U = root / "Unity"
    # 1 空の Renderer Feature + 2 スクリプトの無い Feature（Unity で開いた後 = PackageCache がある → ERROR）
    (U / "Library/PackageCache").mkdir(parents=True, exist_ok=True)
    w(root, "Unity/Assets/Settings/Renderer.asset", renderer([("123", "MyFeature", G["feature_cs"]), ("456", "<empty>", ""),
                                                             ("789", "GoneFeature", G["missing_cs"])]))
    # 2b 同じ RP アセットに Forward の Renderer を足す（本線は Forward+）
    w(root, "Unity/Assets/Settings/Depth.asset", renderer([], mode=0))
    w(root, "Unity/Assets/Settings/Depth.asset.meta", meta(G["renderer2"]))
    rp = (U / "Assets/Settings/RP.asset").read_text(encoding="utf-8")
    w(root, "Unity/Assets/Settings/RP.asset", rp.replace("  m_DefaultRendererIndex: 0\n",
      f"  - {{fileID: 11400000, guid: {G['renderer2']}, type: 2}}\n  m_DefaultRendererIndex: 0\n"))
    # 3 存在しないビルドのシーン
    w(root, "Unity/ProjectSettings/EditorBuildSettings.asset", build_settings(extra_scene=True))
    # 4 版を固定していない git 参照（固定した物・タグの物は出てはいけない）/ 5 file: の先が無い
    m = json.loads((U / "Packages/manifest.json").read_text(encoding="utf-8"))
    m["dependencies"]["com.example.branch"] = "https://github.com/example/branch.git#master"
    m["dependencies"]["com.example.nover"] = "https://github.com/example/nover.git"
    m["dependencies"]["jp.example.gone"] = "file:../../Gone/jp.example.gone"
    w(root, "Unity/Packages/manifest.json", json.dumps(m, indent=2))
    # 6 DX12 が先頭 + AVPro / 7 runInBackground Off / 8 使われない define（BAR_USED は使われているので出てはいけない）
    w(root, "Unity/ProjectSettings/ProjectSettings.asset", player(apis="1200000002000000", run_bg=0, defines="BAR_USED;FOO_UNUSED"))
    (U / "Assets/AVProLiveCamera").mkdir(parents=True, exist_ok=True)
    # 9 同名の asmdef
    w(root, "Unity/Assets/Copy/Local.asmdef", json.dumps({"name": "Example.Local"}))
    # 10 GUID の重なり
    w(root, "Unity/Assets/Copy/Volume2.asset", HEAD)
    w(root, "Unity/Assets/Copy/Volume2.asset.meta", meta(G["volume"]))
    # 11 MCP の固定 URL
    w(root, ".mcp.json", json.dumps({"mcpServers": {"claude-code-mcp-unity": {"command": "node", "args": ["x/index.js"],
                                                                             "env": {"MCP_UNITY_HTTP_URL": "http://localhost:8090"}}}}))
    # 12 UnityEditor を参照して Windows のビルドに入る DLL
    w(root, "Unity/Assets/Plugins/Leaky.dll", b"MZ\x00\x00UnityEditor\x00", binary=True)
    w(root, "Unity/Assets/Plugins/Leaky.dll.meta", meta("f" * 32, "PluginImporter:\n  platformData:\n  - first:\n      Any: \n"
      "    second:\n      enabled: 1\n      settings: {}\n"))
    # 13 Quality の RP が見つからない
    w(root, "Unity/ProjectSettings/QualitySettings.asset", quality(G["missing_rp"]))
    # 13b Input System だけなのに旧 Input を呼ぶ（ENABLE_LEGACY_INPUT_MANAGER で囲んだ物・Editor の物・InputSystem の物は出てはいけない）
    w(root, "Unity/Assets/Scripts/OldInput.cs", "class OldInput { void Update() { if (Input.GetKeyDown(KeyCode.Space)) {} } }\n")
    w(root, "Unity/Assets/Scripts/Guarded.cs", "#if ENABLE_LEGACY_INPUT_MANAGER\nclass G { bool k = Input.GetKey(KeyCode.A); }\n#endif\n")
    w(root, "Unity/Assets/Scripts/Editor/EdInput.cs", "class E { bool k = Input.GetKey(KeyCode.A); }\n")
    w(root, "Unity/Assets/Scripts/NewInput.cs", "class N { bool k = UnityEngine.InputSystem.Keyboard.current.spaceKey.isPressed; }\n")
    # 14 先頭 / の無い .gitignore が深い所を隠す / 15 .sh が eol=lf でない
    w(root, ".gitignore", "/log/\nlog\n/Unity/[Ll]ibrary/\n")
    w(root, "Unity/Assets/Deep/log/keep.txt", "x")
    w(root, ".gitattributes", "*.png filter=lfs diff=lfs merge=lfs -text\n")
    # 16 50 MiB を超える blob が LFS でなく git に入る（GitHub の警告の境目を 1 MiB 超える大きさ）
    w(root, "Unity/Assets/Big/big.bin", b"\0" * (pa.GITHUB_WARN_BYTES + 1024 * 1024), binary=True)
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "broken")
    # 17 LFS のポインタのままの設定ファイル（コミットの後に置く。git には入れない）
    w(root, "Unity/ProjectSettings/TagManager.asset", "version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n")
    # 18 100 MiB を超える追跡外のファイル（日本語名。-z で問わないと引用符付きで返り、LFS の物まで出す）。.png は LFS 指定あり → 出てはいけない
    for name in ("大きい素材.bin", "大きい素材.png"):
        path = U / "Assets/Big" / name
        with open(path, "wb") as fh:
            fh.truncate(pa.GITHUB_BLOCK_BYTES + 1024 * 1024)  # 中身は要らない（大きさだけを見る）


def make_other_avpro(root):
    """DX12 が先頭で、Live Camera でない AVPro（AVPro Video など）だけがある案件 → WARN（ERROR ではない）。"""
    shutil.rmtree(root / "Unity/Assets/AVProLiveCamera")
    # clone の直後（PackageCache が無い）にスクリプトの見つからない Feature → パッケージ側かもしれないので WARN
    w(root, "Unity/Assets/Settings/Renderer.asset", renderer([("123", "MyFeature", G["feature_cs"]), ("789", "PkgFeature", G["missing_cs"])]))
    w(root, "Unity/Assets/AVProVideo/Runtime/MediaPlayer.cs", "class MediaPlayer {}\n")
    w(root, "Unity/ProjectSettings/ProjectSettings.asset", player(apis="1200000002000000"))


def make_nested_attributes(root):
    """.gitattributes が Unity フォルダの中にある案件。git ルートからでなく Unity から見たパスで問わないと *.unity が LFS 無しに見える。"""
    w(root, "Unity/.gitattributes", "*.unity filter=lfs diff=lfs merge=lfs -text\n")


EXPECT_BROKEN = {
    "renderer-empty-feature": "ERROR", "renderer-feature-missing-script": "ERROR", "build-scene-missing": "WARN",
    "git-unpinned": "WARN", "file-ref-missing": "ERROR", "avpro-dx12": "ERROR", "run-in-background": "WARN",
    "define-unused": "INFO", "asmdef-duplicate": "ERROR", "guid-duplicate": "WARN", "mcp-fixed-url": "WARN",
    "dll-editor-in-player": "WARN", "rp-missing": "ERROR", "gitignore-unanchored": "WARN", "sh-eol": "WARN",
    "large-in-git": "WARN", "unreadable": "ERROR", "renderer-mode-mixed": "WARN", "input-legacy-api": "WARN",
    "large-untracked-not-lfs": "WARN",
}


def main():
    keep = "--keep" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="project_audit_test_"))
    fails = []
    try:
        clean = tmp / "clean"
        make_clean(clean)
        snap_c, f_c = pa.check(clean)
        bad = [i for i in f_c.items if i["level"] in ("ERROR", "WARN")]
        if bad:
            fails.append("clean で ERROR/WARN が出た: " + json.dumps(bad, ensure_ascii=False))
        if [i["code"] for i in f_c.items] != ["git-overridden-by-embedded"]:
            fails.append("clean の INFO が想定（git-overridden-by-embedded 1 件）と違う: " + ", ".join(i["code"] for i in f_c.items))
        print(f"clean: {len(f_c.items)} 件（ERROR/WARN {len(bad)}）: " + ", ".join(i["code"] for i in f_c.items))
        # templates/Editor/ProjectSetupApply.cs が読む鍵と型（snapshot の形を変えたらここも Apply も直す）
        contract = [
            (("player", "graphicsApis", "WindowsStandaloneSupport", "apis"), list), (("player", "graphicsApis", "WindowsStandaloneSupport", "automatic"), bool),
            (("player", "colorSpace"), str), (("player", "runInBackground"), bool), (("player", "visibleInBackground"), bool),
            (("player", "apiCompatibility", "Standalone"), str), (("player", "scriptingBackend", "Standalone"), str),
            (("player", "activeInputHandler"), int), (("player", "defines", "Standalone"), list),
            (("editor", "enterPlayModeOptionsEnabled"), bool), (("editor", "enterPlayModeOptions"), int),
            (("tags", "layers"), dict), (("tags", "renderingLayers"), dict),
            (("renderPipelines", "qualityLevels"), list), (("renderPipelines", "graphicsDefault"), str),
        ]
        for path, typ in contract:
            cur = snap_c
            for k in path:
                cur = cur.get(k) if isinstance(cur, dict) else None
            if not isinstance(cur, typ) or isinstance(cur, bool) and typ is int:
                fails.append(f"snapshot の {'.'.join(path)} が {typ.__name__} でない: {cur!r}")
        lv = snap_c["renderPipelines"]["qualityLevels"][0]
        if not (isinstance(lv.get("name"), str) and str(lv.get("renderPipeline", "")).startswith("Assets/")):
            fails.append(f"qualityLevels の name / renderPipeline（Assets/ からのパス）の形が違う: {lv}")

        broken = tmp / "broken"
        shutil.copytree(clean, broken)
        make_broken(broken)
        snap_b, f_b = pa.check(broken)
        got = {}
        for i in f_b.items:
            got.setdefault(i["code"], set()).add(i["level"])
        for code, level in EXPECT_BROKEN.items():
            if level not in got.get(code, set()):
                fails.append(f"broken で {code}（{level}）が出ない")
        unpinned = [i["message"] for i in f_b.items if i["code"] == "git-unpinned"]
        if any("pinned" in m.split(":")[0] or "tagged" in m.split(":")[0] for m in unpinned) or len(unpinned) != 2:
            fails.append("git-unpinned の対象がずれた: " + "; ".join(unpinned))
        unused = [i["message"] for i in f_b.items if i["code"] == "define-unused"]
        if any("BAR_USED" in m for m in unused):
            fails.append("使っている define を未使用と出した")
        if any(i["code"] == "dll-editor-in-player" and "EdOnly" in i["message"] for i in f_b.items):
            fails.append("Editor 専用の DLL を出した")
        legacy = [i["message"] for i in f_b.items if i["code"] == "input-legacy-api"]
        if legacy and ("1 本" not in legacy[0] or "OldInput.cs" not in legacy[0]):
            fails.append("旧 Input の対象がずれた（OldInput.cs だけのはず）: " + legacy[0])
        empty = [i for i in f_b.items if i["code"] == "renderer-empty-feature"]
        if len(empty) != 1:
            fails.append(f"同じ Renderer の空要素が {len(empty)} 回出た（RP アセット 2 つから使われていても 1 回）")
        if empty and "m_RendererFeatures[1]" not in empty[0]["message"]:
            fails.append("空要素の位置がずれた: " + empty[0]["message"])
        big = [i["message"] for i in f_b.items if i["code"] == "large-untracked-not-lfs"]
        if len(big) != 1 or "大きい素材.bin" not in big[0]:
            fails.append("100 MiB 超の追跡外の対象がずれた（LFS 指定の無い 大きい素材.bin だけのはず）: " + "; ".join(big))
        # clean にもある INFO だけを許す。それ以外は誤検出
        extra = sorted(set(got) - set(EXPECT_BROKEN) - {"git-overridden-by-embedded"})
        if extra:
            fails.append("broken で想定外の code: " + ", ".join(extra))
        print(f"broken: {len(f_b.items)} 件。想定外の code: {extra or 'なし'}")

        other = tmp / "other"
        shutil.copytree(clean, other)
        make_other_avpro(other)
        _, f_o = pa.check(other)
        av = [(i["level"], i["message"]) for i in f_o.items if i["code"] == "avpro-dx12"]
        if [lv for lv, _ in av] != ["WARN"]:
            fails.append(f"Live Camera でない AVPro + DX12 先頭が WARN 1 件にならない: {av}")
        miss = [i["level"] for i in f_o.items if i["code"] == "renderer-feature-missing-script"]
        if miss != ["WARN"]:
            fails.append(f"PackageCache が無いときのスクリプトの無い Feature が WARN 1 件にならない: {miss}")
        print(f"other: avpro-dx12 {[lv for lv, _ in av]}")

        nested = tmp / "nested"
        shutil.copytree(clean, nested)
        make_nested_attributes(nested)
        snap_n, _ = pa.snapshot(nested)
        unity_attr = (snap_n.get("git") or {}).get("attributes", {}).get("*.unity", "")
        if "filter=lfs" not in unity_attr:
            fails.append(f"Unity フォルダの中の .gitattributes が効いていない（*.unity = {unity_attr!r}）")
        print(f"nested: *.unity = {unity_attr}")

        # compare: 同じ物どうしは差が 0、clean と broken は揃えるべき所の差が出る
        same = pa.compare(snap_c, json.loads(json.dumps(snap_c)))
        if same:
            fails.append(f"同じ snapshot どうしで差が出た: {same[:3]}")
        rows = pa.compare(snap_c, snap_b)
        keys = {r["key"]: r["category"] for r in rows}
        for k in ("player.graphicsApis.WindowsStandaloneSupport.apis", "player.runInBackground"):
            if keys.get(k) != "align":
                fails.append(f"compare で {k} が align に出ない（{keys.get(k)}）")
        if not any(k.startswith("player.defines") and c == "imports" for k, c in keys.items()):
            fails.append("compare で define の差が imports に出ない")
        print(f"compare: 同じ物 {len(same)} 件 / clean と broken {len(rows)} 件")
    finally:
        if keep:
            print("残した:", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("\nFAIL")
        for x in fails:
            print(" -", x)
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
