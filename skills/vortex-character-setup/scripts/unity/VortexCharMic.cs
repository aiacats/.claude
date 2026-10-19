// vortex キャラセットアップ用の一時 Editor スクリプト（マイクまわり）。 trap-ok:cs-runtime-unityeditor trap-ok:cs-runtime-unityeditor-qualified
// 案件の Assets/_TempVerify/Editor/ にコピーし、MCP の invoke_method から呼ぶ。作業後は必ず削除する。手順は SKILL.md「マイク」。
// 3 つとも Edit モードで、キャラが基準の姿勢（VRM の T ポーズ）のまま呼ぶ（手本のキャラも同じ姿勢で比べる）。
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

public static class VortexCharMic
{
    /// <summary>今のシーンでパスが一致する物。無いか、同じパスが 2 つ以上あれば null（先頭を掴むと同じ名前の別物を書き換える）。</summary>
    private static GameObject Find(string path)
    {
        var hits = Resources.FindObjectsOfTypeAll<GameObject>()
            .Where(g => g.scene.IsValid() && g.scene == EditorSceneManager.GetActiveScene() && PathOf(g.transform) == path)
            .Take(2).ToList();
        return hits.Count == 1 ? hits[0] : null;
    }

    const string NotFound = " (not found, or 2+ objects share the path)";

    /// <summary>握りのプリセット（PosePreset._targetBones の _humanbone）がどちらの手の指か。左手 24〜38・右手 39〜53。混ざる・どちらも無いときは null。</summary>
    private static string PresetHand(Object preset)
    {
        var bones = new SerializedObject(preset).FindProperty("_targetBones");
        if (bones == null || !bones.isArray) return null;
        bool left = false, right = false;
        for (int i = 0; i < bones.arraySize; i++)
        {
            var b = bones.GetArrayElementAtIndex(i).FindPropertyRelative("_humanbone");
            if (b == null) continue;
            int v = b.intValue;
            if (v >= (int)HumanBodyBones.LeftThumbProximal && v <= (int)HumanBodyBones.LeftLittleDistal) left = true;
            if (v >= (int)HumanBodyBones.RightThumbProximal && v <= (int)HumanBodyBones.RightLittleDistal) right = true;
        }
        return left == right ? null : left ? "LeftHand" : "RightHand";
    }

    private static string PathOf(Transform t)
    {
        var sb = new StringBuilder(t.name);
        for (var p = t.parent; p != null; p = p.parent) sb.Insert(0, p.name + "/");
        return sb.ToString();
    }

    /// <summary>キャラの Humanoid の Animator（ルートか子。HoloSDK のキャラは子に付く）。</summary>
    private static Animator HumanAnimator(GameObject character) =>
        character.GetComponentsInChildren<Animator>(true).FirstOrDefault(a => a.isHuman && a.avatar != null);

