// プロジェクト設定を Editor の API で当てる（vortex-project-setup）。
// 使うとき: 案件の Assets/_TempVerify/Editor/ へ写し、Library/ScriptAssemblies/Assembly-CSharp-Editor.dll の時刻でコンパイルを確かめてから
// Unity MCP の invoke_method で呼ぶ。終わったら _TempVerify ごと消す（写し元は ~/.claude/skills/vortex-project-setup/templates/Editor）。
// ここは Unity プロジェクトの外の写し元で、Editor フォルダへ写してから使う（trap-ok:cs-runtime-unityeditor）。
//
// 起動中の Unity の ProjectSettings/*.asset を文字で書き換えると、メモリ側の値で保存し直されて戻る（traps unity-editor）。
// ここでは PlayerSettings・EditorSettings・GraphicsSettings の API と、TagManager・QualitySettings・PlayerSettings の SerializedObject で書き、
// 最後に AssetDatabase.SaveAssets で保存する。Undo は積まない。どの関数も「変える前・変えた後」を JSON で返す。
//
// 入口（invoke_method の methodName。引数の数で選ばれるので同じ名前の重ね書きはしない）:
//   Read()                                   今の値（snapshot と同じ鍵の名前）
//   Plan(snapshotJson, sections)             snapshot の値と今の値の差だけを返す（変えない）
//   Apply(snapshotJson, sections)            snapshot の値を当てる。sections は "all" か下の名前のカンマ区切り
//       graphicsApi, colorSpace, background, apiCompatibility, scriptingBackend, inputHandler, enterPlayMode,
//       layers, renderingLayers, renderPipelines, defines
//       "all" は defines を含まない（define は取り込み物しだいで、無いアセットの define を足すとコンパイルが壊れる）。define は名前で指定する
//       layers / renderingLayers は空きか同じ名前の枠だけ書く。別の名前が入っている枠は conflict と返して変えない（SetLayer で上書きする）
//       renderPipelines の RP アセットは、このプロジェクトに同じパスで入っていること（無ければ error。コピーは先に済ませる）
//   SetProductInfo("ShinkaiFes2026", "")    Product Name・Company Name（空は変えない）
//   SetWindowsGraphicsApis("Direct3D11,Direct3D12") / SetColorSpace("Linear") / SetBackground(true, true)
//   SetDefines("A;B") / AddDefines("A;B") / RemoveDefines("A;B")         いずれも Standalone
//   SetApiCompatibility("NET_Standard") / SetScriptingBackend("Mono2x") / SetActiveInputHandler(1)
//   SetEnterPlayMode(true, 0) / SetLayer(3, "Chara", false) / SetRenderingLayer(1, "Character", false)
//   SetQualityRenderPipeline("PC", "Assets/00_Settings/PC_RPAsset.asset") / SetDefaultRenderPipeline("Assets/...")
//   RemoveEmptyRendererFeatures("Assets/.../Renderer.asset", apply)     m_RendererFeatures の空要素（{fileID: 0}）と Map の同じ位置を外す
//
// 依存: Newtonsoft.Json（com.unity.nuget.newtonsoft-json。jp.pjblue.realtime-live-utility の依存に入っている）。URP の型は使わない。
// activeInputHandler の書き先は com.unity.inputsystem 1.17 の EditorPlayerSettingHelpers と同じ（Unity 6 は BuildProfile の
// s_GlobalPlayerSettings。Build Profile が Player Settings を上書きしていればそちら）。
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEngine;
using UnityEngine.Rendering;
#if UNITY_6000_0_OR_NEWER
using UnityEditor.Build.Profile;
#endif

public static class ProjectSetupApply
{
    const string WindowsTargetKey = "WindowsStandaloneSupport"; // ProjectSettings.asset の m_BuildTarget の名前
    static readonly string[] AllSections =
    {
        "graphicsApi", "colorSpace", "background", "apiCompatibility", "scriptingBackend", "inputHandler", "enterPlayMode",
        "layers", "renderingLayers", "renderPipelines",
    };
    // TagManager の layers で Unity が名前を決めている枠（Default・TransparentFX・Ignore Raycast・Water・UI）
    static readonly int[] BuiltinLayers = { 0, 1, 2, 4, 5 };
    // m_RenderingLayers の 0 番（Default）は名前を変えられない
    const int BuiltinRenderingLayer = 0;
    // InputHandler（com.unity.inputsystem の EditorPlayerSettingHelpers.InputHandler と同じ値）
    static readonly string[] InputHandlerNames = { "InputManager", "InputSystem", "Both" };

