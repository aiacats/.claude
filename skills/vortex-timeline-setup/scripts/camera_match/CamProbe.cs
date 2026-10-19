// 一時検証用（終わったら消す）。Timeline の指定時刻で、番組に出ているカメラ（PGM/PRV のうち fade で選ばれている側）を、
// 記録どおりの位置と、レールに沿ってずらした位置（railOffset の候補）で撮って PNG に書き出す。
// ずらす計算は CameraRecordOverrideTrack と同じ CameraRecordRailOffset.TryApply を使う。
using System.Collections;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.Playables;
using vortex;

public class CamProbe : MonoBehaviour
{
    static readonly StringBuilder s_log = new StringBuilder();
    static string s_state = "idle";

    public static string State() => s_state + "\n" + s_log;

    public static string Clear() { s_log.Clear(); s_state = "idle"; return "ok"; }

    // 撮るズーム候補（カンマ区切り）。既定は記録どおりの画角だけ
    static string s_zooms = "1";
    public static string SetZooms(string csv) { s_zooms = csv; return "zooms " + csv; }

    // 撮る Director（GameObject 名）。SetDirector で選ぶ
    static string s_director = "Azuki-Timeline";

    /// <summary>
    /// 撮る Director を選ぶ。同じスイッチャーを取り合わないよう、ほかの Director は止めて無効にし、選んだものを有効にして再生する。
    /// Play 中だけの変更（Play を抜ければシーンの状態に戻る）。
    /// </summary>
    public static string SetDirector(string name)
    {
        var all = FindObjectsByType<PlayableDirector>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        PlayableDirector target = null;
        foreach (var d in all)
        {
            if (d.gameObject.name == name) { target = d; continue; }
            d.Stop();
            d.gameObject.SetActive(false);
        }
        if (target == null) return "director not found: " + name;
        target.gameObject.SetActive(true);

        // この Timeline のアニメーショントラックがバインドしているキャラだけを有効にし、Character 直下のほかのキャラは隠す
        var chars = new System.Collections.Generic.HashSet<Transform>();
        foreach (var output in target.playableAsset.outputs)
        {
            if (!(output.sourceObject is UnityEngine.Timeline.AnimationTrack track)) continue;
            var b = target.GetGenericBinding(track);
            Transform t = b is Component c ? c.transform : b is GameObject g ? g.transform : null;
            while (t != null && t.parent != null && t.parent.name != "Character") t = t.parent;
            if (t != null && t.parent != null) chars.Add(t);
        }
        var root = chars.Count > 0 ? chars.First().parent : null;
        var shown = new StringBuilder();
        if (root != null)
        {
            foreach (Transform ch in root)
            {
                bool on = chars.Contains(ch);
                ch.gameObject.SetActive(on);
                if (on) shown.Append(ch.name).Append(", ");
            }
        }
        target.Play();
        s_director = name;
        return $"director {name} playing (of {all.Length}); characters: {shown}";
    }

    /// <summary>
    /// 今の Director のアニメーションクリップの Remove Start Offset を切り替えてグラフを作り直す（キャラの立ち位置の確認用）。
    /// アセットを書き換えるので、Play 中でも元に戻らない。確認後に必ず元の値で呼び直す。戻り値は変更前の値の一覧。
    /// </summary>
    public static string SetRemoveStartOffset(bool value)
    {
        var dirGo = GameObject.Find(s_director);
        if (dirGo == null) return "director not found";
        var director = dirGo.GetComponent<PlayableDirector>();
        var sb = new StringBuilder();
        foreach (var output in director.playableAsset.outputs)
        {
            if (!(output.sourceObject is UnityEngine.Timeline.AnimationTrack track)) continue;
            foreach (var clip in track.GetClips())
            {
                if (!(clip.asset is UnityEngine.Timeline.AnimationPlayableAsset a)) continue;
                sb.Append($"{track.name}/{clip.displayName}: {a.removeStartOffset} -> {value}; ");
                a.removeStartOffset = value;
            }
        }
        double t = director.time;
        director.RebuildGraph();
        director.time = t;
        director.Play();
        return sb.ToString();
    }

