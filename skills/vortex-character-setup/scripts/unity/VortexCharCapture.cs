// vortex キャラセットアップ用の一時 Editor スクリプト（映像・表情表の撮影側）。trap-ok:cs-runtime-unityeditor trap-ok:cs-runtime-unityeditor-qualified
// 案件の Assets/_TempVerify/Editor/ にコピーし（VortexCharTool.cs と、vortex-timeline-export の RecGameView.cs も一緒に）、
// MCP の invoke_method から呼ぶ。作業後は必ず削除する。手順と引数は SKILL.md。
// どれもシーンは保存しない前提（Timeline・一時カメラ・OptitrackSkeletonAnimator の無効化は Cleanup で開き直して捨てる）。
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Rendering.Universal;
using UnityEngine.Timeline;
using Object = UnityEngine.Object;

public static class VortexCharCapture
{
    private const BindingFlags Flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    public const string DirectorPrefix = "MotionTest_Director_";   // 1 人ずつ: _0, _1, ... / 全員: _All
    public const string ChartPrefabPath =
        "Packages/jp.pjblue.realtime-live-utility/Script/Editor/EditSupport/KuniDemo/CreateFacialImageUI/CreateFacialImage_String.prefab";

    // 身長の目安と体の中心の高さ。vortex のキャラは 1.6〜1.7m
    private const float CharacterHeight = 1.65f;
    private const float BodyCenterHeight = 0.85f;

    private static AnimationClip LoadClip(string clipFbxPath) =>
        AssetDatabase.LoadAllAssetsAtPath(clipFbxPath).OfType<AnimationClip>()
            .First(c => !c.name.StartsWith("__preview", StringComparison.Ordinal));

    // ルートに Animator が無いモデル（子に Humanoid の Animator を持つ。Ext_TokinoSora_2026-pia のそら・リオナ）もあるので、
    // ルート → 子の順に Humanoid の Animator を探す
    private static Animator HumanoidAnimator(GameObject chara)
    {
        if (chara.TryGetComponent<Animator>(out var root) && root.isHuman) return root;
        var child = chara.GetComponentsInChildren<Animator>(true).FirstOrDefault(a => a.isHuman);
        if (child == null) throw new InvalidOperationException($"{chara.name}: Humanoid の Animator が見つからない");
        return child;
    }

    // ---- Timeline ----

    /// <summary>
    /// テストモーションの Timeline を作る(Edit モードで呼ぶ)。
    /// - 1 人ずつ: MotionTest_Director_0.. (キャラごと、オフセット無し = センター)
    /// - 全員: MotionTest_Director_All (左右 spacing ずつ離して並べる。シーンの配置は触らず、トラックのオフセットで動かす)
    /// どちらも Activation トラックで全尺表示。OptitrackSkeletonAnimator はポーズを上書きするので無効にする。
    /// </summary>
    public static string BuildTimelines(string clipFbxPath, string timelineFolder, float spacing)
    {
        var clip = LoadClip(clipFbxPath);
        var chars = VortexCharTool.Characters();
        var sb = new StringBuilder();

        PlayableDirector NewDirector(string name, string assetName, out TimelineAsset timeline)
        {
            timeline = ScriptableObject.CreateInstance<TimelineAsset>();
            AssetDatabase.CreateAsset(timeline, $"{timelineFolder}/{assetName}.playable");
            var old = GameObject.Find(name);
            if (old != null) Object.DestroyImmediate(old);
            var d = new GameObject(name).AddComponent<PlayableDirector>();
            d.playOnAwake = false;
            d.extrapolationMode = DirectorWrapMode.None;
            d.playableAsset = timeline;
            return d;
        }

        void AddTracks(PlayableDirector d, TimelineAsset timeline, GameObject c, float x)
        {
            var act = timeline.CreateTrack<ActivationTrack>(null, c.name + " Active");
            var actClip = act.CreateDefaultClip();
            actClip.start = 0;
            actClip.duration = clip.length;
            act.postPlaybackState = ActivationTrack.PostPlaybackState.Revert;
            d.SetGenericBinding(act, c);

            var anim = timeline.CreateTrack<AnimationTrack>(null, c.name + " Motion");
            anim.CreateClip(clip).start = 0;
            anim.trackOffset = TrackOffset.ApplyTransformOffsets;
            anim.position = new Vector3(x, 0f, 0f);
            anim.rotation = Quaternion.identity;
            d.SetGenericBinding(anim, HumanoidAnimator(c));
        }

        for (int i = 0; i < chars.Count; i++)
        {
            var d = NewDirector(DirectorPrefix + i, "MotionTest_" + i, out var tl);
            AddTracks(d, tl, chars[i], 0f);
            EditorUtility.SetDirty(tl);
            sb.AppendLine($"{DirectorPrefix}{i} -> {chars[i].name}");
        }
        var all = NewDirector(DirectorPrefix + "All", "MotionTest_All", out var tlAll);
        for (int i = 0; i < chars.Count; i++)
            AddTracks(all, tlAll, chars[i], (i - (chars.Count - 1) * 0.5f) * spacing);
        EditorUtility.SetDirty(tlAll);
        sb.AppendLine($"{DirectorPrefix}All -> {chars.Count} characters, spacing {spacing}m");

        foreach (var c in chars)
            foreach (var b in c.GetComponents<Behaviour>().Where(b => b != null && b.GetType().Name == "OptitrackSkeletonAnimator"))
                b.enabled = false;

        AssetDatabase.SaveAssets();
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        return $"clip={clip.name} duration={clip.length:F2}s\n" + sb;
    }

