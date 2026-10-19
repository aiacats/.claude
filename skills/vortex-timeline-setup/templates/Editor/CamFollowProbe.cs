// 雛形（skill vortex-timeline-setup）。案件の Assets/_TempVerify/Editor/ へ写して使い、終わったら消す。
// カメラ記録の再生で、番組に出ているカメラがキャラをどう追っているかを調べる。呼び方は MCP の invoke_method（typeName CamFollowProbe）。
//   Measure            Play 中に Timeline を 1/fps ずつ Evaluate し、番組カメラ A/B の位置・向き・画角と、キャラの頭・腰を CSV へ（scripts/camfollow.py が読む）
//   SetRotationOverride 1 台のカメラの区間だけ向きをずらす Override Track を置き直す（記録の向きが止まっている所の直し）。Edit モードで呼び、シーンを保存する
//   SwapRecordData     Timeline のクリップの記録データ（_recordData）を別のアセットへ付け替える（表情・カメラの複製へ差し替え）
//   DumpLookat         スイッチャーの各カメラの注視先の番号・種類と、注視の減衰（Aim Damping）
// 画を撮るのは ShotRunner（時刻を動かした直後に Render すると、キャラだけ前の時刻のポーズで写る）。
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Playables;
using vortex;

public static class CamFollowProbe
{
    /// <summary>終わった後も Director は Pause のまま（Play を抜ければ戻る）。characterPath は GameObject のパスか "#n"（n 番目のミュートでない Animation Track のバインド先）。</summary>
    public static string Measure(string directorName, string characterPath, float t0, float t1, float fps, string outCsv)
    {
        // Play 中だけ（Edit モードの PlayableGraph は Humanoid の骨に書かないので、頭・腰が動かないまま CSV ができてしまう）
        if (!Application.isPlaying) return "error: play mode only";
        if (fps <= 0f || t1 <= t0) return "error: t1 > t0, fps > 0";
        var dirGo = GameObject.Find(directorName);
        if (dirGo == null || !dirGo.TryGetComponent<PlayableDirector>(out var director)) return "error: director not found";
        director.Pause(); // 自走を止めて、こちらで時刻を進める
        var switcher = Object.FindAnyObjectByType<VirtualCameraSwitcher>();
        if (switcher == null) return "error: no active VirtualCameraSwitcher (the camera system is disabled?)";
        Animator anim = null;
        if (characterPath.StartsWith("#", System.StringComparison.Ordinal))
        {
            // "#n": Timeline の n 番目の Animation Track のバインド先
            int want = int.Parse(characterPath.Substring(1)), k = 0;
            foreach (var o in director.playableAsset.outputs)
                if (o.sourceObject is UnityEngine.Timeline.AnimationTrack tr && !tr.muted && k++ == want)
                    anim = director.GetGenericBinding(tr) as Animator;
        }
        else
        {
            var chGo = GameObject.Find(characterPath);
            if (chGo != null) anim = chGo.GetComponentInChildren<Animator>();
        }
        if (anim == null) return "character not found";
        var head = anim.GetBoneTransform(HumanBodyBones.Head);
        var hips = anim.GetBoneTransform(HumanBodyBones.Hips);
        var ci = CultureInfo.InvariantCulture;
        var sb = new StringBuilder("t,fade,pgm,prv,ax,ay,az,aqx,aqy,aqz,aqw,afov,bx,by,bz,bqx,bqy,bqz,bqw,bfov,hx,hy,hz,px,py,pz\n");
        int n = Mathf.RoundToInt((t1 - t0) * fps);
        var sw = System.Diagnostics.Stopwatch.StartNew();
        for (int i = 0; i <= n; i++)
        {
            double t = t0 + i / (double)fps;
            director.time = t;
            director.Evaluate();
            CameraRecordPlaybackState.TryGet(switcher, out var frame);
            var a = switcher._activeCamera.OutputCamera;
            var b = switcher._reserveCamera.OutputCamera;
            sb.Append(string.Format(ci, "{0:F4},{1:F4},{2},{3},", t, VirtualCameraSwitcher.FadeAlpha,
                frame != null && frame.Pgm.hasValue ? frame.Pgm.cameraIndex : -1,
                frame != null && frame.Prv.hasValue ? frame.Prv.cameraIndex : -1));
            AppendCam(sb, a, ci);
            AppendCam(sb, b, ci);
            sb.Append(string.Format(ci, "{0:F5},{1:F5},{2:F5},{3:F5},{4:F5},{5:F5}\n",
                head.position.x, head.position.y, head.position.z, hips.position.x, hips.position.y, hips.position.z));
        }
        File.WriteAllText(outCsv, sb.ToString());
        return $"{n + 1} rows, {sw.Elapsed.TotalSeconds:F1}s -> {outCsv}";
    }

