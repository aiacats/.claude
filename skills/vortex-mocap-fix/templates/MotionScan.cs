// 一時（使い終わったら消す）。案件の Assets/_TempVerify/ へ写して使う（Play 中に MCP の invoke_method で呼ぶ）。
// 収録モーションの膝の跳ね・足の接地の揺れを、Timeline を 1/fps ずつ Evaluate して骨の位置から測るための道具。
//   ScanLegs      脚の骨（腰・太もも・すね・足・つま先）のワールドの位置・回転を float32 のバイナリに書く → scripts/leg_scan.py で集計
//   StepSegments  録画（Unity MCP の start_view_recording、clipPath なし・同じ fps）と同じ刻みで Timeline を進める。
//                 録画が始まる（Time.captureFramerate が立つ）までは区間の頭に止め、始まったら 1 コマごとに 1/fps 進める
//   SetFootIK     キャラに当たっている Animation Track のクリップの Foot IK を切り替える（アセットを書き換えるので、Play を抜けたら戻す）
//   SwapClipInPlay キャラに当たっているクリップを別のクリップに差し替える（直す前・後を同じ Play で比べる。戻すときも同じ関数）
//   MakeAnchor    両足首の中点に空の GameObject を置く（録画のカメラの注視点を世界に固定する。足に付けると足の揺れが消えて見える）
// 取り出し方（2026-10-14〜15 SinkaiFes2026 の LegProbe・FogProbe・FootContactProbe をまとめたもの）。
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

public class MotionScan : MonoBehaviour
{
    static string s_state = "idle";
    public static string State() => s_state;

    // 列の形を揃えるため、どの骨も位置（3）と回転（4）を書く
    static readonly HumanBodyBones[] Bones =
    {
        HumanBodyBones.Hips,
        HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot, HumanBodyBones.LeftToes,
        HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot, HumanBodyBones.RightToes,
    };

    static PlayableDirector Director(string name) => GameObject.Find(name)?.GetComponent<PlayableDirector>();
    static Animator Character(string path) => GameObject.Find(path)?.GetComponentInChildren<Animator>();

    /// <summary>
    /// start〜end 秒を 1/fps ずつ Evaluate し、脚の骨の位置・回転（ワールド）を binPath に書く。
    /// 1 行 = t + 骨ごとに px,py,pz,qx,qy,qz,qw（float32）。列の並びは binPath + ".json"。終わると State() が "done ..." になる。
    /// </summary>
    public static string ScanLegs(string directorName, string characterPath, float start, float end, float fps, string binPath)
    {
        // Edit モードの PlayableGraph は Humanoid の骨に書かない（骨が動かないまま「走査できた」ように見える）。コルーチンも Play 中しか回らない
        if (!Application.isPlaying) return "error: play mode only";
        if (fps <= 0f || end <= start) return "error: end > start, fps > 0";
        var d = Director(directorName);
        if (d == null) return "director not found";
        var anim = Character(characterPath);
        if (anim == null || !anim.isHuman) return "humanoid character not found";
        var missing = Bones.Where(b => anim.GetBoneTransform(b) == null).ToArray();
        if (missing.Length > 0) return "missing bones: " + string.Join(",", missing);
        s_state = "scanning";
        var host = new GameObject("_MotionScan");
        host.AddComponent<MotionScan>().StartCoroutine(Scan(host, d, anim, start, end, fps, binPath));
        return "queued";
    }