    /// <summary>
    /// 表情「A」（口を開く）で動く頂点（動きが最大の minDeltaRatio 倍以上）の位置を集める。頭の骨と、顔の前方向（頭の骨 → 動く頂点の重心の水平の向き）も返す。
    /// </summary>
    static string MovedMouthVertices(GameObject character, float minDeltaRatio, out Transform head, out List<Vector3> moved, out Vector3 fwd, out string info)
    {
        head = null; moved = null; fwd = Vector3.forward; info = "";
        var anim = HumanAnimator(character);
        head = anim != null ? anim.GetBoneTransform(HumanBodyBones.Head) : null;
        if (head == null) return "error: humanoid head bone not found";
        var proxy = character.GetComponentsInChildren<VRM.VRMBlendShapeProxy>(true).FirstOrDefault();
        var clip = proxy != null && proxy.BlendShapeAvatar != null
            ? proxy.BlendShapeAvatar.Clips.FirstOrDefault(c => c != null && c.Preset == VRM.BlendShapePreset.A)
            : null;
        if (clip == null || clip.Values.Length == 0) return "error: no blend shape clip A on the VRMBlendShapeProxy";
        var root = proxy.transform;
        // 1) 表情 A の頂点の動き（メッシュの空間）から、動く頂点を選ぶ。2) その頂点だけを、今の骨の位置で線形スキニングして世界の位置にする。
        //    BakeMesh は無効（非表示）のキャラでは骨の姿勢を反映せず、14 cm ずれた（2026-10-19 きまゆ・Anjo・Kosaka）。
        var cand = new List<(SkinnedMeshRenderer smr, int index, float delta)>();
        foreach (var b in clip.Values)
        {
            var t = root.Find(b.RelativePath);
            var smr = t != null ? t.GetComponent<SkinnedMeshRenderer>() : null;
            if (smr == null || smr.sharedMesh == null || b.Index < 0 || b.Index >= smr.sharedMesh.blendShapeCount) continue;
            var mesh = smr.sharedMesh;
            int frame = mesh.GetBlendShapeFrameCount(b.Index) - 1;
            var dv = new Vector3[mesh.vertexCount];
            mesh.GetBlendShapeFrameVertices(b.Index, frame, dv, null, null);
            for (int i = 0; i < dv.Length; i++)
                if (dv[i].sqrMagnitude > 0f) cand.Add((smr, i, dv[i].magnitude * b.Weight / 100f));
        }
        if (cand.Count == 0) return "error: clip A moves no vertex (or its bindings point to no skinned mesh)";
        float max = cand.Max(c => c.delta);
        var points = new List<(Vector3 pos, float delta)>();
        foreach (var g in cand.Where(c => c.delta >= max * minDeltaRatio).GroupBy(c => c.smr))
        {
            var smr = g.Key;
            var mesh = smr.sharedMesh;
            var verts = mesh.vertices;
            var bones = smr.bones;
            var binds = mesh.bindposes;
            var weights = mesh.boneWeights;
            bool skinned = bones.Length > 0 && binds.Length == bones.Length && weights.Length == verts.Length;
            foreach (var c in g)
            {
                var v = verts[c.index];
                Vector3 w;
                if (skinned)
                {
                    var bw = weights[c.index];
                    w = Vector3.zero;
                    void Add(int bi, float wt) { if (wt > 0f && bones[bi] != null) w += wt * (Vector3)(bones[bi].localToWorldMatrix * binds[bi]).MultiplyPoint3x4(v); }
                    Add(bw.boneIndex0, bw.weight0); Add(bw.boneIndex1, bw.weight1); Add(bw.boneIndex2, bw.weight2); Add(bw.boneIndex3, bw.weight3);
                }
                else w = smr.transform.TransformPoint(v); // 骨の無いメッシュ（スキニングしない）はレンダラーの位置そのもの
                points.Add((w, c.delta));
            }
        }
        if (max <= 0f) return "error: clip A moves no vertex";
        moved = points.Select(p => p.pos).ToList();
        var center = moved.Aggregate(Vector3.zero, (a, p) => a + p) / moved.Count;
        var h = Vector3.ProjectOnPlane(center - head.position, Vector3.up);
        if (h.sqrMagnitude > 1e-8f) fwd = h.normalized; // ルートの向きは案件・モデルで違うので、口が頭の骨の前にあることから向きを決める
        info = $"moved vertices {moved.Count}/{cand.Count}, max delta {max * 100f:F2} cm (mesh space)";
        return null;
    }