    /// <summary>Play 中に呼ぶ。index のキャラだけを表示する(-1 で全員)。</summary>
    public static string ShowOnly(int index)
    {
        var chars = VortexCharTool.Characters();
        for (int i = 0; i < chars.Count; i++) chars[i].SetActive(index < 0 || i == index);
        return index < 0 ? $"show all ({chars.Count})" : $"show {chars[index].name}";
    }

    /// <summary>Humanoid クリップのルート移動(RootT.x / RootT.z)の範囲を t=0 基準で返す("minX,maxX,minZ,maxZ")。</summary>
    public static string ClipRootExtents(string clipFbxPath)
    {
        var clip = LoadClip(clipFbxPath);
        AnimationCurve cx = null, cz = null;
        foreach (var b in AnimationUtility.GetCurveBindings(clip))
        {
            if (b.propertyName == "RootT.x") cx = AnimationUtility.GetEditorCurve(clip, b);
            if (b.propertyName == "RootT.z") cz = AnimationUtility.GetEditorCurve(clip, b);
        }
        if (cx == null || cz == null) return "RootT curves (not found)";
        float minX = float.MaxValue, maxX = float.MinValue, minZ = float.MaxValue, maxZ = float.MinValue;
        float x0 = cx.Evaluate(0), z0 = cz.Evaluate(0);
        for (float t = 0; t <= clip.length; t += 1f / 60f)
        {
            float x = cx.Evaluate(t) - x0, z = cz.Evaluate(t) - z0;
            minX = Mathf.Min(minX, x); maxX = Mathf.Max(maxX, x); minZ = Mathf.Min(minZ, z); maxZ = Mathf.Max(maxZ, z);
        }
        return $"{minX:F3},{maxX:F3},{minZ:F3},{maxZ:F3}";
    }

    // ---- 撮影カメラ ----

    /// <summary>
    /// Play 中に呼ぶ。キャラの正面から写す一時カメラを targetDisplay(0 始まり)に置き、確認用の白色ライトを足す。
    /// - 描き方は Camera_PGM を写す(ポストプロセス込み)。PGM 専用 Volume の被写界深度は焦点が合わないので、Volume は Default だけを見る。
    /// - 寄り: heightRatio &gt; 0 なら「身長が画面の高さに占める割合」で距離を決める(距離 = 身長/割合/2/tan(FoV/2))。
    ///         0 なら count 人・左右 spacing・ルート移動 rootMinX..rootMaxX が 16:9 に 1.15 倍の余白で収まる距離にする。
    /// - 高さ: camHeight(m)。体の中心(0.85m)を見る。ユーザーは低め・ほぼ水平を好む(既定 0.4m で少し見上げる)。
    /// - 手前へ来る移動(rootMaxZ)の分だけ後ろへ下げる。
    /// </summary>
    public static string SetupCamera(int targetDisplay0Based, int count, float spacing,
        float rootMinX, float rootMaxX, float rootMaxZ, float heightRatio, float camHeight)
    {
        var chara = VortexCharTool.Characters().First();
        var root = chara.transform.parent != null ? chara.transform.parent : chara.transform;
        var facing = root.forward;   // キャラが向いている側(カメラを置く側)

        foreach (var old in new[] { "__MotionTestCam", "__MotionTestLight" })
        {
            var o = GameObject.Find(old);
            if (o != null) Object.Destroy(o);
        }

        var cam = CreateCameraLikePgm("__MotionTestCam", chara);
        cam.targetDisplay = targetDisplay0Based;
        cam.fieldOfView = 30f;
        cam.nearClipPlane = 0.05f;
        float tanHalf = Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);