    /// <param name="railsCsv">試す railOffset をカンマ区切り（例 "-0.1,-0.05,0,0.05,0.1"）。</param>
    public static string Capture(float time, int targetIndex, string railsCsv, string outDir, string tag)
    {
        var dirGo = GameObject.Find(s_director);
        var switcher = FindAnyObjectByType<VirtualCameraSwitcher>();
        if (dirGo == null || switcher == null) return "director or switcher not found";
        var host = new GameObject("_CamProbe").AddComponent<CamProbe>();
        s_state = "running " + tag;
        host.StartCoroutine(host.Run(dirGo.GetComponent<PlayableDirector>(), switcher, time, targetIndex, railsCsv, outDir, tag));
        return "queued " + tag;
    }

    IEnumerator Run(PlayableDirector director, VirtualCameraSwitcher switcher, float time, int targetIndex, string railsCsv, string outDir, string tag)
    {
        director.time = time;
        // 記録トラックが基準値を publish し、カメラが落ち着くまで数フレーム待つ
        for (int i = 0; i < 4; i++) yield return null;
        yield return new WaitForEndOfFrame();

        Directory.CreateDirectory(outDir);
        if (!CameraRecordPlaybackState.TryGet(switcher, out var frame) || frame == null || !frame.IsPlaying)
        {
            s_log.AppendLine($"{tag}: no playback frame");
            s_state = "done " + tag;
            Destroy(gameObject);
            yield break;
        }

        // 記録の再生中はスイッチャーの _fade が更新されないため、指定した番号のカメラを映している側を選ぶ
        float fade = GetFade(switcher);
        bool onB = frame.Prv.hasValue && frame.Prv.cameraIndex == targetIndex && !(frame.Pgm.hasValue && frame.Pgm.cameraIndex == targetIndex);
        if (!(onB ? frame.Prv : frame.Pgm).hasValue || (onB ? frame.Prv : frame.Pgm).cameraIndex != targetIndex)
            s_log.AppendLine($"{tag}: target {targetIndex} not on PGM({frame.Pgm.cameraIndex})/PRV({frame.Prv.cameraIndex})");
        var baseState = onB ? frame.Prv : frame.Pgm;
        var brain = onB ? switcher._reserveCamera : switcher._activeCamera;
        int lookat = onB ? switcher.PrvLookatID : switcher.PgmLookatID;
        var cam = brain.OutputCamera;
        var chief = baseState.cameraIndex >= 0 && baseState.cameraIndex < switcher._inputCameras.Count ? switcher._inputCameras[baseState.cameraIndex] : null;

        var savedPos = cam.transform.position;
        var savedRot = cam.transform.rotation;
        // 画角の基準は記録値（Timeline の Override の FoV が掛かった値ではなく）。候補のズームは記録値に対して掛ける
        float savedFov = cam.fieldOfView;
        float baseFov = baseState.hasFov ? baseState.fov : savedFov;
        var line = new StringBuilder($"{tag}: t={time:F3} fade={fade:F2} bus={(onB ? "B(PRV)" : "A(PGM)")} index={baseState.cameraIndex} chief={(chief != null ? chief.name : "null")} fov={baseFov:F2}");
        foreach (var s in railsCsv.Split(','))
        {
            float r = float.Parse(s, CultureInfo.InvariantCulture);
            Vector3 p = baseState.position;
            Quaternion q = baseState.rotation;
            var search = new CameraRecordRailSearchState();
            bool ok = r == 0f || CameraRecordRailOffset.TryApply(chief, lookat, r, ref search, ref p, ref q);
            if (!ok) { line.Append($" | r={r}: no rail"); continue; }
            cam.transform.SetPositionAndRotation(p, q);
            string rs = r.ToString("+0.000;-0.000;0.000", CultureInfo.InvariantCulture);
            // ズーム候補 k ごとに撮る（画角の tan を 1/k 倍。k > 1 で寄り）。k = 1 は記録どおりの画角
            foreach (var zs in s_zooms.Split(','))
            {
                float k = float.Parse(zs, CultureInfo.InvariantCulture);
                cam.fieldOfView = 2f * Mathf.Rad2Deg * Mathf.Atan(Mathf.Tan(baseFov * 0.5f * Mathf.Deg2Rad) / k);
                string suffix = Mathf.Approximately(k, 1f) ? "" : "_z" + k.ToString("0.000", CultureInfo.InvariantCulture);
                Save(cam, Path.Combine(outDir, $"{tag}_r{rs}{suffix}.png"));
                SaveMask(cam, Path.Combine(outDir, $"{tag}_r{rs}{suffix}_mask.png"));
            }
            cam.fieldOfView = savedFov;
            line.Append($" | r={r}: pos={p}");
        }
        cam.transform.SetPositionAndRotation(savedPos, savedRot);
        s_log.AppendLine(line.ToString());
        s_state = "done " + tag;
        Destroy(gameObject);
    }