    /// <summary>
    /// 口の位置の候補。動く頂点の重心の左右（right）はそのまま、前は動く頂点の最も前（唇の表面）、高さは方式で決める。
    /// heightMode: "centroid" = 重心の高さ / "pNN" = 動く頂点の高さの NN パーセンタイル（例 p75）
    /// </summary>
    static Vector3 MouthFrom(List<Vector3> moved, Vector3 fwd, string heightMode)
    {
        var center = moved.Aggregate(Vector3.zero, (a, p) => a + p) / moved.Count;
        float front = moved.Max(p => Vector3.Dot(p - center, fwd));
        var pos = center + fwd * front;
        if (heightMode.StartsWith("p", StringComparison.Ordinal) && int.TryParse(heightMode.Substring(1), out int pct))
        {
            var ys = moved.Select(p => p.y).OrderBy(y => y).ToList();
            pos.y = ys[Mathf.Clamp(Mathf.RoundToInt(pct / 100f * (ys.Count - 1)), 0, ys.Count - 1)];
        }
        return pos;
    }

    /// <summary>
    /// MicController の targets のうち、口（_mouthTransform）が置いてある枠について、人が置いた位置と候補（heightModes をカンマ区切り）のずれ（cm）を並べる。シーンは変えない。
    /// </summary>
    public static string CompareMouths(string micControllerPath, float minDeltaRatio, string heightModes)
    {
        var mcGo = Find(micControllerPath);
        var mc = mcGo != null ? mcGo.GetComponents<Component>().FirstOrDefault(c => c != null && c.GetType().Name == "MicController") : null;
        if (mc == null) return "error: MicController" + NotFound + " at " + micControllerPath;
        var modes = heightModes.Split(',');
        var sum = new float[modes.Length];
        int n = 0;
        var sb = new StringBuilder();
        var targets = new SerializedObject(mc).FindProperty("_targets");
        for (int i = 0; i < targets.arraySize; i++)
        {
            var t = targets.GetArrayElementAtIndex(i);
            var mouthT = t.FindPropertyRelative("_mouthTransform").objectReferenceValue as Transform;
            var anim = t.FindPropertyRelative("_targetAnimator").objectReferenceValue as Animator;
            if (mouthT == null || anim == null) continue;
            var proxyOwner = anim.GetComponentInParent<VRM.VRMBlendShapeProxy>(true);
            var character = proxyOwner != null ? proxyOwner.gameObject : anim.gameObject;
            var err = MovedMouthVertices(character, minDeltaRatio, out var head, out var moved, out var fwd, out var info);
            if (err != null) { sb.AppendLine($"[{i}] {character.name}: {err}"); continue; }
            var right = Vector3.Cross(Vector3.up, fwd);
            var human = mouthT.position - head.position;
            sb.Append($"[{i}] {character.name} human (fwd {Vector3.Dot(human, fwd) * 100f:F1}, up {human.y * 100f:F1}, right {Vector3.Dot(human, right) * 100f:F1}) cm from head |");
            for (int k = 0; k < modes.Length; k++)
            {
                var d = MouthFrom(moved, fwd, modes[k]) - mouthT.position;
                sum[k] += d.magnitude;
                sb.Append($" {modes[k]} {d.magnitude * 100f:F1} (fwd {Vector3.Dot(d, fwd) * 100f:+0.0;-0.0} up {d.y * 100f:+0.0;-0.0})");
            }
            sb.AppendLine($" | {info}");
            n++;
        }
        if (n > 0) sb.AppendLine("mean error cm: " + string.Join(", ", modes.Select((m, k) => $"{m} {sum[k] / n * 100f:F2}")));
        return sb.ToString();
    }

    /// <summary>
    /// 口の位置を、VRM の表情「A」（口を開く）で動く頂点から求め、Head の子に MicMouth を作る（あれば位置を置き直す）。
    /// 位置: MouthFrom（heightMode）。人が置いた MicMouth と比べるときは compareWith に既存の MicMouth のパスを渡すと、ずれ（cm）を返す。
    /// </summary>
    public static string CreateMicMouth(string characterPath, float minDeltaRatio, string compareWith) =>
        CreateMicMouth(characterPath, minDeltaRatio, "centroid", compareWith);

