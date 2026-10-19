// シェーダーの先読み（ShaderVariantCollection）を作る・確かめる Editor の道具。 trap-ok:cs-runtime-unityeditor trap-ok:cs-runtime-unityeditor-qualified
// 案件の Assets/_TempVerify/Editor/ へ写して MCP の invoke_method で呼ぶ。終わったら消す。
//   ClearTracked / Tracked / SaveTracked … Editor が「描いたシェーダーの組み合わせ」を数えている記録（Graphics 設定の Save to asset と同じもの）
//   Sweep … Play 中に Timeline を step 秒ごとに進め、各時刻で frames コマ描かせる（記録に組み合わせを集めるため）。State() で進み具合
//   WarmUpTimed … コレクションを WarmUp し、かかった時間と、その間にシェーダーのコンパイルが走っていたかを返す
using System;
using System.Diagnostics;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using Object = UnityEngine.Object;

public static class ShaderVariantTools
{
    // ShaderUtil の記録の口は internal（Graphics 設定の画面が使う）。無い版では例外の文で分かるようにする
    static object CallShaderUtil(string name, params object[] args)
    {
        var m = typeof(ShaderUtil).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
        if (m == null) throw new MissingMethodException("UnityEditor.ShaderUtil." + name + " is not in this Unity version");
        return m.Invoke(null, args);
    }

    public static string ClearTracked()
    {
        CallShaderUtil("ClearCurrentShaderVariantCollection");
        return Tracked();
    }

    public static string Tracked() =>
        $"tracked shaders {CallShaderUtil("GetCurrentShaderVariantCollectionShaderCount")}, variants {CallShaderUtil("GetCurrentShaderVariantCollectionVariantCount")}";

    public static string SaveTracked(string assetPath)
    {
        CallShaderUtil("SaveCurrentShaderVariantCollection", assetPath);
        AssetDatabase.ImportAsset(assetPath);
        var svc = AssetDatabase.LoadAssetAtPath<ShaderVariantCollection>(assetPath);
        return svc == null ? "error: not saved " + assetPath : $"saved {assetPath}: shaders {svc.shaderCount}, variants {svc.variantCount}";
    }

    // ---- Sweep（Play 中）----
    static PlayableDirector s_dir;
    static double s_t, s_t1, s_step;
    static int s_frames, s_waitUntil, s_samples;
    static string s_state = "idle";
    static readonly Stopwatch s_sw = new Stopwatch();
    // 止まりの計測: Tick の間隔。ふだんは 1 コマ（数十 ms）。StallMs を超えた間隔を「止まり」として数える
    // （100 ms = 60 fps で 6 コマ分。目で分かる引っかかり）
    const double StallMs = 100.0;
    static double s_last, s_maxGap, s_stallTotal;
    static int s_stalls, s_compilingTicks;

    public static string State() =>
        $"{s_state} t={s_t:F1} samples={s_samples} {s_sw.Elapsed.TotalSeconds:F1}s | stalls>{StallMs:F0}ms {s_stalls} (total {s_stallTotal / 1000.0:F1}s, max {s_maxGap:F0}ms)" +
        $" | ticks while compiling {s_compilingTicks} | {Tracked()}";

    /// <summary>Play 中に、directorName の Timeline を t0 から t1 まで step 秒ごとに止めて frames コマずつ描かせる。</summary>
    public static string Sweep(string directorName, float t0, float t1, float step, int frames)
    {
        if (!Application.isPlaying) return "error: play mode only";
        if (step <= 0f || t1 <= t0 || frames < 1) return "error: t1 > t0, step > 0, frames >= 1";
        var go = GameObject.Find(directorName);
        if (go == null || !go.TryGetComponent(out s_dir)) return "error: director not found";
        EditorApplication.update -= Tick;
        s_dir.Pause();
        s_t = t0; s_t1 = t1; s_step = step; s_frames = frames; s_samples = 0;
        s_waitUntil = -1;
        s_state = "running";
        s_stalls = s_compilingTicks = 0;
        s_maxGap = s_stallTotal = 0;
        s_sw.Restart();
        s_last = 0;
        EditorApplication.update += Tick;
        return "queued";
    }