    static IEnumerator Scan(GameObject host, PlayableDirector d, Animator anim, float start, float end, float fps, string binPath)
    {
        // 1 フレームで回す数（Editor が固まらない程度。1 本約 30 秒で 1200 秒を 60fps）
        const int batch = 200;
        try
        {
            var tr = Bones.Select(anim.GetBoneTransform).ToArray();
            int n = Mathf.FloorToInt((end - start) * fps);
            Directory.CreateDirectory(Path.GetDirectoryName(binPath));
            using (var w = new BinaryWriter(File.Create(binPath)))
            {
                for (int i = 0; i < n; i++)
                {
                    double t = start + i / (double)fps;
                    d.time = t;
                    d.Evaluate();
                    w.Write((float)t);
                    foreach (var b in tr)
                    {
                        Vector3 p = b.position;
                        Quaternion q = b.rotation;
                        w.Write(p.x); w.Write(p.y); w.Write(p.z);
                        w.Write(q.x); w.Write(q.y); w.Write(q.z); w.Write(q.w);
                    }
                    if (i % batch == batch - 1) { s_state = $"scanning {i + 1}/{n}"; yield return null; }
                }
            }
            d.Pause(); // 終わった後も Director は Pause のまま（Play を抜ければ戻る）
            var cols = new StringBuilder("{\"fps\":").Append(fps).Append(",\"start\":").Append(start).Append(",\"frames\":").Append(n).Append(",\"bones\":[");
            cols.Append(string.Join(",", Bones.Select(b => "\"" + b + "\""))).Append("]}");
            File.WriteAllText(binPath + ".json", cols.ToString());
            s_state = "done " + binPath;
        }
        finally
        {
            // 例外（ファイルが開けない・キャラが消えた等）でコルーチンが止まっても、State() が scanning のまま残らないようにする
            if (!s_state.StartsWith("done", System.StringComparison.Ordinal)) s_state = "error: stopped (see the Console)";
            Destroy(host);
        }
    }

    // ---- 録画と同じ刻みで Timeline を進める ----

    static PlayableDirector s_dir;
    static double[] s_segStart;
    static int[] s_segFrames;
    static int s_fps;
    static int s_k;
    static bool s_started;
    static readonly List<string> s_log = new List<string>();
    static string s_logPath;

    /// <summary>
    /// segments は「開始秒:長さ秒;開始秒:長さ秒;...」。Director を最初の区間の頭に止め、録画が始まったら 1 コマごとに 1/fps 進め、
    /// 区間の終わりで次の区間の頭へ飛ぶ。録画の長さは区間の長さの合計にする。録画が終われば手を引き、logPath に「frameCount,k,seg,time」を書く。
    /// start_view_recording の直前に呼ぶ。区間の頭は揺れものが飛ぶので、見せたい所より前から始めて後で切る。
    /// </summary>
    public static string StepSegments(string directorName, string segments, int fps, string logPath)
    {
        var d = Director(directorName);
        if (d == null) return "director not found";
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        var segs = segments.Split(';').Select(s => s.Split(':')).ToArray();
        s_segStart = segs.Select(s => double.Parse(s[0], inv)).ToArray();
        s_segFrames = segs.Select(s => (int)System.Math.Round(double.Parse(s[1], inv) * fps)).ToArray();
        d.Pause();
        s_dir = d; s_fps = fps; s_k = 0; s_started = false; s_logPath = logPath;
        s_log.Clear();
        var go = GameObject.Find("_MotionStep") ?? new GameObject("_MotionStep");
        if (go.GetComponent<MotionScan>() == null) go.AddComponent<MotionScan>();
        d.time = s_segStart[0];
        d.Evaluate();
        return $"holding {directorName} at {s_segStart[0]:F3}; {s_segStart.Length} segments, {s_segFrames.Sum()} frames = {s_segFrames.Sum() / (double)fps:F3} s";
    }

    static (int seg, double t) At(int k)
    {
        for (int i = 0; i < s_segFrames.Length; i++)
        {
            if (k < s_segFrames[i]) return (i, s_segStart[i] + k / (double)s_fps);
            k -= s_segFrames[i];
        }
        int last = s_segFrames.Length - 1;
        return (last, s_segStart[last] + (s_segFrames[last] - 1) / (double)s_fps);
    }

