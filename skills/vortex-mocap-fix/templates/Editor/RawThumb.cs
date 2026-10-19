// 検証用（BodyRestFix と一緒に使う）。Generic で取り込んだ収録 FBX の生の骨で、親指の向き（BodyRestFix.Thumb と同じ測り方）を時刻ごとに CSV へ書く。
// Humanoid の Avatar を通すと指の自由度の分だけ丸められ、Avatar の基準の姿勢によって 2〜3° 動くので、合わせ込みの物差しを生の骨で確かめるため。
// 使い方: 収録 FBX を _TempVerify へ写し、.meta を別の GUID・animationType 2（Generic）にして（FBX より先に）置く → これを _TempVerify/Editor/ へ写して
// Series(写した FBX, "Azuki_LeftHand", 0.25, csv) → ThumbSeries のキャラの CSV と比べる。終わったら写しを消す。
// ここ（~/.claude/skills/vortex-mocap-fix/templates/Editor）は Unity プロジェクトの外の写し元（trap-ok:cs-runtime-unityeditor）。
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class RawThumb
{
    /// <summary>fbxPath（Generic）を置いてクリップを step 秒ごとに当て、prefix（例 "Azuki_LeftHand"）の手の親指の spread・out を csvPath に書く。</summary>
    public static string Series(string fbxPath, string prefix, float step, string csvPath)
    {
        var clip = AssetDatabase.LoadAllAssetsAtPath(fbxPath).OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview__", System.StringComparison.Ordinal));
        var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
        if (clip == null || model == null) return $"missing (clip {clip != null}, model {model != null})";
        var go = Object.Instantiate(model);
        try
        {
            var all = go.GetComponentsInChildren<Transform>(true).GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
            Transform B(string n) => all.TryGetValue(n, out var t) ? t : null;
            var hand = B(prefix); var mid = B(prefix + "Middle1"); var idx = B(prefix + "Index1"); var lit = B(prefix + "Pinky1");
            var t0 = B(prefix + "Thumb1"); var t2 = B(prefix + "Thumb3");
            if (new[] { hand, mid, idx, lit, t0, t2 }.Any(x => x == null)) return "bone not found";
            var sb = new StringBuilder("t,spread,out\n");
            int n = Mathf.FloorToInt(clip.length / step);
            for (int i = 0; i < n; i++)
            {
                float t = i * step;
                clip.SampleAnimation(go, t);
                var fwd = (mid.position - hand.position).normalized;
                var across = Vector3.ProjectOnPlane(idx.position - lit.position, fwd).normalized;
                var normal = Vector3.Cross(fwd, across);
                var th = (t2.position - t0.position).normalized;
                float spread = Mathf.Atan2(Vector3.Dot(th, across), Vector3.Dot(th, fwd)) * Mathf.Rad2Deg;
                float outOfPlane = Mathf.Asin(Mathf.Clamp(Vector3.Dot(th, normal), -1f, 1f)) * Mathf.Rad2Deg;
                sb.Append($"{t:F3},{spread:F2},{outOfPlane:F2}\n");
            }
            System.IO.File.WriteAllText(csvPath, sb.ToString());
            return $"{n} rows ({clip.name}, {clip.length:F1}s, legacy {clip.legacy}, humanMotion {clip.humanMotion})";
        }
        finally { Object.DestroyImmediate(go); }
    }
}
