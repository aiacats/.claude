// 検証用（BodyRestFix と一緒に使う）。キャラのプレハブに 2 本のクリップを同じ時刻で当て、左右に並べて 1 枚の PNG に撮る（Edit モード、シーンは保存しない）。
// 依存: vortex.PosePreset（サブモジュール。RenderHand で握りのプリセットを当てるとき）。
// ここ（~/.claude/skills/vortex-mocap-fix/templates/Editor）は Unity プロジェクトの外の写し元で、案件の Assets/_TempVerify/Editor/ へ写してから使う（trap-ok:cs-runtime-unityeditor）。
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

public static class PoseCompareRender
{
    // 描く場所。ステージ（原点付近）と水面から離した空中
    static readonly Vector3 Anchor = new Vector3(500f, 500f, 500f);

    static AnimationClip Clip(string path) => AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>()
        .First(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));

    // プレハブを置いてクリップを当て、スキンを焼いた静的メッシュにする（Edit モードではスキンの更新が描画に間に合わないため）。
    // keepYaw なら収録の向きのまま（腰を anchor に）、そうでなければ体の前を faceDir に向ける
    static void Pose(GameObject prefab, AnimationClip clip, float t, Vector3 anchor, Vector3 faceDir, bool keepYaw, Scene scene)
        => PoseWithHand(prefab, clip, t, anchor, faceDir, keepYaw, scene, true);

    // left の手の位置と向き（前 = 手首→中指の付け根、上 = 手の甲側）を持つ目印を、焼いたメッシュと一緒に動かして返す
    // afterSample: クリップを当てた後に骨へ掛ける処理（シーンで MicController が握りのプリセットを上書きするのを再現する等）
    static Transform PoseWithHand(GameObject prefab, AnimationClip clip, float t, Vector3 anchor, Vector3 faceDir, bool keepYaw, Scene scene, bool left,
        System.Action<Animator> afterSample = null)
    {
        var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
        var a = go.GetComponentInChildren<Animator>();
        clip.SampleAnimation(a.gameObject, t);
        afterSample?.Invoke(a);
        var hips = a.GetBoneTransform(HumanBodyBones.Hips);
        var side = a.GetBoneTransform(HumanBodyBones.LeftUpperLeg).position - a.GetBoneTransform(HumanBodyBones.RightUpperLeg).position;
        var fwd = Vector3.Cross(Vector3.up, Vector3.ProjectOnPlane(side, Vector3.up)).normalized;
        var root = new GameObject("baked");
        SceneManager.MoveGameObjectToScene(root, scene);
        root.transform.SetPositionAndRotation(hips.position, keepYaw ? Quaternion.identity : Quaternion.LookRotation(fwd, Vector3.up));
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        {
            if (!r.enabled || !r.gameObject.activeInHierarchy) continue;
            Mesh m;
            var b = new GameObject(r.name);
            if (r is SkinnedMeshRenderer smr)
            {
                if (smr.sharedMesh == null) { Object.DestroyImmediate(b); continue; }
                m = new Mesh(); smr.BakeMesh(m, true);
                b.transform.SetPositionAndRotation(r.transform.position, r.transform.rotation);
            }
            else if (r is MeshRenderer && r.TryGetComponent<MeshFilter>(out var mf) && mf.sharedMesh != null)
            {
                m = mf.sharedMesh;
                b.transform.SetPositionAndRotation(r.transform.position, r.transform.rotation);
                b.transform.localScale = r.transform.lossyScale;
            }
            else { Object.DestroyImmediate(b); continue; }
            b.transform.SetParent(root.transform, true);
            b.AddComponent<MeshFilter>().sharedMesh = m;
            var mr = b.AddComponent<MeshRenderer>();
            mr.sharedMaterials = r.sharedMaterials;
            mr.renderingLayerMask = r.renderingLayerMask;
            b.layer = r.gameObject.layer;
        }
        var hand = a.GetBoneTransform(left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
        var mid = a.GetBoneTransform(left ? HumanBodyBones.LeftMiddleProximal : HumanBodyBones.RightMiddleProximal);
        var idx = a.GetBoneTransform(left ? HumanBodyBones.LeftIndexProximal : HumanBodyBones.RightIndexProximal);
        var lit = a.GetBoneTransform(left ? HumanBodyBones.LeftLittleProximal : HumanBodyBones.RightLittleProximal);
        var hf = (mid.position - hand.position).normalized;
        var across = Vector3.ProjectOnPlane(idx.position - lit.position, hf).normalized;
        // 手の甲側: 左手は 前 × 幅、右手は 幅 × 前（左右で幅の向きが鏡写しになるため）
        var back = left ? Vector3.Cross(hf, across) : Vector3.Cross(across, hf);
        var marker = new GameObject("hand").transform;
        marker.SetPositionAndRotation((hand.position + mid.position) * 0.5f, Quaternion.LookRotation(hf, back));
        marker.SetParent(root.transform, true);
        Object.DestroyImmediate(go);
        root.transform.SetPositionAndRotation(anchor, keepYaw ? Quaternion.identity : Quaternion.LookRotation(faceDir, Vector3.up));
        return marker;
    }

    /// <summary>prefab に clip を時刻 t で当て、左手（left=false なら右手）を 3 方向（手の甲・手のひら・親指側）から寄って撮り、横に並べた PNG にする。</summary>
    public static string RenderHand(string prefabPath, string clipPath, float t, bool left, string pngPath) => RenderHand(prefabPath, clipPath, t, left, pngPath, "");

    /// posePresetPath を渡すと、クリップを当てた後にその PosePreset を重み 1 で掛けてから撮る（マイクの握りのプリセットが指を上書きする状態）。
    public static string RenderHand(string prefabPath, string clipPath, float t, bool left, string pngPath, string posePresetPath)
    {
        System.Action<Animator> after = null;
        if (!string.IsNullOrEmpty(posePresetPath))
        {
            var preset = AssetDatabase.LoadAssetAtPath<vortex.PosePreset>(posePresetPath);
            if (preset == null) return "no pose preset: " + posePresetPath;
            after = a => preset.ApplyPose(a, 1f);
        }
        // 描くのは一時の別シーン（Additive）で、開いているシーンには触らない（保存も閉じもしない）。編集中のシーンが開いていても撮れる
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
        try
        {
            var marker = PoseWithHand(AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath), Clip(clipPath), t, Anchor, Vector3.back, false, scene, left, after);
            var lgo = new GameObject("key");
            SceneManager.MoveGameObjectToScene(lgo, scene);
            var l = lgo.AddComponent<Light>();
            l.type = LightType.Directional; l.intensity = 1.2f;
            lgo.AddComponent<UniversalAdditionalLightData>().renderingLayers = ~0u;
            var cgo = new GameObject("cam");
            SceneManager.MoveGameObjectToScene(cgo, scene);
            var cam = cgo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 0.11f; // 手（手首から指先まで約 0.18m）が収まる大きさ
            cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.18f, 0.18f, 0.2f);
            cam.nearClipPlane = 0.05f; cam.farClipPlane = 2f;
            const int w = 700, h = 700;
            var sheet = new Texture2D(w * 3, h, TextureFormat.RGB24, false);
            var rt = new RenderTexture(w, h, 24);
            cam.targetTexture = rt;
            // 手の甲から・手のひらから・親指側から（親指側 = 手の幅の人差し指側）
            var p = marker.position; var up = marker.up; var fw = marker.forward; var thumbSide = left ? -marker.right : marker.right;
            var views = new[] { up, -up, thumbSide };
            for (int i = 0; i < 3; i++)
            {
                cgo.transform.SetPositionAndRotation(p + views[i] * 0.6f, Quaternion.LookRotation(-views[i], fw));
                lgo.transform.rotation = Quaternion.LookRotation(-views[i] + Vector3.down * 0.3f);
                cam.Render();
                RenderTexture.active = rt;
                sheet.ReadPixels(new Rect(0, 0, w, h), w * i, 0);
                RenderTexture.active = null;
            }
            sheet.Apply();
            System.IO.File.WriteAllBytes(pngPath, sheet.EncodeToPNG());
            Object.DestroyImmediate(sheet);
            cam.targetTexture = null; rt.Release(); Object.DestroyImmediate(rt);
            return "wrote " + pngPath;
        }
        finally { EditorSceneManager.CloseScene(scene, true); }
    }

    /// <summary>prefab に clipA（左）と clipB（右）を時刻 t で当てて撮る。view: "side" = 横から（体の前を画面の左へ）、
    /// "front" = 正面から、"stage" = 収録の向きのまま客席側（-Z）から。枠は腰から頭の上まで。開いているシーンが未保存なら何もしない。</summary>
    public static string Render(string prefabPath, string clipA, string clipB, float t, string view, string pngPath)
    {
        // 描くのは一時の別シーン（Additive）で、開いているシーンには触らない（保存も閉じもしない）。編集中のシーンが開いていても撮れる
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
        try
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            bool full = view.EndsWith("_full", System.StringComparison.Ordinal); // _full = 足先から頭まで
            if (full) view = view.Substring(0, view.Length - 5);
            bool keep = view == "stage";
            // 横から: 画面の右が +X、カメラは +Z を向く。体の前を -X（画面の左）へ。正面から: 体の前を -Z（カメラ）へ
            var face = view == "side" ? Vector3.left : Vector3.back;
            const float gap = 0.9f; // 2 体の間隔（m）。肩幅 0.4m 前後・腕を振る分を見込んだ値
            // 舞台の向き（stage）は客席が +Z なので、カメラを +Z に置いて -Z を向ける。そのとき画面の左は +X
            var leftOnScreen = keep ? Vector3.right : Vector3.left;
            Pose(prefab, Clip(clipA), t, Anchor + leftOnScreen * gap / 2, face, keep, scene);
            Pose(prefab, Clip(clipB), t, Anchor - leftOnScreen * gap / 2, face, keep, scene);

            var lgo = new GameObject("key");
            SceneManager.MoveGameObjectToScene(lgo, scene);
            var l = lgo.AddComponent<Light>();
            l.type = LightType.Directional; l.intensity = 1.2f;
            lgo.transform.rotation = Quaternion.Euler(30f, keep ? 150f : -30f, 0f); // カメラ側の斜め上から当てる
            lgo.AddComponent<UniversalAdditionalLightData>().renderingLayers = ~0u;

            var cgo = new GameObject("cam");
            SceneManager.MoveGameObjectToScene(cgo, scene);
            var cam = cgo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = full ? 0.95f : 0.55f; // 腰から頭の上まで（約 0.8m）、全身なら足先（腰の下 約 0.9m）まで、に余白
            cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.18f, 0.18f, 0.2f);
            cam.nearClipPlane = 0.1f; cam.farClipPlane = 10f;
            cgo.transform.SetPositionAndRotation(Anchor + new Vector3(0f, full ? 0f : 0.45f, keep ? 4f : -4f), keep ? Quaternion.Euler(0f, 180f, 0f) : Quaternion.identity);
            const int w = 1400, h = 1000;
            var rt = new RenderTexture(w, h, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = null;
            System.IO.File.WriteAllBytes(pngPath, tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            cam.targetTexture = null; rt.Release(); Object.DestroyImmediate(rt);
            return "wrote " + pngPath;
        }
        finally { EditorSceneManager.CloseScene(scene, true); }
    }
}