    void Update()
    {
        if (s_dir == null || name != "_MotionStep") return;
        bool recording = Time.captureFramerate == s_fps;
        if (recording) s_started = true;
        else if (s_started)
        {
            File.WriteAllText(s_logPath, "frameCount,k,seg,time\n" + string.Join("\n", s_log));
            s_dir = null;
            Destroy(gameObject);
            return;
        }
        var (seg, t) = s_started ? At(s_k) : (0, s_segStart[0]);
        s_dir.time = t;
        s_dir.Evaluate();
        if (s_started)
        {
            s_log.Add($"{Time.frameCount},{s_k},{seg},{t:F4}");
            s_k++;
        }
    }

    // ---- Timeline のクリップの切り替え（Play 中だけ） ----

    static IEnumerable<AnimationPlayableAsset> ClipsOf(PlayableDirector d, Animator anim)
    {
        var timeline = d.playableAsset as TimelineAsset;
        if (timeline == null) yield break;
        foreach (var track in timeline.GetOutputTracks().OfType<AnimationTrack>())
        {
            if (d.GetGenericBinding(track) as Animator != anim) continue;
            foreach (var c in track.GetClips())
                if (c.asset is AnimationPlayableAsset a) yield return a;
        }
    }

    static void Rebuild(PlayableDirector d)
    {
        double t = d.time;
        d.RebuildGraph();
        d.time = t;
        d.Evaluate();
    }

    /// <summary>キャラのクリップの Foot IK を切り替える。AnimationPlayableAsset（Timeline のアセット）を書き換えるので、Play を抜けても残る。比べ終えたら元の値に戻す。</summary>
    public static string SetFootIK(string directorName, string characterPath, bool on)
    {
        var d = Director(directorName);
        var anim = Character(characterPath);
        if (d == null || anim == null) return "not found";
        var sb = new StringBuilder();
        foreach (var a in ClipsOf(d, anim)) { sb.Append($"{(a.clip != null ? a.clip.name : "null")}: footIK {a.applyFootIK} -> {on}; "); a.applyFootIK = on; }
        Rebuild(d);
        d.Pause();
        return sb.Length > 0 ? sb.ToString() : "no clip bound to the character";
    }

#if UNITY_EDITOR
    /// <summary>Play 中だけ: キャラに当たっているクリップを clipPath（.anim か FBX。FBX なら中のクリップ）に差し替え、グラフを作り直す
    /// （戻すときも同じ関数で元のパス）。Timeline のアセットの参照を書き換えるので、Play を抜ける前に必ず元に戻す。</summary>
    public static string SwapClipInPlay(string directorName, string characterPath, string clipPath)
    {
        if (!Application.isPlaying) return "play mode only";
        var clip = UnityEditor.AssetDatabase.LoadAllAssetsAtPath(clipPath).OfType<AnimationClip>()
            .FirstOrDefault(x => !x.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        var d = Director(directorName);
        var anim = Character(characterPath);
        if (d == null || anim == null || clip == null) return $"not found (director {d != null}, animator {anim != null}, clip {clip != null})";
        var sb = new StringBuilder();
        foreach (var a in ClipsOf(d, anim)) { sb.Append($"{(a.clip != null ? a.clip.name : "null")} -> {clip.name} (footIK {a.applyFootIK}); "); a.clip = clip; }
        Rebuild(d);
        return sb.Length > 0 ? sb.ToString() : "no clip bound to the character";
    }
#endif

    /// <summary>Play 中だけ: 今の両足首の中点（高さは up m 足す）に空の GameObject を置く。</summary>
    public static string MakeAnchor(string characterPath, string name, float up)
    {
        if (!Application.isPlaying) return "play mode only";
        var anim = Character(characterPath);
        if (anim == null) return "animator not found";
        var p = (anim.GetBoneTransform(HumanBodyBones.LeftFoot).position + anim.GetBoneTransform(HumanBodyBones.RightFoot).position) * 0.5f;
        p.y += up;
        var go = GameObject.Find(name) ?? new GameObject(name);
        go.transform.position = p;
        return $"{name} at {p.x:F3},{p.y:F3},{p.z:F3}";
    }
}