    // キャラ（Chara レイヤー）だけを黒背景・ポストプロセス無しで撮る。白い所がキャラ。
    static void SaveMask(Camera cam, string path)
    {
        int mask = cam.cullingMask;
        var flags = cam.clearFlags;
        var bg = cam.backgroundColor;
        var urp = cam.GetComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>();
        bool post = urp != null && urp.renderPostProcessing;
        cam.cullingMask = 1 << LayerMask.NameToLayer("Chara");
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Color.black;
        if (urp != null) urp.renderPostProcessing = false;
        Save(cam, path);
        cam.cullingMask = mask;
        cam.clearFlags = flags;
        cam.backgroundColor = bg;
        if (urp != null) urp.renderPostProcessing = post;
    }

    /// <summary>Timeline のオフセットが効いたままの番組カメラを、指定時刻で撮る（位置・画角に手を加えない）。</summary>
    public static string ShotAsIs(float time, int targetIndex, string path)
    {
        var dirGo = GameObject.Find(s_director);
        var switcher = FindAnyObjectByType<VirtualCameraSwitcher>();
        if (dirGo == null || switcher == null) return "director or switcher not found";
        var host = new GameObject("_CamProbe").AddComponent<CamProbe>();
        s_state = "running asis";
        host.StartCoroutine(host.RunAsIs(dirGo.GetComponent<PlayableDirector>(), switcher, time, targetIndex, path));
        return "queued asis";
    }

    IEnumerator RunAsIs(PlayableDirector director, VirtualCameraSwitcher switcher, float time, int targetIndex, string path)
    {
        director.time = time;
        for (int i = 0; i < 4; i++) yield return null;
        yield return new WaitForEndOfFrame();
        CameraRecordPlaybackState.TryGet(switcher, out var frame);
        bool onB = frame != null && frame.Prv.hasValue && frame.Prv.cameraIndex == targetIndex;
        var cam = (onB ? switcher._reserveCamera : switcher._activeCamera).OutputCamera;
        Save(cam, path);
        s_log.AppendLine($"asis t={time:F3} bus={(onB ? "B" : "A")} pos={cam.transform.position} fov={cam.fieldOfView:F2}");
        s_state = "done asis";
        Destroy(gameObject);
    }

    static float GetFade(VirtualCameraSwitcher switcher)
    {
        var f = typeof(VirtualCameraSwitcher).GetField("_fade", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        return f != null ? (float)f.GetValue(switcher) : -1f;
    }

    static void Save(Camera cam, string path)
    {
        const int W = 640, H = 360;
        var rt = RenderTexture.GetTemporary(W, H, 24);
        var prev = cam.targetTexture;
        cam.targetTexture = rt;
        cam.Render();
        cam.targetTexture = prev;
        var active = RenderTexture.active;
        RenderTexture.active = rt;
        var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, W, H), 0, 0);
        tex.Apply();
        RenderTexture.active = active;
        RenderTexture.ReleaseTemporary(rt);
        File.WriteAllBytes(path, tex.EncodeToPNG());
        Destroy(tex);
    }
}
