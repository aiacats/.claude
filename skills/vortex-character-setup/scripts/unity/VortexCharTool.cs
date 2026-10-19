// vortex キャラセットアップ用の一時 Editor スクリプト（仕込み側）。 trap-ok:cs-runtime-unityeditor trap-ok:cs-runtime-unityeditor-qualified
// 案件の Assets/_TempVerify/Editor/ にコピーし、MCP の invoke_method から呼ぶ。作業後は必ず削除する。
// 手順と引数は SKILL.md。ダイアログを出す処理（ConvertToNiloToon）は 1 体ずつ呼び、モーダルは win-gui で押す。
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;
using Object = UnityEngine.Object;

public static class VortexCharTool
{
    private const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    public const string DefaultPresetPath = "Packages/jp.pjblue.realtime-live-utility/Script/Editor/Facial/FacialPreset/FacialPreset.asset";

    // FacialManager の表情枠(表に載る 14 枠 + スティック + Neutral / 自動まばたき)
    private static readonly string[] MorphSlots =
    {
        "_neutral", "_autoBlnk", "_buttonEast", "_buttonWest", "_buttonNorth", "_buttonSouth",
        "_dpadLeft", "_dpadRight", "_dpadUp", "_dpadDown", "_shoulderLeft", "_shoulderRight",
        "_triggerLeft", "_triggerRight", "_buttonStart", "_buttonSelect",
        "_stickLeftX_Positive", "_stickLeftX_Negative", "_stickLeftY_Positive", "_stickLeftY_Negative",
        "_stickRightX_Positive", "_stickRightX_Negative", "_stickRightY_Positive", "_stickRightY_Negative",
    };

    // 標準プリセットの名前 → VRM 標準の BlendShapeClip 名(プリセットは BlinkL/BlinkR、VRM は Blink_L/Blink_R)
    private static readonly Dictionary<string, string> NameFix = new()
    {
        { "BlinkL", "Blink_L" },
        { "BlinkR", "Blink_R" },
    };

    // ---- 共通 ----

    private static Type FindType(string name) =>
        AppDomain.CurrentDomain.GetAssemblies()
            .SelectMany(a => { try { return a.GetTypes(); } catch { return Type.EmptyTypes; } })
            .First(t => t.Name == name);