    public static string CreateMicMouth(string characterPath, float minDeltaRatio, string heightMode, string compareWith)
    {
        var character = Find(characterPath);
        if (character == null) return "error: character" + NotFound + ": " + characterPath;
        var err = MovedMouthVertices(character, minDeltaRatio, out var head, out var moved, out var fwd, out var info);
        if (err != null) return err;
        var mouth = MouthFrom(moved, fwd, heightMode);

        // 人が置いた MicMouth と比べるときは、置き直す前に比べる（同じ物を渡されたときに 0 にならないように）
        string compare = "";
        if (!string.IsNullOrEmpty(compareWith))
        {
            var other = Find(compareWith);
            if (other == null) compare = $"\ncompare:{NotFound} {compareWith}";
            else
            {
                var d = mouth - other.transform.position;
                var local = Quaternion.Inverse(character.transform.rotation) * d;
                compare = $"\ncompare with {compareWith}: {d.magnitude * 100f:F2} cm (right {local.x * 100f:+0.00;-0.00} up {local.y * 100f:+0.00;-0.00} forward {local.z * 100f:+0.00;-0.00} cm)";
            }
        }

        var existing = head.Find("MicMouth");
        var mm = existing != null ? existing : new GameObject("MicMouth").transform;
        if (existing == null)
        {
            Undo.RegisterCreatedObjectUndo(mm.gameObject, "Create MicMouth");
            Undo.RecordObject(mm, "Place MicMouth"); // 作った直後の代入が Undo の flush で巻き戻らないように
            mm.SetParent(head, false);
        }
        else Undo.RecordObject(mm, "Place MicMouth");
        mm.gameObject.layer = head.gameObject.layer;
        mm.SetPositionAndRotation(mouth, Quaternion.LookRotation(fwd, Vector3.up));
        EditorSceneManager.MarkSceneDirty(character.scene);

        return $"{(existing != null ? "moved" : "created")} {PathOf(mm)} local {mm.localPosition.ToString("F3")} " +
               $"({info}, from head {Vector3.Distance(mouth, head.position) * 100f:F1} cm)" + compare;
    }