    /// <summary>
    /// Camera グループに、1 台のカメラの区間だけ向きをずらす Override Track を置き直す（同名のトラックがあれば中身を作り直す）。
    /// spans: "開始:終了:yaw:pitch" をセミコロン区切り（秒・度、カメラのローカル）。Edit モードで呼び、終わったらシーンを保存する
    /// （トラックのバインドはシーンにあるので、保存しないと効かない。コミットは skill unity-scene-merge）。
    /// 同じカメラの Override が他のトラックにあると、重なる区間ではこのトラックの値だけが効く（ミキサーは「記録値 + 自分のトラックのオフセット」で上書きする）。
    /// そのため、重なる他のトラックのクリップの Rail・FoV をこのクリップにも入れる。位置・回転のオフセットを持つ物と重なるなら断る。
    /// </summary>
    public static string SetRotationOverride(string timelinePath, int index, string spans)
    {
        if (Application.isPlaying) return "error: edit mode only (a binding made in play mode is lost when play mode ends)";
        var ci = CultureInfo.InvariantCulture;
        float[][] parsed;
        try { parsed = spans.Split(';').Where(x => x.Length > 0).Select(s => s.Split(':').Select(x => float.Parse(x, ci)).ToArray()).ToArray(); }
        catch (System.FormatException) { return "error: spans must be start:end:yaw:pitch;..."; }
        if (parsed.Length == 0 || parsed.Any(f => f.Length != 4 || f[1] <= f[0])) return "error: spans must be start:end:yaw:pitch;... with end > start";
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        if (tl == null) return "error: timeline not found";
        var group = tl.GetRootTracks().OfType<UnityEngine.Timeline.GroupTrack>().FirstOrDefault(g => g.name == "Camera");
        if (group == null) return "error: no Camera group";
        var director = Object.FindObjectsByType<PlayableDirector>(FindObjectsInactive.Include, FindObjectsSortMode.None).FirstOrDefault(d => d.playableAsset == tl);
        if (director == null) return "error: no director plays this timeline in the open scenes";
        var switcher = Object.FindAnyObjectByType<VirtualCameraSwitcher>(FindObjectsInactive.Include);
        if (switcher == null || index < 0 || index >= switcher._inputCameras.Count) return "error: switcher or camera index not found";
        string trackName = $"Override Cam{index:00} {switcher._inputCameras[index].name} (aim)";
        var track = tl.GetOutputTracks().OfType<CameraRecordOverrideTrack>().FirstOrDefault(t => t.name == trackName);
        var others = tl.GetOutputTracks().OfType<CameraRecordOverrideTrack>().Where(t => t != track)
            .SelectMany(t => t.GetClips().Select(c => (track: t, clip: c)))
            .Where(x => x.clip.asset is CameraRecordOverrideClip o && o.offset.targetCameraIndex == index).ToList();
        var carry = new (float rail, float fov)[parsed.Length];
        for (int k = 0; k < parsed.Length; k++)
        {
            var f = parsed[k];
            var over = others.Where(x => x.clip.start < f[1] && x.clip.end > f[0]).ToList();
            if (over.Count > 1) return $"error: {f[0]:F2}-{f[1]:F2} overlaps {over.Count} override clips of camera {index}; merge them by hand";
            if (over.Count == 1)
            {
                var o = ((CameraRecordOverrideClip)over[0].clip.asset).offset;
                if (o.positionOffset != Vector3.zero || o.rotationOffset != Vector3.zero)
                    return $"error: {over[0].track.name} has position/rotation offsets; merge them by hand";
                if (over[0].clip.start > f[0] || over[0].clip.end < f[1])
                    return $"error: {over[0].track.name} covers only part of {f[0]:F2}-{f[1]:F2}; split the span";
                carry[k] = (o.railOffset, o.fovOffset);
            }
        }
        if (track == null) track = tl.CreateTrack<CameraRecordOverrideTrack>(group, trackName);
        foreach (var c in track.GetClips().ToList()) tl.DeleteClip(c);
        var log = new StringBuilder(trackName + ": ");
        for (int k = 0; k < parsed.Length; k++)
        {
            var f = parsed[k];
            var clip = track.CreateClip<CameraRecordOverrideClip>();
            clip.start = f[0];
            clip.duration = f[1] - f[0];
            clip.displayName = string.Format(ci, "aim yaw {0:+0.0;-0.0;0} pitch {1:+0.0;-0.0;0}", f[2], f[3]);
            var a = (CameraRecordOverrideClip)clip.asset;
            a.offset.targetCameraIndex = index;
            a.offset.space = CameraRecordOffsetSpace.CameraLocal;
            a.offset.rotationOffset = new Vector3(f[3], f[2], 0f);
            a.offset.positionOffset = Vector3.zero;
            a.offset.railOffset = carry[k].rail;
            a.offset.fovOffset = carry[k].fov;
            EditorUtility.SetDirty(a);
            log.Append($"{f[0]:F2}-{f[1]:F2} yaw {f[2]:+0.0;-0.0} pitch {f[3]:+0.0;-0.0}");
            if (carry[k].rail != 0f || carry[k].fov != 0f) log.Append($" (carried rail {carry[k].rail:+0.00;-0.00} fov {carry[k].fov:+0.00;-0.00})");
            log.Append("; ");
        }
        director.SetGenericBinding(track, switcher);
        EditorUtility.SetDirty(track);
        EditorUtility.SetDirty(tl);
        AssetDatabase.SaveAssetIfDirty(tl); // SaveAssets は関係ない dirty なアセット（実行時に触ったマテリアル等）まで保存する
        EditorSceneManager.MarkSceneDirty(director.gameObject.scene);
        return log + "-> save the scene to keep the binding";
    }

