// vortex キャラクターセットアップ用の一時 Editor スクリプト。
// プロジェクトの Assets/_TempVerify/Editor/ に置き、MCP の invoke_method から呼ぶ。作業後は必ず削除する。
//
//   CharSetupTest.SetupFull("Assets/02_vortex_character/<フォルダ>/<名前>(NiloToon).prefab")
//   CharSetupTest.Compare("<既存の名前>", "<今回の名前>", "<出力先の絶対パス>")
//
// vortexCharacterSetup ウィンドウの「Setup Character」ボタンと同じ処理を反射で実行したうえで、
// ツールが面倒を見ない部分（LookatManager 登録・旧方式から新方式への付け替え）まで行う。

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;

public static class CharSetupTest
{
    private const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;

    // 既存キャラは非アクティブなことが多いので Resources.FindObjectsOfTypeAll で探す
    private static GameObject FindByName(string name) =>
        Resources.FindObjectsOfTypeAll<GameObject>().FirstOrDefault(g => g.name == name && g.scene.IsValid());

    private static Component FindComponentIncludingInactive(string typeName) =>
        Resources.FindObjectsOfTypeAll<Component>()
            .FirstOrDefault(c => c != null && c.GetType().Name == typeName && c.gameObject.scene.IsValid());

    private static Type FindType(string name) =>
        AppDomain.CurrentDomain.GetAssemblies()
            .SelectMany(a => { try { return a.GetTypes(); } catch { return Type.EmptyTypes; } })
            .First(t => t.Name == name);

    public static string SetupFull(string prefabPath)
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        if (prefab == null) return $"prefab が見つからない: {prefabPath}";

        var log = new List<string>();
        var windowType = FindType("vortexCharacterSetup");
        var window = ScriptableObject.CreateInstance(windowType);
        GameObject instance;
        try
        {
            windowType.GetMethod("OnEnable", Flags)?.Invoke(window, null);
            foreach (var n in new[] { "TryAutoAssignRootTransform", "TryAutoAssignOptitrackStreamingClient", "TryAutoAssignLipSyncProfile" })
                windowType.GetMethod(n, Flags)?.Invoke(window, null);

            // LookatController が非アクティブだとツールの自動検出が拾えないので、ここで入れておく
            var lookat = FindComponentIncludingInactive("LookatManager");
            windowType.GetField("_lookatManager", Flags).SetValue(window, lookat);
            log.Add($"lookatManager={(lookat == null ? "null" : lookat.gameObject.name)}");

            instance = UnityEngine.Object.Instantiate(prefab, Vector3.zero, Quaternion.identity);
            instance.name = prefab.name + "_setupped";
            windowType.GetMethod("SetupCharacter", Flags).Invoke(window, new object[] { instance });

            var rootTransform = (Transform)windowType.GetField("_rootTransform", Flags).GetValue(window);
            if (rootTransform != null) instance.transform.parent = rootTransform;

            var activator = windowType.GetField("_characterActivator", Flags).GetValue(window) as Component;
            if (activator != null) windowType.GetMethod("RegisterToCharacterActivator", Flags).Invoke(window, new object[] { instance });
            if (lookat != null) windowType.GetMethod("RegisterToLookatManager", Flags).Invoke(window, new object[] { instance });
        }
        finally { UnityEngine.Object.DestroyImmediate(window); }

        // 旧方式を外す
        foreach (var typeName in new[] { "FacialManager", "uLipSyncBlendShapeVRM", "uLipSyncMicrophone", "uLipSync", "AudioSource" })
        {
            var c = instance.GetComponents<Component>().FirstOrDefault(x => x != null && x.GetType().Name == typeName);
            if (c != null) { UnityEngine.Object.DestroyImmediate(c); log.Add("外した: " + typeName); }
        }

        // 新方式を付ける
        var proxy = instance.GetComponents<Component>().FirstOrDefault(c => c != null && c.GetType().Name == "VRMBlendShapeProxy");

        var lipSync = instance.AddComponent(FindType("OscRx_LipSync"));
        var lipSo = new SerializedObject(lipSync);
        lipSo.FindProperty("characterID").intValue = 0;          // 採番方針はユーザーに確認する
        lipSo.FindProperty("blendShapeProxy").objectReferenceValue = proxy;
        lipSo.ApplyModifiedPropertiesWithoutUndo();