    /// <summary>
    /// 手本のキャラのマイク（templateMicPath）と同じプレハブを、キャラの同じ側の手の骨の子に置く。
    /// 置き方: 手本の「手の骨からマイクまでのずれ」と「マイクの向き」を、手本のキャラのルートの向きで表して、新しいキャラに当てる。
    /// どちらも基準の姿勢（T ポーズ）で、手の骨の軸の取り方がキャラごとに違っても位置と向きが揃う。握り（指）とマイクの寄せ方は MicController で決まる。
    /// </summary>
    public static string PlaceMicLike(string templateMicPath, string characterPath)
    {
        var tmic = Find(templateMicPath);
        var character = Find(characterPath);
        if (tmic == null) return "error: template mic" + NotFound + ": " + templateMicPath;
        if (character == null) return "error: character" + NotFound + ": " + characterPath;
        var source = PrefabUtility.GetCorrespondingObjectFromSource(tmic);
        if (source == null) return "error: the template mic is not a prefab instance (cannot tell which prefab to place)";
        var tchar = tmic.transform.GetComponentInParent<VRM.VRMBlendShapeProxy>(true);
        var tanim = tchar != null ? HumanAnimator(tchar.gameObject) : null;
        var anim = HumanAnimator(character);
        if (tanim == null || anim == null) return "error: humanoid animator not found (template or character)";
        HumanBodyBones side;
        if (tmic.transform.IsChildOf(tanim.GetBoneTransform(HumanBodyBones.RightHand))) side = HumanBodyBones.RightHand;
        else if (tmic.transform.IsChildOf(tanim.GetBoneTransform(HumanBodyBones.LeftHand))) side = HumanBodyBones.LeftHand;
        else return "error: the template mic is not under the template's hand bone";
        var thand = tanim.GetBoneTransform(side);
        var hand = anim.GetBoneTransform(side);
        // 二度呼んだとき（MCP の timeout の後の再送など）に 2 本目を置かない
        var placed = hand.GetComponentsInChildren<Transform>(true)
            .FirstOrDefault(t => PrefabUtility.IsOutermostPrefabInstanceRoot(t.gameObject) && PrefabUtility.GetCorrespondingObjectFromSource(t.gameObject) == source);
        if (placed != null) return $"error: already placed: {PathOf(placed)}";

        var troot = tchar.transform.rotation;
        var root = character.transform.rotation;
        var offset = Quaternion.Inverse(troot) * (tmic.transform.position - thand.position);
        var rotRel = Quaternion.Inverse(troot) * tmic.transform.rotation;
        var mic = (GameObject)PrefabUtility.InstantiatePrefab(source, character.scene);
        Undo.RegisterCreatedObjectUndo(mic, "Place mic");
        Undo.RecordObject(mic.transform, "Place mic");
        mic.transform.SetParent(hand, false);
        mic.transform.SetPositionAndRotation(hand.position + root * offset, root * rotRel);
        // 大きさは世界での大きさを手本に合わせる（手本の親が PropAnchor のような拡大縮小付きの中間ノードでも揃う。骨の拡大縮小は等方とみなす）
        var hs = hand.lossyScale;
        var ts = tmic.transform.lossyScale;
        mic.transform.localScale = new Vector3(ts.x / hs.x, ts.y / hs.y, ts.z / hs.z);
        // レイヤーは手本の同じ位置の物から（番組カメラに写るかは手本と同じになる）。手本に無い子は手本のルートのレイヤー
        foreach (var t in mic.GetComponentsInChildren<Transform>(true))
        {
            var rel = t == mic.transform ? "" : PathOf(t).Substring(PathOf(mic.transform).Length + 1);
            var same = rel == "" ? tmic.transform : tmic.transform.Find(rel);
            t.gameObject.layer = (same != null ? same : tmic.transform).gameObject.layer;
        }
        EditorSceneManager.MarkSceneDirty(character.scene);
        return $"placed {AssetDatabase.GetAssetPath(source)} at {PathOf(mic.transform)} (side {side}, offset {offset.ToString("F3")} m in root space," +
               $" layer {LayerMask.LayerToName(mic.layer)} like the template, world scale {mic.transform.lossyScale.ToString("F3")})";
    }