        float dist;
        float near;
        if (heightRatio > 0f)
        {
            dist = CharacterHeight / heightRatio * 0.5f / tanHalf;
            near = 0f;
        }
        else
        {
            // カメラは立ち位置の中心(X=0)から動かさないので、横幅は左右の移動のうち大きい方で取る。
            // 横: 両端の立ち位置の間隔の半分 + 腕を広げた幅の半分 0.5m + 片側の最大移動量、縦: 身長 1.8m
            float travel = Mathf.Max(Mathf.Abs(rootMinX), Mathf.Abs(rootMaxX));
            float halfW = ((count - 1) * spacing * 0.5f + 0.5f + travel) * 1.15f;
            float halfH = Mathf.Max(0.9f * 1.15f, halfW / (16f / 9f));
            dist = halfH / tanHalf;
            near = rootMaxZ;
        }

        // カメラは立ち位置の中心(Character の原点 = センター)の正面に置く(ユーザー指定: ワールド X を 0 に揃える)。
        // 移動範囲の中央へ寄せると、センターに立つキャラが画面中央からずれて見える。
        var bodyCenter = root.position + Vector3.up * BodyCenterHeight;
        var pos = bodyCenter + facing * (near + dist);
        pos.y = root.position.y + camHeight;
        cam.transform.position = pos;
        cam.transform.LookAt(bodyCenter);