        var facial = instance.AddComponent(FindType("vortex_FacialController"));
        var facialSo = new SerializedObject(facial);
        facialSo.FindProperty("_controllerLabel").stringValue = "";
        facialSo.FindProperty("_proxy").objectReferenceValue = proxy;
        facialSo.FindProperty("_minBlinkMilliSeconds").intValue = 2500;   // 既存キャラの値に合わせる
        facialSo.FindProperty("_maxBlinkMilliSeconds").intValue = 3000;
        facialSo.ApplyModifiedPropertiesWithoutUndo();
        log.Add("付けた: OscRx_LipSync / vortex_FacialController");

        return $"created={instance.name}\n" + string.Join("\n", log);
    }

    public static string Compare(string nameA, string nameB, string outFile)
    {
        var a = FindByName(nameA);
        var b = FindByName(nameB);
        if (a == null || b == null) return $"見つからない a={(a == null ? nameA : "ok")} b={(b == null ? nameB : "ok")}";

        var sb = new System.Text.StringBuilder();
        var ca = a.GetComponents<Component>().Where(c => c != null).ToList();
        var cb = b.GetComponents<Component>().Where(c => c != null).ToList();
        var na = ca.Select(c => c.GetType().Name).ToList();
        var nb = cb.Select(c => c.GetType().Name).ToList();
        sb.AppendLine($"A(既存)={nameA} {ca.Count} 件 / B(今回)={nameB} {cb.Count} 件");
        sb.AppendLine("A のみ: " + string.Join(", ", na.Except(nb)));
        sb.AppendLine("B のみ: " + string.Join(", ", nb.Except(na)));
        sb.AppendLine("A の順: " + string.Join(", ", na));
        sb.AppendLine("B の順: " + string.Join(", ", nb));

        sb.AppendLine("\n## 共通コンポーネントの値の差分");
        foreach (var typeName in na.Intersect(nb))
        {
            var diffs = Diff(ca.First(c => c.GetType().Name == typeName), cb.First(c => c.GetType().Name == typeName));
            if (diffs.Count == 0) continue;
            sb.AppendLine($"- {typeName}");
            foreach (var d in diffs.Take(25)) sb.AppendLine("    " + d);
            if (diffs.Count > 25) sb.AppendLine($"    ...ほか {diffs.Count - 25} 件");
        }

        sb.AppendLine("\n## SkinnedMeshRenderer（マテリアルとレイヤー）");
        foreach (var pair in new[] { new { Go = a, Label = "A" }, new { Go = b, Label = "B" } })
        {
            var renderers = pair.Go.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            sb.AppendLine($"{pair.Label}: {renderers.Length} 件 " +
                          $"layerMask=[{string.Join(",", renderers.Select(r => r.renderingLayerMask).Distinct())}] " +
                          $"updateWhenOffscreen=[{string.Join(",", renderers.Select(r => r.updateWhenOffscreen).Distinct())}]");
            foreach (var r in renderers)
                sb.AppendLine($"   {r.name}: " + string.Join(", ", r.sharedMaterials.Select(m => m == null ? "null" : m.name + "/" + (m.shader == null ? "?" : m.shader.name))));
        }

        File.WriteAllText(outFile, sb.ToString());
        return outFile;
    }

    private static List<string> Diff(Component x, Component y)
    {
        var result = new List<string>();
        var sx = new SerializedObject(x);
        var sy = new SerializedObject(y);
        var it = sx.GetIterator();
        while (it.NextVisible(true))
        {
            if (it.propertyPath == "m_Script") continue;
            var other = sy.FindProperty(it.propertyPath);
            if (other == null) { result.Add($"{it.propertyPath}: A のみ"); continue; }
            var va = Describe(it);
            var vb = Describe(other);
            if (va != vb) result.Add($"{it.propertyPath}: A={va} / B={vb}");
        }
        return result;
    }

    private static string Describe(SerializedProperty p)
    {
        switch (p.propertyType)
        {
            case SerializedPropertyType.ObjectReference:
                return p.objectReferenceValue == null ? "null" : $"{p.objectReferenceValue.name}({p.objectReferenceValue.GetType().Name})";
            case SerializedPropertyType.Generic: return p.isArray ? $"size={p.arraySize}" : "";
            case SerializedPropertyType.Integer: return p.intValue.ToString();
            case SerializedPropertyType.Boolean: return p.boolValue.ToString();
            case SerializedPropertyType.Float: return p.floatValue.ToString("F3");
            case SerializedPropertyType.String: return p.stringValue;
            case SerializedPropertyType.Enum: return p.enumValueIndex.ToString();
            case SerializedPropertyType.Vector3: return p.vector3Value.ToString("F3");
            default: return p.propertyType.ToString();
        }
    }
}