    /// <summary>
    /// MicController の targets に、templateIndex の枠を写した新しい枠を足す（寄せ方・半径・距離・補正の型は手本のまま）。
    /// キャラ固有の参照（Animator・マイク・口・握りのプリセット・名前）を差し替え、手・手首・距離の基準の骨は空にする（実行時に Animator から埋まる）。
    /// 手（右・左）はマイクの親の骨から決める。gripPresetPath が空なら手本のプリセットのまま（手と合わないと黙って効かないので、手が違えば断る）。
    /// </summary>
    public static string AddMicTargetLike(string micControllerPath, int templateIndex, string characterPath, string micPath, string mouthPath, string gripPresetPath, string name)
    {
        var mcGo = Find(micControllerPath);
        var mc = mcGo != null ? mcGo.GetComponents<Component>().FirstOrDefault(c => c != null && c.GetType().Name == "MicController") : null;
        if (mc == null) return "error: MicController" + NotFound + " at " + micControllerPath;
        var character = Find(characterPath);
        var mic = Find(micPath);
        var mouth = Find(mouthPath);
        if (character == null || mic == null || mouth == null) return $"error:{NotFound} (character {character != null}, mic {mic != null}, mouth {mouth != null})";
        var anim = HumanAnimator(character);
        if (anim == null) return "error: humanoid animator not found";
        string hand = mic.transform.IsChildOf(anim.GetBoneTransform(HumanBodyBones.RightHand)) ? "RightHand"
            : mic.transform.IsChildOf(anim.GetBoneTransform(HumanBodyBones.LeftHand)) ? "LeftHand" : null;
        if (hand == null) return "error: the mic is not under the character's hand bone";

        var so = new SerializedObject(mc);
        var targets = so.FindProperty("_targets");
        if (templateIndex < 0 || templateIndex >= targets.arraySize) return $"error: templateIndex {templateIndex} out of range (targets {targets.arraySize})";
        // 二度呼んだとき（MCP の timeout の後の再送など）に同じキャラの枠を 2 つ作らない
        for (int i = 0; i < targets.arraySize; i++)
            if (targets.GetArrayElementAtIndex(i).FindPropertyRelative("_targetAnimator").objectReferenceValue == anim)
                return $"error: the MicController already has a target for this character: [{i}]";
        Object grip = null;
        if (!string.IsNullOrEmpty(gripPresetPath))
        {
            grip = AssetDatabase.LoadMainAssetAtPath(gripPresetPath);
            if (grip == null) return "error: grip preset not found: " + gripPresetPath;
        }
        var tmpl = targets.GetArrayElementAtIndex(templateIndex);
        var handProp = tmpl.FindPropertyRelative("_handOption");
        string tmplHand = handProp.enumNames[handProp.enumValueIndex];
        if (grip == null && tmplHand != hand) return $"error: the template is {tmplHand} but the mic is in the {hand}; pass a grip preset for the {hand}";
        // 握りのプリセットは、マイクを持つ手の指のものでないと黙って効かない
        var effectiveGrip = grip != null ? grip : tmpl.FindPropertyRelative("_gripPosePreset").objectReferenceValue;
        string gripHand = effectiveGrip != null ? PresetHand(effectiveGrip) : null;
        if (gripHand != null && gripHand != hand)
            return $"error: the grip preset {effectiveGrip.name} is for the {gripHand} but the mic is in the {hand}";

        Undo.RecordObject(mc, "Add mic target");
        targets.InsertArrayElementAtIndex(templateIndex); // 手本の直後に同じ中身の要素ができる
        int index = targets.arraySize - 1;
        targets.MoveArrayElement(templateIndex + 1, index);
        var t = targets.GetArrayElementAtIndex(index);
        t.FindPropertyRelative("_name").stringValue = string.IsNullOrEmpty(name) ? character.name : name;
        t.FindPropertyRelative("_targetAnimator").objectReferenceValue = anim;
        t.FindPropertyRelative("_additionalTargetAnimators").arraySize = 0;
        var hp = t.FindPropertyRelative("_handOption");
        hp.enumValueIndex = Array.IndexOf(hp.enumNames, hand);
        var mics = t.FindPropertyRelative("_microphoneObjects");
        mics.arraySize = 1;
        mics.GetArrayElementAtIndex(0).objectReferenceValue = mic;
        t.FindPropertyRelative("_dissolveMaterialTargets").arraySize = 0; // 手本のマイクの Renderer を指したままにしない
        if (grip != null) t.FindPropertyRelative("_gripPosePreset").objectReferenceValue = grip;
        t.FindPropertyRelative("_micTransform").objectReferenceValue = mic.transform;
        t.FindPropertyRelative("_mouthTransform").objectReferenceValue = mouth.transform;
        foreach (var bone in new[] { "_distanceBaseBone", "_handBone", "_handAimBone" })
            t.FindPropertyRelative(bone).objectReferenceValue = null;
        so.ApplyModifiedProperties();
        EditorSceneManager.MarkSceneDirty(mc.gameObject.scene);
        return $"added target [{index}] '{t.FindPropertyRelative("_name").stringValue}' {hand} like [{templateIndex}]" +
               $" (dissolve targets cleared{(t.FindPropertyRelative("_useNiloToonDissolve").boolValue ? "; the template uses NiloToon dissolve: set the mic renderers by hand" : "")})";
    }
}