        AddCheckLight("__MotionTestLight", facing, cam.transform.right);
        return $"camera at {cam.transform.position:F2} dist={dist:F2}+{near:F2} pitch={cam.transform.eulerAngles.x:F1}";
    }

    /// <summary>Camera_PGM と同じ Camera / URP 設定のカメラを作る(出力先 RT は外し、Volume は Default だけにする)。</summary>
    private static Camera CreateCameraLikePgm(string name, GameObject anyCharacter)
    {
        var cam = new GameObject(name).AddComponent<Camera>();
        var pgm = Resources.FindObjectsOfTypeAll<Camera>()
            .FirstOrDefault(c => c.gameObject.scene == anyCharacter.scene && c.name == "Camera_PGM");
        if (pgm == null) throw new InvalidOperationException("Camera_PGM (not found)");
        EditorUtility.CopySerialized(pgm, cam);
        EditorUtility.CopySerialized(pgm.GetComponent<UniversalAdditionalCameraData>(), cam.GetUniversalAdditionalCameraData());
        cam.GetUniversalAdditionalCameraData().volumeLayerMask = 1;   // Default レイヤーの Volume だけ
        cam.targetTexture = null;
        return cam;
    }

    /// <summary>全 Rendering Layer に当たる確認用の白色ライト(ライブ用ライトは DMX 無しでは消灯しているため)。</summary>
    private static void AddCheckLight(string name, Vector3 facing, Vector3 camRight)
    {
        var light = new GameObject(name).AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 1.2f;
        // URP では Light.renderingLayerMask は効かない（キャラが Character の Rendering Layer だけのライトを受ける案件で真っ黒になる）。
        // URP の追加データの renderingLayers で全レイヤーに当てる
        light.GetUniversalAdditionalLightData().renderingLayers = uint.MaxValue;
        light.transform.rotation = Quaternion.LookRotation(-facing + Vector3.down * 0.6f + camRight * 0.3f, Vector3.up);
    }

    // ---- 表情表 ----

    // BlendShape_Screenshot は取り込みパッケージ(VST)にも同名の別クラスがある。表のレイアウト欄(_facialImageObj)を持つ vortex 版を選ぶ
    private static Type ScreenshotWindowType() =>
        AppDomain.CurrentDomain.GetAssemblies()
            .SelectMany(a => { try { return a.GetTypes(); } catch { return Type.EmptyTypes; } })
            .First(t => t.Name == "BlendShape_Screenshot" && t.GetField("_facialImageObj", Flags) != null);

    /// <summary>
    /// Play 中に呼ぶ。index のキャラだけを表示し、顔を正面から写す一時カメラと確認用ライト、表のレイアウト(CreateFacialImage_String.prefab)を置き、
    /// Window/vortex/BlendShape_Screenshot の「Capture BlendShape Results」と同じ処理を始める。
    /// 撮影は Editor の更新で 1 枚ずつ進むので、終わるまで Unity を前面に保つ(keep_front_until.ps1)。
    /// outputFolder に表情ごとの画像と、表 &lt;キャラ名&gt;.png ができる。
    /// </summary>
    public static string StartFacialCapture(int index, string outputFolder)
    {
        try
        {
            var chars = VortexCharTool.Characters();
            for (int i = 0; i < chars.Count; i++) chars[i].SetActive(i == index);
            var chara = chars[index];
            var root = chara.transform;
            var head = HumanoidAnimator(chara).GetBoneTransform(HumanBodyBones.Head);
            // 顔の中心は頭のボーン(首の付け根寄り)より上。0.08m は頭の高さ 0.2m 強の約 1/3
            var faceCenter = head.position + root.up * 0.08f;

            foreach (var old in new[] { "__FaceCam", "__FaceLight", "__FacialChart" })
            {
                var o = GameObject.Find(old);
                if (o != null) Object.Destroy(o);
            }

            var cam = CreateCameraLikePgm("__FaceCam", chara);
            cam.targetDisplay = 7;   // 画面には出さない(撮影は RenderTexture へ描く)
            // 頭頂〜あご 0.25m に前髪・髪飾りの余白を足した 0.45m を縦に収める
            cam.fieldOfView = 20f;
            float dist = 0.45f * 0.5f / Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
            cam.transform.position = faceCenter + root.forward * dist;
            cam.transform.LookAt(faceCenter);
            AddCheckLight("__FaceLight", root.forward, cam.transform.right);

            var chart = Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(ChartPrefabPath));
            chart.name = "__FacialChart";
            chart.transform.position = new Vector3(0f, -500f, 0f);   // ステージやキャラと重ならないよう離す

            var windowType = ScreenshotWindowType();
            var window = EditorWindow.GetWindow(windowType);
            windowType.GetField("vrmPrefab", Flags).SetValue(window, chara);
            windowType.GetField("outputFolder", Flags).SetValue(window, AssetDatabase.LoadAssetAtPath<DefaultAsset>(outputFolder));
            windowType.GetField("_facialImageObj", Flags).SetValue(window, chart);
            var cams = (List<Camera>)windowType.GetField("cameraObjects", Flags).GetValue(window);
            cams.Clear();
            cams.Add(cam);
            windowType.GetField("isTextActive", Flags).SetValue(window, true);
            windowType.GetMethod("BeginCapture", Flags).Invoke(window, null);
            return $"capturing {chara.name} -> {outputFolder} (face dist {dist:F2}m)";
        }
        catch (Exception e) { return "FAILED: " + e; }
    }

    /// <summary>撮影中かどうか(BlendShape_Screenshot.isCapturing)。</summary>
    public static string IsCapturing()
    {
        var windowType = ScreenshotWindowType();
        var window = Resources.FindObjectsOfTypeAll(windowType).FirstOrDefault();
        return window == null ? "no window" : ((bool)windowType.GetField("isCapturing", Flags).GetValue(window)).ToString();
    }

    // ---- 後片付け ----

    /// <summary>
    /// 撮影ウィンドウ(同名の VST 版も)と、録画用に浮かせた Game View(ドッキングしていないもの)を閉じる。
    /// Edit モードなら、さらにシーンを保存せずに開き直して Timeline・Optitrack の無効化などを捨てる(reopenScenePath が空なら開き直さない)。
    /// </summary>
    public static string Cleanup(string reopenScenePath)
    {
        int shots = 0;
        foreach (var w in Resources.FindObjectsOfTypeAll<EditorWindow>().Where(w => w.GetType().Name == "BlendShape_Screenshot").ToList())
        { w.Close(); shots++; }

        var gameViewType = typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView");
        var dockedProp = typeof(EditorWindow).GetProperty("docked", Flags);
        int views = 0;
        foreach (var w in Resources.FindObjectsOfTypeAll(gameViewType).Cast<EditorWindow>())
        {
            if (dockedProp != null && (bool)dockedProp.GetValue(w)) continue;
            w.Close();
            views++;
        }

        string reopened = "";
        if (!string.IsNullOrEmpty(reopenScenePath) && !EditorApplication.isPlaying)
        {
            EditorSceneManager.OpenScene(reopenScenePath, OpenSceneMode.Single);
            reopened = $", reopened {reopenScenePath} dirty={EditorSceneManager.GetActiveScene().isDirty}";
        }
        return $"closed screenshot windows={shots}, floating game views={views}{reopened}";
    }
}