    class Report
    {
        readonly JArray _rows = new JArray();
        public bool Apply;
        public void Add(string section, string key, object before, object after, string status, string note = null)
        {
            var o = new JObject { ["section"] = section, ["key"] = key, ["before"] = Tok(before), ["after"] = Tok(after), ["status"] = status };
            if (!string.IsNullOrEmpty(note)) o["note"] = note;
            _rows.Add(o);
        }
        public int Count(string status) => _rows.Count(r => (string)r["status"] == status);
        public string Json(bool saved)
        {
            var o = new JObject
            {
                ["apply"] = Apply,
                ["saved"] = saved,
                ["counts"] = new JObject
                {
                    ["same"] = Count("same"), ["change"] = Count("change"), ["applied"] = Count("applied"),
                    ["conflict"] = Count("conflict"), ["error"] = Count("error"), ["skip"] = Count("skip"),
                },
                ["rows"] = _rows,
            };
            return o.ToString(Formatting.Indented);
        }
        static JToken Tok(object v) => v == null ? JValue.CreateNull() : v is JToken t ? t : JToken.FromObject(v);
    }

    // ---- 読む --------------------------------------------------------------------------------------
    public static string Read()
    {
        var o = new JObject
        {
            ["unityVersion"] = Application.unityVersion,
            ["editorGraphicsDevice"] = SystemInfo.graphicsDeviceType.ToString(),
            ["player"] = new JObject
            {
                ["productName"] = PlayerSettings.productName,
                ["companyName"] = PlayerSettings.companyName,
                ["graphicsApis"] = new JObject
                {
                    [WindowsTargetKey] = new JObject
                    {
                        ["apis"] = new JArray(PlayerSettings.GetGraphicsAPIs(BuildTarget.StandaloneWindows64).Select(a => a.ToString())),
                        ["automatic"] = PlayerSettings.GetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64),
                    },
                },
                ["colorSpace"] = PlayerSettings.colorSpace.ToString(),
                ["runInBackground"] = PlayerSettings.runInBackground,
                ["visibleInBackground"] = PlayerSettings.visibleInBackground,
                ["fullscreenMode"] = PlayerSettings.fullScreenMode.ToString(),
                ["activeInputHandler"] = ReadInputHandler(out var where),
                ["activeInputHandlerTarget"] = where,
                ["apiCompatibility"] = new JObject { ["Standalone"] = PlayerSettings.GetApiCompatibilityLevel(NamedBuildTarget.Standalone).ToString() },
                ["scriptingBackend"] = new JObject { ["Standalone"] = PlayerSettings.GetScriptingBackend(NamedBuildTarget.Standalone).ToString() },
                ["defines"] = new JObject { ["Standalone"] = new JArray(SplitDefines(PlayerSettings.GetScriptingDefineSymbols(NamedBuildTarget.Standalone))) },
            },
            ["editor"] = new JObject
            {
                ["enterPlayModeOptionsEnabled"] = EditorSettings.enterPlayModeOptionsEnabled,
                ["enterPlayModeOptions"] = (int)EditorSettings.enterPlayModeOptions,
            },
            ["tags"] = new JObject
            {
                ["layers"] = NamesObject(TagManager().FindProperty("layers")),
                ["renderingLayers"] = NamesObject(TagManager().FindProperty("m_RenderingLayers")),
            },
            ["renderPipelines"] = new JObject
            {
                ["graphicsDefault"] = AssetPath(GraphicsSettings.defaultRenderPipeline),
                ["qualityLevels"] = new JArray(QualitySettings.names.Select((n, i) => new JObject
                {
                    ["name"] = n,
                    ["renderPipeline"] = AssetPath(QualitySettings.GetRenderPipelineAssetAt(i)),
                })),
            },
        };
        return o.ToString(Formatting.Indented);
    }

    // ---- snapshot から当てる ---------------------------------------------------------------------------
    public static string Plan(string snapshotJson, string sections) => Run(snapshotJson, sections, false);

    public static string Apply(string snapshotJson, string sections) => Run(snapshotJson, sections, true);

    static string Run(string snapshotJson, string sections, bool apply)
    {
        var r = new Report { Apply = apply };
        JObject snap;
        try
        {
            snap = JObject.Parse(File.ReadAllText(snapshotJson));
        }
        catch (Exception e)
        {
            r.Add("input", snapshotJson, null, null, "error", e.Message);
            return r.Json(false);
        }
        var want = ParseSections(sections, r);
        var player = snap["player"] as JObject ?? new JObject();
        var editor = snap["editor"] as JObject ?? new JObject();
        var tags = snap["tags"] as JObject ?? new JObject();
        var rp = snap["renderPipelines"] as JObject ?? new JObject();

        if (want.Contains("graphicsApi"))
        {
            var w = player["graphicsApis"]?[WindowsTargetKey];
            if (w == null) r.Add("graphicsApi", WindowsTargetKey, null, null, "skip", "snapshot に Windows の値が無い");
            else GraphicsApis(r, w["apis"]?.Values<string>().ToArray() ?? new string[0], (bool?)w["automatic"] ?? false, apply);
        }
        if (want.Contains("colorSpace") && Has(player["colorSpace"])) ColorSpaceStep(r, (string)player["colorSpace"], apply);
        if (want.Contains("background"))
        {
            if (Has(player["runInBackground"])) Bool(r, "background", "runInBackground", PlayerSettings.runInBackground, (bool)player["runInBackground"], v => PlayerSettings.runInBackground = v, apply);
            if (Has(player["visibleInBackground"])) Bool(r, "background", "visibleInBackground", PlayerSettings.visibleInBackground, (bool)player["visibleInBackground"], v => PlayerSettings.visibleInBackground = v, apply);
        }
        if (want.Contains("apiCompatibility") && Has(player["apiCompatibility"]?["Standalone"]))
            ApiCompat(r, (string)player["apiCompatibility"]["Standalone"], apply);
        if (want.Contains("scriptingBackend") && Has(player["scriptingBackend"]?["Standalone"]))
            Backend(r, (string)player["scriptingBackend"]["Standalone"], apply);
        if (want.Contains("inputHandler") && player["activeInputHandler"] != null && player["activeInputHandler"].Type == JTokenType.Integer)
            InputHandler(r, (int)player["activeInputHandler"], apply);
        if (want.Contains("enterPlayMode") && Has(editor["enterPlayModeOptionsEnabled"]))
            EnterPlayMode(r, (bool)editor["enterPlayModeOptionsEnabled"], (int?)editor["enterPlayModeOptions"] ?? 0, apply);
        if (want.Contains("layers") && tags["layers"] is JObject layers)
            foreach (var p in layers.Properties()) Layer(r, "layers", "layers", int.Parse(p.Name), (string)p.Value, false, apply);
        if (want.Contains("renderingLayers") && tags["renderingLayers"] is JObject rls)
            foreach (var p in rls.Properties()) Layer(r, "renderingLayers", "m_RenderingLayers", int.Parse(p.Name), (string)p.Value, false, apply);
        if (want.Contains("renderPipelines"))
        {
            // snapshot で未設定（null）の所は変えない（既定の RP を空にすると Built-in に戻る）。見つからなかった参照も写さない
            if (rp["qualityLevels"] is JArray levels)
                foreach (var lv in levels)
                {
                    if (!Has(lv["renderPipeline"]) || IsMissing((string)lv["renderPipeline"]))
                        r.Add("renderPipelines", "quality " + (string)lv["name"], null, (string)lv["renderPipeline"], "skip", "snapshot で未設定か見つからない参照");
                    else
                        QualityRp(r, (string)lv["name"], (string)lv["renderPipeline"], apply);
                }
            if (!Has(rp["graphicsDefault"]) || IsMissing((string)rp["graphicsDefault"]))
                r.Add("renderPipelines", "graphicsDefault", null, (string)rp["graphicsDefault"], "skip", "snapshot で未設定か見つからない参照");
            else
                DefaultRp(r, (string)rp["graphicsDefault"], apply);
        }
        if (want.Contains("defines") && player["defines"]?["Standalone"] is JArray defs)
            Defines(r, defs.Values<string>().ToArray(), apply);

        return Finish(r, apply);
    }

    static HashSet<string> ParseSections(string sections, Report r)
    {
        var set = new HashSet<string>();
        foreach (var raw in (sections ?? "all").Split(new[] { ',', ' ' }, StringSplitOptions.RemoveEmptyEntries))
        {
            if (raw == "all") set.UnionWith(AllSections);
            else if (raw == "defines" || AllSections.Contains(raw)) set.Add(raw);
            else r.Add("input", "sections", raw, null, "error", "知らない名前: " + string.Join(", ", AllSections) + ", defines のどれか");
        }
        return set;
    }

    static string Finish(Report r, bool apply)
    {
        var saved = false;
        if (apply && r.Count("applied") > 0)
        {
            AssetDatabase.SaveAssets();
            saved = true;
        }
        Debug.Log($"[ProjectSetupApply] {(apply ? "apply" : "plan")}: applied {r.Count("applied")} / change {r.Count("change")} / conflict {r.Count("conflict")} / error {r.Count("error")}");
        return r.Json(saved);
    }

    // ---- 個別の設定（引数から） ------------------------------------------------------------------------
    public static string SetWindowsGraphicsApis(string csv)
    {
        var r = new Report { Apply = true };
        GraphicsApis(r, (csv ?? "").Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries), false, true);
        return Finish(r, true);
    }

    /// <summary>Product Name・Company Name（基準の ProjectSettings を写して作ったときに、案件の名前へ直す）。空の引数は変えない。</summary>
    public static string SetProductInfo(string productName, string companyName)
    {
        var r = new Report { Apply = true };
        if (!string.IsNullOrEmpty(productName))
            Text(r, "product", "productName", PlayerSettings.productName, productName, v => PlayerSettings.productName = v);
        if (!string.IsNullOrEmpty(companyName))
            Text(r, "product", "companyName", PlayerSettings.companyName, companyName, v => PlayerSettings.companyName = v);
        return Finish(r, true);
    }

    static void Text(Report r, string section, string key, string before, string after, Action<string> set)
    {
        if (before == after) { r.Add(section, key, before, after, "same"); return; }
        set(after);
        r.Add(section, key, before, after, "applied");
    }

    public static string SetColorSpace(string name)
    {
        var r = new Report { Apply = true };
        ColorSpaceStep(r, name, true);
        return Finish(r, true);
    }

    public static string SetBackground(bool runInBackground, bool visibleInBackground)
    {
        var r = new Report { Apply = true };
        Bool(r, "background", "runInBackground", PlayerSettings.runInBackground, runInBackground, v => PlayerSettings.runInBackground = v, true);
        Bool(r, "background", "visibleInBackground", PlayerSettings.visibleInBackground, visibleInBackground, v => PlayerSettings.visibleInBackground = v, true);
        return Finish(r, true);
    }

    public static string SetDefines(string symbols)
    {
        var r = new Report { Apply = true };
        Defines(r, SplitDefines(symbols), true);
        return Finish(r, true);
    }

    public static string AddDefines(string symbols)
    {
        var now = SplitDefines(PlayerSettings.GetScriptingDefineSymbols(NamedBuildTarget.Standalone)).ToList();
        foreach (var s in SplitDefines(symbols))
            if (!now.Contains(s)) now.Add(s);
        return SetDefines(string.Join(";", now));
    }

    public static string RemoveDefines(string symbols)
    {
        var drop = new HashSet<string>(SplitDefines(symbols));
        var now = SplitDefines(PlayerSettings.GetScriptingDefineSymbols(NamedBuildTarget.Standalone)).Where(s => !drop.Contains(s));
        return SetDefines(string.Join(";", now));
    }

    public static string SetApiCompatibility(string level)
    {
        var r = new Report { Apply = true };
        ApiCompat(r, level, true);
        return Finish(r, true);
    }

    public static string SetScriptingBackend(string backend)
    {
        var r = new Report { Apply = true };
        Backend(r, backend, true);
        return Finish(r, true);
    }

    public static string SetActiveInputHandler(int value)
    {
        var r = new Report { Apply = true };
        InputHandler(r, value, true);
        return Finish(r, true);
    }

    public static string SetEnterPlayMode(bool enabled, int options)
    {
        var r = new Report { Apply = true };
        EnterPlayMode(r, enabled, options, true);
        return Finish(r, true);
    }

    public static string SetLayer(int index, string name, bool overwrite)
    {
        var r = new Report { Apply = true };
        Layer(r, "layers", "layers", index, name, overwrite, true);
        return Finish(r, true);
    }

    public static string SetRenderingLayer(int index, string name, bool overwrite)
    {
        var r = new Report { Apply = true };
        Layer(r, "renderingLayers", "m_RenderingLayers", index, name, overwrite, true);
        return Finish(r, true);
    }

    public static string SetQualityRenderPipeline(string levelName, string assetPath)
    {
        var r = new Report { Apply = true };
        QualityRp(r, levelName, assetPath, true);
        return Finish(r, true);
    }

    public static string SetDefaultRenderPipeline(string assetPath)
    {
        var r = new Report { Apply = true };
        DefaultRp(r, assetPath, true);
        return Finish(r, true);
    }

    /// <summary>
    /// Renderer（ScriptableRendererData）の m_RendererFeatures から空要素（{fileID: 0}）を外し、m_RendererFeatureMap の同じ位置も外す。
    /// 空要素があるとビルドの URP の GatherShaderFeatures が NRE を出し、バリアントの間引きが止まる（SinkaiFes2026 cf636af9）。
    /// apply = false なら見るだけ。スクリプトが無くなった Feature（参照先の塊はある）は空要素ではないので外さない。
    /// </summary>
    public static string RemoveEmptyRendererFeatures(string rendererPath, bool apply)
    {
        var r = new Report { Apply = apply };
        var data = AssetDatabase.LoadMainAssetAtPath(rendererPath) as ScriptableObject;
        if (data == null)
        {
            r.Add("renderer", rendererPath, null, null, "error", "Renderer のアセットを読めない");
            return r.Json(false);
        }
        var so = new SerializedObject(data);
        var list = so.FindProperty("m_RendererFeatures");
        var map = so.FindProperty("m_RendererFeatureMap");
        if (list == null || map == null || !list.isArray || !map.isArray)
        {
            r.Add("renderer", rendererPath, null, null, "error", "m_RendererFeatures / m_RendererFeatureMap が無い（ScriptableRendererData ではない）");
            return r.Json(false);
        }
        if (list.arraySize != map.arraySize)
        {
            r.Add("renderer", rendererPath, list.arraySize, map.arraySize, "error", "一覧と Map の数が合わない。どこを外すか決められないので触らない");
            return r.Json(false);
        }
        var empty = new List<int>();
        for (var i = 0; i < list.arraySize; i++)
        {
            var e = list.GetArrayElementAtIndex(i);
            if (e.objectReferenceValue == null && e.objectReferenceInstanceIDValue == 0) empty.Add(i);
        }
        var before = Describe(list);
        if (empty.Count == 0)
        {
            r.Add("renderer", rendererPath, before, before, "same", "空要素は無い");
            return r.Json(false);
        }
        if (!apply)
        {
            r.Add("renderer", rendererPath, before, "外す位置: " + string.Join(",", empty), "change");
            return r.Json(false);
        }
        for (var k = empty.Count - 1; k >= 0; k--)
        {
            var i = empty[k];
            var n = list.arraySize;
            // null の要素は 1 回で消える（null でない参照の要素だけ、1 回目は null にするだけ）
            list.DeleteArrayElementAtIndex(i);
            map.DeleteArrayElementAtIndex(i);
            if (list.arraySize != n - 1 || map.arraySize != n - 1)
            {
                r.Add("renderer", rendererPath, n, list.arraySize, "error", $"[{i}] を外せなかった（保存しない）");
                return r.Json(false);
            }
        }
        so.ApplyModifiedPropertiesWithoutUndo();
        EditorUtility.SetDirty(data);
        AssetDatabase.SaveAssetIfDirty(data);
        r.Add("renderer", rendererPath, before, Describe(new SerializedObject(data).FindProperty("m_RendererFeatures")), "applied",
            "外した位置: " + string.Join(",", empty));
        return r.Json(true);
    }

    static string Describe(SerializedProperty list)
    {
        var names = new List<string>();
        for (var i = 0; i < list.arraySize; i++)
        {
            var o = list.GetArrayElementAtIndex(i).objectReferenceValue;
            names.Add(o != null ? o.name : list.GetArrayElementAtIndex(i).objectReferenceInstanceIDValue != 0 ? "(missing script)" : "<empty>");
        }
        return string.Join(" / ", names);
    }

    // ---- 各設定の中身 ------------------------------------------------------------------------------
    static void GraphicsApis(Report r, string[] names, bool automatic, bool apply)
    {
        var t = BuildTarget.StandaloneWindows64;
        var beforeAuto = PlayerSettings.GetUseDefaultGraphicsAPIs(t);
        var before = string.Join(",", PlayerSettings.GetGraphicsAPIs(t)) + (beforeAuto ? " (automatic)" : "");
        var apis = new List<GraphicsDeviceType>();
        foreach (var n in names)
        {
            if (!Enum.TryParse(n, out GraphicsDeviceType d))
            {
                r.Add("graphicsApi", "Windows", before, n, "error", "GraphicsDeviceType に無い名前");
                return;
            }
            apis.Add(d);
        }
        var after = automatic ? "(automatic)" : string.Join(",", apis);
        var same = automatic ? beforeAuto : !beforeAuto && PlayerSettings.GetGraphicsAPIs(t).SequenceEqual(apis);
        if (same)
        {
            r.Add("graphicsApi", "Windows", before, before, "same");
            return;
        }
        if (!automatic && apis.Count == 0)
        {
            r.Add("graphicsApi", "Windows", before, after, "error", "API の並びが空");
            return;
        }
        if (!apply)
        {
            r.Add("graphicsApi", "Windows", before, after, "change");
            return;
        }
        PlayerSettings.SetUseDefaultGraphicsAPIs(t, automatic);
        if (!automatic) PlayerSettings.SetGraphicsAPIs(t, apis.ToArray());
        var now = string.Join(",", PlayerSettings.GetGraphicsAPIs(t)) + (PlayerSettings.GetUseDefaultGraphicsAPIs(t) ? " (automatic)" : "");
        r.Add("graphicsApi", "Windows", before, now, "applied",
            $"エディタは今 {SystemInfo.graphicsDeviceType} で動いている。先頭を変えたなら、エディタの API は Unity を開き直したときに変わる");
    }

    static void ColorSpaceStep(Report r, string name, bool apply)
    {
        var before = PlayerSettings.colorSpace;
        if (!Enum.TryParse(name, out ColorSpace cs) || cs == ColorSpace.Uninitialized)
        {
            r.Add("colorSpace", "colorSpace", before.ToString(), name, "error", "Gamma か Linear");
            return;
        }
        if (cs == before) { r.Add("colorSpace", "colorSpace", before.ToString(), cs.ToString(), "same"); return; }
        if (!apply) { r.Add("colorSpace", "colorSpace", before.ToString(), cs.ToString(), "change", "変えるとテクスチャを全部取り込み直す"); return; }
        PlayerSettings.colorSpace = cs;
        r.Add("colorSpace", "colorSpace", before.ToString(), PlayerSettings.colorSpace.ToString(), "applied");
    }

    static void Bool(Report r, string section, string key, bool before, bool after, Action<bool> set, bool apply)
    {
        if (before == after) { r.Add(section, key, before, after, "same"); return; }
        if (!apply) { r.Add(section, key, before, after, "change"); return; }
        set(after);
        r.Add(section, key, before, after, "applied");
    }

    static void ApiCompat(Report r, string name, bool apply)
    {
        var before = PlayerSettings.GetApiCompatibilityLevel(NamedBuildTarget.Standalone);
        if (!Enum.TryParse(name, out ApiCompatibilityLevel level))
        {
            r.Add("apiCompatibility", "Standalone", before.ToString(), name, "error", "ApiCompatibilityLevel に無い名前（NET_Standard / NET_Unity_4_8）");
            return;
        }
        if (level == before) { r.Add("apiCompatibility", "Standalone", before.ToString(), level.ToString(), "same"); return; }
        if (!apply) { r.Add("apiCompatibility", "Standalone", before.ToString(), level.ToString(), "change"); return; }
        PlayerSettings.SetApiCompatibilityLevel(NamedBuildTarget.Standalone, level);
        r.Add("apiCompatibility", "Standalone", before.ToString(), PlayerSettings.GetApiCompatibilityLevel(NamedBuildTarget.Standalone).ToString(), "applied");
    }

    static void Backend(Report r, string name, bool apply)
    {
        var before = PlayerSettings.GetScriptingBackend(NamedBuildTarget.Standalone);
        if (!Enum.TryParse(name, out ScriptingImplementation impl))
        {
            r.Add("scriptingBackend", "Standalone", before.ToString(), name, "error", "ScriptingImplementation に無い名前（Mono2x / IL2CPP）");
            return;
        }
        if (impl == before) { r.Add("scriptingBackend", "Standalone", before.ToString(), impl.ToString(), "same"); return; }
        if (!apply) { r.Add("scriptingBackend", "Standalone", before.ToString(), impl.ToString(), "change"); return; }
        PlayerSettings.SetScriptingBackend(NamedBuildTarget.Standalone, impl);
        r.Add("scriptingBackend", "Standalone", before.ToString(), PlayerSettings.GetScriptingBackend(NamedBuildTarget.Standalone).ToString(), "applied");
    }

    static void Defines(Report r, string[] want, bool apply)
    {
        var before = PlayerSettings.GetScriptingDefineSymbols(NamedBuildTarget.Standalone);
        var after = string.Join(";", want.Where(s => !string.IsNullOrWhiteSpace(s)).Select(s => s.Trim()).Distinct());
        if (SplitDefines(before).SequenceEqual(SplitDefines(after))) { r.Add("defines", "Standalone", before, after, "same"); return; }
        if (!apply) { r.Add("defines", "Standalone", before, after, "change", "取り込み物に無い define を足すとコンパイルが壊れることがある"); return; }
        PlayerSettings.SetScriptingDefineSymbols(NamedBuildTarget.Standalone, after);
        r.Add("defines", "Standalone", before, PlayerSettings.GetScriptingDefineSymbols(NamedBuildTarget.Standalone), "applied", "スクリプトがコンパイルし直される");
    }

    static void InputHandler(Report r, int value, bool apply)
    {
        int before;
        string where;
        SerializedObject so;
        try
        {
            so = PlayerSettingsObject(out where);
            before = so.FindProperty("activeInputHandler").intValue;
        }
        catch (Exception e)
        {
            r.Add("inputHandler", "activeInputHandler", null, value, "error", e.Message);
            return;
        }
        if (value < 0 || value >= InputHandlerNames.Length)
        {
            r.Add("inputHandler", "activeInputHandler", before, value, "error", "0 = InputManager / 1 = InputSystem / 2 = Both");
            return;
        }
        var note = $"{InputHandlerNames[before]} → {InputHandlerNames[value]}（書き先: {where}）";
        if (before == value) { r.Add("inputHandler", "activeInputHandler", before, value, "same", note); return; }
        if (!apply) { r.Add("inputHandler", "activeInputHandler", before, value, "change", note + "。変えると Unity の再起動が要る"); return; }
        so.FindProperty("activeInputHandler").intValue = value;
        so.ApplyModifiedPropertiesWithoutUndo();
        r.Add("inputHandler", "activeInputHandler", before, PlayerSettingsObject(out _).FindProperty("activeInputHandler").intValue, "applied",
            note + "。Unity を開き直すまで入力の仕組みは切り替わらない");
    }

    static int ReadInputHandler(out string where)
    {
        try
        {
            return PlayerSettingsObject(out where).FindProperty("activeInputHandler").intValue;
        }
        catch (Exception e)
        {
            where = "error: " + e.Message;
            return -1;
        }
    }

    static SerializedObject PlayerSettingsObject(out string where)
    {
        UnityEngine.Object ps;
#if UNITY_6000_0_OR_NEWER
        var global = typeof(BuildProfile).GetField("s_GlobalPlayerSettings", BindingFlags.Static | BindingFlags.NonPublic);
        if (global == null)
            throw new InvalidOperationException("BuildProfile.s_GlobalPlayerSettings が無い（Unity の版で変わった。com.unity.inputsystem の EditorPlayerSettingHelpers に合わせる）");
        ps = global.GetValue(null) as UnityEngine.Object;
        where = "global";
        var active = BuildProfile.GetActiveBuildProfile();
        if (active != null)
        {
            var field = typeof(BuildProfile).GetField("m_PlayerSettings", BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null)
                throw new InvalidOperationException("BuildProfile.m_PlayerSettings が無い（Unity の版で変わった）");
            if (field.GetValue(active) is UnityEngine.Object over && over != null)
            {
                ps = over;
                where = "build profile " + active.name;
            }
        }
#else
        ps = Resources.FindObjectsOfTypeAll<PlayerSettings>().FirstOrDefault();
        where = "global";
#endif
        if (ps == null) throw new InvalidOperationException("PlayerSettings の実体が見つからない");
        var so = new SerializedObject(ps);
        if (so.FindProperty("activeInputHandler") == null) throw new InvalidOperationException("PlayerSettings に activeInputHandler が無い");
        return so;
    }

    static void EnterPlayMode(Report r, bool enabled, int options, bool apply)
    {
        var beforeEnabled = EditorSettings.enterPlayModeOptionsEnabled;
        var beforeOptions = (int)EditorSettings.enterPlayModeOptions;
        var before = $"{beforeEnabled}/{beforeOptions}";
        var after = $"{enabled}/{options}";
        // 効き目で比べる。Options が無効なら、Options の値に関係なくドメインもシーンも読み直す（= Options 0 と同じ）。
        // Unity 6.3 はファイルが m_EnterPlayModeOptionsEnabled: 1 / m_EnterPlayModeOptions: 0 でも API が False/0 を返す（2026-10-19 SinkaiFes2026 で実測）。
        int Effective(bool en, int opt) => en ? opt : 0;
        if (Effective(beforeEnabled, beforeOptions) == Effective(enabled, options))
        {
            r.Add("enterPlayMode", "enabled/options", before, after, "same", before == after ? null : "効き目は同じ（どちらもドメインとシーンを読み直す）");
            return;
        }
        if (!apply) { r.Add("enterPlayMode", "enabled/options", before, after, "change"); return; }
        EditorSettings.enterPlayModeOptionsEnabled = enabled;
        EditorSettings.enterPlayModeOptions = (EnterPlayModeOptions)options;
        r.Add("enterPlayMode", "enabled/options", before, $"{EditorSettings.enterPlayModeOptionsEnabled}/{(int)EditorSettings.enterPlayModeOptions}", "applied");
    }

    static SerializedObject TagManager() => new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset")[0]);

    static void Layer(Report r, string section, string prop, int index, string name, bool overwrite, bool apply)
    {
        var so = TagManager();
        var arr = so.FindProperty(prop);
        var key = $"{prop}[{index}]";
        if (arr == null || !arr.isArray) { r.Add(section, key, null, name, "error", $"TagManager に {prop} が無い"); return; }
        var isLayer = prop == "layers";
        if (IsDefaultRenderingLayerName(prop, index, name))
        {
            r.Add(section, key, null, name, "skip", "Unity の仮の名前（Light Layer N）は写さない");
            return;
        }
        if (isLayer ? BuiltinLayers.Contains(index) : index == BuiltinRenderingLayer)
        {
            var cur = index < arr.arraySize ? arr.GetArrayElementAtIndex(index).stringValue : null;
            r.Add(section, key, cur, name, cur == name ? "same" : "skip", "Unity が名前を決めている枠");
            return;
        }
        // layers は 32 枠固定。m_RenderingLayers は使う所まで（最大 32）
        if (index < 0 || index >= 32 || (isLayer && index >= arr.arraySize)) { r.Add(section, key, null, name, "error", "番号が範囲外"); return; }
        var before = index < arr.arraySize ? arr.GetArrayElementAtIndex(index).stringValue : "";
        if (before == name) { r.Add(section, key, before, name, "same"); return; }
        if (!string.IsNullOrEmpty(before) && !overwrite && !IsDefaultRenderingLayerName(prop, index, before))
        {
            r.Add(section, key, before, name, "conflict", "別の名前が入っている。上書きするなら Set" + (isLayer ? "Layer" : "RenderingLayer") + "(index, name, true)");
            return;
        }
        if (!apply) { r.Add(section, key, before, name, "change"); return; }
        while (arr.arraySize <= index)
        {
            arr.InsertArrayElementAtIndex(arr.arraySize);
            arr.GetArrayElementAtIndex(arr.arraySize - 1).stringValue = "";
        }
        arr.GetArrayElementAtIndex(index).stringValue = name;
        so.ApplyModifiedPropertiesWithoutUndo();
        r.Add(section, key, before, TagManager().FindProperty(prop).GetArrayElementAtIndex(index).stringValue, "applied");
    }

    // m_RenderingLayers の未使用の枠は Unity が "Light Layer N" と名付けて並べる（SinkaiFes2026 の TagManager.asset 3〜6 番）。上書きしてよい
    static bool IsDefaultRenderingLayerName(string prop, int index, string name) => prop == "m_RenderingLayers" && name == "Light Layer " + index;

    static void QualityRp(Report r, string levelName, string assetPath, bool apply)
    {
        var key = "quality " + levelName;
        var so = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/QualitySettings.asset")[0]);
        var levels = so.FindProperty("m_QualitySettings");
        SerializedProperty slot = null;
        for (var i = 0; i < levels.arraySize; i++)
            if (levels.GetArrayElementAtIndex(i).FindPropertyRelative("name").stringValue == levelName)
                slot = levels.GetArrayElementAtIndex(i).FindPropertyRelative("customRenderPipeline");
        if (slot == null) { r.Add("renderPipelines", key, null, assetPath, "error", "その名前の Quality レベルが無い（レベルを足すのは Project Settings > Quality で）"); return; }
        var before = AssetPath(slot.objectReferenceValue);
        RenderPipelineAsset asset = null;
        if (!string.IsNullOrEmpty(assetPath))
        {
            asset = AssetDatabase.LoadAssetAtPath<RenderPipelineAsset>(assetPath);
            if (asset == null) { r.Add("renderPipelines", key, before, assetPath, "error", "そのパスに Render Pipeline Asset が無い（先にアセットを入れる）"); return; }
        }
        if (before == AssetPath(asset)) { r.Add("renderPipelines", key, before, assetPath, "same"); return; }
        if (!apply) { r.Add("renderPipelines", key, before, assetPath, "change"); return; }
        slot.objectReferenceValue = asset;
        so.ApplyModifiedPropertiesWithoutUndo();
        var idx = Array.IndexOf(QualitySettings.names, levelName);
        r.Add("renderPipelines", key, before, AssetPath(QualitySettings.GetRenderPipelineAssetAt(idx)), "applied");
    }

    static void DefaultRp(Report r, string assetPath, bool apply)
    {
        var before = AssetPath(GraphicsSettings.defaultRenderPipeline);
        RenderPipelineAsset asset = null;
        if (!string.IsNullOrEmpty(assetPath))
        {
            asset = AssetDatabase.LoadAssetAtPath<RenderPipelineAsset>(assetPath);
            if (asset == null) { r.Add("renderPipelines", "graphicsDefault", before, assetPath, "error", "そのパスに Render Pipeline Asset が無い（先にアセットを入れる）"); return; }
        }
        if (before == AssetPath(asset)) { r.Add("renderPipelines", "graphicsDefault", before, assetPath, "same"); return; }
        if (!apply) { r.Add("renderPipelines", "graphicsDefault", before, assetPath, "change"); return; }
        GraphicsSettings.defaultRenderPipeline = asset;
        r.Add("renderPipelines", "graphicsDefault", before, AssetPath(GraphicsSettings.defaultRenderPipeline), "applied");
    }

    // ---- 小物 --------------------------------------------------------------------------------------
    // JSON の null は C# の null ではなく Type が Null の JValue になる
    static bool Has(JToken t) => t != null && t.Type != JTokenType.Null;

    // snapshot が見つけられなかった参照（"(missing <guid>)"）
    static bool IsMissing(string path) => path != null && path.StartsWith("(missing", StringComparison.Ordinal);

    static string[] SplitDefines(string s) =>
        (s ?? "").Split(new[] { ';', ',' }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).Where(x => x.Length > 0).ToArray();

    static string AssetPath(UnityEngine.Object o) => o == null ? null : AssetDatabase.GetAssetPath(o);

    static JObject NamesObject(SerializedProperty arr)
    {
        var o = new JObject();
        if (arr == null) return o;
        for (var i = 0; i < arr.arraySize; i++)
        {
            var n = arr.GetArrayElementAtIndex(i).stringValue;
            if (!string.IsNullOrEmpty(n)) o[i.ToString()] = n;
        }
        return o;
    }
}