    private static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (var p = t.parent; p != null; p = p.parent) sb.Insert(0, p.name + "/");
        return sb.ToString();
    }

    private static IEnumerable<GameObject> SceneObjects() =>
        Resources.FindObjectsOfTypeAll<GameObject>().Where(g => g.scene.IsValid() && g.scene == EditorSceneManager.GetActiveScene());

    public static bool IsCharacter(GameObject g) =>
        g.GetComponents<Component>().Any(c => c != null && c.GetType().Name == "VRMBlendShapeProxy");

    /// <summary>シーン内のキャラ(VRMBlendShapeProxy を持つもの)を Hierarchy の並び順で返す。</summary>
    public static List<GameObject> Characters() =>
        SceneObjects().Where(IsCharacter).OrderBy(g => g.transform.GetSiblingIndex()).ToList();

    public static string OpenScene(string path)
    {
        var scene = EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
        return $"opened {scene.path} dirty={scene.isDirty}";
    }

    public static string SaveScene()
    {
        var scene = EditorSceneManager.GetActiveScene();
        return $"saved={EditorSceneManager.SaveScene(scene)} {scene.path}";
    }

    public static string EnsureFolder(string parent, string name)
    {
        var path = parent + "/" + name;
        if (!AssetDatabase.IsValidFolder(path)) AssetDatabase.CreateFolder(parent, name);
        return path;
    }

    // ---- 点検 ----

    /// <summary>キャラの一覧と、それらを外から参照しているコンポーネント・OSC サーバーの配線を outFile に書き出す。</summary>
    public static string Inspect(string outFile)
    {
        var sb = new StringBuilder();
        var chars = Characters();
        sb.AppendLine($"# characters: {chars.Count}");
        foreach (var g in chars)
        {
            var t = g.transform;
            sb.AppendLine($"- {PathOf(t)} activeSelf={g.activeSelf} pos={t.localPosition:F3} rot={t.localEulerAngles:F1} scale={t.localScale:F3}");
            sb.AppendLine("    components: " + string.Join(", ", g.GetComponents<Component>().Where(c => c != null).Select(c => c.GetType().Name)));
        }

        var charSet = new HashSet<GameObject>(chars);
        GameObject OwnerChar(Object o)
        {
            Transform t = o switch { GameObject go => go.transform, Component c => c.transform, _ => null };
            for (; t != null; t = t.parent) if (charSet.Contains(t.gameObject)) return t.gameObject;
            return null;
        }

        sb.AppendLine("\n# references to characters from outside");
        foreach (var comp in SceneObjects().SelectMany(g => g.GetComponents<Component>()).Where(c => c != null))
        {
            if (OwnerChar(comp) != null) continue;
            var so = new SerializedObject(comp);
            var it = so.GetIterator();
            var hits = new List<string>();
            while (it.Next(true))
            {
                if (it.propertyType != SerializedPropertyType.ObjectReference || it.objectReferenceValue == null) continue;
                var owner = OwnerChar(it.objectReferenceValue);
                if (owner != null) hits.Add($"{it.propertyPath} -> {owner.name} ({it.objectReferenceValue.GetType().Name} {it.objectReferenceValue.name})");
            }
            if (hits.Count > 0)
            {
                sb.AppendLine($"- {PathOf(comp.transform)} [{comp.GetType().Name}] ({hits.Count})");
                foreach (var h in hits.Take(40)) sb.AppendLine("    " + h);
            }
        }

        foreach (var server in SceneObjects().SelectMany(g => g.GetComponents<uOSC.uOscServer>()))
        {
            sb.AppendLine($"\n# uOscServer port {server.port} enabled={server.enabled && server.gameObject.activeInHierarchy} onDataReceived @ {PathOf(server.transform)}");
            for (int i = 0; i < server.onDataReceived.GetPersistentEventCount(); i++)
            {
                var target = server.onDataReceived.GetPersistentTarget(i);
                sb.AppendLine($"  [{i}] {server.onDataReceived.GetPersistentMethodName(i)} -> " +
                              (target == null ? "null" : $"{target.GetType().Name} @ {(target is Component c ? PathOf(c.transform) : target.name)}"));
            }
        }
        File.WriteAllText(outFile, sb.ToString());
        return outFile;
    }

    // キャラの表情・口パクを受けるコンポーネント（OSC の配線先を見分けるのに使う）
    private static readonly string[] CharacterOscReceivers = { "FacialManager", "OscRx_LipSync", "vortex_FacialController" };

    /// <summary>
    /// キャラの OSC を配線する uOscServer を選ぶ。path を渡せばそれ。無ければ、既にキャラの表情・口パクが配線されている数が最も多いサーバー。
    /// どれにも配線が無く、サーバーが 1 つだけならそれ。決められなければ候補を並べて error を返す（.First() で選ぶと、マイク用など別のサーバーに付くことがある）。
    /// </summary>
    private static uOSC.uOscServer CharacterServer(string path, out string error)
    {
        error = null;
        var servers = SceneObjects().SelectMany(g => g.GetComponents<uOSC.uOscServer>()).ToList();
        if (!string.IsNullOrEmpty(path))
        {
            var hit = servers.FirstOrDefault(s => PathOf(s.transform) == path);
            if (hit == null) error = $"uOscServer not found at {path}. candidates: " + string.Join(" / ", servers.Select(s => PathOf(s.transform)));
            return hit;
        }
        int Score(uOSC.uOscServer s)
        {
            int n = 0;
            for (int i = 0; i < s.onDataReceived.GetPersistentEventCount(); i++)
                if (s.onDataReceived.GetPersistentTarget(i) is Component c && CharacterOscReceivers.Contains(c.GetType().Name)) n++;
            return n;
        }
        var scored = servers.Select(s => (s, n: Score(s))).OrderByDescending(x => x.n).ToList();
        if (scored.Count == 0) { error = "no uOscServer in the scene"; return null; }
        if (scored[0].n > 0 && (scored.Count == 1 || scored[1].n < scored[0].n)) return scored[0].s;
        if (scored.Count == 1) return scored[0].s;
        error = "cannot choose the uOscServer for characters; pass oscServerPath. candidates: " +
                string.Join(" / ", scored.Select(x => $"{PathOf(x.s.transform)} (port {x.s.port}, character listeners {x.n})"));
        return null;
    }

    /// <summary>
    /// シーンに既にいるキャラから、GameObject のレイヤーと Rendering Layer（1 ビットのもの）を読む。
    /// 案件ごとにキャラ用のレイヤー（SinkaiFes2026 は Chara・Character）が違うので、既存のキャラに揃える。
    /// キャラごとに多数派を取り、キャラの過半数が同じ値のときだけそれを返す（割れていれば -1。シーンの中で揃っていないので指定してもらう）。
    /// note には、多数派と違うキャラを並べる。
    /// </summary>
    private static (int layer, int renderingLayerIndex, string note) ExistingCharacterLayers(GameObject exclude)
    {
        var per = Characters().Where(g => g != exclude)
            .Select(g => (g, rs: g.GetComponentsInChildren<SkinnedMeshRenderer>(true)))
            .Where(x => x.rs.Length > 0)
            .Select(x => (x.g,
                layer: x.rs.GroupBy(r => r.gameObject.layer).OrderByDescending(k => k.Count()).First().Key,
                mask: x.rs.GroupBy(r => r.renderingLayerMask).OrderByDescending(k => k.Count()).First().Key))
            .ToList();
        if (per.Count == 0) return (-1, -1, "no character in the scene");
        int Majority<T>(Func<(GameObject g, int layer, uint mask), T> key, out T value)
        {
            var top = per.GroupBy(key).OrderByDescending(k => k.Count()).First();
            value = top.Key;
            return top.Count();
        }
        var notes = new List<string>();
        int layer = -1, index = -1;
        if (Majority(x => x.layer, out int l) * 2 > per.Count) layer = l;
        if (Majority(x => x.mask, out uint m) * 2 > per.Count && m != 0 && (m & (m - 1)) == 0) index = (int)Math.Log(m, 2);
        string Dist<T>(Func<(GameObject g, int layer, uint mask), T> key, Func<T, string> name) =>
            string.Join(", ", per.GroupBy(key).Select(k => $"{name(k.Key)} x{k.Count()}"));
        notes.Add("characters' layers: " + Dist(x => x.layer, v => LayerMask.LayerToName(v)) + " / rendering layer masks: " + Dist(x => x.mask, v => v.ToString()));
        if (layer >= 0)
        {
            var odd = per.Where(x => x.layer != layer).Select(x => x.g.name).ToList();
            if (odd.Count > 0) notes.Add($"warn: not on {LayerMask.LayerToName(layer)}: " + string.Join(", ", odd));
        }
        return (layer, index, string.Join("\n", notes));
    }

    /// <summary>コンポーネントの配列プロパティを要素ごとに書き出す(CharacterActivator._characters / LookatManager._lookatTargets など)。</summary>
    public static string DumpArray(string componentTypeName, string arrayPath)
    {
        var comp = SceneObjects().SelectMany(g => g.GetComponents<Component>())
            .FirstOrDefault(c => c != null && c.GetType().Name == componentTypeName);
        if (comp == null) return "(not found) " + componentTypeName;
        var array = new SerializedObject(comp).FindProperty(arrayPath);
        if (array == null || !array.isArray) return "(not an array) " + arrayPath;
        var sb = new StringBuilder($"{componentTypeName}.{arrayPath} size={array.arraySize}\n");
        for (int i = 0; i < array.arraySize; i++)
        {
            var e = array.GetArrayElementAtIndex(i);
            var end = e.GetEndProperty();
            var it = e.Copy();
            var parts = new List<string>();
            if (it.NextVisible(true))
            {
                while (!SerializedProperty.EqualContents(it, end))
                {
                    switch (it.propertyType)
                    {
                        case SerializedPropertyType.ObjectReference: parts.Add($"{it.name}={(it.objectReferenceValue == null ? "null" : it.objectReferenceValue.name)}"); break;
                        case SerializedPropertyType.Integer: parts.Add($"{it.name}={it.intValue}"); break;
                        case SerializedPropertyType.Float: parts.Add($"{it.name}={it.floatValue:F2}"); break;
                        case SerializedPropertyType.Boolean: parts.Add($"{it.name}={it.boolValue}"); break;
                        case SerializedPropertyType.String: parts.Add($"{it.name}='{it.stringValue}'"); break;
                        case SerializedPropertyType.Enum: parts.Add($"{it.name}={it.enumValueIndex}"); break;
                    }
                    if (!it.NextVisible(it.propertyType == SerializedPropertyType.Generic)) break;
                }
            }
            sb.AppendLine($"  [{i}] " + string.Join(" ", parts));
        }
        return sb.ToString();
    }

    /// <summary>
    /// 2 体のキャラのコンポーネントの種類・順序・値の差分と SkinnedMeshRenderer の設定を outFile に書き出す。
    /// 既存キャラは非アクティブなことが多いので Resources.FindObjectsOfTypeAll で探す。
    /// </summary>
    public static string Compare(string nameA, string nameB, string outFile)
    {
        var a = SceneObjects().FirstOrDefault(g => g.name == nameA);
        var b = SceneObjects().FirstOrDefault(g => g.name == nameB);
        if (a == null || b == null) return $"(not found) a={(a == null ? nameA : "ok")} b={(b == null ? nameB : "ok")}";

        var sb = new StringBuilder();
        var ca = a.GetComponents<Component>().Where(c => c != null).ToList();
        var cb = b.GetComponents<Component>().Where(c => c != null).ToList();
        var na = ca.Select(c => c.GetType().Name).ToList();
        var nb = cb.Select(c => c.GetType().Name).ToList();
        sb.AppendLine($"A={nameA} {ca.Count} / B={nameB} {cb.Count}");
        sb.AppendLine("A only: " + string.Join(", ", na.Except(nb)));
        sb.AppendLine("B only: " + string.Join(", ", nb.Except(na)));
        sb.AppendLine("\n## value diffs of shared components");
        foreach (var typeName in na.Intersect(nb))
        {
            var sa = new SerializedObject(ca.First(c => c.GetType().Name == typeName));
            var sbj = new SerializedObject(cb.First(c => c.GetType().Name == typeName));
            var diffs = new List<string>();
            var it = sa.GetIterator();
            while (it.NextVisible(true))
            {
                if (it.propertyPath == "m_Script") continue;
                var other = sbj.FindProperty(it.propertyPath);
                if (other == null) { diffs.Add($"{it.propertyPath}: A only"); continue; }
                string Describe(SerializedProperty p) => p.propertyType switch
                {
                    SerializedPropertyType.ObjectReference => p.objectReferenceValue == null ? "null" : p.objectReferenceValue.name,
                    SerializedPropertyType.Integer => p.intValue.ToString(),
                    SerializedPropertyType.Boolean => p.boolValue.ToString(),
                    SerializedPropertyType.Float => p.floatValue.ToString("F3"),
                    SerializedPropertyType.String => p.stringValue,
                    SerializedPropertyType.Enum => p.enumValueIndex.ToString(),
                    SerializedPropertyType.Generic => p.isArray ? $"size={p.arraySize}" : "",
                    _ => p.propertyType.ToString(),
                };
                if (Describe(it) != Describe(other)) diffs.Add($"{it.propertyPath}: A={Describe(it)} / B={Describe(other)}");
            }
            if (diffs.Count == 0) continue;
            sb.AppendLine($"- {typeName}");
            foreach (var d in diffs.Take(25)) sb.AppendLine("    " + d);
        }
        sb.AppendLine("\n## SkinnedMeshRenderer");
        foreach (var (go, label) in new[] { (a, "A"), (b, "B") })
        {
            var rs = go.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            sb.AppendLine($"{label}: {rs.Length} layerMask=[{string.Join(",", rs.Select(r => r.renderingLayerMask).Distinct())}] " +
                          $"updateWhenOffscreen=[{string.Join(",", rs.Select(r => r.updateWhenOffscreen).Distinct())}]");
        }
        File.WriteAllText(outFile, sb.ToString());
        return outFile;
    }

    // ---- NiloToon 変換 ----

    /// <summary>
    /// NiloToon 複数プレハブ変換ウィンドウの「選択プレハブを変換」と同じ変換を、結果ダイアログを出さずに 1 体だけ行う。
    /// 途中で NiloToon 本体のモーダルが 2 つ出る(convert materials? → Yes / Material Upgrader → Proceed)。win-gui で押す。
    /// MCP が timeout しても Unity 側では後から実行されるので、再送しない。
    /// </summary>
    public static string ConvertToNiloToon(string prefabPath)
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        if (prefab == null) return "prefab (not found): " + prefabPath;
        var type = FindType("NiloToonMultiPrefabConvert");
        var method = type.GetMethod("TryCreatePrefabVariantAndCloneMaterials", BindingFlags.Static | BindingFlags.NonPublic);
        var dir = Path.GetDirectoryName(prefabPath).Replace("\\", "/");
        var variantPath = AssetDatabase.GenerateUniqueAssetPath($"{dir}/{prefab.name}(NiloToon).prefab");
        var args = new object[] { prefab, variantPath, null, null };
        bool ok = (bool)method.Invoke(null, args);
        return ok ? $"ok -> {variantPath}" : $"failed: {args[3]}";
    }

    // ---- 元のキャラの削除 ----

    /// <summary>
    /// キャラ(names が "*" なら全員、それ以外はカンマ区切りの名前)と、includeMicOffset なら Micoffset_* を、
    /// 外から参照している登録ごと取り除いて削除する。配列の中の参照は「いちばん外側の配列要素」ごと消す(空の枠を残さない)。
    /// </summary>
    public static string RemoveCharacters(string names, bool includeMicOffset)
    {
        var wanted = names == "*" ? null : new HashSet<string>(names.Split(',').Select(s => s.Trim()));
        var targets = SceneObjects().Where(g =>
                (IsCharacter(g) && (wanted == null || wanted.Contains(g.name))) ||
                (includeMicOffset && g.name.StartsWith("Micoffset_", StringComparison.Ordinal)))
            .ToList();
        return string.Join("\n", targets.Select(RemoveObject));
    }

    private static string RemoveObject(GameObject target)
    {
        string name = target.name;
        bool IsInTarget(Object o)
        {
            Transform t = o switch { GameObject go => go.transform, Component c => c.transform, _ => null };
            for (; t != null; t = t.parent) if (t.gameObject == target) return true;
            return false;
        }

        var log = new List<string>();
        foreach (var comp in SceneObjects().SelectMany(g => g.GetComponents<Component>()).Where(c => c != null).ToList())
        {
            if (comp is Transform) continue;
            if (IsInTarget(comp)) continue;
            var so = new SerializedObject(comp);
            bool changed;
            do
            {
                changed = false;
                var it = so.GetIterator();
                while (it.Next(true))
                {
                    if (it.propertyType != SerializedPropertyType.ObjectReference || it.objectReferenceValue == null) continue;
                    if (!IsInTarget(it.objectReferenceValue)) continue;

                    var path = it.propertyPath;
                    int idx = path.IndexOf(".Array.data[", StringComparison.Ordinal);
                    if (idx >= 0)
                    {
                        int start = idx + ".Array.data[".Length;
                        int close = path.IndexOf(']', start);
                        var arrayPath = path.Substring(0, idx);
                        int element = int.Parse(path.Substring(start, close - start));
                        var array = so.FindProperty(arrayPath);
                        int before = array.arraySize;
                        array.DeleteArrayElementAtIndex(element);
                        if (array.arraySize == before) array.DeleteArrayElementAtIndex(element); // 参照の要素は 1 回目で null になるだけ
                        log.Add($"  {PathOf(comp.transform)} [{comp.GetType().Name}] {arrayPath}[{element}] removed");
                    }
                    else
                    {
                        it.objectReferenceValue = null;
                        log.Add($"  {PathOf(comp.transform)} [{comp.GetType().Name}] {path} = null");
                    }
                    so.ApplyModifiedProperties();
                    changed = true;
                    break;
                }
            } while (changed);
        }
        Undo.DestroyObjectImmediate(target);
        return $"deleted: {name}\n" + string.Join("\n", log);
    }

    // ---- 仕込み ----

    /// <summary>
    /// CharacterSetup ウィンドウの「Setup Character」と同じ処理を反射で実行し、最近のライブシーン(Iori・ProBlueFes・SinkaiFes2026)と同じ
    /// OscRx_LipSync + FacialManager の形に整えて OSC サーバーへ配線する。引数の意味は SetupCharacterEx。
    /// </summary>
    public static string SetupCharacter(string prefabPath, int id, string presetPath, string deviceType) =>
        SetupCharacterEx(prefabPath, id, presetPath, deviceType, "", "", "", "");

    /// <summary>
    /// - 表情の割り当ては presetPath の FacialPreset を適用する(ウィンドウの _facialPreset が null だと丸ごと飛ばされるため必ず渡す)。
    /// - deviceType は FacialManager.DeviceType の名前(例 "Osc_XBox")。ウィンドウ経由では保存値に戻るので最後に直接書く。
    /// - id は OscRx_LipSync.characterID と FacialManager.oscFacialID に同じ値を入れる。
    /// - oscServerPath: キャラを配線する uOscServer のヒエラルキーパス。空なら、既にキャラが配線されているサーバーを選ぶ（CharacterServer）。
    /// - layerName / renderingLayerName: キャラの GameObject のレイヤーと、SkinnedMeshRenderer の Rendering Layer の名前。
    ///   空なら、シーンに既にいるキャラの多数派に揃える。どちらも決められなければ何も作らずに error を返す
    ///   （ウィンドウを CreateInstance で作ると Rendering Layer が 0 = Default のままになり、Character のライトだけを受ける案件でキャラが真っ黒になる）。
    /// - skeletonName: OptitrackSkeletonAnimator.SkeletonAssetName（Motive の名前）。空なら既定（Skeleton1）のまま。
    /// </summary>
    public static string SetupCharacterEx(string prefabPath, int id, string presetPath, string deviceType,
        string oscServerPath, string layerName, string renderingLayerName, string skeletonName)
    {
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        if (prefab == null) return $"error: prefab (not found): {prefabPath}";
        var preset = AssetDatabase.LoadAssetAtPath<ScriptableObject>(string.IsNullOrEmpty(presetPath) ? DefaultPresetPath : presetPath);
        if (preset == null) return $"error: preset (not found): {presetPath}";
        var device = (vortex.FacialManager.DeviceType)Enum.Parse(typeof(vortex.FacialManager.DeviceType), deviceType);
        // 表情の枠を合わせるのに BlendShapeAvatar が、仕込みのウィンドウに Humanoid が要る。作り始めてから落ちないよう、先にプレハブで確かめる
        var proxyAsset = prefab.GetComponent<VRM.VRMBlendShapeProxy>();
        if (proxyAsset == null || proxyAsset.BlendShapeAvatar == null)
            return $"error: {prefab.name} has no VRMBlendShapeProxy with a BlendShapeAvatar on its root (not a VRM character)";
        var animatorAsset = prefab.GetComponentInChildren<Animator>(true);
        if (animatorAsset == null || animatorAsset.avatar == null || !animatorAsset.avatar.isHuman)
            return $"error: {prefab.name} has no Humanoid Animator";
        // 二度呼んだとき（MCP の timeout の後の再送など）に 2 体目を作らない
        string instanceName = prefab.name + "_setupped";
        var already = SceneObjects().FirstOrDefault(g => g.name == instanceName ||
            (PrefabUtility.IsOutermostPrefabInstanceRoot(g) && PrefabUtility.GetCorrespondingObjectFromSource(g) == prefab));
        if (already != null) return $"error: already in the scene: {PathOf(already.transform)} (delete it first with DeleteCharacter)";

        // 先に配線先とレイヤーを決める（決められなければ、シーンに何も足さずに返す）
        var server = CharacterServer(oscServerPath, out var serverError);
        if (server == null) return "error: " + serverError;
        var (existingLayer, existingRl, layerNote) = ExistingCharacterLayers(null);
        int layer = string.IsNullOrEmpty(layerName) ? existingLayer : LayerMask.NameToLayer(layerName);
        if (layer < 0) return string.IsNullOrEmpty(layerName)
            ? "error: cannot copy the layer from the characters in the scene (none, or no majority); pass layerName (e.g. Chara)\n" + layerNote
            : $"error: layer '{layerName}' does not exist (TagManager)";
        // 名前 → ビットの番号。renderingLayerMaskNames の並びの番号は、名前の無い枠があるとビットとずれる
        var rlNames = RenderingLayerMask.GetDefinedRenderingLayerNames();
        int rlIndex = string.IsNullOrEmpty(renderingLayerName) ? existingRl : RenderingLayerMask.NameToRenderingLayer(renderingLayerName);
        if (rlIndex < 0) return string.IsNullOrEmpty(renderingLayerName)
            ? "error: cannot read a single rendering layer from the characters in the scene (none, or no majority); pass renderingLayerName (e.g. Character). names: " + string.Join(",", rlNames) + "\n" + layerNote
            : $"error: rendering layer '{renderingLayerName}' not found. names: " + string.Join(",", rlNames);

        var log = new List<string>
        {
            $"layer={LayerMask.LayerToName(layer)} ({(string.IsNullOrEmpty(layerName) ? "copied from the characters in the scene" : "given")})" +
            $" renderingLayer={RenderingLayerMask.RenderingLayerToName(rlIndex)} (bit {rlIndex}, {(string.IsNullOrEmpty(renderingLayerName) ? "copied" : "given")})",
            layerNote
        };
        // 1 回の Undo で全部戻るようにまとめる。生成の記録は生成の直後に置く（仕上げてから記録すると、Redo で OSC サーバー・
        // CharacterActivator の参照がキャラより先に戻り、壊れた参照になった。2026-10-19 実測）。記録の直後に階層ごと記録して、
        // 以降の素の書き込み（ウィンドウの AddComponent など）が Undo の flush で生成直後の姿に戻らないようにする（traps unity-editor）。
        // 途中で落ちたら、記録した変更（キャラの生成・CharacterActivator・LookatManager・OSC サーバー）を戻し、残ったキャラを消す
        Undo.IncrementCurrentGroup();
        int undoGroup = Undo.GetCurrentGroup();
        Undo.SetCurrentGroupName("Setup Character " + prefab.name);
        GameObject instance = null;
        try
        {
            var windowType = FindType("vortexCharacterSetup");
            var window = ScriptableObject.CreateInstance(windowType);
            try
            {
                windowType.GetMethod("OnEnable", Flags)?.Invoke(window, null);
                foreach (var n in new[] { "TryAutoAssignRootTransform", "TryAutoAssignOptitrackStreamingClient", "TryAutoAssignLipSyncProfile" })
                    windowType.GetMethod(n, Flags)?.Invoke(window, null);
                windowType.GetField("_facialPreset", Flags).SetValue(window, preset);
                windowType.GetField("_deviceType", Flags).SetValue(window, device);
                windowType.GetField("_selectedRenderingLayer", Flags).SetValue(window, rlIndex);

                // LookatController・ObjectActivator が非アクティブ（System の塊ごと無効のシーンがある）だと、ツールの自動検出
                // （FindObjectOfType）が拾えない。非アクティブも含めて、今のシーンから探して入れる
                Component InScene(string typeName) => Resources.FindObjectsOfTypeAll<Component>()
                    .FirstOrDefault(c => c != null && c.GetType().Name == typeName && c.gameObject.scene == EditorSceneManager.GetActiveScene());
                var lookat = InScene("LookatManager");
                windowType.GetField("_lookatManager", Flags).SetValue(window, lookat);
                var activatorFound = InScene("CharacterActivator");
                if (activatorFound != null) windowType.GetField("_characterActivator", Flags).SetValue(window, activatorFound);

                instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, EditorSceneManager.GetActiveScene());
                Undo.RegisterCreatedObjectUndo(instance, "Setup Character " + prefab.name);
                Undo.RegisterFullObjectHierarchyUndo(instance, "Setup Character " + prefab.name);
                instance.name = instanceName;
                windowType.GetMethod("SetupCharacter", Flags).Invoke(window, new object[] { instance });

                var rootTransform = (Transform)windowType.GetField("_rootTransform", Flags).GetValue(window);
                if (rootTransform != null) instance.transform.SetParent(rootTransform, false);
                var activator = windowType.GetField("_characterActivator", Flags).GetValue(window) as Component;
                if (activator != null) windowType.GetMethod("RegisterToCharacterActivator", Flags).Invoke(window, new object[] { instance });
                if (lookat != null) windowType.GetMethod("RegisterToLookatManager", Flags).Invoke(window, new object[] { instance });
                log.Add($"root={(rootTransform == null ? "null" : PathOf(rootTransform))} activator={(activator == null ? "null" : activator.name)} lookat={(lookat == null ? "null" : lookat.name)}");
            }
            finally { Object.DestroyImmediate(window); }

            // GameObject のレイヤー（ウィンドウは設定しない）。番組カメラの cullingMask がキャラのレイヤーで絞っている案件がある
            int relayered = 0;
            foreach (var t in instance.GetComponentsInChildren<Transform>(true))
                if (t.gameObject.layer != layer) { t.gameObject.layer = layer; relayered++; }
            log.Add($"set layer on {relayered} objects");
            var smrs = instance.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            log.Add($"skinned meshes {smrs.Length}, rendering layer mask {string.Join(",", smrs.Select(r => r.renderingLayerMask).Distinct())}");

            if (!string.IsNullOrEmpty(skeletonName))
            {
                // OptiTrack の asmdef は Assembly-CSharp-Editor から参照されないので、型名で探して SerializedObject で書く
                var opti = instance.GetComponents<Component>().FirstOrDefault(c => c != null && c.GetType().Name == "OptitrackSkeletonAnimator");
                if (opti == null) log.Add("warn: no OptitrackSkeletonAnimator (skeleton not set)");
                else
                {
                    var so = new SerializedObject(opti);
                    so.FindProperty("SkeletonAssetName").stringValue = skeletonName;
                    so.ApplyModifiedPropertiesWithoutUndo();
                    log.Add("skeleton=" + skeletonName);
                }
            }

            // マイク直結の口パク(uLipSync 系)は使わない。OSC の口パク(OscRx_LipSync)にする
            foreach (var typeName in new[] { "uLipSyncMicrophone", "uLipSyncBlendShapeVRM", "uLipSync", "AudioSource" })
            {
                var c = instance.GetComponents<Component>().FirstOrDefault(x => x != null && x.GetType().Name == typeName);
                if (c != null) { Object.DestroyImmediate(c); log.Add("removed: " + typeName); }
            }

            var proxy = instance.GetComponent<VRM.VRMBlendShapeProxy>();
            var lipSync = instance.AddComponent<vortex.OscRx_LipSync>();
            var lipSo = new SerializedObject(lipSync);
            lipSo.FindProperty("characterID").intValue = id;
            lipSo.FindProperty("blendShapeProxy").objectReferenceValue = proxy;
            lipSo.ApplyModifiedPropertiesWithoutUndo();

            var facial = instance.GetComponent<vortex.FacialManager>();
            var facialSo = new SerializedObject(facial);
            facialSo.FindProperty("_lipSync").objectReferenceValue = null;
            facialSo.FindProperty("_oscLipSync").objectReferenceValue = lipSync;
            facialSo.FindProperty("oscFacialID").intValue = id;
            facialSo.FindProperty("_deviceType").enumValueIndex = (int)device;
            facialSo.ApplyModifiedPropertiesWithoutUndo();
            log.Add(FixMorphNames(instance));

            // OSC サーバーへの配線(Iori と同じく FacialManager と OscRx_LipSync の OscOnDataReceived)
            Undo.RecordObject(server, "Wire OSC");
            UnityEventTools.AddPersistentListener(server.onDataReceived,
                (UnityAction<uOSC.Message>)Delegate.CreateDelegate(typeof(UnityAction<uOSC.Message>), facial, "OscOnDataReceived"));
            UnityEventTools.AddPersistentListener(server.onDataReceived,
                (UnityAction<uOSC.Message>)Delegate.CreateDelegate(typeof(UnityAction<uOSC.Message>), lipSync, "OscOnDataReceived"));
            EditorUtility.SetDirty(server);
            log.Add($"id={id} device={deviceType} OSC wired x2 @ {PathOf(server.transform)} (port {server.port})");

            Undo.CollapseUndoOperations(undoGroup);
        }
        catch (Exception e)
        {
            Undo.RevertAllDownToGroup(undoGroup);
            if (instance != null) Object.DestroyImmediate(instance);
            var inner = e is TargetInvocationException tie && tie.InnerException != null ? tie.InnerException : e;
            return $"error: setup failed and was rolled back: {inner.GetType().Name}: {inner.Message}\n" + string.Join("\n", log);
        }

        EditorSceneManager.MarkSceneDirty(instance.scene);
        return $"created={PathOf(instance.transform)}\n" + string.Join("\n", log);
    }

    /// <summary>
    /// 仕込み済みのキャラ全員に FacialPreset を当て直す(表情枠が空で保存されてしまったときの修正用)。
    /// </summary>
    public static string ApplyFacialPreset(string presetPath, string deviceType)
    {
        var preset = AssetDatabase.LoadAssetAtPath<ScriptableObject>(string.IsNullOrEmpty(presetPath) ? DefaultPresetPath : presetPath);
        if (preset == null) return $"preset (not found): {presetPath}";
        var device = (vortex.FacialManager.DeviceType)Enum.Parse(typeof(vortex.FacialManager.DeviceType), deviceType);
        var windowType = FindType("vortexCharacterSetup");
        var sb = new StringBuilder();
        foreach (var c in Characters())
        {
            var fm = c.GetComponent<vortex.FacialManager>();
            if (fm == null) { sb.AppendLine($"{c.name}: no FacialManager"); continue; }
            var window = ScriptableObject.CreateInstance(windowType);
            try
            {
                windowType.GetField("_facialPreset", Flags).SetValue(window, preset);
                windowType.GetField("_deviceType", Flags).SetValue(window, device);
                windowType.GetMethod("ApplyFacialPreset", Flags).Invoke(window, new object[] { fm });
            }
            finally { Object.DestroyImmediate(window); }
            var so = new SerializedObject(fm);
            so.FindProperty("_deviceType").enumValueIndex = (int)device;
            so.ApplyModifiedPropertiesWithoutUndo();
            sb.AppendLine($"{c.name}: {FixMorphNames(c)}");
        }
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        return sb.ToString();
    }

    /// <summary>表情枠の名前をモデルの BlendShapeClip に合わせて直し(BlinkL→Blink_L 等)、モデルに無い名前を報告する。</summary>
    private static string FixMorphNames(GameObject chara)
    {
        var fm = chara.GetComponent<vortex.FacialManager>();
        var so = new SerializedObject(fm);
        var clipNames = new HashSet<string>(chara.GetComponent<VRM.VRMBlendShapeProxy>().BlendShapeAvatar.Clips
            .Where(x => x != null).Select(x => x.BlendShapeName));
        var missing = new List<string>();
        int assigned = 0;
        foreach (var slot in MorphSlots)
        {
            var p = so.FindProperty(slot + "._morphName");
            if (p == null) continue;
            if (NameFix.TryGetValue(p.stringValue, out var fixedName) && clipNames.Contains(fixedName)) p.stringValue = fixedName;
            if (string.IsNullOrEmpty(p.stringValue)) continue;
            assigned++;
            if (!clipNames.Contains(p.stringValue)) missing.Add($"{slot}={p.stringValue}");
        }
        so.ApplyModifiedPropertiesWithoutUndo();
        return $"morph slots assigned={assigned} missing=[{string.Join(", ", missing)}]";
    }

    /// <summary>キャラ全員の表情枠の割り当て数・モデルに無い名前・ID・機器を一覧にする(保存前の確認用)。</summary>
    public static string CheckFacial()
    {
        var sb = new StringBuilder();
        foreach (var c in Characters())
        {
            var fm = c.GetComponent<vortex.FacialManager>();
            var lip = c.GetComponent<vortex.OscRx_LipSync>();
            if (fm == null) { sb.AppendLine($"{c.name}: no FacialManager"); continue; }
            var so = new SerializedObject(fm);
            var clipNames = new HashSet<string>(c.GetComponent<VRM.VRMBlendShapeProxy>().BlendShapeAvatar.Clips
                .Where(x => x != null).Select(x => x.BlendShapeName));
            var slots = MorphSlots.Select(s => (s, so.FindProperty(s + "._morphName")?.stringValue ?? "")).ToList();
            var missing = slots.Where(x => x.Item2 != "" && !clipNames.Contains(x.Item2)).Select(x => $"{x.s}={x.Item2}");
            var dev = so.FindProperty("_deviceType");
            sb.AppendLine($"{c.name}: assigned={slots.Count(x => x.Item2 != "")} missing=[{string.Join(", ", missing)}] " +
                          $"device={dev.enumNames[dev.enumValueIndex]} oscFacialID={so.FindProperty("oscFacialID").intValue} " +
                          $"characterID={(lip == null ? "none" : new SerializedObject(lip).FindProperty("characterID").intValue.ToString())}");
        }
        return sb.ToString();
    }

    // ---- テストモーション ----

    /// <summary>テストモーションの FBX を Humanoid・ループで読み込ませ、クリップ名と尺を返す。</summary>
    public static string ImportMotionAsHumanoid(string fbxPath)
    {
        var importer = (ModelImporter)AssetImporter.GetAtPath(fbxPath);
        if (importer == null) return "(not found) " + fbxPath;
        importer.animationType = ModelImporterAnimationType.Human;
        importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
        var clips = importer.defaultClipAnimations;
        foreach (var c in clips) c.loopTime = true;
        importer.clipAnimations = clips;
        importer.SaveAndReimport();
        var names = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<AnimationClip>()
            .Where(c => !c.name.StartsWith("__preview", StringComparison.Ordinal)).Select(c => $"{c.name}({c.length:F2}s)");
        return "clips: " + string.Join(", ", names);
    }
}