    /// <summary>Timeline の全クリップのうち、_recordData が oldPath のアセットを指すものを newPath へ付け替える。</summary>
    public static string SwapRecordData(string timelinePath, string oldPath, string newPath)
    {
        AssetDatabase.ImportAsset(newPath);
        var oldA = AssetDatabase.LoadMainAssetAtPath(oldPath);
        var newA = AssetDatabase.LoadMainAssetAtPath(newPath);
        if (oldA == null || newA == null || oldA.GetType() != newA.GetType()) return $"load failed (old {oldA}, new {newA})";
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        var sb = new StringBuilder();
        foreach (var track in tl.GetOutputTracks())
            foreach (var clip in track.GetClips())
            {
                if (clip.asset == null) continue;
                var so = new SerializedObject(clip.asset);
                var p = so.FindProperty("_recordData");
                if (p == null || p.objectReferenceValue != oldA) continue;
                p.objectReferenceValue = newA;
                so.ApplyModifiedPropertiesWithoutUndo();
                sb.Append($"{track.name}/{clip.displayName}; ");
            }
        if (sb.Length == 0) return "no clip referenced " + oldPath;
        EditorUtility.SetDirty(tl);
        AssetDatabase.SaveAssetIfDirty(tl);
        if (Application.isPlaying)
        {
            // Play 中は動いているグラフがクリップの参照を持ったままなので、作り直して新しい記録を読ませる
            foreach (var d in Object.FindObjectsByType<PlayableDirector>(FindObjectsInactive.Include, FindObjectsSortMode.None).Where(x => x.playableAsset == tl))
            {
                double t = d.time;
                bool playing = d.state == PlayState.Playing;
                d.RebuildGraph();
                d.time = t;
                if (playing) d.Play(); else d.Evaluate();
            }
        }
        return "swapped: " + sb;
    }

    /// <summary>スイッチャーの各カメラの、注視先の設定（生成器ごとの lookatIndex と種類）と注視の減衰を一覧する。</summary>
    public static string DumpLookat()
    {
        var switcher = Object.FindAnyObjectByType<VirtualCameraSwitcher>(FindObjectsInactive.Include);
        var sb = new StringBuilder();
        for (int i = 0; i < switcher._inputCameras.Count; i++)
        {
            var c = switcher._inputCameras[i];
            sb.Append($"{i:00} {c.name} aimType {c._cineBodyAndAim._aimType} body {c._cineBodyAndAim._bodyType} damp {c._cineBodyAndAim._aimDamping} | ");
            foreach (var g in c._vCams) sb.Append(g == null ? "null; " : $"{g.name}: idx {g._lookatIndex} {g._targetType}; ");
            sb.Append('\n');
        }
        return sb.ToString();
    }

    /// <summary>Timeline のアセット（トラック・クリップを含む）を dirty にして保存する。</summary>
    public static string SaveTimeline(string timelinePath)
    {
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        if (tl == null) return "not found";
        EditorUtility.SetDirty(tl);
        foreach (var o in AssetDatabase.LoadAllAssetsAtPath(timelinePath)) if (o != null) EditorUtility.SetDirty(o);
        AssetDatabase.SaveAssetIfDirty(tl);
        return "saved " + timelinePath;
    }

    static void AppendCam(StringBuilder sb, Camera c, CultureInfo ci)
    {
        var p = c.transform.position; var q = c.transform.rotation;
        sb.Append(string.Format(ci, "{0:F5},{1:F5},{2:F5},{3:F6},{4:F6},{5:F6},{6:F6},{7:F3},",
            p.x, p.y, p.z, q.x, q.y, q.z, q.w, c.fieldOfView));
    }
}