    static void Tick()
    {
        if (!Application.isPlaying || s_dir == null) { EditorApplication.update -= Tick; s_state = "error: play mode ended"; return; }
        double ms = s_sw.Elapsed.TotalMilliseconds;
        double gap = ms - s_last;
        s_last = ms;
        if (gap > s_maxGap) s_maxGap = gap;
        if (gap > StallMs) { s_stalls++; s_stallTotal += gap; }
        if (ShaderUtil.anythingCompiling) s_compilingTicks++;
        int now = Time.renderedFrameCount;
        if (s_waitUntil >= 0 && now < s_waitUntil) { s_dir.time = s_t; s_dir.Evaluate(); return; } // 止めた時刻のまま描かせる
        if (s_waitUntil >= 0) { s_samples++; s_t += s_step; }
        if (s_t > s_t1) { EditorApplication.update -= Tick; s_sw.Stop(); s_state = "done"; return; }
        s_dir.time = s_t;
        s_dir.Evaluate();
        s_waitUntil = now + s_frames;
    }

    // ---- 仕組みの確かめ ----
    const string TestShaderPath = "Assets/_TempVerify/WarmUpProbe.shader";

    /// <summary>
    /// まだ一度もコンパイルしていない組み合わせ（新しく書いたシェーダーのキーワード付き）について、
    /// WarmUp の前・後で ShaderUtil.IsPassCompiled がどう変わるかを返す。Editor の WarmUp が先にコンパイルするかの確かめ。
    /// method: "warmup" = ShaderVariantCollection.WarmUp、"compilepass" = ShaderUtil.CompilePass(forceSync)。
    /// </summary>
    public static string MechanismTest(string method)
    {
        string keyword = "_PROBE_" + Guid.NewGuid().ToString("N").Substring(0, 8).ToUpperInvariant();
        System.IO.File.WriteAllText(TestShaderPath,
            "Shader \"Hidden/WarmUpProbe\" { SubShader { Pass {\n" +
            "HLSLPROGRAM\n#pragma vertex v\n#pragma fragment f\n#pragma multi_compile _ " + keyword + "\n" +
            "float4 v(float4 p : POSITION) : SV_POSITION { return p; }\n" +
            "float4 f() : SV_Target {\n#if defined(" + keyword + ")\nreturn 1;\n#else\nreturn 0;\n#endif\n}\nENDHLSL\n} } }\n");
        AssetDatabase.ImportAsset(TestShaderPath, ImportAssetOptions.ForceSynchronousImport);
        var shader = AssetDatabase.LoadAssetAtPath<Shader>(TestShaderPath);
        if (shader == null) return "error: probe shader not imported";
        var mat = new Material(shader);
        mat.EnableKeyword(keyword);
        bool before = ShaderUtil.IsPassCompiled(mat, 0);
        var sw = Stopwatch.StartNew();
        string how;
        if (method == "none")
        {
            how = "nothing (control)";
        }
        else if (method == "compilepass")
        {
            ShaderUtil.CompilePass(mat, 0, true);
            how = "CompilePass(forceSync)";
        }
        else
        {
            var svc = new ShaderVariantCollection();
            bool added = svc.Add(new ShaderVariantCollection.ShaderVariant(shader, UnityEngine.Rendering.PassType.Normal, keyword));
            svc.WarmUp();
            how = $"WarmUp (variant added={added})";
            Object.DestroyImmediate(svc);
        }
        sw.Stop();
        bool after = ShaderUtil.IsPassCompiled(mat, 0);
        Object.DestroyImmediate(mat);
        AssetDatabase.DeleteAsset(TestShaderPath);
        return $"{how}: compiled before={before} after={after} ({sw.Elapsed.TotalMilliseconds:F0} ms)";
    }

    // ---- 先読み ----
    public static string WarmUpTimed(string assetPath)
    {
        var svc = AssetDatabase.LoadAssetAtPath<ShaderVariantCollection>(assetPath);
        if (svc == null) return "error: not found " + assetPath;
        bool before = ShaderUtil.anythingCompiling;
        var sw = Stopwatch.StartNew();
        svc.WarmUp();
        sw.Stop();
        return $"WarmUp {svc.shaderCount} shaders / {svc.variantCount} variants: {sw.Elapsed.TotalMilliseconds:F0} ms, isWarmedUp={svc.isWarmedUp}, compiling before={before} after={ShaderUtil.anythingCompiling}";
    }
}
