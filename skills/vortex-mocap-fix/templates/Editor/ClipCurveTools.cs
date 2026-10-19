// 一時（使い終わったら消す）。案件の Assets/_TempVerify/Editor/ へ写して使う（MCP の invoke_method で呼ぶ）。BodyRestFix がこれに依存する。
// Humanoid のクリップ（.anim か FBX の中のクリップ）のカーブを読む・比べる・間引く・Timeline のクリップを差し替える道具。
// 2026-10-14〜15 SinkaiFes2026 の ClipMuscleDump・FootContactProbe をまとめたもの。
// 間引いた .anim を作るときは BodyRestFix.ExtractClip / RebuildCurves を使う（Root と足の目標を細かい許容で間引く。マッスルと同じ許容だと足がガタつく）。
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class ClipCurveTools
{
    public static AnimationClip Load(string path)
    {
        if (AssetDatabase.LoadMainAssetAtPath(path) is AnimationClip c) return c;
        return AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>()
            .FirstOrDefault(x => !x.name.StartsWith("__preview__", System.StringComparison.Ordinal));
    }

    static AnimationCurve Curve(AnimationClip c, string n) => AnimationUtility.GetEditorCurve(c, EditorCurveBinding.FloatCurve("", typeof(Animator), n));

    /// <summary>
    /// マッスルの最大・最小と、上限 1 を超えている時間の割合（1/fps ごと）。names は「;」区切り（既定は膝 2 本）。
    /// 膝（Lower Leg Stretch）が 1 を超えると FK の膝が反り、Foot IK On でときどき反った側へ跳ねる。まずこれを読む。
    /// </summary>
    public static string MuscleStats(string clipPath, string names, float fps)
    {
        var clip = Load(clipPath);
        if (clip == null) return "no clip at " + clipPath;
        if (string.IsNullOrEmpty(names)) names = "Left Lower Leg Stretch;Right Lower Leg Stretch";
        var sb = new StringBuilder($"{clip.name} {clip.length:F1}s\n");
        int frames = Mathf.FloorToInt(clip.length * fps);
        foreach (var n in names.Split(';'))
        {
            var c = Curve(clip, n);
            if (c == null) { sb.Append($"{n}: missing\n"); continue; }
            float mx = float.MinValue, mn = float.MaxValue; int over = 0;
            for (int i = 0; i < frames; i++)
            {
                float v = c.Evaluate(i / fps);
                mx = Mathf.Max(mx, v); mn = Mathf.Min(mn, v);
                if (v > 1f) over++;
            }
            sb.Append($"{n}: max {mx:F3} min {mn:F3} over 1 for {100f * over / Mathf.Max(1, frames):F1}% (keys {c.length})\n");
        }
        return sb.ToString();
    }

    /// <summary>musclesCsv は「;」区切りのカーブ名（例: "Left Lower Leg Stretch;RootT.x"）。空なら名前一覧だけ返す。1/fps ごとに CSV へ書く。</summary>
    public static string Dump(string clipPath, string musclesCsv, float fps, string csvPath)
    {
        var clip = Load(clipPath);
        if (clip == null) return "no clip at " + clipPath;
        var bindings = AnimationUtility.GetCurveBindings(clip);
        if (string.IsNullOrEmpty(musclesCsv))
            return $"{clip.name} length {clip.length:F2}s, {bindings.Length} curves: " + string.Join(", ", bindings.Select(b => b.propertyName).Where(n => !n.Contains("Root")).Take(120));
        var names = musclesCsv.Split(';');
        var curves = names.Select(n => Curve(clip, n)).ToArray();
        var miss = names.Where((n, i) => curves[i] == null).ToArray();
        if (miss.Length > 0) return "missing curves: " + string.Join(", ", miss);
        int frames = Mathf.FloorToInt(clip.length * fps);
        var sb = new StringBuilder("t," + string.Join(",", names.Select(n => n.Replace(' ', '_'))) + "\n");
        for (int i = 0; i < frames; i++)
        {
            float t = i / fps;
            sb.Append(t.ToString("F4"));
            foreach (var c in curves) sb.Append(',').Append(c.Evaluate(t).ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            sb.Append('\n');
        }
        File.WriteAllText(csvPath, sb.ToString());
        return $"{clip.name} {frames} frames -> {csvPath}; keys " + string.Join(" ", curves.Select(c => c.length));
    }

    /// <summary>2 本のクリップで共通の Animator のカーブを 1/fps ごとに比べ、カーブごとの a−b を CSV に書く。filter（「;」区切り）を含む名前だけに絞れる。</summary>
    public static string DiffScan(string clipA, string clipB, string filter, float fps, string csvPath)
    {
        var a = Load(clipA); var b = Load(clipB);
        if (a == null || b == null) return "no clip";
        var fs = string.IsNullOrEmpty(filter) ? null : filter.Split(';');
        var names = AnimationUtility.GetCurveBindings(a).Where(x => x.type == typeof(Animator) && x.path == "")
            .Select(x => x.propertyName)
            .Where(n => fs == null || fs.Any(f => n.Contains(f)))
            .Intersect(AnimationUtility.GetCurveBindings(b).Where(x => x.type == typeof(Animator) && x.path == "").Select(x => x.propertyName))
            .OrderBy(n => n, System.StringComparer.Ordinal).ToArray();
        var ca = names.Select(n => Curve(a, n)).ToArray();
        var cb = names.Select(n => Curve(b, n)).ToArray();
        int frames = Mathf.FloorToInt(Mathf.Min(a.length, b.length) * fps);
        var sb = new StringBuilder("t," + string.Join(",", names.Select(n => n.Replace(' ', '_').Replace(',', '_'))) + "\n");
        for (int i = 0; i < frames; i++)
        {
            float t = i / fps;
            sb.Append(t.ToString("F4"));
            for (int k = 0; k < names.Length; k++) sb.Append(',').Append((ca[k].Evaluate(t) - cb[k].Evaluate(t)).ToString("F4"));
            sb.Append('\n');
        }
        File.WriteAllText(csvPath, sb.ToString());
        return $"{names.Length} curves, {frames} frames -> {csvPath}";
    }

    /// <summary>
    /// 足の IK の目標（RootT + RootQ × FootT、Humanoid の正規化した長さ）と RootT を 1/fps ごとに CSV へ書く。
    /// 列: t, 左の目標 x,y,z と向き x,y,z,w, 右も同じ, RootT x,y,z。Foot IK On のとき舞台の足はこの目標に置かれる → scripts/goal_jitter.py で接地中の揺れを数える。
    /// </summary>
    public static string GoalCsv(string clipPath, float fps, string csvPath)
    {
        var clip = Load(clipPath);
        if (clip == null) return "no clip at " + clipPath;
        string[] names =
        {
            "RootT.x", "RootT.y", "RootT.z", "RootQ.x", "RootQ.y", "RootQ.z", "RootQ.w",
            "LeftFootT.x", "LeftFootT.y", "LeftFootT.z", "LeftFootQ.x", "LeftFootQ.y", "LeftFootQ.z", "LeftFootQ.w",
            "RightFootT.x", "RightFootT.y", "RightFootT.z", "RightFootQ.x", "RightFootQ.y", "RightFootQ.z", "RightFootQ.w",
        };
        var cv = names.Select(n => Curve(clip, n)).ToArray();
        var miss = names.Where((n, i) => cv[i] == null).ToArray();
        if (miss.Length > 0) return "missing curves: " + string.Join(", ", miss);
        int frames = Mathf.FloorToInt(clip.length * fps);
        var sb = new StringBuilder("t,lx,ly,lz,lqx,lqy,lqz,lqw,rx,ry,rz,rqx,rqy,rqz,rqw,rootx,rooty,rootz\n");
        float[] v = new float[names.Length];
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        for (int i = 0; i < frames; i++)
        {
            float t = i / fps;
            for (int k = 0; k < cv.Length; k++) v[k] = cv[k].Evaluate(t);
            var rt = new Vector3(v[0], v[1], v[2]);
            var rq = new Quaternion(v[3], v[4], v[5], v[6]).normalized;
            var lg = rt + rq * new Vector3(v[7], v[8], v[9]);
            var rg = rt + rq * new Vector3(v[14], v[15], v[16]);
            var lq = rq * new Quaternion(v[10], v[11], v[12], v[13]).normalized;
            var rqq = rq * new Quaternion(v[17], v[18], v[19], v[20]).normalized;
            sb.Append(t.ToString("F5", inv));
            foreach (var f in new[] { lg.x, lg.y, lg.z, lq.x, lq.y, lq.z, lq.w, rg.x, rg.y, rg.z, rqq.x, rqq.y, rqq.z, rqq.w, rt.x, rt.y, rt.z })
                sb.Append(',').Append(f.ToString("F6", inv));
            sb.Append('\n');
        }
        File.WriteAllText(csvPath, sb.ToString());
        return $"{clip.name} len {clip.length:F2}s fr {clip.frameRate} -> {frames} rows; keys " + string.Join(" ", names.Select((n, i) => $"{n}={cv[i].length}"));
    }

    /// <summary>FBX のアニメーションの圧縮を変えて取り込み直す（0 = Off、1 = Keyframe Reduction、2 = Optimal）。長い FBX は数十分かかる。前の値を返す。
    /// .meta を変えるので、確かめ終えたら元の値へ戻すか、git checkout で .meta を戻す（Library のキャッシュで戻りは速い）。</summary>
    public static string SetCompression(string fbxPath, int mode)
    {
        var mi = (ModelImporter)AssetImporter.GetAtPath(fbxPath);
        var before = mi.animationCompression;
        mi.animationCompression = (ModelImporterAnimationCompression)mode;
        var sw = System.Diagnostics.Stopwatch.StartNew();
        mi.SaveAndReimport();
        return $"{fbxPath}: {before} -> {mi.animationCompression} ({sw.Elapsed.TotalSeconds:F0}s)";
    }

    /// <summary>キーを、残したキー同士を直線で結んだときに落としたキーの値が eps 以内に収まる範囲で間引く（キー数に比例する手間）。
    /// 「キーが毎フレームある」前提。圧縮して取り込んだ（キーがまばらで、間の形を接線で持つ）カーブに掛けると形が崩れる。</summary>
    public static AnimationCurve ReduceLinear(AnimationCurve curve, float eps)
    {
        var k = curve.keys;
        if (k.Length <= 2) return curve;
        var keep = new System.Collections.Generic.List<int> { 0 };
        // 起点から引く直線の傾きが、間のキーすべてを eps 以内に通す範囲 [lo, hi] を 1 キーずつ狭める。
        // 次のキーへの傾きがその範囲を外れたら、直前のキーを残して新しい起点にする（素朴に全区間を見直すと一定値のカーブで O(n^2) になり Unity が 20 分止まった）
        int anchor = 0;
        double lo = double.NegativeInfinity, hi = double.PositiveInfinity;
        for (int i = anchor + 1; i < k.Length; i++)
        {
            double dt = k[i].time - k[anchor].time, dv = k[i].value - k[anchor].value;
            double s = dv / dt;
            if (i > anchor + 1 && (s < lo || s > hi))
            {
                keep.Add(i - 1);
                anchor = i - 1;
                lo = double.NegativeInfinity; hi = double.PositiveInfinity;
                dt = k[i].time - k[anchor].time; dv = k[i].value - k[anchor].value;
            }
            lo = System.Math.Max(lo, (dv - eps) / dt);
            hi = System.Math.Min(hi, (dv + eps) / dt);
        }
        keep.Add(k.Length - 1);
        var outKeys = new Keyframe[keep.Count];
        for (int n = 0; n < keep.Count; n++)
        {
            var src = k[keep[n]];
            float inT = n > 0 ? (src.value - k[keep[n - 1]].value) / (src.time - k[keep[n - 1]].time) : 0f;
            float outT = n < keep.Count - 1 ? (k[keep[n + 1]].value - src.value) / (k[keep[n + 1]].time - src.time) : 0f;
            if (n == 0) inT = outT;
            if (n == keep.Count - 1) outT = inT;
            outKeys[n] = new Keyframe(src.time, src.value, inT, outT);
        }
        var res = new AnimationCurve(outKeys) { preWrapMode = curve.preWrapMode, postWrapMode = curve.postWrapMode };
        for (int n = 0; n < res.length; n++)
        {
            AnimationUtility.SetKeyBroken(res, n, true);
            AnimationUtility.SetKeyLeftTangentMode(res, n, AnimationUtility.TangentMode.Free);
            AnimationUtility.SetKeyRightTangentMode(res, n, AnimationUtility.TangentMode.Free);
        }
        res.keys = outKeys;
        return res;
    }

    /// <summary>Timeline の中で、oldClipPath のクリップを再生しているアニメーションクリップを newClipPath に差し替える（Foot IK などクリップの設定はそのまま）。
    /// .playable の差分は m_Clip（と内部名）だけになる。</summary>
    public static string SwapTimelineClip(string timelinePath, string oldClipPath, string newClipPath)
    {
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        var oldClip = Load(oldClipPath); var newClip = Load(newClipPath);
        if (tl == null || oldClip == null || newClip == null) return "missing asset";
        var sb = new StringBuilder();
        foreach (var track in tl.GetOutputTracks().OfType<UnityEngine.Timeline.AnimationTrack>())
            foreach (var c in track.GetClips())
                if (c.asset is UnityEngine.Timeline.AnimationPlayableAsset a && a.clip == oldClip)
                {
                    Undo.RecordObject(a, "Swap clip");
                    a.clip = newClip;
                    EditorUtility.SetDirty(a);
                    sb.Append($"{track.name}/{c.displayName}: {oldClip.name} -> {newClip.name} (footIK {a.applyFootIK}, start {c.start:F2}, duration {c.duration:F2}, clip length {newClip.length:F2})\n");
                }
        EditorUtility.SetDirty(tl);
        AssetDatabase.SaveAssets();
        return sb.Length == 0 ? "no clip using " + oldClip.name : sb.ToString();
    }

    /// <summary>Timeline の中で clipPath のクリップを再生しているアニメーションクリップの Foot IK を設定して保存する。</summary>
    public static string SetFootIK(string timelinePath, string clipPath, bool on)
    {
        var tl = AssetDatabase.LoadAssetAtPath<UnityEngine.Timeline.TimelineAsset>(timelinePath);
        var clip = Load(clipPath);
        if (tl == null || clip == null) return "missing asset";
        var sb = new StringBuilder();
        foreach (var track in tl.GetOutputTracks().OfType<UnityEngine.Timeline.AnimationTrack>())
            foreach (var c in track.GetClips())
                if (c.asset is UnityEngine.Timeline.AnimationPlayableAsset a && a.clip == clip)
                {
                    Undo.RecordObject(a, "Foot IK");
                    a.applyFootIK = on;
                    EditorUtility.SetDirty(a);
                    sb.Append($"{track.name}/{c.displayName}: footIK {a.applyFootIK}\n");
                }
        EditorUtility.SetDirty(tl);
        AssetDatabase.SaveAssets();
        return sb.Length == 0 ? "no clip" : sb.ToString();
    }

    /// <summary>FBX の Humanoid の対応で、骨の名前の接頭辞 from を to へ付け替える（2 人分の骨格が入った FBX で、自動の対応が別の人を拾ったとき）。
    /// apply=false なら付け替え先の骨がモデルにあるかだけ数える。取り込み直しは圧縮 Off で、次の Editor の更新で始めてすぐ返す（数十分かかる）。</summary>
    public static string RemapHuman(string fbxPath, string from, string to, bool apply)
    {
        var imp = (ModelImporter)AssetImporter.GetAtPath(fbxPath);
        var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
        var names = new System.Collections.Generic.HashSet<string>(model.GetComponentsInChildren<Transform>(true).Select(t => t.name));
        var avatar = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<Avatar>().FirstOrDefault();
        var hd = avatar != null ? avatar.humanDescription : imp.humanDescription;
        var human = hd.human.ToArray();
        int ok = 0;
        var missing = new System.Collections.Generic.List<string>();
        for (int i = 0; i < human.Length; i++)
        {
            var n = human[i].boneName.Replace(from, to);
            if (names.Contains(n)) { human[i].boneName = n; ok++; }
            else missing.Add(human[i].humanName + "=" + n);
        }
        if (!apply || missing.Count > 0)
            return $"{ok}/{human.Length} found; missing: {string.Join(", ", missing)}; sample {string.Join(", ", human.Take(3).Select(h => h.humanName + "=" + h.boneName))}";
        hd.human = human;
        imp.animationType = ModelImporterAnimationType.Human;
        imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
        imp.humanDescription = hd;
        // キーフレーム削減の job で Unity が落ちた前例（Else の FBX）があり、間引きも後で自前で行うので Off で取り込む
        imp.animationCompression = ModelImporterAnimationCompression.Off;
        EditorApplication.delayCall += () =>
        {
            var sw = System.Diagnostics.Stopwatch.StartNew();
            imp.SaveAndReimport();
            Debug.Log($"[RemapHuman] reimported {fbxPath} in {sw.Elapsed.TotalSeconds:F0}s; {AvatarInfo(fbxPath)}");
        };
        EditorApplication.QueuePlayerLoopUpdate();
        return "reimport scheduled";
    }

    public static string AvatarInfo(string fbxPath)
    {
        var av = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<Avatar>().FirstOrDefault();
        if (av == null) return "no avatar";
        return $"avatar valid {av.isValid} human {av.isHuman}; hips = {av.humanDescription.human.FirstOrDefault(h => h.humanName == "Hips").boneName}";
    }

    /// <summary>パスに filter を含む Transform のカーブ（Humanoid の対応外の骨）について、キー数と値の幅を返す。動きがどの骨格に入っているかを調べる。</summary>
    public static string TransformCurves(string clipPath, string filter)
    {
        var clip = Load(clipPath);
        if (clip == null) return "no clip at " + clipPath;
        var sb = new StringBuilder();
        foreach (var b in AnimationUtility.GetCurveBindings(clip).Where(b => b.type == typeof(Transform) && b.path.Contains(filter)))
        {
            var c = AnimationUtility.GetEditorCurve(clip, b);
            float lo = c.keys.Min(k => k.value), hi = c.keys.Max(k => k.value);
            sb.Append($"{b.path.Substring(b.path.LastIndexOf('/') + 1)}.{b.propertyName} keys {c.length} range {lo:F3}..{hi:F3}\n");
        }
        return sb.Length == 0 ? "no transform curves matching " + filter : sb.ToString();
    }
}
